#!/usr/bin/env python3
"""Task 035 WLN baseline, calibration, held-out and negative-control runner."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from configs.phase1_radar import get_phase1_radar_params
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation
from utils.test_contract import (
    _call_algorithm,
    _generate_case,
    _mean,
    _std,
    _ci95,
    _whitelist_radar_par,
    _jammer_contract,
)


CALIBRATION_JSRS = (0.0, 5.0, 10.0, 20.0, 30.0)
FMZUSE_JSRS = (0.0, 10.0, 20.0, 30.0)
NEGATIVE_JSRS = (10.0, 20.0, 30.0)
NEGATIVE_JAMMERS = (
    'AMNoiseGaiJam', 'FMNoiseAimedJam', 'FMNoiseSaopin',
    'SMSP', 'NoiseProductJamming',
)
DEFAULT_CANDIDATES = [
    {'name': 'Current_WLN', 'par1': 0.3, 'par2': 6},
    {'name': 'WLN_p01_o4', 'par1': 0.1, 'par2': 4},
    {'name': 'WLN_p01_o6', 'par1': 0.1, 'par2': 6},
    {'name': 'WLN_p03_o4', 'par1': 0.3, 'par2': 4},
    {'name': 'WLN_p03_o8', 'par1': 0.3, 'par2': 8},
    {'name': 'WLN_p06_o4', 'par1': 0.6, 'par2': 4},
    {'name': 'WLN_p06_o6', 'par1': 0.6, 'par2': 6},
    {'name': 'WLN_p10_o4', 'par1': 1.0, 'par2': 4},
    {'name': 'WLN_p10_o6', 'par1': 1.0, 'par2': 6},
]


def _write_csv(path, rows):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _run_trial(jammer, jsr, seed, candidate):
    config = get_phase1_radar_params({'JSR_dB': jsr})
    generated, template, received, target = _generate_case(jammer, config, seed)
    contract = _jammer_contract(generated, jsr)
    base = {
        'jammer': jammer,
        'algorithm': candidate['name'],
        'jsr_db': jsr,
        'seed': seed,
        **contract,
    }
    identity_metrics = evaluate_algorithm_output(target, received, received, config, runtime_ms=0.0, memory_usage_bytes=0)
    identity_metrics.update(evaluate_target_preservation(target, target, config))
    radar_par = _whitelist_radar_par(config, received, template)
    result = _call_algorithm('WLN', 'WLN', radar_par, {'par1': candidate['par1'], 'par2': candidate['par2']})
    if result.get('interface_status') != 'PASS':
        return {**base, 'interface_status': 'FAIL', 'failure_reason': result.get('failure_reason', ''), 'oracle_input_status': result.get('oracle_input_status', '')}
    target_par = _whitelist_radar_par(config, target, template)
    target_result = _call_algorithm('WLN', 'WLN', target_par, {'par1': candidate['par1'], 'par2': candidate['par2']}, target_only=True)
    if target_result.get('interface_status') != 'PASS':
        return {**base, 'interface_status': 'FAIL', 'failure_reason': 'TARGET_ONLY_INTERFACE_FAIL', 'oracle_input_status': target_result.get('oracle_input_status', '')}
    metrics = evaluate_algorithm_output(
        target, received, result['output'][0], config,
        runtime_ms=result['runtime_ms'], memory_usage_bytes=result['memory_usage_bytes'],
    )
    metrics.update(evaluate_target_preservation(target, target_result['output'][0], config))
    return {
        **base,
        'interface_status': 'PASS',
        'oracle_input_status': result.get('oracle_input_status', 'FAIL'),
        'forbidden_keys_present': result.get('forbidden_keys_present', ''),
        'delta_sinr_db': metrics['sinr_after_db'] - identity_metrics['sinr_before_db'],
        'pd_identity': float(identity_metrics['detected_before']),
        'pd_algorithm': float(metrics['detected_after']),
        'peak_error_identity': identity_metrics['peak_error_before'],
        'peak_error_algorithm': metrics['peak_error_after'],
        'false_peak_identity': identity_metrics['false_peak_count_before'],
        'false_peak_algorithm': metrics['false_peak_count_after'],
        'target_only_response_change_db': metrics['target_only_response_change_db'],
        'target_preservation_status': metrics['target_preservation_status'],
        'runtime_ms': metrics['runtime_ms'],
        'memory_usage_bytes': metrics['memory_usage_bytes'],
        'max_false_peak_db_after': metrics['max_false_peak_db_after'],
    }


def _aggregate(rows, keys=('jammer', 'algorithm', 'jsr_db')):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    output = []
    for group, values in sorted(groups.items()):
        valid = [row for row in values if row.get('interface_status') == 'PASS']
        statuses = {row.get('target_preservation_status') for row in valid}
        preservation = (
            'TARGET_ERASED' if 'TARGET_ERASED' in statuses else
            'TARGET_ATTENUATED' if 'TARGET_ATTENUATED' in statuses else
            'TARGET_PRESERVED'
        )
        row = dict(zip(keys, group))
        row.update({
            'trials': len(values),
            'valid_trials': len(valid),
            'interface_status': 'PASS' if len(valid) == len(values) else 'FAIL',
            'delta_sinr_mean_db': _mean([r.get('delta_sinr_db') for r in valid]),
            'delta_sinr_std_db': _std([r.get('delta_sinr_db') for r in valid]),
            'delta_sinr_ci95_db': _ci95([r.get('delta_sinr_db') for r in valid]),
            'pd_identity': _mean([r.get('pd_identity') for r in valid]),
            'pd_algorithm': _mean([r.get('pd_algorithm') for r in valid]),
            'peak_error_identity_mean': _mean([r.get('peak_error_identity') for r in valid]),
            'peak_error_algorithm_mean': _mean([r.get('peak_error_algorithm') for r in valid]),
            'false_peak_identity_mean': _mean([r.get('false_peak_identity') for r in valid]),
            'false_peak_algorithm_mean': _mean([r.get('false_peak_algorithm') for r in valid]),
            'target_only_response_change_mean_db': _mean([r.get('target_only_response_change_db') for r in valid]),
            'target_only_response_change_ci95_db': _ci95([r.get('target_only_response_change_db') for r in valid]),
            'target_preservation_status': preservation,
            'runtime_mean_ms': _mean([r.get('runtime_ms') for r in valid]),
            'memory_usage_bytes_mean': _mean([r.get('memory_usage_bytes') for r in valid]),
            'jammer_contract_status': ','.join(sorted({str(r.get('jammer_contract_status')) for r in values})),
            'oracle_input_status': ','.join(sorted({str(r.get('oracle_input_status')) for r in values})),
        })
        output.append(row)
    return output


def _score(rows):
    grouped = _aggregate(rows)
    fmz = [r for r in grouped if r['jammer'] == 'FMZuse']
    if not fmz:
        return float('-inf')
    gain = _mean([r['delta_sinr_mean_db'] for r in fmz])
    low_jsr_harm = max(0.0, -next((r['delta_sinr_mean_db'] for r in fmz if r['jsr_db'] == 0.0), 0.0))
    damage = max(0.0, -_mean([r['target_only_response_change_mean_db'] for r in fmz]))
    false_increase = _mean([r['false_peak_algorithm_mean'] - r['false_peak_identity_mean'] for r in fmz])
    return float(gain - low_jsr_harm - damage - max(0.0, false_increase))


def run_baseline(output_dir, seeds, jsrs=FMZUSE_JSRS):
    candidate = DEFAULT_CANDIDATES[0]
    rows = [_run_trial('FMZuse', jsr, seed, candidate) for jsr in jsrs for seed in seeds]
    _write_csv(Path(output_dir) / 'current_wln_results.csv', rows)
    _write_csv(Path(output_dir) / 'current_wln_aggregate.csv', _aggregate(rows))
    (Path(output_dir) / 'baseline_metadata.json').write_text(json.dumps({
        'branch': 'algorithm_design_0711',
        'baseline_commit': 'fe5a2e1b89ab20ad1b039054a4094a2bc63df6f2',
        'algorithm': 'Current_WLN',
        'parameters': candidate,
        'jsrs_db': list(jsrs),
        'seeds': [min(seeds), max(seeds), len(seeds)],
        'contract': 'Task 034-fix3',
    }, indent=2))
    return rows


def run_calibration(output_dir, seeds):
    all_rows = []
    ranking = []
    for candidate in DEFAULT_CANDIDATES:
        rows = [_run_trial('FMZuse', jsr, seed, candidate) for jsr in CALIBRATION_JSRS for seed in seeds]
        all_rows.extend(rows)
        ranking.append({**candidate, 'score': _score(rows)})
    _write_csv(Path(output_dir) / 'parameter_search.csv', _aggregate(all_rows, keys=('algorithm', 'jsr_db')))
    _write_csv(Path(output_dir) / 'candidate_ranking.csv', ranking)
    selected = max(ranking, key=lambda row: row['score'])
    (Path(output_dir) / 'selected_candidate.json').write_text(json.dumps(selected, indent=2))
    return selected, all_rows


def run_comparison(output_dir, jammer_names, jsrs, seeds, candidates):
    trial_rows = []
    for jammer in jammer_names:
        if jammer in ('ISDJ', 'SliceCombineJam'):
            continue
        for candidate in candidates:
            algorithm_rows = [_run_trial(jammer, jsr, seed, candidate) for jsr in jsrs for seed in seeds]
            trial_rows.extend(algorithm_rows)
            for row in algorithm_rows:
                if candidate != candidates[0]:
                    continue
                identity = dict(row)
                identity.update({
                    'algorithm': 'Identity',
                    'delta_sinr_db': 0.0,
                    'pd_algorithm': row.get('pd_identity'),
                    'peak_error_algorithm': row.get('peak_error_identity'),
                    'false_peak_algorithm': row.get('false_peak_identity'),
                    'target_only_response_change_db': 0.0,
                    'target_preservation_status': 'TARGET_PRESERVED',
                    'runtime_ms': 0.0,
                    'memory_usage_bytes': 0,
                })
                trial_rows.append(identity)
    aggregate = _aggregate(trial_rows)
    _write_csv(Path(output_dir) / 'per_trial_results.csv', trial_rows)
    _write_csv(Path(output_dir) / 'aggregate_results.csv', aggregate)
    return trial_rows, aggregate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('baseline', 'calibration', 'heldout', 'negative'), required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    output = Path(args.output_dir)
    if args.mode == 'baseline':
        run_baseline(output, range(1000, 1020))
    elif args.mode == 'calibration':
        run_calibration(output, range(1000, 1020))
    else:
        selected = json.loads(Path('results/phase1/task035/calibration/selected_candidate.json').read_text())
        candidates = [DEFAULT_CANDIDATES[0], selected]
        if args.mode == 'heldout':
            run_comparison(output, ('FMZuse',), FMZUSE_JSRS, range(2000, 2050), candidates)
        else:
            run_comparison(output, NEGATIVE_JAMMERS, NEGATIVE_JSRS, range(2000, 2030), candidates)


if __name__ == '__main__':
    main()
