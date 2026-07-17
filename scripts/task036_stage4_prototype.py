"""Task 036 Stage 4 isolated smoke matrix for fair prototypes A/B."""

from __future__ import annotations

import argparse
import csv
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
    fit_adapt_filter_fair_multihypothesis,
)
from anti_jamming.adapters import get_antijam_func  # noqa: E402
from configs.phase1_radar import get_phase1_radar_params  # noqa: E402
from scripts.task036_stage2_sensitivity import (  # noqa: E402
    _full_target,
    _generate_base,
    _shift_record,
)
from unified_framework import JammerLoader, RadarEnvironment  # noqa: E402
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation  # noqa: E402


JAMMERS = (
    'NoiseProductJamming',
    'NoiseConvolutionJamming',
    'NoJammer',
    'AMNoiseGaiJam',
    'FMNoiseAimedJam',
)
JSRS = (0.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(6000, 6010))
TARGET_CENTERS = (500, 1500, 3500)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _public_input(config: dict, received: np.ndarray, template: np.ndarray) -> dict:
    allowed = ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N')
    # IQ and the local template are explicit fit() arguments. Keeping them
    # out of this config dictionary prevents duplicate/conflicting inputs.
    return {key: config[key] for key in allowed}


def _oracle_input(received: np.ndarray, template: np.ndarray, true_idx: int) -> dict:
    return {
        'Srt_matrix': np.asarray(received, dtype=complex)[None, :],
        'St_base': np.asarray(template, dtype=complex).copy(),
        'target_idx': int(true_idx),
    }


def _serialize_diagnostics(model: dict) -> str:
    diagnostics = model.get('diagnostics', {}) if isinstance(model, dict) else {}
    return json.dumps(diagnostics, ensure_ascii=False, sort_keys=True, default=float)


def _run_identity(received: np.ndarray) -> dict:
    return {
        'processed': np.asarray(received, dtype=complex)[None, :],
        'fit_status': 'IDENTITY',
        'estimated_target_idx': None,
        'estimator_confidence': 1.0,
        'condition_number': 1.0,
        'regularization': 0.0,
        'fallback': 'Identity',
        'diagnostics': {},
        'interface_status': 'PASS',
        'oracle_input_status': 'PASS',
        'forbidden_keys_present': '',
        'runtime_ms': 0.0,
        'memory_usage_bytes': 0,
        'exception_type': '',
        'exception_message': '',
    }


def _run_fair(name: str, received: np.ndarray, template: np.ndarray, public: dict) -> dict:
    if FORBIDDEN_KEYS.intersection(public):
        raise AssertionError('fair prototype input unexpectedly contains forbidden key')
    started = time.perf_counter()
    tracemalloc.start()
    try:
        if name == 'adapt_filter_fair':
            model = fit_adapt_filter_fair(received, template, public)
        else:
            model = fit_adapt_filter_fair_multihypothesis(received, template, public)
        processed = apply_adapt_filter_fair(received, model)
        _, peak_memory = tracemalloc.get_traced_memory()
        processed = np.asarray(processed)
        return {
            'processed': processed,
            'model': model,
            'fit_status': model.get('fit_status'),
            'estimated_target_idx': model.get('estimated_target_idx'),
            'estimator_confidence': model.get('estimator_confidence'),
            'condition_number': model.get('condition_number'),
            'regularization': model.get('regularization'),
            'fallback': model.get('fallback'),
            'diagnostics': model.get('diagnostics', {}),
            'interface_status': 'PASS' if processed.shape == (1, received.size) and np.all(np.isfinite(processed)) else 'FAIL',
            'oracle_input_status': 'PASS',
            'forbidden_keys_present': '',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': '',
            'exception_message': '',
        }
    except Exception as exc:
        _, peak_memory = tracemalloc.get_traced_memory()
        return {
            'processed': None,
            'model': {},
            'fit_status': 'INTERFACE_FAIL',
            'estimated_target_idx': None,
            'estimator_confidence': 0.0,
            'condition_number': float('nan'),
            'regularization': float('nan'),
            'fallback': None,
            'diagnostics': {},
            'interface_status': 'FAIL',
            'oracle_input_status': 'PASS',
            'forbidden_keys_present': '',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
        }
    finally:
        tracemalloc.stop()


def _run_oracle(received: np.ndarray, template: np.ndarray, true_idx: int) -> dict:
    started = time.perf_counter()
    tracemalloc.start()
    try:
        processed, processed_template = get_antijam_func('adapt_filter')(
            _oracle_input(received, template, true_idx), par1=0.01, par2=None
        )
        _, peak_memory = tracemalloc.get_traced_memory()
        processed = np.asarray(processed)
        return {
            'processed': processed,
            'processed_template': processed_template,
            'fit_status': 'LEGACY_ORACLE_TRUE_TARGET_IDX',
            'estimated_target_idx': int(true_idx),
            'estimator_confidence': 1.0,
            'condition_number': float('nan'),
            'regularization': 0.01,
            'fallback': None,
            'diagnostics': {},
            'interface_status': 'PASS' if processed.shape == (1, received.size) and np.all(np.isfinite(processed)) else 'FAIL',
            'oracle_input_status': 'ORACLE_TRUE_TARGET_IDX',
            'forbidden_keys_present': 'target_idx',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': '',
            'exception_message': '',
        }
    except Exception as exc:
        _, peak_memory = tracemalloc.get_traced_memory()
        return {
            'processed': None,
            'processed_template': None,
            'fit_status': 'ORACLE_INTERFACE_FAIL',
            'estimated_target_idx': int(true_idx),
            'estimator_confidence': 1.0,
            'condition_number': float('nan'),
            'regularization': 0.01,
            'fallback': None,
            'diagnostics': {},
            'interface_status': 'FAIL',
            'oracle_input_status': 'ORACLE_TRUE_TARGET_IDX',
            'forbidden_keys_present': 'target_idx',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
        }
    finally:
        tracemalloc.stop()


def _one_case(config: dict, jammer_name: str, jsr_db: float, seed: int, center: int) -> list[dict]:
    received_base, template = _generate_base(config, jammer_name, seed)
    shift = int(center - config['target_idx'])
    received = _shift_record(received_base, shift)
    target = _shift_record(_full_target(template, received.size, int(config['target_start_idx'])), shift)
    eval_config = dict(config)
    eval_config['target_start_idx'] = int(center - template.size // 2)
    eval_config['target_idx'] = int(center)
    public = _public_input(config, received, template)
    implementations = [
        ('Identity', _run_identity(received), 'IDENTITY_BASELINE'),
        ('adapt_filter_oracle', _run_oracle(received, template, center), 'ORACLE_UPPER_BOUND'),
        ('adapt_filter_fair', _run_fair('adapt_filter_fair', received, template, public), 'FAIR_PROTOTYPE_A'),
        ('adapt_filter_fair_multihypothesis', _run_fair('adapt_filter_fair_multihypothesis', received, template, public), 'FAIR_PROTOTYPE_B'),
    ]
    rows = []
    for name, result, role in implementations:
        row = {
            'jammer': jammer_name,
            'jsr_db': float(jsr_db),
            'seed': int(seed),
            'target_position': int(center),
            'algorithm': name,
            'role': role,
            'true_target_idx_for_evaluation_only': int(center),
            'estimated_target_idx': result.get('estimated_target_idx'),
            'estimation_error_for_evaluation_only': (
                None if result.get('estimated_target_idx') is None
                else abs(int(result['estimated_target_idx']) - int(center))
            ),
            'estimator_confidence': result.get('estimator_confidence'),
            'fallback': result.get('fallback'),
            'fit_status': result.get('fit_status'),
            'condition_number': result.get('condition_number'),
            'regularization': result.get('regularization'),
            'diagnostics_json': _serialize_diagnostics(result),
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
            if role.startswith('FAIR'):
                public_target = _public_input(config, target, template)
                fair_name = 'adapt_filter_fair' if name == 'adapt_filter_fair' else 'adapt_filter_fair_multihypothesis'
                target_result = _run_fair(fair_name, target, template, public_target)
            elif role == 'ORACLE_UPPER_BOUND':
                target_result = _run_oracle(target, template, center)
            else:
                target_result = _run_identity(target)
            if target_result.get('interface_status') == 'PASS':
                target_metrics = evaluate_target_preservation(
                    target,
                    target_result['processed'][0] if target_result['processed'].ndim == 2 else target_result['processed'],
                    eval_config,
                )
                row.update(target_metrics)
            else:
                row.update({
                    'target_only_response_change_db': float('-inf'),
                    'target_only_response_change_is_finite': False,
                    'target_preservation_status': 'TARGET_ERASED',
                })
            row.update({
                'delta_sinr_db': metrics['delta_sinr_db'],
                'detected_before': metrics['detected_before'],
                'detected_after': metrics['detected_after'],
                'peak_error_before': metrics['peak_error_before'],
                'peak_error_after': metrics['peak_error_after'],
                'false_peak_count_before': metrics['false_peak_count_before'],
                'false_peak_count_after': metrics['false_peak_count_after'],
                'target_window_peak_change_db': metrics['target_window_peak_change_db'],
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
                'target_only_response_change_is_finite': False,
                'target_preservation_status': 'INTERFACE_FAIL',
            })
        rows.append(row)
    return rows


def _aggregate(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        key = (row['jammer'], row['algorithm'], row['jsr_db'], row['target_position'])
        grouped.setdefault(key, []).append(row)
    output = []
    for key, group in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        valid = [r for r in group if r.get('interface_status') == 'PASS']
        deltas = [float(r['delta_sinr_db']) for r in valid if np.isfinite(r.get('delta_sinr_db', np.nan))]
        target_changes = [float(r['target_only_response_change_db']) for r in valid if np.isfinite(r.get('target_only_response_change_db', np.nan))]
        out = dict(zip(('jammer', 'algorithm', 'jsr_db', 'target_position'), key))
        out.update({
            'trials': len(group),
            'interface_pass': sum(r.get('interface_status') == 'PASS' for r in group),
            'oracle_input_failures': sum(r.get('oracle_input_status') == 'FAIL' for r in group),
            'target_erased_count': sum(r.get('target_preservation_status') == 'TARGET_ERASED' for r in group),
            'fallback_count': sum(r.get('fallback') == 'Identity' for r in group),
            'delta_sinr_mean_db': float(np.mean(deltas)) if deltas else float('nan'),
            'delta_sinr_std_db': float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0,
            'target_only_change_mean_db': float(np.mean(target_changes)) if target_changes else float('nan'),
            'pd_after': float(np.mean([r['detected_after'] for r in valid if r.get('detected_after') is not None])) if valid else float('nan'),
            'estimation_error_mean': float(np.mean([r['estimation_error_for_evaluation_only'] for r in valid if r.get('estimation_error_for_evaluation_only') is not None])) if valid else float('nan'),
            'confidence_mean': float(np.mean([r['estimator_confidence'] for r in group if r.get('estimator_confidence') is not None])) if group else float('nan'),
            'runtime_mean_ms': float(np.mean([r['runtime_ms'] for r in group])) if group else float('nan'),
            'memory_mean_bytes': float(np.mean([r['memory_usage_bytes'] for r in group])) if group else float('nan'),
        })
        output.append(out)
    return output


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for jammer in JAMMERS:
        for jsr_db in JSRS:
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            for seed in SEEDS:
                for center in TARGET_CENTERS:
                    rows.extend(_one_case(config, jammer, jsr_db, seed, center))
    aggregate = _aggregate(rows)
    _write_csv(output_dir / 'per_trial_results.csv', rows)
    _write_csv(output_dir / 'aggregate_results.csv', aggregate)
    _write_csv(output_dir / 'estimator_diagnostics.csv', [
        row for row in rows if row['role'].startswith('FAIR')
    ])
    _write_csv(output_dir / 'interface_results.csv', [
        {key: row.get(key) for key in (
            'jammer', 'jsr_db', 'seed', 'target_position', 'algorithm', 'role',
            'interface_status', 'oracle_input_status', 'forbidden_keys_present',
            'fit_status', 'exception_type', 'exception_message',
        )}
        for row in rows
    ])
    metadata = {
        'task': '036',
        'stage': 'stage4',
        'prototypes': ['adapt_filter_fair', 'adapt_filter_fair_multihypothesis'],
        'fair_input_keys': ['C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N', 'Srt_matrix', 'St_base'],
        'forbidden_keys': sorted(FORBIDDEN_KEYS),
        'smoke_matrix': {
            'jammers': list(JAMMERS),
            'jsrs_db': list(JSRS),
            'seeds': [SEEDS[0], SEEDS[-1]],
            'target_centers': list(TARGET_CENTERS),
        },
        'oracle_role': 'legacy current adapt_filter with true target_idx; upper bound only',
        'fallback': 'Identity on low confidence or numerical failure',
    }
    (output_dir / 'prototype_metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    summary = {
        'task': '036',
        'stage': 'stage4',
        'status': 'COMPLETED',
        'case_count': len(JAMMERS) * len(JSRS) * len(SEEDS) * len(TARGET_CENTERS),
        'row_count': len(rows),
        'interface_failures': sum(r.get('interface_status') != 'PASS' for r in rows),
        'oracle_input_failures': sum(r.get('oracle_input_status') == 'FAIL' for r in rows),
        'fair_prototype_rows': sum(r['role'].startswith('FAIR') for r in rows),
        'target_erased_fair_rows': sum(r['role'].startswith('FAIR') and r.get('target_preservation_status') == 'TARGET_ERASED' for r in rows),
        'fair_prototypes': ['adapt_filter_fair', 'adapt_filter_fair_multihypothesis'],
        'decision_gate_pending': True,
        'next_stage': 'stage5',
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036/stage4')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary['interface_failures'] == 0 and summary['oracle_input_failures'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
