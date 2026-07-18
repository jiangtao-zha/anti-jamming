#!/usr/bin/env python3
"""Task 037 Stage 4 decision-gated observable prototype record."""

import argparse
import csv
import json
from pathlib import Path


def empty_csv(path, fields):
    with path.open('w', newline='') as handle:
        csv.DictWriter(handle, fieldnames=fields).writeheader()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage3 = output.parents[0] / 'stage3' / 'oracle_upper_bound_summary.json'
    if not stage3.exists():
        raise SystemExit(f'MISSING_STAGE3_SUMMARY: {stage3}')
    oracle = json.loads(stage3.read_text())
    if oracle.get('oracle_upper_bound') != 'FAILED':
        raise SystemExit('DECISION_GATE_MISMATCH: Stage 4 skip requires oracle_upper_bound=FAILED')
    empty_csv(output / 'design_candidates.csv', ['candidate_id', 'direction', 'status'])
    empty_csv(output / 'design_scores.csv', ['candidate_id', 'score', 'status'])
    empty_csv(output / 'smoke_results.csv', ['candidate_id', 'status', 'reason'])
    (output / 'selected_designs.json').write_text(json.dumps({'status': 'SKIPPED_BY_DECISION_GATE', 'reason': 'ORACLE_UPPER_BOUND_FAILED', 'designs': []}, indent=2) + '\n')
    (output / 'prototype_metadata.json').write_text(json.dumps({'status': 'SKIPPED_BY_DECISION_GATE', 'implemented': False, 'candidate_matrix_eligible': False, 'rl_eligible': False}, indent=2) + '\n')
    summary = {'task': '037', 'stage': 'stage4', 'status': 'SKIPPED_BY_DECISION_GATE', 'reason': 'ORACLE_UPPER_BOUND_FAILED', 'candidate_count': 0, 'implemented': False, 'candidate_matrix_eligible': False, 'rl_eligible': False, 'next_stage': 'stage5_skipped_by_decision_gate'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
