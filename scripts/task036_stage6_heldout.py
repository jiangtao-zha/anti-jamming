"""Task 036 Stage 6 held-out evaluation.

When calibration produces no qualified candidate, this script runs the
required rejection-confirmation comparison: Identity, legacy oracle upper
bound, and the frozen best-but-unqualified fair prototype.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from anti_jamming.adapt_filter_fair import (  # noqa: E402
    FORBIDDEN_KEYS,
    apply_adapt_filter_fair,
    fit_adapt_filter_fair,
)
from configs.phase1_radar import get_phase1_radar_params  # noqa: E402
from scripts.task036_stage2_sensitivity import (  # noqa: E402
    _full_target,
    _generate_base,
    _shift_record,
)
from scripts.task036_stage4_prototype import _run_oracle  # noqa: E402
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation  # noqa: E402


TARGET_JAMMERS = ('NoiseProductJamming', 'NoiseConvolutionJamming')
NEGATIVE_CONTROLS = ('NoJammer', 'AMNoiseGaiJam', 'FMNoiseAimedJam', 'FMNoiseSaopin', 'SMSP', 'FMZuse')
JAMMERS = TARGET_JAMMERS + NEGATIVE_CONTROLS
JSRS = (0.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(8000, 8050))
TARGET_CENTERS = (500, 1250, 2500, 3750, 4500)
FROZEN_CANDIDATE = {
    'candidate_id': 'A_k3_c0.05_r0.001',
    'design': 'A',
    'top_k': 3,
    'confidence_threshold': 0.05,
    'regularization': 0.001,
}
_ORACLE_TARGET_CACHE: dict[tuple[int, int, bytes], np.ndarray] = {}


def _write_csv(path: Path, rows: list[dict]) -> None:
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


def _public_config(config: dict) -> dict:
    return {key: config[key] for key in ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N')}


def _identity(received: np.ndarray) -> dict:
    return {
        'processed': received[None, :].copy(),
        'interface_status': 'PASS',
        'oracle_input_status': 'PASS',
        'forbidden_keys_present': '',
        'estimated_target_idx': None,
        'estimator_confidence': 1.0,
        'fallback': 'Identity',
        'fit_status': 'IDENTITY',
        'runtime_ms': 0.0,
        'memory_usage_bytes': 0,
        'exception_type': '',
        'exception_message': '',
    }


def _fair(received: np.ndarray, target: np.ndarray, template: np.ndarray, config: dict, center: int) -> dict:
    public = _public_config(config)
    if FORBIDDEN_KEYS.intersection(public):
        raise AssertionError('forbidden fair input key')
    fit_kwargs = {
        'top_k': FROZEN_CANDIDATE['top_k'],
        'confidence_threshold': FROZEN_CANDIDATE['confidence_threshold'],
        'regularization': FROZEN_CANDIDATE['regularization'],
    }
    started = time.perf_counter()
    tracemalloc.start()
    try:
        model = fit_adapt_filter_fair(received, template, public, **fit_kwargs)
        processed = apply_adapt_filter_fair(received, model)
        target_model = fit_adapt_filter_fair(target, template, public, **fit_kwargs)
        target_processed = apply_adapt_filter_fair(target, target_model)
        _, peak_memory = tracemalloc.get_traced_memory()
        return {
            'processed': processed,
            'target_processed': target_processed,
            'model': model,
            'interface_status': 'PASS' if processed.shape == (1, received.size) and np.all(np.isfinite(processed)) else 'FAIL',
            'oracle_input_status': 'PASS',
            'forbidden_keys_present': '',
            'estimated_target_idx': model.get('estimated_target_idx'),
            'estimator_confidence': model.get('estimator_confidence'),
            'fallback': model.get('fallback'),
            'fit_status': model.get('fit_status'),
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': '',
            'exception_message': '',
        }
    except Exception as exc:
        _, peak_memory = tracemalloc.get_traced_memory()
        return {
            'processed': None,
            'target_processed': None,
            'model': {},
            'interface_status': 'FAIL',
            'oracle_input_status': 'PASS',
            'forbidden_keys_present': '',
            'estimated_target_idx': None,
            'estimator_confidence': 0.0,
            'fallback': None,
            'fit_status': 'INTERFACE_FAIL',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
        }
    finally:
        tracemalloc.stop()


def _row(algorithm: str, role: str, result: dict, received: np.ndarray, target: np.ndarray, template: np.ndarray, config: dict, center: int, jammer: str, jsr_db: float, seed: int) -> dict:
    eval_config = dict(config)
    eval_config['target_start_idx'] = int(center - template.size // 2)
    eval_config['target_idx'] = int(center)
    row = {
        'jammer': jammer,
        'jsr_db': float(jsr_db),
        'seed': int(seed),
        'target_position': int(center),
        'algorithm': algorithm,
        'role': role,
        'candidate_id': FROZEN_CANDIDATE['candidate_id'] if role == 'FROZEN_FAIR_REJECTION_CONFIRMATION' else '',
        'true_target_idx_for_evaluation_only': int(center),
        'estimated_target_idx': result.get('estimated_target_idx'),
        'estimation_error_for_evaluation_only': None if result.get('estimated_target_idx') is None else abs(int(result['estimated_target_idx']) - int(center)),
        'estimator_confidence': result.get('estimator_confidence'),
        'fallback': result.get('fallback'),
        'fit_status': result.get('fit_status'),
        'oracle_input_status': result.get('oracle_input_status'),
        'forbidden_keys_present': result.get('forbidden_keys_present', ''),
        'interface_status': result.get('interface_status'),
        'runtime_ms': result.get('runtime_ms'),
        'memory_usage_bytes': result.get('memory_usage_bytes'),
        'exception_type': result.get('exception_type'),
        'exception_message': result.get('exception_message'),
    }
    processed = result.get('processed')
    if result.get('interface_status') == 'PASS' and processed is not None:
        processed_1d = processed[0] if processed.ndim == 2 else processed
        metrics = evaluate_algorithm_output(
            target, received, processed_1d, eval_config,
            runtime_ms=result.get('runtime_ms'),
            memory_usage_bytes=result.get('memory_usage_bytes'),
        )
        target_processed = result.get('target_processed')
        if target_processed is None:
            if role == 'ORACLE_UPPER_BOUND':
                # Evaluate the oracle's target-only response independently. The
                # received record is the jammer case; using it as the target
                # reference would either be invalid or mark the oracle as
                # TARGET_ERASED merely because _run_oracle has no paired
                # target output.
                cache_key = (int(center), int(target.size), template.tobytes())
                if cache_key not in _ORACLE_TARGET_CACHE:
                    target_oracle = _run_oracle(target, template, center)
                    if target_oracle.get('interface_status') == 'PASS':
                        _ORACLE_TARGET_CACHE[cache_key] = target_oracle['processed'].copy()
                target_processed = _ORACLE_TARGET_CACHE.get(cache_key)
            elif role == 'IDENTITY_BASELINE':
                target_processed = processed
        if role == 'IDENTITY_BASELINE':
            target_metrics = evaluate_target_preservation(target, target, eval_config)
        elif target_processed is not None:
            target_metrics = evaluate_target_preservation(
                target,
                target_processed[0] if target_processed.ndim == 2 else target_processed,
                eval_config,
            )
        else:
            target_metrics = {
                'target_only_response_change_db': float('-inf'),
                'target_preservation_status': 'TARGET_ERASED',
            }
        row.update({
            'delta_sinr_db': metrics['delta_sinr_db'],
            'detected_before': metrics['detected_before'],
            'detected_after': metrics['detected_after'],
            'peak_error_before': metrics['peak_error_before'],
            'peak_error_after': metrics['peak_error_after'],
            'false_peak_count_before': metrics['false_peak_count_before'],
            'false_peak_count_after': metrics['false_peak_count_after'],
            'target_window_peak_change_db': metrics['target_window_peak_change_db'],
            'target_only_response_change_db': target_metrics['target_only_response_change_db'],
            'target_preservation_status': target_metrics['target_preservation_status'],
        })
    else:
        row.update({
            'delta_sinr_db': float('nan'),
            'detected_before': None,
            'detected_after': None,
            'peak_error_before': None,
            'peak_error_after': None,
            'false_peak_count_before': None,
            'false_peak_count_after': None,
            'target_window_peak_change_db': float('nan'),
            'target_only_response_change_db': float('-inf'),
            'target_preservation_status': 'INTERFACE_FAIL',
        })
    return row


def _aggregate(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        key = (row['jammer'], row['algorithm'], row['role'], row['jsr_db'], row['target_position'])
        grouped.setdefault(key, []).append(row)
    output = []
    for key, group in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        valid = [r for r in group if r['interface_status'] == 'PASS']
        deltas = np.asarray([r['delta_sinr_db'] for r in valid if np.isfinite(r.get('delta_sinr_db', np.nan))], float)
        target_changes = np.asarray([r['target_only_response_change_db'] for r in valid if np.isfinite(r.get('target_only_response_change_db', np.nan))], float)
        out = dict(zip(('jammer', 'algorithm', 'role', 'jsr_db', 'target_position'), key))
        out.update({
            'trials': len(group),
            'interface_pass': sum(r['interface_status'] == 'PASS' for r in group),
            'oracle_input_failures': sum(r['oracle_input_status'] == 'FAIL' for r in group),
            'target_erased_count': sum(r.get('target_preservation_status') == 'TARGET_ERASED' for r in group),
            'fallback_count': sum(r.get('fallback') == 'Identity' for r in group),
            'delta_sinr_mean_db': float(np.mean(deltas)) if deltas.size else float('nan'),
            'delta_sinr_std_db': float(np.std(deltas, ddof=1)) if deltas.size > 1 else 0.0,
            'delta_sinr_ci95_db': float(1.96 * np.std(deltas, ddof=1) / np.sqrt(deltas.size)) if deltas.size > 1 else 0.0,
            'target_only_change_mean_db': float(np.mean(target_changes)) if target_changes.size else float('nan'),
            'pd_after': float(np.mean([r['detected_after'] for r in valid if r.get('detected_after') is not None])) if valid else float('nan'),
            'estimation_error_mean': float(np.mean([r['estimation_error_for_evaluation_only'] for r in valid if r.get('estimation_error_for_evaluation_only') is not None])) if any(r.get('estimation_error_for_evaluation_only') is not None for r in valid) else float('nan'),
            'confidence_mean': float(np.mean([r['estimator_confidence'] for r in group])),
            'runtime_mean_ms': float(np.mean([r['runtime_ms'] for r in group])),
            'memory_mean_bytes': float(np.mean([r['memory_usage_bytes'] for r in group])),
        })
        output.append(out)
    return output


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_path = Path('results/phase1/task036/stage5/selected_candidate.json')
    selected = json.loads(selected_path.read_text())
    assert selected['rejection_confirmation_candidate']['candidate_id'] == FROZEN_CANDIDATE['candidate_id']
    candidate_hash = hashlib.sha256(selected_path.read_bytes()).hexdigest()
    rows = []
    for jammer in JAMMERS:
        for jsr_db in JSRS:
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            for seed in SEEDS:
                received_base, template = _generate_base(config, jammer, seed)
                for center in TARGET_CENTERS:
                    shift = int(center - config['target_idx'])
                    received = _shift_record(received_base, shift)
                    target = _shift_record(_full_target(template, received.size, int(config['target_start_idx'])), shift)
                    identity = _identity(received)
                    oracle = _run_oracle(received, template, center)
                    fair = _fair(received, target, template, config, center)
                    rows.append(_row('Identity', 'IDENTITY_BASELINE', identity, received, target, template, config, center, jammer, jsr_db, seed))
                    rows.append(_row('adapt_filter_oracle', 'ORACLE_UPPER_BOUND', oracle, received, target, template, config, center, jammer, jsr_db, seed))
                    rows.append(_row('adapt_filter_fair_frozen', 'FROZEN_FAIR_REJECTION_CONFIRMATION', fair, received, target, template, config, center, jammer, jsr_db, seed))
    aggregate = _aggregate(rows)
    fair_aggregate = [r for r in aggregate if r['role'] == 'FROZEN_FAIR_REJECTION_CONFIRMATION']
    identity_aggregate = [r for r in aggregate if r['role'] == 'IDENTITY_BASELINE']
    oracle_aggregate = [r for r in aggregate if r['role'] == 'ORACLE_UPPER_BOUND']
    _write_csv(output_dir / 'per_trial_results.csv', rows)
    _write_csv(output_dir / 'aggregate_results.csv', aggregate)
    _write_csv(output_dir / 'identity_comparison.csv', identity_aggregate + fair_aggregate)
    _write_csv(output_dir / 'oracle_upper_bound_comparison.csv', oracle_aggregate)
    _write_csv(output_dir / 'position_robustness.csv', fair_aggregate)
    _write_csv(output_dir / 'fallback_analysis.csv', [
        {key: row[key] for key in ('jammer', 'jsr_db', 'target_position', 'trials', 'fallback_count', 'confidence_mean', 'estimation_error_mean', 'target_erased_count')}
        for row in fair_aggregate
    ])
    fair_target = [r for r in fair_aggregate if r['jammer'] in TARGET_JAMMERS and float(r['jsr_db']) in (10.0, 20.0, 30.0)]
    positive_conditions = sum(float(r['delta_sinr_mean_db']) > 0.5 and float(r['delta_sinr_mean_db']) - float(r['delta_sinr_ci95_db']) >= 0.0 for r in fair_target if np.isfinite(float(r['delta_sinr_mean_db'])))
    target_erased = sum(int(r['target_erased_count']) for r in fair_aggregate)
    no_jammer = [r for r in fair_aggregate if r['jammer'] == 'NoJammer']
    no_jammer_target_change = np.asarray([float(r['target_only_change_mean_db']) for r in no_jammer if np.isfinite(float(r['target_only_change_mean_db']))], float)
    position_spread = float(np.mean([max(float(r['delta_sinr_mean_db']) for r in fair_target if r['jammer'] == jammer and float(r['jsr_db']) == jsr) - min(float(r['delta_sinr_mean_db']) for r in fair_target if r['jammer'] == jammer and float(r['jsr_db']) == jsr) for jammer in TARGET_JAMMERS for jsr in (10.0, 20.0, 30.0)]))
    decision = 'FAIR_CANDIDATE' if positive_conditions >= 2 and target_erased == 0 and no_jammer_target_change.size and float(np.mean(no_jammer_target_change)) > -1.0 and position_spread < 5.0 else 'ORACLE_UPPER_BOUND_ONLY'
    summary = {
        'task': '036',
        'stage': 'stage6',
        'status': 'COMPLETED',
        'mode': 'rejection_confirmation_only',
        'jammers': list(JAMMERS),
        'jsrs_db': list(JSRS),
        'seeds': [SEEDS[0], SEEDS[-1]],
        'seed_count': len(SEEDS),
        'target_positions': list(TARGET_CENTERS),
        'candidate_id': FROZEN_CANDIDATE['candidate_id'],
        'candidate_file_sha256': candidate_hash,
        'candidate_source_commit': 'b623a01',
        'fair_positive_conditions': positive_conditions,
        'fair_target_erased_count': target_erased,
        'fair_no_jammer_target_only_mean_db': float(np.mean(no_jammer_target_change)) if no_jammer_target_change.size else float('nan'),
        'fair_position_spread_db': position_spread,
        'decision_signal_only': decision,
        'heldout_after_tuning': False,
        'next_stage': 'stage7',
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (output_dir / 'heldout_metadata.json').write_text(json.dumps({
        'mode': 'rejection_confirmation_only',
        'candidate': FROZEN_CANDIDATE,
        'candidate_file_sha256': candidate_hash,
        'candidate_source_commit': 'b623a01',
        'seeds': [SEEDS[0], SEEDS[-1]],
        'target_positions': list(TARGET_CENTERS),
        'no_post_heldout_tuning': True,
    }, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036/stage6')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
