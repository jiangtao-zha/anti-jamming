#!/usr/bin/env python3
"""Configuration, shape, determinism, and state-transform checks for Phase 1."""

import copy
import numpy as np

from configs.phase1_radar import (
    get_phase1_jammer_params,
    get_phase1_radar_params,
)
from rl_framework.config import Config
from rl_framework.environment import AntiJamEnv
from unified_framework import JammerLoader, RadarEnvironment


def main():
    expected = get_phase1_radar_params()
    env = RadarEnvironment()
    loader_params = JammerLoader.DEFAULT_RADAR_PARAMS
    cfg = Config()
    rl_env = AntiJamEnv(cfg)

    for key in ('f0', 'Bw', 'Pw', 'Fs', 'Tr', 'target_dist'):
        assert env.radar_params[key] == expected[key], key
        assert getattr(cfg, {'Bw': 'Bw'}.get(key, key)) == expected[key], key
    for key, value in get_phase1_jammer_params().items():
        assert loader_params[key] == value, f'loader:{key}'

    assert expected['N'] == 5000
    assert expected['pulse_samples'] == 1000
    assert np.isclose(expected['target_delay_s'], 40e-6)
    assert expected['target_idx'] == 1500
    assert env.radar_params['N'] == expected['N']
    assert env.radar_params['target_idx'] == expected['target_idx']
    assert rl_env.radar_env.radar_params['N'] == 5000
    assert rl_env.radar_env.radar_params['Pw'] == 20e-6
    assert rl_env.radar_env.radar_params['Fs'] == 50e6

    np.random.seed(42)
    first = RadarEnvironment().generate_without_jammer(noise_level=0.5)
    np.random.seed(42)
    second = RadarEnvironment().generate_without_jammer(noise_level=0.5)
    assert first['Srt_matrix'].shape == (1, 5000)
    assert np.array_equal(first['Srt_matrix'], second['Srt_matrix'])
    assert np.array_equal(first['St_base'], second['St_base'])

    np.random.seed(123)
    jammer_a = JammerLoader.load('FMZuse')
    signal_a = RadarEnvironment().generate_with_jammer(jammer_a)
    np.random.seed(123)
    jammer_b = JammerLoader.load('FMZuse')
    signal_b = RadarEnvironment().generate_with_jammer(jammer_b)
    assert signal_a['Srt_matrix'].shape == (1, 5000)
    assert np.array_equal(signal_a['Srt_matrix'], signal_b['Srt_matrix'])

    np.random.seed(7)
    state = rl_env.reset()
    assert state['signal'].shape == (2, 1024)
    assert rl_env.current_radar_par['Srt_matrix'].shape == (1, 5000)
    oracle_changed = copy.deepcopy(rl_env.current_radar_par)
    oracle_changed['target_idx'] = 1
    oracle_changed['jam_info'] = {'jammer_type': 'different', 'target_idx': 2}
    assert np.array_equal(
        state['signal'], rl_env._extract_state(oracle_changed)
    )

    print('PASS: Phase 1 configuration, derived parameters, shapes, determinism, and state transform')
    print(f"radar_shape={first['Srt_matrix'].shape}")
    print(f"rl_state_shape={state['signal'].shape}")
    print(f"N={expected['N']} pulse_samples={expected['pulse_samples']} target_idx={expected['target_idx']}")


if __name__ == '__main__':
    main()
