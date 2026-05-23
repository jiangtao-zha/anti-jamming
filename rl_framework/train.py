"""
rl_framework/train.py
=====================
PPO 训练主循环。

支持:
  - 实时 matplotlib 窗口（训练中弹窗，原地刷新曲线）
  - TensorBoard 日志
  - 定期模型保存 & 中断恢复
  - 命令行参数覆盖配置
  - 训练结束自动保存高清终版图片

用法:
    python -m rl_framework.train
    python -m rl_framework.train --episodes 2000 --state_mode range_profile
    python -m rl_framework.train --resume rl_framework/checkpoints/ppo_ep500.pt
"""

import os
import sys
import time
import argparse
import numpy as np

# 确保项目根目录在 path 中
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from rl_framework.config import Config
from rl_framework.environment import AntiJamEnv
from rl_framework.agent_factory import create_agent
from rl_framework.utils import RolloutBuffer, set_seed, get_device

import matplotlib
# 尝试使用交互式后端；无显示器时自动回退到 Agg（仅保存文件）
_backend_candidates = ['TkAgg', 'Qt5Agg', 'QtAgg', 'GTK4Agg', 'GTK3Agg', 'macosx']
_interactive_ok = False
for _b in _backend_candidates:
    try:
        matplotlib.use(_b, force=True)
        import matplotlib.pyplot as plt
        plt.figure()
        plt.close('all')
        _interactive_ok = True
        break
    except Exception:
        continue

if not _interactive_ok:
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

import matplotlib.pyplot as plt

# 覆盖 unified_framework 等模块中设置的 SimHei 字体，macOS 上不可用
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False


# =====================================================================
# 绘图工具
# =====================================================================
def _ma_window(n_points):
    """自适应移动平均窗口：数据量的 5%，夹在 [5, 50] 之间，保证奇数。"""
    w = max(5, min(50, max(1, n_points) // 20))
    return w if w % 2 == 1 else w + 1


def _smooth(arr, window):
    """简单移动平均，返回与输入等长的数组（边缘不收缩）。"""
    if len(arr) < window or window < 2:
        return np.array(arr)
    kernel = np.ones(window) / window
    padded = np.pad(arr, (window // 2, window - window // 2 - 1), mode='edge')
    return np.convolve(padded, kernel, mode='valid')[:len(arr)]


class LivePlotter:
    """
    交互式实时绘图器。
    在训练循环外创建一次 figure + line 对象，每次调用 update() 时原地刷新。
    """

    def __init__(self, max_episodes):
        self.max_episodes = max_episodes
        self.interactive = _interactive_ok

        # 预分配 x 轴容量
        self.x_capacity = max(200, max_episodes)

        # ---- 创建 figure (4 子图) ----
        self.fig, self.axes = plt.subplots(
            4, 1, figsize=(12, 16),
            gridspec_kw={'hspace': 0.45})
        self.fig.canvas.manager.set_window_title('PPO Training Monitor')
        self.fig.patch.set_facecolor('#fafafa')

        # ---- 子图 1: Reward ----
        ax = self.axes[0]
        ax.set_facecolor('#fdfdfd')
        ax.set_title('Average Reward per Episode', fontsize=11, fontweight='bold')
        ax.set_xlabel('Episode')
        ax.set_ylabel('Reward')
        ax.grid(True, alpha=0.25)
        self.line_reward_raw, = ax.plot([], [], alpha=0.25, color='steelblue', lw=0.5)
        self.line_reward_ma,  = ax.plot([], [], color='steelblue', lw=2, label='Reward (MA)')
        ax.legend(loc='upper left', fontsize=8)

        # ---- 子图 2: SINR Improvement ----
        ax = self.axes[1]
        ax.set_facecolor('#fdfdfd')
        ax.set_title('SINR Improvement per Episode', fontsize=11, fontweight='bold')
        ax.set_xlabel('Episode')
        ax.set_ylabel('SINR Improvement (dB)')
        ax.grid(True, alpha=0.25)
        self.line_sinr_raw, = ax.plot([], [], alpha=0.25, color='darkorange', lw=0.5)
        self.line_sinr_ma,  = ax.plot([], [], color='darkorange', lw=2, label='SINR imp. (MA)')
        ax.legend(loc='upper left', fontsize=8)

        self.title_text_0 = self.axes[0].set_title('', fontsize=11, fontweight='bold')

        # ---- 子图 3: Loss ----
        ax = self.axes[2]
        ax.set_facecolor('#fdfdfd')
        ax.set_title('Actor & Critic Loss', fontsize=11, fontweight='bold')
        ax.set_xlabel('Episode')
        ax.set_ylabel('Loss')
        ax.grid(True, alpha=0.25)

        self.line_actor_raw,  = ax.plot([], [], alpha=0.25, color='crimson',   lw=0.5)
        self.line_actor_ma,   = ax.plot([], [], color='crimson',    lw=2, label='Actor (MA)')
        self.line_critic_raw, = ax.plot([], [], alpha=0.25, color='seagreen',  lw=0.5)
        self.line_critic_ma,  = ax.plot([], [], color='seagreen',   lw=2, label='Critic (MA)')
        ax.legend(loc='upper right', fontsize=8)

        # ---- 子图 4: Detection Rate ----
        ax = self.axes[3]
        ax.set_facecolor('#fdfdfd')
        ax.set_title('Detection Rate', fontsize=11, fontweight='bold')
        ax.set_xlabel('Episode')
        ax.set_ylabel('Detection Rate')
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.25)

        self.fill_det = ax.fill_between([], [], alpha=0.12, color='mediumpurple')
        self.line_det_raw, = ax.plot([], [], alpha=0.25, color='mediumpurple', lw=0.5)
        self.line_det_ma,  = ax.plot([], [], color='mediumpurple',   lw=2, label='Detect rate (MA)')
        ax.legend(loc='upper left', fontsize=8)

        plt.tight_layout(rect=[0, 0, 1, 0.97])
        if self.interactive:
            plt.show(block=False)
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
            plt.show(block=False)
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()

    def update(self, history, current_episode):
        """用最新 history 数据原地刷新所有曲线。"""
        n = len(history['reward'])
        if n == 0:
            return
        x = np.arange(n)
        window = _ma_window(n)

        # Reward (子图 0)
        self.line_reward_raw.set_data(x, history['reward'])
        self.line_reward_ma.set_data(x, _smooth(history['reward'], window))
        self.title_text_0.set_text(
            f'[{current_episode}/{self.max_episodes}] Average Reward per Episode')
        self.axes[0].set_xlim(0, max(n, 10))
        self.axes[0].relim(); self.axes[0].autoscale_view()

        # SINR (子图 1)
        self.line_sinr_raw.set_data(x, history['sinr_improvement'])
        self.line_sinr_ma.set_data(x, _smooth(history['sinr_improvement'], window))
        self.axes[1].set_xlim(0, max(n, 10))
        self.axes[1].relim(); self.axes[1].autoscale_view()

        # Loss (子图 2)
        self.line_actor_raw.set_data(x, history['actor_loss'])
        self.line_actor_ma.set_data(x, _smooth(history['actor_loss'], window))
        self.line_critic_raw.set_data(x, history['critic_loss'])
        self.line_critic_ma.set_data(x, _smooth(history['critic_loss'], window))
        self.axes[2].set_xlim(0, max(n, 10))
        self.axes[2].relim(); self.axes[2].autoscale_view()

        # Detection rate (子图 3)
        self.line_det_raw.set_data(x, history['detect_rate'])
        self.line_det_ma.set_data(x, _smooth(history['detect_rate'], window))

        # 更新 fill_between（需要删旧的画新的）
        self.fill_det.remove()
        self.fill_det = self.axes[3].fill_between(
            x, history['detect_rate'], alpha=0.12, color='mediumpurple')
        self.axes[3].set_xlim(0, max(n, 10))

        # 刷新 canvas
        if self.interactive:
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()

    def close(self):
        """训练结束后关闭窗口（用户仍可手动关闭）。"""
        try:
            plt.close(self.fig)
        except Exception:
            pass


def save_final_plots(history, save_dir, agent_type='ppo'):
    """
    训练结束后绘制高清终版图表并保存到文件。
    2x2: reward / SINR / actor loss / critic loss + 检测率单独一张。
    使用 Agg 后端确保无交互窗口弹出。
    """
    n = len(history['reward'])
    if n == 0:
        return

    # 临时切到 Agg 后端保存
    orig_backend = matplotlib.get_backend()
    matplotlib.use('Agg')

    episodes = np.arange(n)
    window = _ma_window(n)

    def smooth_plot(ax, key, color, title, ylabel):
        ax.plot(episodes, history[key], alpha=0.3, color=color, lw=0.6)
        s = _smooth(history[key], window)
        ax.plot(episodes, s, color=color, lw=2, label=f'MA({window})')
        ax.set_title(title); ax.set_xlabel('Episode'); ax.set_ylabel(ylabel)
        ax.legend(); ax.grid(True, alpha=0.3)

    # ---- 2x2 ----
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    smooth_plot(axes[0, 0], 'reward',           'steelblue',  'Average Reward per Episode',           'Reward')
    smooth_plot(axes[0, 1], 'sinr_improvement', 'darkorange', 'Average SINR Improvement (dB)',        'SINR Improvement (dB)')
    smooth_plot(axes[1, 0], 'actor_loss',       'crimson',    'Actor Loss per Episode',                'Actor Loss')
    smooth_plot(axes[1, 1], 'critic_loss',      'seagreen',   'Critic Loss per Episode',               'Critic Loss')
    plt.tight_layout()
    path1 = os.path.join(save_dir, f'training_curves_{agent_type}.png')
    fig.savefig(path1, dpi=150)
    plt.close(fig)
    print(f"[train] 训练曲线已保存: {path1}")

    # ---- 检测率 ----
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    ax2.fill_between(episodes, history['detect_rate'], alpha=0.15, color='mediumpurple')
    ax2.plot(episodes, history['detect_rate'], alpha=0.3, color='mediumpurple', lw=0.6)
    ax2.plot(episodes, _smooth(history['detect_rate'], window),
             color='mediumpurple', lw=2, label=f'Detect Rate MA({window})')
    ax2.set_title('Detection Rate per Episode')
    ax2.set_xlabel('Episode'); ax2.set_ylabel('Detection Rate')
    ax2.set_ylim(-0.05, 1.05); ax2.legend(); ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    path2 = os.path.join(save_dir, f'detect_rate_{agent_type}.png')
    fig2.savefig(path2, dpi=150)
    plt.close(fig2)
    print(f"[train] 检测率曲线已保存: {path2}")

    # 恢复后端
    matplotlib.use(orig_backend)


# =====================================================================
# 参数 & 配置
# =====================================================================
def parse_args():
    parser = argparse.ArgumentParser(description='PPO 抗干扰训练')
    parser.add_argument('--episodes', type=int, default=None, help='最大训练回合数')
    parser.add_argument('--steps', type=int, default=None, help='每回合脉冲数')
    parser.add_argument('--lr', type=float, default=None, help='学习率')
    parser.add_argument('--state_mode', type=str, default=None,
                        choices=['raw_iq', 'range_profile'])
    parser.add_argument('--state_len', type=int, default=None)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--device', type=str, default=None)
    parser.add_argument('--log_dir', type=str, default=None)
    parser.add_argument('--save_dir', type=str, default=None)
    parser.add_argument('--resume', type=str, default=None, help='恢复训练的 checkpoint 路径')
    parser.add_argument('--no_tensorboard', action='store_true', help='禁用 TensorBoard')
    parser.add_argument('--plot_interval', type=int, default=None,
                        help='实时刷新图表的间隔（回合数），默认与 log_interval 相同')
    parser.add_argument('--agent_type', type=str, default=None,
                        choices=['cppo', 'std_ppo', 'expert'],
                        help='智能体类型（默认使用 config 中的设置）')
    parser.add_argument('--save_history', action='store_true',
                        help='训练结束后将训练历史保存为 .npz 文件')
    return parser.parse_args()


def merge_args_to_config(cfg, args):
    """用命令行参数覆盖 Config 字段。"""
    if args.episodes is not None:
        cfg.max_episodes = args.episodes
    if args.steps is not None:
        cfg.steps_per_episode = args.steps
    if args.lr is not None:
        cfg.lr = args.lr
    if args.state_mode is not None:
        cfg.state_mode = args.state_mode
    if args.state_len is not None:
        cfg.state_len = args.state_len
    if args.seed is not None:
        cfg.seed = args.seed
    if args.device is not None:
        cfg.device = args.device
    else:
        cfg.device = get_device("cpu")
    if args.log_dir is not None:
        cfg.log_dir = args.log_dir
    if args.save_dir is not None:
        cfg.model_save_dir = args.save_dir
    if args.agent_type is not None:
        cfg.agent_type = args.agent_type
        cfg.use_jammer_type = (args.agent_type == 'cppo')
        cfg.input_mode = 'signal_and_jammer' if args.agent_type == 'cppo' else 'jammer_only'
    return cfg


# =====================================================================
# 训练主函数
# =====================================================================
def train(cfg, use_tensorboard=True, resume_path=None, plot_interval=None,
         save_history=False):
    """
    PPO 训练主函数。
    训练过程中弹窗实时刷新曲线，训练结束后关闭窗口并保存高清图片。
    """
    set_seed(cfg.seed)
    print(f"[train] seed={cfg.seed}, device={cfg.device}")

    # ---- 目录 ----
    os.makedirs(cfg.log_dir, exist_ok=True)
    os.makedirs(cfg.model_save_dir, exist_ok=True)

    # ---- TensorBoard ----
    writer = None
    if use_tensorboard:
        try:
            from torch.utils.tensorboard import SummaryWriter
            writer = SummaryWriter(log_dir=cfg.log_dir)
            print(f"[train] TensorBoard 日志: {cfg.log_dir}")
        except ImportError:
            print("[train] tensorboard 不可用，跳过日志")
            use_tensorboard = False

    # ---- 环境 ----
    env = AntiJamEnv(cfg)
    print(f"[train] 环境: state_mode={cfg.state_mode}, signal_shape={env.get_signal_shape()}")
    print(f"[train] 离散动作={env.num_discrete_actions}, 连续参数={env.max_continuous_dim}")
    print(f"[train] 干扰类型={len(env.jammer_list)}, 抗干扰={len(env.antijam_list)}")

    # ---- 智能体 ----
    agent = create_agent(cfg, signal_shape=env.get_signal_shape(),
                         num_jammers=env.num_jammers)
    print(f"[train] 智能体类型: {cfg.agent_type}")

    if cfg.agent_type == 'expert':
        print("[train] Expert 策略无需训练，退出。")
        return agent

    start_episode = 0
    if resume_path and os.path.isfile(resume_path):
        agent.load(resume_path)
        fname = os.path.basename(resume_path)
        for part in fname.replace('.pt', '').split('_'):
            if part.startswith('ep'):
                try:
                    start_episode = int(part[2:])
                except ValueError:
                    pass
        print(f"[train] 从 {resume_path} 恢复训练, episode={start_episode}")

    # ---- 缓冲区 ----
    buffer = RolloutBuffer()

    # ---- 训练历史 ----
    history = {
        'reward': [],
        'sinr_improvement': [],
        'detect_rate': [],
        'actor_loss': [],
        'critic_loss': [],
    }

    # ---- 实时绘图 ----
    if plot_interval is None:
        plot_interval = cfg.log_interval
    plotter = LivePlotter(max_episodes=cfg.max_episodes)
    if _interactive_ok:
        print(f"[train] 实时图表窗口已弹出，每 {plot_interval} 回合刷新")
    else:
        print(f"[train] 无可用图形界面，图表将在训练结束后保存到文件")

    # ---- 训练循环 ----
    best_avg_reward = -float('inf')
    t_start = time.time()

    for episode in range(start_episode, cfg.max_episodes):
        state = env.reset()
        ep_reward = 0.0
        ep_sinr_improvement = 0.0
        ep_detects = 0

        for t in range(cfg.steps_per_episode):
            discrete_idx, continuous_vals, logprob, value = agent.select_action(state)
            next_state, reward, done, info = env.step(discrete_idx, continuous_vals)

            buffer.store(
                signal_state=state['signal'],
                jammer_onehot=state['jammer_onehot'],
                discrete_action=discrete_idx,
                continuous_action=continuous_vals,
                logprob=logprob,
                reward=reward,
                done=float(done),
                value=value,
            )

            ep_reward += reward
            ep_sinr_improvement += info['sinr_improvement']
            if info.get('sinr_after', 0) > 5:
                ep_detects += 1

            state = next_state

            if done:
                break

        # ---- PPO 更新 ----
        if len(buffer) > 0:
            agent.update(buffer)

        # ---- 统计 ----
        avg_reward = ep_reward / cfg.steps_per_episode
        avg_sinr_imp = ep_sinr_improvement / cfg.steps_per_episode

        # ---- 控制台日志 ----
        if episode % cfg.log_interval == 0:
            elapsed = time.time() - t_start
            print(
                f"Ep {episode:4d} | "
                f"avg_r={avg_reward:+8.3f} | "
                f"sinr_imp={avg_sinr_imp:+6.2f} dB | "
                f"detects={ep_detects}/{cfg.steps_per_episode} | "
                f"a_loss={agent.actor_loss_val:.4f} | "
                f"c_loss={agent.critic_loss_val:.4f} | "
                f"t={elapsed:.1f}s"
            )

        if use_tensorboard and writer:
            writer.add_scalar('episode/reward', avg_reward, episode)
            writer.add_scalar('episode/sinr_improvement', avg_sinr_imp, episode)
            writer.add_scalar('episode/detect_rate',
                              ep_detects / cfg.steps_per_episode, episode)
            writer.add_scalar('loss/actor', agent.actor_loss_val, episode)
            writer.add_scalar('loss/critic', agent.critic_loss_val, episode)

        # ---- 记录历史 ----
        history['reward'].append(avg_reward)
        history['sinr_improvement'].append(avg_sinr_imp)
        history['detect_rate'].append(ep_detects / cfg.steps_per_episode)
        history['actor_loss'].append(agent.actor_loss_val)
        history['critic_loss'].append(agent.critic_loss_val)

        # ---- 实时刷新曲线 ----
        if (episode + 1) % plot_interval == 0:
            plotter.update(history, episode + 1)

        # ---- 保存模型 ----
        if (episode + 1) % cfg.save_interval == 0:
            save_path = os.path.join(cfg.model_save_dir, f'ppo_ep{episode + 1}.pt')
            agent.save(save_path)
            print(f"[train] 模型已保存: {save_path}")

            if avg_reward > best_avg_reward:
                best_avg_reward = avg_reward
                best_path = os.path.join(cfg.model_save_dir, 'ppo_best.pt')
                agent.save(best_path)
                print(f"[train] 最佳模型已保存: {best_path} (avg_reward={avg_reward:.3f})")

    # ---- 训练结束 ----
    plotter.close()

    final_path = os.path.join(cfg.model_save_dir, 'ppo_final.pt')
    agent.save(final_path)
    print(f"\n[train] 训练完成! 最终模型: {final_path}")

    # ---- 保存高清终版图片 ----
    if len(history['reward']) > 0:
        save_final_plots(history, cfg.model_save_dir, agent_type=cfg.agent_type)

    # ---- 保存训练历史 (.npz) ----
    if save_history and len(history['reward']) > 0:
        history_path = os.path.join(
            cfg.model_save_dir,
            f'training_history_{cfg.agent_type}.npz')
        np.savez_compressed(
            history_path,
            reward=np.array(history['reward'], dtype=np.float64),
            sinr_improvement=np.array(history['sinr_improvement'], dtype=np.float64),
            detect_rate=np.array(history['detect_rate'], dtype=np.float64),
            actor_loss=np.array(history['actor_loss'], dtype=np.float64),
            critic_loss=np.array(history['critic_loss'], dtype=np.float64),
        )
        print(f"[train] 训练历史已保存: {history_path}")

    if writer:
        writer.close()

    return agent


def main():
    args = parse_args()
    cfg = Config()
    cfg = merge_args_to_config(cfg, args)

    use_tb = not args.no_tensorboard
    train(cfg, use_tensorboard=use_tb, resume_path=args.resume,
          plot_interval=args.plot_interval, save_history=args.save_history)


if __name__ == '__main__':
    main()
