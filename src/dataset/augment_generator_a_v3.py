"""Add validated synthetic loop-transformation examples for Generator A v3.

Place this file at src/dataset/augment_generator_a_v3.py and run:
    python -m src.dataset.augment_generator_a_v3

It preserves dataset_v1 and its existing train/validation/test JSONL files.
It adds programs 06-08 as new training-only source families, validates their
source/target pairs by compilation and differential tests, and writes a new
training JSONL plus configs/generator_a_v3.json.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "configs" / "specification_v1.json"
BASE_CONFIG_PATH = ROOT / "configs" / "generator_a_v2.json"
NEW_TRAIN_PATH = ROOT / "data" / "training_v2" / "generator_a_train.jsonl"
NEW_CONFIG_PATH = ROOT / "configs" / "generator_a_v3.json"

PROGRAMS: list[dict[str, Any]] = [
    {
        "program_id": "program_06",
        "description": "sum a sequence; for-to-while, renaming and identity expression",
        "original": r'''#include <stdio.h>
int main(void) {
    int count;
    if (scanf("%d", &count) != 1 || count < 0) return 0;
    int total = 0;
    for (int i = 0; i < count; ++i) {
        int value;
        if (scanf("%d", &value) != 1) return 0;
        total += value;
    }
    printf("%d\n", total);
    return 0;
}
''',
        "target": r'''#include <stdio.h>
int main(void) {
    int limit;
    if (scanf("%d", &limit) != 1 || limit < 0) return 0;
    int accumulator = 0;
    int index = 0;
    while (index < limit) {
        int item;
        if (scanf("%d", &item) != 1) return 0;
        accumulator = accumulator + (item | 0);
        ++index;
    }
    printf("%d\n", accumulator);
    return 0;
}
''',
        "tests": [
            {"name": "empty", "stdin": "0\n"},
            {"name": "positive_values", "stdin": "3\n1 2 3\n"},
            {"name": "mixed_values", "stdin": "4\n-1 0 2 5\n"},
            {"name": "single_value", "stdin": "1\n9\n"},
        ],
    },
    {
        "program_id": "program_07",
        "description": "count positive values; for-to-while and conditional expression",
        "original": r'''#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1 || n < 0) return 0;
    int positives = 0;
    for (int i = 0; i < n; ++i) {
        int x;
        if (scanf("%d", &x) != 1) return 0;
        if (x > 0) ++positives;
    }
    printf("%d\n", positives);
    return 0;
}
''',
        "target": r'''#include <stdio.h>
int main(void) {
    int length;
    if (scanf("%d", &length) != 1 || length < 0) return 0;
    int positive_count = 0;
    int index = 0;
    while (index < length) {
        int item;
        if (scanf("%d", &item) != 1) return 0;
        positive_count = positive_count + ((item > 0) ? 1 : 0);
        ++index;
    }
    printf("%d\n", positive_count);
    return 0;
}
''',
        "tests": [
            {"name": "empty", "stdin": "0\n"},
            {"name": "mixed", "stdin": "4\n1 -2 0 3\n"},
            {"name": "all_negative", "stdin": "3\n-7 -1 -3\n"},
            {"name": "all_positive", "stdin": "3\n2 4 6\n"},
        ],
    },
    {
        "program_id": "program_08",
        "description": "maximum of a nonempty sequence; for-to-while, renaming and condition expression",
        "original": r'''#include <stdio.h>
int main(void) {
    int n;
    if (scanf("%d", &n) != 1 || n <= 0) return 0;
    int first;
    if (scanf("%d", &first) != 1) return 0;
    int maximum = first;
    for (int i = 1; i < n; ++i) {
        int value;
        if (scanf("%d", &value) != 1) return 0;
        if (value > maximum) maximum = value;
    }
    printf("%d\n", maximum);
    return 0;
}
''',
        "target": r'''#include <stdio.h>
int main(void) {
    int length;
    if (scanf("%d", &length) != 1 || length <= 0) return 0;
    int first_item;
    if (scanf("%d", &first_item) != 1) return 0;
    int highest = first_item;
    int index = 1;
    while (index < length) {
        int item;
        if (scanf("%d", &item) != 1) return 0;
        if ((item > highest) != 0) highest = item;
        ++index;
    }
    printf("%d\n", highest);
    return 0;
}
''',
        "tests": [
            {"name": "single_negative", "stdin": "1\n-4\n"},
            {"name": "mixed", "stdin": "5\n1 5 -3 9 0\n"},
            {"name": "all_negative", "stdin": "4\n-9 -2 -8 -3\n"},
            {"name": "strictly_increasing", "stdin": "4\n1 2 3 4\n"},
        ],
    },
]


def run_checked(command: list[str], *, stdin: str | None = None, timeout: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=ROOT,
    )


def verify_pair(program_dir: Path, tests: list[dict[str, str]], compiler: str, flags: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="generator_a_v3_pair_") as td:
        tmp = Path(td)
        executables: list[Path] = []
        for stem in ("original", "positive"):
            source = program_dir / ("original.c" if stem == "original" else "positive.c")
            exe = tmp / stem
            result = run_checked([compiler, *flags, str(source), "-o", str(exe)], timeout=30)
            if result.returncode != 0:
                raise RuntimeError(
                    f"{program_dir.name}/{source.name} failed compilation:\n{result.stderr}"
                )
            executables.append(exe)

        for test in tests:
            original = run_checked([str(executables[0])], stdin=test["stdin"])
            positive = run_checked([str(executables[1])], stdin=test["stdin"])
            if original.returncode != positive.returncode or original.stdout != positive.stdout:
                raise RuntimeError(
                    f"Differential test failed for {program_dir.name}, case {test['name']!r}.\n"
                    f"Original: rc={original.returncode}, stdout={original.stdout!r}, stderr={original.stderr!r}\n"
                    f"Target:   rc={positive.returncode}, stdout={positive.stdout!r}, stderr={positive.stderr!r}"
                )


def main() -> int:
    for required in (SPEC_PATH, BASE_CONFIG_PATH, ROOT / "data/training_v1/generator_a_train.jsonl"):
        if not required.is_file():
            raise FileNotFoundError(f"Required project file is missing: {required}")

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    base_config = json.loads(BASE_CONFIG_PATH.read_text(encoding="utf-8"))
    compiler = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        raise RuntimeError("No C compiler found (clang, gcc, or cc).")
    flags = list(spec.get("compiler_flags", ["-std=c11"]))

    new_records: list[dict[str, Any]] = []
    for item in PROGRAMS:
        folder = ROOT / "data" / "dataset_v1" / item["program_id"]
        folder.mkdir(parents=True, exist_ok=True)
        original_path = folder / "original.c"
        target_path = folder / "positive.c"
        tests_path = folder / "tests.json"
        original_path.write_text(item["original"], encoding="utf-8")
        target_path.write_text(item["target"], encoding="utf-8")
        tests_path.write_text(json.dumps(item["tests"], indent=2) + "\n", encoding="utf-8")

        verify_pair(folder, item["tests"], compiler, flags)

        prompt = (
            "Task: OBFUSCATE_C\n"
            "Transform the supplied C11 source according to the specification.\n"
            "Preserve observable behavior and function interfaces.\n"
            "Apply all required transformations and avoid forbidden changes.\n"
            "Return only the complete transformed C11 source code.\n"
            "SPECIFICATION_JSON:\n"
            + json.dumps(spec, sort_keys=True)
            + "\nORIGINAL_SOURCE:\n"
            + item["original"]
        )
        new_records.append({
            "example_id": f"{item['program_id']}_positive_v3",
            "program_id": item["program_id"],
            "spec_id": spec.get("spec_id", "SPEC_V1"),
            "transformation_id": "validated_synthetic_loop_transform_v3",
            "split": "train",
            "input_text": prompt,
            "target_text": item["target"],
            "source_path": str(original_path.relative_to(ROOT)),
            "target_path": str(target_path.relative_to(ROOT)),
            "correctness_passed": True,
            "correctness": {"compile_ok": True, "behavior_ok": True, "test_cases_passed": len(item["tests"])},
            "rule_observations": {
                "identifier_transformation_observed": True,
                "control_flow_transformation_observed": True,
                "expression_transformation_observed": True,
            },
            "token_counts": {},
            "synthetic_example": True,
            "description": item["description"],
        })
        print(f"VALIDATED {item['program_id']}: compiled and passed {len(item['tests'])} differential tests")

    train_v1_path = ROOT / "data" / "training_v1" / "generator_a_train.jsonl"
    old_records = [json.loads(line) for line in train_v1_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    old_ids = {record.get("program_id") for record in old_records}
    duplicate_ids = old_ids & {record["program_id"] for record in new_records}
    if duplicate_ids:
        raise ValueError(f"Synthetic program ID collision: {sorted(duplicate_ids)}")

    NEW_TRAIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_records = old_records + new_records
    NEW_TRAIN_PATH.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in all_records),
        encoding="utf-8",
    )

    config = json.loads(json.dumps(base_config))
    config["dataset"]["train"] = "data/training_v2/generator_a_train.jsonl"
    config["output"] = {
        "trainer_dir": "models/checkpoints/generator_a_lora_v3",
        "adapter_dir": "models/checkpoints/generator_a_lora_v3/final_adapter",
        "report_dir": "results/generator_a_v3",
    }
    config["experiment"] = {
        **config.get("experiment", {}),
        "purpose": "expanded_validated_loop_transformation_training_v3",
        "generalization_claim_allowed": False,
        "training_examples_note": (
            "Three additional synthetic training-only programs provide validated for-to-while examples. "
            "Programs 04 and 05 remain validation/test and are not copied into training."
        ),
    }
    NEW_CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print("\nGENERATOR A V3 DATA PREPARATION COMPLETE")
    print(f"Training examples: {len(old_records)} existing + {len(new_records)} synthetic = {len(all_records)}")
    print(f"Training JSONL: {NEW_TRAIN_PATH.relative_to(ROOT)}")
    print(f"New config: {NEW_CONFIG_PATH.relative_to(ROOT)}")
    print("Validation and test files were not modified.")
    print("This remains a small controlled experiment, not a generalization claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
