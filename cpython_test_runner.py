#!/usr/bin/env python3
"""
CPython Test Runner for PyTorch Dynamo

Runs CPython tests on PyTorch and saves raw test output for analysis.

Usage:
    python3 cpython_test_runner.py                                           # Runs all tests, auto-generates output file
    python3 cpython_test_runner.py --modules test_bool test_set              # Run 2 modules
    python3 cpython_test_runner.py --save-output custom.txt                  # Custom output filename
    python3 cpython_test_runner.py --reuse-output data.txt                   # Reuse previous output (no re-run)
"""

import subprocess
import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse
from datetime import datetime



TEST_DIR = Path("~/git/pytorch313/test/dynamo/cpython/3_13").expanduser()
PYTORCH_ROOT = Path("~/git/pytorch313").expanduser()
WORKSPACE_NAME = "pytorch"
ENV_NAME = "pytorch313"


def get_commit_hash(repo_path: str) -> str:
    """
    Get the current git commit hash (11 characters) from a repository.

    Args:
        repo_path: Path to the git repository

    Returns:
        11-character commit hash (e.g., 'fa3de09238'), or 'unknown' if unavailable
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short=11', 'HEAD'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def run_pytest_tests(module_names: Optional[List[str]] = None) -> str:
    """
    Run unittest tests via micromamba and capture output.

    Args:
        module_names: Optional list of specific test modules (e.g., ['test_bool', 'test_set'])

    Returns:
        combined test output as string
    """
    if module_names:
        test_files = [f"test/dynamo/cpython/3_13/{name}.py" for name in module_names]
    else:
        # Get all test files in the cpython directory
        cpython_dir = os.path.join(PYTORCH_ROOT, 'test/dynamo/cpython/3_13')
        test_files = sorted([
            f"test/dynamo/cpython/3_13/{f}"
            for f in os.listdir(cpython_dir)
            if f.startswith('test_') and f.endswith('.py')
        ])

    print(f"Running {len(test_files)} test file(s) via unittest")
    print(f"Working directory: {PYTORCH_ROOT}")
    print(f"Environment: PYTORCH_TEST_WITH_DYNAMO=1")
    print()

    # Set environment variable to enable Dynamo
    env = os.environ.copy()
    env['PYTORCH_TEST_WITH_DYNAMO'] = '1'

    all_output = []

    # Run each test file separately
    for test_file in test_files:
        cmd = [
            "pixi", "run", "-w", WORKSPACE_NAME, "-e", ENV_NAME,
            "python", test_file,
            "-v"
        ]

        print(f"  Running {test_file}...")

        result = subprocess.run(
            cmd,
            cwd=PYTORCH_ROOT,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per file
            env=env
        )

        # Add markers so we know which test file this output came from
        all_output.append(f"\n=== TEST FILE: {test_file} ===\n")
        all_output.append(result.stdout)
        all_output.append(result.stderr)

    return '\n'.join(all_output)


def parse_pytest_output(
    output: str, *, warn_on_count_mismatch: bool = True
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, List[Dict]]]:
    """
    Parse unittest output and extract per-module statistics AND detailed test results.

    Parses output like:
    test_blocked (__main__.BoolTest.test_blocked) ... skipped 'Unsupported method call\n  Explanation: ...'

    Also handles tests where warnings appear before the status (status may be on next line).

    Returns:
        Tuple of:
        - Dict mapping module name -> {total, passed, failed, skipped}
        - Dict mapping module name -> List of {test_name, status, reason}
    """
    summary: Dict[str, Dict[str, int]] = {}
    details: Dict[str, List[Dict]] = {}

    # Extract expected test counts from "Ran X tests" lines
    ran_pattern = re.compile(r'Ran (\d+) tests?')
    expected_counts: Dict[str, int] = {}

    # Pattern to match test result lines from unittest -v output
    # Format: test_name (__main__.ClassName.test_name) ... [optional warnings] ok|FAIL|skipped 'reason'
    # Also matches lines without the ... (test_name (__main__.ClassName.test_name) with status on same/next line)
    # Supports both test_xxx and testXxx patterns
    test_start_pattern = re.compile(
        r'(test\w+) \(__main__\.(\w+)\.(test\w+)\)',
        re.MULTILINE
    )

    # Pattern to detect test file markers (full stem: test_set, test_bool, ...)
    file_pattern = re.compile(
        r"=== TEST FILE: test/dynamo/cpython/3_13/(test_\w+)\.py ==="
    )

    # Pattern to find the status (ok, FAIL, skipped, or ERROR) and optional reason
    status_pattern = re.compile(r'\b(ok|FAIL|skipped|ERROR)\b')

    lines = output.split('\n')
    current_module = None
    current_module_name: Optional[str] = None

    # First pass: extract expected test counts from "Ran X tests" lines
    for line in lines:
        file_match = file_pattern.search(line)
        if file_match:
            current_module_name = file_match.group(1)

        ran_match = ran_pattern.search(line)
        if ran_match and current_module_name is not None:
            expected_counts[current_module_name] = int(ran_match.group(1))

    current_module = None

    # Parse all test result lines
    for i, line in enumerate(lines):
        # Update current module if we detect a test file marker
        file_match = file_pattern.search(line)
        if file_match:
            current_module = file_match.group(1)

        match = test_start_pattern.search(line)
        if match:
            test_simple_name = match.group(1)
            class_name = match.group(2)
            test_name = match.group(3)

            # Use detected module
            module_name = current_module
            if not module_name:
                continue

            # Format test name as "TestClass.test_name"
            formatted_test_name = f"{class_name}.{test_name}"

            # Find the status - it may be on the same line or next lines
            # (warnings can appear between the test name and status)
            status_str = None
            reason_raw = ''

            # First check current line (after the "...")
            rest_of_line = line[match.end():]
            status_match = status_pattern.search(rest_of_line)

            if status_match:
                status_str = status_match.group(1)
                # Get the reason if it's on the same line
                reason_raw = rest_of_line[status_match.end():].strip()
            else:
                # Status might be on the next lines (if there are warnings)
                # Look in the next few lines
                for j in range(i + 1, min(i + 20, len(lines))):
                    next_line = lines[j]
                    status_match = status_pattern.search(next_line)
                    if status_match:
                        status_str = status_match.group(1)
                        # Get the reason if it's on this line
                        reason_raw = next_line[status_match.end():].strip()
                        break

            if not status_str:
                # Check if the rest of the line contains "Exception ignored" (cleanup error)
                # This means the test ran but had a cleanup exception
                if 'Exception ignored' in rest_of_line:
                    status_str = 'ERROR'
                    reason_raw = rest_of_line.split('Exception ignored')[1].strip()
                else:
                    # Could not find status, skip this test
                    continue

            # Map status
            if status_str == 'ok':
                status = 'PASSED'
            elif status_str == 'FAIL':
                status = 'FAILED'
            elif status_str == 'ERROR':
                status = 'ERROR'
            else:  # skipped
                status = 'SKIPPED'

            # Update summary
            if module_name not in summary:
                summary[module_name] = {
                    'total': 0,
                    'passed': 0,
                    'failed': 0,
                    'skipped': 0,
                    'error': 0
                }

            summary[module_name]['total'] += 1
            summary[module_name][status.lower()] += 1

            # Track detailed results
            if module_name not in details:
                details[module_name] = []

            # Extract reason
            reason = ''
            if status == 'PASSED':
                reason = ''
            elif status == 'SKIPPED':
                # Extract reason from between quotes: skipped 'reason'
                if reason_raw.startswith("'"):
                    # Find the closing quote (being careful about escaped quotes)
                    # The reason is everything between the first and last single quote
                    reason = reason_raw[1:-1] if reason_raw.endswith("'") else reason_raw[1:]
                    # Unescape the newlines
                    reason = reason.replace('\\n', '\n')
                else:
                    reason = reason_raw
            elif status == 'FAILED':
                reason = 'Failed in Dynamo compilation'
            elif status == 'ERROR':
                reason = reason_raw if reason_raw else 'Test execution error'

            details[module_name].append({
                'test_name': formatted_test_name,
                'status': status,
                'reason': reason
            })

    # Check for discrepancies between expected and parsed counts
    discrepancies = []
    for module_name, parsed_total in [(m, s['total']) for m, s in summary.items()]:
        expected = expected_counts.get(module_name)
        if expected and expected != parsed_total:
            discrepancies.append((module_name, expected, parsed_total))

    if discrepancies and warn_on_count_mismatch:
        print("\n⚠️  WARNING: Test count mismatch detected!")
        print("=" * 80)
        for module_name, expected, parsed in discrepancies:
            print(f"  {module_name:30s}: Expected {expected} tests, but parsed {parsed}")
        print("=" * 80)
        print("This may indicate a parsing issue. Please review the results carefully.")
        print()

    return summary, details


def calculate_failure_percentage(skipped: int, total: int) -> float:
    """Calculate failure percentage as skipped/total."""
    if total == 0:
        return 0.0
    return (skipped / total) * 100


def print_summary(summary: Dict[str, Dict[str, int]]):
    """Print results summary to console."""
    print("\n" + "="*80)
    print("CPython Test Results Summary")
    print("="*80)
    print()
    
    total_tests = 0
    total_passed = 0
    total_skipped = 0
    
    for module_name in sorted(summary.keys()):
        stats = summary[module_name]
        failure_pct = calculate_failure_percentage(stats['skipped'], stats['total'])
        
        print(f"{module_name:30s} | Total: {stats['total']:4d} | Pass: {stats['passed']:4d} | Skip: {stats['skipped']:4d} | Fail: {failure_pct:>6.2f}%")
        
        total_tests += stats['total']
        total_passed += stats['passed']
        total_skipped += stats['skipped']
    
    print()
    total_failure_pct = calculate_failure_percentage(total_skipped, total_tests)
    print(f"{'TOTAL':30s} | Total: {total_tests:4d} | Pass: {total_passed:4d} | Skip: {total_skipped:4d} | Fail: {total_failure_pct:>6.2f}%")
    print("="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Run CPython tests on PyTorch and save raw test output"
    )
    parser.add_argument(
        "--modules", "-m",
        nargs="+",
        help="Run specific test modules (e.g., test_bool test_set)",
        default=None
    )
    parser.add_argument(
        "--save-output",
        help="Custom filename for raw test output (default: all_tests_output_<commit>_<date>.txt)",
        default=None
    )
    parser.add_argument(
        "--reuse-output",
        help="Reuse previously saved test output instead of running tests",
        default=None
    )

    args = parser.parse_args()

    # Ensure data directory exists
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Get commit hash and date for filename generation
    commit = get_commit_hash(str(PYTORCH_ROOT))
    date = datetime.now().strftime("%Y%m%d")

    # Get test output (either run tests or load from file)
    if args.reuse_output:
        print(f"Loading test output from {args.reuse_output}...")
        with open(args.reuse_output, 'r') as f:
            output = f.read()
    else:
        # Run tests
        print(f"Running CPython tests...")
        output = run_pytest_tests(args.modules)

        # Auto-generate raw output filename if not provided
        if args.save_output is None:
            args.save_output = str(data_dir / f"all_tests_output_{commit}_{date}.txt")

        # Always save raw output
        print(f"Saving test output to {args.save_output}...")
        with open(args.save_output, 'w') as f:
            f.write(output)
    
    # Parse results
    print("Parsing results...")
    summary, _ = parse_pytest_output(output)
    
    if not summary:
        print("ERROR: No test results found in pytest output!")
        print("\nPytest output (last 50 lines):")
        print('\n'.join(output.split('\n')[-50:]))
        return 1
    
    # Print summary
    print_summary(summary)

    return 0


if __name__ == "__main__":
    exit(main())
