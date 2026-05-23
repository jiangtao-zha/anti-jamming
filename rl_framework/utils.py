"""
rl_framework/utils.py
=====================
经验回放缓冲区、状态预处理、SINR 计算、动作解码等工具函数。
"""

import numpy as np
from scipy import signal
import torch


# =====================================================================
# 1. 经验回放缓冲区
# =====================================================================
class RolloutBuffer:
    """
    存储一个 rollout（多条轨迹片段）的数据，用于 PPO 更新。
    每条记录对应一个 (s, a, log_prob, r, done, V) 元组。
    """

    def __init__(self):
        self.signals = []       # 原始信号状态
        self.jammer_onehots = []  # 干扰 one-hot
        self.discrete_actions = []  # 离散动作索引 (int)
        self.continuous_actions = []  # 连续动作 (np.array)
        self.logprobs = []      # 动作对数概率 (float)
        self.rewards = []       # 奖励
        self.dones = []         # 是否结束
        self.values = []        # V(s)

    def store(self, signal_state, jammer_onehot, discrete_action,
              continuous_action, logprob, reward, done, value):
        self.signals.append(signal_state)
        self.jammer_onehots.append(jammer_onehot)
        self.discrete_actions.append(discrete_action)
        self.continuous_actions.append(continuous_action)
        self.logprobs.append(logprob)
        self.rewards.append(reward)
        self.dones.append(done)
        self.values.append(value)

    def get_tensors(self, device):
        """
        将缓冲区数据转为 torch.Tensor 并移至 device。
        返回字典形式的 mini-batch 数据。
        """
        signals = torch.tensor(np.array(self.signals), dtype=torch.float32).to(device)
        onehots = torch.tensor(np.array(self.jammer_onehots), dtype=torch.float32).to(device)
        discrete_actions = torch.tensor(self.discrete_actions, dtype=torch.long).to(device)
        continuous_actions = torch.tensor(
            np.array(self.continuous_actions), dtype=torch.float32).to(device)
        logprobs = torch.tensor(self.logprobs, dtype=torch.float32).to(device)
        rewards = torch.tensor(self.rewards, dtype=torch.float32).to(device)
        dones = torch.tensor(self.dones, dtype=torch.float32).to(device)
        values = torch.tensor(self.values, dtype=torch.float32).to(device)

        return {
            'signals': signals,
            'jammer_onehots': onehots,
            'discrete_actions': discrete_actions,
            'continuous_actions': continuous_actions,
            'logprobs': logprobs,
            'rewards': rewards,
            'dones': dones,
            'values': values,
        }

    def __len__(self):
        return len(self.rewards)

    def clear(self):
        self.signals.clear()
        self.jammer_onehots.clear()
        self.discrete_actions.clear()
        self.continuous_actions.clear()
        self.logprobs.clear()
        self.rewards.clear()
        self.dones.clear()
        self.values.clear()


# =====================================================================
# 2. 状态预处理
# =====================================================================
def preprocess_raw_iq(rx_signal, target_len):
    """
    将复数信号转换为 (2, L) 的双通道实数矩阵。

    使用幅度+相位表示（保留幅度信息，便于 CNN 区分干扰强度）:
      通道0: 归一化幅度 |x| / max(|x|)
      通道1: 归一化相位 angle(x) / π ∈ [-1, 1]

    参数:
        rx_signal  : 1D 复数 numpy 数组，长度 N
        target_len : 目标长度 L

    返回:
        state : numpy float32 数组，形状 (2, L)
    """
    mag = np.abs(rx_signal).astype(np.float32)
    phase = np.angle(rx_signal).astype(np.float32)

    # 幅度 max 归一化（保留相对功率）
    mag_max = mag.max()
    if mag_max > 1e-10:
        mag /= mag_max

    # 相位归一化到 [-1, 1]
    phase /= np.pi

    N = len(mag)
    state = np.zeros((2, target_len), dtype=np.float32)

    if N >= target_len:
        start = (N - target_len) // 2
        state[0] = mag[start:start + target_len]
        state[1] = phase[start:start + target_len]
    else:
        start = (target_len - N) // 2
        state[0, start:start + N] = mag
        state[1, start:start + N] = phase

    return state


def preprocess_range_profile(rx_signal, ref_signal, target_len):
    """
    计算脉冲压缩后的距离像幅度，归一化并调整长度。
    
    参数:
        rx_signal   : 1D 复数接收信号
        ref_signal  : 1D 复数参考信号（匹配滤波模板）
        target_len  : 目标长度 L

    返回:
        state : numpy float32 数组，形状 (1, L)
    """
    matched_filter = np.conj(ref_signal[::-1])
    compressed = signal.fftconvolve(rx_signal, matched_filter, mode='same')
    magnitude = np.abs(compressed).astype(np.float32)

    # 归一化
    mag_max = magnitude.max()
    if mag_max > 1e-10:
        magnitude /= mag_max

    N = len(magnitude)
    state = np.zeros((1, target_len), dtype=np.float32)

    if N >= target_len:
        start = (N - target_len) // 2
        state[0] = magnitude[start:start + target_len]
    else:
        start = (target_len - N) // 2
        state[0, start:start + N] = magnitude

    return state


# =====================================================================
# 3. SINR 计算
# =====================================================================
def compute_sinr_db(rx_signal, ref_signal, target_idx, ref_cells=20):
    """
    计算匹配滤波后的峰值 SINR (dB)。

    参数:
        rx_signal   : 1D 复数接收信号
        ref_signal  : 1D 复数参考信号
        target_idx  : 目标在接收窗中的索引
        ref_cells   : 旁瓣参考单元数量

    返回:
        sinr_db : float，峰值 SINR (dB)
    """
    matched_filter = np.conj(ref_signal[::-1])
    compressed = signal.fftconvolve(rx_signal, matched_filter, mode='same')
    mag = np.abs(compressed)

    N = len(mag)
    tol = 10
    start = max(0, target_idx - tol)
    end = min(N, target_idx + tol + 1)

    # 目标峰值功率
    target_peak_power = np.max(mag[start:end]) ** 2

    # 背景干扰功率（目标附近旁瓣区域均值）
    bg_start = max(0, start - ref_cells)
    bg_end = min(N, end + ref_cells)
    bg_region = mag[bg_start:bg_end]
    bg_mean = np.mean(bg_region) ** 2 + 1e-12

    sinr_db = 10 * np.log10(target_peak_power / bg_mean)
    return sinr_db


def compute_sinr_from_radar_par(radar_par, ref_cells=20):
    """
    从 radar_par 字典直接计算 SINR。

    参数:
        radar_par : 包含 'Srt_matrix', 'St_base', 'target_idx' 的字典

    返回:
        sinr_db : float
    """
    rx_signal = radar_par['Srt_matrix'][0]
    ref_signal = radar_par['St_base']
    target_idx = radar_par['target_idx']
    return compute_sinr_db(rx_signal, ref_signal, target_idx, ref_cells)


# =====================================================================
# 4. 动作解码
# =====================================================================
def decode_action(algo_idx, continuous_vals, config):
    """
    将网络输出的离散索引 + 连续参数 [0,1] 解码为实际算法名称和参数字典。

    参数:
        algo_idx         : int，离散动作索引（对应 config.antijam_list）
        continuous_vals  : numpy array，归一化到 [0,1] 的连续参数
        config           : Config 实例

    返回:
        algo_name  : str，抗干扰算法名称
        param_dict : dict，传递给适配器的 kwargs
    """
    algo_name = config.antijam_list[algo_idx]
    param_info = config.algo_param_map.get(algo_name, (0, []))
    dim, ranges = param_info

    param_dict = {}

    if algo_name == 'WLN':
        # par1: threshold, par2: fixed=6
        param_dict['par1'] = float(np.clip(continuous_vals[0], 0, 1) * (ranges[0][1] - ranges[0][0]) + ranges[0][0])
        param_dict['par2'] = 6

    elif algo_name == 'FrequencyDomainCanceller':
        # use_fitted_freq: 0 or 1 based on continuous val
        param_dict['use_fitted_freq'] = bool(continuous_vals[0] > 0.5)
        param_dict['f0_fixed'] = 2 * np.pi * config.f0

    elif algo_name == 'adapt_filter':
        param_dict['par1'] = float(np.clip(continuous_vals[0], 0, 1) * (ranges[0][1] - ranges[0][0]) + ranges[0][0])
        param_dict['par2'] = None

    elif algo_name == 'frft_filter':
        # mask_threshold: 模板归一化幅度阈值，控制 FrFT 掩膜宽度
        param_dict['mask_threshold'] = float(
            np.clip(continuous_vals[0], 0, 1) * (ranges[0][1] - ranges[0][0]) + ranges[0][0]
        )

    elif algo_name == 'qpzh':
        # m: segments, n: fixed threshold multiplier
        m = int(np.clip(continuous_vals[0], 0, 1) * (ranges[0][1] - ranges[0][0]) + ranges[0][0])
        param_dict['m'] = max(2, m)
        param_dict['n'] = 3.0

    elif algo_name == 'FastSlowTimeProcessor':
        limit = float(np.clip(continuous_vals[0], 0, 1) * (ranges[0][1] - ranges[0][0]) + ranges[0][0])
        param_dict['limit_factor'] = limit

    return algo_name, param_dict


# =====================================================================
# 5. 数值稳定辅助
# =====================================================================
def set_seed(seed):
    """设置随机种子以确保可复现性。"""
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_device(device_str):
    """
    解析 device 字符串。
    'auto' → cuda if available else cpu
    """
    if device_str == 'auto':
        if torch.cuda.is_available():
            return torch.device('cuda')
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return torch.device('mps')
        return torch.device('cpu')
    return torch.device(device_str)
