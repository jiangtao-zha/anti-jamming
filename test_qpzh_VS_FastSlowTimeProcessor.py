import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift
from jamming.ISDJ import ISRJDirectJam

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# =====================================================================
# 模块 1：快慢时间域抗干扰处理器 (Action 执行器)
# =====================================================================
class FastSlowTimeProcessor:
    def __init__(self, num_pulses, num_samples, limit_factor=3.0):
        self.M = num_pulses
        self.N = num_samples
        self.limit_factor = limit_factor

    def pulse_compression(self, Srt_matrix, ref_signal):
        PC_matrix = np.zeros_like(Srt_matrix, dtype=complex)
        matched_filter = np.conj(ref_signal[::-1])
        for m in range(self.M):
            PC_matrix[m, :] = signal.fftconvolve(Srt_matrix[m, :], matched_filter, mode='same')
        return PC_matrix

    def process(self, Srt_matrix, ref_signal):
        # 快时间域脉压
        PC_matrix = self.pulse_compression(Srt_matrix, ref_signal)
        # 慢时间域 FFT
        window = np.hamming(self.M)[:, None]
        RD_matrix = fftshift(fft(PC_matrix * window, axis=0), axes=0)
        Filtered_RD = RD_matrix.copy()

        # 通道能量评估与自适应挖空
        doppler_energy = np.mean(np.abs(RD_matrix), axis=1)
        global_median_energy = np.median(doppler_energy)
        jammed_channels = doppler_energy > (global_median_energy * self.limit_factor)
        noise_floor = np.median(np.abs(RD_matrix))

        for m in range(self.M):
            if jammed_channels[m]:
                # 整行切除并填充底噪
                Filtered_RD[m, :] = (np.random.randn(self.N) + 
                                     1j * np.random.randn(self.N)) * (noise_floor / np.sqrt(2))

        # 投影回一维距离像
        range_profile_before = np.max(np.abs(RD_matrix), axis=0)
        range_profile_after = np.max(np.abs(Filtered_RD), axis=0)

        return range_profile_before, range_profile_after

# =====================================================================
# 模块 2：统一评价函数 Evaluator (Reward 计算器)
# =====================================================================
class UnifiedEvaluator:
    def __init__(self, guard_cells=4, ref_cells=20, Pfa=1e-5):
        self.guard_cells = guard_cells
        self.ref_cells = ref_cells
        self.Pfa = Pfa

    def ca_cfar_fast(self, mag):
        """向量化极速 CA-CFAR 检测 (RL 必备)"""
        N = len(mag)
        alpha = self.Pfa ** (-1.0 / (2 * self.ref_cells)) - 1
        
        # 构造卷积核 [1..1, 0..0, 1..1]
        kernel_size = 1 + 2 * self.guard_cells + 2 * self.ref_cells
        kernel = np.ones(kernel_size)
        kernel[self.ref_cells : self.ref_cells + 2 * self.guard_cells + 1] = 0
        kernel = kernel / (2 * self.ref_cells)
        
        # 计算背景噪声均值
        mu = signal.correlate(mag, kernel, mode='same', method='fft')
        threshold = alpha * mu
        detections = mag > threshold
        return detections, threshold

    def evaluate(self, range_profile, target_idx, w1=0.5, w2=0.5):
        """
        计算统一的 Reward
        参数:
            range_profile: 处理后的一维距离像幅度
            target_idx: 真实目标在距离像中的预期索引位置
            w1, w2: 检测率和SINR的权重
        """
        detections, thresholds = self.ca_cfar_fast(range_profile)
        
        # 允许目标峰值有轻微偏移 (容差窗口)
        tol = 5 
        start_idx = max(0, target_idx - tol)
        end_idx = min(len(range_profile), target_idx + tol + 1)
        
        # 1. 检测评估 (R_Ed)
        target_region_det = detections[start_idx:end_idx]
        is_detected = np.any(target_region_det)
        R_Ed = 1.0 if is_detected else 0.0
        
        # 2. SINR 评估 (R_ESINR)
        target_peak_power = np.max(range_profile[start_idx:end_idx])**2
        bg_region = range_profile[max(0, start_idx - self.ref_cells) : min(len(range_profile), end_idx + self.ref_cells)]
        interference_power = np.mean(bg_region)**2 + 1e-12
        
        sinr_db = 10 * np.log10(target_peak_power / interference_power)
        
        # 将 SINR 归一化到 [0, 1] 之间 (假设 0dB极差，30dB极好)
        R_ESINR = np.clip((sinr_db - 0.0) / 30.0, 0.0, 1.0)
        if not is_detected:
            R_ESINR = 0.0 # 没检测到则 SINR 奖励清零
            
        # 3. 综合 Reward
        reward = w1 * R_Ed + w2 * R_ESINR
        
        info = {
            'is_detected': is_detected,
            'sinr_db': sinr_db,
            'reward': reward,
            'thresholds': thresholds
        }
        return info

# =====================================================================
# 模块 3：环境生成器 (Env Step 模拟)
# =====================================================================
def generate_isrj_jamming(ref_signal, repeats=4):
    N = len(ref_signal)
    slice_len = N // (repeats * 2)
    jamming = np.zeros(N, dtype=complex)
    for i in range(repeats):
        start = i * (slice_len * 2)
        jamming[start : start + slice_len] = ref_signal[:slice_len]
    return jamming

def env_step(radar_par):
    """根据统一雷达参数生成 CPI 回波矩阵 (模拟环境交互)"""
    Fs, Pw, Bw, M, N = radar_par['Fs'], radar_par['Pw'], radar_par['Bw'], radar_par['M'], radar_par['N']
    Ts = 1 / Fs
    Npw = int(Pw / Ts)
    t_fast = np.arange(0, Npw) * Ts
    
    # 1. 基础波形
    K = Bw / Pw
    St_base = np.exp(1j * 2 * np.pi * (radar_par['f0'] * t_fast + 0.5 * K * t_fast**2))
    Srt_matrix = np.zeros((M, N), dtype=complex)
    
    # 2. 目标与干扰的真实延迟索引 (未经过脉压)
    target_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts)
    jammer_idx = int((radar_par['jammer_dist'] * 2 / 3e8) / Ts)
    
    # 使用统一的 ISRJDirectJam 类生成间歇采样直接转发干扰
    jammer = ISRJDirectJam(
        C=3e8, fc=radar_par['f0'], T=Pw, Tr=100e-6, B=Bw
    )
    
    # 生成干扰信号（包含目标回波和噪声）
    # 注意：这里我们指定一个近似的目标距离来生成干扰
    J_composite, X_t, jam_info = jammer.generate(
        R_target=radar_par['jammer_dist'],  # 使用干扰机距离作为参考
        M=4,  # 转发次数
        JSR_dB=20,  # 高干信比
        noise_var=0.1
    )
    
    # 从复合信号中提取纯干扰部分
    target_signal = jam_info['target_signal']
    noise_signal = jam_info['noise_signal']
    J_base = J_composite - target_signal - noise_signal
    
    # 截取干扰信号的核心部分（通常是中间部分）
    # 找到干扰能量最高的区域
    energy = np.abs(J_base)**2
    max_idx = np.argmax(energy)
    window_start = max(0, max_idx - Npw//2)
    window_end = min(len(J_base), window_start + Npw)
    J_base = J_base[window_start:window_end]
    
    # 如果长度不够，扩展到Npw长度
    if len(J_base) < Npw:
        J_extended = np.zeros(Npw, dtype=complex)
        J_extended[:len(J_base)] = J_base
        J_base = J_extended
    elif len(J_base) > Npw:
        J_base = J_base[:Npw]
    
    # 3. 生成二维回波
    for m in range(M):
        phase_target = np.exp(1j * 2 * np.pi * radar_par['target_fd'] * (m * radar_par['PRT'])) 
        phase_jammer = np.exp(1j * 2 * np.pi * radar_par['jammer_fd'] * (m * radar_par['PRT']))
        
        Srt_matrix[m, target_idx:target_idx+Npw] += St_base * phase_target * radar_par['target_amp']
        Srt_matrix[m, jammer_idx:jammer_idx+Npw] += J_base * phase_jammer * radar_par['jammer_amp']
        Srt_matrix[m, :] += 0.5 * (np.random.randn(N) + 1j * np.random.randn(N))
        
    return Srt_matrix, St_base

# =====================================================================
# 主函数：标准化强化学习对抗流程测试
# =====================================================================
def run_standardized_test():
    # ---------------------------------------------------------
    # 步骤 1: 统一雷达与环境参数初始化 (Env Reset)
    # ---------------------------------------------------------
    radar_par = {
        'f0': 10e6, 'Bw': 5e6, 'Pw': 20e-6, 'Fs': 40e6, 
        'PRF': 1000, 'PRT': 1e-3, 'M': 16,
        'N': int(100e-6 * 40e6), # 100us 接收窗
        'target_dist': 6000,     'target_fd': 500,  'target_amp': 1.0,
        'jammer_dist': 5250,     'jammer_fd': -800, 'jammer_amp': 20.0
    }
    Ts = 1 / radar_par['Fs']
    Npw = int(radar_par['Pw'] / Ts)

    # ---------------------------------------------------------
    # 步骤 2: 环境步进 (获取含干扰的回波状态 Srt_matrix)
    # ---------------------------------------------------------
    Srt_matrix, St_base = env_step(radar_par)

    # ---------------------------------------------------------
    # 步骤 3: 智能体执行动作 (调用抗干扰算法)
    # 这里模拟 RL 输出连续动作 limit_factor = 3.0
    # ---------------------------------------------------------
    action_limit_factor = 3.0
    processor = FastSlowTimeProcessor(radar_par['M'], radar_par['N'], limit_factor=action_limit_factor)
    
    # 执行处理，获取抗干扰前后的距离像
    profile_before, profile_after = processor.process(Srt_matrix, St_base)

    # ---------------------------------------------------------
    # 步骤 4: 统一评价与 Reward 计算
    # ---------------------------------------------------------
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    
    # 【核心对齐】：脉压(mode='same')会导致峰值向右偏移 Npw/2
    # 必须告诉评价函数，目标峰值的正确预期位置在哪里
    expected_target_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts) + Npw // 2
    
    # 评估抗干扰【前】的效果 (仅作对比，RL不需要)
    info_before = evaluator.evaluate(profile_before, expected_target_idx)
    # 评估抗干扰【后】的效果 (这就是传给 CPPO 的 Reward)
    info_after = evaluator.evaluate(profile_after, expected_target_idx)
    
    print("========= 强化学习接口反馈 =========")
    print(f"抗干扰前 -> 检测状态: {info_before['is_detected']}, SINR: {info_before['sinr_db']:.2f} dB")
    print(f"抗干扰后 -> 检测状态: {info_after['is_detected']}, SINR: {info_after['sinr_db']:.2f} dB")
    print(f"当前动作 (limit={action_limit_factor}) 获得 Reward: {info_after['reward']:.4f}")
    print("====================================")

    # ---------------------------------------------------------
    # 步骤 5: 结果可视化验证 (证明对抗成功)
    # ---------------------------------------------------------
    plt.figure(figsize=(15, 8))
    
    # 修正坐标轴使其对应真实距离 (扣除 Npw/2 偏移)
    dist_axis = (np.arange(radar_par['N']) - Npw/2) * (3e8 / (2 * radar_par['Fs'])) / 1000 
    
    plt.subplot(2, 1, 1)
    plt.plot(dist_axis, 20*np.log10(profile_before + 1e-10), label='信号幅度 (仅快时间脉压)', color='gray')
    plt.plot(dist_axis, 20*np.log10(info_before['thresholds'] + 1e-10), label='CA-CFAR 检测阈值', color='orange', linestyle='--')
    plt.axvline(x=radar_par['target_dist']/1000, color='blue', linestyle='-.', label='真实目标位置')
    plt.title(f'抗干扰前检测状态 (目标完全被干扰产生的阈值抬升淹没) - Reward: {info_before["reward"]:.2f}')
    plt.ylabel('幅度 (dB)')
    plt.xlim([4, 10]); plt.ylim([0, 80]); plt.legend(); plt.grid(True)

    plt.subplot(2, 1, 2)
    plt.plot(dist_axis, 20*np.log10(profile_after + 1e-10), label='信号幅度 (快慢时间联合处理后)', color='red')
    plt.plot(dist_axis, 20*np.log10(info_after['thresholds'] + 1e-10), label='CA-CFAR 检测阈值', color='green', linestyle='--')
    plt.axvline(x=radar_par['target_dist']/1000, color='blue', linestyle='-.', label='真实目标位置')
    plt.title(f'抗干扰后检测状态 (目标刺破 CFAR 阈值，检测成功！) - Reward: {info_after["reward"]:.4f}')
    plt.xlabel('距离 (km)'); plt.ylabel('幅度 (dB)')
    plt.xlim([4, 10]); plt.ylim([0, 80]); plt.legend(); plt.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_standardized_test()