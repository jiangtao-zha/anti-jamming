"""Task 036-fix Stage E: independent held-out rejection confirmation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from anti_jamming.adapt_filter_fair import apply_adapt_filter_fair  # noqa: E402
from scripts.task036_fix_fixture import compose, generate_bank  # noqa: E402
from scripts.task036_fix_dispatch import dispatch_info, fit_candidate, validate_dispatch_identity  # noqa: E402
from scripts.task036_stage4_prototype import _run_oracle  # noqa: E402
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation  # noqa: E402


TARGET_JAMMERS = ('NoiseProductJamming', 'NoiseConvolutionJamming')
JAMMERS = TARGET_JAMMERS + ('NoJammer', 'AMNoiseGaiJam', 'FMNoiseAimedJam', 'FMNoiseSaopin', 'SMSP', 'FMZuse')
JSRS = (0.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(9200, 9250))
TARGET_CENTERS = (1000, 1500, 2500, 3500, 4000)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def public_config(config: dict) -> dict:
    return {key: config[key] for key in ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N')}


def load_frozen_candidate() -> tuple[dict, str, dict]:
    path = Path('results/phase1/task036_fix2/stageB/selected_candidate.json')
    payload = json.loads(path.read_text())
    candidate = payload.get('selected_candidate') or payload.get('rejection_confirmation_candidate')
    if not candidate:
        raise RuntimeError('Stage B did not freeze a candidate representative')
    dispatch_info(candidate)
    return candidate, hashlib.sha256(path.read_bytes()).hexdigest(), payload


def run_candidate(candidate: dict, observed: np.ndarray, template: np.ndarray, config: dict) -> tuple[dict, np.ndarray, float, dict]:
    dispatch = dispatch_info(candidate)
    started = time.perf_counter()
    model = fit_candidate(candidate, observed, template, public_config(config))
    processed = apply_adapt_filter_fair(observed, model)
    runtime_ms = (time.perf_counter() - started) * 1000.0
    if processed.shape != (1, observed.size) or not np.all(np.isfinite(processed)):
        raise RuntimeError(f'interface failure for candidate {candidate["candidate_id"]}')
    validate_dispatch_identity(dispatch['candidate_design'], dispatch['fit_function_name'])
    return model, processed, runtime_ms, dispatch


def metric_row(role, algorithm, received, target, processed, eval_config, runtime_ms, memory_bytes, metadata):
    metrics = evaluate_algorithm_output(
        target, received, processed, eval_config,
        runtime_ms=runtime_ms, memory_usage_bytes=memory_bytes,
    )
    return {
        **metadata,
        'algorithm': algorithm, 'role': role,
        'interface_status': 'PASS' if np.all(np.isfinite(processed)) and processed.shape == (received.size,) else 'FAIL',
        'delta_sinr_db': metrics['delta_sinr_db'],
        'detected_before': metrics['detected_before'], 'detected_after': metrics['detected_after'],
        'pd_after': metrics['detected_after'],
        'peak_error_before': metrics['peak_error_before'], 'peak_error_after': metrics['peak_error_after'],
        'false_peak_count_before': metrics['false_peak_count_before'], 'false_peak_count_after': metrics['false_peak_count_after'],
        'target_window_peak_change_db': metrics['target_window_peak_change_db'],
        'runtime_ms': runtime_ms, 'memory_usage_bytes': memory_bytes,
    }


def aggregate(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups = {}
    for row in rows:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    output = []
    for key, group in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        deltas = np.asarray([float(r['delta_sinr_db']) for r in group if r['delta_sinr_db'] is not None and np.isfinite(float(r['delta_sinr_db']))])
        target_changes = np.asarray([float(r['target_only_response_change_db']) for r in group if r.get('target_only_response_change_db') is not None and np.isfinite(float(r['target_only_response_change_db']))])
        by_position = {}
        for row in group:
            if row.get('target_position') is None or row.get('delta_sinr_db') is None:
                continue
            value = float(row['delta_sinr_db'])
            if np.isfinite(value):
                by_position.setdefault(row['target_position'], []).append(value)
        position_means = [float(np.mean(values)) for values in by_position.values() if values]
        position_spread_db = (max(position_means) - min(position_means)) if len(position_means) > 1 else 0.0
        out = dict(zip(keys, key))
        out.update({
            'trials': len(group),
            'interface_pass': sum(r['interface_status'] == 'PASS' for r in group),
            'interface_failures': sum(r['interface_status'] != 'PASS' for r in group),
            'oracle_input_failures': sum(r.get('oracle_input_status') == 'FAIL' for r in group),
            'target_erased_count': sum(r.get('target_preservation_status') == 'TARGET_ERASED' for r in group),
            'delta_sinr_mean_db': float(np.mean(deltas)) if deltas.size else float('nan'),
            'delta_sinr_std_db': float(np.std(deltas, ddof=1)) if deltas.size > 1 else 0.0,
            'delta_sinr_ci95_db': float(1.96 * np.std(deltas, ddof=1) / np.sqrt(deltas.size)) if deltas.size > 1 else 0.0,
            'pd_mean': float(np.mean([r['pd_after'] for r in group])) if group else float('nan'),
            'target_only_change_mean_db': float(np.mean(target_changes)) if target_changes.size else float('nan'),
            'fallback_ratio': float(np.mean([r.get('fallback') == 'Identity' for r in group])),
            'estimation_error_mean': float(np.mean([r['estimation_error_for_evaluation_only'] for r in group if r.get('estimation_error_for_evaluation_only') is not None])) if any(r.get('estimation_error_for_evaluation_only') is not None for r in group) else float('nan'),
            'confidence_mean': float(np.mean([r.get('estimator_confidence', 0.0) for r in group])),
            'position_spread_db': position_spread_db,
        })
        output.append(out)
    return output


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate, candidate_hash, freeze_payload = load_frozen_candidate()
    candidate_role = 'FROZEN_CANDIDATE' if freeze_payload.get('selected_candidate') is not None else 'FROZEN_REJECTION_CONFIRMATION'
    dispatch = dispatch_info(candidate)
    rows = []
    oracle_target_cache = {}
    fair_target_cache = {}
    for jammer in JAMMERS:
        for jsr_db in JSRS:
            for seed in SEEDS:
                bank = generate_bank(jammer, jsr_db, seed)
                for center in TARGET_CENTERS:
                    fixture = compose(bank, center)
                    target = fixture['target']
                    received = fixture['received']
                    template = fixture['template']
                    eval_config = dict(bank.config)
                    eval_config['target_start_idx'] = center - template.size // 2
                    eval_config['target_idx'] = center
                    base_metadata = {
                        'jammer': jammer, 'jsr_db': jsr_db, 'seed': seed, 'target_position': center,
                        'true_target_idx_for_evaluation_only': center,
                        'candidate_id': candidate['candidate_id'] if jammer else '',
                    }
                    identity_processed = received.copy()
                    identity = metric_row('IDENTITY_BASELINE', 'Identity', received, target, identity_processed, eval_config, 0.0, 0, {
                        **base_metadata, 'candidate_id': '', 'estimated_target_idx': None,
                        'estimation_error_for_evaluation_only': None, 'estimator_confidence': 1.0,
                        'fallback': 'Identity', 'fit_status': 'IDENTITY', 'oracle_input_status': 'PASS',
                        'candidate_design': '', 'fit_function_name': '', 'dispatch_status': 'NOT_APPLICABLE',
                        'candidate_params_json': '',
                        'forbidden_keys_present': '', 'target_preservation_status': 'TARGET_PRESERVED',
                        'target_only_response_change_db': 0.0,
                    })
                    rows.append(identity)
                    oracle = _run_oracle(received, template, center)
                    oracle_processed = oracle['processed'][0] if oracle.get('processed') is not None and oracle['processed'].ndim == 2 else oracle.get('processed')
                    if center not in oracle_target_cache:
                        oracle_target_cache[center] = _run_oracle(target, template, center)
                    oracle_target = oracle_target_cache[center]
                    oracle_target_processed = oracle_target['processed'][0] if oracle_target.get('processed') is not None and oracle_target['processed'].ndim == 2 else oracle_target.get('processed')
                    oracle_preservation = evaluate_target_preservation(target, oracle_target_processed, eval_config)
                    oracle_row = metric_row('ORACLE_UPPER_BOUND', 'adapt_filter_oracle', received, target, oracle_processed, eval_config, oracle.get('runtime_ms', 0.0), oracle.get('memory_usage_bytes', 0), {
                        **base_metadata, 'candidate_id': '', 'estimated_target_idx': center,
                        'estimation_error_for_evaluation_only': 0, 'estimator_confidence': 1.0,
                        'fallback': None, 'fit_status': 'LEGACY_ORACLE_TRUE_TARGET_IDX',
                        'oracle_input_status': 'ORACLE_TRUE_TARGET_IDX', 'forbidden_keys_present': 'target_idx',
                        'candidate_design': '', 'fit_function_name': '', 'dispatch_status': 'NOT_APPLICABLE',
                        'candidate_params_json': '',
                        'target_preservation_status': oracle_preservation['target_preservation_status'],
                        'target_only_response_change_db': oracle_preservation['target_only_response_change_db'],
                    })
                    rows.append(oracle_row)
                    cache_key = (candidate['candidate_id'], center)
                    if cache_key not in fair_target_cache:
                        target_model, fair_target_processed, _, _ = run_candidate(candidate, target, template, bank.config)
                        fair_target_cache[cache_key] = (target_model, fair_target_processed)
                    fair_model, fair_processed, runtime_ms, fair_dispatch = run_candidate(candidate, received, template, bank.config)
                    fair_target_model, fair_target_processed = fair_target_cache[cache_key]
                    fair_target_1d = fair_target_processed[0] if fair_target_processed.ndim == 2 else fair_target_processed
                    fair_preservation = evaluate_target_preservation(target, fair_target_1d, eval_config)
                    fair_processed_1d = fair_processed[0] if fair_processed.ndim == 2 else fair_processed
                    fair_row = metric_row(candidate_role, 'adapt_filter_fair_frozen', received, target, fair_processed_1d, eval_config, runtime_ms, int(fair_processed.nbytes), {
                        **base_metadata, 'estimated_target_idx': fair_model.get('estimated_target_idx'),
                        'estimation_error_for_evaluation_only': None if fair_model.get('estimated_target_idx') is None else abs(int(fair_model['estimated_target_idx']) - center),
                        'estimator_confidence': fair_model.get('estimator_confidence', 0.0), 'fallback': fair_model.get('fallback'),
                        'fit_status': fair_model.get('fit_status'), 'oracle_input_status': 'PASS', 'forbidden_keys_present': '',
                        'candidate_design': fair_dispatch['candidate_design'], 'fit_function_name': fair_dispatch['fit_function_name'],
                        'dispatch_status': fair_dispatch['dispatch_status'],
                        'candidate_params_json': json.dumps(fair_dispatch['candidate_params'], sort_keys=True),
                        'target_preservation_status': fair_preservation['target_preservation_status'],
                        'target_only_response_change_db': fair_preservation['target_only_response_change_db'],
                    })
                    rows.append(fair_row)
    aggregate_rows = aggregate(rows, ('jammer', 'role', 'jsr_db'))
    position_rows = aggregate(rows, ('jammer', 'role', 'jsr_db', 'target_position'))
    fair_rows = [row for row in rows if row['role'] == candidate_role]
    fallback_rows = aggregate(fair_rows, ('jammer', 'jsr_db'))
    oracle_rows = [row for row in aggregate_rows if row['role'] in ('IDENTITY_BASELINE', 'ORACLE_UPPER_BOUND', candidate_role)]
    identity_lookup = {(r['jammer'], r['jsr_db']): r for r in aggregate_rows if r['role'] == 'IDENTITY_BASELINE'}
    fair_agg = [r for r in aggregate_rows if r['role'] == candidate_role]
    by_jammer_pass = {}
    pass_rows = []
    for jammer in TARGET_JAMMERS:
        passed = 0
        for row in fair_agg:
            if row['jammer'] != jammer or float(row['jsr_db']) not in (10.0, 20.0, 30.0):
                continue
            identity = identity_lookup[(jammer, row['jsr_db'])]
            criterion = (
                float(row['delta_sinr_mean_db']) > 0.5
                and float(row['delta_sinr_mean_db']) - float(row['delta_sinr_ci95_db']) >= 0.0
                and float(row['pd_mean']) >= float(identity['pd_mean'])
                and int(row['target_erased_count']) == 0
                and float(row['position_spread_db']) < 5.0
            )
            pass_rows.append({**row, 'identity_pd_mean': identity['pd_mean'], 'jsr_condition_pass': criterion})
            passed += int(criterion)
        by_jammer_pass[jammer] = passed
    high_jsr_negative = any(float(row['jsr_db']) in (20.0, 30.0) and float(row['delta_sinr_mean_db']) < 0.0 for row in fair_agg if row['jammer'] in TARGET_JAMMERS)
    position_spread_large = any(float(row['position_spread_db']) > 5.0 for row in fair_agg if row['jammer'] in TARGET_JAMMERS and float(row['jsr_db']) in (10.0, 20.0, 30.0))
    fallback_ratio = float(np.mean([row.get('fallback') == 'Identity' for row in fair_rows]))
    if max(by_jammer_pass.values()) < 2 or high_jsr_negative or position_spread_large:
        decision = 'ORACLE_UPPER_BOUND_ONLY_CONFIRMED'
        blocking_reasons = []
        if max(by_jammer_pass.values()) < 2:
            blocking_reasons.append('no target jammer has two distinct passing JSR conditions after seed x position aggregation')
        if high_jsr_negative:
            blocking_reasons.append('frozen fair representative has negative high-JSR target-jammer Delta SINR')
        if position_spread_large:
            blocking_reasons.append('position spread exceeds 5 dB on at least one target jammer condition')
    else:
        decision = 'CONDITIONAL_RESEARCH_ONLY'
        blocking_reasons = ['fair behavior remains outside RL/candidate eligibility by Task 036-fix policy']
    write_csv(output_dir / 'per_trial_results.csv', rows)
    write_csv(output_dir / 'aggregate_by_jammer_jsr.csv', aggregate_rows)
    write_csv(output_dir / 'position_robustness.csv', position_rows)
    write_csv(output_dir / 'fallback_analysis.csv', fallback_rows)
    write_csv(output_dir / 'oracle_comparison.csv', oracle_rows + pass_rows)
    write_csv(output_dir / 'dispatch_validation.csv', [{
        **dispatch,
        'candidate_params_json': json.dumps(dispatch['candidate_params'], sort_keys=True),
        'heldout_calls': len(fair_rows),
        'dispatch_mismatch_count': 0,
        'interface_failures': sum(row['interface_status'] != 'PASS' for row in fair_rows),
        'dispatch_status': 'PASS',
    }])
    final_decision = {
        'decision': decision,
        'legacy_decision': 'ORACLE_UPPER_BOUND_ONLY',
        'fair_status': 'REJECTED_EXPERIMENTAL' if decision == 'ORACLE_UPPER_BOUND_ONLY_CONFIRMED' else 'CONDITIONAL_RESEARCH_ONLY',
        'rl_eligible': False, 'candidate_matrix_eligible': False, 'fair_registered': False,
        'rl_action_space_modified': False, 'fallback': 'Identity',
        'candidate_id': candidate['candidate_id'], 'candidate_file_sha256': candidate_hash,
        'candidate_design': dispatch['candidate_design'], 'fit_function_name': dispatch['fit_function_name'],
        'candidate_params': dispatch['candidate_params'], 'dispatch_status': 'PASS', 'dispatch_mismatch_count': 0,
        'heldout_mode': 'PERFORMANCE_CANDIDATE' if candidate_role == 'FROZEN_CANDIDATE' else 'REJECTION_CONFIRMATION_ONLY',
        'seed_range': [SEEDS[0], SEEDS[-1]], 'invalid_historical_seed_range': [9100, 9149],
        'target_positions': list(TARGET_CENTERS), 'passing_jsr_count_by_jammer': by_jammer_pass,
        'overall_fallback_ratio': fallback_ratio, 'blocking_reasons': blocking_reasons,
    }
    (output_dir / 'final_decision.json').write_text(json.dumps(final_decision, indent=2, ensure_ascii=False, default=str))
    summary = {
        'task': '036-fix2', 'stage': 'stageC', 'status': 'COMPLETED',
        'mode': 'PERFORMANCE_CANDIDATE' if candidate_role == 'FROZEN_CANDIDATE' else 'REJECTION_CONFIRMATION_ONLY', 'decision': decision,
        'per_trial_rows': len(rows), 'aggregate_rows': len(aggregate_rows),
        'position_rows': len(position_rows), 'seed_range': [SEEDS[0], SEEDS[-1]],
        'candidate_id': candidate['candidate_id'], 'candidate_file_sha256': candidate_hash,
        'candidate_design': dispatch['candidate_design'], 'fit_function_name': dispatch['fit_function_name'],
        'candidate_params': dispatch['candidate_params'], 'dispatch_mismatch_count': 0,
        'passing_jsr_count_by_jammer': by_jammer_pass,
        'overall_fallback_ratio': fallback_ratio,
        'interface_failures': sum(r['interface_status'] != 'PASS' for r in rows),
        'fair_target_erased_count': sum(r.get('target_preservation_status') == 'TARGET_ERASED' for r in fair_rows),
        'interface_failures': sum(r['interface_status'] != 'PASS' for r in rows),
        'heldout_after_tuning': False, 'old_invalid_dispatch_seed_range': [9100, 9149],
        'next_stage': 'stageD',
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    (output_dir / 'heldout_metadata.json').write_text(json.dumps({
        'candidate': candidate, 'candidate_file_sha256': candidate_hash,
        'candidate_design': dispatch['candidate_design'], 'fit_function_name': dispatch['fit_function_name'],
        'candidate_params': dispatch['candidate_params'],
        'seed_range': [SEEDS[0], SEEDS[-1]], 'target_positions': list(TARGET_CENTERS),
        'old_invalid_dispatch_seed_range': [9100, 9149], 'no_post_heldout_tuning': True,
        'formal_aggregation': 'jammer x JSR across seed x target_position',
    }, indent=2, ensure_ascii=False, default=str))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036_fix/stageE')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
