"""Compatibility wrapper for the Phase 1 jammer interface.

Legacy jammer formulas remain untouched. The wrapper calls each legacy model
at JSR=0, extracts its raw jammer from the returned components, and applies
the single public JSR definition in :mod:`utils.jsr_validation`.
"""

from copy import deepcopy

import numpy as np

from configs.phase1_radar import get_phase1_radar_params
from utils.jsr_validation import calculate_jsr, calculate_power, scale_to_jsr


class Phase1JammerAdapter:
    """Expose a dict interface while preserving legacy tuple calls."""

    def __init__(self, jammer_type, legacy_jammer):
        self.jammer_type = jammer_type
        self.legacy = legacy_jammer

    def __getattr__(self, name):
        return getattr(self.legacy, name)

    @staticmethod
    def _embed_target(target_signal, params, length):
        target = np.asarray(target_signal, dtype=complex)
        if target.ndim != 1:
            raise ValueError('target_signal must be one-dimensional')
        if target.size == length:
            return target.copy()
        pulse_samples = params['pulse_samples']
        if target.size != pulse_samples:
            raise ValueError(
                f'target_signal length {target.size} does not match '
                f'pulse_samples {pulse_samples} or N {length}'
            )
        full = np.zeros(length, dtype=complex)
        start = params['target_start_idx']
        end = min(start + target.size, length)
        full[start:end] = target[:end - start]
        return full

    def generate_phase1(self, target_signal, config, jsr_db, seed=None):
        """Generate target/jammer/noise/received with measured JSR metadata."""
        params = get_phase1_radar_params(config)
        state = np.random.get_state()
        if seed is not None:
            np.random.seed(seed)
        try:
            raw_received, range_axis, legacy_info = self.legacy.generate(
                R_target=params['target_dist'],
                JSR_dB=0.0,
                noise_var=params['noise_var'],
            )
        finally:
            np.random.set_state(state)

        raw_received = np.asarray(raw_received, dtype=complex)
        target_generated = np.asarray(
            legacy_info.get('target_signal'), dtype=complex
        )
        noise = np.asarray(legacy_info.get('noise_signal'), dtype=complex)
        if target_generated.shape != raw_received.shape or noise.shape != raw_received.shape:
            raise ValueError(
                f'{self.jammer_type} does not expose aligned target/noise '
                f'components: received={raw_received.shape}, '
                f'target={target_generated.shape}, noise={noise.shape}'
            )

        provided_target = None
        if target_signal is not None:
            provided = np.asarray(target_signal, dtype=complex)
            # A full receive-window target is authoritative. A local pulse
            # template is retained as caller metadata, while the legacy
            # model's aligned full target preserves the existing waveform
            # sampling convention and regression behavior.
            if provided.size == raw_received.size:
                provided_target = provided.copy()
        target = target_generated.copy() if provided_target is None else provided_target
        raw_jammer = raw_received - target_generated - noise
        scaled_jammer = scale_to_jsr(raw_jammer, target, jsr_db)
        received = target + scaled_jammer + noise
        measured_jsr = calculate_jsr(target, scaled_jammer)

        metadata = deepcopy(legacy_info)
        metadata.update({
            'jammer_type': self.jammer_type,
            'requested_jsr_db': float(jsr_db),
            'measured_jsr_db': measured_jsr,
            'jsr_status': 'unified/pass',
            'legacy_components_available': True,
            'target_power': calculate_power(target),
            'jammer_power': calculate_power(scaled_jammer),
            'noise_power': calculate_power(noise),
            'input_target_power': (
                calculate_power(target_signal)
                if target_signal is not None else None
            ),
            'raw_jammer': raw_jammer,
            'scaled_jammer': scaled_jammer,
        })
        return {
            'target': target,
            'jammer': scaled_jammer,
            'noise': noise,
            'received': received,
            'requested_jsr_db': float(jsr_db),
            'measured_jsr_db': measured_jsr,
            'jsr_status': 'unified/pass',
            'legacy_components_available': True,
            'range_axis': range_axis,
            'metadata': metadata,
        }

    def generate(self, target_signal=None, config=None, jsr_db=None, seed=None, **kwargs):
        """Support the new dict API and the existing legacy tuple API."""
        is_new_api = target_signal is not None or config is not None or jsr_db is not None
        if is_new_api:
            if target_signal is None or config is None or jsr_db is None:
                raise TypeError(
                    'new interface requires target_signal, config, and jsr_db'
                )
            return self.generate_phase1(target_signal, config, jsr_db, seed)

        result = self.generate_phase1(
            target_signal=None,
            config=self.legacy_config(kwargs),
            jsr_db=kwargs.get('JSR_dB', 10),
            seed=seed,
        )
        return result['received'], result['range_axis'], result['metadata']

    def legacy_config(self, kwargs):
        return {
            'C': self.legacy.C,
            'f0': self.legacy.f0,
            'Bw': self.legacy.B,
            'Pw': self.legacy.T,
            'Fs': self.legacy.Fs,
            'Tr': self.legacy.Tr,
            'target_dist': kwargs.get('R_target', 6000.0),
            'noise_var': kwargs.get('noise_var', 0.1),
        }


class LegacyTupleJammerAdapter:
    """Expose a legacy tuple-only jammer through the Phase 1 dict contract."""

    def __init__(self, jammer_type, legacy_jammer):
        self.jammer_type = jammer_type
        self.legacy = legacy_jammer

    def __getattr__(self, name):
        return getattr(self.legacy, name)

    def generate(self, target_signal=None, config=None, jsr_db=None, seed=None, **kwargs):
        is_new_api = target_signal is not None or config is not None or jsr_db is not None
        if not is_new_api:
            return self.legacy.generate(**kwargs)
        if target_signal is None or config is None or jsr_db is None:
            raise TypeError('new interface requires target_signal, config, and jsr_db')

        state = np.random.get_state()
        if seed is not None:
            np.random.seed(seed)
        try:
            raw_received, range_axis, legacy_info = self.legacy.generate(
                R_target=config['target_dist'],
                JSR_dB=jsr_db,
                noise_var=config.get('noise_var', 0.1),
            )
        finally:
            np.random.set_state(state)

        raw_received = np.asarray(raw_received, dtype=complex)
        target_input = np.asarray(target_signal, dtype=complex)
        if target_input.size == raw_received.size:
            target = target_input.copy()
        else:
            target = np.zeros(raw_received.size, dtype=complex)
            start = int(config.get('target_start_idx', 0))
            end = min(start + target_input.size, target.size)
            if end > start:
                target[start:end] = target_input[:end - start]

        # The legacy model exposes only a composite tuple. Keep the residual
        # as a legacy jammer estimate and explicitly mark unified JSR blocked.
        jammer = raw_received - target
        noise = np.zeros_like(raw_received)
        metadata = dict(legacy_info) if isinstance(legacy_info, dict) else {}
        metadata.update({
            'jammer_type': self.jammer_type,
            'interface_status': 'PASS',
            'jsr_status': 'legacy/unified-JSR-blocked',
            'legacy_components_available': False,
        })
        return {
            'target': target,
            'jammer': jammer,
            'noise': noise,
            'received': target + jammer + noise,
            'requested_jsr_db': float(jsr_db),
            'measured_jsr_db': None,
            'jsr_status': 'legacy/unified-JSR-blocked',
            'legacy_components_available': False,
            'range_axis': range_axis,
            'metadata': metadata,
        }
