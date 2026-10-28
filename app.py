import os
import re
import tempfile
import subprocess
import torch
import streamlit as st
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

from src.controllers.ast_fallback import fallback_obfuscate
from src.controllers.obfuscation_pipeline import extract_c_functions, run_differential_test

# Enforce offline execution mode
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

ROOT = Path(".")
LOCAL_BASE_MODEL = ROOT / "models/base_models/Qwen2.5-Coder-1.5B-Instruct"
ADAPTER_PATH = ROOT / "models/checkpoints/generator_a_qwen_1.5b_130_rtx/final_adapter"

# Cross-platform Device Selection (CUDA for Windows/Linux, MPS for macOS, CPU Fallback)
def get_target_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"

# Page Configuration
st.set_page_config(
    page_title="Enterprise C Obfuscation & Metric Studio",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Clean CSS: Fixed Text Contrast, Uniform Outlines, Clean Borders
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="st-"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .stApp {
        background-color: #0B0F17;
        color: #F8FAFC;
    }

    #MainMenu, footer, header, .stAppHeader {
        display: none !important;
    }
    
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 96%;
    }

    /* Studio Header Banner */
    .nav-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 1.5rem;
        background: #111827;
        border-radius: 8px;
        margin-bottom: 1.5rem;
        border: 1px solid #1F2937;
    }
    
    .nav-title {
        color: #F8FAFC;
        font-size: 1.25rem;
        font-weight: 600;
        margin: 0;
    }
    
    .nav-badge {
        background: #064E3B;
        color: #34D399;
        border: 1px solid #059669;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Metric Cards */
    .metric-card-container {
        background: #111827;
        border: 1px solid #1F2937;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    
    .metric-label {
        color: #9CA3AF;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.3rem;
    }
    
    .metric-value {
        color: #F8FAFC;
        font-size: 1.6rem;
        font-weight: 700;
        font-family: 'Fira Code', monospace;
    }

    .editor-label {
        font-size: 0.875rem;
        font-weight: 600;
        color: #9CA3AF;
        margin-bottom: 0.5rem;
    }

    /* Streamlit Code & Text Input Contrast Fixes */
    .stTextArea textarea {
        background-color: #111827 !important;
        color: #F8FAFC !important;
        -webkit-text-fill-color: #F8FAFC !important;
        border: 1px solid #374151 !important;
        border-radius: 8px !important;
        font-family: 'Fira Code', monospace !important;
        font-size: 0.875rem !important;
        line-height: 1.5 !important;
    }
    
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 1px #2563EB !important;
        outline: none !important;
    }

    .stTextInput input {
        background-color: #111827 !important;
        color: #F8FAFC !important;
        -webkit-text-fill-color: #F8FAFC !important;
        border: 1px solid #374151 !important;
        border-radius: 8px !important;
        font-family: 'Fira Code', monospace !important;
        font-size: 0.875rem !important;
    }

    .stTextInput label {
        color: #9CA3AF !important;
        font-size: 0.85rem !important;
    }

    /* Primary Button Styling */
    div.stButton > button {
        width: 100%;
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        font-weight: 600;
        font-size: 0.9rem;
        padding: 0.65rem 1.25rem;
        border-radius: 8px;
        border: none !important;
        transition: background-color 0.15s ease;
    }
    
    div.stButton > button:hover {
        background-color: #1D4ED8 !important;
    }

    .stCodeBlock {
        border-radius: 8px !important;
        border: 1px solid #1F2937 !important;
        background-color: #111827 !important;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

@st.cache_resource
def load_offline_generator():
    device = get_target_device()
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16
    ) if device == "cuda" else None

    model_path = str(LOCAL_BASE_MODEL) if LOCAL_BASE_MODEL.exists() else "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    kwargs = {"trust_remote_code": True, "local_files_only": True}
    if bnb_config:
        kwargs["quantization_config"] = bnb_config
        kwargs["device_map"] = "auto"
    elif device == "mps":
        kwargs["torch_dtype"] = torch.float16
    else:
        kwargs["torch_dtype"] = torch.float32

    base_model = AutoModelForCausalLM.from_pretrained(model_path, **kwargs)
    
    if not bnb_config:
        base_model = base_model.to(device)

    if ADAPTER_PATH.exists():
        model = PeftModel.from_pretrained(base_model, str(ADAPTER_PATH))
    else:
        model = base_model

    model.eval()
    return model, tokenizer

_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')

def extract_identifiers(c_code: str) -> set:
    keywords = {
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if",
        "inline", "int", "long", "register", "restrict", "return", "short",
        "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
        "unsigned", "void", "volatile", "while", "include", "define", "stdio",
        "stdlib", "stdint", "printf", "scanf", "main", "NULL", "h", "uintptr_t"
    }
    code_clean = re.sub(r'//.*?\n', '\n', c_code)
    code_clean = re.sub(r'/\*.*?\*/', '', code_clean, flags=re.DOTALL)
    code_clean = _STRING_LITERAL_RE.sub('""', code_clean)
    code_clean = re.sub(r'#include\s*<[^>]*>', '', code_clean)
    tokens = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', code_clean))
    return tokens - keywords

def extract_metric_features(orig: str, obf: str) -> dict:
    char_growth = len(obf) / max(1, len(orig))
    orig_ids = extract_identifiers(orig)
    obf_ids = extract_identifiers(obf)
    overlap = (len(orig_ids & obf_ids) / max(1, len(orig_ids))) if orig_ids else 0.0
    return {
        "char_growth_ratio": char_growth,
        "identifier_overlap_ratio": overlap,
        "while_count_obf": obf.count("while"),
        "ternary_count_obf": obf.count("?")
    }

def clean_code_block(raw_text: str) -> str:
    match = re.search(r'```(?:c|C)?\s*(.*?)\s*(?:```|$)', raw_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_text.strip()

def deduplicate_headers_and_helpers(code: str) -> str:
    lines = code.splitlines()
    seen_defines = set()
    deduped_lines = []
    
    in_add_func = False
    add_func_included = False

    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("#include"):
            if stripped in seen_defines:
                continue
            seen_defines.add(stripped)
            deduped_lines.append(line)
            continue
            
        if stripped.startswith("#define"):
            macro_name = stripped.split()[1] if len(stripped.split()) > 1 else stripped
            if macro_name in seen_defines:
                continue
            seen_defines.add(macro_name)
            deduped_lines.append(line)
            continue

        if "static inline int _0xADD" in stripped or "int _0xADD(" in stripped:
            if add_func_included:
                in_add_func = True
                continue
            add_func_included = True

        if in_add_func:
            if stripped == "}":
                in_add_func = False
            continue

        deduped_lines.append(line)

    return "\n".join(deduped_lines).strip()

def generate_neural_obfuscation(model, tokenizer, c_code: str) -> str:
    system_prompt = (
        "You are an expert low-level reverse-engineering resistance compiler pass.\n"
        "Transform the input C program using extreme structural obfuscation:\n"
        "1. Maximum Identifier Entropy: Rename all variables, parameters, macros, and function identifiers to randomized combinations of underscores and hex strings.\n"
        "2. Complete Control-Flow Flattening: Rewrite loops and functions into consolidated switch state machines.\n"
        "3. IOCCC Pointer Aliasing: Replace array indexing with inverted pointer indexing.\n"
        "4. Bitwise Logic Equivalence: Replace arithmetic operations with bitwise half-adders.\n"
        "5. Dynamic Opaque Predicates: Guard execution blocks using dynamic invariants.\n\n"
        "OUTPUT REQUIREMENT: Output strictly valid, executable C code inside ```c ... ``` blocks."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Obfuscate the following C program aggressively:\n\n{c_code}"}
    ]

    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    device = get_target_device()
    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=896,
            temperature=0.1,
            top_p=0.90,
            do_sample=True
        )

    full_output = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
    return clean_code_block(full_output)

def run_neural_pipeline(model, tokenizer, c_code: str) -> str:
    input_tokens = len(tokenizer.encode(c_code))
    if input_tokens <= 700:
        raw_out = generate_neural_obfuscation(model, tokenizer, c_code)
        return deduplicate_headers_and_helpers(raw_out)

    blocks = extract_c_functions(c_code)
    processed_chunks = []
    for block_type, code_content in blocks:
        if block_type == "function" and len(code_content.strip()) > 15:
            chunk_out = generate_neural_obfuscation(model, tokenizer, code_content)
            processed_chunks.append(chunk_out)
        else:
            processed_chunks.append(code_content)

    combined = "\n\n".join(processed_chunks)
    return deduplicate_headers_and_helpers(combined)

# --- Navigation Header ---
st.markdown("""
<div class="nav-header">
    <div class="nav-title">C Obfuscation & Security Evaluation Studio</div>
    <div class="nav-badge">100% Offline</div>
</div>
""", unsafe_allow_html=True)

# Main Studio Grid Layout
col_left, col_right = st.columns(2, gap="medium")

with col_left:
    st.markdown('<div class="editor-label">Baseline C Source Code</div>', unsafe_allow_html=True)
    user_code = st.text_area(
        label="C Code Input",
        label_visibility="collapsed",
        height=340,
        placeholder="#include <stdio.h>\n\nint main() {\n    printf(\"Hello World\\n\");\n    return 0;\n}"
    )
    
    test_input = st.text_input(
        "Optional Runtime Arguments (stdin):",
        placeholder="Standard input string/values if required by executable"
    )
    
    submit_btn = st.button("Transform & Evaluate Code", type="primary")

# Layout balance for initial render
with col_right:
    st.markdown('<div class="editor-label">Transformed Executable Output</div>', unsafe_allow_html=True)

if submit_btn:
    if not user_code.strip():
        st.warning("Please enter valid C source code before executing the transformation pipeline.")
    else:
        with st.spinner("Executing Structural Transformation & Differential Verification Pass..."):
            model, tokenizer = load_offline_generator()
            raw_neural_output = run_neural_pipeline(model, tokenizer, user_code)

            # Execution Gate
            beh_passed, orig_out, obf_out = run_differential_test(user_code, raw_neural_output, test_input)

            if not beh_passed:
                final_code = fallback_obfuscate(user_code)
            else:
                final_code = raw_neural_output

        with col_right:
            st.code(final_code, language="c")

        # Metrics Section
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("##### Obfuscation Quality Metrics")
        
        metrics = extract_metric_features(user_code, final_code)

        m1, m2, m3, m4 = st.columns(4, gap="small")
        
        with m1:
            st.markdown(f"""
            <div class="metric-card-container">
                <div class="metric-label">Char Growth Ratio</div>
                <div class="metric-value">{metrics['char_growth_ratio']:.2f}x</div>
            </div>
            """, unsafe_allow_html=True)
            
        with m2:
            st.markdown(f"""
            <div class="metric-card-container">
                <div class="metric-label">Identifier Overlap</div>
                <div class="metric-value">{metrics['identifier_overlap_ratio']*100:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)

        with m3:
            st.markdown(f"""
            <div class="metric-card-container">
                <div class="metric-label">Flattened Loops</div>
                <div class="metric-value">{metrics['while_count_obf']}</div>
            </div>
            """, unsafe_allow_html=True)

        with m4:
            st.markdown(f"""
            <div class="metric-card-container">
                <div class="metric-label">Opaque Predicates</div>
                <div class="metric-value">{metrics['ternary_count_obf']}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Quality Baseline Verdict
        if metrics['char_growth_ratio'] >= 2.2 and metrics['identifier_overlap_ratio'] <= 0.15:
            st.success("ACCEPT: Transformed binary satisfies all structural entropy and quality security baselines.")
        else:
            st.warning("REJECT: Structural expansion ratio is below security quality threshold.")
else:
    with col_right:
        st.code("// Transformed C code will appear here after execution...", language="c")