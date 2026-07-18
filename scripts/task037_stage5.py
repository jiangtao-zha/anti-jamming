#!/usr/bin/env python3
"""Task 037 Stage 5 decision-gated calibration record."""

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
    stage4 = output.parents[0] / 'stage4' / 'summary.json'
    if not stage3.exists() or not stage4.exists():
        raise SystemExit('MISSING_DECISION_GATE_SUMMARY')
    oracle = json.loads(stage3.read_text())
    prototype = json.loads(stage4.read_text())
    if oracle.get('oracle_upper_bound') != 'FAILED' or prototype.get('status') != 'SKIPPED_BY_DECISION_GATE':
        raise SystemExit('DECISION_GATE_MISMATCH: Stage 5 skip requires Stage 3 failure and Stage 4 skip')
    fields = ['candidate_id', 'status', 'reason']
    for name in ('nominal_candidates.csv', 'behavior_signatures.csv', 'equivalence_classes.csv', 'effective_candidates.csv', 'parameter_search.csv', 'aggregate_results.csv', 'candidate_ranking.csv'):
        empty_csv(output / name, fields)
    (output / 'selected_candidate.json').write_text(json.dumps({'status': 'SKIPPED_BY_DECISION_GATE', 'selected_candidate': None, 'heldout_mode': 'REJECTION_CONFIRMATION_ONLY'}, indent=2) + '\n')
    summary = {'task': '037', 'stage': 'stage5', 'status': 'SKIPPED_BY_DECISION_GATE', 'reason': 'ORACLE_UPPER_BOUND_FAILED', 'nominal_candidate_count': 0, 'effective_candidate_count': 0, 'heldout_mode': 'REJECTION_CONFIRMATION_ONLY', 'candidate_matrix_eligible': False, 'rl_eligible': False, 'next_stage': 'stage6_rejection_confirmation'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
