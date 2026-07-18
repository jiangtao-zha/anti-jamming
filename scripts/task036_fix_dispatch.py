"""Shared candidate dispatch for Task 036-fix2."""

from __future__ import annotations

from typing import Any

from anti_jamming.adapt_filter_fair import (
    fit_adapt_filter_fair,
    fit_adapt_filter_fair_multihypothesis,
)


FIT_FUNCTIONS = {
    'A': fit_adapt_filter_fair,
    'B': fit_adapt_filter_fair_multihypothesis,
}


class CandidateDispatchMismatch(RuntimeError):
    """Raised when a candidate design and the selected fit function disagree."""


def dispatch_info(candidate: dict[str, Any]) -> dict[str, Any]:
    design = str(candidate.get('design', ''))
    if design not in FIT_FUNCTIONS:
        raise CandidateDispatchMismatch(f'unsupported candidate design: {design!r}')
    fit_fn = FIT_FUNCTIONS[design]
    return {
        'candidate_id': candidate.get('candidate_id'),
        'candidate_design': design,
        'fit_function_name': fit_fn.__name__,
        'candidate_params': {
            'top_k': int(candidate['top_k']),
            'confidence_threshold': float(candidate['confidence_threshold']),
            'regularization': float(candidate['regularization']),
        },
        'dispatch_status': 'PASS',
    }


def validate_dispatch_identity(design: str, fit_function_name: str) -> None:
    """Validate the runtime design/function identity, raising on mismatch."""

    if design not in FIT_FUNCTIONS:
        raise CandidateDispatchMismatch(f'unsupported candidate design: {design!r}')
    expected = FIT_FUNCTIONS[design].__name__
    if expected != fit_function_name:
        raise CandidateDispatchMismatch(
            f'design {design!r} expected {expected}, received {fit_function_name}'
        )


def fit_candidate(
    candidate: dict[str, Any],
    observed,
    template,
    public_config: dict[str, Any],
):
    """Fit exactly the implementation selected by ``candidate['design']``."""

    info = dispatch_info(candidate)
    fit_fn = FIT_FUNCTIONS[info['candidate_design']]
    validate_dispatch_identity(info['candidate_design'], fit_fn.__name__)
    model = fit_fn(
        observed,
        template,
        public_config,
        top_k=info['candidate_params']['top_k'],
        confidence_threshold=info['candidate_params']['confidence_threshold'],
        regularization=info['candidate_params']['regularization'],
    )
    # Re-check after the call so a changed mapping cannot silently pass.
    validate_dispatch_identity(info['candidate_design'], fit_fn.__name__)
    return model
