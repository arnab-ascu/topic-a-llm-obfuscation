"""Locally test the deterministic fallback against dataset C programs.

Run from the repository root:
    python /path/to/check_hybrid_fallback.py

The script compiles both each original C program and its fallback-transformed
version with the local macOS compiler, then compares stdout and return codes on
the stdin cases in that program's tests.json. Windows .exe files are never run.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA_ROOT = ROOT / "data" / "dataset_v1"
REPORT_PATH = ROOT / "results" / "hybrid_fallback_local_check.json"
INPUT_KEYS = ("stdin", "input", "input_data", "stdin_text")


def load_cases(path: Path) -> list[tuple[str, str]]:
    """Return (name, stdin) pairs from common JSON test layouts."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc

    if isinstance(raw, dict):
        cases: Any = None
        for key in ("tests", "test_cases", "cases", "inputs", "stdin_cases"):
            if isinstance(raw.get(key), list):
                cases = raw[key]
                break
        if cases is None:
            raise ValueError(f"No case list found in {path}")
    elif isinstance(raw, list):
        cases = raw
    else:
        raise ValueError(f"Unsupported JSON layout in {path}")

    parsed: list[tuple[str, str]] = []
    for index, case in enumerate(cases, start=1):
        if isinstance(case, str):
            parsed.append((str(index), case))
            continue
        if not isinstance(case, dict):
            continue
        value = next((case[key] for key in INPUT_KEYS if key in case), None)
        if value is None:
            continue
        if isinstance(value, list):
            stdin = " ".join(str(item) for item in value)
        elif isinstance(value, str):
            stdin = value
        else:
            stdin = str(value)
        parsed.append((str(case.get("name", index)), stdin))

    return parsed


def compile_c(compiler: str, source_path: Path, exe_path: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [compiler, "-std=c11", "-Wall", "-Wextra", "-Wpedantic", str(source_path), "-o", str(exe_path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        return {
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stderr": proc.stderr[-3000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "returncode": None, "stderr": str(exc)}


def run_case(exe_path: Path, stdin: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [str(exe_path)],
            cwd=ROOT,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": exc.stdout,
            "stderr": "Execution timed out after 3 seconds.",
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "returncode": None,
            "stdout": None,
            "stderr": str(exc),
            "timed_out": False,
        }


def main() -> int:
    if not DATA_ROOT.is_dir():
        print(f"ERROR: run this from repository root; not found: {DATA_ROOT}", file=sys.stderr)
        return 2

    compiler = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        print("ERROR: No C compiler found (clang, gcc, or cc).", file=sys.stderr)
        return 2

    try:
        from src.models.hybrid_fallback import apply_ast_fallback_obfuscation
    except Exception as exc:
        print(f"ERROR: Could not import fallback: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    report: dict[str, Any] = {
        "compiler": compiler,
        "platform": sys.platform,
        "scope": "local fallback smoke test; not a proof of AST correctness or generalization",
        "programs": [],
    }

    directories = sorted(DATA_ROOT.glob("program_*"))
    for program_dir in directories:
        original_path = program_dir / "original.c"
        tests_path = program_dir / "tests.json"
        if not original_path.is_file():
            continue

        original_code = original_path.read_text(encoding="utf-8")
        transformed_code = apply_ast_fallback_obfuscation(original_code)
        item: dict[str, Any] = {
            "program_id": program_dir.name,
            "original_path": str(original_path.relative_to(ROOT)),
            "fallback_nonempty": bool(transformed_code.strip()),
        }

        try:
            cases = load_cases(tests_path) if tests_path.is_file() else []
            item["test_case_count"] = len(cases)
        except ValueError as exc:
            cases = []
            item["test_case_count"] = 0
            item["test_case_parse_error"] = str(exc)

        with tempfile.TemporaryDirectory(prefix=f"fallback_{program_dir.name}_") as tmp:
            tmpdir = Path(tmp)
            original_exe = tmpdir / "original_program"
            candidate_source = tmpdir / "candidate.c"
            candidate_exe = tmpdir / "candidate_program"
            candidate_source.write_text(transformed_code, encoding="utf-8")

            item["original_compile"] = compile_c(compiler, original_path, original_exe)
            item["candidate_compile"] = compile_c(compiler, candidate_source, candidate_exe)

            comparisons: list[dict[str, Any]] = []
            if item["original_compile"]["passed"] and item["candidate_compile"]["passed"] and cases:
                for case_name, stdin in cases:
                    original_result = run_case(original_exe, stdin)
                    candidate_result = run_case(candidate_exe, stdin)
                    same = (
                        not original_result["timed_out"]
                        and not candidate_result["timed_out"]
                        and original_result["returncode"] == candidate_result["returncode"]
                        and original_result["stdout"] == candidate_result["stdout"]
                    )
                    comparisons.append({
                        "case": case_name,
                        "passed": same,
                        "original": original_result,
                        "candidate": candidate_result,
                    })
            elif not cases:
                item["behavior_status"] = "NOT_EVALUATED_NO_TEST_INPUTS"

            if comparisons:
                item["cases_passed"] = sum(1 for case in comparisons if case["passed"])
                item["cases_total"] = len(comparisons)
                item["behavior_status"] = "PASS" if item["cases_passed"] == len(comparisons) else "FAIL"
                item["case_results"] = comparisons
            elif item.get("behavior_status") is None:
                item["behavior_status"] = "NOT_EVALUATED_COMPILE_FAILURE"

        print(
            f"[{program_dir.name}] original_compile={item['original_compile']['passed']} "
            f"fallback_compile={item['candidate_compile']['passed']} "
            f"behavior={item['behavior_status']} "
            f"({item.get('cases_passed', 0)}/{item.get('cases_total', 0)} cases)"
        )
        report["programs"].append(item)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport: {REPORT_PATH.relative_to(ROOT)}")
    print("A PASS means only that the listed local test inputs matched; it does not certify all possible inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
