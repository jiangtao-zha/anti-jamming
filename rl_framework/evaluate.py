"""
rl_framework/evaluate.py
=========================
评估脚本：对比无抗干扰、随机算法、PPO 智能体在不同干扰类型下的 SINR 和检测表现。

用法:
    python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_best.pt
    python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_final.pt --num_episodes 50
"""

import os
import sys
import argparse
import numpy as np

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from unified_framework import RadarEnvironment, JammerLoader
from anti_jamming.adapters import get_antijam_func
from rl_framework.config import Config
from rl_framework.environment import AntiJamEnv
from rl_framework.ppo_agent import PPOAgent
from rl_framework.utils import compute_sinr_from_radar_par, decode_action, set_seed


def evaluate_single_jammer(env, agent, jammer_name, num_episodes, cfg):
    """
    对单个干扰类型进行多回合评估，对比 4 种策略。

    返回:
        dict: 每种策略的平均 SINR 改善和检测率
    """
    results = {
        'no_antijam': {'sinr_before': [], 'sinr_after': [], 'improvement': [], 'detected': []},
        'random':     {'sinr_before': [], 'sinr_after': [], 'improvement': [], 'detected': []},
        'ppo':        {'sinr_before': [], 'sinr_after': [], 'improvement': [], 'detected': []},
    }

    for ep in range(num_episodes):
        # 手动选择干扰类型
        jammer_idx = env.jammer_list.index(jammer_name)
        env.current_jammer_idx = jammer_idx
        env.current_jammer_name = jammer_name
        env.jammer_onehot = np.zeros(env.num_jammers, dtype=np.float32)
        env.jammer_onehot[jammer_idx] = 1.0
        env.current_jammer = JammerLoader.load(
            jammer_name, f0=cfg.f0, B=cfg.Bw, T=cfg.Pw, Tr=cfg.Tr)

        for t in range(cfg.steps_per_episode):
            # 生成含干扰信号
            radar_par = env.radar_env.generate_with_jammer(env.current_jammer)
            sinr_before = compute_sinr_from_radar_par(
                radar_par, ref_cells=cfg.cfar_ref_cells)

            # --- 1) 无抗干扰 ---
            sinr_no_antijam = sinr_before
            results['no_antijam']['sinr_before'].append(sinr_before)
            results['no_antijam']['sinr_after'].append(sinr_no_antijam)
            results['no_antijam']['improvement'].append(0.0)
            results['no_antijam']['detected'].append(1.0 if sinr_no_antijam > 5 else 0.0)

            # --- 2) 随机选择抗干扰 ---
            rand_idx = np.random.randint(len(env.antijam_list))
            rand_continuous = np.random.uniform(0, 1, cfg.max_continuous_dim).astype(np.float32)
            rand_algo, rand_params = decode_action(rand_idx, rand_continuous, cfg)
            rand_func = get_antijam_func(rand_algo)
            try:
                proc_sig, proc_tpl = rand_func(radar_par, **rand_params)
                proc_par = dict(radar_par)
                proc_par['Srt_matrix'] = proc_sig
                proc_par['St_base'] = proc_tpl
                sinr_rand = compute_sinr_from_radar_par(proc_par, ref_cells=cfg.cfar_ref_cells)
            except Exception:
                sinr_rand = sinr_before
            results['random']['sinr_before'].append(sinr_before)
            results['random']['sinr_after'].append(sinr_rand)
            results['random']['improvement'].append(sinr_rand - sinr_before)
            results['random']['detected'].append(1.0 if sinr_rand > 5 else 0.0)

            # --- 3) PPO 智能体 ---
            signal_state = env._extract_state(radar_par)
            state_dict = {
                'signal': signal_state,
                'jammer_onehot': env.jammer_onehot.copy(),
            }
            ppo_idx, ppo_continuous, _, _ = agent.select_action(state_dict)
            ppo_algo, ppo_params = decode_action(ppo_idx, ppo_continuous, cfg)
            ppo_func = get_antijam_func(ppo_algo)
            try:
                proc_sig2, proc_tpl2 = ppo_func(radar_par, **ppo_params)
                proc_par2 = dict(radar_par)
                proc_par2['Srt_matrix'] = proc_sig2
                proc_par2['St_base'] = proc_tpl2
                sinr_ppo = compute_sinr_from_radar_par(proc_par2, ref_cells=cfg.cfar_ref_cells)
            except Exception:
                sinr_ppo = sinr_before
            results['ppo']['sinr_before'].append(sinr_before)
            results['ppo']['sinr_after'].append(sinr_ppo)
            results['ppo']['improvement'].append(sinr_ppo - sinr_before)
            results['ppo']['detected'].append(1.0 if sinr_ppo > 5 else 0.0)

    return results


def print_results(jammer_name, results):
    """打印单个干扰类型的评估结果。"""
    print(f"\n{'='*70}")
    print(f"  干扰类型: {jammer_name}")
    print(f"{'='*70}")
    print(f"{'策略':<18} {'SINR前(dB)':>12} {'SINR后(dB)':>12} {'改善(dB)':>10} {'检测率':>8}")
    print(f"{'-'*70}")

    for strategy, data in results.items():
        avg_before = np.mean(data['sinr_before'])
        avg_after = np.mean(data['sinr_after'])
        avg_imp = np.mean(data['improvement'])
        detect_rate = np.mean(data['detected'])
        label = {'no_antijam': '无抗干扰', 'random': '随机算法', 'ppo': 'PPO智能体'}[strategy]
        print(f"{label:<18} {avg_before:>12.2f} {avg_after:>12.2f} {avg_imp:>+10.2f} {detect_rate:>7.1%}")


def main():
    parser = argparse.ArgumentParser(description='PPO 抗干扰评估')
    parser.add_argument('--model', type=str, required=True,
                        help='训练好的模型路径 (.pt)')
    parser.add_argument('--num_episodes', type=int, default=20,
                        help='每种干扰的评估回合数')
    parser.add_argument('--jammer', type=str, default=None,
                        help='只评估指定干扰类型（默认评估全部）')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    cfg = Config()
    set_seed(args.seed)

    # 创建环境和加载模型
    env = AntiJamEnv(cfg)
    agent = PPOAgent(cfg, signal_shape=env.get_signal_shape(), num_jammers=env.num_jammers)
    agent.load(args.model)
    print(f"[eval] 模型已加载: {args.model}")
    print(f"[eval] 评估回合数: {args.num_episodes} (每干扰类型)")

    # 选择要评估的干扰
    if args.jammer:
        jammers_to_eval = [args.jammer]
        if args.jammer not in env.jammer_list:
            print(f"[warn] {args.jammer} 不在 jammer_list 中，尝试加载...")
    else:
        jammers_to_eval = env.jammer_list

    # 全局汇总
    all_results = {}
    for jname in jammers_to_eval:
        print(f"\n>>> 评估干扰: {jname} ({args.num_episodes} episodes)...")
        try:
            results = evaluate_single_jammer(env, agent, jname, args.num_episodes, cfg)
            print_results(jname, results)
            all_results[jname] = results
        except Exception as e:
            print(f"[error] 评估 {jname} 失败: {e}")

    # 汇总表
    print(f"\n{'='*70}")
    print(f"  总体汇总")
    print(f"{'='*70}")
    print(f"{'干扰类型':<24} {'无抗干扰':>10} {'随机':>10} {'PPO':>10} {'PPO增益':>10}")
    print(f"{'-'*70}")

    for jname, res in all_results.items():
        no_imp = np.mean(res['no_antijam']['improvement'])
        rnd_imp = np.mean(res['random']['improvement'])
        ppo_imp = np.mean(res['ppo']['improvement'])
        print(f"{jname:<24} {no_imp:>+10.2f} {rnd_imp:>+10.2f} {ppo_imp:>+10.2f} {ppo_imp - rnd_imp:>+10.2f}")

    avg_ppo = np.mean([np.mean(r['ppo']['improvement']) for r in all_results.values()])
    avg_rnd = np.mean([np.mean(r['random']['improvement']) for r in all_results.values()])
    print(f"{'-'*70}")
    print(f"{'平均':<24} {'':>10} {avg_rnd:>+10.2f} {avg_ppo:>+10.2f} {avg_ppo - avg_rnd:>+10.2f}")


if __name__ == '__main__':
    main()
