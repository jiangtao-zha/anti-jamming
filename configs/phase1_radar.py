"""Authoritative single-pulse radar configuration for Phase 1.

The receive array starts at the absolute target delay used by the jammer
models.  Therefore ``target_delay_s`` is an absolute physical delay, while
``target_idx`` is the target pulse center in that delay-relative array.
"""

from copy import deepcopy


PHASE1_RADAR_CONFIG = {
    'C': 3e8,
    'f0': 15e6,
    'Bw': 5e6,
    'Pw': 20e-6,
    'Fs': 50e6,
    'Tr': 100e-6,
    'M': 1,
    'target_dist': 6000.0,
    'target_amp': 1.0,
    'noise_var': 0.1,
    'JSR_dB': 10,
}


def get_phase1_radar_params(overrides=None):
    """Return a fresh radar parameter dict with all scalar derivations."""
    params = deepcopy(PHASE1_RADAR_CONFIG)
    if overrides:
        params.update(overrides)

    # N is always derived from the physical receive duration and sampling rate.
    params['N'] = round(params['Tr'] * params['Fs'])
    params['pulse_samples'] = round(params['Pw'] * params['Fs'])
    params['target_delay_s'] = 2.0 * params['target_dist'] / params['C']

    # Jammer output arrays start at target_delay_s. The target occupies the
    # following Pw interval, so the pulse center is 1.5*Pw in this coordinate.
    params['target_start_idx'] = round(params['Pw'] * params['Fs'])
    params['target_idx'] = params['target_start_idx'] + round(
        0.5 * params['Pw'] * params['Fs']
    )
    return params


def get_phase1_jammer_params(overrides=None):
    """Return jammer constructor parameters using jammer-side field names."""
    params = get_phase1_radar_params(overrides)
    return {
        'C': params['C'],
        'f0': params['f0'],
        'T': params['Pw'],
        'Tr': params['Tr'],
        'B': params['Bw'],
        'Fs': params['Fs'],
    }
