#!/usr/bin/env python3
"""Compatibility entry point for the unified Phase 1 contract runner."""

import sys
from pathlib import Path

from utils.test_contract import print_summary, run_contract_matrix


def run_all_tests():
    """Run the same contract as validate_algorithms.py for traceability."""
    summary = run_contract_matrix(Path('results/phase1/task034_fix'))
    print_summary(summary)
    return summary


if __name__ == '__main__':
    result = run_all_tests()
    sys.exit(result['exit_code'])
