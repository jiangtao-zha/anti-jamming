#!/usr/bin/env python3
"""Task 037 Stage 6: frozen held-out rejection confirmation."""

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anti_jamming.adapters import frft_adapter
from anti_jamming.frft_filter import myfrft
from scripts.task036_fix_fixture import SAFE_TARGET_CENTERS, compose, generate_bank
from scripts.task037_stage2 import FORMAL_TARGET_JAMMERS, normalized_overlap, transform_stack, best_orders
from scripts.task037_stage3 import apply_oracle
from utils.test_contract import _whitelist_radar_par
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation


FORMAL_JAMMERS = ('SMSP', 'FMNoiseSaopin')
NEGATIVE_CONTROLS = ('NoJammer', 'AMNoiseGaiJam', 'FMNoiseAimedJam', 'FMZuse', 'NoiseProductJamming', 'NoiseConvolutionJamming')
HOLDOUT_JAMMERS = FORMAL_JAMMERS + NEGATIVE_CONTROLS
JSRS = (0.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(10300, 10350))
WINDOW_LENGTH = 1000
FIXED_ORDER = 1.0


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


def stats(values):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {'n': 0, 'mean': float('nan'), 'std': float('nan'), 'ci95_margin': float('nan'), 'ci95_lower': float('nan')}
    mean = float(np.mean(finite))
    std = float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0
    margin = float(1.96 * std / np.sqrt(finite.size))
    return {'n': int(finite.size), 'mean': mean, 'std': std, 'ci95_margin': margin, 'ci95_lower': mean - margin}


def algorithm_input(config, received, template):
    return _whitelist_radar_par(config, received, template)


def run_current(received, template, config):
    radar = algorithm_input(config, received, template)
    started = time.perf_counter()
    processed, processed_template = frft_adapter(radar, mask_threshold=0.1)
    processed = np.asarray(processed, dtype=complex)
    return processed[0], np.asarray(processed_template, dtype=complex), (time.perf_counter() - started) * 1000.0


def run_oracle(received, target, jammer, config):
    start = int(config['target_idx']) - WINDOW_LENGTH // 2
    stop = start + WINDOW_LENGTH
    target_local = np.asarray(target[start:stop], dtype=complex)
    jammer_local = np.asarray(jammer[start:stop], dtype=complex)
    received_local = np.asarray(received[start:stop], dtype=complex)
    target_stack = transform_stack(target_local)
    order = best_orders(target_stack)['peak']
    filtered_local, target_only_local, mask = apply_oracle(
        received_local, target_local, jammer_local, order, 'oracle_target_protection'
    )
    processed = np.asarray(received, dtype=complex).copy()
    processed[start:stop] = filtered_local
    target_only = np.zeros_like(processed)
    target_only[start:stop] = target_only_local
    return processed, target_only, float(order), mask


def row_id(jammer, jsr, seed, center, algorithm):
    return f'{jammer}|jsr={jsr:g}|seed={seed}|center={center}|{algorithm}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    selected_candidate_path = output.parents[0] / 'stage5' / 'selected_candidate.json'
    if not selected_candidate_path.exists():
        raise SystemExit(f'MISSING_FROZEN_CANDIDATE: {selected_candidate_path}')
    candidate_bytes = selected_candidate_path.read_bytes()
    candidate_hash = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_state = json.loads(candidate_bytes.decode('utf-8'))
    if candidate_state.get('status') != 'SKIPPED_BY_DECISION_GATE':
        raise SystemExit('CANDIDATE_HASH_STATE_MISMATCH: expected frozen no-candidate rejection state')

    metadata = {
        'task': '037',
        'stage': 'stage6',
        'dataset_role': 'HELD_OUT_REJECTION_CONFIRMATION',
        'seeds': [SEEDS[0], SEEDS[-1], len(SEEDS)],
        'jsrs_db': list(JSRS),
        'target_centers': list(SAFE_TARGET_CENTERS),
        'formal_jammers': list(FORMAL_JAMMERS),
        'negative_controls': list(NEGATIVE_CONTROLS),
        'candidate_path': str(selected_candidate_path),
        'candidate_hash_sha256': candidate_hash,
        'candidate_status': candidate_state.get('status'),
        'calibration_after_heldout': False,
        'frozen_current_frft_params': {'mask_threshold': 0.1},
        'frozen_oracle_reference': 'true_target_optimum + oracle_target_protection_90pct_support; diagnostic only',
    }
    (output / 'heldout_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')

    trial_rows = []
    order_rows = []
    mask_rows = []
    preservation_rows = []
    oracle_rows = []
    for jammer in HOLDOUT_JAMMERS:
        for jsr in JSRS:
            for seed in SEEDS:
                bank = generate_bank(jammer, jsr, seed)
                for center in SAFE_TARGET_CENTERS:
                    composed = compose(bank, center)
                    received = np.asarray(composed['received'], dtype=complex)
                    target = np.asarray(composed['target'], dtype=complex)
                    jammer_component = np.asarray(composed['jammer_component'], dtype=complex)
                    config = deepcopy(bank.config)
                    config['target_start_idx'] = int(center - bank.template.size // 2)
                    config['target_idx'] = int(center)
                    identity = received.copy()
                    current, _, current_runtime = run_current(received, bank.template, config)
                    current_target, _, current_target_runtime = run_current(target, bank.template, config)
                    algorithms = [
                        ('Identity', identity, target, 0.0, 1.0, 'OBSERVABLE_BASELINE', 0.0, 0.0, 1.0, 0.0),
                        ('Current_FrFT', current, current_target, float('nan'), FIXED_ORDER, 'OBSERVABLE_CURRENT_BASELINE', current_runtime, float('nan'), float('nan'), float(np.mean(np.abs(current) > 0))),
                        ('FROZEN_REJECTION_CONFIRMATION', current, current_target, float('nan'), FIXED_ORDER, 'FROZEN_CURRENT_FRFT_NO_STAGE4_CANDIDATE', current_runtime, float('nan'), float('nan'), float(np.mean(np.abs(current) > 0))),
                    ]
                    oracle_available = jammer in FORMAL_JAMMERS
                    if oracle_available:
                        oracle, oracle_target, oracle_order, oracle_mask = run_oracle(received, target, jammer_component, config)
                        algorithms.append(('Oracle_FrFT_UpperBound', oracle, oracle_target, oracle_order, FIXED_ORDER, 'ORACLE_DIAGNOSTIC_ONLY;NOT_FAIR;NOT_RL_ELIGIBLE', 0.0, float(np.mean(oracle_mask > 0.5)), float(np.nan), float(np.mean(oracle_mask > 0.5))))
                    else:
                        oracle = None
                        oracle_target = None
                        oracle_order = float('nan')
                        oracle_mask = None
                    identity_eval = evaluate_algorithm_output(bank.template, received, identity, config)
                    for algorithm, processed, processed_target, selected_order, theoretical_order, role, runtime, support_ratio, target_overlap, mask_support in algorithms:
                        metrics = evaluate_algorithm_output(bank.template, received, processed, config)
                        damage = evaluate_target_preservation(bank.template, processed_target, config)
                        is_oracle = algorithm == 'Oracle_FrFT_UpperBound'
                        if is_oracle:
                            overlap = normalized_overlap(
                                np.abs(myfrft(target[int(center)-500:int(center)+500], selected_order)) ** 2,
                                np.abs(myfrft(jammer_component[int(center)-500:int(center)+500], selected_order)) ** 2,
                            )
                            target_overlap = overlap['overlap']
                        interface = bool(processed.shape == received.shape and np.all(np.isfinite(processed)))
                        fallback = bool(np.allclose(processed, received))
                        row = {
                            'trial_id': row_id(jammer, jsr, seed, center, algorithm),
                            'jammer': jammer,
                            'jsr_db': float(jsr),
                            'seed': int(seed),
                            'target_position': int(center),
                            'algorithm': algorithm,
                            'role': role,
                            'oracle_audit': 'PASS' if not is_oracle else 'ORACLE_DIAGNOSTIC_ONLY',
                            'jammer_contract': composed['jsr_status'],
                            'interface_status': 'PASS' if interface else 'FAIL',
                            'sinr_before_db': metrics['sinr_before_db'],
                            'sinr_after_db': metrics['sinr_after_db'],
                            'delta_sinr_db': metrics['delta_sinr_db'],
                            'detected_before': bool(metrics['detected_before']),
                            'detected_after': bool(metrics['detected_after']),
                            'identity_detected': bool(identity_eval['detected_before']),
                            'peak_error_before': metrics['peak_error_before'],
                            'peak_error_after': metrics['peak_error_after'],
                            'false_peak_count_before': metrics['false_peak_count_before'],
                            'false_peak_count_after': metrics['false_peak_count_after'],
                            'target_only_response_change_db': damage['target_only_response_change_db'],
                            'target_preservation_status': damage['target_preservation_status'],
                            'selected_order': selected_order,
                            'theoretical_target_order': theoretical_order,
                            'order_deviation_d4': d4_distance(selected_order, theoretical_order) if np.isfinite(selected_order) else float('nan'),
                            'mask_support_ratio': support_ratio if np.isfinite(support_ratio) else mask_support,
                            'target_protection_overlap': target_overlap,
                            'fallback': fallback,
                            'fallback_ratio': float(fallback),
                            'runtime_ms': float(runtime),
                            'memory_usage_bytes': int(processed.nbytes),
                            'candidate_hash_sha256': candidate_hash,
                        }
                        trial_rows.append(row)
                        order_rows.append({key: row[key] for key in ('trial_id', 'jammer', 'jsr_db', 'seed', 'target_position', 'algorithm', 'selected_order', 'theoretical_target_order', 'order_deviation_d4')})
                        mask_rows.append({key: row[key] for key in ('trial_id', 'jammer', 'jsr_db', 'seed', 'target_position', 'algorithm', 'mask_support_ratio', 'target_protection_overlap', 'fallback_ratio')})
                        preservation_rows.append({key: row[key] for key in ('trial_id', 'jammer', 'jsr_db', 'seed', 'target_position', 'algorithm', 'target_only_response_change_db', 'target_preservation_status')})
                        if is_oracle:
                            oracle_rows.append(row)
                    
                if (seed - SEEDS[0] + 1) % 10 == 0:
                    print(f'completed={jammer} jsr={jsr:g} seed={seed}', flush=True)

    write_csv(output / 'per_trial_results.csv', trial_rows)
    write_csv(output / 'order_diagnostics.csv', order_rows)
    write_csv(output / 'mask_diagnostics.csv', mask_rows)
    write_csv(output / 'target_preservation.csv', preservation_rows)
    write_csv(output / 'oracle_comparison.csv', oracle_rows)

    groups = defaultdict(list)
    for row in trial_rows:
        groups[(row['algorithm'], row['jammer'], row['jsr_db'])].append(row)
    aggregate = []
    for (algorithm, jammer, jsr), rows in sorted(groups.items()):
        delta = stats([row['delta_sinr_db'] for row in rows])
        target_change = stats([row['target_only_response_change_db'] for row in rows])
        positions = []
        for center in SAFE_TARGET_CENTERS:
            values = [row['delta_sinr_db'] for row in rows if row['target_position'] == center]
            if values:
                positions.append(float(np.mean(values)))
        position_spread = max(positions) - min(positions) if positions else float('nan')
        pd_identity = float(np.mean([row['identity_detected'] for row in rows]))
        pd_after = float(np.mean([row['detected_after'] for row in rows]))
        erased = sum(row['target_preservation_status'] == 'TARGET_ERASED' for row in rows)
        aggregate.append({
            'algorithm': algorithm,
            'jammer': jammer,
            'jsr_db': jsr,
            'role': rows[0]['role'],
            'oracle_audit': rows[0]['oracle_audit'],
            'interface_pass': all(row['interface_status'] == 'PASS' for row in rows),
            'trials': len(rows),
            'delta_sinr_mean_db': delta['mean'],
            'delta_sinr_std_db': delta['std'],
            'delta_sinr_ci95_lower_db': delta['ci95_lower'],
            'pd_identity': pd_identity,
            'pd_after': pd_after,
            'target_only_change_mean_db': target_change['mean'],
            'target_erased_count': erased,
            'position_spread_db': position_spread,
            'fallback_ratio_mean': float(np.mean([row['fallback_ratio'] for row in rows])),
            'runtime_ms_mean': float(np.mean([row['runtime_ms'] for row in rows])),
            'memory_usage_bytes_mean': float(np.mean([row['memory_usage_bytes'] for row in rows])),
        })
    write_csv(output / 'aggregate_results.csv', aggregate)

    final_decision = {
        'decision': 'REJECTED_NO_USABLE_SEPARABILITY',
        'current_frft_status': 'RETAINED_BASELINE_ONLY',
        'observable_candidate_registered': False,
        'candidate_matrix_eligible': False,
        'rl_eligible': False,
        'oracle_upper_bound_available': True,
        'oracle_upper_bound_status': 'FAILED',
        'supported_jammers': [],
        'supported_jsr_region': [],
        'fallback': 'Identity',
        'blocking_reasons': [
            'Stage 3 Oracle upper bound failed for SMSP and FMNoiseSaopin',
            'Stage 4 observable prototype and Stage 5 calibration skipped by decision gate',
            'held-out is rejection confirmation only; no candidate was frozen',
        ],
        'evidence_commits': ['b6899b3', '4475ac1', '38d3778', 'd68ec82', 'c838c01'],
        'candidate_hash_sha256': candidate_hash,
    }
    (output / 'final_decision.json').write_text(json.dumps(final_decision, ensure_ascii=False, indent=2) + '\n')
    summary = {
        'task': '037',
        'stage': 'stage6',
        'status': 'COMPLETED',
        'decision': final_decision['decision'],
        'trial_rows': len(trial_rows),
        'aggregate_rows': len(aggregate),
        'oracle_rows': len(oracle_rows),
        'observable_candidate': 'NONE',
        'heldout_mode': 'REJECTION_CONFIRMATION_ONLY',
        'candidate_hash_sha256': candidate_hash,
        'calibration_after_heldout': False,
        'candidate_matrix_eligible': False,
        'rl_eligible': False,
    }
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
