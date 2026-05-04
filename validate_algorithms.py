#!/usr/bin/env python3
"""
已知干扰-抗干扰配对正确性验证脚本 (validate_algorithms.py)

覆盖以下对应关系:
  切片组合干扰、频谱弥散干扰  --- 快慢时间域联合处理
  噪声调幅干扰              --- 频域对消算法
  扫频干扰、间歇采样干扰    --- 频率捷变
  噪声调频阻塞干扰          --- 宽窄限电路
  距离欺骗干扰              --- 波形捷变抗干扰
  瞄频干扰                  --- 分数阶傅里叶变换抗干扰
  噪声卷积干扰、噪声乘积干扰 --- 自相关滤波器

对每个配对，运行 10 次独立试验（随机种子不同），记录:
- 抗干扰前/后的检测成功率
- SINR 改善量的均值和标准差
"""
import sys
sys.path.insert(0, '.')

import numpy as np
from scipy import signal

from unified_framework import (
    RadarEnvironment, UnifiedEvaluator, JammerLoader, AntiJammingProcessor
)

# ============================================================
# 测试配对配置 (按照指定的对应关系)
# ============================================================
TEST_PAIRS = [
    # 切片组合干扰 + 快慢时间处理
    {
        'jammer_type': 'SliceCombineJam',
        'antijam_type': 'FastSlowTimeProcessor',
        'antijam_kwargs': {'limit_factor': 3.0},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '切片组合干扰 vs 快慢时间域联合处理',
    },
    # 频谱弥散干扰 + 快慢时间处理
    {
        'jammer_type': 'SMSP',
        'antijam_type': 'FastSlowTimeProcessor',
        'antijam_kwargs': {'limit_factor': 3.0},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '频谱弥散干扰 vs 快慢时间域联合处理',
    },
    # 噪声调幅干扰 + 频域对消
    {
        'jammer_type': 'AMNoiseGaiJam',
        'antijam_type': 'FrequencyDomainCanceller',
        'antijam_kwargs': {'use_fitted_freq': False},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '噪声调幅干扰 vs 频域对消算法',
    },
    # 扫频干扰 + 频率捷变
    {
        'jammer_type': 'FMNoiseSaopin',
        'antijam_type': 'Frequency_agile',
        'antijam_kwargs': {},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '扫频干扰 vs 频率捷变',
    },
    # 间歇采样干扰 + 频率捷变
    {
        'jammer_type': 'ISDJ',
        'antijam_type': 'Frequency_agile',
        'antijam_kwargs': {},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '间歇采样干扰 vs 频率捷变',
    },
    # 噪声调频阻塞干扰 + 宽窄限电路
    {
        'jammer_type': 'FMZuse',
        'antijam_type': 'WLN',
        'antijam_kwargs': {'par1': 0.6, 'par2': 6},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '噪声调频阻塞干扰 vs 宽窄限电路',
    },
    # 距离欺骗干扰 + 波形捷变
    {
        'jammer_type': 'RGPO',
        'antijam_type': 'wave_agile',
        'antijam_kwargs': {},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '距离欺骗干扰 vs 波形捷变抗干扰',
    },
    # 瞄频干扰 + 分数阶傅里叶变换
    {
        'jammer_type': 'FMNoiseAimedJam',
        'antijam_type': 'frft_filter',
        'antijam_kwargs': {'a1': 0.5, 'a2': 0.5, 'w': 100},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '瞄频干扰 vs 分数阶傅里叶变换抗干扰',
    },
    # 噪声卷积干扰 + 自相关滤波器
    {
        'jammer_type': 'NoiseConvolutionJamming',
        'antijam_type': 'adapt_filter',
        'antijam_kwargs': {'par1': 0.01},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '噪声卷积干扰 vs 自相关滤波器',
    },
    # 噪声乘积干扰 + 自相关滤波器
    {
        'jammer_type': 'NoiseProductJamming',
        'antijam_type': 'adapt_filter',
        'antijam_kwargs': {'par1': 0.01},
        'JSR_dB': 10,
        'noise_var': 0.1,
        'description': '噪声乘积干扰 vs 自相关滤波器',
    },
]


def load_special_jammer(jammer_type):
    """
    加载干扰器，对 SliceCombineJam 做特殊处理（因它位于 anti_jamming 目录）。
    """
    if jammer_type == 'SliceCombineJam':
        from anti_jamming.qpzh import SliceCombineJam
        # 假设 SliceCombineJam 的构造函数接受标准参数（如有不同，这里可按需调整）
        return SliceCombineJam()
    else:
        return JammerLoader.load(jammer_type)


def run_single_trial(pair_config, radar_params, seed=None):
    """
    运行单次试验。
    
    Returns:
        dict: 包含 detected_before, detected_after, sinr_before, sinr_after, sinr_improvement
    """
    if seed is not None:
        np.random.seed(seed)
    
    jammer_type = pair_config['jammer_type']
    antijam_type = pair_config['antijam_type']
    antijam_kwargs = pair_config['antijam_kwargs']
    
    # 创建雷达环境
    env = RadarEnvironment(radar_params)
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    
    # 加载干扰器（特殊类型单独处理）
    jammer = load_special_jammer(jammer_type)
    
    # 生成干扰信号
    radar_par = env.generate_with_jammer(jammer)
    
    St_base = radar_par['St_base']
    Srt_orig = radar_par['Srt_matrix'][0]
    target_idx = radar_par['target_idx']
    
    # 抗干扰前评估
    pc_orig = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')
    info_orig = evaluator.evaluate(np.abs(pc_orig), target_idx)
    
    # 应用抗干扰
    try:
        processor = AntiJammingProcessor(antijam_type)
        processed_signal, processed_template = processor.process(radar_par, **antijam_kwargs)
        
        if isinstance(processed_signal, np.ndarray) and processed_signal.ndim == 2:
            Srt_filtered = processed_signal[0]
        else:
            Srt_filtered = np.asarray(processed_signal)
        
        # 抗干扰后评估
        pc_filtered = signal.fftconvolve(Srt_filtered, np.conj(St_base[::-1]), mode='same')
        info_filtered = evaluator.evaluate(np.abs(pc_filtered), target_idx)
        
        return {
            'detected_before': info_orig['is_detected'],
            'detected_after': info_filtered['is_detected'],
            'sinr_before': info_orig['sinr_db'],
            'sinr_after': info_filtered['sinr_db'],
            'sinr_improvement': info_filtered['sinr_db'] - info_orig['sinr_db'],
            'error': None,
        }
    except Exception as e:
        return {
            'detected_before': info_orig['is_detected'],
            'detected_after': False,
            'sinr_before': info_orig['sinr_db'],
            'sinr_after': float('-inf'),
            'sinr_improvement': float('-inf'),
            'error': str(e),
        }


def run_pair_validation(pair_config, num_trials=10):
    """
    对一个干扰-抗干扰配对运行多次试验。
    
    Returns:
        dict: 包含统计结果
    """
    radar_params = {
        'f0': 15e6,
        'Bw': 5e6,
        'Pw': 20e-6,
        'Fs': 50e6,
        'M': 1,
        'N': int(100e-6 * 50e6),
        'target_dist': 6000,
        'target_amp': 1.0,
        'JSR_dB': pair_config['JSR_dB'],
        'noise_var': pair_config['noise_var'],
    }
    
    trials = []
    for i in range(num_trials):
        seed = 42 + i * 1000
        result = run_single_trial(pair_config, radar_params, seed=seed)
        trials.append(result)
    
    # 统计
    detected_before_count = sum(1 for t in trials if t['detected_before'])
    detected_before_rate = detected_before_count / num_trials
    detected_after_count = sum(1 for t in trials if t['detected_after'])
    detected_after_rate = detected_after_count / num_trials
    
    sinr_improvements = [t['sinr_improvement'] for t in trials if t['error'] is None]
    
    if sinr_improvements:
        mean_improvement = np.mean(sinr_improvements)
        std_improvement = np.std(sinr_improvements)
    else:
        mean_improvement = float('-inf')
        std_improvement = 0.0
    
    error_count = sum(1 for t in trials if t['error'] is not None)
    
    return {
        'pair': f"{pair_config['jammer_type']} vs {pair_config['antijam_type']}",
        'description': pair_config['description'],
        'num_trials': num_trials,
        'detected_before_rate': detected_before_count / num_trials,
        'detected_after_rate': detected_after_count / num_trials,
        'mean_sinr_improvement': mean_improvement,
        'std_sinr_improvement': std_improvement,
        'error_count': error_count,
        'trials': trials,
        'pass_detection': detected_after_rate >= detected_before_rate,
        'pass_sinr': mean_improvement >= -1.0,
        'pass': (detected_after_rate >= detected_before_rate) and (mean_improvement >= -1.0),
    }


def main():
    """运行所有配对验证。"""
    print("=" * 80)
    print("干扰-抗干扰配对正确性验证（覆盖指定对应关系）")
    print("=" * 80)
    
    all_results = []
    
    for pair_config in TEST_PAIRS:
        pair_name = f"{pair_config['jammer_type']} vs {pair_config['antijam_type']}"
        print(f"\n{'─' * 80}")
        print(f"测试配对: {pair_name}")
        print(f"描述: {pair_config['description']}")
        print(f"JSR: {pair_config['JSR_dB']} dB, noise_var: {pair_config['noise_var']}")
        print(f"运行 10 次独立试验...")
        
        result = run_pair_validation(pair_config, num_trials=10)
        all_results.append(result)
        
        det_before_str = f"{result['detected_before_rate']*100:.0f}%"
        det_after_str = f"{result['detected_after_rate']*100:.0f}%"
        sinr_str = f"{result['mean_sinr_improvement']:+.2f} ± {result['std_sinr_improvement']:.2f} dB"
        pass_str = "PASS" if result['pass'] else "FAIL"
        
        print(f"  检测率 (前): {det_before_str}")
        print(f"  检测率 (后): {det_after_str}")
        print(f"  SINR 改善:   {sinr_str}")
        if result['error_count'] > 0:
            print(f"  错误次数:   {result['error_count']}")
        print(f"  结果:        {pass_str}")
    
    # 汇总表格
    print(f"\n{'=' * 80}")
    print("汇总结果")
    print(f"{'=' * 80}")
    print(f"{'配对':<50s} | {'检测率前':^8s} | {'检测率后':^8s} | {'SINR改善':^22s} | {'状态':^6s}")
    print("-" * 80)
    
    for result in all_results:
        det_before = f"{result['detected_before_rate']*100:.0f}%"
        det_after = f"{result['detected_after_rate']*100:.0f}%"
        sinr = f"{result['mean_sinr_improvement']:+.2f} ± {result['std_sinr_improvement']:.2f} dB"
        status = "PASS" if result['pass'] else "FAIL"
        print(f"{result['pair']:<50s} | {det_before:^8s} | {det_after:^8s} | {sinr:^22s} | {status:^6s}")
    
    print("-" * 80)
    total = len(all_results)
    passed = sum(1 for r in all_results if r['pass'])
    print(f"\n总结: {passed}/{total} 配对通过测试")
    
    if passed < total:
        failed = [r['pair'] for r in all_results if not r['pass']]
        print(f"未通过: {failed}")
    
    return all_results


if __name__ == "__main__":
    results = main()
    
    all_pass = all(r['pass'] for r in results)
    sys.exit(0 if all_pass else 1)