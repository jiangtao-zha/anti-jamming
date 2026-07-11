#!/usr/bin/env python3
"""
按马尔可夫状态分组测试各干扰-抗干扰配对的 SINR 改善和检测率。
用于为 r_t 设计提供实际数据支撑。
"""
import sys
sys.path.insert(0, '.')

import numpy as np
from scipy import signal
from unified_framework import (
    RadarEnvironment, UnifiedEvaluator, JammerLoader, AntiJammingProcessor
)
from configs.phase1_radar import get_phase1_radar_params

# ============================================================
# 马尔可夫状态分组配对
# ============================================================
STATE_PAIRS = {
    'S1': {
        'label': '脉内采样欺骗',
        'pairs': [
            {
                'jammer_type': 'ISDJ',
                'antijam_type': 'FastSlowTimeProcessor',
                'antijam_kwargs': {'limit_factor': 3.0},
            },
            {
                'jammer_type': 'SMSP',
                'antijam_type': 'FastSlowTimeProcessor',
                'antijam_kwargs': {'limit_factor': 3.0},
            },
        ],
    },
    'S2': {
        'label': '脉间采样欺骗',
        'pairs': [
            {
                'jammer_type': 'RGPO',
                'antijam_type': 'wave_agile',
                'antijam_kwargs': {},
            },
        ],
    },
    'S3': {
        'label': '瞄准式压制',
        'pairs': [
            {
                'jammer_type': 'FMNoiseAimedJam',
                'antijam_type': 'frft_filter',
                'antijam_kwargs': {'a1': 0.5, 'a2': 0.5, 'w': 100},
            },
            {
                'jammer_type': 'AMNoiseGaiJam',
                'antijam_type': 'FrequencyDomainCanceller',
                'antijam_kwargs': {'use_fitted_freq': True},
            },
        ],
    },
    'S4': {
        'label': '覆盖式压制',
        'pairs': [
            {
                'jammer_type': 'FMZuse',
                'antijam_type': 'WLN',
                'antijam_kwargs': {'par1': 0.3, 'par2': 6},
            },
            {
                'jammer_type': 'FMNoiseSaopin',
                'antijam_type': 'Frequency_agile',
                'antijam_kwargs': {},
            },
        ],
    },
    'S5': {
        'label': '信号结构污染',
        'pairs': [
            {
                'jammer_type': 'NoiseProductJamming',
                'antijam_type': 'adapt_filter',
                'antijam_kwargs': {'par1': 0.01},
            },
            {
                'jammer_type': 'NoiseConvolutionJamming',
                'antijam_type': 'adapt_filter',
                'antijam_kwargs': {'par1': 0.01},
            },
        ],
    },
}

NUM_TRIALS = 20


def run_trial(jammer_type, antijam_type, antijam_kwargs, radar_params, seed=None):
    if seed is not None:
        np.random.seed(seed)

    env = RadarEnvironment(radar_params)
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    jammer = JammerLoader.load(jammer_type)
    radar_par = env.generate_with_jammer(jammer)

    St_base = radar_par['St_base']
    Srt_orig = radar_par['Srt_matrix'][0]
    target_idx = radar_par['target_idx']

    # 抗干扰前
    pc_orig = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')
    info_orig = evaluator.evaluate(np.abs(pc_orig), target_idx)

    # 抗干扰后
    try:
        processor = AntiJammingProcessor(antijam_type)
        processed_signal, processed_template = processor.process(radar_par, **antijam_kwargs)

        if isinstance(processed_signal, np.ndarray) and processed_signal.ndim == 2:
            Srt_filtered = processed_signal[0]
        else:
            Srt_filtered = np.asarray(processed_signal)

        pc_filtered = signal.fftconvolve(Srt_filtered, np.conj(St_base[::-1]), mode='same')
        info_filtered = evaluator.evaluate(np.abs(pc_filtered), target_idx)

        return {
            'sinr_before': info_orig['sinr_db'],
            'sinr_after': info_filtered['sinr_db'],
            'improvement': info_filtered['sinr_db'] - info_orig['sinr_db'],
            'det_before': info_orig['is_detected'],
            'det_after': info_filtered['is_detected'],
            'error': None,
        }
    except Exception as e:
        return {
            'sinr_before': info_orig['sinr_db'],
            'sinr_after': float('-inf'),
            'improvement': float('-inf'),
            'det_before': info_orig['is_detected'],
            'det_after': False,
            'error': str(e),
        }


def main():
    radar_params = get_phase1_radar_params({
        'JSR_dB': 10,
        'noise_var': 0.1,
    })

    # 收集所有结果
    all_results = {}

    for state_name, state_info in STATE_PAIRS.items():
        print(f"\n{'='*70}")
        print(f"{state_name}: {state_info['label']}")
        print(f"{'='*70}")

        for pair in state_info['pairs']:
            jtype = pair['jammer_type']
            atype = pair['antijam_type']
            key = f"{jtype} vs {atype}"
            print(f"\n  {key}")
            print(f"  {'-'*50}")

            trials = []
            for i in range(NUM_TRIALS):
                result = run_trial(
                    jtype, atype, pair['antijam_kwargs'],
                    radar_params, seed=42 + i * 1000
                )
                trials.append(result)

            # 统计
            valid = [t for t in trials if t['error'] is None]
            errors = [t for t in trials if t['error'] is not None]

            if valid:
                sinr_b = [t['sinr_before'] for t in valid]
                sinr_a = [t['sinr_after'] for t in valid]
                improvements = [t['improvement'] for t in valid]
                det_b = sum(1 for t in valid if t['det_before']) / len(valid)
                det_a = sum(1 for t in valid if t['det_after']) / len(valid)

                print(f"  SINR_before: {np.mean(sinr_b):7.2f} ± {np.std(sinr_b):.2f} dB  "
                      f"(range: {np.min(sinr_b):.2f} ~ {np.max(sinr_b):.2f})")
                print(f"  SINR_after:  {np.mean(sinr_a):7.2f} ± {np.std(sinr_a):.2f} dB  "
                      f"(range: {np.min(sinr_a):.2f} ~ {np.max(sinr_a):.2f})")
                print(f"  改善量:      {np.mean(improvements):7.2f} ± {np.std(improvements):.2f} dB  "
                      f"(range: {np.min(improvements):.2f} ~ {np.max(improvements):.2f})")
                print(f"  检测率:      {det_b*100:.0f}% → {det_a*100:.0f}%")

                all_results[key] = {
                    'state': state_name,
                    'sinr_before_mean': np.mean(sinr_b),
                    'sinr_before_std': np.std(sinr_b),
                    'sinr_before_min': np.min(sinr_b),
                    'sinr_before_max': np.max(sinr_b),
                    'sinr_after_mean': np.mean(sinr_a),
                    'sinr_after_std': np.std(sinr_a),
                    'improvement_mean': np.mean(improvements),
                    'improvement_std': np.std(improvements),
                    'improvement_min': np.min(improvements),
                    'improvement_max': np.max(improvements),
                    'det_rate_before': det_b,
                    'det_rate_after': det_a,
                    'num_errors': len(errors),
                }

            if errors:
                for e in errors:
                    print(f"  ERROR: {e['error']}")

    # ============================================================
    # 汇总表（按状态分组）
    # ============================================================
    print(f"\n\n{'='*70}")
    print("汇总表（20 次平均）")
    print(f"{'='*70}")
    print(f"{'状态':<4} {'干扰':<28} {'SINR_before':>12} {'SINR_after':>12} "
          f"{'改善':>8} {'检测率':>10}")
    print(f"{'-'*80}")

    for state_name in ['S1', 'S2', 'S3', 'S4', 'S5']:
        state_results = {k: v for k, v in all_results.items() if v['state'] == state_name}
        for key, r in state_results.items():
            jname = key.split(' vs ')[0]
            print(f"{state_name:<4} {jname:<28} "
                  f"{r['sinr_before_mean']:>8.2f}±{r['sinr_before_std']:<3.1f} "
                  f"{r['sinr_after_mean']:>8.2f}±{r['sinr_after_std']:<3.1f} "
                  f"{r['improvement_mean']:>+7.2f} "
                  f"{r['det_rate_before']*100:>4.0f}%→{r['det_rate_after']*100:<4.0f}%")

    # ============================================================
    # 按状态聚合统计（用于 r_t 设计参考）
    # ============================================================
    print(f"\n\n{'='*70}")
    print("按状态聚合（r_t 设计参考）")
    print(f"{'='*70}")
    print(f"{'状态':<4} {'标签':<14} {'SINR_b均值':>10} {'SINR_b范围':>16} "
          f"{'改善均值':>10} {'改善范围':>16} {'检测率after':>10}")
    print(f"{'-'*85}")

    for state_name in ['S1', 'S2', 'S3', 'S4', 'S5']:
        state_results = [v for v in all_results.values() if v['state'] == state_name]
        if not state_results:
            continue
        label = STATE_PAIRS[state_name]['label']
        all_sinr_b = []
        all_improvements = []
        total_det = 0
        total_n = 0
        for r in state_results:
            all_sinr_b.append(r['sinr_before_mean'])
            all_improvements.append(r['improvement_mean'])
            total_det += r['det_rate_after']
            total_n += 1

        sinr_b_mean = np.mean(all_sinr_b)
        sinr_b_min = min(r['sinr_before_mean'] - r['sinr_before_std'] for r in state_results)
        sinr_b_max = max(r['sinr_before_mean'] + r['sinr_before_std'] for r in state_results)
        imp_mean = np.mean(all_improvements)
        imp_min = min(r['improvement_min'] for r in state_results)
        imp_max = max(r['improvement_max'] for r in state_results)
        det_avg = total_det / total_n

        print(f"{state_name:<4} {label:<14} "
              f"{sinr_b_mean:>10.2f} {sinr_b_min:>7.1f}~{sinr_b_max:<7.1f} "
              f"{imp_mean:>+10.2f} {imp_min:>+7.1f}~{imp_max:>+7.1f} "
              f"{det_avg*100:>8.0f}%")


if __name__ == '__main__':
    main()
