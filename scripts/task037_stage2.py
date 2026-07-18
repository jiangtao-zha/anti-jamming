#!/usr/bin/env python3
"""Task 037 Stage 2: component-level FrFT separability diagnostics.

The true target/jammer/noise components are used only in this diagnostic
runner.  No component or evaluation truth is passed to an algorithm adapter.
The diagnostic window is the 1000-sample receive window used by the current
FrFT adapter, centered at each prescribed target position.
"""

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anti_jamming.frft_filter import _centered_unitary_dft
from scripts.task036_fix_fixture import (
    JAMMERS,
    JSRS,
    SAFE_TARGET_CENTERS,
    compose,
    generate_bank,
)


SEEDS = tuple(range(10000, 10030))
ORDERS = np.round(np.arange(-1.0, 1.0001, 0.02), 2)
TOP_K = 10
WINDOW_LENGTH = 1000
METRICS = ('peak', 'topk', 'entropy')
SIGNALS = ('target', 'jammer', 'noise', 'received')
EPS = 1e-30
FORMAL_TARGET_JAMMERS = ('SMSP', 'FMNoiseSaopin')


def write_csv(path, rows):
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
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def d4_distance(a, b):
    return float(min(abs(float(a) - float(b) + 4.0 * k) for k in range(-2, 3)))


def centered_peak_width(power, peak_index):
    peak = float(power[peak_index])
    if peak <= 0.0:
        return 0
    threshold = 0.5 * peak
    left = int(peak_index)
    right = int(peak_index)
    while left > 0 and power[left - 1] >= threshold:
        left -= 1
    while right + 1 < power.size and power[right + 1] >= threshold:
        right += 1
    return right - left + 1


def support90(power):
    total = float(np.sum(power))
    if total <= EPS:
        return 0
    return int(np.searchsorted(np.cumsum(np.sort(power)[::-1]), 0.9 * total) + 1)


def transform_stack(values):
    """Return all coarse-grid FrFT outputs without repeatedly recomputing U."""
    values = np.asarray(values, dtype=complex).reshape(-1)
    u0 = values.copy()
    u1 = _centered_unitary_dft(u0)
    u2 = _centered_unitary_dft(u1)
    u3 = _centered_unitary_dft(u2)
    powers = np.stack((u0, u1, u2, u3), axis=0)
    projectors = np.stack([
        sum(np.exp(1j * np.pi * k * m / 2.0) * powers[m] for m in range(4)) / 4.0
        for k in range(4)
    ], axis=0)
    phases = np.exp(-1j * np.pi * np.outer(ORDERS, np.arange(4)) / 2.0)
    return phases @ projectors


def metric_rows(signal_name, stack, case):
    rows = []
    for order, transformed in zip(ORDERS, stack):
        power = np.abs(transformed) ** 2
        total = float(np.sum(power))
        if total <= EPS:
            peak = 0.0
            topk = 0.0
            entropy = 0.0
            support = 0
            width = 0
            peak_index = -1
        else:
            probabilities = power / total
            peak_index = int(np.argmax(power))
            peak = float(power[peak_index] / total)
            topk = float(np.sum(np.sort(power)[-TOP_K:]) / total)
            entropy = float(-np.sum(probabilities * np.log(probabilities + EPS)))
            support = support90(power)
            width = centered_peak_width(power, peak_index)
        rows.append({
            **case,
            'signal': signal_name,
            'order': float(order),
            'top_k': TOP_K,
            'peak_bin': peak_index,
            'peak_concentration': peak,
            'topk_concentration': topk,
            'spectral_entropy': entropy,
            'support_90': support,
            'peak_width_half_power': width,
            'energy': total,
            'metric_scope': 'FORMAL_TARGET_JAMMERS' if case['jammer'] in FORMAL_TARGET_JAMMERS else 'SUPPLEMENTARY_DIAGNOSTIC',
        })
    return rows


def best_orders(stack):
    values = []
    for transformed in stack:
        power = np.abs(transformed) ** 2
        total = float(np.sum(power))
        if total <= EPS:
            values.append((0.0, 0.0, 0.0))
        else:
            probabilities = power / total
            values.append((
                float(np.max(power) / total),
                float(np.sum(np.sort(power)[-TOP_K:]) / total),
                float(-np.sum(probabilities * np.log(probabilities + EPS))),
            ))
    scores = np.asarray(values)
    return {
        'peak': float(ORDERS[int(np.argmax(scores[:, 0]))]),
        'topk': float(ORDERS[int(np.argmax(scores[:, 1]))]),
        'entropy': float(ORDERS[int(np.argmin(scores[:, 2]))]),
    }


def normalized_overlap(target_power, jammer_power):
    target_total = float(np.sum(target_power))
    jammer_total = float(np.sum(jammer_power))
    if target_total <= EPS or jammer_total <= EPS:
        return {'overlap': 0.0, 'target_inside_jammer': 0.0, 'jammer_inside_target': 0.0, 'iou': 0.0, 'center_distance_combined_width': float('nan')}
    target_prob = target_power / target_total
    jammer_prob = jammer_power / jammer_total
    target_support = target_prob >= np.quantile(target_prob[target_prob > 0], 0.9) if np.any(target_prob > 0) else np.zeros_like(target_prob, dtype=bool)
    jammer_support = jammer_prob >= np.quantile(jammer_prob[jammer_prob > 0], 0.9) if np.any(jammer_prob > 0) else np.zeros_like(jammer_prob, dtype=bool)
    intersection = np.logical_and(target_support, jammer_support)
    union = np.logical_or(target_support, jammer_support)
    target_peak = int(np.argmax(target_prob))
    jammer_peak = int(np.argmax(jammer_prob))
    target_width = max(1, int(np.sum(target_support)))
    jammer_width = max(1, int(np.sum(jammer_support)))
    return {
        'overlap': float(np.sum(np.minimum(target_prob, jammer_prob))),
        'target_inside_jammer': float(np.sum(target_prob[jammer_support])),
        'jammer_inside_target': float(np.sum(jammer_prob[target_support])),
        'iou': float(np.sum(intersection) / (np.sum(union) + EPS)),
        'center_distance_combined_width': float(abs(target_peak - jammer_peak) / (target_width + jammer_width)),
    }


def case_key(jammer, jsr, seed, center):
    return f'{jammer}|jsr={jsr:g}|seed={seed}|center={center}'


def summarize(values):
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return {'n': 0, 'mean': None, 'std': None, 'ci95_low': None, 'ci95_high': None, 'min': None, 'q25': None, 'median': None, 'q75': None, 'max': None}
    mean = float(np.mean(array))
    std = float(np.std(array, ddof=1)) if array.size > 1 else 0.0
    margin = 1.96 * std / np.sqrt(array.size)
    return {'n': int(array.size), 'mean': mean, 'std': std, 'ci95_low': mean - margin, 'ci95_high': mean + margin, 'min': float(np.min(array)), 'q25': float(np.quantile(array, 0.25)), 'median': float(np.median(array)), 'q75': float(np.quantile(array, 0.75)), 'max': float(np.max(array))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    per_order = []
    optimal = []
    gaps = []
    overlaps = []
    case_records = []
    noise_hashes = {}
    transform_cache = {}

    total_cases = len(JAMMERS) * len(JSRS) * len(SEEDS) * len(SAFE_TARGET_CENTERS)
    completed_cases = 0
    for jammer in JAMMERS:
        for jsr in JSRS:
            for seed in SEEDS:
                bank = generate_bank(jammer, jsr, seed)
                full_noise_hash = hashlib.sha256(np.asarray(bank.noise_base).tobytes()).hexdigest()
                noise_hashes[(jammer, jsr, seed)] = full_noise_hash
                for center in SAFE_TARGET_CENTERS:
                    case_id = case_key(jammer, jsr, seed, center)
                    composed = compose(bank, center)
                    start = int(center) - WINDOW_LENGTH // 2
                    stop = start + WINDOW_LENGTH
                    case = {
                        'case_id': case_id,
                        'jammer': jammer,
                        'jsr_db': float(jsr),
                        'seed': int(seed),
                        'target_position': int(center),
                        'window_start': start,
                        'window_stop': stop,
                        'window_length': WINDOW_LENGTH,
                        'fixture_label': composed['fixture_label'],
                        'position_policy': composed['position_policy'],
                        'measured_jsr_db': composed['measured_jsr_db'],
                        'jsr_status': composed['jsr_status'],
                    }
                    signals = {}
                    for name, value in (
                        ('target', composed['target']),
                        ('jammer', composed['jammer_component']),
                        ('noise', composed['noise']),
                        ('received', composed['received']),
                    ):
                        local = np.asarray(value[start:stop], dtype=complex)
                        cache_key = (name, hashlib.sha256(local.tobytes()).hexdigest())
                        if cache_key not in transform_cache:
                            transform_cache[cache_key] = transform_stack(local)
                        signals[name] = transform_cache[cache_key]
                        if jammer in FORMAL_TARGET_JAMMERS:
                            per_order.extend(metric_rows(name, signals[name], case))

                    best = {name: best_orders(signals[name]) for name in SIGNALS}
                    for metric in METRICS:
                        target_order = best['target'][metric]
                        jammer_order = best['jammer'][metric]
                        received_order = best['received'][metric]
                        gap = d4_distance(target_order, jammer_order)
                        gaps.append({**case, 'selection_metric': metric, 'a_target': target_order, 'a_jammer': jammer_order, 'a_received': received_order, 'order_gap_d4': gap, 'metric_scope': 'FORMAL_TARGET_JAMMERS' if jammer in FORMAL_TARGET_JAMMERS else 'SUPPLEMENTARY_DIAGNOSTIC'})
                        optimal.extend([
                            {**case, 'signal': signal_name, 'selection_metric': metric, 'optimal_order': best[signal_name][metric], 'metric_scope': 'FORMAL_TARGET_JAMMERS' if jammer in FORMAL_TARGET_JAMMERS else 'SUPPLEMENTARY_DIAGNOSTIC'}
                            for signal_name in SIGNALS
                        ])
                        for source_name, source_order in (('target', target_order), ('jammer', jammer_order), ('received', received_order)):
                            target_power = np.abs(signals['target'][int(np.argmin(np.abs(ORDERS - source_order)))]) ** 2
                            jammer_power = np.abs(signals['jammer'][int(np.argmin(np.abs(ORDERS - source_order)))]) ** 2
                            overlap = normalized_overlap(target_power, jammer_power)
                            overlaps.append({**case, 'selection_metric': metric, 'order_source': source_name, 'evaluation_order': source_order, **overlap, 'metric_scope': 'FORMAL_TARGET_JAMMERS' if jammer in FORMAL_TARGET_JAMMERS else 'SUPPLEMENTARY_DIAGNOSTIC'})
                    case_records.append({**case, 'noise_hash': full_noise_hash, 'noise_same_across_positions': True})
                    completed_cases += 1
                    if completed_cases % 100 == 0:
                        print(f'completed_cases={completed_cases}/{total_cases}', flush=True)

    write_csv(output / 'per_order_metrics.csv', per_order)
    write_csv(output / 'optimal_orders.csv', optimal)
    write_csv(output / 'domain_overlap.csv', overlaps)

    gap_groups = defaultdict(list)
    for row in gaps:
        gap_groups[(row['jammer'], row['jsr_db'], row['selection_metric'])].append(row['order_gap_d4'])
    gap_summary = []
    for (jammer, jsr, metric), values in sorted(gap_groups.items()):
        gap_summary.append({'jammer': jammer, 'jsr_db': jsr, 'selection_metric': metric, 'metric_scope': 'FORMAL_TARGET_JAMMERS' if jammer in FORMAL_TARGET_JAMMERS else 'SUPPLEMENTARY_DIAGNOSTIC', **summarize(values)})
    write_csv(output / 'order_gap_summary.csv', gap_summary)

    position_groups = defaultdict(list)
    for row in gaps:
        position_groups[(row['jammer'], row['jsr_db'], row['selection_metric'], row['target_position'])].append(row['order_gap_d4'])
    position_rows = []
    for (jammer, jsr, metric, center), values in sorted(position_groups.items()):
        stats = summarize(values)
        position_rows.append({'jammer': jammer, 'jsr_db': jsr, 'selection_metric': metric, 'target_position': center, 'metric_scope': 'FORMAL_TARGET_JAMMERS' if jammer in FORMAL_TARGET_JAMMERS else 'SUPPLEMENTARY_DIAGNOSTIC', **stats})
    write_csv(output / 'position_robustness.csv', position_rows)

    formal_gaps = [row for row in gap_summary if row['jammer'] in FORMAL_TARGET_JAMMERS and row['selection_metric'] == 'peak' and row['jsr_db'] in (10.0, 20.0, 30.0)]
    formal_overlaps = [row for row in overlaps if row['jammer'] in FORMAL_TARGET_JAMMERS and row['order_source'] in ('target', 'jammer', 'received')]
    gate_by_jammer = {}
    for jammer in FORMAL_TARGET_JAMMERS:
        rows = [row for row in formal_gaps if row['jammer'] == jammer]
        values = [float(row['median']) for row in rows if row['median'] is not None]
        overlap_values = [float(row['overlap']) for row in formal_overlaps if row['jammer'] == jammer and np.isfinite(float(row['overlap']))]
        gate_by_jammer[jammer] = {
            'order_gap_median_across_jsr': float(np.median(values)) if values else None,
            'order_gap_q25_across_jsr': float(np.quantile(values, 0.25)) if values else None,
            'domain_overlap_median': float(np.median(overlap_values)) if overlap_values else None,
            'preliminary_order_gate': bool(values and np.median(values) > 0.08 and np.quantile(values, 0.25) > 0.04),
            'preliminary_spatial_gate': bool(overlap_values and np.median(overlap_values) < 0.5),
        }
    summary = {
        'task': '037',
        'stage': 'stage2',
        'status': 'COMPLETED',
        'diagnostic_window': 'local 1000-sample window centered at prescribed target position',
        'orders': {'min': float(ORDERS[0]), 'max': float(ORDERS[-1]), 'step': 0.02, 'periodic_distance': 'd4(a,b)=min_k |a-b+4k|'},
        'seeds': [SEEDS[0], SEEDS[-1], len(SEEDS)],
        'target_centers': list(SAFE_TARGET_CENTERS),
        'jsrs_db': list(JSRS),
        'formal_target_jammers': list(FORMAL_TARGET_JAMMERS),
        'supplementary_jammers': [name for name in JAMMERS if name not in FORMAL_TARGET_JAMMERS],
        'total_cases': total_cases,
        'completed_cases': completed_cases,
        'formal_per_order_rows': len(per_order),
        'component_truth_used_only_in_runner': True,
        'noise_realization_reused_across_positions': all(row['noise_same_across_positions'] for row in case_records),
        'preliminary_gate_by_target_jammer': gate_by_jammer,
        'stage3_recommendation': 'RUN_ORACLE_UPPER_BOUND_FOR_TARGET_JAMMERS' if any(item['preliminary_order_gate'] or item['preliminary_spatial_gate'] for item in gate_by_jammer.values()) else 'LIMIT_STAGE3_TO_ORACLE_REJECTION_CONFIRMATION',
        'not_an_algorithm_qualification': True,
    }
    (output / 'separability_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
