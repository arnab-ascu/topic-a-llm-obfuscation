import json
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.ensemble import RandomForestClassifier
import joblib

def extract_metric_features(orig_code: str, obf_code: str) -> dict:
    loc_orig = len(orig_code.splitlines())
    loc_obf = len(obf_code.splitlines())
    char_orig = len(orig_code)
    char_obf = len(obf_code)
    
    words_orig = set(w for w in orig_code.split() if len(w) > 2)
    words_obf = set(w for w in obf_code.split() if len(w) > 2)
    overlap_ratio = len(words_orig.intersection(words_obf)) / max(1, len(words_orig))
    
    return {
        "loc_growth_ratio": loc_obf / max(1, loc_orig),
        "char_growth_ratio": char_obf / max(1, char_orig),
        "identifier_overlap_ratio": overlap_ratio,
        "while_count_obf": obf_code.count("while"),
        "ternary_count_obf": obf_code.count("?")
    }

def train_ml_models():
    ROOT = Path(".")
    train_data = [json.loads(l) for l in (ROOT / "data/training_expanded/train_130.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    X, y = [], []

    for item in train_data:
        orig = item["input_text"].replace("// Task: Obfuscate C source code while preserving behavior\n", "")
        pos = item["target_text"]
        
        # Positive Pair (y=1)
        X.append(extract_metric_features(orig, pos))
        y.append(1)
        
        # Negative Pair (y=0, no-op)
        X.append(extract_metric_features(orig, orig))
        y.append(0)

    df_X = pd.DataFrame(X)
    arr_y = np.array(y)

    dt = DecisionTreeClassifier(max_depth=4, random_state=42)
    dt.fit(df_X, arr_y)
    print("=== DECISION TREE RULES ===")
    print(export_text(dt, feature_names=list(df_X.columns)))

    rf = RandomForestClassifier(n_estimators=50, random_state=42)
    rf.fit(df_X, arr_y)
    print("\n=== RANDOM FOREST FEATURE IMPORTANCE ===")
    for feat, imp in zip(df_X.columns, rf.feature_importances_):
        print(f" - {feat:25s}: {imp:.4f}")

    out_dir = ROOT / "models/ml_evaluators"
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(dt, out_dir / "decision_tree.joblib")
    joblib.dump(rf, out_dir / "random_forest.joblib")

if __name__ == "__main__":
    train_ml_models()