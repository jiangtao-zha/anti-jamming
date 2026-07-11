"""Power and JSR utilities shared by Phase 1 jammer validation."""

import numpy as np


def calculate_power(signal):
    """Return mean complex-sample power, including zero-padded samples."""
    values = np.asarray(signal)
    if values.size == 0:
        return 0.0
    return float(np.mean(np.abs(values) ** 2))


def calculate_jsr(target, jammer):
    """Return 10*log10(P_jammer/P_target), or -inf for zero jammer power."""
    target_power = calculate_power(target)
    jammer_power = calculate_power(jammer)
    if jammer_power <= 0.0:
        return float('-inf')
    if target_power <= 0.0:
        return float('inf')
    return float(10.0 * np.log10(jammer_power / target_power))


def scale_to_jsr(jammer, target, jsr_db):
    """Scale a raw jammer to the requested power ratio and return a copy."""
    raw = np.asarray(jammer, dtype=complex)
    target_power = calculate_power(target)
    jammer_power = calculate_power(raw)
    if target_power <= 0.0:
        raise ValueError('target signal has zero power')
    if jammer_power <= 0.0:
        raise ValueError('raw jammer has zero power')
    desired_power = target_power * (10.0 ** (float(jsr_db) / 10.0))
    return raw * np.sqrt(desired_power / jammer_power)
