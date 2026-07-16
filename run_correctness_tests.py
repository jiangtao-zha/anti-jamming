#!/usr/bin/env python3
"""Run fast correctness regression checks, without performance ranking."""

import sys
from pathlib import Path

from utils.test_contract import run_correctness_regression


def run_all_tests():
    """Run loader, adapter, no-jammer and boundary regression checks."""
    summary = run_correctness_regression(
        Path('results/phase1/task034_fix3/correctness_regression')
    )
    print(f"Loader cases: {summary['loader_cases']}")
    print(f"Adapter cases: {summary['adapter_cases']}")
    print(f"No-jammer cases: {summary['no_jammer_cases']}")
    print(f"Failures: {summary['failures']}")
    print(f"Process Exit Code: {summary['exit_code']}")
    return summary


if __name__ == '__main__':
    result = run_all_tests()
    sys.exit(result['exit_code'])
