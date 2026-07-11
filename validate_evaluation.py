#!/usr/bin/env python3
"""Run the Phase 1 algorithm evaluation contract matrix."""

import argparse
import csv
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

import numpy as np

from anti_jamming.adapters import get_antijam_func
from configs.phase1_radar import get_phase1_radar_params
from unified_framework import JammerLoader, RadarEnvironment
from utils.evaluation import evaluate_algorithm_output


JAMMERS = [
    'FMZuse', 'FMNoiseAimedJam', 'FMNoiseSaopin', 'AMNoiseGaiJam',
    'SMSP', 'NoiseProductJamming', 'NoiseConvolutionJamming',
]
ALGORITHMS = ['Identity', 'WLN', 'FDC', 'adapt_filter', 'FrFT', 'qpzh']
ALGORITHM_TYPES = {
    'WLN': 'WLN',
    'FDC': 'FrequencyDomainCanceller',
    'adapt_filter': 'adapt_filter',
    'FrFT': 'frft_filter',
    'qpzh': 'qpzh',
}
ALGORITHM_PARAMS = {
    'WLN': {'par1': 0.3, 'par2': 6},
    'FDC': {'cancellation_strength': 0.8},
    'adapt_filter': {'par1': 0.01},
    'FrFT': {'mask_threshold': 0.1},
    'qpzh': {'m': 8, 'n': 2},
}


def _write_csv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _mean(rows, key):
    values = [float(row[key]) for row in rows if row.get(key) not in ('', None)]
    return float(np.mean(values)) if values else float('nan')


def _rate(rows, key):
    values = [bool(row[key]) for row in rows]
    return float(np.mean(values)) if values else float('nan')


def _conclusion(rows, algorithm):
    if algorithm == 'Identity':
        return 'Baseline'
    valid = [row for row in rows if row['interface_ok']]
    if not valid:
        return 'Interface FAIL'
    delta = _mean(valid, 'delta_sinr_db')
    pd_before = _rate(valid, 'detected_before')
    pd_after = _rate(valid, 'detected_after')
    false_before = _mean(valid, 'false_peak_count_before')
    false_after = _mean(valid, 'false_peak_count_after')
    error_before = _mean(valid, 'peak_error_before')
    error_after = _mean(valid, 'peak_error_after')
    loss = _mean(valid, 'target_peak_loss_db')
    if delta >= 0.2 and pd_after >= pd_before and loss >= -1.0:
        return 'Recommended'
    if (false_after < false_before or error_after < error_before) and pd_after >= pd_before:
        return 'Conditional'
    if delta >= -0.2 and pd_after >= pd_before and loss >= -1.0:
        return 'Neutral'
    return 'Harmful/Not demonstrated'


def run_matrix(output_dir, seeds):
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_rows = []
    oracle_notes = []
    for jammer_type in JAMMERS:
        for jsr_db in (0.0, 10.0, 20.0, 30.0):
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            radar_env = RadarEnvironment(config)
            target_template = radar_env.generate_target_signal()
            for seed in seeds:
                jammer = JammerLoader.load(jammer_type)
                generated = jammer.generate(
                    target_signal=target_template,
                    config=config,
                    jsr_db=jsr_db,
                    seed=seed,
                )
                received = generated['received']
                # No target_idx, jammer type, true jammer, or jam_info enters
                # the algorithm adapter dictionary below.
                radar_par = dict(config)
                radar_par['Srt_matrix'] = received[np.newaxis, :]
                radar_par['St_base'] = target_template
                for algorithm in ALGORITHMS:
                    base = {
                        'jammer': jammer_type,
                        'algorithm': algorithm,
                        'jsr_db': jsr_db,
                        'seed': seed,
                        'interface_ok': False,
                        'oracle_target_idx_passed': False,
                        'oracle_jammer_info_passed': False,
                    }
                    tracemalloc.start()
                    tracemalloc.reset_peak()
                    started = time.perf_counter()
                    try:
                        if algorithm == 'Identity':
                            processed = received.copy()
                        else:
                            func = get_antijam_func(ALGORITHM_TYPES[algorithm])
                            processed, _ = func(
                                radar_par, **ALGORITHM_PARAMS[algorithm]
                            )
                            processed = np.asarray(processed)[0]
                        runtime_ms = (time.perf_counter() - started) * 1000.0
                        _, peak_memory = tracemalloc.get_traced_memory()
                        metrics = evaluate_algorithm_output(
                            generated['target'],
                            received,
                            processed,
                            config,
                            runtime_ms=runtime_ms,
                            memory_usage_bytes=peak_memory,
                        )
                        base.update(metrics)
                    except Exception as exc:
                        base.update({
                            'error': repr(exc),
                            'runtime_ms': (time.perf_counter() - started) * 1000.0,
                            'memory_usage_bytes': tracemalloc.get_traced_memory()[1],
                        })
                    finally:
                        tracemalloc.stop()
                    raw_rows.append(base)
                if seed == seeds[0]:
                    oracle_notes.append({
                        'jammer': jammer_type,
                        'algorithms': ','.join(ALGORITHMS),
                        'target_idx_in_radar_par': False,
                        'jam_info_in_radar_par': False,
                        'true_jammer_signal_in_radar_par': False,
                        'adapt_filter_target_idx_dependency': True,
                        'oracle_status': 'blocked_for_fair_comparison',
                    })

    metrics_path = output_dir / 'metrics.csv'
    _write_csv(metrics_path, raw_rows)
    _write_csv(output_dir / 'oracle_check.csv', oracle_notes)

    grouped = defaultdict(list)
    for row in raw_rows:
        grouped[(row['jammer'], row['algorithm'], row['jsr_db'])].append(row)
    summary = []
    for (jammer, algorithm, jsr_db), rows in grouped.items():
        valid = [row for row in rows if row['interface_ok']]
        summary.append({
            'Jammer': jammer,
            'Algorithm': algorithm,
            'JSR_dB': jsr_db,
            'Trials': len(rows),
            'InterfacePassRate': _rate(rows, 'interface_ok'),
            'Pd_before': _rate(valid, 'detected_before') if valid else 0.0,
            'Pd_after': _rate(valid, 'detected_after') if valid else 0.0,
            'MeanDeltaSINR_dB': _mean(valid, 'delta_sinr_db') if valid else float('nan'),
            'MeanPeakError_before': _mean(valid, 'peak_error_before') if valid else float('nan'),
            'MeanPeakError_after': _mean(valid, 'peak_error_after') if valid else float('nan'),
            'MeanFalsePeak_before': _mean(valid, 'false_peak_count_before') if valid else float('nan'),
            'MeanFalsePeak_after': _mean(valid, 'false_peak_count_after') if valid else float('nan'),
            'MeanTargetPeakLoss_dB': _mean(valid, 'target_peak_loss_db') if valid else float('nan'),
            'MeanRuntime_ms': _mean(valid, 'runtime_ms') if valid else float('nan'),
            'Conclusion': _conclusion(valid, algorithm) if valid else 'Interface FAIL',
        })
    _write_csv(output_dir / 'summary.csv', summary)

    all_grouped = defaultdict(list)
    for row in raw_rows:
        all_grouped[(row['jammer'], row['algorithm'])].append(row)
    matrix = []
    for (jammer, algorithm), rows in all_grouped.items():
        valid = [row for row in rows if row['interface_ok']]
        matrix.append({
            'Jammer': jammer,
            'Algorithm': algorithm,
            'DeltaSINR_dB': _mean(valid, 'delta_sinr_db') if valid else float('nan'),
            'Pd_before': _rate(valid, 'detected_before') if valid else 0.0,
            'Pd_after': _rate(valid, 'detected_after') if valid else 0.0,
            'PeakError_before': _mean(valid, 'peak_error_before') if valid else float('nan'),
            'PeakError_after': _mean(valid, 'peak_error_after') if valid else float('nan'),
            'FalsePeak_before': _mean(valid, 'false_peak_count_before') if valid else float('nan'),
            'FalsePeak_after': _mean(valid, 'false_peak_count_after') if valid else float('nan'),
            'TargetPeakLoss_dB': _mean(valid, 'target_peak_loss_db') if valid else float('nan'),
            'Conclusion': _conclusion(valid, algorithm) if valid else 'Interface FAIL',
        })
    _write_csv(output_dir / 'algorithm_matrix.csv', matrix)
    _write_csv(output_dir / 'algorithm_applicability_matrix.csv', matrix)
    _write_csv(
        output_dir / 'identity_baseline.csv',
        [row for row in summary if row['Algorithm'] == 'Identity'],
    )
    return raw_rows, summary, matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/evaluation')
    parser.add_argument('--seeds', type=int, default=20)
    args = parser.parse_args()
    seeds = list(range(42, 42 + args.seeds))
    raw_rows, summary, matrix = run_matrix(Path(args.output_dir), seeds)
    print(f'cases={len(raw_rows)} summary_rows={len(summary)} matrix_rows={len(matrix)}')
    print(f'interface_pass_rate={np.mean([row["interface_ok"] for row in raw_rows]):.4f}')


if __name__ == '__main__':
    main()
