import numpy as np
from scipy import signal

class JamSuppressionEvaluator:
    """
    抗干扰效果评估类 (专为强化学习环境优化)
    极速计算脉冲压缩、CA-CFAR检测，并直接输出 RL 所需的综合奖励 (Reward)。
    """

    def __init__(self, fs, T, C=3e8):
        self.fs = fs
        self.T = T
        self.C = C

    def generate_ref_signal(self, f0, K, T=None):
        if T is None:
            T = self.T
        N = int(np.round(T * self.fs))
        t = np.linspace(0, T, N, endpoint=False)
        return np.exp(1j * (np.pi * K * t**2 + 2 * np.pi * f0 * t))

    def pulse_compression(self, rx_signal, ref_signal):
        """
        使用 fftconvolve 进行极速脉冲压缩
        """
        matched_filter = np.conj(ref_signal[::-1])
        # fftconvolve 比常规 convolve 在处理长序列时快几十倍
        compressed = signal.fftconvolve(rx_signal, matched_filter, mode='same')
        return compressed

    def ca_cfar_fast(self, mag, guard_cells=2, ref_cells=16, Pfa=1e-6):
        """
        【核心优化】：向量化 CA-CFAR 检测
        使用一维卷积替代 for 循环，速度提升百倍以上，极大缩短 RL 训练时间。
        """
        N = len(mag)
        alpha = Pfa ** (-1.0 / (2 * ref_cells)) - 1
        
        # 构造 CFAR 滑动窗口卷积核
        # 结构: [1,1..,1, 0,0..,0, 1,1..,1] (参考单元为1，保护单元和待测单元为0)
        kernel_size = 1 + 2 * guard_cells + 2 * ref_cells
        kernel = np.ones(kernel_size)
        kernel[ref_cells : ref_cells + 2 * guard_cells + 1] = 0
        kernel = kernel / (2 * ref_cells) # 归一化求均值
        
        # 边界处理：使用 'constant' 填充避免边缘误报
        mu = signal.correlate(mag, kernel, mode='same', method='fft')
        
        threshold = alpha * mu
        detections = mag > threshold
        
        return detections, threshold

    def evaluate_reward(self, rx_signal, ref_signal, target_tau, 
                        guard_cells=2, ref_cells=16, Pfa=1e-6, 
                        w1=0.5, w2=0.5):
        """
        针对 CPPO 单步交互 (Step) 的评估与奖励计算函数。
        
        参数:
            rx_signal : 单个时间步接收到的复数信号 (对消/抗干扰后的基带信号)
            ref_signal: 参考信号 (模板)
            target_tau: 真实目标的时延 (s)，用于定位检测窗口
            w1, w2    : 论文公式 r_t = w1*R_Ed + w2*R_ESINR 中的权重
            
        返回:
            reward    : 综合奖励值 r_t
            info      : 包含详细评估指标的字典 (供可视化和 Log 使用)
        """
        # 1. 脉冲压缩
        compressed = self.pulse_compression(rx_signal, ref_signal)
        mag = np.abs(compressed)
        
        # 2. 快速 CA-CFAR 检测
        detections, thresholds = self.ca_cfar_fast(mag, guard_cells, ref_cells, Pfa)
        
        # 3. 目标位置定位 (允许一定误差，通常为脉宽倒数对应的距离单元)
        # 根据时延计算目标在接收窗中的理论索引
        idx_target = int(np.round(target_tau * self.fs))
        
        # 容差范围 (例如容忍 5 个采样点的偏移)
        tol = 5 
        start_idx = max(0, idx_target - tol)
        end_idx = min(len(mag), idx_target + tol + 1)
        
        # 4. 计算检测奖励 R_Ed (0 或 1)
        target_region_det = detections[start_idx:end_idx]
        is_detected = np.any(target_region_det)
        R_Ed = 1.0 if is_detected else 0.0
        
        # 5. 计算脉压后局部信干噪比 (Post-PC SINR)
        # 提取目标峰值功率
        target_peak_power = np.max(mag[start_idx:end_idx])**2
        
        # 提取目标周围参考单元的干扰+噪声平均功率
        # 借用 CFAR 的背景均值 mu 计算局部底噪功率
        local_bg_mu = np.mean(mag[max(0, start_idx-ref_cells) : min(len(mag), end_idx+ref_cells)])
        interference_power = local_bg_mu**2 + 1e-12 # 防止除零
        
        sinr_linear = target_peak_power / interference_power
        sinr_db = 10 * np.log10(sinr_linear)
        
        # 6. SINR 奖励归一化 R_ESINR
        # 强化学习中，奖励最好限制在 [0, 1] 或 [-1, 1] 之间。
        # 假设脉压后极好的 SINR 是 30dB，极差是 0dB (刚好被淹没)。我们将其线性映射到 [0, 1]。
        sinr_max = 30.0
        sinr_min = 5.0
        R_ESINR = np.clip((sinr_db - sinr_min) / (sinr_max - sinr_min), 0.0, 1.0)
        
        # 如果连目标都没检测到，ESINR 奖励强行清零（惩罚无效抗干扰）
        if not is_detected:
            R_ESINR = 0.0
            
        # 7. 计算总奖励 (带入你论文的公式)
        reward = w1 * R_Ed + w2 * R_ESINR
        
        # 打包调试信息
        info = {
            'is_detected': is_detected,
            'sinr_db': sinr_db,
            'R_Ed': R_Ed,
            'R_ESINR': R_ESINR,
            'target_idx': idx_target
        }
        
        return reward, info