
import os
import re
import tempfile
import subprocess
import joblib
import pandas as pd
import torch
import streamlit as st
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

from src.controllers.ast_fallback import fallback_obfuscate
from src.controllers.obfuscation_pipeline import extract_c_functions, run_differential_test

# Enforce offline mode
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

ROOT = Path(".")
LOCAL_BASE_MODEL = ROOT / "models/base_models/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = ROOT / "models/checkpoints/generator_a_qwen_1.5b_130_rtx/final_adapter"
RF_MODEL_PATH = ROOT / "models/ml_evaluators/random_forest.joblib"

st.set_page_config(
    page_title="Offline C Obfuscation & Evaluation Studio",
    layout="wide"
)


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@st.cache_resource
def load_offline_generator():
    device = get_device()

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16
    ) if device == "cuda" else None

    if not LOCAL_BASE_MODEL.exists():
        raise FileNotFoundError(
            f"Local base model not found: {LOCAL_BASE_MODEL}"
        )

    model_path = str(LOCAL_BASE_MODEL)

    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=True
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    kwargs = {
        "trust_remote_code": True,
        "local_files_only": True
    }

    if device == "cuda":
        kwargs["quantization_config"] = bnb_config
        kwargs["device_map"] = "auto"
    elif device == "mps":
        kwargs["torch_dtype"] = torch.float16
    else:
        kwargs["torch_dtype"] = torch.float32

    base_model = AutoModelForCausalLM.from_pretrained(
        model_path,
        **kwargs
    )

    if device != "cuda":
        base_model = base_model.to(device)

    if ADAPTER_PATH.exists():
        model = PeftModel.from_pretrained(
            base_model,
            str(ADAPTER_PATH),
            local_files_only=True
        )
    else:
        model = base_model

    model.eval()
    return model, tokenizer


_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def extract_identifiers(c_code: str) -> set:
    """Strips comments, string literals, headers, and standard C keywords before computing overlap."""

    keywords = {
        "auto", "break", "case", "char", "const", "continue", "default",
        "do", "double", "else", "enum", "extern", "float", "for", "goto",
        "if", "inline", "int", "long", "register", "restrict", "return",
        "short", "signed", "sizeof", "static", "struct", "switch",
        "typedef", "union", "unsigned", "void", "volatile", "while",
        "include", "define", "stdio", "stdlib", "stdint", "printf",
        "scanf", "main", "NULL", "h", "uintptr_t"
    }

    # 1. Strip C comments
    code_clean = re.sub(r'//.*?$', '', c_code, flags=re.MULTILINE)
    code_clean = re.sub(r'/\*.*?\*/', '', code_clean, flags=re.DOTALL)

    # 2. Strip string literals and system header inclusions
    code_clean = _STRING_LITERAL_RE.sub('""', code_clean)
    code_clean = re.sub(r'#include\s*<[^>]*>', '', code_clean)

    # 3. Extract word tokens and filter standard C keywords
    tokens = set(
        re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', code_clean)
    )

    return tokens - keywords


def extract_metric_features(orig: str, obf: str) -> dict:
    char_growth = len(obf) / max(1, len(orig))

    orig_ids = extract_identifiers(orig)
    obf_ids = extract_identifiers(obf)

    overlap = (
        len(orig_ids & obf_ids) / max(1, len(orig_ids))
        if orig_ids else 0.0
    )

    return {
        "char_growth_ratio": char_growth,
        "identifier_overlap_ratio": overlap,
        "while_count_obf": obf.count("while"),
        "ternary_count_obf": obf.count("?")
    }


def process_function_chunk(model, tokenizer, func_code: str) -> str:
    system_prompt = (
        "You are an expert low-level reverse-engineering resistance compiler pass.\n"
        "Transform the input C code using aggressive structural obfuscation:\n"
        "1. Rename variables/functions to underscore/hex sequences.\n"
        "2. Flatten loops into single switch-case state machines (_S_x...).\n"
        "3. Replace array indexing arr[i] with inverted notation i[arr].\n"
        "4. Replace addition (+) with bitwise half-adders (_0xADD).\n"
        "OUTPUT REQUIREMENT: Output strictly valid C code inside ```c ... ``` blocks."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Obfuscate the following C code:\n\n{func_code}"
        }
    ]

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    device = get_device()

    inputs = tokenizer(
        prompt,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.2,
            top_p=0.90,
            do_sample=True
        )

    full_output = tokenizer.decode(
        outputs[0][inputs.input_ids.shape[1]:],
        skip_special_tokens=True
    ).strip()

    if "```c" in full_output:
        return full_output.split("```c", 1)[1].split("```", 1)[0].strip()
    elif "```" in full_output:
        return full_output.split("```", 1)[1].split("```", 1)[0].strip()

    return full_output


# --- UI Layout ---
st.title("Offline C Code Obfuscator & Metric Evaluator")
st.caption(
    "100% Offline | Function-Chunked Neural Generation + AST Fallback | GCC Differential Gate"
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Source Code Input")

    user_code = st.text_area(
        "Paste C source code here:",
        height=320,
        placeholder='#include <stdio.h>\nint main() {\n    printf("Test\\n");\n    return 0;\n}'
    )

    test_input = st.text_input(
        "Optional Standard Input (stdin) for execution test:",
        value=""
    )

    submit_btn = st.button(
        "Obfuscate & Evaluate Code",
        type="primary"
    )


if submit_btn:
    if not user_code.strip():
        st.warning("Please provide C source code to process.")

    else:
        with st.spinner("Processing through Function-Chunking Pipeline..."):
            model, tokenizer = load_offline_generator()

            blocks = extract_c_functions(user_code)
            processed_chunks = []

            for block_type, code_content in blocks:
                if block_type == "function" and len(code_content.strip()) > 15:
                    chunk_out = process_function_chunk(
                        model,
                        tokenizer,
                        code_content
                    )
                    processed_chunks.append(chunk_out)
                else:
                    processed_chunks.append(code_content)

            raw_neural_output = "\n\n".join(processed_chunks)

            # Verification Gate
            beh_passed, orig_out, obf_out = run_differential_test(
                user_code,
                raw_neural_output,
                test_input
            )

            if not beh_passed:
                st.warning(
                    "Neural output failed verification gate. "
                    "Routing to AST Fallback Engine..."
                )

                final_code = fallback_obfuscate(user_code)
                engine_type = "AST Fallback Engine"

            else:
                final_code = raw_neural_output
                engine_type = "Qwen 1.5B Chunked Neural Engine"

        with col2:
            st.subheader(f"Obfuscated C Code ({engine_type})")
            st.code(final_code, language="c")

        # Metric Evaluation Panel
        st.markdown("---")
        st.subheader("Obfuscation Metric Evaluation")

        metrics = extract_metric_features(user_code, final_code)

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "Char Growth Ratio",
            f"{metrics['char_growth_ratio']:.2f}x"
        )

        m2.metric(
            "Identifier Overlap",
            f"{metrics['identifier_overlap_ratio'] * 100:.1f}%"
        )

        m3.metric(
            "Obfuscated Whiles",
            metrics["while_count_obf"]
        )

        m4.metric(
            "Obfuscated Ternaries",
            metrics["ternary_count_obf"]
        )

        if (
            metrics["char_growth_ratio"] >= 2.2
            and metrics["identifier_overlap_ratio"] <= 0.15
        ):
            st.success("ACCEPT: Obfuscation Quality Criteria Satisfied.")
        else:
            st.warning(
                "REJECT: Structural Expansion Below Quality Baseline."
            )
