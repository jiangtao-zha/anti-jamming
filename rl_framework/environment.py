"""
rl_framework/environment.py
============================
抗干扰 MDP 环境。

每步：接收一个含干扰的脉冲 → 智能体选择抗干扰算法和参数 → 评估 SINR 改善 → 返回奖励。
一个回合包含多个脉冲（固定 steps_per_episode），干扰类型在同一回合内保持不变。
"""

import sys
import os
import numpy as np

# 将项目根目录添加到 sys.path，确保可以导入上层模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from unified_framework import RadarEnvironment, JammerLoader
from anti_jamming.adapters import get_antijam_func
from rl_framework.config import Config
from rl_framework.utils import (
    preprocess_raw_iq,
    preprocess_range_profile,
    compute_sinr_from_radar_par,
    decode_action,
)


class AntiJamEnv:
    """
    抗干扰强化学习环境 (gym-style interface)。

    状态: {'signal': np.array, 'jammer_onehot': np.array}
    动作: (discrete_idx, continuous_vals)
    """

    def __init__(self, cfg=None):
        """
        参数:
            cfg : Config 实例，为 None 时使用默认配置
        """
        self.cfg = cfg or Config()
        cfg = self.cfg

        # ---- 雷达参数 (调低采样率 / 脉宽 以缩短信号) ----
        radar_params = {
            'f0': cfg.f0,
            'Bw': cfg.Bw,
            'Pw': cfg.Pw,
            'Fs': cfg.Fs,
            'M': 1,
            'N': int(cfg.Tr * cfg.Fs),       # 接收窗长度
            'target_dist': cfg.target_dist,
            'target_amp': cfg.target_amp,
            'jammer_amp': cfg.jammer_amp,
            'JSR_dB': cfg.JSR_dB,
            'noise_var': cfg.noise_var,
        }
        self.radar_env = RadarEnvironment(radar_params)

        # ---- 干扰列表 & 概率 ----
        self.jammer_list = list(cfg.jammer_list)
        self.jammer_probs = cfg.jammer_probs  # None → 等概率

        # ---- 抗干扰列表 ----
        self.antijam_list = list(cfg.antijam_list)
        self.num_discrete_actions = len(self.antijam_list)
        self.max_continuous_dim = cfg.max_continuous_dim

        # ---- 状态参数 ----
        self.state_mode = cfg.state_mode
        self.state_len = cfg.state_len
        self.num_jammers = len(self.jammer_list)

        # ---- 回合控制 ----
        self.steps_per_episode = cfg.steps_per_episode
        self.current_step = 0

        # ---- 奖励权重 ----
        self.sinr_weight = cfg.reward_sinr_weight
        self.detect_weight = cfg.reward_detect_weight

        # ---- 当前回合状态 ----
        self.current_jammer = None
        self.current_jammer_name = None
        self.current_jammer_idx = -1
        self.jammer_onehot = np.zeros(self.num_jammers, dtype=np.float32)
        self.current_radar_par = None
        self.current_signal_state = None

    # -----------------------------------------------------------------
    # 核心接口
    # -----------------------------------------------------------------
    def reset(self):
        """
        重置环境，开始新回合。
        
        返回:
            state : dict {'signal': np.array, 'jammer_onehot': np.array}
        """
        self.current_step = 0

        # 1) 随机选择干扰类型
        idx = np.random.choice(len(self.jammer_list), p=self.jammer_probs)
        self.current_jammer_idx = idx
        self.current_jammer_name = self.jammer_list[idx]
        self.jammer_onehot = np.zeros(self.num_jammers, dtype=np.float32)
        self.jammer_onehot[idx] = 1.0

        # 2) 加载干扰器
        self.current_jammer = JammerLoader.load(
            self.current_jammer_name,
            f0=self.cfg.f0,
            B=self.cfg.Bw,
            T=self.cfg.Pw,
            Tr=self.cfg.Tr,
        )

        # 3) 生成含干扰回波
        self.current_radar_par = self.radar_env.generate_with_jammer(self.current_jammer)

        # 4) 提取状态
        self.current_signal_state = self._extract_state(self.current_radar_par)

        return {
            'signal': self.current_signal_state,
            'jammer_onehot': self.jammer_onehot.copy(),
        }

    def step(self, discrete_idx, continuous_vals):
        """
        执行一步：对当前脉冲进行抗干扰处理。

        参数:
            discrete_idx    : int，抗干扰算法索引
            continuous_vals : numpy array (max_continuous_dim,)，归一化到 [0,1]

        返回:
            state  : dict {'signal': np.array, 'jammer_onehot': np.array}
            reward : float
            done   : bool
            info   : dict
        """
        # 1) 解码动作
        algo_name, param_dict = decode_action(
            discrete_idx, continuous_vals, self.cfg)

        # 2) 计算抗干扰前 SINR
        sinr_before = compute_sinr_from_radar_par(
            self.current_radar_par, ref_cells=self.cfg.cfar_ref_cells)

        # 3) 调用抗干扰适配器
        antijam_func = get_antijam_func(algo_name)
        try:
            processed_signal, processed_template = antijam_func(
                self.current_radar_par, **param_dict)
        except Exception as e:
            # 抗干扰失败，使用原始信号
            processed_signal = self.current_radar_par['Srt_matrix']
            processed_template = self.current_radar_par['St_base']

        # 4) 计算抗干扰后 SINR
        processed_par = dict(self.current_radar_par)
        processed_par['Srt_matrix'] = processed_signal
        processed_par['St_base'] = processed_template
        sinr_after = compute_sinr_from_radar_par(
            processed_par, ref_cells=self.cfg.cfar_ref_cells)

        # 5) 计算奖励: SINR 改善 + 检测成功奖励
        sinr_improvement = sinr_after - sinr_before
        detect_bonus = 0.0
        if sinr_after > self.cfg.cfar_pfa:  # 简化检测判断
            detect_bonus = self.detect_weight

        reward = self.sinr_weight * sinr_improvement + detect_bonus

        # 6) 更新步数
        self.current_step += 1
        done = (self.current_step >= self.steps_per_episode)

        # 7) 生成下一个脉冲状态（保持同一干扰类型）
        if not done:
            self.current_radar_par = self.radar_env.generate_with_jammer(self.current_jammer)
            self.current_signal_state = self._extract_state(self.current_radar_par)
        else:
            self.current_signal_state = self._extract_state(self.current_radar_par)

        info = {
            'algo_name': algo_name,
            'param_dict': param_dict,
            'sinr_before': sinr_before,
            'sinr_after': sinr_after,
            'sinr_improvement': sinr_improvement,
            'jammer_name': self.current_jammer_name,
            'step': self.current_step,
        }

        return {
            'signal': self.current_signal_state,
            'jammer_onehot': self.jammer_onehot.copy(),
        }, reward, done, info

    def render(self, mode='human'):
        """调试可视化：绘制当前脉冲的时域波形和距离像。"""
        if self.current_radar_par is None:
            return
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from scipy import signal as sig

            rx = self.current_radar_par['Srt_matrix'][0]
            ref = self.current_radar_par['St_base']
            target_idx = self.current_radar_par['target_idx']

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4))

            # 时域
            ax1.plot(np.abs(rx), label='|rx signal|')
            ax1.set_title(f'Time domain - {self.current_jammer_name}')
            ax1.set_xlabel('Sample')
            ax1.legend()
            ax1.grid(True)

            # 距离像
            mf = np.conj(ref[::-1])
            pc = sig.fftconvolve(rx, mf, mode='same')
            ax2.plot(20 * np.log10(np.abs(pc) + 1e-10))
            ax2.axvline(target_idx, color='r', ls='--', label='Target')
            ax2.set_title('Range profile')
            ax2.set_xlabel('Range bin')
            ax2.legend()
            ax2.grid(True)

            plt.tight_layout()
            plt.savefig('rl_framework/debug_render.png', dpi=100)
            plt.close()
            print('[env] Debug render saved to rl_framework/debug_render.png')
        except ImportError:
            print('[env] matplotlib not available, skipping render.')

    # -----------------------------------------------------------------
    # 内部方法
    # -----------------------------------------------------------------
    def _extract_state(self, radar_par):
        """
        根据 state_mode 从 radar_par 提取状态数组。
        返回 np.array:
          raw_iq         → (2, state_len)
          range_profile  → (1, state_len)
        """
        rx_signal = radar_par['Srt_matrix'][0]
        ref_signal = radar_par['St_base']

        if self.state_mode == 'raw_iq':
            return preprocess_raw_iq(rx_signal, self.state_len)
        elif self.state_mode == 'range_profile':
            return preprocess_range_profile(rx_signal, ref_signal, self.state_len)
        else:
            raise ValueError(f"Unknown state_mode: {self.state_mode}")

    def get_action_dim(self):
        """返回 (num_discrete, max_continuous_dim)。"""
        return self.num_discrete_actions, self.max_continuous_dim

    def get_signal_shape(self):
        """返回信号部分的形状 (channels, L)。"""
        if self.state_mode == 'raw_iq':
            return (2, self.state_len)
        else:
            return (1, self.state_len)
