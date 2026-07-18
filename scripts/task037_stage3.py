#!/usr/bin/env python3
"""Task 037 Stage 3: Oracle-only FrFT suppression upper bound."""

import argparse
import csv
import json
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anti_jamming.frft_filter import myfrft
from configs.phase1_radar import get_phase1_radar_params
from scripts.task036_fix_fixture import SAFE_TARGET_CENTERS, compose, generate_bank
from scripts.task037_stage2 import best_orders, transform_stack
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation


FORMAL_JAMMERS = ('SMSP', 'FMNoiseSaopin')
JSRS = (0.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(10100, 10120))
WINDOW_LENGTH = 1000
FIXED_ORDER = 1.0
EPS = 1e-30
ORDER_STRATEGIES = ('true_target_optimum', 'true_jammer_optimum', 'received_only_optimum', 'fixed_theoretical_target_order')
MASKS = ('oracle_target_protection', 'oracle_jammer_rejection', 'oracle_ratio', 'oracle_soft_wiener')


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


def stats(values):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {'n': 0, 'mean': float('nan'), 'std': float('nan'), 'ci95_margin': float('nan'), 'ci95_lower': float('nan')}
    mean = float(np.mean(finite))
    std = float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0
    margin = float(1.96 * std / np.sqrt(finite.size))
    return {'n': int(finite.size), 'mean': mean, 'std': std, 'ci95_margin': margin, 'ci95_lower': mean - margin}


def build_mask(mask_name, target_power, jammer_power):
    target_max = float(np.max(target_power))
    jammer_max = float(np.max(jammer_power))
    target_norm = target_power / (target_max + EPS)
    jammer_norm = jammer_power / (jammer_max + EPS)
    if mask_name == 'oracle_target_protection':
        # Keep the smallest true-target support carrying 90% of target
        # FrFT energy.  This is a hard, optimistic target-protection oracle,
        # deliberately stronger than an observable soft mask.
        if target_power.sum() <= EPS:
            return np.ones_like(target_power)
        order = np.argsort(target_power)[::-1]
        keep = int(np.searchsorted(np.cumsum(target_power[order]), 0.90 * target_power.sum()) + 1)
        mask = np.zeros_like(target_power, dtype=float)
        mask[order[:keep]] = 1.0
        return mask
    if mask_name == 'oracle_jammer_rejection':
        return 1.0 - 0.95 * np.sqrt(jammer_norm)
    if mask_name == 'oracle_ratio':
        return target_power / (target_power + 2.0 * jammer_power + EPS)
    if mask_name == 'oracle_soft_wiener':
        return target_power / (target_power + jammer_power + EPS)
    raise ValueError(f'unknown oracle mask {mask_name}')


def apply_oracle(received_local, target_local, jammer_local, order, mask_name):
    target_domain = myfrft(target_local, order)
    jammer_domain = myfrft(jammer_local, order)
    received_domain = myfrft(received_local, order)
    mask = build_mask(mask_name, np.abs(target_domain) ** 2, np.abs(jammer_domain) ** 2)
    filtered_local = myfrft(received_domain * mask, -order)
    target_only_local = myfrft(target_domain * mask, -order)
    return filtered_local, target_only_local, mask


def case_id(jammer, jsr, seed, center):
    return f'{jammer}|jsr={jsr:g}|seed={seed}|center={center}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    mask_definitions = {
        'oracle_target_protection': {'formula': 'binary support of smallest bins carrying 90% cumulative true-target FrFT energy', 'information': 'true target FrFT power', 'label': 'ORACLE_DIAGNOSTIC_ONLY'},
        'oracle_jammer_rejection': {'formula': '1 - 0.95*sqrt(Pj/max(Pj))', 'information': 'true jammer FrFT power', 'label': 'ORACLE_DIAGNOSTIC_ONLY'},
        'oracle_ratio': {'formula': 'Pt/(Pt + 2*Pj + eps)', 'information': 'true target and jammer FrFT power', 'label': 'ORACLE_DIAGNOSTIC_ONLY'},
        'oracle_soft_wiener': {'formula': 'Pt/(Pt + Pj + eps)', 'information': 'true target and jammer FrFT power', 'label': 'ORACLE_DIAGNOSTIC_ONLY'},
    }
    (output / 'oracle_mask_definitions.json').write_text(json.dumps({
        'status': 'FROZEN_BEFORE_TRIALS',
        'oracle_labels': ['ORACLE_DIAGNOSTIC_ONLY', 'NOT_FAIR', 'NOT_RL_ELIGIBLE'],
        'order_strategies': {
            'true_target_optimum': 'argmax target peak concentration on coarse diagnostic grid',
            'true_jammer_optimum': 'argmax jammer peak concentration on coarse diagnostic grid',
            'received_only_optimum': 'argmax received peak concentration on coarse diagnostic grid',
            'fixed_theoretical_target_order': 'fixed order 1.0; finite-grid Fourier reference, not a continuous LFM theorem',
        },
        'masks': mask_definitions,
    }, ensure_ascii=False, indent=2) + '\n')

    trial_rows = []
    damage_rows = []
    for jammer in FORMAL_JAMMERS:
        for jsr in JSRS:
            for seed in SEEDS:
                bank = generate_bank(jammer, jsr, seed)
                for center in SAFE_TARGET_CENTERS:
                    composed = compose(bank, center)
                    start = int(center) - WINDOW_LENGTH // 2
                    stop = start + WINDOW_LENGTH
                    target = np.asarray(composed['target'][start:stop], dtype=complex)
                    jammer_component = np.asarray(composed['jammer_component'][start:stop], dtype=complex)
                    received = np.asarray(composed['received'][start:stop], dtype=complex)
                    target_stack = transform_stack(target)
                    jammer_stack = transform_stack(jammer_component)
                    received_stack = transform_stack(received)
                    target_order = best_orders(target_stack)['peak']
                    jammer_order = best_orders(jammer_stack)['peak']
                    received_order = best_orders(received_stack)['peak']
                    selected_orders = {
                        'true_target_optimum': target_order,
                        'true_jammer_optimum': jammer_order,
                        'received_only_optimum': received_order,
                        'fixed_theoretical_target_order': FIXED_ORDER,
                    }
                    config = deepcopy(bank.config)
                    config['target_start_idx'] = int(center - bank.template.size // 2)
                    config['target_idx'] = int(center)
                    full_received = np.asarray(composed['received'], dtype=complex)
                    identity = evaluate_algorithm_output(bank.template, full_received, full_received, config)
                    for strategy in ORDER_STRATEGIES:
                        order = selected_orders[strategy]
                        for mask_name in MASKS:
                            filtered_local, target_only_local, mask = apply_oracle(
                                received, target, jammer_component, order, mask_name
                            )
                            processed = full_received.copy()
                            processed[start:stop] = filtered_local
                            target_only_full = np.zeros_like(full_received)
                            target_only_full[start:stop] = target_only_local
                            metrics = evaluate_algorithm_output(bank.template, full_received, processed, config)
                            damage = evaluate_target_preservation(bank.template, target_only_full, config)
                            row = {
                                'case_id': case_id(jammer, jsr, seed, center),
                                'jammer': jammer,
                                'jsr_db': float(jsr),
                                'seed': int(seed),
                                'target_position': int(center),
                                'strategy': strategy,
                                'mask': mask_name,
                                'order': float(order),
                                'target_optimum_order': float(target_order),
                                'jammer_optimum_order': float(jammer_order),
                                'received_optimum_order': float(received_order),
                                'oracle_label': 'ORACLE_DIAGNOSTIC_ONLY;NOT_FAIR;NOT_RL_ELIGIBLE',
                                'sinr_before_db': metrics['sinr_before_db'],
                                'sinr_after_db': metrics['sinr_after_db'],
                                'delta_sinr_db': metrics['delta_sinr_db'],
                                'detected_before': bool(metrics['detected_before']),
                                'detected_after': bool(metrics['detected_after']),
                                'identity_pd': bool(identity['detected_before']),
                                'target_only_response_change_db': damage['target_only_response_change_db'],
                                'target_preservation_status': damage['target_preservation_status'],
                                'mask_min': float(np.min(mask)),
                                'mask_max': float(np.max(mask)),
                                'mask_mean': float(np.mean(mask)),
                            }
                            trial_rows.append(row)
                            damage_rows.append({key: row[key] for key in ('case_id', 'jammer', 'jsr_db', 'seed', 'target_position', 'strategy', 'mask', 'order', 'target_only_response_change_db', 'target_preservation_status', 'mask_min', 'mask_max', 'mask_mean')})
                    if (len(trial_rows) // (len(MASKS) * len(ORDER_STRATEGIES))) % 100 == 0:
                        print(f'completed_cases={len(trial_rows) // (len(MASKS) * len(ORDER_STRATEGIES))}/800', flush=True)

    write_csv(output / 'per_trial_results.csv', trial_rows)
    write_csv(output / 'target_damage.csv', damage_rows)

    groups = defaultdict(list)
    for row in trial_rows:
        groups[(row['jammer'], row['jsr_db'], row['strategy'], row['mask'])].append(row)
    aggregate = []
    for key, rows in sorted(groups.items()):
        jammer, jsr, strategy, mask = key
        delta = stats([row['delta_sinr_db'] for row in rows])
        target_change = stats([row['target_only_response_change_db'] for row in rows])
        position_means = []
        for center in SAFE_TARGET_CENTERS:
            values = [row['delta_sinr_db'] for row in rows if row['target_position'] == center]
            position_means.append(float(np.mean(values)) if values else float('nan'))
        finite_positions = [value for value in position_means if np.isfinite(value)]
        position_spread = float(max(finite_positions) - min(finite_positions)) if finite_positions else float('inf')
        pd_before = float(np.mean([row['detected_before'] for row in rows]))
        pd_after = float(np.mean([row['detected_after'] for row in rows]))
        erased_count = sum(row['target_preservation_status'] == 'TARGET_ERASED' for row in rows)
        checks = {
            'delta_mean_gt_1db': bool(delta['mean'] > 1.0),
            'delta_ci_lower_nonnegative': bool(delta['ci95_lower'] >= 0.0),
            'pd_not_below_identity': bool(pd_after >= pd_before),
            'target_only_gt_minus_1db': bool(target_change['mean'] > -1.0),
            'no_target_erased': erased_count == 0,
            'position_spread_lt_5db': bool(position_spread < 5.0),
        }
        aggregate.append({
            'jammer': jammer,
            'jsr_db': jsr,
            'strategy': strategy,
            'mask': mask,
            'oracle_label': 'ORACLE_DIAGNOSTIC_ONLY;NOT_FAIR;NOT_RL_ELIGIBLE',
            'trials': len(rows),
            'delta_sinr_mean_db': delta['mean'],
            'delta_sinr_std_db': delta['std'],
            'delta_sinr_ci95_margin_db': delta['ci95_margin'],
            'delta_sinr_ci95_lower_db': delta['ci95_lower'],
            'pd_identity': pd_before,
            'pd_after': pd_after,
            'target_only_change_mean_db': target_change['mean'],
            'target_only_change_std_db': target_change['std'],
            'target_erased_count': erased_count,
            'position_spread_db': position_spread,
            **{f'gate_{name}': value for name, value in checks.items()},
            'qualifies_oracle_upper_bound': all(checks.values()),
        })
    write_csv(output / 'aggregate_results.csv', aggregate)

    qualified = [row for row in aggregate if row['qualifies_oracle_upper_bound']]
    qualified_jsrs = defaultdict(set)
    for row in qualified:
        qualified_jsrs[row['jammer']].add(float(row['jsr_db']))
    target_jammer_decisions = {}
    for jammer in FORMAL_JAMMERS:
        candidates = [row for row in qualified if row['jammer'] == jammer and row['jsr_db'] in (10.0, 20.0, 30.0)]
        target_jammer_decisions[jammer] = {
            'qualified_rows': len(candidates),
            'qualified_jsrs': sorted({float(row['jsr_db']) for row in candidates}),
            'two_jsr_gate': len({float(row['jsr_db']) for row in candidates}) >= 2,
            'status': 'ORACLE_UPPER_BOUND_PASS' if len({float(row['jsr_db']) for row in candidates}) >= 2 else 'ORACLE_UPPER_BOUND_FAIL',
        }
    upper_bound_pass = any(item['status'] == 'ORACLE_UPPER_BOUND_PASS' for item in target_jammer_decisions.values())
    summary = {
        'task': '037',
        'stage': 'stage3',
        'status': 'COMPLETED',
        'oracle_upper_bound': 'PASSED' if upper_bound_pass else 'FAILED',
        'formal_jammers': list(FORMAL_JAMMERS),
        'seeds': [SEEDS[0], SEEDS[-1], len(SEEDS)],
        'jsrs_db': list(JSRS),
        'target_centers': list(SAFE_TARGET_CENTERS),
        'strategies': list(ORDER_STRATEGIES),
        'masks': list(MASKS),
        'trial_rows': len(trial_rows),
        'aggregate_rows': len(aggregate),
        'qualified_rows': len(qualified),
        'target_jammer_decisions': target_jammer_decisions,
        'next_stage': 'stage4_observable_prototype' if upper_bound_pass else 'stage4_and_stage5_skipped_by_decision_gate',
        'candidate_matrix_eligible': False,
        'rl_eligible': False,
        'oracle_only': True,
    }
    (output / 'oracle_upper_bound_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
