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

FORBIDDEN_ALGORITHM_KEYS = frozenset({
    'target_idx', 'target_start_idx', 'target_dist', 'target_range',
    'jammer_type', 'jam_info', 'true_jammer_signal', 'jammer_signal',
    'requested_jsr_db', 'measured_jsr_db', 'jsr_status',
})

PHASE1_JAMMERS = (
    'FMZuse', 'FMNoiseAimedJam', 'FMNoiseSaopin', 'AMNoiseGaiJam',
    'SMSP', 'NoiseProductJamming', 'NoiseConvolutionJamming',
)


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
    allowed = ('C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N')
    radar_par = {key: config[key] for key in allowed if key in config}
    radar_par['Srt_matrix'] = np.asarray(received, dtype=complex)[None, :]
    radar_par['St_base'] = np.asarray(template, dtype=complex).copy()
    return radar_par


def _audit_algorithm_input(radar_par):
    forbidden = sorted(FORBIDDEN_ALGORITHM_KEYS.intersection(radar_par))
    return {
        'forbidden_keys_present': ','.join(forbidden),
        'oracle_input_status': 'PASS' if not forbidden else 'FAIL',
    }


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
    audit = _audit_algorithm_input(radar_par)
    if audit['oracle_input_status'] != 'PASS':
        return {
            'algorithm': algorithm_name,
            'target_only': target_only,
            'interface_status': 'FAIL',
            'failure_reason': 'ORACLE_INPUT_LEAK',
            'call_attempted': False,
            **audit,
            'runtime_ms': 0.0,
            'memory_usage_bytes': 0,
            'output': None,
            'processed_template': None,
        }
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
        check['call_attempted'] = True
        check.update(audit)
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
            'call_attempted': True,
        }
        result.update(audit)
        result.update(_interface_error(exc))
        return result
    finally:
        tracemalloc.stop()


def _generate_case(jammer_name, config, seed):
    np.random.seed(seed)
    env = RadarEnvironment(config)
    template = env.generate_target_signal()
    if jammer_name == 'NoJammer':
        radar = env.generate_without_jammer(noise_level=np.sqrt(config.get('noise_var', 0.1)))
        pulse = int(config['pulse_samples'])
        target = np.zeros(int(config['N']), dtype=complex)
        start = int(config['target_start_idx'])
        target[start:start + pulse] = template[:min(pulse, target.size - start)]
        received = np.asarray(radar['Srt_matrix'][0], dtype=complex)
        return {
            'target': target,
            'jammer': np.zeros_like(target),
            'noise': received - target,
            'received': received,
            'requested_jsr_db': None,
            'measured_jsr_db': None,
            'jsr_status': 'no-jammer/not-applicable',
            'jammer_contract_status': 'NO_JAMMER_NOT_APPLICABLE',
            'legacy_components_available': False,
            'metadata': {'jammer_type': 'NoJammer'},
        }, template, received, target
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


def _jammer_contract(generated, requested_jsr_db):
    if generated.get('jammer_contract_status') == 'NO_JAMMER_NOT_APPLICABLE':
        return {
            'jammer_contract_status': 'NO_JAMMER_NOT_APPLICABLE',
            'jammer_comparable': False,
            'requested_jsr_db': None,
            'measured_jsr_db': None,
            'jsr_error_db': None,
            'jsr_status': 'no-jammer/not-applicable',
            'legacy_components_available': False,
        }
    metadata = generated.get('metadata') or {}
    requested = generated.get('requested_jsr_db', requested_jsr_db)
    measured = generated.get('measured_jsr_db')
    legacy = generated.get('legacy_components_available', metadata.get('legacy_components_available', True))
    jsr_status = generated.get('jsr_status', metadata.get('jsr_status', ''))
    try:
        requested = float(requested)
    except (TypeError, ValueError):
        requested = None
    try:
        measured = float(measured)
    except (TypeError, ValueError):
        measured = None
    error = measured - requested if measured is not None and requested is not None and np.isfinite(measured) else None
    if 'legacy' in str(jsr_status).lower() or not legacy or measured is None:
        status = 'LEGACY_JSR_BLOCKED'
        comparable = False
    elif (
        not np.isfinite(requested)
        or not np.isfinite(measured)
        or error is None
        or abs(error) > 0.1
    ):
        status = 'GENERATION_FAIL'
        comparable = False
    else:
        status = 'UNIFIED_JSR_PASS'
        comparable = True
    return {
        'jammer_contract_status': status,
        'jammer_comparable': comparable,
        'requested_jsr_db': requested,
        'measured_jsr_db': measured,
        'jsr_error_db': error,
        'jsr_status': jsr_status or ('unified/pass' if comparable else ''),
        'legacy_components_available': bool(legacy),
    }


def _case_row(base, result, role):
    row = dict(base)
    row.update({key: value for key, value in result.items() if key not in ('output', 'processed_template')})
    row['role'] = role
    return row


def _aggregate_target_preservation_status(rows):
    statuses = {row.get('target_preservation_status') for row in rows}
    if 'TARGET_ERASED' in statuses:
        return 'TARGET_ERASED'
    if 'TARGET_ATTENUATED' in statuses:
        return 'TARGET_ATTENUATED'
    return 'TARGET_PRESERVED'


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


def _performance_status(algorithm, jammer, valid_rows, identity_rows, interface_pass, jammer_contract_status, radar_config):
    if not interface_pass:
        return 'INTERFACE_FAIL'
    if algorithm == 'adapt_filter':
        return 'BLOCKED_ORACLE'
    if algorithm == 'FSTP' and int(radar_config.get('M', 1)) < 2:
        return 'NOT_APPLICABLE_MULTIPULSE'
    if jammer_contract_status != 'UNIFIED_JSR_PASS':
        return 'BLOCKED_JAMMER_CONTRACT'
    if not valid_rows:
        return 'INTERFACE_FAIL'

    delta = _mean([row['delta_sinr_db'] for row in valid_rows])
    delta_ci = _ci95([row['delta_sinr_db'] for row in valid_rows])
    pd_before = _mean([row['detected_before'] for row in identity_rows])
    pd_after = _mean([row['detected_after'] for row in valid_rows])
    target_change = _mean([row['target_only_response_change_db'] for row in valid_rows])
    target_erased = any(row.get('target_preservation_status') == 'TARGET_ERASED' for row in valid_rows)
    false_before = _mean([row['false_peak_count_before'] for row in identity_rows])
    false_after = _mean([row['false_peak_count_after'] for row in valid_rows])
    error_before = _mean([row['peak_error_before'] for row in identity_rows])
    error_after = _mean([row['peak_error_after'] for row in valid_rows])

    if target_erased:
        return 'HARMFUL'
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
                    base.update(_jammer_contract(generated, jsr_db))
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
                    base.update({
                        'oracle_input_status': result.get('oracle_input_status', 'PASS'),
                        'forbidden_keys_present': result.get('forbidden_keys_present', ''),
                    })
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
                            **{key: base.get(key) for key in (
                                'jammer_contract_status', 'jammer_comparable',
                                'requested_jsr_db', 'measured_jsr_db', 'jsr_error_db',
                                'jsr_status', 'legacy_components_available',
                            )},
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
                            'oracle_input_status': result.get('oracle_input_status', 'FAIL'),
                            'forbidden_keys_present': result.get('forbidden_keys_present', ''),
                        })
                        # Re-evaluate algorithm output using the required identity baseline.
                        case_metrics.append(algorithm_metrics)
                    else:
                        case_metrics.append({
                            'jammer': jammer_name, 'algorithm': algorithm_name,
                            'jsr_db': jsr_db, 'seed': seed,
                            'interface_status': 'FAIL',
                            **base,
                        })
                except Exception as exc:
                    failure = dict(base)
                    failure.update({
                        'interface_status': 'FAIL', 'role': 'generation',
                        'jammer_contract_status': 'GENERATION_FAIL',
                        'jammer_comparable': False,
                        **_interface_error(exc),
                    })
                    base.update({
                        'jammer_contract_status': 'GENERATION_FAIL',
                        'jammer_comparable': False,
                        'oracle_input_status': 'PASS',
                    })
                    raw_interface.append(failure)
                    generation_failures.append(failure)
                    case_metrics.append({
                        'jammer': jammer_name, 'algorithm': algorithm_name,
                        'jsr_db': jsr_db, 'seed': seed,
                        'interface_status': 'FAIL',
                        **base,
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
        statuses = {row.get('jammer_contract_status') for row in rows}
        contract_status = next(iter(statuses)) if len(statuses) == 1 else 'GENERATION_FAIL'
        radar_config = get_phase1_radar_params({'JSR_dB': jsr_db})
        status = _performance_status(
            algorithm, jammer, valid, identity_rows, interface_pass,
            contract_status, radar_config,
        )
        jammer_comparable = contract_status == 'UNIFIED_JSR_PASS'
        fair_eligible = jammer_comparable and status in {
            'RECOMMENDED', 'CONDITIONAL', 'NEUTRAL', 'HARMFUL'
        }
        performance.append({
            'jammer': jammer, 'algorithm': algorithm, 'jsr_db': jsr_db,
            'trials': len(list(seeds)),
            'interface_status': 'PASS' if interface_pass else 'FAIL',
            'performance_status': status,
            'jammer_contract_status': contract_status,
            'jammer_comparable': jammer_comparable,
            'fair_ranking_eligible': fair_eligible,
            'exploratory_only': not jammer_comparable,
            'requested_jsr_db': _mean([row.get('requested_jsr_db') for row in rows]),
            'measured_jsr_db': _mean([row.get('measured_jsr_db') for row in rows]),
            'jsr_error_db': _mean([row.get('jsr_error_db') for row in rows]),
            'jsr_status': ','.join(sorted({str(row.get('jsr_status', '')) for row in rows})),
            'legacy_components_available': all(row.get('legacy_components_available', False) for row in rows),
            'oracle_input_status': ','.join(sorted({str(row.get('oracle_input_status', '')) for row in valid})),
            'forbidden_keys_present': ','.join(sorted({str(row.get('forbidden_keys_present', '')) for row in valid if row.get('forbidden_keys_present')})),
            'delta_sinr_mean_db': _mean([row.get('delta_sinr_db') for row in valid]),
            'delta_sinr_std_db': _std([row.get('delta_sinr_db') for row in valid]),
            'delta_sinr_ci95_db': _ci95([row.get('delta_sinr_db') for row in valid]),
            'sinr_identity_mean_db': _mean([row.get('sinr_identity_db') for row in valid]),
            'sinr_algorithm_mean_db': _mean([row.get('sinr_algorithm_db') for row in valid]),
            'pd_identity': _mean([row.get('detected_identity') for row in valid]),
            'pd_algorithm': _mean([row.get('detected_algorithm') for row in valid]),
            'target_only_response_change_mean_db': _mean([row.get('target_only_response_change_db') for row in valid]),
            'target_only_response_change_ci95_db': _ci95([row.get('target_only_response_change_db') for row in valid]),
            'target_preservation_status': _aggregate_target_preservation_status(valid),
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
    _write_csv(output_dir / 'jammer_contract_results.csv', performance)
    _write_csv(output_dir / 'fair_ranking_results.csv', [row for row in performance if row['fair_ranking_eligible']])

    interface_counts = Counter(row.get('interface_status') for row in raw_interface)
    performance_counts = Counter(row.get('performance_status') for row in performance)
    summary = {
        'interface_pass': interface_counts.get('PASS', 0),
        'interface_fail': interface_counts.get('FAIL', 0),
        'performance_counts': dict(performance_counts),
        'generation_failures': len(generation_failures),
        'case_count': len(case_metrics),
        'expected_case_count': len(PAIR_MATRIX) * len(tuple(jsrs)) * len(tuple(seeds)),
        'interface_failures': sum(
            row.get('interface_status') == 'FAIL' and row.get('role') == 'algorithm'
            for row in raw_interface
        ),
        'generation_exceptions': len(generation_failures),
        'contract_generation_failures': sum(
            row.get('jammer_contract_status') == 'GENERATION_FAIL'
            for row in performance
        ),
        'oracle_input_failures': sum(
            row.get('oracle_input_status') == 'FAIL'
            for row in raw_interface
            if row.get('role') == 'algorithm'
        ),
        'correctness_failures': 0,
        'exit_code': 1 if (
            interface_counts.get('FAIL', 0)
            or generation_failures
            or any(row.get('jammer_contract_status') == 'GENERATION_FAIL' for row in performance)
            or any(row.get('oracle_input_status') == 'FAIL' for row in raw_interface)
        ) else 0,
        'jammer_contract_counts': dict(Counter(row.get('jammer_contract_status') for row in performance)),
        'fair_ranking_eligible_count': sum(row['fair_ranking_eligible'] for row in performance),
        'forbidden_input_failures': sum(row.get('oracle_input_status') == 'FAIL' for row in raw_interface),
    }
    (output_dir / 'test_summary.json').parent.mkdir(parents=True, exist_ok=True)
    (output_dir / 'test_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def run_correctness_regression(output_dir):
    """Run fast loader/adapter/regression checks without performance ranking."""
    output_dir = Path(output_dir)
    loader_rows = []
    adapter_rows = []
    no_jammer_rows = []
    boundary_rows = []
    config = get_phase1_radar_params({'JSR_dB': 10.0})

    loader_names = PHASE1_JAMMERS + ('ISDJ', 'SliceCombineJam', 'NoJammer')
    for name in loader_names:
        row = {'jammer': name, 'status': 'PASS'}
        try:
            generated, template, received, target = _generate_case(name, config, 42)
            contract = _jammer_contract(generated, 10.0)
            row.update(contract)
            row.update({
                'received_shape': str(received.shape),
                'target_shape': str(target.shape),
                'finite': bool(np.all(np.isfinite(received))),
            })
            if received.shape != target.shape or not row['finite']:
                row.update({'status': 'FAIL', 'failure_reason': 'SHAPE_OR_FINITE'})
        except Exception as exc:
            row.update({'status': 'FAIL', 'failure_reason': 'LOADER_SMOKE', **_interface_error(exc)})
        loader_rows.append(row)

    for jammer_name, algorithm_name, adapter_name, params in PAIR_MATRIX:
        row = {'algorithm': algorithm_name, 'adapter': adapter_name, 'status': 'PASS'}
        try:
            generated, template, received, target = _generate_case(jammer_name, config, 42)
            radar_par = _whitelist_radar_par(config, received, template)
            result = _call_algorithm(algorithm_name, adapter_name, radar_par, params)
            target_par = _whitelist_radar_par(config, target, template)
            target_result = _call_algorithm(algorithm_name, adapter_name, target_par, params, target_only=True)
            row.update({
                'interface_status': result.get('interface_status'),
                'target_only_interface_status': target_result.get('interface_status'),
                'oracle_input_status': result.get('oracle_input_status'),
                'forbidden_keys_present': result.get('forbidden_keys_present', ''),
                'target_only_response_change_db': None,
            })
            if result.get('interface_status') != 'PASS' or target_result.get('interface_status') != 'PASS':
                row.update({'status': 'FAIL', 'failure_reason': 'ADAPTER_SMOKE'})
            elif result.get('oracle_input_status') != 'PASS' or target_result.get('oracle_input_status') != 'PASS':
                row.update({'status': 'FAIL', 'failure_reason': 'ORACLE_INPUT_LEAK'})
            else:
                row['target_only_response_change_db'] = evaluate_target_preservation(
                    target, target_result['output'][0], config,
                )['target_only_response_change_db']
        except Exception as exc:
            row.update({'status': 'FAIL', 'failure_reason': 'ADAPTER_SMOKE', **_interface_error(exc)})
        adapter_rows.append(row)

    try:
        generated, template, received, target = _generate_case('NoJammer', config, 42)
        for _, algorithm_name, adapter_name, params in PAIR_MATRIX:
            row = {'algorithm': algorithm_name, 'status': 'PASS'}
            radar_par = _whitelist_radar_par(config, received, template)
            result = _call_algorithm(algorithm_name, adapter_name, radar_par, params)
            row.update({
                'interface_status': result.get('interface_status'),
                'target_only_response_change_db': None,
            })
            if result.get('interface_status') != 'PASS':
                row.update({'status': 'FAIL', 'failure_reason': 'NO_JAMMER_INTERFACE'})
            else:
                row['target_only_response_change_db'] = evaluate_target_preservation(
                    target, result['output'][0], config,
                )['target_only_response_change_db']
            no_jammer_rows.append(row)
    except Exception as exc:
        no_jammer_rows.append({'algorithm': 'all', 'status': 'FAIL', **_interface_error(exc)})

    boundary_inputs = {
        'empty_iq': np.empty((1, 0), dtype=complex),
        'wrong_shape_iq': np.zeros((2, 17), dtype=complex),
        'nan_iq': np.full((1, int(config['N'])), np.nan + 0j, dtype=complex),
    }
    for case_name, invalid_iq in boundary_inputs.items():
        for _, algorithm_name, adapter_name, params in PAIR_MATRIX:
            radar_par = _whitelist_radar_par(config, invalid_iq, template)
            result = _call_algorithm(algorithm_name, adapter_name, radar_par, params)
            boundary_rows.append({
                'case': case_name,
                'algorithm': algorithm_name,
                'call_attempted': result.get('call_attempted', False),
                'interface_status': result.get('interface_status', 'FAIL'),
                'exception_type': result.get('exception_type', ''),
                'failure_reason': result.get('failure_reason', ''),
                'status': 'PASS' if result.get('call_attempted') else 'FAIL',
            })

    invalid_param_result = _call_algorithm(
        'FDC', 'FrequencyDomainCanceller',
        _whitelist_radar_par(config, received, template),
        {'cancellation_strength': float('nan')},
    )
    boundary_rows.extend([
        {'case': 'forbidden_key_audit', 'status': 'PASS' if _audit_algorithm_input({'target_dist': 1})['oracle_input_status'] == 'FAIL' else 'FAIL'},
        {'case': 'invalid_parameter_rejected', 'status': 'PASS' if invalid_param_result['interface_status'] == 'FAIL' else 'FAIL'},
        {'case': 'FSTP_M1_status', 'status': 'PASS' if _performance_status(
            'FSTP', 'SMSP', [], [], True, 'UNIFIED_JSR_PASS', config
        ) == 'NOT_APPLICABLE_MULTIPULSE' else 'FAIL'},
    ])

    _write_csv(output_dir / 'loader_smoke.csv', loader_rows)
    _write_csv(output_dir / 'adapter_smoke.csv', adapter_rows)
    _write_csv(output_dir / 'no_jammer_regression.csv', no_jammer_rows)
    _write_csv(output_dir / 'parameter_boundary.csv', boundary_rows)
    failures = sum(row.get('status') == 'FAIL' for rows in (loader_rows, adapter_rows, no_jammer_rows, boundary_rows) for row in rows)
    summary = {
        'loader_cases': len(loader_rows),
        'adapter_cases': len(adapter_rows),
        'no_jammer_cases': len(no_jammer_rows),
        'boundary_cases': len(boundary_rows),
        'boundary_call_attempts': sum(row.get('call_attempted', False) for row in boundary_rows),
        'correctness_failures': failures,
        'failures': failures,
        'exit_code': 1 if failures else 0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'correctness_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def print_summary(summary):
    print('Interface Summary')
    print(f"PASS: {summary['interface_pass']}")
    print(f"FAIL: {summary['interface_fail']}")
    print('')
    print('Performance Summary')
    for status in ('RECOMMENDED', 'CONDITIONAL', 'NEUTRAL', 'HARMFUL', 'BLOCKED_ORACLE', 'BLOCKED_JAMMER_CONTRACT', 'NOT_APPLICABLE_MULTIPULSE', 'INTERFACE_FAIL'):
        print(f"{status}: {summary['performance_counts'].get(status, 0)}")
    print(f"Process Exit Code: {summary['exit_code']}")
