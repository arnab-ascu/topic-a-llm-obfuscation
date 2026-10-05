from __future__ import annotations
import argparse
import json
from pathlib import Path
from src.validation.correctness_runner import correctness_check

PROGRAMS = {
    "program_01": {
        "original": """#include <stdio.h>
int main(void) {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("%d\\n", a + b);
    return 0;
}
""",
        "positive": """#include <stdio.h>
int main(void) {
    int lhs, rhs;
    scanf("%d %d", &lhs, &rhs);
    int total;
    if ((lhs | rhs) == (lhs | rhs)) {
        total = lhs - (-rhs);
    } else {
        total = lhs - (-rhs);
    }
    printf("%d\\n", total);
    return 0;
}
""",
        "negative": """#include <stdio.h>
int main(void) {
    int lhs, rhs;
    scanf("%d %d", &lhs, &rhs);
    int total;
    if ((lhs | rhs) == (lhs | rhs)) {
        total = lhs - rhs;
    } else {
        total = lhs - rhs;
    }
    printf("%d\\n", total);
    return 0;
}
""",
        "negative_type": "NEGATIVE_BEHAVIOR",
        "tests": [
            {"name": "positive", "stdin": "10 20\n"},
            {"name": "negative", "stdin": "-5 8\n"},
            {"name": "zero", "stdin": "0 0\n"},
            {"name": "mixed", "stdin": "100 -30\n"}
        ]
    },
    "program_02": {
        "original": """#include <stdio.h>
int main(void) {
    int a, b;
    scanf("%d %d", &a, &b);
    if (a > b) {
        printf("%d\\n", a);
    } else {
        printf("%d\\n", b);
    }
    return 0;
}
""",
        "positive": """#include <stdio.h>
int main(void) {
    int left, right;
    scanf("%d %d", &left, &right);
    int bigger;
    switch ((left > right) ? 1 : 0) {
        case 1:
            bigger = left - (-0);
            break;
        default:
            bigger = right - (-0);
            break;
    }
    printf("%d\\n", bigger);
    return 0;
}
""",
        "negative": """#include <stdio.h>
int main(void) {
    int a, b;
    scanf("%d %d", &a, &b);
    int bigger
    printf("%d\\n", bigger);
    return 0;
}
""",
        "negative_type": "NEGATIVE_COMPILE",
        "tests": [
            {"name": "greater_right", "stdin": "10 20\n"},
            {"name": "greater_left", "stdin": "20 10\n"},
            {"name": "equal", "stdin": "5 5\n"},
            {"name": "negative", "stdin": "-3 -8\n"}
        ]
    },
    "program_03": {
        "original": """#include <stdio.h>
int main(void) {
    int x;
    scanf("%d", &x);
    if (x < 0) {
        x = -x;
    }
    printf("%d\\n", x);
    return 0;
}
""",
        "positive": """#include <stdio.h>
int main(void) {
    int value;
    scanf("%d", &value);
    int mask = (value < 0) ? -1 : 0;
    int magnitude = (value ^ mask) - mask;
    printf("%d\\n", magnitude);
    return 0;
}
""",
        "negative": """#include <stdio.h>
int main(void) {
    int x;
    scanf("%d", &x);
    if (x < 0) {
        x = -x;
    }
    printf("%d\\n", x);
    return 0;
}
""",
        "negative_type": "NEGATIVE_NO_OP",
        "tests": [
            {"name": "positive", "stdin": "10\n"},
            {"name": "negative", "stdin": "-10\n"},
            {"name": "zero", "stdin": "0\n"},
            {"name": "large_positive", "stdin": "37\n"},
            {"name": "large_negative", "stdin": "-37\n"}
        ]
    },
    "program_04": {
        "original": """#include <stdio.h>
int main(void) {
    int n;
    scanf("%d", &n);
    int result = 1;
    for (int i = 1; i <= n; ++i) {
        result = result * i;
    }
    printf("%d\\n", result);
    return 0;
}
""",
        "positive": """#include <stdio.h>
int main(void) {
    int limit;
    scanf("%d", &limit);
    int product = 1;
    int index = 1;
    while (index <= limit) {
        product = product * (index | 0);
        ++index;
    }
    printf("%d\\n", product);
    return 0;
}
""",
        "negative": None,
        "negative_type": "NEGATIVE_BLOAT",
        "tests": [
            {"name": "zero", "stdin": "0\n"},
            {"name": "one", "stdin": "1\n"},
            {"name": "five", "stdin": "5\n"},
            {"name": "seven", "stdin": "7\n"}
        ]
    },
    "program_05": {
        "original": """#include <stdio.h>
int main(void) {
    int n;
    scanf("%d", &n);
    int sum = 0;
    for (int i = 0; i < n; ++i) {
        int value;
        scanf("%d", &value);
        sum += value;
    }
    printf("%d\\n", sum);
    return 0;
}
""",
        "positive": """#include <stdio.h>
int main(void) {
    int count;
    scanf("%d", &count);
    int total = 0;
    int index = 0;
    while (index < count) {
        int item;
        scanf("%d", &item);
        total = total + (item ^ 0);
        ++index;
    }
    printf("%d\\n", total);
    return 0;
}
""",
        "negative": """#include <stdio.h>

int main(void)
{
    int n;
    scanf("%d", &n);
    int sum = 0;
    for (int i = 0; i < n; ++i)
    {
        int value;
        scanf("%d", &value);
        sum += value;
    }
    printf("%d\\n", sum);
    return 0;
}
""",
        "negative_type": "NEGATIVE_SIGNATURE",
        "tests": [
            {"name": "zero", "stdin": "0\n"},
            {"name": "three_values", "stdin": "3\n1 2 3\n"},
            {"name": "mixed", "stdin": "4\n10 -5 7 2\n"},
            {"name": "negative_sum", "stdin": "5\n-1 -2 3 4 -5\n"}
        ]
    }
}

def build_bloat(original: str) -> str:
    padding = "\n".join(f"    int padding_{i} = {i};" for i in range(100))
    return original.replace("    printf(\"%d\\n\", result);",f"{padding}\n    printf(\"%d\\n\", result);")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default="clang")
    args = parser.parse_args()

    data_root = Path("data/dataset_v1")
    result_root = Path("results/dataset_v1")
    data_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)

    records = []

    for program_id, program in PROGRAMS.items():
        program_dir = data_root / program_id
        program_dir.mkdir(parents=True, exist_ok=True)

        original_path = program_dir / "original.c"
        positive_path = program_dir / "positive.c"
        negative_path = program_dir / "negative.c"
        tests_path = program_dir / "tests.json"

        original_path.write_text(program["original"], encoding="utf-8")
        positive_path.write_text(program["positive"], encoding="utf-8")
        negative_source = program["negative"]
        if program_id == "program_04":
            negative_source = build_bloat(program["original"])
        negative_path.write_text(negative_source, encoding="utf-8")

        tests_path.write_text(json.dumps(program["tests"], indent=2),encoding="utf-8")
        positive_result = correctness_check(original_path,positive_path,tests_path,args.compiler,3.0)
        negative_result = correctness_check(original_path,negative_path,tests_path,args.compiler,3.0)

        positive_result_path = result_root / f"{program_id}_positive.json"
        negative_result_path = result_root / f"{program_id}_negative.json"
        positive_result_path.write_text(json.dumps(positive_result, indent=2),encoding="utf-8")
        negative_result_path.write_text(json.dumps(negative_result, indent=2),encoding="utf-8")

        records.append({
            "program_id": program_id,
            "spec_id": "SPEC_V1",
            "transformation_id": "FULL_V1",
            "record_type": "positive",
            "original_path": str(original_path),
            "candidate_path": str(positive_path),
            "correctness_status": positive_result["failure_reason"],
            "behavior_ok": positive_result["behavior_equivalent"]
        })

        records.append({
            "program_id": program_id,
            "spec_id": "SPEC_V1",
            "transformation_id": program["negative_type"],
            "record_type": "negative",
            "original_path": str(original_path),
            "candidate_path": str(negative_path),
            "correctness_status": negative_result["failure_reason"],
            "behavior_ok": negative_result["behavior_equivalent"]
        })

    dataset_path = data_root / "dataset_v1.json"
    dataset_path.write_text(json.dumps(records, indent=2),encoding="utf-8")
    print(f"Dataset created: {dataset_path}")
    print(f"Records: {len(records)}")

if __name__ == "__main__":
    main()