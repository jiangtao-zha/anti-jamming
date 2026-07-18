"""Physical component-recomposition fixture for Task 036-fix.

The original Task 036 position stress test translated the whole received
record. This module keeps the generated noise realization fixed and moves
only the target component, plus the jammer component when the active jammer
code is coupled to the target template.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from configs.phase1_radar import get_phase1_radar_params  # noqa: E402
from unified_framework import JammerLoader, RadarEnvironment  # noqa: E402
from utils.jsr_validation import calculate_jsr, calculate_power  # noqa: E402


TARGET_JAMMERS = ('NoiseProductJamming', 'NoiseConvolutionJamming')
NEGATIVE_CONTROLS = ('NoJammer', 'AMNoiseGaiJam', 'FMNoiseAimedJam', 'FMNoiseSaopin', 'SMSP', 'FMZuse')
JAMMERS = TARGET_JAMMERS + NEGATIVE_CONTROLS
JSRS = (0.0, 10.0, 20.0, 30.0)
SAFE_TARGET_CENTERS = (1000, 1500, 2500, 3500, 4000)

# This policy is derived from the active component code, not from evaluation
# labels. NPJ/NCJ construct their jammer waveform from an LFM pulse-shaped
# factor, so their component keeps its relative delay to the target. The
# other selected active jammer components are generated on an independent
# local jammer time axis and are held fixed in the receive-window fixture.
POSITION_POLICIES = {
    'NoiseProductJamming': 'TARGET_COUPLED_COMPONENT_SHIFT',
    'NoiseConvolutionJamming': 'TARGET_COUPLED_COMPONENT_SHIFT',
    'NoJammer': 'NO_JAMMER',
    'AMNoiseGaiJam': 'TARGET_INDEPENDENT_COMPONENT_FIXED',
    'FMNoiseAimedJam': 'TARGET_INDEPENDENT_COMPONENT_FIXED',
    'FMNoiseSaopin': 'TARGET_INDEPENDENT_COMPONENT_FIXED',
    'SMSP': 'TARGET_INDEPENDENT_COMPONENT_FIXED',
    'FMZuse': 'TARGET_INDEPENDENT_COMPONENT_FIXED',
}
POLICY_EVIDENCE = {
    'NoiseProductJamming': 'jammer component is St_pulse multiplied by generated noise; relative target-template gate is retained',
    'NoiseConvolutionJamming': 'jammer component is convolution with St_pulse; relative target-template gate is retained',
    'NoJammer': 'no jammer component; noise realization is held fixed',
    'AMNoiseGaiJam': 'active jammer waveform uses local t_jam and does not consume target waveform or R_target for component placement',
    'FMNoiseAimedJam': 'active jammer waveform uses local t_jam and does not consume target waveform or R_target for component placement',
    'FMNoiseSaopin': 'active jammer waveform uses local t_jam and does not consume target waveform or R_target for component placement',
    'SMSP': 'active jammer pulses use local tau_i/t_jam and do not consume target waveform for component placement',
    'FMZuse': 'active jammer waveform uses local t_jam and does not consume target waveform or R_target for component placement',
}


@dataclass(frozen=True)
class FixtureBank:
    jammer: str
    jsr_db: float
    seed: int
    config: dict
    template: np.ndarray
    target_base: np.ndarray
    jammer_base: np.ndarray
    noise_base: np.ndarray
    received_base: np.ndarray
    policy: str


def embed_target(template: np.ndarray, center: int, n: int) -> np.ndarray:
    template = np.asarray(template, dtype=complex).reshape(-1)
    start = int(center) - template.size // 2
    end = start + template.size
    if start < 0 or end > n:
        raise ValueError(f'target center {center} produces invalid support {start}:{end} for N={n}')
    target = np.zeros(n, dtype=complex)
    target[start:end] = template
    return target


def translate_component(value: np.ndarray, shift: int) -> np.ndarray:
    value = np.asarray(value, dtype=complex).reshape(-1)
    output = np.zeros_like(value)
    if shift >= 0:
        source_start, destination_start = 0, int(shift)
    else:
        source_start, destination_start = int(-shift), 0
    count = min(value.size - source_start, value.size - destination_start)
    if count > 0:
        output[destination_start:destination_start + count] = value[source_start:source_start + count]
    return output


def _generate_no_jammer(config: dict, template: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    state = np.random.get_state()
    np.random.seed(seed)
    try:
        env = RadarEnvironment(config)
        radar = env.generate_without_jammer(noise_level=np.sqrt(config.get('noise_var', 0.1)))
    finally:
        np.random.set_state(state)
    target = embed_target(template, int(config['target_idx']), int(config['N']))
    received = np.asarray(radar['Srt_matrix'][0], dtype=complex)
    return target, np.zeros_like(received), received - target


def generate_bank(jammer: str, jsr_db: float, seed: int) -> FixtureBank:
    if jammer not in JAMMERS:
        raise ValueError(f'unsupported Task 036-fix jammer: {jammer}')
    config = get_phase1_radar_params({'JSR_dB': float(jsr_db)})
    template = np.asarray(RadarEnvironment(config).generate_target_signal(), dtype=complex)
    if jammer == 'NoJammer':
        target, jammer_component, noise = _generate_no_jammer(config, template, seed)
    else:
        instance = JammerLoader.load(jammer)
        generated = instance.generate_phase1(
            target_signal=template,
            config=config,
            jsr_db=float(jsr_db),
            seed=int(seed),
        )
        target = np.asarray(generated['target'], dtype=complex).reshape(-1)
        jammer_component = np.asarray(generated['jammer'], dtype=complex).reshape(-1)
        noise = np.asarray(generated['noise'], dtype=complex).reshape(-1)
    received = target + jammer_component + noise
    n = int(config['N'])
    for name, value in (('target', target), ('jammer', jammer_component), ('noise', noise), ('received', received)):
        if value.size != n:
            raise ValueError(f'{jammer} {name} has length {value.size}, expected {n}')
        if not np.all(np.isfinite(value)):
            raise ValueError(f'{jammer} {name} contains non-finite values')
    return FixtureBank(
        jammer=jammer,
        jsr_db=float(jsr_db),
        seed=int(seed),
        config=config,
        template=template,
        target_base=target,
        jammer_base=jammer_component,
        noise_base=noise,
        received_base=received,
        policy=POSITION_POLICIES[jammer],
    )


def compose(bank: FixtureBank, center: int) -> dict:
    n = int(bank.config['N'])
    target = embed_target(bank.template, int(center), n)
    baseline_center = int(bank.config['target_idx'])
    shift = int(center) - baseline_center
    if bank.policy == 'TARGET_COUPLED_COMPONENT_SHIFT':
        jammer = translate_component(bank.jammer_base, shift)
    else:
        jammer = bank.jammer_base.copy()
    noise = bank.noise_base.copy()
    received = target + jammer + noise
    measured_jsr = calculate_jsr(target, jammer)
    return {
        'jammer': bank.jammer,
        'jsr_db': bank.jsr_db,
        'seed': bank.seed,
        'target_position': int(center),
        'fixture_label': 'PHYSICAL_COMPONENT_RECOMPOSITION',
        'position_policy': bank.policy,
        'target': target,
        'jammer_component': jammer,
        'noise': noise,
        'received': received,
        'template': bank.template,
        'requested_jsr_db': bank.jsr_db,
        'measured_jsr_db': measured_jsr,
        'jsr_status': 'NO_JAMMER_NOT_APPLICABLE' if bank.jammer == 'NoJammer' else 'unified/pass',
    }


def component_power(value: np.ndarray) -> float:
    return calculate_power(value)


def power_change_db(value: np.ndarray, reference: np.ndarray) -> float:
    left, right = component_power(value), component_power(reference)
    if left <= 0.0 and right <= 0.0:
        return 0.0
    if left <= 0.0 or right <= 0.0:
        return float('-inf')
    return float(10.0 * np.log10(left / right))


def target_support(target: np.ndarray) -> tuple[int, int, int]:
    indices = np.flatnonzero(np.abs(target) > 0.0)
    if indices.size == 0:
        return -1, -1, 0
    return int(indices[0]), int(indices[-1]), int(indices.size)

