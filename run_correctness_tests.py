"""
批量正确性测试运行脚本。
对每个抗干扰算法运行 5 次独立试验，收集检测率和 SINR 指标，
按判定标准给出结论。

用法:
    python run_correctness_tests.py
"""

import sys
import os
import numpy as np
import traceback
from datetime import datetime

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# =====================================================================
# 测试配置：每个抗干扰算法与其对应的干扰样式
# =====================================================================
TEST_CONFIG = [
    {
        'antijam_name': 'WLN',
        'module': 'anti_jamming.wln_filter',
        'test_func': 'test_wln',
        'jammers': ['FMZuse'],
    },
    {
        'antijam_name': 'FrequencyDomainCanceller',
        'module': 'anti_jamming.FrequencyDomainCanceller',
        'test_func': 'test_frequency_domain_canceller',
        'jammers': ['AMNoiseGaiJam'],
    },
    {
        'antijam_name': 'adapt_filter',
        'module': 'anti_jamming.adapt_filter',
        'test_func': 'test_adapt_filter',
        'jammers': ['NoiseConvolutionJamming', 'NoiseProductJamming'],
    },
    {
        'antijam_name': 'FastSlowTimeProcessor',
        'module': 'anti_jamming.FastSlowTimeProcessor',
        'test_func': 'test_fast_slow_time_processor',
        'jammers': ['SliceCombineJam', 'SMSP', 'ISDJ'],
    },
    {
        'antijam_name': 'Frequency_agile',
        'module': 'anti_jamming.Frequency_agile',
        'test_func': 'test_frequency_agile',
        'jammers': ['FMNoiseSaopin'],
    },
    {
        'antijam_name': 'wave_agile',
        'module': 'anti_jamming.wave_agile',
        'test_func': 'test_wave_agile',
        'jammers': ['RGPO'],
    },
    {
        'antijam_name': 'frft_filter',
        'module': 'anti_jamming.frft_filter',
        'test_func': 'test_frft_filter',
        'jammers': ['FMNoiseAimedJam'],
    },
]

NUM_RUNS = 5
SEEDS = [42, 123, 456, 789, 2024]


# =====================================================================
# 判定标准
# =====================================================================
def judge(before_det_rate, after_det_rate, avg_sinr_improvement):
    """
    判定测试结果。

    返回: (verdict, reason)
        verdict: 'PASS', 'WARN', 'FAIL'
    """
    if after_det_rate < before_det_rate:
        return 'FAIL', f'检测率下降 ({before_det_rate:.0%} -> {after_det_rate:.0%})'
    if avg_sinr_improvement < -1.0:
        return 'WARN', f'SINR恶化 {avg_sinr_improvement:.2f} dB'
    return 'PASS', ''


# =====================================================================
# 主测试流程
# =====================================================================
def run_all_tests():
    all_results = []  # 最终汇总列表

    print("=" * 70)
    print("  雷达抗干扰算法 — 针对性正确性测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  每个配对运行 {NUM_RUNS} 次，种子: {SEEDS}")
    print("=" * 70)

    for config in TEST_CONFIG:
        antijam_name = config['antijam_name']
        jammers = config['jammers']

        print(f"\n{'#'*70}")
        print(f"  抗干扰算法: {antijam_name}")
        print(f"  对应干扰: {', '.join(jammers)}")
        print(f"{'#'*70}")

        # 动态导入测试函数
        try:
            mod = __import__(config['module'], fromlist=[config['test_func']])
            test_func = getattr(mod, config['test_func'])
        except Exception as e:
            print(f"  [错误] 无法导入测试函数: {e}")
            for jt in jammers:
                all_results.append({
                    'antijam': antijam_name,
                    'jammer': jt,
                    'avg_det_before': -1, 'avg_det_after': -1,
                    'avg_sinr_before': float('nan'), 'avg_sinr_after': float('nan'),
                    'sinr_improvement': float('nan'),
                    'verdict': 'FAIL', 'reason': f'导入失败: {e}',
                    'errors': [str(e)]
                })
            continue

        # 对每种干扰样式运行测试
        for jt in jammers:
            print(f"\n  --- {antijam_name} vs {jt} ---")

            run_data = []  # 每次运行的记录

            for run_idx, seed in enumerate(SEEDS):
                print(f"    运行 {run_idx+1}/{NUM_RUNS} (seed={seed})...", end=" ")
                try:
                    np.random.seed(seed)
                    result = test_func(seed=seed)

                    if jt in result:
                        info_b = result[jt]['before']
                        info_a = result[jt]['after']
                        run_data.append({
                            'seed': seed,
                            'det_before': info_b['is_detected'],
                            'det_after': info_a['is_detected'],
                            'sinr_before': info_b['sinr_db'],
                            'sinr_after': info_a['sinr_db'],
                            'improvement': info_a['sinr_db'] - info_b['sinr_db'],
                            'error': None
                        })
                        print(f"DET: {info_b['is_detected']}->{info_a['is_detected']}, "
                              f"SINR: {info_b['sinr_db']:.1f}->{info_a['sinr_db']:.1f} dB "
                              f"(Δ{info_a['sinr_db'] - info_b['sinr_db']:+.1f})")
                    else:
                        print(f"[警告] 结果中无 '{jt}' 键")
                        run_data.append({'seed': seed, 'error': f'结果中无 {jt} 键'})

                except Exception as e:
                    print(f"[异常] {type(e).__name__}: {e}")
                    run_data.append({'seed': seed, 'error': str(e)})

            # 汇总统计
            valid_runs = [r for r in run_data if r.get('error') is None]
            errors = [r['error'] for r in run_data if r.get('error') is not None]

            if valid_runs:
                det_before_rate = np.mean([r['det_before'] for r in valid_runs])
                det_after_rate = np.mean([r['det_after'] for r in valid_runs])
                avg_sinr_before = np.mean([r['sinr_before'] for r in valid_runs])
                avg_sinr_after = np.mean([r['sinr_after'] for r in valid_runs])
                sinr_improvement = avg_sinr_after - avg_sinr_before

                verdict, reason = judge(det_before_rate, det_after_rate, sinr_improvement)

                verdict_symbol = {'PASS': '✅ 通过', 'WARN': '⚠️ 警告', 'FAIL': '❌ 失败'}
                print(f"\n    汇总: 检测率 {det_before_rate:.0%} -> {det_after_rate:.0%}, "
                      f"SINR {avg_sinr_before:.2f} -> {avg_sinr_after:.2f} dB "
                      f"(Δ{sinr_improvement:+.2f} dB)")
                print(f"    判定: {verdict_symbol[verdict]} {reason}")
            else:
                det_before_rate = det_after_rate = -1
                avg_sinr_before = avg_sinr_after = float('nan')
                sinr_improvement = float('nan')
                verdict = 'FAIL'
                reason = '所有运行均异常'
                print(f"\n    汇总: 所有 {NUM_RUNS} 次运行均失败")
                print(f"    判定: ❌ 失败 {reason}")

            all_results.append({
                'antijam': antijam_name,
                'jammer': jt,
                'avg_det_before': det_before_rate,
                'avg_det_after': det_after_rate,
                'avg_sinr_before': avg_sinr_before,
                'avg_sinr_after': avg_sinr_after,
                'sinr_improvement': sinr_improvement,
                'verdict': verdict,
                'reason': reason,
                'errors': errors,
                'run_data': valid_runs,
            })

    # =====================================================================
    # 打印汇总表
    # =====================================================================
    print(f"\n\n{'='*100}")
    print("  测试结果汇总表")
    print(f"{'='*100}")
    header = f"{'抗干扰算法':<28} {'干扰样式':<28} {'检测率(前)':<10} {'检测率(后)':<10} {'SINR(前)':<12} {'SINR(后)':<12} {'改善dB':<10} {'判定':<6}"
    print(header)
    print("-" * 100)
    for r in all_results:
        det_b = f"{r['avg_det_before']:.0%}" if r['avg_det_before'] >= 0 else 'N/A'
        det_a = f"{r['avg_det_after']:.0%}" if r['avg_det_after'] >= 0 else 'N/A'
        sinr_b = f"{r['avg_sinr_before']:.2f}" if not np.isnan(r['avg_sinr_before']) else 'N/A'
        sinr_a = f"{r['avg_sinr_after']:.2f}" if not np.isnan(r['avg_sinr_after']) else 'N/A'
        imp = f"{r['sinr_improvement']:+.2f}" if not np.isnan(r['sinr_improvement']) else 'N/A'
        v = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(r['verdict'], '?')
        print(f"{r['antijam']:<28} {r['jammer']:<28} {det_b:<10} {det_a:<10} {sinr_b:<12} {sinr_a:<12} {imp:<10} {v:<6}")
    print("-" * 100)

    # 统计
    n_pass = sum(1 for r in all_results if r['verdict'] == 'PASS')
    n_warn = sum(1 for r in all_results if r['verdict'] == 'WARN')
    n_fail = sum(1 for r in all_results if r['verdict'] == 'FAIL')
    print(f"\n  总计: {len(all_results)} 项 | ✅ 通过: {n_pass} | ⚠️ 警告: {n_warn} | ❌ 失败: {n_fail}")

    return all_results


# =====================================================================
# 诊断输出（供阶段三使用）
# =====================================================================
def diagnose_failed(results):
    """对失败/警告案例输出详细诊断信息。"""
    failed = [r for r in results if r['verdict'] in ('FAIL', 'WARN')]
    if not failed:
        print("\n所有测试均通过，无需诊断。")
        return

    print(f"\n{'='*70}")
    print(f"  需要诊断的案例: {len(failed)} 项")
    print(f"{'='*70}")

    for r in failed:
        print(f"\n{'#'*50}")
        print(f"  {r['antijam']} vs {r['jammer']}: {r['verdict']}")
        print(f"  原因: {r['reason']}")
        if r.get('errors'):
            print(f"  错误记录:")
            for err in r['errors']:
                print(f"    - {err}")
        if r.get('run_data'):
            print(f"  各次运行详情:")
            for rd in r['run_data']:
                print(f"    seed={rd['seed']}: DET {rd['det_before']}->{rd['det_after']}, "
                      f"SINR {rd['sinr_before']:.1f}->{rd['sinr_after']:.1f} dB "
                      f"(Δ{rd['improvement']:+.1f})")


if __name__ == "__main__":
    results = run_all_tests()
    diagnose_failed(results)
