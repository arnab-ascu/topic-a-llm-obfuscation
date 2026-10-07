import subprocess
import sys
from pathlib import Path

def main():
    programs = ["program_01", "program_02", "program_03", "program_04", "program_05"]
    types = ["positive", "negative"]

    output_dir = Path("results/metrics_v1_rtx")
    output_dir.mkdir(parents=True, exist_ok=True)

    total_runs = len(programs) * len(types)
    successful_runs = 0

    print(f"Starting Day 4 RTX Metric Extraction across {total_runs} pairs...\n")

    for prog in programs:
        for t in types:
            orig_path = Path(f"data/dataset_v1/{prog}/original.c")
            cand_path = Path(f"data/dataset_v1/{prog}/{t}.c")
            tests_path = Path(f"data/dataset_v1/{prog}/tests.json")
            spec_path = Path("configs/specification_v1.json")
            out_path = output_dir / f"{prog}_{t}.json"

            cmd = [
                sys.executable, "-m", "src.metrics.metric_extractor",
                "--original", str(orig_path),
                "--candidate", str(cand_path),
                "--tests", str(tests_path),
                "--spec", str(spec_path),
                "--compiler", "gcc",
                "--output", str(out_path)
            ]

            print(f"Executing: {prog}_{t}...", end=" ", flush=True)
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print("SUCCESS")
                successful_runs += 1
            else:
                print(f"FAILED (Exit Code {result.returncode})")
                if result.stderr:
                    print(f"   Error details: {result.stderr.strip()}")

    print(f"\nExtraction complete: {successful_runs}/{total_runs} succeeded.")

if __name__ == "__main__":
    main()