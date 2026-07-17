"""Task 036 Stage 5 calibration for fair prototype A/B."""

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
from configs.phase1_radar import get_phase1_radar_params  # noqa: E402
from scripts.task036_stage2_sensitivity import (  # noqa: E402
    _full_target,
    _generate_base,
    _shift_record,
)
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation  # noqa: E402


TARGET_JAMMERS = ('NoiseProductJamming', 'NoiseConvolutionJamming')
NEGATIVE_CONTROLS = ('NoJammer', 'AMNoiseGaiJam', 'FMNoiseAimedJam', 'FMNoiseSaopin', 'SMSP')
JAMMERS = TARGET_JAMMERS + NEGATIVE_CONTROLS
JSRS = (0.0, 5.0, 10.0, 20.0, 30.0)
SEEDS = tuple(range(7000, 7030))
TARGET_CENTERS = (500, 1250, 2500, 3750, 4500)


def _candidate_grid() -> list[dict]:
    candidates = []
    for top_k in (3, 5):
        for confidence in (0.05, 0.12):
            for regularization in (0.001, 0.01):
                candidates.append({
                    'candidate_id': f'A_k{top_k}_c{confidence:g}_r{regularization:g}',
                    'design': 'A',
                    'top_k': top_k,
                    'confidence_threshold': confidence,
                    'regularization': regularization,
                })
                candidates.append({
                    'candidate_id': f'B_k{top_k}_c{confidence:g}_r{regularization:g}',
                    'design': 'B',
                    'top_k': top_k,
                    'confidence_threshold': confidence,
                    'regularization': regularization,
                })
    return candidates


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


def _run_candidate(candidate: dict, received: np.ndarray, target: np.ndarray, template: np.ndarray, config: dict, center: int) -> dict:
    public = _public_config(config)
    assert not FORBIDDEN_KEYS.intersection(public)
    started = time.perf_counter()
    tracemalloc.start()
    try:
        fit_kwargs = {
            'top_k': int(candidate['top_k']),
            'confidence_threshold': float(candidate['confidence_threshold']),
            'regularization': float(candidate['regularization']),
        }
        if candidate['design'] == 'A':
            model = fit_adapt_filter_fair(received, template, public, **fit_kwargs)
        else:
            model = fit_adapt_filter_fair_multihypothesis(received, template, public, **fit_kwargs)
        processed = apply_adapt_filter_fair(received, model)
        target_public = _public_config(config)
        if candidate['design'] == 'A':
            target_model = fit_adapt_filter_fair(target, template, target_public, **fit_kwargs)
        else:
            target_model = fit_adapt_filter_fair_multihypothesis(target, template, target_public, **fit_kwargs)
        target_processed = apply_adapt_filter_fair(target, target_model)
        _, peak_memory = tracemalloc.get_traced_memory()
        eval_config = dict(config)
        eval_config['target_start_idx'] = int(center - template.size // 2)
        eval_config['target_idx'] = int(center)
        metrics = evaluate_algorithm_output(
            target, received, processed[0], eval_config,
            runtime_ms=(time.perf_counter() - started) * 1000.0,
            memory_usage_bytes=int(peak_memory),
        )
        target_metrics = evaluate_target_preservation(target, target_processed[0], eval_config)
        return {
            'candidate_id': candidate['candidate_id'],
            'design': candidate['design'],
            'top_k': candidate['top_k'],
            'confidence_threshold': candidate['confidence_threshold'],
            'regularization': candidate['regularization'],
            'interface_status': 'PASS' if processed.shape == (1, received.size) and np.all(np.isfinite(processed)) else 'FAIL',
            'oracle_input_status': 'PASS',
            'forbidden_keys_present': '',
            'estimated_target_idx': model.get('estimated_target_idx'),
            'estimation_error_for_evaluation_only': None if model.get('estimated_target_idx') is None else abs(int(model['estimated_target_idx']) - int(center)),
            'estimator_confidence': model.get('estimator_confidence'),
            'fit_status': model.get('fit_status'),
            'fallback': model.get('fallback'),
            'condition_number': model.get('condition_number'),
            'target_only_response_change_db': target_metrics['target_only_response_change_db'],
            'target_preservation_status': target_metrics['target_preservation_status'],
            'delta_sinr_db': metrics['delta_sinr_db'],
            'detected_after': metrics['detected_after'],
            'peak_error_after': metrics['peak_error_after'],
            'false_peak_count_after': metrics['false_peak_count_after'],
            'target_window_peak_change_db': metrics['target_window_peak_change_db'],
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': '',
            'exception_message': '',
        }
    except Exception as exc:
        _, peak_memory = tracemalloc.get_traced_memory()
        return {
            'candidate_id': candidate['candidate_id'],
            'design': candidate['design'],
            'top_k': candidate['top_k'],
            'confidence_threshold': candidate['confidence_threshold'],
            'regularization': candidate['regularization'],
            'interface_status': 'FAIL',
            'oracle_input_status': 'PASS',
            'forbidden_keys_present': '',
            'estimated_target_idx': None,
            'estimation_error_for_evaluation_only': None,
            'estimator_confidence': 0.0,
            'fit_status': 'INTERFACE_FAIL',
            'fallback': None,
            'condition_number': float('nan'),
            'target_only_response_change_db': float('-inf'),
            'target_preservation_status': 'INTERFACE_FAIL',
            'delta_sinr_db': float('nan'),
            'detected_after': None,
            'peak_error_after': None,
            'false_peak_count_after': None,
            'target_window_peak_change_db': float('nan'),
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
        }
    finally:
        tracemalloc.stop()


def _aggregate(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        key = (row['candidate_id'], row['design'], row['dataset_role'], row['jammer'], row['jsr_db'], row['target_position'])
        grouped.setdefault(key, []).append(row)
    output = []
    for key, group in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        valid = [r for r in group if r['interface_status'] == 'PASS']
        deltas = np.asarray([r['delta_sinr_db'] for r in valid if np.isfinite(r.get('delta_sinr_db', np.nan))], float)
        target_changes = np.asarray([r['target_only_response_change_db'] for r in valid if np.isfinite(r.get('target_only_response_change_db', np.nan))], float)
        out = dict(zip(('candidate_id', 'design', 'dataset_role', 'jammer', 'jsr_db', 'target_position'), key))
        out.update({
            'trials': len(group),
            'interface_pass': sum(r['interface_status'] == 'PASS' for r in group),
            'oracle_input_failures': sum(r['oracle_input_status'] == 'FAIL' for r in group),
            'target_erased_count': sum(r.get('target_preservation_status') == 'TARGET_ERASED' for r in group),
            'fallback_count': sum(r.get('fallback') == 'Identity' for r in group),
            'delta_sinr_mean_db': float(np.mean(deltas)) if deltas.size else float('nan'),
            'delta_sinr_ci95_db': float(1.96 * np.std(deltas, ddof=1) / np.sqrt(deltas.size)) if deltas.size > 1 else 0.0,
            'target_only_change_mean_db': float(np.mean(target_changes)) if target_changes.size else float('nan'),
            'confidence_mean': float(np.mean([r['estimator_confidence'] for r in group])),
            'estimation_error_mean': float(np.mean([r['estimation_error_for_evaluation_only'] for r in group if r.get('estimation_error_for_evaluation_only') is not None])) if any(r.get('estimation_error_for_evaluation_only') is not None for r in group) else float('nan'),
            'runtime_mean_ms': float(np.mean([r['runtime_ms'] for r in group])),
            'memory_mean_bytes': float(np.mean([r['memory_usage_bytes'] for r in group])),
        })
        output.append(out)
    return output


def _rank_candidates(aggregate: list[dict], candidates: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    ranking = []
    position_rows = []
    rejected = []
    for candidate in candidates:
        cid = candidate['candidate_id']
        target_rows = [r for r in aggregate if r['candidate_id'] == cid and r['dataset_role'] == 'target_jammer']
        controls = [r for r in aggregate if r['candidate_id'] == cid and r['dataset_role'] == 'negative_control']
        no_jammer = [r for r in controls if r['jammer'] == 'NoJammer']
        target_high = [r for r in target_rows if float(r['jsr_db']) in (10.0, 20.0, 30.0)]
        target_gain = np.asarray([float(r['delta_sinr_mean_db']) for r in target_high if np.isfinite(float(r['delta_sinr_mean_db']))], float)
        positive_conditions = sum(float(r['delta_sinr_mean_db']) > 0.0 for r in target_high if np.isfinite(float(r['delta_sinr_mean_db'])))
        target_damage = np.asarray([float(r['target_only_change_mean_db']) for r in target_rows if np.isfinite(float(r['target_only_change_mean_db']))], float)
        no_jammer_damage = np.asarray([float(r['target_only_change_mean_db']) for r in no_jammer if np.isfinite(float(r['target_only_change_mean_db']))], float)
        target_erased = sum(int(r['target_erased_count']) for r in target_rows)
        interface_fail = sum(int(r['trials']) - int(r['interface_pass']) for r in aggregate if r['candidate_id'] == cid)
        position_means = {}
        for r in target_high:
            position_means.setdefault((r['jammer'], r['jsr_db']), []).append(float(r['delta_sinr_mean_db']))
        position_spread = float(np.mean([max(v) - min(v) for v in position_means.values() if v])) if position_means else float('inf')
        qualifies = bool(
            target_gain.size > 0
            and positive_conditions >= 2
            and target_erased == 0
            and (float(np.mean(target_damage)) if target_damage.size else -np.inf) > -1.0
            and (float(np.mean(no_jammer_damage)) if no_jammer_damage.size else -np.inf) >= -0.5
            and position_spread < 5.0
            and interface_fail == 0
        )
        score = (
            (float(np.mean(target_gain)) if target_gain.size else -50.0)
            - 0.5 * max(0.0, -(float(np.mean(no_jammer_damage)) if no_jammer_damage.size else 50.0))
            - 0.2 * position_spread
            - 0.1 * target_erased
        )
        row = dict(candidate)
        row.update({
            'target_gain_mean_db': float(np.mean(target_gain)) if target_gain.size else float('nan'),
            'positive_target_conditions': positive_conditions,
            'target_only_mean_db': float(np.mean(target_damage)) if target_damage.size else float('nan'),
            'NoJammer_target_only_mean_db': float(np.mean(no_jammer_damage)) if no_jammer_damage.size else float('nan'),
            'target_erased_count': target_erased,
            'interface_failures': interface_fail,
            'position_spread_db': position_spread,
            'score': score,
            'calibration_qualified': qualifies,
            'rejection_reason': '' if qualifies else 'CALIBRATION_GATE_NOT_MET',
        })
        ranking.append(row)
        position_rows.extend([
            {
                'candidate_id': cid,
                'design': candidate['design'],
                'jammer': r['jammer'],
                'jsr_db': r['jsr_db'],
                'target_position': r['target_position'],
                'delta_sinr_mean_db': r['delta_sinr_mean_db'],
                'target_only_change_mean_db': r['target_only_change_mean_db'],
                'target_erased_count': r['target_erased_count'],
            }
            for r in target_high
        ])
        if not qualifies:
            rejected.append(row)
    ranking.sort(key=lambda row: row['score'], reverse=True)
    return ranking, rejected, position_rows


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = _candidate_grid()
    assert len(candidates) == 16
    rows = []
    for jammer in JAMMERS:
        dataset_role = 'target_jammer' if jammer in TARGET_JAMMERS else 'negative_control'
        for jsr_db in JSRS:
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            for seed in SEEDS:
                received_base, template = _generate_base(config, jammer, seed)
                for center in TARGET_CENTERS:
                    shift = int(center - config['target_idx'])
                    received = _shift_record(received_base, shift)
                    target = _shift_record(_full_target(template, received.size, int(config['target_start_idx'])), shift)
                    for candidate in candidates:
                        result = _run_candidate(candidate, received, target, template, config, center)
                        result.update({
                            'dataset_role': dataset_role,
                            'jammer': jammer,
                            'jsr_db': float(jsr_db),
                            'seed': int(seed),
                            'target_position': int(center),
                        })
                        rows.append(result)
    aggregate = _aggregate(rows)
    ranking, rejected, position_rows = _rank_candidates(aggregate, candidates)
    _write_csv(output_dir / 'parameter_search.csv', aggregate)
    _write_csv(output_dir / 'candidate_ranking.csv', ranking)
    _write_csv(output_dir / 'rejected_candidates.csv', rejected)
    _write_csv(output_dir / 'position_robustness.csv', position_rows)
    selected = next((row for row in ranking if row['calibration_qualified']), None)
    selected_payload = {
        'selected_candidate': selected,
        'all_candidates_frozen_for_heldout': False if selected is None else True,
        'candidate_count': len(candidates),
        'seed_range': [SEEDS[0], SEEDS[-1]],
        'target_positions': list(TARGET_CENTERS),
        'heldout_allowed': selected is not None,
    }
    (output_dir / 'selected_candidate.json').write_text(json.dumps(selected_payload, indent=2, ensure_ascii=False))
    summary = {
        'task': '036',
        'stage': 'stage5',
        'status': 'COMPLETED',
        'candidate_count': len(candidates),
        'raw_rows': len(rows),
        'aggregate_rows': len(aggregate),
        'interface_failures': sum(r['interface_status'] != 'PASS' for r in rows),
        'oracle_input_failures': sum(r['oracle_input_status'] == 'FAIL' for r in rows),
        'calibration_qualified_count': sum(row['calibration_qualified'] for row in ranking),
        'selected_candidate_id': None if selected is None else selected['candidate_id'],
        'heldout_gate': 'OPEN' if selected is not None else 'REJECTION_CONFIRMATION_ONLY',
        'heldout_seed_range': [8000, 8049],
        'next_stage': 'stage6',
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    metadata = {
        'parameter_grid': candidates,
        'target_jammers': list(TARGET_JAMMERS),
        'negative_controls': list(NEGATIVE_CONTROLS),
        'jsrs_db': list(JSRS),
        'seeds': [SEEDS[0], SEEDS[-1]],
        'target_positions': list(TARGET_CENTERS),
        'maximum_candidate_count': 40,
        'forbidden_keys': sorted(FORBIDDEN_KEYS),
    }
    (output_dir / 'calibration_metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036/stage5')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary['interface_failures'] == 0 and summary['oracle_input_failures'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
