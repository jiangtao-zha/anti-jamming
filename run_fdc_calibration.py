#!/usr/bin/env python3
"""Task 034 FDC baselines, parameter search, and negative tests."""

import argparse
import csv
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from anti_jamming.adapters import get_antijam_func
from configs.phase1_radar import get_phase1_radar_params
from unified_framework import JammerLoader, RadarEnvironment
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation


ALGORITHMS = {
    'Identity': None,
    'Current_FDC': 'FrequencyDomainCanceller',
    'New_FDC': 'FrequencyDomainCancellerCalibrated',
}
JAMMERS = ['AMNoiseGaiJam', 'FMZuse', 'FMNoiseAimedJam', 'NoiseProductJamming']
SEARCH_STRENGTHS = (0.2, 0.4, 0.6, 0.8, 1.0)
SEARCH_REGULARIZATIONS = (0.05, 0.15, 0.30)


def write_csv(path, rows):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def algorithm_params(name, strength=0.6, regularization=0.15):
    if name == 'Current_FDC':
        return {'cancellation_strength': strength}
    if name == 'New_FDC':
        return {
            'cancellation_strength': strength,
            'regularization': regularization,
        }
    return {}


def algorithm_radar_par(config, received, template):
    # Deliberately whitelist the adapter inputs.  In particular, target_idx,
    # jammer metadata, and the true jammer component are not passed.
    allowed = ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N', 'target_dist')
    radar_par = {key: config[key] for key in allowed if key in config}
    radar_par['Srt_matrix'] = received[np.newaxis, :]
    radar_par['St_base'] = template
    return radar_par


def run_one(config, jammer_name, jsr_db, seed, algorithm, strength, regularization):
    np.random.seed(seed)
    env = RadarEnvironment(config)
    target = env.generate_target_signal()
    jammer = JammerLoader.load(jammer_name)
    generated = jammer.generate(
        target_signal=target,
        config=config,
        jsr_db=jsr_db,
        seed=seed,
    )
    received = generated['received']
    radar_par = algorithm_radar_par(config, received, target)
    target_only_par = algorithm_radar_par(config, generated['target'], target)
    params = algorithm_params(algorithm, strength, regularization)
    started = time.perf_counter()
    if algorithm == 'Identity':
        processed = received.copy()
        processed_target = generated['target'].copy()
    else:
        func = get_antijam_func(ALGORITHMS[algorithm])
        processed, _ = func(radar_par, **params)
        processed_target, _ = func(target_only_par, **params)
        processed = np.asarray(processed)[0]
        processed_target = np.asarray(processed_target)[0]
    runtime_ms = (time.perf_counter() - started) * 1000.0
    metrics = evaluate_algorithm_output(
        generated['target'], received, processed, config, runtime_ms=runtime_ms
    )
    metrics.update(evaluate_target_preservation(
        generated['target'], processed_target, config
    ))
    metrics.update({
        'jammer': jammer_name,
        'algorithm': algorithm,
        'jsr_db': jsr_db,
        'seed': seed,
        'parameter_strength': strength,
        'parameter_regularization': regularization,
        'interface_ok': True,
    })
    return metrics


def run_cases(output_dir, jammers, algorithms, jsrs, seeds, strength, regularization):
    rows = []
    for jammer_name in jammers:
        for jsr_db in jsrs:
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            for seed in seeds:
                for algorithm in algorithms:
                    try:
                        rows.append(run_one(
                            config, jammer_name, jsr_db, seed, algorithm,
                            strength, regularization,
                        ))
                    except Exception as exc:
                        rows.append({
                            'jammer': jammer_name, 'algorithm': algorithm,
                            'jsr_db': jsr_db, 'seed': seed,
                            'parameter_strength': strength,
                            'parameter_regularization': regularization,
                            'interface_ok': False, 'error': repr(exc),
                        })
    write_csv(output_dir, rows)
    return rows


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        if row.get('interface_ok'):
            grouped[(row['jammer'], row['algorithm'], row['jsr_db'])].append(row)
    summaries = []
    for (jammer, algorithm, jsr_db), group in sorted(grouped.items()):
        def mean(key):
            return float(np.mean([float(row[key]) for row in group]))
        def ci95(key):
            values = np.asarray([float(row[key]) for row in group])
            if len(values) < 2:
                return 0.0
            return float(1.96 * np.std(values, ddof=1) / np.sqrt(len(values)))
        summaries.append({
            'Jammer': jammer,
            'Algorithm': algorithm,
            'JSR_dB': jsr_db,
            'Trials': len(group),
            'DeltaSINR_mean_dB': mean('delta_sinr_db'),
            'DeltaSINR_std_dB': float(np.std([float(row['delta_sinr_db']) for row in group], ddof=1)) if len(group) > 1 else 0.0,
            'DeltaSINR_ci95_dB': ci95('delta_sinr_db'),
            'Pd_before': mean('detected_before'),
            'Pd_after': mean('detected_after'),
            'PeakError_before': mean('peak_error_before'),
            'PeakError_after': mean('peak_error_after'),
            'FalsePeak_before': mean('false_peak_count_before'),
            'FalsePeak_after': mean('false_peak_count_after'),
            'TargetOnlyResponseChange_mean_dB': mean('target_only_response_change_db'),
            'TargetOnlyResponseChange_ci95_dB': ci95('target_only_response_change_db'),
            'Runtime_mean_ms': mean('runtime_ms'),
        })
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/fdc')
    parser.add_argument('--seeds', type=int, default=20)
    parser.add_argument('--strength', type=float, default=1.0)
    parser.add_argument('--regularization', type=float, default=0.05)
    parser.add_argument('--skip-search', action='store_true')
    args = parser.parse_args()
    root = Path(args.output_dir)
    seeds = list(range(42, 42 + args.seeds))
    jsrs = (0.0, 10.0, 20.0, 30.0)

    if not args.skip_search:
        search_rows = []
        for strength in SEARCH_STRENGTHS:
            for regularization in SEARCH_REGULARIZATIONS:
                config = get_phase1_radar_params({'JSR_dB': 20.0})
                rows = run_cases(
                    root / 'parameter_search' / f's{strength:g}_r{regularization:g}.csv',
                    ['AMNoiseGaiJam'], ['New_FDC'], (20.0,), seeds,
                    strength, regularization,
                )
                summary = summarize(rows)[0]
                search_rows.append({
                    'strength': strength,
                    'regularization': regularization,
                    **summary,
                })
        write_csv(root / 'parameter_search' / 'summary.csv', search_rows)

    baseline_rows = run_cases(
        root / 'baseline' / 'metrics.csv', ['AMNoiseGaiJam'],
        ['Identity', 'Current_FDC'], jsrs, seeds, args.strength, args.regularization,
    )
    am_rows = run_cases(
        root / 'am_results' / 'metrics.csv', ['AMNoiseGaiJam'],
        ['Identity', 'Current_FDC', 'New_FDC'], jsrs, seeds,
        args.strength, args.regularization,
    )
    negative_rows = run_cases(
        root / 'negative_results' / 'metrics.csv',
        ['FMZuse', 'FMNoiseAimedJam', 'NoiseProductJamming'],
        ['Identity', 'Current_FDC', 'New_FDC'], jsrs, seeds,
        args.strength, args.regularization,
    )
    final_rows = summarize(am_rows + negative_rows)
    write_csv(root / 'final_matrix.csv', final_rows)
    print(f'baseline_cases={len(baseline_rows)}')
    print(f'am_cases={len(am_rows)} negative_cases={len(negative_rows)}')
    print(f'final_rows={len(final_rows)}')


if __name__ == '__main__':
    main()
