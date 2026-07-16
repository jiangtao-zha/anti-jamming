#!/usr/bin/env python3
"""Run the unified Phase 1 interface/performance contract matrix."""

import sys
from pathlib import Path

from utils.test_contract import print_summary, run_contract_matrix


def main():
    output_dir = Path('results/phase1/task034_fix2/performance_contract')
    summary = run_contract_matrix(output_dir)
    print_summary(summary)
    return summary


if __name__ == '__main__':
    result = main()
    sys.exit(result['exit_code'])
