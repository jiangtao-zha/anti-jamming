#!/usr/bin/env python3
"""
重复实验脚本：对 CPPO 和 stdPPO 各跑 N 次实验，取平均后绘制对比图。

用法:
    .venv/bin/python run_repeated_experiments.py --repeats 3 --episodes 600
"""

import os
import sys
import argparse
import numpy as np

sys.path.insert(0, '.')
os.environ['MPLBACKEND'] = 'Agg'

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

from rl_framework.config import Config
from rl_framework.train import train


def run_one(agent_type, episodes, seed, base_save_dir):
    cfg = Config()
    cfg.agent_type = agent_type
    cfg.input_mode = 'signal_and_jammer' if agent_type == 'cppo' else 'jammer_only'
    cfg.use_jammer_type = (agent_type == 'cppo')
    cfg.max_episodes = episodes
    cfg.seed = seed
    cfg.model_save_dir = os.path.join(base_save_dir, f'{agent_type}_seed{seed}')
    cfg.log_dir = os.path.join(base_save_dir, f'tb_{agent_type}_seed{seed}')
    cfg.device = 'auto'

    train(cfg, use_tensorboard=False, save_history=True)

    path = os.path.join(cfg.model_save_dir, f'training_history_{agent_type}.npz')
    return dict(np.load(path))


def smooth(arr, window):
    if len(arr) < window:
        return np.array(arr)
    kernel = np.ones(window) / window
    padded = np.pad(arr, (window // 2, window - window // 2 - 1), mode='edge')
    return np.convolve(padded, kernel, mode='valid')[:len(arr)]


def plot_comparison(all_histories, save_dir, episodes):
    agents = list(all_histories.keys())
    keys = [
        ('reward', 'Average Reward per Episode', 'steelblue', 'darkorange'),
        ('sinr_improvement', 'Average SINR Improvement (dB)', 'steelblue', 'darkorange'),
        ('detect_rate', 'Detection Rate', 'steelblue', 'darkorange'),
    ]
    colors = {'cppo': 'steelblue', 'std_ppo': 'darkorange'}
    labels_map = {'cppo': 'CPPO (CNN+one-hot)', 'std_ppo': 'stdPPO (one-hot only)'}

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    ep = np.arange(episodes)
    ma_window = max(5, min(30, episodes // 20))
    if ma_window % 2 == 0:
        ma_window += 1

    for ax, (key, title, _, _) in zip(axes, keys):
        for agent_type in agents:
            runs = all_histories[agent_type]
            data = np.array([runs[i][key] for i in range(len(runs))])
            mean = np.mean(data, axis=0)
            std = np.std(data, axis=0)
            s = smooth(mean, ma_window)

            ax.fill_between(ep, mean - std, mean + std, alpha=0.15, color=colors[agent_type])
            ax.plot(ep, mean, alpha=0.25, color=colors[agent_type], lw=0.5)
            ax.plot(ep, s, color=colors[agent_type], lw=2, label=labels_map[agent_type])

        ax.set_title(title, fontweight='bold')
        ax.set_xlabel('Episode')
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(save_dir, 'repeated_comparison.png')
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"\n[plot] 对比图已保存: {path}")

    # 分指标单独保存高清图
    for key, title, _, _ in keys:
        fig2, ax2 = plt.subplots(figsize=(10, 5))
        for agent_type in agents:
            runs = all_histories[agent_type]
            data = np.array([runs[i][key] for i in range(len(runs))])
            mean = np.mean(data, axis=0)
            std = np.std(data, axis=0)
            s = smooth(mean, ma_window)

            ax2.fill_between(ep, mean - std, mean + std, alpha=0.15, color=colors[agent_type])
            ax2.plot(ep, mean, alpha=0.25, color=colors[agent_type], lw=0.5)
            ax2.plot(ep, s, color=colors[agent_type], lw=2, label=labels_map[agent_type])

        ax2.set_title(f'{title} (mean ± std over {len(runs)} runs)', fontweight='bold')
        ax2.set_xlabel('Episode')
        ax2.set_ylabel(title.split('(')[0].strip() if '(' in title else title)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        p = os.path.join(save_dir, f'comparison_{key}.png')
        fig2.savefig(p, dpi=150)
        plt.close(fig2)
        print(f"[plot] {p}")


def print_summary(all_histories, episodes):
    print("\n" + "=" * 70)
    print("实验汇总")
    print("=" * 70)

    for agent_type, runs in all_histories.items():
        final_rewards = [np.mean(runs[i]['reward'][-20:]) for i in range(len(runs))]
        final_sinrs = [np.mean(runs[i]['sinr_improvement'][-20:]) for i in range(len(runs))]
        final_dets = [np.mean(runs[i]['detect_rate'][-20:]) for i in range(len(runs))]
        print(f"\n  {agent_type}:")
        print(f"    Reward (最后20轮平均): {np.mean(final_rewards):+.2f} ± {np.std(final_rewards):.2f}")
        print(f"    SINR改善:              {np.mean(final_sinrs):+.2f} ± {np.std(final_sinrs):.2f} dB")
        print(f"    检测率:                {np.mean(final_dets):.3f} ± {np.std(final_dets):.3f}")

    if 'cppo' in all_histories and 'std_ppo' in all_histories:
        c_sinrs = [np.mean(all_histories['cppo'][i]['sinr_improvement'][-20:]) for i in range(len(all_histories['cppo']))]
        s_sinrs = [np.mean(all_histories['std_ppo'][i]['sinr_improvement'][-20:]) for i in range(len(all_histories['std_ppo']))]
        gap = np.mean(c_sinrs) - np.mean(s_sinrs)
        print(f"\n  CPPO - stdPPO SINR差距: {gap:+.2f} dB")


def main():
    parser = argparse.ArgumentParser(description='重复实验对比')
    parser.add_argument('--repeats', type=int, default=3, help='每种agent重复次数')
    parser.add_argument('--episodes', type=int, default=600, help='每次训练轮数')
    parser.add_argument('--save_dir', type=str, default='experiment_results', help='结果保存目录')
    args = parser.parse_args()

    os.makedirs(args.save_dir, exist_ok=True)

    all_histories = {}
    for agent_type in ['cppo', 'std_ppo']:
        runs = []
        for i in range(args.repeats):
            seed = 42 + i * 1000
            print(f"\n{'=' * 70}")
            print(f"  {agent_type} run {i+1}/{args.repeats} (seed={seed})")
            print(f"{'=' * 70}")
            history = run_one(agent_type, args.episodes, seed, args.save_dir)
            runs.append(history)
        all_histories[agent_type] = runs

    plot_comparison(all_histories, args.save_dir, args.episodes)
    print_summary(all_histories, args.episodes)


if __name__ == '__main__':
    main()
