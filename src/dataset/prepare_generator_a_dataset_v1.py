from __future__ import annotations
import json
from pathlib import Path
from transformers import AutoTokenizer

ROOT = Path(".")
SPEC_PATH = ROOT / "configs/specification_v1.json"
DATASET_PATH = ROOT / "data/dataset_v1/dataset_v1.json"
GATE_PATH = ROOT / "results/correctness_gate_v1/correctness_gate_v1.json"
METRICS_ROOT = ROOT / "results/metrics_v1"
TOKENIZER_PATH = ROOT / "models/base/codet5-small"
OUTPUT_ROOT = ROOT / "data/training_v1"
MAX_TOKENS = 512

SPLIT_BY_PROGRAM = {
    "program_01": "train",
    "program_02": "train",
    "program_03": "train",
    "program_04": "validation",
    "program_05": "test",
}

REQUIRED_FLAGS = [
    "identifier_transformation_observed",
    "control_flow_transformation_observed",
    "expression_transformation_observed",
]

def read_json(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

def main() -> None:
    spec = read_json(SPEC_PATH)
    dataset = read_json(DATASET_PATH)
    gate = read_json(GATE_PATH)

    tokenizer = AutoTokenizer.from_pretrained(str(TOKENIZER_PATH),local_files_only=True,)
    gate_lookup = {(record["program_id"], record["record_type"]): record for record in gate["records"]}
    positive_pairs = sorted((record for record in dataset if record["record_type"] == "positive"),key=lambda record: record["program_id"],)

    if not positive_pairs:
        raise ValueError("No positive examples found in Dataset v1.")

    if len(positive_pairs) != len(SPLIT_BY_PROGRAM):
        raise ValueError(
            "Unexpected positive-example count. "
            "Review the split assignment before continuing."
        )

    spec_text = json.dumps(spec, separators=(",", ":"), sort_keys=True)
    examples = []

    for pair in positive_pairs:
        program_id = pair["program_id"]

        if program_id not in SPLIT_BY_PROGRAM:
            raise ValueError(f"No split assigned to {program_id}.")

        gate_record = gate_lookup.get((program_id, "positive"))

        if not gate_record or not gate_record["accepted_by_correctness_gate"]:
            raise ValueError(f"{program_id} has not passed the correctness gate.")

        original_path = ROOT / Path(pair["original_path"].replace("\\", "/"))
        target_path = ROOT / Path(pair["candidate_path"].replace("\\", "/"))
        metrics_path = METRICS_ROOT / f"{program_id}_positive.json"

        original_source = original_path.read_text(encoding="utf-8")
        target_source = target_path.read_text(encoding="utf-8").rstrip() + "\n"

        metrics = read_json(metrics_path)
        flags = metrics["specification_flags"]

        failed_flags = [name for name in REQUIRED_FLAGS if not flags.get(name, False)]

        if failed_flags:
            raise ValueError(
                f"{program_id} is missing required transformation "
                f"evidence: {failed_flags}"
            )

        if not flags.get("code_growth_within_limit", False):
            raise ValueError(f"{program_id} exceeds the code-growth limit.")

        if not metrics["runtime_limit"]["within_limit"]:
            raise ValueError(f"{program_id} exceeds the runtime limit.")

        input_text = (
            "Task: OBFUSCATE_C\n"
            "Transform the supplied C11 source according to the specification.\n"
            "Preserve observable behavior and function interfaces.\n"
            "Apply all required transformations and avoid forbidden changes.\n"
            "Return only the complete transformed C11 source code.\n"
            f"SPECIFICATION_JSON:\n{spec_text}\n"
            f"INPUT_C_SOURCE:\n{original_source.rstrip()}\n"
        )

        input_tokens = len(tokenizer.encode(input_text))
        target_tokens = len(tokenizer.encode(target_source))

        if input_tokens > MAX_TOKENS or target_tokens > MAX_TOKENS:
            raise ValueError(
                f"{program_id} exceeds CodeT5's configured "
                f"{MAX_TOKENS}-token example limit "
                f"(input={input_tokens}, target={target_tokens}). "
                "Do not silently truncate C source."
            )

        examples.append({
            "example_id": f"{program_id}_{pair['transformation_id']}",
            "program_id": program_id,
            "spec_id": spec["spec_id"],
            "transformation_id": pair["transformation_id"],
            "split": SPLIT_BY_PROGRAM[program_id],
            "input_text": input_text,
            "target_text": target_source,
            "source_path": str(pair["original_path"]),
            "target_path": str(pair["candidate_path"]),
            "correctness": {
                "behavior_ok": gate_record["behavior_ok"],
                "accepted_by_correctness_gate": (gate_record["accepted_by_correctness_gate"]),
            },
            "rule_observations": {name: flags[name] for name in REQUIRED_FLAGS},
            "metric_record_path": str(metrics_path),
            "token_counts": {
                "input": input_tokens,"target": target_tokens,},
        })

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    split_records = {
        split: [example for example in examples if example["split"] == split]
        for split in ("train", "validation", "test")
    }

    write_jsonl(OUTPUT_ROOT / "generator_a_all.jsonl", examples)
    for split, records in split_records.items():
        write_jsonl(OUTPUT_ROOT / f"generator_a_{split}.jsonl", records)

    manifest = {
        "dataset_id": "GENERATOR_A_SFT_V1",
        "spec_id": spec["spec_id"],
        "base_model": "Salesforce/codet5-small",
        "source_dataset": "Dataset v1",
        "example_count": len(examples),
        "split_counts": {
            split: len(records) for split, records in split_records.items()
        },
        "split_assignment": SPLIT_BY_PROGRAM,
        "target_format": "C source code only",
        "split_policy": "Group by original program to prevent source leakage.",
        "limitations": [
            "Five original programs are only a pipeline smoke dataset.",
            "Expand the corpus before making meaningful training or "
            "generalization claims.",
            "Keep the test split untouched during fine-tuning and selection.",
        ],
    }

    (OUTPUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2),encoding="utf-8",)

    print("GENERATOR A DATASET PREPARED")
    print(f"Total examples: {len(examples)}")
    for split, records in split_records.items():
        print(f"{split}: {len(records)}")
    print(f"Output directory: {OUTPUT_ROOT}")
    print("Note: this is a small pipeline-validation dataset, not a")
    print("research-scale training corpus.")

if __name__ == "__main__":
    main()