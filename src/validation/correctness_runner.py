from __future__ import annotations
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 3.0

def compile_program(source_path: Path,executable_path: Path,compiler: str,) -> dict[str, Any]:
    command = [
        compiler,
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Wpedantic",
        str(source_path),
        "-o",
        str(executable_path),
    ]
    result = subprocess.run(command,capture_output=True,text=True,)

    return {
        "success": result.returncode == 0,
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }

def run_program(executable_path: Path,stdin_data: str,timeout: float,) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(executable_path)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "timeout": False,
            "crash": result.returncode < 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "timeout": True,
            "crash": False,
            "return_code": None,
            "stdout": "",
            "stderr": "",
        }

def normalize_output(value: str) -> str:
    value = value.replace("\r\n", "\n")
    value = value.replace("\r", "\n")
    lines = [line.rstrip() for line in value.splitlines()]
    return "\n".join(lines).strip()

def load_tests(test_path: Path) -> list[dict[str, Any]]:
    with test_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("tests.json must contain a JSON list")
    for test in data:
        if "name" not in test or "stdin" not in test:
            raise ValueError("Each test must contain 'name' and 'stdin'")
    return data

def compare_results(original_result: dict[str, Any],candidate_result: dict[str, Any],) -> dict[str, Any]:
    original_output = normalize_output(original_result["stdout"])
    candidate_output = normalize_output(candidate_result["stdout"])
    same_stdout = original_output == candidate_output
    same_return_code = (original_result["return_code"] == candidate_result["return_code"])

    passed = (
        not original_result["timeout"]
        and not candidate_result["timeout"]
        and not original_result["crash"]
        and not candidate_result["crash"]
        and same_stdout
        and same_return_code)

    return {
        "passed": passed,
        "same_stdout": same_stdout,
        "same_return_code": same_return_code,
        "original_output": original_output,
        "candidate_output": candidate_output,
    }

def correctness_check(original: Path,candidate: Path,tests_path: Path,compiler: str,timeout: float,) -> dict[str, Any]:
    tests = load_tests(tests_path)
    result: dict[str, Any] = {
        "original_source": str(original),
        "candidate_source": str(candidate),
        "compiler": compiler,
        "timeout_seconds": timeout,
        "tests": [],
    }
    with tempfile.TemporaryDirectory(prefix="obfuscation_test_") as temp_dir:
        temp_dir = Path(temp_dir)
        original_exe = temp_dir / "original"
        candidate_exe = temp_dir / "candidate"
        original_compile = compile_program(original,original_exe,compiler,)
        candidate_compile = compile_program(candidate,candidate_exe,compiler,)
        result["original_compile"] = original_compile
        result["candidate_compile"] = candidate_compile

        if not original_compile["success"]:
            result["behavior_equivalent"] = False
            result["failure_reason"] = "ORIGINAL_COMPILE_FAILURE"
            return result
        if not candidate_compile["success"]:
            result["behavior_equivalent"] = False
            result["failure_reason"] = "CANDIDATE_COMPILE_FAILURE"
            return result
        all_passed = True
        for test in tests:
            original_run = run_program(original_exe,test["stdin"],timeout,)
            candidate_run = run_program(candidate_exe,test["stdin"],timeout,)
            comparison = compare_results(original_run,candidate_run,)
            test_result = {
                "name": test["name"],
                "stdin": test["stdin"],
                "original": original_run,
                "candidate": candidate_run,
                "comparison": comparison,
            }

            result["tests"].append(test_result)
            if not comparison["passed"]:
                all_passed = False
        result["behavior_equivalent"] = all_passed
        if all_passed:
            result["failure_reason"] = None
        else:
            candidate_timeouts = any(test["candidate"]["timeout"] for test in result["tests"])
            candidate_crashes = any(test["candidate"]["crash"] for test in result["tests"])
            if candidate_timeouts:
                result["failure_reason"] = "CANDIDATE_TIMEOUT"
            elif candidate_crashes:
                result["failure_reason"] = "CANDIDATE_CRASH"
            else:
                result["failure_reason"] = "BEHAVIOR_MISMATCH"
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description="C program correctness comparison")
    parser.add_argument("--original",required=True,type=Path,)
    parser.add_argument("--candidate",required=True,type=Path,)
    parser.add_argument("--tests",required=True,type=Path,)
    parser.add_argument("--compiler",default="clang",)
    parser.add_argument("--timeout",type=float,default=DEFAULT_TIMEOUT,)
    parser.add_argument("--output",type=Path,required=True,)
    args = parser.parse_args()

    result = correctness_check(
        original=args.original,
        candidate=args.candidate,
        tests_path=args.tests,
        compiler=args.compiler,
        timeout=args.timeout,
    )

    args.output.parent.mkdir(parents=True,exist_ok=True,)
    with args.output.open("w",encoding="utf-8",) as file:
        json.dump(result,file,indent=2,)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()