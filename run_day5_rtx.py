import json
import sys
from pathlib import Path
from src.validation.correctness_runner import correctness_check

DATA_ROOT = Path("data/dataset_v1")
RESULT_ROOT = Path("results/correctness_gate_v1_rtx")

def main() -> None:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    records = []

    print("Starting Day 5 RTX Correctness Gate Validation (GCC)...\n")

    for program_dir in sorted(DATA_ROOT.glob("program_*")):
        original = program_dir / "original.c"
        tests_path = program_dir / "tests.json"

        for record_type in ("positive", "negative"):
            candidate = program_dir / f"{record_type}.c"
            
            # Execute low-level correctness check using MinGW GCC
            result = correctness_check(
                original=original,
                candidate=candidate,
                tests_path=tests_path,
                compiler="gcc",
                timeout=3.0
            )

            # Day 5 gate acceptance condition:
            # Must be a positive candidate AND pass behavioral equivalence
            accepted = (record_type == "positive") and result["behavior_equivalent"]

            record_entry = {
                "program_id": program_dir.name,
                "record_type": record_type,
                "behavior_ok": result["behavior_equivalent"],
                "failure_reason": result["failure_reason"],
                "accepted_by_correctness_gate": accepted
            }
            records.append(record_entry)

            status = "ACCEPT" if accepted else f"REJECT ({result['failure_reason'] or 'INTENTIONAL_NEGATIVE'})"
            print(f"[{program_dir.name}] {record_type.upper():<8} -> {status}")

    output = {
        "gate": "CORRECTNESS_V1_RTX",
        "compiler": "gcc",
        "program_count": 5,
        "record_count": len(records),
        "positive_pass_count": sum(
            1 for r in records if r["accepted_by_correctness_gate"]
        ),
        "records": records
    }

    output_path = RESULT_ROOT / "correctness_gate_v1.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    
    print(f"\nGate Complete: {output['positive_pass_count']}/5 positive candidates accepted.")
    print(f"Results saved to: {output_path}")

if __name__ == "__main__":
    main()