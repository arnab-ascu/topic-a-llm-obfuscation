"""Generator A v2: compact-prompt CodeT5 fine-tuning with LoRA.

Run preflight:
    python -m src.models.train_generator_a --config configs/generator_a_v2.json --preflight

Run the controlled fit diagnostic:
    TOKENIZERS_PARALLELISM=false python -m src.models.train_generator_a --config configs/generator_a_v2.json --max-steps 500

Important: the current dataset has only three training examples. This is a pipeline/overfit diagnostic, not evidence of generalization.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from transformers import (
    AutoConfig,
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    set_seed,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "generator_a_v2.json"

INPUT_KEYS = ("input_text", "prompt_text", "model_input", "prompt", "instruction", "input", "source_text", "source_code", "source")
TARGET_KEYS = ("target_text", "target_code", "candidate_text", "obfuscated_code", "completion", "output_text", "output", "target", "answer")
PROGRAM_ID_KEYS = ("original_program_id", "source_program_id", "program_id", "program_key")
CORRECTNESS_FLAG_KEYS = ("correctness_passed", "correctness_gate_passed", "passed_correctness_gate", "semantic_valid")


def compact_obfuscation_prompt(raw_prompt: str) -> str:
    """Drop the verbose JSON spec wrapper; retain the actual original C source.

    Current dataset records place the original source in the input after the
    embedded specification. The examples are full C programs and start with
    #include. If no source can be located, fail loudly rather than train on an
    irrelevant or truncated prompt.
    """
    import re

    matches = list(re.finditer(r"(?m)^[ \t]*#[ \t]*include\b", raw_prompt))
    if matches:
        source = raw_prompt[matches[0].start():].strip()
    else:
        # Support records that delimit code without an include directive.
        marker_patterns = (
            r"(?is)(?:ORIGINAL_SOURCE|SOURCE_CODE|C_SOURCE|ORIGINAL_C_SOURCE|SOURCE):\s*",
        )
        source = ""
        for pattern in marker_patterns:
            match = re.search(pattern, raw_prompt)
            if match:
                source = raw_prompt[match.end():].strip()
                break
        if not source or not re.search(r"\b(?:main|return|printf|scanf)\b", source):
            raise ValueError(
                "Could not extract the original C source from input_text. "
                "Expected a line beginning with #include or a SOURCE_CODE marker."
            )

    return (
        "Task: OBFUSCATE_C11\n"
        "Apply all required source transformations: identifier transformation, "
        "control-flow transformation, and expression transformation.\n"
        "Preserve observable input/output behavior, return values, and public "
        "function signatures. Do not introduce undefined behavior.\n"
        "Return only the complete transformed C11 source code.\n"
        "SOURCE_CODE:\n"
        f"{source}\n"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_of(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def get_device_summary() -> dict[str, Any]:
    if torch.cuda.is_available():
        device, name = "cuda", torch.cuda.get_device_name(0)
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device, name = "mps", "Apple Metal Performance Shaders"
    else:
        device, name = "cpu", platform.processor() or "CPU"
    return {
        "selected_device": device,
        "device_name": name,
        "cuda_available": torch.cuda.is_available(),
        "mps_available": hasattr(torch.backends, "mps") and torch.backends.mps.is_available(),
    }


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Configuration not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    required = ("model_name_or_path", "dataset", "output", "tokenization", "training", "lora", "generation", "experiment")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Configuration is missing sections: {missing}")
    return config


def _mappings(record: dict[str, Any]) -> list[dict[str, Any]]:
    result = [record]
    for key in ("metadata", "example", "data", "record"):
        value = record.get(key)
        if isinstance(value, dict):
            result.append(value)
    return result


def _first_value(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for mapping in _mappings(record):
        for key in keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def get_program_id(record: dict[str, Any]) -> str | None:
    for mapping in _mappings(record):
        for key in PROGRAM_ID_KEYS:
            value = mapping.get(key)
            if value is not None and str(value).strip():
                return str(value)
    return None


def record_mappings(record: dict[str, Any]) -> list[dict[str, Any]]:
    return _mappings(record)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset split not found: {path}")
    examples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path.name}, line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path.name}, line {line_number} must be a JSON object")
            raw_input = _first_value(record, INPUT_KEYS)
            target = _first_value(record, TARGET_KEYS)
            if raw_input is None or target is None:
                raise ValueError(
                    f"Cannot identify input/target in {path.name}, line {line_number}. "
                    f"Available keys: {sorted(record.keys())}"
                )
            for mapping in _mappings(record):
                for flag in CORRECTNESS_FLAG_KEYS:
                    if mapping.get(flag) is False:
                        raise ValueError(f"{path.name} line {line_number}: {flag}=false")
            examples.append({
                "input_text": compact_obfuscation_prompt(raw_input),
                "raw_input_text": raw_input,
                "target_text": target,
                "program_id": get_program_id(record),
                "original_record": record,
                "line_number": line_number,
            })
    if not examples:
        raise ValueError(f"Dataset split is empty: {path}")
    return examples


def assert_no_split_leakage(splits: dict[str, list[dict[str, Any]]]) -> None:
    names = list(splits)
    for i, left_name in enumerate(names):
        for right_name in names[i + 1:]:
            left, right = splits[left_name], splits[right_name]
            ids_left = {x["program_id"] for x in left if x["program_id"] is not None}
            ids_right = {x["program_id"] for x in right if x["program_id"] is not None}
            if ids_left & ids_right:
                raise ValueError(f"Program leakage between {left_name} and {right_name}: {sorted(ids_left & ids_right)}")
            prompts_left = {hashlib.sha256(x["input_text"].encode()).hexdigest() for x in left}
            prompts_right = {hashlib.sha256(x["input_text"].encode()).hexdigest() for x in right}
            if prompts_left & prompts_right:
                raise ValueError(f"Identical compact prompts occur in {left_name} and {right_name}")


def check_dependencies() -> None:
    missing = [name for name in ("peft", "accelerate") if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("Missing dependencies: " + ", ".join(missing) + ". Install with: python -m pip install peft accelerate")


def prepare_and_validate(config_path: Path):
    check_dependencies()
    config = load_config(config_path)
    model_path = (ROOT / config["model_name_or_path"]).resolve()
    if not model_path.is_dir():
        raise FileNotFoundError(f"Local base model directory not found: {model_path}")
    spec_path = (ROOT / config["experiment"]["specification"]).resolve()
    if not spec_path.is_file():
        raise FileNotFoundError(f"Specification not found: {spec_path}")
    data_paths = {split: (ROOT / path).resolve() for split, path in config["dataset"].items()}
    if set(data_paths) != {"train", "validation", "test"}:
        raise ValueError("Dataset config must contain train, validation and test")
    splits = {split: read_jsonl(path) for split, path in data_paths.items()}
    assert_no_split_leakage(splits)
    AutoConfig.from_pretrained(str(model_path), local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    max_source = int(config["tokenization"]["max_source_length"])
    max_target = int(config["tokenization"]["max_target_length"])
    lengths: dict[str, Any] = {}
    for split_name, examples in splits.items():
        src_lens, tgt_lens = [], []
        for row in examples:
            src = tokenizer(row["input_text"], add_special_tokens=True, truncation=False)["input_ids"]
            tgt = tokenizer(row["target_text"], add_special_tokens=True, truncation=False)["input_ids"]
            src_lens.append(len(src)); tgt_lens.append(len(tgt))
            if len(src) > max_source:
                raise ValueError(f"{split_name} line {row['line_number']}: compact prompt has {len(src)} tokens; limit={max_source}")
            if len(tgt) > max_target:
                raise ValueError(f"{split_name} line {row['line_number']}: target has {len(tgt)} tokens; limit={max_target}")
        lengths[split_name] = {"source_token_lengths": src_lens, "target_token_lengths": tgt_lens}
    config["_resolved_model_path"] = str(model_path)
    config["_resolved_specification_path"] = str(spec_path)
    config["_resolved_dataset_paths"] = {k: str(v) for k, v in data_paths.items()}
    config["_length_report"] = lengths
    return config, splits, tokenizer


class TokenizedCodeDataset(torch.utils.data.Dataset):
    def __init__(self, examples, tokenizer, max_source_length, max_target_length):
        self.items = []
        for row in examples:
            source = tokenizer(row["input_text"], add_special_tokens=True, truncation=False)
            target = tokenizer(row["target_text"], add_special_tokens=True, truncation=False)
            if len(source["input_ids"]) > max_source_length or len(target["input_ids"]) > max_target_length:
                raise ValueError("An example exceeds the configured token limit; refusing silent truncation")
            self.items.append({"input_ids": source["input_ids"], "attention_mask": source["attention_mask"], "labels": target["input_ids"]})
    def __len__(self):
        return len(self.items)
    def __getitem__(self, index):
        return self.items[index]


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _base_report(config, config_path, splits) -> dict[str, Any]:
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": config["experiment"].get("purpose", "pipeline_smoke_test"),
        "generalization_claim_allowed": False,
        "dataset_counts": {k: len(v) for k, v in splits.items()},
        "dataset_sha256": {k: sha256_file(Path(config["_resolved_dataset_paths"][k])) for k in splits},
        "config_sha256": sha256_file(config_path),
        "specification_sha256": sha256_file(Path(config["_resolved_specification_path"])),
        "model_path": config["_resolved_model_path"],
        "git_commit": _git_commit(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "transformers_version": version_of("transformers"),
        "peft_version": version_of("peft"),
        "accelerate_version": version_of("accelerate"),
        "prompt_strategy": "compact task instruction + original C source extracted from input_text",
        "lora_config": config["lora"],
        **get_device_summary(),
        "token_length_report": config["_length_report"],
    }


def run_preflight(config, config_path, splits):
    report = _base_report(config, config_path, splits)
    report["status"] = "PREFLIGHT_PASSED"
    report["notes"] = ["Validated compact prompts and untruncated targets.", "Validation/test are never used for gradient updates.", "Only three training examples are available; no generalization claim is valid."]
    outdir = ROOT / config["output"]["report_dir"]
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "preflight_report.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("GENERATOR A V2 PREFLIGHT PASSED")
    print(f"Device: {report['selected_device']} ({report['device_name']})")
    print(f"Dataset counts: {report['dataset_counts']}")
    print(f"Token lengths: {report['token_length_report']}")
    print(f"Report: {path.relative_to(ROOT)}")


def train(config, config_path, splits, tokenizer, args):
    from peft import LoraConfig, TaskType, get_peft_model
    set_seed(int(config["training"]["seed"]))
    trainer_dir = (ROOT / config["output"]["trainer_dir"]).resolve()
    adapter_dir = (ROOT / config["output"]["adapter_dir"]).resolve()
    if trainer_dir.exists() and any(trainer_dir.iterdir()):
        if args.overwrite_output_dir:
            import shutil
            shutil.rmtree(trainer_dir)
        elif not args.resume_from_checkpoint:
            raise FileExistsError(f"Output directory is not empty: {trainer_dir}. Use a new config or --overwrite-output-dir.")
    trainer_dir.mkdir(parents=True, exist_ok=True)
    report_dir = (ROOT / config["output"]["report_dir"]).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    ml = config["tokenization"]
    train_ds = TokenizedCodeDataset(splits["train"], tokenizer, int(ml["max_source_length"]), int(ml["max_target_length"]))
    valid_ds = TokenizedCodeDataset(splits["validation"], tokenizer, int(ml["max_source_length"]), int(ml["max_target_length"]))
    model = AutoModelForSeq2SeqLM.from_pretrained(config["_resolved_model_path"], local_files_only=True)
    model.config.use_cache = False
    lora = config["lora"]
    peft_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        r=int(lora["rank"]),
        lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora["dropout"]),
        target_modules=list(lora["target_modules"]),
        bias="none",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    tr = config["training"]
    eval_steps = int(tr.get("eval_steps", 50))
    save_steps = int(tr.get("save_steps", eval_steps))
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(trainer_dir),
        num_train_epochs=float(tr["num_train_epochs"]),
        max_steps=int(args.max_steps) if args.max_steps is not None else -1,
        learning_rate=float(tr["learning_rate"]),
        weight_decay=float(tr["weight_decay"]),
        warmup_ratio=float(tr["warmup_ratio"]),
        per_device_train_batch_size=int(tr["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(tr["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(tr["gradient_accumulation_steps"]),
        logging_strategy="steps",
        logging_steps=int(tr.get("logging_steps", 10)),
        eval_strategy="steps",
        eval_steps=eval_steps,
        save_strategy="steps",
        save_steps=save_steps,
        save_total_limit=int(tr.get("save_total_limit", 2)),
        load_best_model_at_end=False,
        report_to=[],
        fp16=False,
        bf16=False,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        optim="adamw_torch",
        seed=int(tr["seed"]),
        data_seed=int(tr["seed"]),
        save_safetensors=True,
        remove_unused_columns=True,
        gradient_checkpointing=False,
    )
    collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, label_pad_token_id=-100)
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        data_collator=collator,
        processing_class=tokenizer,
    )
    print(f"Training on {get_device_summary()}")
    print(f"Examples: train={len(train_ds)}, validation={len(valid_ds)}; test={len(splits['test'])} held out")
    result = trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    adapter_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    try:
        trainer.log_metrics("train", result.metrics)
        trainer.save_metrics("train", result.metrics)
        trainer.save_state()
    except Exception as exc:
        print(f"Warning saving auxiliary trainer metrics: {exc}")
    report = _base_report(config, config_path, splits)
    report.update({
        "status": "TRAINING_COMPLETED",
        "adapter_dir": str(adapter_dir),
        "trainer_dir": str(trainer_dir),
        "training_metrics": result.metrics,
        "training_log_history": trainer.state.log_history,
        "training_args": {
            "num_train_epochs": tr["num_train_epochs"], "max_steps_override": args.max_steps,
            "learning_rate": tr["learning_rate"], "gradient_accumulation_steps": tr["gradient_accumulation_steps"],
            "eval_steps": eval_steps, "save_steps": save_steps,
        },
        "notes": ["Only training split contributes gradients.", "Compact-prompt experiment increases LoRA capacity and uses all configured projection/feed-forward module names.", "Training loss is not evidence of valid generation.", "Five data points are insufficient for any generalization claim."],
    })
    report_path = report_dir / "training_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("\nGENERATOR A V2 TRAINING FINISHED")
    print(f"Adapter: {adapter_dir.relative_to(ROOT)}")
    print(f"Report: {report_path.relative_to(ROOT)}")


def parse_args():
    parser = argparse.ArgumentParser(description="Compact-prompt CodeT5 LoRA fine-tuning")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--overwrite-output-dir", action="store_true")
    parser.add_argument("--resume-from-checkpoint", default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    try:
        config, splits, tokenizer = prepare_and_validate(config_path)
        if args.preflight:
            run_preflight(config, config_path, splits)
            return 0
        if args.max_steps is not None and args.max_steps < 1:
            raise ValueError("--max-steps must be positive")
        train(config, config_path, splits, tokenizer, args)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
