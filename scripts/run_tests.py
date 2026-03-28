#!/usr/bin/env python
"""
Automated Test Runner for NeuraLeads AI Cold-Email Automation System.

This script runs all tests and generates a comprehensive test report.

Usage:
    python scripts/run_tests.py [--unit] [--integration] [--e2e] [--all] [--report]

Options:
    --unit          Run only unit tests
    --integration   Run only integration tests
    --e2e           Run only end-to-end tests
    --all           Run all tests (default)
    --report        Generate HTML report
    --verbose       Verbose output
"""

import argparse
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
REPORTS_DIR = PROJECT_ROOT / "test_reports"


def ensure_reports_dir():
    """Ensure test reports directory exists."""
    REPORTS_DIR.mkdir(exist_ok=True)


def run_command(cmd, cwd=None):
    """Run a command and return the result."""
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    result = subprocess.run(
        cmd,
        cwd=cwd or BACKEND_DIR,
        capture_output=False,
        text=True
    )
    return result.returncode


def run_unit_tests(verbose=False, report=False):
    """Run unit tests."""
    print("\n" + "="*60)
    print("RUNNING UNIT TESTS")
    print("="*60)

    cmd = ["python", "-m", "pytest", "tests/unit", "-v"]

    if report:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_DIR / f"unit_test_report_{timestamp}.html"
        cmd.extend(["--html", str(report_path), "--self-contained-html"])

    return run_command(cmd)


def run_integration_tests(verbose=False, report=False):
    """Run integration tests."""
    print("\n" + "="*60)
    print("RUNNING INTEGRATION TESTS")
    print("="*60)

    cmd = ["python", "-m", "pytest", "tests/integration", "-v"]

    if report:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_DIR / f"integration_test_report_{timestamp}.html"
        cmd.extend(["--html", str(report_path), "--self-contained-html"])

    return run_command(cmd)


def run_e2e_tests(verbose=False, report=False):
    """Run end-to-end tests."""
    print("\n" + "="*60)
    print("RUNNING END-TO-END TESTS")
    print("="*60)

    cmd = ["python", "-m", "pytest", "tests/e2e", "-v"]

    if report:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_DIR / f"e2e_test_report_{timestamp}.html"
        cmd.extend(["--html", str(report_path), "--self-contained-html"])

    return run_command(cmd)


def run_all_tests(verbose=False, report=False):
    """Run all tests with coverage."""
    print("\n" + "="*60)
    print("RUNNING ALL TESTS WITH COVERAGE")
    print("="*60)

    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "-v",
        "--cov=app",
        "--cov-report=term-missing"
    ]

    if report:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = REPORTS_DIR / f"full_test_report_{timestamp}.html"
        coverage_path = REPORTS_DIR / f"coverage_{timestamp}"
        cmd.extend([
            "--html", str(report_path), "--self-contained-html",
            f"--cov-report=html:{coverage_path}"
        ])

    return run_command(cmd)


def generate_test_summary(results):
    """Generate a test summary report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = f"""
================================================================================
                    NEURALEADS AI TEST EXECUTION SUMMARY
================================================================================

Execution Time: {timestamp}

Test Results:
-------------
"""

    for test_type, result in results.items():
        status = "PASSED" if result == 0 else "FAILED"
        summary += f"  {test_type:20} : {status}\n"

    overall = "PASSED" if all(r == 0 for r in results.values()) else "FAILED"
    summary += f"""
--------------------------------------------------------------------------------
Overall Status: {overall}
--------------------------------------------------------------------------------

Test Reports Location: {REPORTS_DIR}

================================================================================
"""

    print(summary)

    # Save summary to file
    ensure_reports_dir()
    summary_path = REPORTS_DIR / f"test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(summary_path, 'w') as f:
        f.write(summary)

    print(f"Summary saved to: {summary_path}")

    return overall == "PASSED"


def main():
    parser = argparse.ArgumentParser(description="Run NeuraLeads AI tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--e2e", action="store_true", help="Run e2e tests only")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--report", action="store_true", help="Generate HTML reports")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Default to running all tests if no specific type selected
    if not any([args.unit, args.integration, args.e2e]):
        args.all = True

    ensure_reports_dir()
    results = {}

    print("\n" + "="*60)
    print("       NEURALEADS AI AUTOMATED TEST SUITE")
    print("="*60)
    print(f"\nStart Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Report Generation: {'Enabled' if args.report else 'Disabled'}")

    try:
        if args.all:
            results["All Tests"] = run_all_tests(args.verbose, args.report)
        else:
            if args.unit:
                results["Unit Tests"] = run_unit_tests(args.verbose, args.report)
            if args.integration:
                results["Integration Tests"] = run_integration_tests(args.verbose, args.report)
            if args.e2e:
                results["E2E Tests"] = run_e2e_tests(args.verbose, args.report)

        success = generate_test_summary(results)
        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"\nError running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
