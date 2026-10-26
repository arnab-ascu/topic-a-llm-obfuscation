import json
from pathlib import Path
from src.controller.pipeline import RetryController

def evaluate_heldout_test_set():
    ROOT = Path(".")
    test_file = ROOT / "data/training_expanded/test_130.jsonl"
    
    if not test_file.exists():
        print("Error: data/training_expanded/test_130.jsonl not found!")
        return

    test_records = [json.loads(l) for l in test_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    controller = RetryController(max_retries=3)
    
    results = []
    first_attempt_passes = 0
    eventual_passes = 0

    print(f"\n=== DAY 13: HELDOUT TEST SET EVALUATION ({len(test_records)} Untouched Programs) ===")

    for item in test_records:
        prog_id = item["program_id"]
        raw_input = item["input_text"]

        res = controller.run_pipeline(prog_id, raw_input)
        results.append({
            "program_id": prog_id,
            "final_attempt": res["final_attempt"],
            "decision": res["decision"],
            "history_length": len(res["history"])
        })

        if res["final_attempt"] == 1:
            first_attempt_passes += 1
        if "ACCEPT" in res["decision"]:
            eventual_passes += 1

    total = len(test_records)
    print("\n=======================================================")
    print("           DAY 13 FINAL EVALUATION SUMMARY             ")
    print("=======================================================")
    print(f"Total Test Programs         : {total}")
    print(f"First-Attempt Acceptance Rate: {first_attempt_passes}/{total} ({first_attempt_passes/total*100:.1f}%)")
    print(f"Eventual Acceptance Rate    : {eventual_passes}/{total} ({eventual_passes/total*100:.1f}%)")
    print("=======================================================\n")

    out_file = ROOT / "results/day13_test_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Detailed results report saved to {out_file}")

if __name__ == "__main__":
    evaluate_heldout_test_set()