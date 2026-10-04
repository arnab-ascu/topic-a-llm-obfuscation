from pathlib import Path
from transformers import RobertaTokenizer,T5ForConditionalGeneration

model_dir = "models/base/codet5-small"
source_path = Path("data/sample/program_01/original.c")

source = source_path.read_text(encoding="utf-8")
masked_source = source.replace("a + b","<extra_id_0>")

tokenizer = RobertaTokenizer.from_pretrained(model_dir,local_files_only=True)
model = T5ForConditionalGeneration.from_pretrained(model_dir,local_files_only=True)

inputs = tokenizer(masked_source,return_tensors="pt")
outputs = model.generate(**inputs,max_new_tokens=64)

generated = tokenizer.decode(outputs[0],skip_special_tokens=True)

print("=== ORIGINAL C SOURCE ===")
print(source)
print("=== MASKED C SOURCE ===")
print(masked_source)
print("=== LOCAL CODET5 COMPLETION ===")
print(generated)
print("=== SMOKE TEST COMPLETE ===")