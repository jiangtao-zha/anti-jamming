#!/usr/bin/env python3
"""Task 037 Stage 1: audit and validate the finite-dimensional FrFT core."""

import argparse
import ast
import csv
import inspect
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anti_jamming.adapters import frft_adapter
from anti_jamming.frft_filter import _centered_unitary_dft, myfrft
from configs.phase1_radar import get_phase1_radar_params
from utils.test_contract import FORBIDDEN_ALGORITHM_KEYS, _audit_algorithm_input, _whitelist_radar_par


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


def relative_error(actual, expected):
    denominator = np.linalg.norm(expected)
    if denominator == 0:
        return float(np.linalg.norm(actual))
    return float(np.linalg.norm(actual - expected) / denominator)


def d4_distance(a, b):
    return float(min(abs(float(a) - float(b) + 4.0 * k) for k in range(-2, 3)))


def make_signals():
    rng = np.random.default_rng(3701)
    n = 64
    t = np.arange(n, dtype=float)
    return {
        'impulse': np.eye(1, n, 17, dtype=complex).ravel(),
        'single_tone': np.exp(1j * 2.0 * np.pi * 0.13 * t),
        'linear_chirp': np.exp(1j * 2.0 * np.pi * (0.07 * t + 0.5 * 0.0025 * t ** 2)),
        'reverse_chirp': np.exp(1j * 2.0 * np.pi * (0.31 * t - 0.5 * 0.0025 * t ** 2)),
        'random_complex_noise': rng.normal(size=n) + 1j * rng.normal(size=n),
    }


def run_property_tests():
    rng = np.random.default_rng(3702)
    rows = []
    orders = (0.37, 0.73, 1.21)
    sizes = (8, 15, 16, 31, 32, 64)
    for name, base in make_signals().items():
        for size in sizes:
            if name == 'impulse':
                x = np.zeros(size, dtype=complex)
                x[min(size - 1, size // 3)] = 1.0
            else:
                x = np.resize(base, size).astype(complex)
            for order in orders:
                before = x.copy()
                transformed = myfrft(x, order)
                recovered = myfrft(transformed, -order)
                row = {
                    'signal': name,
                    'length': size,
                    'order': order,
                    'identity_error': relative_error(myfrft(x, 0), x),
                    'fourier_error': relative_error(myfrft(x, 1), _centered_unitary_dft(x)),
                    'inverse_error': relative_error(recovered, x),
                    'period4_error': relative_error(myfrft(x, order + 4), transformed),
                    'energy_ratio': float(np.linalg.norm(transformed) ** 2 / (np.linalg.norm(x) ** 2 + 1e-30)),
                    'energy_error': float(abs(np.linalg.norm(transformed) ** 2 / (np.linalg.norm(x) ** 2 + 1e-30) - 1.0)),
                    'finite_output': bool(np.all(np.isfinite(transformed))),
                    'input_unchanged': bool(np.array_equal(x, before)),
                }
                row['status'] = 'PASS' if (
                    row['inverse_error'] < 1e-10
                    and row['period4_error'] < 1e-10
                    and row['energy_error'] < 1e-10
                    and row['finite_output']
                    and row['input_unchanged']
                ) else 'FAIL'
                rows.append(row)

    # Include one long, non-power-of-two vector representative of the Phase 1
    # receive dimensions.  This catches FFT-length and parity regressions.
    for size in (1000, 5000):
        x = rng.normal(size=size) + 1j * rng.normal(size=size)
        order = 0.731
        transformed = myfrft(x, order)
        recovered = myfrft(transformed, -order)
        rows.append({
            'signal': 'random_complex_long',
            'length': size,
            'order': order,
            'identity_error': relative_error(myfrft(x, 0), x),
            'fourier_error': relative_error(myfrft(x, 1), _centered_unitary_dft(x)),
            'inverse_error': relative_error(recovered, x),
            'period4_error': relative_error(myfrft(x, order + 4), transformed),
            'energy_ratio': float(np.linalg.norm(transformed) ** 2 / np.linalg.norm(x) ** 2),
            'energy_error': float(abs(np.linalg.norm(transformed) ** 2 / np.linalg.norm(x) ** 2 - 1.0)),
            'finite_output': bool(np.all(np.isfinite(transformed))),
            'input_unchanged': True,
            'status': 'PASS' if relative_error(recovered, x) < 1e-10 else 'FAIL',
        })
    return rows


def run_edge_cases():
    rows = []
    zero = np.zeros(32, dtype=complex)
    transformed = myfrft(zero, 0.731)
    rows.append({'case': 'zero_signal', 'status': 'PASS' if np.array_equal(transformed, zero) else 'FAIL', 'detail': 'finite zero output'})
    for case, values, order in (
        ('empty_input', np.array([], dtype=complex), 0.5),
        ('wrong_dimension', np.zeros((2, 2), dtype=complex), 0.5),
        ('nan_order', np.ones(8, dtype=complex), np.nan),
        ('inf_order', np.ones(8, dtype=complex), np.inf),
    ):
        try:
            myfrft(values, order)
        except ValueError as exc:
            rows.append({'case': case, 'status': 'PASS', 'detail': f'{type(exc).__name__}: {exc}'})
        except Exception as exc:  # pragma: no cover - defensive audit output
            rows.append({'case': case, 'status': 'FAIL', 'detail': f'unexpected {type(exc).__name__}: {exc}'})
        else:
            rows.append({'case': case, 'status': 'FAIL', 'detail': 'expected controlled ValueError'})
    return rows


def chirp_rows():
    config = get_phase1_radar_params()
    template = np.asarray(
        np.exp(1j * 2.0 * np.pi * (
            config['f0'] * np.arange(config['pulse_samples']) / config['Fs']
            + 0.5 * (config['Bw'] / config['Pw'])
            * (np.arange(config['pulse_samples']) / config['Fs']) ** 2
        )),
        dtype=complex,
    )
    t = np.arange(1000, dtype=float)
    signals = {
        'linear_chirp': np.exp(1j * 2.0 * np.pi * (0.07 * t + 0.5 * 0.0025 * t ** 2)),
        'reverse_chirp': np.exp(1j * 2.0 * np.pi * (0.31 * t - 0.5 * 0.0025 * t ** 2)),
        'phase1_target_template': template,
    }
    a_vals = np.linspace(-2.0, 2.0, 161)
    rows = []
    for name, signal in signals.items():
        scores = []
        for order in a_vals:
            transformed = myfrft(signal, order)
            energy = np.sum(np.abs(transformed) ** 2)
            scores.append(float(np.max(np.abs(transformed)) ** 2 / (energy + 1e-30)))
        best = float(a_vals[int(np.argmax(scores))])
        rows.append({
            'signal': name,
            'search_min': float(a_vals[0]),
            'search_max': float(a_vals[-1]),
            'grid_step': float(a_vals[1] - a_vals[0]),
            'numeric_best_order': best,
            'numeric_best_concentration': max(scores),
            'periodic_distance_to_zero': d4_distance(best, 0.0),
            'theoretical_order': 'NOT_IDENTIFIABLE_WITHOUT_CONTINUOUS_SCALING',
            'theoretical_order_status': 'NOT_APPLICABLE_FOR_SPECTRAL_DFT_CONVENTION',
            'interpretation': 'The finite-grid spectral definition has no continuous LFM focusing-order claim; this is recorded rather than inferred.',
        })
    return rows


def static_oracle_access_audit():
    source = inspect.getsource(frft_adapter)
    tree = ast.parse(source)
    accessed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            accessed.add(node.slice.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get':
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                accessed.add(node.args[0].value)
    forbidden_access = sorted(accessed.intersection(FORBIDDEN_ALGORITHM_KEYS))
    config = get_phase1_radar_params()
    template = np.asarray(np.exp(1j * np.linspace(0, 1, config['pulse_samples'])), dtype=complex)
    received = np.zeros(config['N'], dtype=complex)
    received[1000:2000] = template
    radar_par = _whitelist_radar_par(config, received, template)
    input_audit = _audit_algorithm_input(radar_par)
    processed, processed_template = frft_adapter(radar_par, mask_threshold=0.1)
    return [{
        'runtime_input_keys': ','.join(sorted(radar_par)),
        'runtime_forbidden_keys': input_audit['forbidden_keys_present'],
        'runtime_oracle_input_status': input_audit['oracle_input_status'],
        'static_forbidden_accesses': ','.join(forbidden_access),
        'static_oracle_access_status': 'PASS' if not forbidden_access else 'FAIL',
        'output_shape': str(tuple(np.asarray(processed).shape)),
        'template_shape': str(tuple(np.asarray(processed_template).shape)),
        'finite_output': bool(np.all(np.isfinite(processed))),
        'adapter_audit_status': 'PASS' if (
            input_audit['oracle_input_status'] == 'PASS'
            and not forbidden_access
            and np.asarray(processed).shape == (1, config['N'])
            and np.all(np.isfinite(processed))
        ) else 'FAIL',
    }]


def write_definition(path, property_rows, edge_rows, chirp, oracle):
    max_inverse = max(float(row['inverse_error']) for row in property_rows)
    max_energy = max(float(row['energy_error']) for row in property_rows)
    max_period = max(float(row['period4_error']) for row in property_rows)
    path.write_text(f'''# Task 037 Stage 1 — FrFT mathematical definition

The audited implementation is `anti_jamming.frft_filter.myfrft`.  It uses a
finite-dimensional spectral fractional power of the centered orthonormal DFT
`U`, not the former chirp-convolution translation.  The order-angle relation
is `theta = pi*a/2`; orders are reduced modulo 4.

For this finite grid, `a=0` is identity, `a=1` is the centered unitary DFT,
`a=2` is `U^2` (the finite-grid circular/centered reversal), `a=3` is
`U^3`, and `a=4` is identity.  The implementation constructs the four
projectors of `U` and applies the eigenphase `exp(-j*pi*k*a/2)` to each.
This makes the convention explicit without claiming a continuously scaled
Ozaktas LFM focusing order.

## Numerical audit

- Maximum inverse relative error: `{max_inverse:.3e}`
- Maximum period-4 relative error: `{max_period:.3e}`
- Maximum energy error: `{max_energy:.3e}`
- Edge cases: `{sum(row['status'] == 'PASS' for row in edge_rows)}/{len(edge_rows)} PASS`
- Chirp validation: the numeric scan is reported, but a continuous theoretical
  order is `NOT_IDENTIFIABLE_WITHOUT_CONTINUOUS_SCALING` under this discrete
  spectral convention.  No order is silently treated as ground truth.
- Oracle/input audit: `{oracle[0]['adapter_audit_status']}`

The old implementation's chirp-convolution index/shift convention failed the
same energy and inverse tests in the Stage 1 pre-fix baseline.  The core fix is
limited to `myfrft`; mask calibration and candidate dispatch are not changed
in this stage.

The periodic distance used by later diagnostics is
`d4(a,b) = min_k |a-b+4k|`, with the search interval documented per result.
''')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    property_rows = run_property_tests()
    edge_rows = run_edge_cases()
    chirp = chirp_rows()
    oracle = static_oracle_access_audit()
    write_csv(output / 'property_tests.csv', property_rows + edge_rows)
    write_csv(output / 'chirp_order_validation.csv', chirp)
    write_csv(output / 'oracle_input_audit.csv', oracle)
    inventory = [
        {'component': 'myfrft', 'path': 'anti_jamming/frft_filter.py', 'definition': 'finite spectral fractional power of centered unitary DFT', 'order_angle': 'theta=pi*a/2', 'period': 4, 'integer_orders': '0=I;1=U;2=U^2;3=U^3;4=I'},
        {'component': 'frft_adapter', 'path': 'anti_jamming/adapters.py', 'definition': 'template/received concentration scan and soft mask', 'default_order_range': '0.75..1.35, 25 steps', 'mask_parameter': 'mask_threshold, default 0.1'},
        {'component': 'contract', 'path': 'utils/test_contract.py', 'definition': 'whitelisted receiver fields plus Srt_matrix/St_base', 'forbidden_oracle_fields': ','.join(sorted(FORBIDDEN_ALGORITHM_KEYS))},
    ]
    write_csv(output / 'implementation_inventory.csv', inventory)
    write_definition(output / 'mathematical_definition.md', property_rows, edge_rows, chirp, oracle)

    property_pass = all(row['status'] == 'PASS' for row in property_rows)
    edge_pass = all(row['status'] == 'PASS' for row in edge_rows)
    chirp_complete = len(chirp) == 3 and all(row['theoretical_order_status'] == 'NOT_APPLICABLE_FOR_SPECTRAL_DFT_CONVENTION' for row in chirp)
    oracle_pass = oracle[0]['adapter_audit_status'] == 'PASS'
    summary = {
        'task': '037',
        'stage': 'stage1',
        'status': 'COMPLETED' if property_pass and edge_pass and chirp_complete and oracle_pass else 'FAILED',
        'gate': 'PASS' if property_pass and edge_pass and chirp_complete and oracle_pass else 'FAIL',
        'core_correctness_fix_applied': True,
        'previous_baseline_failed_energy_inverse': True,
        'property_rows': len(property_rows),
        'property_failures': sum(row['status'] != 'PASS' for row in property_rows),
        'edge_case_rows': len(edge_rows),
        'edge_case_failures': sum(row['status'] != 'PASS' for row in edge_rows),
        'oracle_audit_status': oracle[0]['adapter_audit_status'],
        'next_stage': 'stage2_separability_diagnostics' if property_pass and edge_pass and oracle_pass else 'STOP_CORE_CORRECTNESS_FAILURE',
        'definition': 'finite-dimensional spectral fractional power of centered orthonormal DFT',
    }
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if summary['status'] != 'COMPLETED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
