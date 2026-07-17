"""Observable-only adapt-filter research prototypes for Task 036.

The legacy implementation in :mod:`anti_jamming.adapt_filter` is intentionally
untouched. These prototypes accept only the public radar configuration, the
known local transmit template, and observed IQ. Target position is estimated
from the observation and is never accepted as an input field.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal


FORBIDDEN_KEYS = frozenset({
    'target_idx', 'target_start_idx', 'target_dist', 'target_range',
    'jammer_type', 'jam_info', 'true_jammer_signal', 'jammer_signal',
    'requested_jsr_db', 'measured_jsr_db', 'jsr_status',
})
ALLOWED_CONFIG_KEYS = frozenset({
    'C', 'f0', 'Bw', 'Pw', 'Fs', 'Tr', 'M', 'N',
})


def _validate_inputs(observed_iq: Any, template: Any, radar_params: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    if not isinstance(radar_params, dict):
        raise TypeError('radar_params must be a dictionary')
    forbidden = sorted(FORBIDDEN_KEYS.intersection(radar_params))
    if forbidden:
        raise ValueError(f'forbidden oracle keys present: {forbidden}')
    unknown = sorted(set(radar_params) - ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ValueError(f'unapproved radar parameter keys present: {unknown}')
    received = np.asarray(observed_iq, dtype=complex)
    if received.ndim == 1:
        received = received[None, :]
    if received.ndim != 2 or received.shape[0] < 1 or received.shape[1] < 1:
        raise ValueError('observed_iq must be a non-empty 1D/2D complex array')
    local_template = np.asarray(template, dtype=complex).reshape(-1)
    if local_template.size < 1:
        raise ValueError('template must be non-empty')
    if local_template.size > received.shape[1]:
        raise ValueError('template cannot be longer than observed IQ')
    if not np.all(np.isfinite(received)) or not np.all(np.isfinite(local_template)):
        raise ValueError('observed_iq and template must be finite')
    if np.linalg.norm(local_template) <= 1e-12:
        raise ValueError('template has zero energy')
    return received, local_template, dict(radar_params)


def _valid_center_bounds(n_samples: int, template_length: int) -> tuple[int, int]:
    half = template_length // 2
    return half, n_samples - (template_length - half)


def _aligned_template(template: np.ndarray, n_samples: int, center: int) -> np.ndarray:
    vector = np.zeros(n_samples, dtype=complex)
    start = max(0, int(center) - template.size // 2)
    end = min(n_samples, start + template.size)
    if end > start:
        vector[start:end] = template[:end - start]
    return vector


def _aggregate_matched_response(received: np.ndarray, template: np.ndarray) -> np.ndarray:
    correlations = [
        signal.fftconvolve(row, np.conj(template[::-1]), mode='same')
        for row in received
    ]
    return np.mean(np.abs(np.asarray(correlations)), axis=0)


def _candidate_centers(response: np.ndarray, template_length: int, top_k: int, separation: int) -> list[int]:
    low, high = _valid_center_bounds(response.size, template_length)
    if high < low:
        raise ValueError('no valid template placement in observed IQ')
    clipped = np.asarray(response, dtype=float).copy()
    clipped[:low] = 0.0
    clipped[high + 1:] = 0.0
    peaks, properties = signal.find_peaks(
        clipped,
        distance=max(1, int(separation)),
        prominence=max(float(np.max(clipped)) * 1e-6, 1e-12),
    )
    if peaks.size == 0:
        peaks = np.asarray([int(np.argmax(clipped))], dtype=int)
        peak_scores = clipped[peaks]
    else:
        peak_scores = properties.get('prominences', clipped[peaks])
    order = np.argsort(clipped[peaks])[::-1]
    selected: list[int] = []
    for index in order:
        center = int(peaks[index])
        if all(abs(center - previous) >= max(1, int(separation)) for previous in selected):
            selected.append(center)
        if len(selected) >= max(1, int(top_k)):
            break
    if not selected:
        selected = [int(np.argmax(clipped))]
    return selected


def _projection_output(received: np.ndarray, template_vector: np.ndarray, regularization: float) -> tuple[np.ndarray, float, float]:
    energy = float(np.vdot(template_vector, template_vector).real)
    if not np.isfinite(energy) or energy <= 1e-12:
        raise ValueError('aligned template has zero/non-finite energy')
    denominator = energy + max(0.0, float(regularization))
    coefficient = (received @ template_vector.conj()) / denominator
    output = coefficient[:, None] * template_vector[None, :]
    condition_number = float((energy + max(0.0, float(regularization))) / energy)
    return output, condition_number, energy


def _candidate_diagnostics(response: np.ndarray, candidates: list[int]) -> list[dict]:
    scale = float(np.median(response) + 1e-12)
    maximum = float(np.max(response) + 1e-12)
    diagnostics = []
    for center in candidates:
        score = float(response[center] / scale)
        diagnostics.append({
            'center': int(center),
            'matched_response': float(response[center]),
            'relative_score': score,
            'normalized_peak': float(response[center] / maximum),
        })
    diagnostics.sort(key=lambda item: item['relative_score'], reverse=True)
    return diagnostics


def _identity_model(status: str, diagnostics: dict, regularization: float) -> dict:
    return {
        'estimated_target_idx': None,
        'estimator_confidence': 0.0,
        'filter_coefficients': None,
        'condition_number': 1.0,
        'regularization': float(regularization),
        'fit_status': status,
        'diagnostics': diagnostics,
        'fallback': 'Identity',
    }


def _model_for_center(received: np.ndarray, template: np.ndarray, center: int, regularization: float) -> dict:
    vector = _aligned_template(template, received.shape[1], center)
    _, condition_number, energy = _projection_output(received, vector, regularization)
    return {
        'estimated_target_idx': int(center),
        'filter_coefficients': vector,
        'condition_number': condition_number,
        'regularization': float(regularization),
        'template_energy': energy,
    }


def fit_adapt_filter_fair(
    observed_iq: Any,
    template: Any,
    radar_params: dict,
    *,
    top_k: int = 5,
    confidence_threshold: float = 0.12,
    candidate_separation: int | None = None,
    regularization: float = 0.01,
) -> dict:
    """Prototype A: estimate one observable delay and protect its template.

    Confidence is a normalized margin over the observable matched-filter
    candidates. The true target index is not accepted or inferred from any
    forbidden field.
    """
    received, local_template, _ = _validate_inputs(observed_iq, template, radar_params)
    if top_k < 1 or not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError('top_k/confidence_threshold out of range')
    separation = candidate_separation or max(4, local_template.size // 8)
    response = _aggregate_matched_response(received, local_template)
    candidates = _candidate_centers(response, local_template.size, top_k, separation)
    candidate_info = _candidate_diagnostics(response, candidates)
    best = candidate_info[0]
    second = candidate_info[1]['relative_score'] if len(candidate_info) > 1 else 0.0
    margin_confidence = float((best['relative_score'] - second) / (best['relative_score'] + 1e-12))
    peak_confidence = float(best['normalized_peak'])
    confidence = float(np.clip(0.5 * margin_confidence + 0.5 * peak_confidence, 0.0, 1.0))
    diagnostics = {
        'method': 'matched_filter_top_k_peak_margin',
        'candidate_count': len(candidate_info),
        'topk_candidates': candidate_info,
        'margin_confidence': margin_confidence,
        'peak_confidence': peak_confidence,
        'candidate_separation': int(separation),
    }
    if confidence < confidence_threshold:
        return _identity_model('FALLBACK_IDENTITY_LOW_CONFIDENCE', diagnostics, regularization)
    try:
        model = _model_for_center(received, local_template, int(best['center']), regularization)
    except (ValueError, FloatingPointError) as exc:
        diagnostics['fit_error'] = str(exc)
        return _identity_model('FALLBACK_IDENTITY_NUMERICAL', diagnostics, regularization)
    model.update({
        'estimator_confidence': confidence,
        'fit_status': 'FITTED_TOPK_PROTECTED_PROJECTION',
        'diagnostics': diagnostics,
        'fallback': None,
    })
    return model


def fit_adapt_filter_fair_multihypothesis(
    observed_iq: Any,
    template: Any,
    radar_params: dict,
    *,
    top_k: int = 5,
    confidence_threshold: float = 0.08,
    candidate_separation: int | None = None,
    regularization: float = 0.01,
) -> dict:
    """Prototype B: fit multiple protected hypotheses and select observably.

    Each candidate is processed with the same protected template projection.
    Selection uses only the candidate's post-filter matched response and local
    off-candidate suppression proxy, never evaluation truth.
    """
    received, local_template, _ = _validate_inputs(observed_iq, template, radar_params)
    if top_k < 1 or not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError('top_k/confidence_threshold out of range')
    separation = candidate_separation or max(4, local_template.size // 8)
    response = _aggregate_matched_response(received, local_template)
    candidates = _candidate_centers(response, local_template.size, top_k, separation)
    candidate_models = []
    candidate_scores = []
    for center in candidates:
        model = _model_for_center(received, local_template, center, regularization)
        output, _, _ = _projection_output(received, model['filter_coefficients'], regularization)
        output_response = _aggregate_matched_response(output, local_template)
        local_left = max(0, center - max(4, local_template.size // 20))
        local_right = min(output_response.size, center + max(4, local_template.size // 20) + 1)
        local_peak = float(np.max(output_response[local_left:local_right]))
        outside = np.ones(output_response.size, dtype=bool)
        outside[local_left:local_right] = False
        off_peak = float(np.max(output_response[outside])) if np.any(outside) else 0.0
        stability = float(local_peak / (off_peak + 1e-12))
        observable_score = float(
            math.log1p(max(0.0, stability))
            + 0.25 * math.log1p(max(0.0, response[center]))
        )
        model['observable_selection_score'] = observable_score
        model['local_peak'] = local_peak
        model['off_candidate_peak'] = off_peak
        model['stability_proxy'] = stability
        candidate_models.append(model)
        candidate_scores.append(observable_score)
    order = np.argsort(candidate_scores)[::-1]
    best_index = int(order[0])
    best_score = float(candidate_scores[best_index])
    second_score = float(candidate_scores[order[1]]) if len(order) > 1 else 0.0
    margin_confidence = float((best_score - second_score) / (abs(best_score) + 1e-12))
    peak_confidence = float(response[candidates[best_index]] / (np.max(response) + 1e-12))
    confidence = float(np.clip(0.5 * max(0.0, margin_confidence) + 0.5 * peak_confidence, 0.0, 1.0))
    diagnostics = {
        'method': 'multi_hypothesis_observable_stability',
        'candidate_count': len(candidate_models),
        'candidate_scores': [float(value) for value in candidate_scores],
        'topk_candidates': [
            {
                'center': int(model['estimated_target_idx']),
                'observable_selection_score': float(model['observable_selection_score']),
                'stability_proxy': float(model['stability_proxy']),
                'local_peak': float(model['local_peak']),
                'off_candidate_peak': float(model['off_candidate_peak']),
            }
            for model in candidate_models
        ],
        'margin_confidence': margin_confidence,
        'peak_confidence': peak_confidence,
        'candidate_separation': int(separation),
    }
    if confidence < confidence_threshold:
        return _identity_model('FALLBACK_IDENTITY_LOW_CONFIDENCE', diagnostics, regularization)
    selected = candidate_models[best_index]
    selected.update({
        'estimator_confidence': confidence,
        'fit_status': 'FITTED_MULTI_HYPOTHESIS_PROTECTED_PROJECTION',
        'diagnostics': diagnostics,
        'fallback': None,
    })
    return selected


def apply_adapt_filter_fair(observed_iq: Any, model: dict) -> np.ndarray:
    """Apply a fitted fair model without accessing evaluation truth."""
    received = np.asarray(observed_iq, dtype=complex)
    if received.ndim == 1:
        received = received[None, :]
    if received.ndim != 2 or not np.all(np.isfinite(received)):
        raise ValueError('observed_iq must be a finite 1D/2D array')
    if not isinstance(model, dict):
        raise TypeError('model must be a dictionary returned by a fair fit function')
    coefficients = model.get('filter_coefficients')
    if model.get('fallback') == 'Identity' or coefficients is None:
        return received.copy()
    vector = np.asarray(coefficients, dtype=complex).reshape(-1)
    if vector.size != received.shape[1] or not np.all(np.isfinite(vector)):
        raise ValueError('model coefficients have wrong shape or non-finite values')
    regularization = float(model.get('regularization', 0.01))
    output, condition_number, _ = _projection_output(received, vector, regularization)
    max_condition = float(model.get('max_condition_number', 1e6))
    if not np.all(np.isfinite(output)) or condition_number > max_condition:
        return received.copy()
    return output
