"""Task 036-fix Stage C: effective observable confidence and Identity gating."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from anti_jamming.adapt_filter_fair import (  # noqa: E402
    CONFIDENCE_WEIGHTS,
    apply_adapt_filter_fair,
    fit_adapt_filter_fair,
    fit_adapt_filter_fair_multihypothesis,
)
from configs.phase1_radar import get_phase1_radar_params  # noqa: E402
from scripts.task036_fix_fixture import compose, embed_target, generate_bank  # noqa: E402
from unified_framework import RadarEnvironment  # noqa: E402


ALGORITHMS = {
    'A': fit_adapt_filter_fair,
    'B': fit_adapt_filter_fair_multihypothesis,
}
CONFIDENCE_THRESHOLD = 0.80
TOP_K = 3
REGULARIZATION = 0.001


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


def build_cases() -> list[dict]:
    config = get_phase1_radar_params({'JSR_dB': 10.0})
    template = np.asarray(RadarEnvironment(config).generate_target_signal(), dtype=complex)
    center = 1500
    cases = []
    target = embed_target(template, center, config['N'])
    cases.append({
        'case_id': 'clean_target', 'case_type': 'CLEAN_TARGET', 'jammer': 'NoJammer',
        'jsr_db': 0.0, 'seed': 0, 'true_center': center,
        'observed': target, 'template': template, 'config': config,
    })
    for jsr_db, seed, label in ((0.0, 6200, 'LOW_JSR'), (10.0, 6201, 'MID_JSR'), (30.0, 6202, 'HIGH_JSR')):
        bank = generate_bank('NoiseProductJamming', jsr_db, seed)
        fixture = compose(bank, center)
        cases.append({
            'case_id': f'npj_jsr_{int(jsr_db)}', 'case_type': label, 'jammer': 'NoiseProductJamming',
            'jsr_db': jsr_db, 'seed': seed, 'true_center': center,
            'observed': fixture['received'], 'template': fixture['template'], 'config': bank.config,
        })
    bank = generate_bank('NoJammer', 0.0, 6203)
    fixture = compose(bank, center)
    cases.append({
        'case_id': 'no_jammer', 'case_type': 'NO_JAMMER', 'jammer': 'NoJammer',
        'jsr_db': 0.0, 'seed': 6203, 'true_center': center,
        'observed': fixture['received'], 'template': fixture['template'], 'config': bank.config,
    })
    rng = np.random.default_rng(6204)
    noise = 0.03 * (rng.normal(size=config['N']) + 1j * rng.normal(size=config['N']))
    false_target = 2.5 * embed_target(template, 3500, config['N'])
    weak_true = 0.15 * target
    cases.append({
        'case_id': 'false_peak_dominant', 'case_type': 'FALSE_PEAK_DOMINANT', 'jammer': 'synthetic_observable_case',
        'jsr_db': 0.0, 'seed': 6204, 'true_center': center,
        'observed': false_target + weak_true + noise, 'template': template, 'config': config,
    })
    rng = np.random.default_rng(6205)
    ambiguity_noise = 0.02 * (rng.normal(size=config['N']) + 1j * rng.normal(size=config['N']))
    ambiguous = embed_target(template, center, config['N']) + embed_target(template, 3000, config['N']) + ambiguity_noise
    cases.append({
        'case_id': 'ambiguous_two_peaks', 'case_type': 'AMBIGUOUS_PEAKS', 'jammer': 'synthetic_observable_case',
        'jsr_db': 0.0, 'seed': 6205, 'true_center': center,
        'observed': ambiguous, 'template': template, 'config': config,
    })
    rng = np.random.default_rng(6206)
    pure_noise = rng.normal(size=config['N']) + 1j * rng.normal(size=config['N'])
    cases.append({
        'case_id': 'pure_noise', 'case_type': 'PURE_NOISE', 'jammer': 'synthetic_observable_case',
        'jsr_db': 0.0, 'seed': 6206, 'true_center': center,
        'observed': pure_noise, 'template': template, 'config': config,
    })
    return cases


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    case_rows = []
    component_rows = []
    for case in cases:
        public = public_config(case['config'])
        for algorithm, fit_fn in ALGORITHMS.items():
            try:
                model = fit_fn(
                    case['observed'], case['template'], public,
                    top_k=TOP_K,
                    confidence_threshold=CONFIDENCE_THRESHOLD,
                    regularization=REGULARIZATION,
                )
                processed = apply_adapt_filter_fair(case['observed'], model)
                interface_status = 'PASS' if processed.shape == (1, case['observed'].size) and np.all(np.isfinite(processed)) else 'FAIL'
                exception_type, exception_message = '', ''
            except Exception as exc:
                model = {'estimated_target_idx': None, 'estimator_confidence': 0.0, 'fallback': 'Identity', 'fit_status': 'INTERFACE_FAIL', 'diagnostics': {}}
                interface_status = 'FAIL'
                exception_type, exception_message = type(exc).__name__, str(exc)
            diagnostics = model.get('diagnostics', {})
            components = diagnostics.get('confidence_components', {})
            for component in CONFIDENCE_WEIGHTS:
                component_rows.append({
                    'case_id': case['case_id'], 'case_type': case['case_type'], 'algorithm': algorithm,
                    'component': component, 'value': float(components.get(component, 0.0)),
                    'in_unit_interval': 0.0 <= float(components.get(component, 0.0)) <= 1.0,
                })
            estimated = model.get('estimated_target_idx')
            error = None if estimated is None else abs(int(estimated) - case['true_center'])
            case_rows.append({
                'case_id': case['case_id'], 'case_type': case['case_type'], 'jammer': case['jammer'],
                'jsr_db': case['jsr_db'], 'seed': case['seed'], 'algorithm': algorithm,
                'true_target_idx_for_evaluation_only': case['true_center'],
                'estimated_target_idx': estimated, 'evaluation_only_estimation_error': error,
                'confidence': float(model.get('estimator_confidence', 0.0)),
                'confidence_threshold': CONFIDENCE_THRESHOLD, 'fallback': model.get('fallback'),
                'fit_status': model.get('fit_status'), 'interface_status': interface_status,
                'gate_reasons': json.dumps(diagnostics.get('gate_reasons', []), ensure_ascii=False),
                'exception_type': exception_type, 'exception_message': exception_message,
            })
    write_csv(output_dir / 'confidence_cases.csv', case_rows)
    write_csv(output_dir / 'confidence_components.csv', component_rows)
    fallback_rows = []
    for (algorithm, case_type), group in sorted({
        (algorithm, case_type): [row for row in case_rows if row['algorithm'] == algorithm and row['case_type'] == case_type]
        for algorithm in ALGORITHMS for case_type in sorted({c['case_type'] for c in cases})
    }.items()):
        fallback_rows.append({
            'algorithm': algorithm, 'case_type': case_type, 'trials': len(group),
            'fallback_count': sum(row['fallback'] == 'Identity' for row in group),
            'fallback_ratio': sum(row['fallback'] == 'Identity' for row in group) / len(group),
            'confidence_mean': float(np.mean([float(row['confidence']) for row in group])),
            'estimation_error_mean': float(np.mean([row['evaluation_only_estimation_error'] for row in group if row['evaluation_only_estimation_error'] is not None])) if any(row['evaluation_only_estimation_error'] is not None for row in group) else None,
            'interface_failures': sum(row['interface_status'] != 'PASS' for row in group),
        })
    write_csv(output_dir / 'fallback_analysis.csv', fallback_rows)
    fallback_ratios = [row['fallback_ratio'] for row in fallback_rows]
    total_trials = len(case_rows)
    total_fallbacks = sum(row['fallback'] == 'Identity' for row in case_rows)
    overall_fallback_ratio = total_fallbacks / total_trials if total_trials else 0.0
    summary = {
        'task': '036-fix', 'stage': 'stageC', 'status': 'COMPLETED',
        'case_count': len(cases), 'algorithm_count': len(ALGORITHMS),
        'confidence_weights': CONFIDENCE_WEIGHTS,
        'confidence_threshold': CONFIDENCE_THRESHOLD, 'top_k': TOP_K,
        'regularization': REGULARIZATION,
        'component_range_pass': all(row['in_unit_interval'] for row in component_rows),
        'interface_failures': sum(row['interface_status'] != 'PASS' for row in case_rows),
        'fallback_ratio_min': min(fallback_ratios), 'fallback_ratio_max': max(fallback_ratios),
        'total_trials': total_trials, 'total_fallbacks': total_fallbacks,
        'overall_fallback_ratio': overall_fallback_ratio,
        'fallback_ratio_strictly_between_zero_one': 0.0 < overall_fallback_ratio < 1.0,
        'no_oracle': True, 'no_target_erased_metric_in_fit': True,
        'next_stage': 'stageD',
    }
    (output_dir / 'gating_metadata.json').write_text(json.dumps({
        'confidence_components': list(CONFIDENCE_WEIGHTS),
        'weights': CONFIDENCE_WEIGHTS,
        'threshold': CONFIDENCE_THRESHOLD,
        'top_k': TOP_K,
        'regularization': REGULARIZATION,
        'edge_guard_rule': 'min distance to valid center bound >= max(4, template_length//10)',
        'condition_number_limit': 1e6,
        'output_proxy_minimum': 0.05,
        'oracle_inputs': [],
        'case_types': sorted({case['case_type'] for case in cases}),
    }, indent=2, ensure_ascii=False))
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='results/phase1/task036_fix/stageC')
    args = parser.parse_args()
    summary = run(Path(args.output_dir))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
