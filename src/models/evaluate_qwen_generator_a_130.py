"""Evaluate the Qwen 130-program adapter on the held-out 24-program split.

Run from the repository root:
  python -m src.models.evaluate_qwen_generator_a_130 --max-examples 2
  python -m src.models.evaluate_qwen_generator_a_130

This evaluator uses the adapter in models/checkpoints/qwen_130_adapter_incoming
by default. It does not retrain, modify dataset files, or use the old adapter.
For these generated fixed-constant programs, behavior is compared by compiling
and running original/candidate with empty stdin; this is limited differential
testing, not proof of arbitrary-input equivalence.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import torch
from src.models.evaluate_qwen_generator_a import load_qwen, generate_qwen
from src.models.required_transformations import apply_required_transformations
from src.models.evaluate_generator_a import identifiers, scrub_comments_and_literals

ROOT = Path(__file__).resolve().parents[2]
SPLIT_PATH = ROOT / "data/training_expanded/test_130.jsonl"
DATA_ROOT = ROOT / "data/dataset_expanded"
DEFAULT_ADAPTER = ROOT / "models/checkpoints/qwen_130_adapter_incoming"
OUTPUT_ROOT = ROOT / "results/generator_a_qwen_130_eval"
TIMEOUT_SECONDS = 3.0


def choose_compiler() -> str:
    compiler = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        raise RuntimeError("No C compiler found; install clang or GCC.")
    return compiler


def compile_c(source: Path, exe: Path, compiler: str) -> dict[str, Any]:
    cmd = [
        compiler, "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
        str(source), "-o", str(exe),
    ]
    try:
        result = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=20, check=False
        )
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-2000:],
            "command": cmd,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "passed": False, "returncode": None, "stdout": "",
            "stderr": str(exc), "command": cmd,
        }


def run_c(exe: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(exe)], cwd=ROOT, input="", capture_output=True,
            text=True, timeout=TIMEOUT_SECONDS, check=False,
        )
        return {
            "timeout": False,
            "returncode": result.returncode,
            "stdout": result.stdout.replace("\r\n", "\n").strip(),
            "stderr": result.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "timeout": True, "returncode": None,
            "stdout": None, "stderr": "Execution timed out",
        }
    except OSError as exc:
        return {
            "timeout": False, "returncode": None,
            "stdout": None, "stderr": str(exc),
        }


def balanced_delimiters(code: str) -> bool:
    clean = scrub_comments_and_literals(code)
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for char in clean:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack


def identifier_change(original: str, candidate: str) -> dict[str, Any]:
    original_ids = identifiers(original)
    candidate_ids = identifiers(candidate)
    union = original_ids | candidate_ids
    similarity = len(original_ids & candidate_ids) / len(union) if union else 1.0
    return {
        "original_identifier_count": len(original_ids),
        "candidate_identifier_count": len(candidate_ids),
        "jaccard_similarity": similarity,
        "passed": bool(original_ids and candidate_ids and similarity < 1.0),
    }


def loop_kinds(code: str) -> list[str]:
    return re.findall(r"\b(for|while|do)\b", scrub_comments_and_literals(code))


def ternary_count(code: str) -> int:
    return scrub_comments_and_literals(code).count("?")


def pointer_arithmetic(code: str) -> bool:
    clean = scrub_comments_and_literals(code)
    return bool(re.search(
        r"\*\s*\(\s*[A-Za-z_]\w*\s*[+-]\s*\d",
        clean,
    ))


def category_rule(
    program_id: str, original: str, reference: str, candidate: str
) -> dict[str, Any]:
    parts = program_id.split("_")
    category = parts[1] if len(parts) > 1 else "unknown"
    orig_clean = scrub_comments_and_literals(original)
    ref_clean = scrub_comments_and_literals(reference)
    cand_clean = scrub_comments_and_literals(candidate)
    details: dict[str, Any] = {"category": category}

    if category == "loop":
        original_loops = loop_kinds(original)
        reference_loops = loop_kinds(reference)
        candidate_loops = loop_kinds(candidate)
        ref_introduced = Counter(reference_loops) - Counter(original_loops)
        ref_removed = Counter(original_loops) - Counter(reference_loops)
        introduced_ok = all(candidate_loops.count(k) >= n for k, n in ref_introduced.items())
        removed_ok = all(candidate_loops.count(k) <= original_loops.count(k) - n
                         for k, n in ref_removed.items())
        passed = bool(ref_introduced or ref_removed) and introduced_ok and removed_ok
        details.update({
            "rule": "loop-control-form change matching reference transformation",
            "original_loop_kinds": original_loops,
            "reference_loop_kinds": reference_loops,
            "candidate_loop_kinds": candidate_loops,
            "passed": passed,
        })
    elif category == "cond":
        orig_q = ternary_count(original)
        ref_q = ternary_count(reference)
        cand_q = ternary_count(candidate)
        expected_increase = ref_q > orig_q
        passed = cand_q > orig_q if expected_increase else cand_q != orig_q
        details.update({
            "rule": "conditional-expression rewrite matching reference transformation",
            "original_ternary_count": orig_q,
            "reference_ternary_count": ref_q,
            "candidate_ternary_count": cand_q,
            "passed": passed,
        })
    elif category == "arr":
        ref_pointer = pointer_arithmetic(reference)
        candidate_pointer = pointer_arithmetic(candidate)
        passed = (not ref_pointer) or candidate_pointer
        details.update({
            "rule": "pointer-arithmetic rewrite matching reference transformation",
            "reference_uses_pointer_arithmetic": ref_pointer,
            "candidate_uses_pointer_arithmetic": candidate_pointer,
            "passed": passed,
        })
    elif category == "math":
        original_loops = loop_kinds(original)
        reference_loops = loop_kinds(reference)
        candidate_loops = loop_kinds(candidate)
        original_q = ternary_count(original)
        reference_q = ternary_count(reference)
        candidate_q = ternary_count(candidate)
        loop_expected = len(reference_loops) > len(original_loops)
        ternary_removed = reference_q < original_q
        loop_ok = (not loop_expected) or len(candidate_loops) > len(original_loops)
        ternary_ok = (not ternary_removed) or candidate_q < original_q
        passed = (loop_expected or ternary_removed) and loop_ok and ternary_ok
        details.update({
            "rule": "recursive/conditional math rewrite toward iterative reference",
            "original_loop_kinds": original_loops,
            "reference_loop_kinds": reference_loops,
            "candidate_loop_kinds": candidate_loops,
            "original_ternary_count": original_q,
            "reference_ternary_count": reference_q,
            "candidate_ternary_count": candidate_q,
            "passed": passed,
        })
    else:
        details.update({
            "rule": "no category-specific rule available",
            "passed": False,
        })
    details["methodology_note"] = (
        "Category-specific lexical proxies are inferred from each dataset "
        "category's stored positive.c pattern; they are not AST proofs."
    )
    return details


def assess(
    row: dict[str, Any],
    candidate_name: str,
    candidate_code: str,
    compiler: str,
    output_dir: Path,
    index: int,
) -> dict[str, Any]:
    pid = str(row["program_id"])
    program_dir = DATA_ROOT / pid
    original_path = program_dir / "original.c"
    reference_path = program_dir / "positive.c"
    if not original_path.is_file() or not reference_path.is_file():
        raise FileNotFoundError(f"Missing original/positive C file for {pid}")
    original = original_path.read_text(encoding="utf-8")
    reference = reference_path.read_text(encoding="utf-8")

    cand_dir = output_dir / "candidates"
    exe_dir = output_dir / "executables"
    cand_dir.mkdir(parents=True, exist_ok=True)
    exe_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = cand_dir / f"{pid}_{candidate_name}.c"
    candidate_path.write_text(candidate_code, encoding="utf-8")

    original_exe = exe_dir / f"{pid}_original"
    candidate_exe = exe_dir / f"{pid}_{candidate_name}"
    original_compile = compile_c(original_path, original_exe, compiler)
    candidate_compile = compile_c(candidate_path, candidate_exe, compiler)

    behavior: dict[str, Any]
    if not original_compile["passed"]:
        behavior = {
            "status": "NOT_EVALUATED",
            "reason": "Original program failed compilation",
            "passed_cases": 0,
            "total_cases": 1,
        }
    elif not candidate_compile["passed"]:
        behavior = {
            "status": "NOT_EVALUATED",
            "reason": "Candidate failed compilation",
            "passed_cases": 0,
            "total_cases": 1,
        }
    else:
        original_run = run_c(original_exe)
        candidate_run = run_c(candidate_exe)
        same = (
            not original_run["timeout"] and not candidate_run["timeout"]
            and original_run["returncode"] == candidate_run["returncode"]
            and original_run["stdout"] == candidate_run["stdout"]
        )
        behavior = {
            "status": "PASS" if same else "FAIL",
            "passed_cases": 1 if same else 0,
            "total_cases": 1,
            "input": "",
            "comparison": "stdout and return code under empty stdin",
            "original": original_run,
            "candidate": candidate_run,
        }

    ids = identifier_change(original, candidate_code)
    category = category_rule(pid, original, reference, candidate_code)
    shape_ok = (
        len(candidate_code.strip()) >= 20
        and bool(re.search(r"\bmain\s*\(", scrub_comments_and_literals(candidate_code)))
        and balanced_delimiters(candidate_code)
    )
    accepted = (
        original_compile["passed"]
        and candidate_compile["passed"]
        and behavior["status"] == "PASS"
        and ids["passed"]
        and category["passed"]
        and shape_ok
    )
    return {
        "program_id": pid,
        "category": pid.split("_")[1] if len(pid.split("_")) > 1 else "unknown",
        "candidate_name": candidate_name,
        "candidate_path": str(candidate_path.relative_to(ROOT)),
        "original_compile": original_compile,
        "candidate_compile": candidate_compile,
        "shape_proxy_pass": shape_ok,
        "identifier_transformation": ids,
        "category_transformation": category,
        "behavior": behavior,
        "accepted": accepted,
    }


def evaluate(args: argparse.Namespace) -> int:
    adapter_path = Path(args.adapter_path)
    if not adapter_path.is_absolute():
        adapter_path = ROOT / adapter_path
    for required_file in ("adapter_config.json", "adapter_model.safetensors"):
        if not (adapter_path / required_file).is_file():
            raise FileNotFoundError(f"Adapter file missing: {adapter_path / required_file}")
    if not SPLIT_PATH.is_file():
        raise FileNotFoundError(f"Test split missing: {SPLIT_PATH}")

    rows = [
        json.loads(line)
        for line in SPLIT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.max_examples:
        rows = rows[:args.max_examples]
    if not rows:
        raise ValueError("Test split is empty.")
    compiler = choose_compiler()
    output_dir = OUTPUT_ROOT / "test"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Test examples: {len(rows)}")
    print(f"Adapter: {adapter_path}")
    print(f"Compiler: {compiler}")
    print("Loading Qwen once; generated results will be evaluated as raw and repaired candidates.")
    model, tokenizer = load_qwen(adapter_path)

    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        pid = str(row.get("program_id", ""))
        if not pid:
            raise ValueError(f"Test record {index} has no program_id.")
        original = (DATA_ROOT / pid / "original.c").read_text(encoding="utf-8")
        print(f"\n[{index}/{len(rows)}] Generating {pid}...")
        raw_code = generate_qwen(model, tokenizer, row["input_text"])
        attempts = [
            assess(row, "raw", raw_code, compiler, output_dir, index)
        ]
        repaired, repair_steps = apply_required_transformations(raw_code)
        if repair_steps and repaired.strip() != raw_code.strip():
            repaired_result = assess(
                row, "repaired", repaired, compiler, output_dir, index
            )
            repaired_result["repair_steps"] = repair_steps
            attempts.append(repaired_result)

        accepted = [item for item in attempts if item["accepted"]]
        if accepted:
            selected = accepted[0]
        else:
            selected = max(
                attempts,
                key=lambda item: (
                    item["candidate_compile"]["passed"],
                    item["behavior"]["status"] == "PASS",
                    item["identifier_transformation"]["passed"],
                    item["category_transformation"]["passed"],
                ),
            )
        record = {
            "program_id": pid,
            "category": pid.split("_")[1],
            "selected_candidate": selected["candidate_name"],
            "accepted": selected["accepted"],
            "attempts": attempts,
        }
        records.append(record)
        print(
            f"  selected={selected['candidate_name']} "
            f"compile={selected['candidate_compile']['passed']} "
            f"identifier={selected['identifier_transformation']['passed']} "
            f"category_rule={selected['category_transformation']['passed']} "
            f"behavior={selected['behavior']['status']} "
            f"accepted={selected['accepted']}"
        )

    categories: dict[str, dict[str, int]] = {}
    for record in records:
        key = record["category"]
        categories.setdefault(key, {"count": 0, "accepted": 0})
        categories[key]["count"] += 1
        categories[key]["accepted"] += int(record["accepted"])

    report = {
        "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "adapter_path": str(adapter_path),
        "split": "held_out_test",
        "split_file": str(SPLIT_PATH.relative_to(ROOT)),
        "program_count": len(records),
        "accepted_count": sum(int(r["accepted"]) for r in records),
        "category_summary": categories,
        "records": records,
        "limitations": [
            "The programs are generated with fixed constants; behavior comparison uses empty stdin.",
            "Each program receives one deterministic generation in this run.",
            "Category transformation checks are lexical proxies inferred from positive.c, not AST proofs.",
            "The evaluator can assess a deterministic repair alternative; inspect selected_candidate and attempts to distinguish raw and repaired results.",
        ],
    }
    report_path = output_dir / "evaluation_130.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n========== HELD-OUT SUMMARY ==========")
    print(f"Accepted: {report['accepted_count']}/{report['program_count']}")
    for category, values in categories.items():
        print(f"{category}: {values['accepted']}/{values['count']}")
    print(f"Report: {report_path.relative_to(ROOT)}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--adapter-path",
        default=str(DEFAULT_ADAPTER),
        help="Adapter directory; defaults to qwen_130_adapter_incoming.",
    )
    parser.add_argument(
        "--max-examples", type=int, default=None,
        help="Optional small smoke-test limit; omit to evaluate all 24 test records.",
    )
    args = parser.parse_args()
    evaluate(args)


if __name__ == "__main__":
    main()
