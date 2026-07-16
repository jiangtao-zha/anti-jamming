"""Unified Phase 1 interface/performance contract for algorithm tests."""

import csv
import json
import time
import traceback
import tracemalloc
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from anti_jamming.adapters import get_antijam_func
from configs.phase1_radar import get_phase1_radar_params
from unified_framework import JammerLoader, RadarEnvironment
from utils.evaluation import evaluate_algorithm_output, evaluate_target_preservation


PAIR_MATRIX = [
    ('AMNoiseGaiJam', 'FDC', 'FrequencyDomainCanceller', {'cancellation_strength': 0.8}),
    ('FMNoiseAimedJam', 'FrFT', 'frft_filter', {'mask_threshold': 0.1}),
    ('FMNoiseSaopin', 'FrFT', 'frft_filter', {'mask_threshold': 0.1}),
    ('SMSP', 'qpzh', 'qpzh', {'m': 8, 'n': 2}),
    ('ISDJ', 'qpzh', 'qpzh', {'m': 8, 'n': 2}),
    ('SliceCombineJam', 'FSTP', 'FastSlowTimeProcessor', {'limit_factor': 3.0}),
    ('SMSP', 'FSTP', 'FastSlowTimeProcessor', {'limit_factor': 3.0}),
    ('NoiseProductJamming', 'adapt_filter', 'adapt_filter', {'par1': 0.01}),
    ('NoiseConvolutionJamming', 'adapt_filter', 'adapt_filter', {'par1': 0.01}),
    ('FMZuse', 'WLN', 'WLN', {'par1': 0.3, 'par2': 6}),
]


def _write_csv(path, rows):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _whitelist_radar_par(config, received, template):
    allowed = ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N', 'target_dist')
    radar_par = {key: config[key] for key in allowed if key in config}
    radar_par['Srt_matrix'] = np.asarray(received, dtype=complex)[None, :]
    radar_par['St_base'] = np.asarray(template, dtype=complex).copy()
    return radar_par


def _interface_error(exc):
    return {
        'exception_type': type(exc).__name__,
        'exception_message': str(exc),
        'traceback_summary': traceback.format_exc().splitlines()[-1] if traceback.format_exc() else '',
    }


def _validate_output(output, expected_shape, input_before, input_after):
    output = np.asarray(output)
    finite = bool(np.all(np.isfinite(output)))
    complex_ok = bool(np.iscomplexobj(output))
    shape_ok = output.shape == expected_shape
    unchanged = bool(np.array_equal(input_before, input_after))
    return {
        'output_shape': str(tuple(output.shape)),
        'expected_shape': str(tuple(expected_shape)),
        'shape_ok': shape_ok,
        'complex_dtype_ok': complex_ok,
        'finite_ok': finite,
        'input_unchanged': unchanged,
        'interface_status': 'PASS' if shape_ok and complex_ok and finite and unchanged else 'FAIL',
    }


def _call_algorithm(algorithm_name, adapter_name, radar_par, params, target_only=False):
    input_before = np.array(radar_par['Srt_matrix'], copy=True)
    started = time.perf_counter()
    tracemalloc.start()
    try:
        func = get_antijam_func(adapter_name)
        processed, processed_template = func(radar_par, **params)
        _, peak_memory = tracemalloc.get_traced_memory()
        output = np.asarray(processed)
        check = _validate_output(
            output,
            radar_par['Srt_matrix'].shape,
            input_before,
            radar_par['Srt_matrix'],
        )
        template = np.asarray(processed_template)
        check['template_finite_ok'] = bool(np.all(np.isfinite(template)))
        check['runtime_ms'] = (time.perf_counter() - started) * 1000.0
        check['memory_usage_bytes'] = int(peak_memory)
        check['algorithm'] = algorithm_name
        check['target_only'] = target_only
        check['output'] = output
        check['processed_template'] = template
        return check
    except Exception as exc:
        _, peak_memory = tracemalloc.get_traced_memory()
        result = {
            'algorithm': algorithm_name,
            'target_only': target_only,
            'interface_status': 'FAIL',
            'runtime_ms': (time.perf_counter() - started) * 1000.0,
            'memory_usage_bytes': int(peak_memory),
            'output': None,
            'processed_template': None,
        }
        result.update(_interface_error(exc))
        return result
    finally:
        tracemalloc.stop()


def _generate_case(jammer_name, config, seed):
    np.random.seed(seed)
    env = RadarEnvironment(config)
    template = env.generate_target_signal()
    jammer = JammerLoader.load(jammer_name)
    generated = jammer.generate(
        target_signal=template,
        config=config,
        jsr_db=config['JSR_dB'],
        seed=seed,
    )
    received = np.asarray(generated['received'], dtype=complex)
    target = np.asarray(generated['target'], dtype=complex)
    if received.shape != target.shape:
        raise ValueError(f'generated target/received shape mismatch: {target.shape} vs {received.shape}')
    return generated, template, received, target


def _case_row(base, result, role):
    row = dict(base)
    row.update({key: value for key, value in result.items() if key not in ('output', 'processed_template')})
    row['role'] = role
    return row


def _mean(values):
    values = [float(value) for value in values if value is not None and np.isfinite(value)]
    return float(np.mean(values)) if values else float('nan')


def _ci95(values):
    values = np.asarray([float(value) for value in values if value is not None and np.isfinite(value)])
    if len(values) < 2:
        return 0.0
    return float(1.96 * np.std(values, ddof=1) / np.sqrt(len(values)))


def _std(values):
    values = np.asarray([float(value) for value in values if value is not None and np.isfinite(value)])
    return float(np.std(values, ddof=1)) if len(values) > 1 else 0.0


def _performance_status(algorithm, jammer, valid_rows, identity_rows, interface_pass):
    if not interface_pass:
        return 'INTERFACE_FAIL'
    if algorithm == 'adapt_filter':
        return 'BLOCKED_ORACLE'
    if algorithm == 'FSTP':
        return 'NOT_APPLICABLE_MULTIPULSE'
    if not valid_rows:
        return 'INTERFACE_FAIL'

    delta = _mean([row['delta_sinr_db'] for row in valid_rows])
    delta_ci = _ci95([row['delta_sinr_db'] for row in valid_rows])
    pd_before = _mean([row['detected_before'] for row in identity_rows])
    pd_after = _mean([row['detected_after'] for row in valid_rows])
    target_change = _mean([row['target_only_response_change_db'] for row in valid_rows])
    false_before = _mean([row['false_peak_count_before'] for row in identity_rows])
    false_after = _mean([row['false_peak_count_after'] for row in valid_rows])
    error_before = _mean([row['peak_error_before'] for row in identity_rows])
    error_after = _mean([row['peak_error_after'] for row in valid_rows])

    if delta > 0.2 and delta - delta_ci >= 0 and pd_after >= pd_before and target_change > -1.0:
        return 'RECOMMENDED'
    if (false_after < false_before or error_after < error_before) and pd_after >= pd_before:
        return 'CONDITIONAL'
    if delta >= -0.2 and pd_after >= pd_before and target_change >= -1.0:
        return 'NEUTRAL'
    return 'HARMFUL'


def run_contract_matrix(output_dir, jsrs=(0.0, 10.0, 20.0, 30.0), seeds=range(42, 52)):
    output_dir = Path(output_dir)
    raw_interface = []
    case_metrics = []
    generation_failures = []

    for jammer_name, algorithm_name, adapter_name, params in PAIR_MATRIX:
        for jsr_db in jsrs:
            config = get_phase1_radar_params({'JSR_dB': jsr_db})
            for seed in seeds:
                base = {
                    'jammer': jammer_name,
                    'algorithm': algorithm_name,
                    'adapter': adapter_name,
                    'jsr_db': jsr_db,
                    'seed': seed,
                    'oracle_target_idx_passed': False,
                    'oracle_jammer_type_passed': False,
                    'oracle_true_jammer_signal_passed': False,
                }
                try:
                    generated, template, received, target = _generate_case(jammer_name, config, seed)
                    identity = {
                        'interface_status': 'PASS',
                        'output_shape': str(tuple(received[None, :].shape)),
                        'expected_shape': str(tuple(received[None, :].shape)),
                        'complex_dtype_ok': True,
                        'finite_ok': bool(np.all(np.isfinite(received))),
                        'input_unchanged': True,
                        'runtime_ms': 0.0,
                        'memory_usage_bytes': 0,
                        'output': received[None, :].copy(),
                        'processed_template': template,
                    }
                    radar_par = _whitelist_radar_par(config, received, template)
                    result = _call_algorithm(algorithm_name, adapter_name, radar_par, params)
                    target_par = _whitelist_radar_par(config, target, template)
                    target_result = _call_algorithm(algorithm_name, adapter_name, target_par, params, target_only=True)
                    interface_pass = (
                        result['interface_status'] == 'PASS'
                        and target_result['interface_status'] == 'PASS'
                        and result.get('template_finite_ok', True)
                        and target_result.get('template_finite_ok', True)
                    )
                    interface = _case_row(base, result, 'algorithm')
                    interface['target_only_interface_status'] = target_result['interface_status']
                    interface['interface_status'] = 'PASS' if interface_pass else 'FAIL'
                    if not interface_pass and result.get('interface_status') == 'PASS':
                        interface.update({
                            'exception_type': target_result.get('exception_type', ''),
                            'exception_message': target_result.get('exception_message', ''),
                            'traceback_summary': target_result.get('traceback_summary', ''),
                        })
                    raw_interface.append(interface)
                    raw_interface.append(_case_row(base, identity, 'identity'))

                    if interface_pass:
                        algorithm_metrics = evaluate_algorithm_output(
                            target, received, result['output'][0], config,
                            runtime_ms=result['runtime_ms'],
                            memory_usage_bytes=result['memory_usage_bytes'],
                        )
                        algorithm_metrics.update(evaluate_target_preservation(
                            target, target_result['output'][0], config,
                        ))
                        identity_metrics = evaluate_algorithm_output(
                            target, received, received, config,
                            runtime_ms=0.0, memory_usage_bytes=0,
                        )
                        identity_metrics.update(evaluate_target_preservation(target, target, config))
                        algorithm_metrics.update({
                            'jammer': jammer_name, 'algorithm': algorithm_name,
                            'jsr_db': jsr_db, 'seed': seed,
                            'detected_identity': identity_metrics['detected_before'],
                            'detected_algorithm': algorithm_metrics['detected_after'],
                            'sinr_identity_db': identity_metrics['sinr_before_db'],
                            'sinr_algorithm_db': algorithm_metrics['sinr_after_db'],
                            'delta_sinr_db': algorithm_metrics['sinr_after_db'] - identity_metrics['sinr_before_db'],
                            'peak_error_identity': identity_metrics['peak_error_before'],
                            'peak_error_algorithm': algorithm_metrics['peak_error_after'],
                            'false_peak_identity': identity_metrics['false_peak_count_before'],
                            'false_peak_algorithm': algorithm_metrics['false_peak_count_after'],
                            'interface_status': 'PASS',
                            'target_only_response_change_db': algorithm_metrics['target_only_response_change_db'],
                        })
                        # Re-evaluate algorithm output using the required identity baseline.
                        case_metrics.append(algorithm_metrics)
                    else:
                        case_metrics.append({
                            'jammer': jammer_name, 'algorithm': algorithm_name,
                            'jsr_db': jsr_db, 'seed': seed,
                            'interface_status': 'FAIL',
                        })
                except Exception as exc:
                    failure = dict(base)
                    failure.update({'interface_status': 'FAIL', 'role': 'generation', **_interface_error(exc)})
                    raw_interface.append(failure)
                    generation_failures.append(failure)
                    case_metrics.append({
                        'jammer': jammer_name, 'algorithm': algorithm_name,
                        'jsr_db': jsr_db, 'seed': seed,
                        'interface_status': 'FAIL',
                    })

    grouped = defaultdict(list)
    for row in case_metrics:
        grouped[(row['jammer'], row['algorithm'], row['jsr_db'])].append(row)
    interface_grouped = defaultdict(list)
    for row in raw_interface:
        interface_grouped[(row['jammer'], row['algorithm'], row['jsr_db'])].append(row)

    performance = []
    for (jammer, algorithm, jsr_db), rows in sorted(grouped.items()):
        interfaces = [
            row for row in interface_grouped[(jammer, algorithm, jsr_db)]
            if row.get('role') == 'algorithm'
        ]
        valid = [row for row in rows if row.get('interface_status') == 'PASS']
        identity_rows = [row for row in valid]
        interface_pass = len(interfaces) == len(list(seeds)) and all(row.get('interface_status') == 'PASS' for row in interfaces)
        status = _performance_status(algorithm, jammer, valid, identity_rows, interface_pass)
        performance.append({
            'jammer': jammer, 'algorithm': algorithm, 'jsr_db': jsr_db,
            'trials': len(list(seeds)),
            'interface_status': 'PASS' if interface_pass else 'FAIL',
            'performance_status': status,
            'delta_sinr_mean_db': _mean([row.get('delta_sinr_db') for row in valid]),
            'delta_sinr_std_db': _std([row.get('delta_sinr_db') for row in valid]),
            'delta_sinr_ci95_db': _ci95([row.get('delta_sinr_db') for row in valid]),
            'sinr_identity_mean_db': _mean([row.get('sinr_identity_db') for row in valid]),
            'sinr_algorithm_mean_db': _mean([row.get('sinr_algorithm_db') for row in valid]),
            'pd_identity': _mean([row.get('detected_identity') for row in valid]),
            'pd_algorithm': _mean([row.get('detected_algorithm') for row in valid]),
            'target_only_response_change_mean_db': _mean([row.get('target_only_response_change_db') for row in valid]),
            'target_only_response_change_ci95_db': _ci95([row.get('target_only_response_change_db') for row in valid]),
            'peak_error_identity_mean': _mean([row.get('peak_error_identity') for row in valid]),
            'peak_error_algorithm_mean': _mean([row.get('peak_error_algorithm') for row in valid]),
            'false_peak_identity_mean': _mean([row.get('false_peak_identity') for row in valid]),
            'false_peak_algorithm_mean': _mean([row.get('false_peak_algorithm') for row in valid]),
            'runtime_mean_ms': _mean([row.get('runtime_ms') for row in valid]),
            'memory_usage_bytes_mean': _mean([row.get('memory_usage_bytes') for row in valid]),
        })

    combined = list(performance)
    _write_csv(output_dir / 'interface_results.csv', raw_interface)
    _write_csv(output_dir / 'performance_results.csv', performance)
    _write_csv(output_dir / 'combined_results.csv', combined)

    interface_counts = Counter(row.get('interface_status') for row in raw_interface)
    performance_counts = Counter(row.get('performance_status') for row in performance)
    summary = {
        'interface_pass': interface_counts.get('PASS', 0),
        'interface_fail': interface_counts.get('FAIL', 0),
        'performance_counts': dict(performance_counts),
        'generation_failures': len(generation_failures),
        'case_count': len(case_metrics),
        'expected_case_count': len(PAIR_MATRIX) * len(tuple(jsrs)) * len(tuple(seeds)),
        'exit_code': 1 if interface_counts.get('FAIL', 0) or generation_failures else 0,
    }
    (output_dir / 'test_summary.json').parent.mkdir(parents=True, exist_ok=True)
    (output_dir / 'test_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def print_summary(summary):
    print('Interface Summary')
    print(f"PASS: {summary['interface_pass']}")
    print(f"FAIL: {summary['interface_fail']}")
    print('')
    print('Performance Summary')
    for status in ('RECOMMENDED', 'CONDITIONAL', 'NEUTRAL', 'HARMFUL', 'BLOCKED_ORACLE', 'NOT_APPLICABLE_MULTIPULSE', 'INTERFACE_FAIL'):
        print(f"{status}: {summary['performance_counts'].get(status, 0)}")
    print(f"Process Exit Code: {summary['exit_code']}")
