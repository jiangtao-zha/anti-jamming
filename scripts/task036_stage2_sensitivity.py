"""Task 036 Stage 2: fixed-IQ target-index sensitivity diagnostics.

This runner intentionally exercises the legacy adapt_filter implementation with
different alignment indices. The true index is retained only in the runner for
evaluation and comparison; it is never put in the fair-input dictionary unless
the selected diagnostic mode explicitly asks for an index stress case.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import json
import time
import tracemalloc
from pathlib import Path

import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from anti_jamming.adapters import get_antijam_func
from configs.phase1_radar import get_phase1_radar_params
from unified_framework import JammerLoader, RadarEnvironment
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation


JAMMERS = (
    'NoiseProductJamming',
    'NoiseConvolutionJamming',
    'NoJammer',
    'AMNoiseGaiJam',
    'FMNoiseAimedJam',
    'SMSP',
)
JSRS = (0.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(5000, 5020))
TARGET_CENTERS = (500, 1250, 2500, 3750, 4500)
OFFSETS = (-32, -16, -8, -4, -2, -1, 0, 1, 2, 4, 8, 16, 32)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _full_target(template: np.ndarray, n: int, start: int) -> np.ndarray:
    target = np.zeros(n, dtype=complex)
    end = min(n, start + template.size)
    if end > start:
        target[start:end] = template[:end - start]
    return target


def _shift_record(value: np.ndarray, shift: int) -> np.ndarray:
    """Translate a record with zero padding for position stress testing."""
    value = np.asarray(value)
    output = np.zeros_like(value)
    if shift >= 0:
        source_start = 0
        destination_start = shift
    else:
        source_start = -shift
        destination_start = 0
    count = min(value.size - source_start, value.size - destination_start)
    if count > 0:
        output[destination_start:destination_start + count] = value[
            source_start:source_start + count
        ]
    return output


def _diagnostic_modes(true_idx: int, n: int, seed: int) -> list[dict]:
    modes = [{'mode': 'true', 'supplied_target_idx': int(true_idx)}]
    for offset in OFFSETS:
        if offset == 0:
            continue
        modes.append({
            'mode': f'offset_{offset:+d}',
            'supplied_target_idx': int(np.clip(true_idx + offset, 0, n - 1)),
        })
    modes.extend([
        {'mode': 'fixed_0', 'supplied_target_idx': 0},
        {
            'mode': 'random',
            'supplied_target_idx': int(np.random.default_rng(seed + 903600).integers(0, n)),
        },
        {'mode': 'missing', 'supplied_target_idx': None},
    ])
    return modes


def _algorithm_input(config: dict, received: np.ndarray, template: np.ndarray, target_idx: int | None) -> dict:
    allowed = ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N')
    radar_par = {key: config[key] for key in allowed}
    radar_par['Srt_matrix'] = np.asarray(received, dtype=complex)[None, :]
    radar_par['St_base'] = np.asarray(template, dtype=complex).copy()
    if target_idx is not None:
        # This branch is diagnostic only. Stage 2 records the stress value and
        # does not claim the call is fair when a target index is supplied.
        radar_par['target_idx'] = int(target_idx)
    return radar_par


def _template_vector(template: np.ndarray, n: int, target_idx: int | None) -> np.ndarray:
    s = np.zeros(n, dtype=complex)
    offset = 0 if target_idx is None else max(0, int(target_idx) - template.size // 2)
    end = min(offset + template.size, n)
    if end > offset:
        s[offset:end] = template[:end - offset]
    return s


def _normalized_difference(left: np.ndarray, right: np.ndarray) -> float:
    denominator = np.linalg.norm(right)
    return float(np.linalg.norm(left - right) / (denominator + 1e-12))


def _run_filter_active(radar_par: dict) -> dict:
    started = time.perf_counter()
    tracemalloc.start()
    try:
        processed, processed_template = get_antijam_func('adapt_filter')(
            radar_par, par1=0.01, par2=None
        )
        _, peak_memory = tracemalloc.get_traced_memory()
        processed = np.asarray(processed)
        processed_template = np.asarray(processed_template)
        finite = bool(np.all(np.isfinite(processed)))
        shape_ok = processed.shape == radar_par['Srt_matrix'].shape
        interface = 'PASS' if finite and shape_ok and np.iscomplexobj(processed) else 'FAIL'
        return {
            'processed': processed,
            'processed_template': processed_template,
            'interface_status': interface,
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': '',
            'exception_message': '',
        }
    except Exception as exc:  # keep one bad diagnostic from hiding all cases
        _, peak_memory = tracemalloc.get_traced_memory()
        return {
            'processed': None,
            'processed_template': None,
            'interface_status': 'FAIL',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
        }
    finally:
        tracemalloc.stop()


def _run_filter(radar_par: dict) -> dict:
    """Evaluate the exact algebraic equivalent without materializing ``P_s``.

    Stage 1 proved that the active core computes ``r @ (s^H*a*s)``. This
    implementation applies the same associativity transformation as the
    commented optimization in ``anti_jamming/adapt_filter.py``. The active
    implementation is spot-checked against this path in ``run`` so the full
    Stage 2 matrix does not allocate a 5000x5000 complex matrix for every
    diagnostic mode.
    """
    started = time.perf_counter()
    try:
        s = np.atleast_2d(radar_par['St1'] if 'St1' in radar_par else radar_par['St_base'])
        r = np.atleast_2d(radar_par['Srt_temp'] if 'Srt_temp' in radar_par else radar_par['Srt_matrix'])
        n_r = r.shape[1]
        n_s = s.shape[1]
        if n_s != n_r:
            padded = np.zeros((s.shape[0], n_r), dtype=complex)
            target_idx = radar_par.get('target_idx')
            offset = 0 if target_idx is None else max(0, int(target_idx) - n_s // 2)
            end = min(offset + n_s, n_r)
            if end > offset:
                padded[0, offset:end] = s[0, :end - offset]
            s = padded
        s_h = s.conj().T
        s_inner = (s @ s_h)[0, 0]
        inv_term = 1.0 / (s_inner + 0.01)
        weight = (r @ s_h) * inv_term
        processed = weight @ s
        # Keep the active-core matrix footprint visible in the evidence while
        # also recording the actual equivalent workspace used by this runner.
        legacy_matrix_bytes = int(n_r * n_r * np.dtype(complex).itemsize)
        equivalent_workspace_bytes = int(r.nbytes + s.nbytes + weight.nbytes)
        return {
            'processed': processed,
            'processed_template': np.asarray(radar_par['St_base']),
            'interface_status': 'PASS' if np.all(np.isfinite(processed)) else 'FAIL',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': legacy_matrix_bytes,
            'equivalent_workspace_bytes': equivalent_workspace_bytes,
            'implementation_path': 'algebraic_equivalent_to_active_core',
            'exception_type': '',
            'exception_message': '',
        }
    except Exception as exc:
        return {
            'processed': None,
            'processed_template': None,
            'interface_status': 'FAIL',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': 0,
            'equivalent_workspace_bytes': 0,
            'implementation_path': 'algebraic_equivalent_to_active_core',
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
        }


def _generate_base(config: dict, jammer_name: str, seed: int) -> tuple[np.ndarray, np.ndarray]:
    np.random.seed(seed)
    env = RadarEnvironment(config)
    template = env.generate_target_signal()
    if jammer_name == 'NoJammer':
        radar_par = env.generate_without_jammer(
            noise_level=np.sqrt(config.get('noise_var', 0.1))
        )
    else:
        radar_par = env.generate_with_jammer(JammerLoader.load(jammer_name))
    return np.asarray(radar_par['Srt_matrix'][0], complex), np.asarray(template, complex)


def _one_case(config: dict, jammer_name: str, jsr_db: float, seed: int, center: int) -> list[dict]:
    received_base, template = _generate_base(config, jammer_name, seed)
    baseline_center = int(config['target_idx'])
    shift = int(center - baseline_center)
    received = _shift_record(received_base, shift)
    target = _shift_record(_full_target(template, received.size, int(config['target_start_idx'])), shift)
    eval_config = dict(config)
    eval_config['target_start_idx'] = int(center - template.size // 2)
    eval_config['target_idx'] = int(center)
    true_idx = int(center)
    rows: list[dict] = []
    modes = _diagnostic_modes(true_idx, received.size, seed + center)
    true_result = None
    processed_outputs: dict[str, np.ndarray] = {}
    true_template_vector = _template_vector(template, received.size, true_idx)
    for mode_info in modes:
        mode = mode_info['mode']
        supplied_idx = mode_info['supplied_target_idx']
        radar_par = _algorithm_input(config, received, template, supplied_idx)
        result = _run_filter(radar_par)
        row = {
            'jammer': jammer_name,
            'jsr_db': float(jsr_db),
            'seed': int(seed),
            'target_position': int(center),
            'true_target_idx_for_evaluation_only': int(true_idx),
            'mode': mode,
            'supplied_target_idx': supplied_idx,
            'effective_target_idx': 0 if supplied_idx is None else supplied_idx,
            'target_idx_error': None if supplied_idx is None else int(abs(supplied_idx - true_idx)),
            'oracle_input_status': 'DIAGNOSTIC_INDEX_INJECTED' if supplied_idx is not None else 'PASS_MISSING_INDEX',
            'forbidden_keys_present': 'target_idx' if supplied_idx is not None else '',
            'interface_status': result['interface_status'],
            'runtime_ms': result['runtime_ms'],
            'memory_usage_bytes': result['memory_usage_bytes'],
            'equivalent_workspace_bytes': result.get('equivalent_workspace_bytes', ''),
            'implementation_path': result.get('implementation_path', 'active_core'),
            'exception_type': result['exception_type'],
            'exception_message': result['exception_message'],
        }
        vector = _template_vector(template, received.size, supplied_idx)
        row['filter_coefficient_difference_norm'] = _normalized_difference(vector, true_template_vector)
        if result['interface_status'] == 'PASS':
            processed = result['processed'][0]
            metrics = evaluate_algorithm_output(
                target, received, processed, eval_config,
                runtime_ms=result['runtime_ms'],
                memory_usage_bytes=result['memory_usage_bytes'],
            )
            target_only_input = _algorithm_input(config, target, template, supplied_idx)
            target_only_result = _run_filter(target_only_input)
            if target_only_result['interface_status'] == 'PASS':
                target_metrics = evaluate_target_preservation(
                    target, target_only_result['processed'][0], eval_config
                )
                row.update(target_metrics)
            else:
                row.update({
                    'target_only_response_change_db': float('-inf'),
                    'target_only_response_change_is_finite': False,
                    'target_preservation_status': 'TARGET_ERASED',
                })
            row.update({
                key: metrics[key] for key in (
                    'delta_sinr_db', 'detected_before', 'detected_after',
                    'peak_error_before', 'peak_error_after',
                    'false_peak_count_before', 'false_peak_count_after',
                    'target_window_peak_change_db',
                )
            })
            if mode == 'true':
                true_result = processed.copy()
            processed_outputs[mode] = processed.copy()
            row['output_is_finite'] = True
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
                'output_is_finite': False,
            })
        rows.append(row)

    if true_result is not None:
        for row in rows:
            mode = row['mode']
            processed = processed_outputs.get(mode)
            if processed is not None:
                row['normalized_output_difference_vs_true'] = _normalized_difference(
                    processed, true_result
                )
            else:
                row['normalized_output_difference_vs_true'] = float('nan')
    return rows


def _aggregate(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[key] for key in keys), []).append(row)
    output = []
    for group_key, group in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        valid = [r for r in group if r.get('interface_status') == 'PASS']
        delta = np.asarray([r['delta_sinr_db'] for r in valid if np.isfinite(r.get('delta_sinr_db', np.nan))], float)
        target_change = np.asarray([r['target_only_response_change_db'] for r in valid if np.isfinite(r.get('target_only_response_change_db', np.nan))], float)
        out = {key: value for key, value in zip(keys, group_key)}
        out.update({
            'trials': len(group),
            'interface_pass': sum(r.get('interface_status') == 'PASS' for r in group),
            'target_erased_count': sum(r.get('target_preservation_status') == 'TARGET_ERASED' for r in group),
            'delta_sinr_mean_db': float(np.mean(delta)) if delta.size else float('nan'),
            'delta_sinr_std_db': float(np.std(delta, ddof=1)) if delta.size > 1 else 0.0,
            'delta_sinr_ci95_db': float(1.96 * np.std(delta, ddof=1) / np.sqrt(delta.size)) if delta.size > 1 else 0.0,
            'target_only_change_mean_db': float(np.mean(target_change)) if target_change.size else float('nan'),
            'target_only_change_min_db': float(np.min(target_change)) if target_change.size else float('nan'),
            'detected_after_mean': float(np.mean([r['detected_after'] for r in valid if r.get('detected_after') is not None])) if valid else float('nan'),
            'peak_error_after_mean': float(np.mean([r['peak_error_after'] for r in valid if r.get('peak_error_after') is not None])) if valid else float('nan'),
            'false_peak_after_mean': float(np.mean([r['false_peak_count_after'] for r in valid if r.get('false_peak_count_after') is not None])) if valid else float('nan'),
            'normalized_output_difference_mean': float(np.mean([r['normalized_output_difference_vs_true'] for r in valid if np.isfinite(r.get('normalized_output_difference_vs_true', np.nan))])) if valid else float('nan'),
            'filter_coefficient_difference_mean': float(np.mean([r['filter_coefficient_difference_norm'] for r in group])) if group else float('nan'),
            'runtime_mean_ms': float(np.mean([r['runtime_ms'] for r in group])) if group else float('nan'),
            'memory_mean_bytes': float(np.mean([r['memory_usage_bytes'] for r in group])) if group else float('nan'),
        })
        output.append(out)
    return output


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for jammer in JAMMERS:
        for jsr_db in JSRS:
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            for seed in SEEDS:
                for center in TARGET_CENTERS:
                    rows.extend(_one_case(config, jammer, jsr_db, seed, center))
    aggregate_offset = _aggregate(rows, ('jammer', 'jsr_db', 'mode'))
    aggregate_position = _aggregate(rows, ('jammer', 'jsr_db', 'target_position', 'mode'))
    _write_csv(output_dir / 'per_trial_results.csv', rows)
    _write_csv(output_dir / 'aggregate_by_offset.csv', aggregate_offset)
    _write_csv(output_dir / 'aggregate_by_target_position.csv', aggregate_position)
    spot_rows = []
    for jammer_name in ('NoiseProductJamming', 'NoiseConvolutionJamming'):
        config = get_phase1_radar_params({'JSR_dB': 10.0})
        received_base, template = _generate_base(config, jammer_name, 5000)
        for center in (1500, 2500):
            shift = int(center - config['target_idx'])
            received = _shift_record(received_base, shift)
            for mode_info in _diagnostic_modes(center, received.size, 5000 + center):
                supplied_idx = mode_info['supplied_target_idx']
                radar_par = _algorithm_input(config, received, template, supplied_idx)
                active = _run_filter_active(radar_par)
                equivalent = _run_filter(radar_par)
                if active['interface_status'] == 'PASS' and equivalent['interface_status'] == 'PASS':
                    difference = _normalized_difference(active['processed'][0], equivalent['processed'][0])
                else:
                    difference = float('nan')
                spot_rows.append({
                    'jammer': jammer_name,
                    'target_position': center,
                    'mode': mode_info['mode'],
                    'active_status': active['interface_status'],
                    'equivalent_status': equivalent['interface_status'],
                    'normalized_output_difference': difference,
                    'active_runtime_ms': active['runtime_ms'],
                    'active_memory_bytes': active['memory_usage_bytes'],
                    'equivalent_runtime_ms': equivalent['runtime_ms'],
                    'equivalent_workspace_bytes': equivalent.get('equivalent_workspace_bytes', 0),
                })
    _write_csv(output_dir / 'active_core_equivalence_spot_check.csv', spot_rows)
    summary = {
        'task': '036',
        'stage': 'stage2',
        'status': 'COMPLETED',
        'jammers': list(JAMMERS),
        'jsrs_db': list(JSRS),
        'seeds': [SEEDS[0], SEEDS[-1]],
        'seed_count': len(SEEDS),
        'target_centers': list(TARGET_CENTERS),
        'diagnostic_modes': ['true'] + [f'offset_{o:+d}' for o in OFFSETS if o] + ['fixed_0', 'random', 'missing'],
        'per_trial_rows': len(rows),
        'target_position_fixture': 'zero_padded_translation_of_same_generated_IQ; used because current Phase 1 config derives a fixed target_idx=1500 and target_dist does not move the delay-relative output',
        'oracle_input_policy': 'true_target_idx_for_evaluation_only is held in runner variables; only diagnostic target-index variants inject target_idx into the legacy adapter',
        'implementation_path': 'algebraic_equivalent_to_active_core_for_full_matrix; active_core_equivalence_spot_check_saved_separately',
        'active_core_spot_check_rows': len(spot_rows),
        'active_core_spot_check_max_normalized_difference': float(np.nanmax([r['normalized_output_difference'] for r in spot_rows])),
        'next_stage': 'stage3',
    }
    (output_dir / 'oracle_dependency_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036/stage2')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
