from __future__ import annotations
import json
from pathlib import Path
from src.validation.correctness_runner import correctness_check

DATA_ROOT = Path("data/dataset_v1")
RESULT_ROOT = Path("results/correctness_gate_v1")

def main() -> None:
    RESULT_ROOT.mkdir(parents=True,exist_ok=True)
    records = []

    for program_dir in sorted(DATA_ROOT.glob("program_*")):
        original = program_dir / "original.c"
        tests = program_dir / "tests.json"

        for record_type in ("positive","negative"):
            candidate = program_dir / f"{record_type}.c"
            result = correctness_check(original=original,candidate=candidate,tests_path=tests,compiler="clang",timeout=3.0,)

            records.append({
                "program_id": program_dir.name,
                "record_type": record_type,
                "behavior_ok": result["behavior_equivalent"],
                "failure_reason": result["failure_reason"],
                "accepted_by_correctness_gate": (record_type == "positive"and result["behavior_equivalent"]),})

    output = {
        "gate": "CORRECTNESS_V1",
        "program_count": 5,
        "record_count": len(records),
        "records": records,
        "positive_pass_count": sum(record["accepted_by_correctness_gate"] for record in records),}

    output_path = RESULT_ROOT / "correctness_gate_v1.json"
    output_path.write_text(json.dumps(output,indent=2),encoding="utf-8",)
    print(json.dumps(output,indent=2))

if __name__ == "__main__":
    main()