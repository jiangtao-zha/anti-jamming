"""
rl_framework/run_comparison.py
===============================
综合对比实验脚本。

独立运行，对比四种条件下的 SINR 改善：
  1. 无抗干扰（原始信号直接脉压）
  2. Expert 策略（领域规则）
  3. Standard PPO（加载权重，默认 jammer_only 模式）
  4. CPPO（加载权重，默认 signal_and_jammer 模式）

输出：控制台表格 + 柱状图。

用法:
    # 完整对比（需要提供 PPO 权重文件）
    python run_comparison.py --cppo_weights cppo_best.pt --std_ppo_weights std_ppo_best.pt

    # 仅对比 Expert vs 无处理（不需要 PPO 权重）
    python run_comparison.py

    # 自定义 input_mode
    python run_comparison.py --std_ppo_weights std_ppo_best.pt --std_ppo_input_mode signal_and_jammer

    # 自定义参数
    python run_comparison.py --episodes 30 --output_plot my_comparison.png
"""

import os
import sys
import argparse
import numpy as np

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from unified_framework import JammerLoader
from rl_framework.config import Config, CPPOConfig, StdPPOConfig, ExpertConfig, resolve_config
from rl_framework.environment import AntiJamEnv
from rl_framework.agent_factory import create_agent
from rl_framework.utils import compute_sinr_from_radar_par, decode_action, set_seed
from anti_jamming.adapters import get_antijam_func


# =====================================================================
# 评估核心
# =====================================================================
def _eval_no_antijam(env, jammer_name, num_episodes, cfg):
    """无抗干扰：直接测 SINR before（= after，不做处理）。"""
    improvements = []
    for _ in range(num_episodes):
        jam_idx = env.jammer_list.index(jammer_name)
        env.current_jammer = JammerLoader.load(
            jammer_name, f0=cfg.f0, B=cfg.Bw, T=cfg.Pw, Tr=cfg.Tr)
        for t in range(cfg.steps_per_episode):
            radar_par = env.radar_env.generate_with_jammer(env.current_jammer)
            sinr = compute_sinr_from_radar_par(radar_par, ref_cells=cfg.cfar_ref_cells)
            improvements.append(0.0)  # 无处理，改善为 0
    return np.mean(improvements)


def _eval_agent(env, agent, jammer_name, num_episodes, cfg):
    """用指定智能体评估。"""
    improvements = []
    jam_idx = env.jammer_list.index(jammer_name)

    for _ in range(num_episodes):
        env.current_jammer_idx = jam_idx
        env.current_jammer_name = jammer_name
        env.jammer_onehot = np.zeros(env.num_jammers, dtype=np.float32)
        env.jammer_onehot[jam_idx] = 1.0
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

            improvements.append(sinr_after - sinr_before)

    return np.mean(improvements)


# =====================================================================
# 绘图
# =====================================================================
def plot_comparison(results_table, jammer_names, output_path):
    """
    绘制柱状图：X=干扰类型, Y=平均SINR改善, 可用策略各一根柱子。
    """
    n_jammers = len(jammer_names)
    x = np.arange(n_jammers)
    width = 0.18

    # 只绘制有数据的策略
    all_strategies = [
        ('none',     'No Anti-Jam',  '#b0b0b0'),
        ('expert',   'Expert',       '#3498db'),
        ('std_ppo',  'Std PPO',      '#e67e22'),
        ('cppo',     'CPPO',         '#e74c3c'),
    ]
    strategies = [(k, l, c) for k, l, c in all_strategies
                  if len(results_table.get(k, [])) == n_jammers]

    if not strategies:
        print("[warn] 无可用策略数据，跳过绘图")
        return

    n_strategies = len(strategies)
    offsets = np.arange(n_strategies) - (n_strategies - 1) / 2.0

    fig, ax = plt.subplots(figsize=(max(10, n_jammers * 1.5), 6))

    for (key, label, color), offset in zip(strategies, offsets):
        vals = results_table[key]
        ax.bar(x + offset * width, vals, width, label=label,
               color=color, edgecolor='white', linewidth=0.5)

    ax.set_xlabel('Jamming Type', fontsize=11)
    ax.set_ylabel('Avg SINR Improvement (dB)', fontsize=11)
    ax.set_title('Anti-Jamming Strategy Comparison', fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(jammer_names, rotation=30, ha='right', fontsize=9)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"\n[comparison] 图表已保存: {output_path}")


# =====================================================================
# 主函数
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description='抗干扰策略综合对比实验')
    parser.add_argument('--cppo_weights', type=str, default=None,
                        help='CPPO 模型权重路径 (.pt)')
    parser.add_argument('--std_ppo_weights', type=str, default=None,
                        help='Standard PPO 模型权重路径 (.pt)')
    parser.add_argument('--episodes', type=int, default=50,
                        help='每个干扰类型测试的回合数')
    parser.add_argument('--output_plot', type=str, default='comparison_results.png',
                        help='输出图表文件名')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--std_ppo_input_mode', type=str, default='jammer_only',
                        choices=['signal_and_jammer', 'jammer_only'],
                        help='Standard PPO input_mode (default: jammer_only)')
    parser.add_argument('--cppo_input_mode', type=str, default='signal_and_jammer',
                        choices=['signal_and_jammer', 'jammer_only'],
                        help='CPPO input_mode (default: signal_and_jammer)')
    args = parser.parse_args()

    set_seed(args.seed)
    cfg = Config()
    env = AntiJamEnv(cfg)

    jammer_names = env.jammer_list
    print(f"[comparison] 干扰类型: {jammer_names}")
    print(f"[comparison] 每种干扰测试回合数: {args.episodes}")

    # ---- 创建智能体 ----
    agents = {}

    # Expert
    expert_cfg = ExpertConfig()
    expert_cfg.expert_rules = {}
    agents['expert'] = create_agent(expert_cfg, env.get_signal_shape(), env.num_jammers)
    print("[comparison] Expert 策略已加载")

    # Std PPO
    if args.std_ppo_weights:
        std_cfg = StdPPOConfig()
        std_cfg.input_mode = args.std_ppo_input_mode
        agents['std_ppo'] = create_agent(std_cfg, env.get_signal_shape(), env.num_jammers)
        agents['std_ppo'].load(args.std_ppo_weights)
        print(f"[comparison] Std PPO 已加载: {args.std_ppo_weights} (input_mode={std_cfg.input_mode})")
    else:
        print("[comparison] 未提供 --std_ppo_weights，跳过 Std PPO")

    # CPPO
    if args.cppo_weights:
        cppo_cfg = CPPOConfig()
        cppo_cfg.input_mode = args.cppo_input_mode
        agents['cppo'] = create_agent(cppo_cfg, env.get_signal_shape(), env.num_jammers)
        agents['cppo'].load(args.cppo_weights)
        print(f"[comparison] CPPO 已加载: {args.cppo_weights} (input_mode={cppo_cfg.input_mode})")
    else:
        print("[comparison] 未提供 --cppo_weights，跳过 CPPO")

    # ---- 评估 ----
    results_table = {k: [] for k in ['none', 'expert', 'std_ppo', 'cppo']}
    results_table['none'] = [0.0] * len(jammer_names)  # 无处理始终为 0

    for jname in jammer_names:
        print(f"\n>>> 评估干扰: {jname} ...", end=' ', flush=True)

        # Expert
        imp = _eval_agent(env, agents['expert'], jname, args.episodes, cfg)
        results_table['expert'].append(imp)
        print(f"Expert={imp:+.2f}", end=' ', flush=True)

        # Std PPO
        if 'std_ppo' in agents:
            imp = _eval_agent(env, agents['std_ppo'], jname, args.episodes, cfg)
            results_table['std_ppo'].append(imp)
            print(f"StdPPO={imp:+.2f}", end=' ', flush=True)

        # CPPO
        if 'cppo' in agents:
            imp = _eval_agent(env, agents['cppo'], jname, args.episodes, cfg)
            results_table['cppo'].append(imp)
            print(f"CPPO={imp:+.2f}", end=' ', flush=True)

        print()

    # ---- 控制台表格 ----
    available = [k for k in ['none', 'expert', 'std_ppo', 'cppo']
                 if len(results_table.get(k, [])) == len(jammer_names)]

    col_labels = {
        'none': 'No Anti-Jam',
        'expert': 'Expert',
        'std_ppo': 'Std PPO',
        'cppo': 'CPPO',
    }

    # 表头
    header = f"{'干扰类型':<24}"
    for k in available:
        header += f"{col_labels[k]:>12}"
    print(f"\n{'=' * (24 + 12 * len(available))}")
    print(header)
    print(f"{'-' * (24 + 12 * len(available))}")

    for i, jname in enumerate(jammer_names):
        row = f"{jname:<24}"
        for k in available:
            vals = results_table[k]
            v = vals[i] if i < len(vals) else 0.0
            row += f"{v:>+12.2f}"
        print(row)

    # 平均行
    print(f"{'-' * (24 + 12 * len(available))}")
    avg_row = f"{'平均':<24}"
    for k in available:
        vals = results_table[k]
        avg_row += f"{np.mean(vals):>+12.2f}"
    print(avg_row)
    print(f"{'=' * (24 + 12 * len(available))}")

    # ---- 绘图 ----
    plot_comparison(results_table, jammer_names, args.output_plot)


if __name__ == '__main__':
    main()
