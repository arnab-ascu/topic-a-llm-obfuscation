# Qwen Generator A integration patch

## Files
- `src/models/train_qwen_generator_a.py`: fixes the default dataset path to V5 and masks prompt tokens from the SFT loss. This remains an RTX/CUDA 4-bit QLoRA trainer.
- `src/models/evaluate_qwen_generator_a.py`: supports CUDA (4-bit when bitsandbytes is available) and Apple MPS, uses the real per-program `tests.json`, applies the existing lexical transformation proxies, and reports each gate independently.

## Apply from the repository root on the Mac

Download this ZIP, then in Terminal `cd` into `topic-a-llm-obfuscation` and run:

```bash
unzip -o ~/Downloads/qwen_obfuscation_patch.zip -d .
python -m py_compile src/models/train_qwen_generator_a.py src/models/evaluate_qwen_generator_a.py
```

Run the no-model fallback evaluation first (it does not require the Qwen adapter):

```bash
python -m src.models.evaluate_qwen_generator_a --split validation --backend fallback
```

The fallback only performs conservative identifier renaming. It is expected to fail the full transformation-rule gate because the specification also requires control-flow and expression transformations. The report must show that honestly; do not treat compilation or behavior equivalence alone as complete obfuscation success.

## Running neural evaluation

The Mac currently lacks `models/checkpoints/generator_a_qwen_1.5b_rtx/final_adapter`. Ask the teammate who trained Qwen to send that exact `final_adapter` directory (at minimum `adapter_config.json` and `adapter_model.safetensors`; include any tokenizer files saved in that directory). Do not send or commit the 1.5B base model weights.

After putting the directory at that path, run:

```bash
python -m src.models.evaluate_qwen_generator_a --split validation --backend qwen
python -m src.models.evaluate_qwen_generator_a --split test --backend qwen
```

For a local fallback-only diagnostic, use `--backend fallback`. `--backend auto` uses Qwen only when the adapter directory exists; otherwise it explicitly switches to fallback-only mode.

Reports and candidate C files are written under `results/qwen_generator_a/`. The evaluator's `accepted` flag is true only when compilation, the project's required lexical rule proxies, and every available differential test pass. These lexical proxies are not proof of AST-level transformations or absence of undefined behavior.
