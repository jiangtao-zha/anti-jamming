"""
rl_framework/evaluate.py
========================
评估脚本：加载训练好的模型，对比不同策略在不同干扰类型下的 SINR 表现。

用法:
    # 评估 CPPO 智能体
    python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_best.pt

    # 评估 Standard PPO（自动根据 checkpoint 中保存的配置）
    python -m rl_framework.evaluate --model std_ppo_best.pt

    # 评估 Expert（不需要模型文件）
    python -m rl_framework.evaluate --agent_type expert
"""

import os
import sys
import argparse
import numpy as np

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from unified_framework import JammerLoader
from rl_framework.config import Config, resolve_config
from rl_framework.environment import AntiJamEnv
from rl_framework.agent_factory import create_agent
from rl_framework.utils import compute_sinr_from_radar_par, decode_action, set_seed
from anti_jamming.adapters import get_antijam_func


def evaluate_agent_on_jammer(env, agent, jammer_name, num_episodes, cfg):
    """
    用指定智能体在单个干扰类型上评估。

    返回:
        dict: {'improvement': [...], 'detected': [...], 'sinr_after': [...]}
    """
    results = {'improvement': [], 'detected': [], 'sinr_after': []}

    for _ in range(num_episodes):
        jammer_idx = env.jammer_list.index(jammer_name)
        env.current_jammer_idx = jammer_idx
        env.current_jammer_name = jammer_name
        env.jammer_onehot = np.zeros(env.num_jammers, dtype=np.float32)
        env.jammer_onehot[jammer_idx] = 1.0
        env.current_jammer = JammerLoader.load(
            jammer_name, f0=cfg.f0, B=cfg.Bw, T=cfg.Pw, Tr=cfg.Tr)

        for t in range(cfg.steps_per_episode):
            radar_par = env.radar_env.generate_with_jammer(env.current_jammer)
            sinr_before = compute_sinr_from_radar_par(
                radar_par, ref_cells=cfg.cfar_ref_cells)

            signal_state = env._extract_state(radar_par)
            state_dict = {
                'signal': signal_state,
                'jammer_onehot': env.jammer_onehot.copy(),
            }

            disc_idx, cont_vals, _, _ = agent.select_action(state_dict)
            algo_name, params = decode_action(disc_idx, cont_vals, cfg)
            antijam_func = get_antijam_func(algo_name)

            try:
                proc_sig, proc_tpl = antijam_func(radar_par, **params)
                proc_par = dict(radar_par)
                proc_par['Srt_matrix'] = proc_sig
                proc_par['St_base'] = proc_tpl
                sinr_after = compute_sinr_from_radar_par(
                    proc_par, ref_cells=cfg.cfar_ref_cells)
            except Exception:
                sinr_after = sinr_before

            results['improvement'].append(sinr_after - sinr_before)
            results['sinr_after'].append(sinr_after)
            results['detected'].append(1.0 if sinr_after > 5 else 0.0)

    return results


def main():
    parser = argparse.ArgumentParser(description='抗干扰智能体评估')
    parser.add_argument('--model', type=str, default=None,
                        help='训练好的模型路径 (.pt)，Expert 策略不需要')
    parser.add_argument('--agent_type', type=str, default=None,
                        choices=['cppo', 'std_ppo', 'expert'],
                        help='智能体类型（默认 cppo）')
    parser.add_argument('--num_episodes', type=int, default=20,
                        help='每种干扰的评估回合数')
    parser.add_argument('--jammer', type=str, default=None,
                        help='只评估指定干扰类型')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    cfg = Config()
    # 覆盖 agent_type
    if args.agent_type:
        cfg.agent_type = args.agent_type
    if cfg.agent_type == 'cppo':
        cfg.use_jammer_type = True
    elif cfg.agent_type == 'std_ppo':
        cfg.use_jammer_type = False

    set_seed(args.seed)

    env = AntiJamEnv(cfg)
    agent = create_agent(cfg, signal_shape=env.get_signal_shape(),
                         num_jammers=env.num_jammers)

    if cfg.agent_type != 'expert' and args.model:
        agent.load(args.model)
        print(f"[eval] 模型已加载: {args.model}")
    elif cfg.agent_type == 'expert':
        print(f"[eval] 使用 Expert 策略")
    else:
        print(f"[eval] 未提供模型路径，使用随机初始化的 {cfg.agent_type}")

    print(f"[eval] 智能体类型: {cfg.agent_type}")
    print(f"[eval] 评估回合数: {args.num_episodes} (每干扰类型)")

    jammers_to_eval = [args.jammer] if args.jammer else env.jammer_list

    # 表头
    agent_label = {'cppo': 'CPPO', 'std_ppo': 'StdPPO', 'expert': 'Expert'}[cfg.agent_type]
    print(f"\n{'='*65}")
    print(f"  评估: {agent_label}")
    print(f"{'='*65}")
    print(f"{'干扰类型':<24} {'SINR改善(dB)':>12} {'检测率':>8}")
    print(f"{'-'*65}")

    all_improvements = []
    for jname in jammers_to_eval:
        try:
            res = evaluate_agent_on_jammer(env, agent, jname, args.num_episodes, cfg)
            avg_imp = np.mean(res['improvement'])
            det_rate = np.mean(res['detected'])
            all_improvements.append(avg_imp)
            print(f"{jname:<24} {avg_imp:>+12.2f} {det_rate:>7.1%}")
        except Exception as e:
            print(f"{jname:<24} {'ERROR':>12} {str(e)[:30]}")

    if all_improvements:
        print(f"{'-'*65}")
        print(f"{'平均':<24} {np.mean(all_improvements):>+12.2f}")


if __name__ == '__main__':
    main()
