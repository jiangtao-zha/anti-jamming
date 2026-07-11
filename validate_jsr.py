#!/usr/bin/env python3
"""Validate the common Phase 1 jammer interface and JSR calibration."""

import csv
from pathlib import Path

import numpy as np

from configs.phase1_radar import get_phase1_radar_params
from unified_framework import JammerLoader, RadarEnvironment
from utils.jsr_validation import calculate_jsr, calculate_power


JAMMERS = [
    'FMZuse',
    'FMNoiseAimedJam',
    'FMNoiseSaopin',
    'AMNoiseGaiJam',
    'SMSP',
    'NoiseProductJamming',
    'NoiseConvolutionJamming',
]
REQUESTED_JSR = [0.0, 10.0, 20.0, 30.0]
SEEDS = list(range(42, 52))
OUTPUT_DIR = Path('results/phase1/jammer_validation')


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    params = get_phase1_radar_params()
    target = RadarEnvironment(params).generate_target_signal()
    rows = []
    power_rows = []
    failures = []
    representatives = {}

    for jammer_type in JAMMERS:
        for requested in REQUESTED_JSR:
            for seed in SEEDS:
                try:
                    jammer = JammerLoader.load(jammer_type)
                    output = jammer.generate(
                        target_signal=target,
                        config=params,
                        jsr_db=requested,
                        seed=seed,
                    )
                    measured = calculate_jsr(output['target'], output['jammer'])
                    error = measured - requested
                    raw = output['metadata']['raw_jammer']
                    scaled = output['metadata']['scaled_jammer']
                    normalized_correlation = abs(np.vdot(raw, scaled)) / (
                        np.linalg.norm(raw) * np.linalg.norm(scaled) + 1e-12
                    )
                    raw_spectrum = np.abs(np.fft.fft(raw))
                    scaled_spectrum = np.abs(np.fft.fft(scaled))
                    spectral_correlation = abs(np.vdot(
                        raw_spectrum, scaled_spectrum
                    )) / (
                        np.linalg.norm(raw_spectrum)
                        * np.linalg.norm(scaled_spectrum)
                        + 1e-12
                    )
                    rows.append({
                        'Jammer': jammer_type,
                        'Seed': seed,
                        'Requested JSR': requested,
                        'Measured JSR': measured,
                        'Error': error,
                    })
                    power_rows.append({
                        'Jammer': jammer_type,
                        'Seed': seed,
                        'Requested JSR': requested,
                        'Target Power': calculate_power(output['target']),
                        'Raw Jammer Power': calculate_power(raw),
                        'Scaled Jammer Power': calculate_power(scaled),
                        'Noise Power': calculate_power(output['noise']),
                        'Normalized Correlation': normalized_correlation,
                        'Spectrum Correlation': spectral_correlation,
                    })
                    if (jammer_type, requested) not in representatives:
                        representatives[(jammer_type, requested)] = output
                except Exception as exc:
                    failures.append({
                        'Jammer': jammer_type,
                        'Seed': seed,
                        'Requested JSR': requested,
                        'Error': repr(exc),
                    })

    with (OUTPUT_DIR / 'jsr_measurement.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with (OUTPUT_DIR / 'power_statistics.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=power_rows[0].keys())
        writer.writeheader()
        writer.writerows(power_rows)
    with (OUTPUT_DIR / 'failed_cases.csv').open('w', newline='') as handle:
        fieldnames = ['Jammer', 'Seed', 'Requested JSR', 'Error']
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(failures)

    # Preserve both raw and scaled waveforms for one representative per jammer.
    for jammer_type in JAMMERS:
        output = representatives[(jammer_type, 20.0)]
        np.savez_compressed(
            OUTPUT_DIR / f'{jammer_type}_seed42_jsr20.npz',
            raw_jammer=output['metadata']['raw_jammer'],
            scaled_jammer=output['metadata']['scaled_jammer'],
            target=output['target'],
            noise=output['noise'],
        )

    errors = np.asarray([abs(float(row['Error'])) for row in rows])
    print(f'cases={len(rows)} failures={len(failures)}')
    print(f'max_abs_jsr_error_db={errors.max():.12f}')
    print(f'pass_under_0.2db={bool(len(failures) == 0 and np.all(errors < 0.2))}')
    if failures:
        for failure in failures:
            print(failure)
    if failures or not np.all(errors < 0.2):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
