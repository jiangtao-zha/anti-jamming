"""Unified, oracle-aware evaluation contract for Phase 1 algorithms."""

import time

import numpy as np
from scipy import signal


def _full_target(target_signal, radar_config, length):
    target = np.asarray(target_signal, dtype=complex)
    if target.ndim != 1:
        raise ValueError('target_signal must be one-dimensional')
    if target.size == length:
        return target.copy()
    pulse_samples = int(radar_config['pulse_samples'])
    if target.size != pulse_samples:
        raise ValueError('target_signal must have N or pulse_samples samples')
    full = np.zeros(length, dtype=complex)
    start = int(radar_config['target_start_idx'])
    end = min(start + target.size, length)
    full[start:end] = target[:end - start]
    return full


def _local_template(target_signal, radar_config, length):
    target = np.asarray(target_signal, dtype=complex)
    if target.size == length:
        start = int(radar_config['target_start_idx'])
        pulse_samples = int(radar_config['pulse_samples'])
        return target[start:start + pulse_samples]
    return target


def _ca_cfar(magnitude, guard_cells, reference_cells, pfa):
    alpha = np.sqrt(-4.0 * np.log(pfa) / np.pi)
    kernel_size = 1 + 2 * guard_cells + 2 * reference_cells
    kernel = np.ones(kernel_size, dtype=float)
    center = reference_cells
    kernel[center:center + 2 * guard_cells + 1] = 0.0
    kernel /= 2.0 * reference_cells
    background = signal.correlate(magnitude, kernel, mode='same', method='fft')
    threshold = alpha * background
    return magnitude > threshold, threshold


def _profile(received, target):
    return np.abs(signal.fftconvolve(received, np.conj(target[::-1]), mode='same'))


def _peak_and_false_metrics(profile, reference_peak, guard_cells, reference_cells, pfa):
    detections, threshold = _ca_cfar(profile, guard_cells, reference_cells, pfa)
    target_half_width = max(10, guard_cells + 2)
    left = max(0, reference_peak - target_half_width)
    right = min(profile.size, reference_peak + target_half_width + 1)
    detected = bool(np.any(detections[left:right]))
    peak_index = int(np.argmax(profile))
    peak_error = abs(peak_index - reference_peak)

    outside = np.ones(profile.size, dtype=bool)
    outside[max(0, reference_peak - target_half_width):
            min(profile.size, reference_peak + target_half_width + 1)] = False
    false_profile = np.where(outside & detections, profile, 0.0)
    peaks, _ = signal.find_peaks(
        false_profile,
        height=threshold,
        distance=max(1, guard_cells),
    )
    false_peak_count = int(peaks.size)
    target_peak = float(np.max(profile[left:right]))
    max_false_peak = float(np.max(false_profile)) if false_peak_count else 0.0
    return {
        'detected': detected,
        'peak_index': peak_index,
        'peak_error': int(peak_error),
        'false_peak_count': false_peak_count,
        'true_false_peak_ratio': (
            max_false_peak / (target_peak + 1e-12)
        ),
        'max_false_peak_db': (
            20.0 * np.log10(max_false_peak / (target_peak + 1e-12))
            if max_false_peak > 0.0 else float('-inf')
        ),
        'target_peak': target_peak,
        'threshold': threshold,
    }


def evaluate_algorithm_output(
    target_signal,
    received_before,
    processed_after,
    radar_config,
    runtime_ms=None,
    memory_usage_bytes=None,
):
    """Evaluate before/after IQ without accepting jammer or target-index oracle.

    ``target_signal`` may be the local pulse template or a full receive-window
    target. The ideal target's own matched-filter peak supplies the reference
    index; callers do not pass ``target_idx``.
    """
    started = time.perf_counter()
    before = np.asarray(received_before, dtype=complex).reshape(-1)
    after = np.asarray(processed_after, dtype=complex).reshape(-1)
    if before.shape != after.shape:
        raise ValueError('before and after signals must have identical shape')
    if not np.all(np.isfinite(before)) or not np.all(np.isfinite(after)):
        raise ValueError('before or after contains NaN/Inf')

    target = _full_target(target_signal, radar_config, before.size)
    template = _local_template(target_signal, radar_config, before.size)
    reference_profile = _profile(target, template)
    reference_peak = int(np.argmax(reference_profile))
    before_profile = _profile(before, template)
    after_profile = _profile(after, template)

    guard_cells = int(radar_config.get('eval_guard_cells', 4))
    reference_cells = int(radar_config.get('eval_reference_cells', 20))
    pfa = float(radar_config.get('eval_pfa', 1e-4))
    before_metrics = _peak_and_false_metrics(
        before_profile, reference_peak, guard_cells, reference_cells, pfa
    )
    after_metrics = _peak_and_false_metrics(
        after_profile, reference_peak, guard_cells, reference_cells, pfa
    )

    target_window = max(10, guard_cells + 2)
    left = max(0, reference_peak - target_window)
    right = min(before_profile.size, reference_peak + target_window + 1)
    before_target_power = np.max(before_profile[left:right]) ** 2
    after_target_power = np.max(after_profile[left:right]) ** 2
    background_mask = np.ones(before_profile.size, dtype=bool)
    background_mask[max(0, reference_peak - reference_cells):
                    min(before_profile.size, reference_peak + reference_cells + 1)] = False
    before_background_power = np.mean(before_profile[background_mask] ** 2) + 1e-12
    after_background_power = np.mean(after_profile[background_mask] ** 2) + 1e-12
    sinr_before = 10.0 * np.log10(before_target_power / before_background_power)
    sinr_after = 10.0 * np.log10(after_target_power / after_background_power)
    target_peak_loss = 20.0 * np.log10(
        np.sqrt(after_target_power) / (np.sqrt(before_target_power) + 1e-12)
    )
    range_bin_m = float(radar_config['C']) / (2.0 * float(radar_config['Fs']))
    measured_runtime = (time.perf_counter() - started) * 1000.0

    return {
        'interface_ok': True,
        'sinr_before_db': float(sinr_before),
        'sinr_after_db': float(sinr_after),
        'delta_sinr_db': float(sinr_after - sinr_before),
        'detected_before': before_metrics['detected'],
        'detected_after': after_metrics['detected'],
        'peak_index_before': before_metrics['peak_index'],
        'peak_index_after': after_metrics['peak_index'],
        'peak_error_before': before_metrics['peak_error'],
        'peak_error_after': after_metrics['peak_error'],
        'range_error_before_m': before_metrics['peak_error'] * range_bin_m,
        'range_error_after_m': after_metrics['peak_error'] * range_bin_m,
        'target_peak_loss_db': float(target_peak_loss),
        'false_peak_count_before': before_metrics['false_peak_count'],
        'false_peak_count_after': after_metrics['false_peak_count'],
        'true_false_peak_ratio_before': before_metrics['true_false_peak_ratio'],
        'true_false_peak_ratio_after': after_metrics['true_false_peak_ratio'],
        'max_false_peak_db_before': before_metrics['max_false_peak_db'],
        'max_false_peak_db_after': after_metrics['max_false_peak_db'],
        'runtime_ms': float(
            measured_runtime if runtime_ms is None else runtime_ms
        ),
        'memory_usage_bytes': int(
            after.nbytes if memory_usage_bytes is None else memory_usage_bytes
        ),
        'reference_peak_index': reference_peak,
    }
