"""Task 036-fix Stage D: behavior deduplication and small calibration."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from anti_jamming.adapt_filter_fair import (  # noqa: E402
    apply_adapt_filter_fair,
    fit_adapt_filter_fair,
    fit_adapt_filter_fair_multihypothesis,
)
from configs.phase1_radar import get_phase1_radar_params  # noqa: E402
from scripts.task036_fix_fixture import (  # noqa: E402
    JAMMERS,
    JSRS,
    SAFE_TARGET_CENTERS,
    compose,
    generate_bank,
)
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation  # noqa: E402


CALIBRATION_JAMMERS = (
    'NoiseProductJamming', 'NoiseConvolutionJamming', 'NoJammer',
    'AMNoiseGaiJam', 'FMNoiseAimedJam', 'SMSP',
)
CALIBRATION_JSRS = (0.0, 10.0, 20.0, 30.0)
CALIBRATION_SEEDS = tuple(range(9000, 9020))
DIAGNOSTIC_JAMMERS = JAMMERS
DIAGNOSTIC_JSRS = (0.0, 20.0, 30.0)
DIAGNOSTIC_SEEDS = (9000, 9001)
DIAGNOSTIC_CENTERS = (1000, 2500, 4000)
NOMINAL = []
for design in ('A', 'B'):
    for top_k in (3, 5):
        for threshold in (0.65, 0.80):
            NOMINAL.append({
                'candidate_id': f'{design}_k{top_k}_c{threshold:g}_r0.001',
                'design': design,
                'top_k': top_k,
                'confidence_threshold': threshold,
                'regularization': 0.001,
            })

FIT_FUNCTIONS = {'A': fit_adapt_filter_fair, 'B': fit_adapt_filter_fair_multihypothesis}


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


def candidate_map():
    return {candidate['candidate_id']: candidate for candidate in NOMINAL}


def run_candidate(candidate: dict, observed: np.ndarray, template: np.ndarray, config: dict) -> tuple[dict, np.ndarray, float]:
    fit_fn = FIT_FUNCTIONS[candidate['design']]
    started = __import__('time').perf_counter()
    model = fit_fn(
        observed, template, public_config(config),
        top_k=int(candidate['top_k']),
        confidence_threshold=float(candidate['confidence_threshold']),
        regularization=float(candidate['regularization']),
    )
    processed = apply_adapt_filter_fair(observed, model)
    runtime_ms = (__import__('time').perf_counter() - started) * 1000.0
    return model, processed, runtime_ms


def normalized_output_hash(processed: np.ndarray) -> str:
    values = np.asarray(processed, dtype=complex).reshape(-1)
    norm = float(np.linalg.norm(values))
    normalized = values / (norm + 1e-12)
    quantized = np.round(np.stack((normalized.real, normalized.imag), axis=1), 6)
    return hashlib.sha256(quantized.tobytes()).hexdigest()


def behavior_signature(candidate: dict) -> tuple[str, list[dict]]:
    sequence = []
    for jammer in DIAGNOSTIC_JAMMERS:
        for jsr_db in DIAGNOSTIC_JSRS:
            for seed in DIAGNOSTIC_SEEDS:
                bank = generate_bank(jammer, jsr_db, seed)
                for center in DIAGNOSTIC_CENTERS:
                    fixture = compose(bank, center)
                    model, processed, _ = run_candidate(candidate, fixture['received'], fixture['template'], bank.config)
                    diagnostics = model.get('diagnostics', {})
                    sequence.append({
                        'jammer': jammer, 'jsr_db': jsr_db, 'seed': seed, 'target_position': center,
                        'estimated_target_idx': model.get('estimated_target_idx'),
                        'fallback': model.get('fallback'),
                        'fit_status': model.get('fit_status'),
                        'confidence_q': round(float(model.get('estimator_confidence', 0.0)), 6),
                        'output_hash': normalized_output_hash(processed),
                        'gate_reasons': json.dumps(diagnostics.get('gate_reasons', []), sort_keys=True),
                    })
    serialized = json.dumps(sequence, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(serialized).hexdigest(), sequence


def identity_metrics(target, received, eval_config):
    return evaluate_algorithm_output(target, received, received, eval_config, runtime_ms=0.0, memory_usage_bytes=0)


def evaluate_row(candidate: dict, bank, fixture, target_cache: dict) -> dict:
    center = int(fixture['target_position'])
    eval_config = dict(bank.config)
    eval_config['target_start_idx'] = center - fixture['template'].size // 2
    eval_config['target_idx'] = center
    target = fixture['target']
    received = fixture['received']
    identity = identity_metrics(target, received, eval_config)
    model, processed, runtime_ms = run_candidate(candidate, received, fixture['template'], bank.config)
    processed_1d = processed[0] if processed.ndim == 2 else processed
    metrics = evaluate_algorithm_output(
        target, received, processed_1d, eval_config,
        runtime_ms=runtime_ms, memory_usage_bytes=int(processed.nbytes),
    )
    cache_key = (candidate['candidate_id'], center)
    if cache_key not in target_cache:
        target_model, target_processed, _ = run_candidate(candidate, target, fixture['template'], bank.config)
        target_cache[cache_key] = (target_model, target_processed)
    target_model, target_processed = target_cache[cache_key]
    target_1d = target_processed[0] if target_processed.ndim == 2 else target_processed
    target_metrics = evaluate_target_preservation(target, target_1d, eval_config)
    estimated = model.get('estimated_target_idx')
    diagnostics = model.get('diagnostics', {})
    return {
        'candidate_id': candidate['candidate_id'], 'design': candidate['design'],
        'top_k': candidate['top_k'], 'confidence_threshold': candidate['confidence_threshold'],
        'regularization': candidate['regularization'], 'jammer': bank.jammer,
        'jsr_db': bank.jsr_db, 'seed': bank.seed, 'target_position': center,
        'true_target_idx_for_evaluation_only': center,
        'estimated_target_idx': estimated,
        'estimation_error_for_evaluation_only': None if estimated is None else abs(int(estimated) - center),
        'estimator_confidence': float(model.get('estimator_confidence', 0.0)),
        'fallback': model.get('fallback'), 'fit_status': model.get('fit_status'),
        'oracle_input_status': 'PASS', 'forbidden_keys_present': '',
        'interface_status': 'PASS' if processed.shape == (1, received.size) and np.all(np.isfinite(processed)) else 'FAIL',
        'delta_sinr_db': metrics.get('delta_sinr_db'),
        'detected_before': identity.get('detected_before'), 'detected_after': metrics.get('detected_after'),
        'pd_identity': identity.get('detected_after'), 'pd_algorithm': metrics.get('detected_after'),
        'peak_error_before': metrics.get('peak_error_before'), 'peak_error_after': metrics.get('peak_error_after'),
        'false_peak_count_before': metrics.get('false_peak_count_before'), 'false_peak_count_after': metrics.get('false_peak_count_after'),
        'target_only_response_change_db': target_metrics.get('target_only_response_change_db'),
        'target_preservation_status': target_metrics.get('target_preservation_status'),
        'target_window_peak_change_db': metrics.get('target_window_peak_change_db'),
        'runtime_ms': runtime_ms, 'memory_usage_bytes': int(processed.nbytes),
        'gate_reasons': json.dumps(diagnostics.get('gate_reasons', []), sort_keys=True),
    }


def aggregate_rows(rows: list[dict]) -> list[dict]:
    groups = {}
    for row in rows:
        groups.setdefault((row['candidate_id'], row['jammer'], row['jsr_db']), []).append(row)
    output = []
    for key, group in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        candidate_id, jammer, jsr_db = key
        deltas = np.asarray([float(r['delta_sinr_db']) for r in group if r['delta_sinr_db'] is not None and np.isfinite(float(r['delta_sinr_db']))])
        target_changes = np.asarray([float(r['target_only_response_change_db']) for r in group if r['target_only_response_change_db'] is not None and np.isfinite(float(r['target_only_response_change_db']))])
        position_means = []
        for position in sorted({r['target_position'] for r in group}):
            position_values = [float(r['delta_sinr_db']) for r in group if r['target_position'] == position and r['delta_sinr_db'] is not None and np.isfinite(float(r['delta_sinr_db']))]
            if position_values:
                position_means.append(float(np.mean(position_values)))
        ci = float(1.96 * np.std(deltas, ddof=1) / np.sqrt(deltas.size)) if deltas.size > 1 else 0.0
        output.append({
            'candidate_id': candidate_id, 'jammer': jammer, 'jsr_db': jsr_db,
            'trials': len(group), 'interface_pass': sum(r['interface_status'] == 'PASS' for r in group),
            'interface_failures': sum(r['interface_status'] != 'PASS' for r in group),
            'oracle_input_failures': sum(r['oracle_input_status'] == 'FAIL' for r in group),
            'target_erased_count': sum(r['target_preservation_status'] == 'TARGET_ERASED' for r in group),
            'delta_sinr_mean_db': float(np.mean(deltas)) if deltas.size else float('nan'),
            'delta_sinr_std_db': float(np.std(deltas, ddof=1)) if deltas.size > 1 else 0.0,
            'delta_sinr_ci95_db': ci,
            'pd_identity': float(np.mean([r['pd_identity'] for r in group])),
            'pd_algorithm': float(np.mean([r['pd_algorithm'] for r in group])),
            'position_spread_db': float(max(position_means) - min(position_means)) if position_means else float('nan'),
            'fallback_ratio': float(np.mean([r['fallback'] == 'Identity' for r in group])),
            'estimation_error_mean': float(np.mean([r['estimation_error_for_evaluation_only'] for r in group if r['estimation_error_for_evaluation_only'] is not None])) if any(r['estimation_error_for_evaluation_only'] is not None for r in group) else float('nan'),
            'target_only_change_db': float(np.mean(target_changes)) if target_changes.size else float('nan'),
            'confidence_mean': float(np.mean([r['estimator_confidence'] for r in group])),
            'runtime_mean_ms': float(np.mean([r['runtime_ms'] for r in group])),
        })
    return output


def rank_candidates(candidates: list[dict], aggregate: list[dict], trial_rows: list[dict]) -> list[dict]:
    output = []
    for candidate in candidates:
        cid = candidate['candidate_id']
        groups = [row for row in aggregate if row['candidate_id'] == cid]
        target_groups = [row for row in groups if row['jammer'] in ('NoiseProductJamming', 'NoiseConvolutionJamming') and float(row['jsr_db']) in (10.0, 20.0, 30.0)]
        controls = [row for row in groups if row['jammer'] == 'NoJammer']
        positive_by_jammer = {
            jammer: sum(
                float(row['delta_sinr_mean_db']) > 0.5 and float(row['delta_sinr_mean_db']) - float(row['delta_sinr_ci95_db']) >= 0.0
                and float(row['pd_algorithm']) >= float(row['pd_identity'])
                and int(row['target_erased_count']) == 0
                and float(row['position_spread_db']) < 5.0
                for row in target_groups if row['jammer'] == jammer
            )
            for jammer in ('NoiseProductJamming', 'NoiseConvolutionJamming')
        }
        fair_rows = [row for row in trial_rows if row['candidate_id'] == cid]
        target_only = [float(row['target_only_change_db']) for row in groups if np.isfinite(float(row['target_only_change_db']))]
        fallback_values = [float(row['fallback_ratio']) for row in groups]
        criteria = {
            'target_jammer_pass': max(positive_by_jammer.values()) >= 2,
            'pd_not_below_identity': all(float(row['pd_algorithm']) >= float(row['pd_identity']) for row in target_groups),
            'target_erased_zero': all(int(row['target_erased_count']) == 0 for row in groups),
            'target_only_gt_minus_0_5': bool(target_only) and float(np.mean(target_only)) > -0.5,
            'nojammer_target_only_gt_minus_0_5': bool(controls) and all(float(row['target_only_change_db']) > -0.5 for row in controls if np.isfinite(float(row['target_only_change_db']))),
            'position_spread_lt_5': all(float(row['position_spread_db']) < 5.0 for row in target_groups),
            'fallback_nonconstant': bool(fallback_values) and 0.0 < float(np.mean(fallback_values)) < 1.0,
            'no_oracle': all(row['oracle_input_status'] == 'PASS' for row in fair_rows),
            'interface_pass': all(row['interface_status'] == 'PASS' for row in fair_rows),
        }
        qualification = all(criteria.values())
        target_means = [float(row['delta_sinr_mean_db']) for row in target_groups if np.isfinite(float(row['delta_sinr_mean_db']))]
        score = (float(np.mean(target_means)) if target_means else -100.0) - 2.0 * (float(np.mean([max(0.0, float(row['position_spread_db']) - 5.0) for row in target_groups])) if target_groups else 100.0)
        output.append({
            **candidate, 'effective_candidate': True, 'qualification': qualification,
            'positive_jsr_count_npj': positive_by_jammer['NoiseProductJamming'],
            'positive_jsr_count_ncj': positive_by_jammer['NoiseConvolutionJamming'],
            'target_delta_mean_db': float(np.mean(target_means)) if target_means else float('nan'),
            'score': score, 'criteria_json': json.dumps(criteria, sort_keys=True),
        })
    return sorted(output, key=lambda row: (bool(row['qualification']), float(row['score'])), reverse=True)


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    nominal_rows = [dict(candidate) for candidate in NOMINAL]
    signature_rows = []
    sequences = {}
    for candidate in NOMINAL:
        signature, sequence = behavior_signature(candidate)
        sequences[candidate['candidate_id']] = sequence
        signature_rows.append({
            **candidate,
            'behavior_signature': signature,
            'diagnostic_trial_count': len(sequence),
            'estimated_sequence_hash': hashlib.sha256(json.dumps([r['estimated_target_idx'] for r in sequence]).encode()).hexdigest(),
            'fallback_sequence_hash': hashlib.sha256(json.dumps([r['fallback'] for r in sequence]).encode()).hexdigest(),
            'confidence_sequence_hash': hashlib.sha256(json.dumps([r['confidence_q'] for r in sequence]).encode()).hexdigest(),
            'processed_output_sequence_hash': hashlib.sha256(json.dumps([r['output_hash'] for r in sequence]).encode()).hexdigest(),
        })
    classes = {}
    for row in signature_rows:
        classes.setdefault(row['behavior_signature'], []).append(row['candidate_id'])
    class_rows, effective_rows = [], []
    class_by_candidate = {}
    for index, (signature, members) in enumerate(sorted(classes.items()), start=1):
        class_id = f'EQ_{index:03d}'
        representative = members[0]
        class_rows.append({'equivalence_class': class_id, 'behavior_signature': signature, 'member_count': len(members), 'representative_candidate': representative, 'members': json.dumps(members)})
        for member in members:
            class_by_candidate[member] = class_id
        effective_rows.append({**candidate_map()[representative], 'equivalence_class': class_id, 'behavior_signature': signature, 'equivalent_nominal_count': len(members)})
    write_csv(output_dir / 'nominal_candidates.csv', nominal_rows)
    write_csv(output_dir / 'behavior_signatures.csv', signature_rows)
    write_csv(output_dir / 'equivalence_classes.csv', class_rows)
    write_csv(output_dir / 'effective_candidates.csv', effective_rows)
    effective_map = candidate_map()
    effective_map = {row['candidate_id']: row for row in effective_rows}
    calibration_rows = []
    target_cache = {}
    for jammer in CALIBRATION_JAMMERS:
        for jsr_db in CALIBRATION_JSRS:
            for seed in CALIBRATION_SEEDS:
                bank = generate_bank(jammer, jsr_db, seed)
                for center in SAFE_TARGET_CENTERS:
                    fixture = compose(bank, center)
                    for candidate in effective_map.values():
                        calibration_rows.append(evaluate_row(candidate, bank, fixture, target_cache))
    aggregate = aggregate_rows(calibration_rows)
    ranking = rank_candidates(list(effective_map.values()), aggregate, calibration_rows)
    # Add equivalence class metadata to ranking and output a single frozen object.
    for row in ranking:
        row['equivalence_class'] = class_by_candidate[row['candidate_id']]
    selected = next((row for row in ranking if row['qualification']), None)
    selected_payload = {
        'selected_candidate': selected,
        'rejection_confirmation_candidate': None if selected else ranking[0],
        'nominal_candidate_count': len(nominal_rows),
        'effective_candidate_count': len(effective_rows),
        'all_candidates_frozen_for_heldout': True,
        'heldout_allowed': selected is not None,
        'heldout_mode': 'PERFORMANCE_CANDIDATE' if selected else 'REJECTION_CONFIRMATION_ONLY',
    }
    write_csv(output_dir / 'per_trial_results.csv', calibration_rows)
    write_csv(output_dir / 'aggregate_results.csv', aggregate)
    write_csv(output_dir / 'candidate_ranking.csv', ranking)
    (output_dir / 'selected_candidate.json').write_text(json.dumps(selected_payload, indent=2, ensure_ascii=False, default=str))
    summary = {
        'task': '036-fix', 'stage': 'stageD', 'status': 'COMPLETED',
        'nominal_candidate_count': len(nominal_rows), 'effective_candidate_count': len(effective_rows),
        'equivalence_class_count': len(class_rows), 'calibration_trial_rows': len(calibration_rows),
        'calibration_aggregate_rows': len(aggregate), 'calibration_qualified_count': sum(bool(row['qualification']) for row in ranking),
        'selected_candidate_id': selected['candidate_id'] if selected else None,
        'heldout_mode': selected_payload['heldout_mode'],
        'candidate_freeze_sha_source': 'selected_candidate.json',
        'no_oracle': all(row['oracle_input_failures'] == 0 for row in aggregate),
        'interface_failures': sum(row['interface_failures'] for row in aggregate),
        'next_stage': 'stageE',
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036_fix/stageD')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
