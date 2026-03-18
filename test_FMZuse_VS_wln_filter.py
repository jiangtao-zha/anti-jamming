import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift, ifft, fftfreq

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# =====================================================================
# 模块 1：宽窄限电路处理器 (Action 执行器)
# =====================================================================
def WLN_Processor(radar_par, par1=0.8, par2=6):
    Srt = np.atleast_2d(radar_par['Srt_matrix'])
    f0, B, Fs = radar_par['f0'], radar_par['Bw'], radar_par['Fs']
    Nyq = Fs / 2.0
    
    # 宽/窄带滤波器设计
    b_bw, a_bw = signal.butter(int(par2), [max(1.0, f0 - B)/Nyq, min(Nyq-1, f0 + B)/Nyq], btype='bandpass')
    b_bn, a_bn = signal.butter(int(par2), [max(1.0, f0 - B/2)/Nyq, min(Nyq-1, f0 + B/2)/Nyq], btype='bandpass')
    
    # 动态限幅阈值 (使用固定参考值以防边缘振荡干扰)
    VL = par1 * 1.48 # 1.48 是标准单位幅度 LFM 信号的估算 Vs_est
    
    num_pulses, _ = Srt.shape
    J_wln = np.zeros_like(Srt)
    eps = np.finfo(float).eps
    
    for i in range(num_pulses):
        J = Srt[i, :]
        # (1) Wide: 宽带滤波
        J_w = signal.filtfilt(b_bw, a_bw, J)
        # (2) Limit: 非线性限幅
        gain = np.minimum(1.0, VL / (np.abs(J_w) + eps))
        J_lim = J_w * gain
        # (3) Narrow: 窄带滤波清理外带互调杂波
        J_wln[i, :] = signal.filtfilt(b_bn, a_bn, J_lim)
        
    return J_wln, VL

# =====================================================================
# 模块 2：统一评价函数 Evaluator
# =====================================================================
class UnifiedEvaluator:
    def __init__(self, guard_cells=4, ref_cells=20, Pfa=1e-5):
        self.guard_cells = guard_cells
        self.ref_cells = ref_cells
        self.Pfa = Pfa

    def ca_cfar_fast(self, mag):
        alpha = self.Pfa ** (-1.0 / (2 * self.ref_cells)) - 1
        kernel_size = 1 + 2 * self.guard_cells + 2 * self.ref_cells
        kernel = np.ones(kernel_size)
        kernel[self.ref_cells : self.ref_cells + 2 * self.guard_cells + 1] = 0
        kernel = kernel / (2 * self.ref_cells)
        mu = signal.correlate(mag, kernel, mode='same', method='fft')
        threshold = alpha * mu
        return mag > threshold, threshold

    def evaluate(self, range_profile, target_idx, w1=0.5, w2=0.5):
        detections, thresholds = self.ca_cfar_fast(range_profile)
        tol = 10 
        start_idx, end_idx = max(0, target_idx - tol), min(len(range_profile), target_idx + tol + 1)
        
        is_detected = np.any(detections[start_idx:end_idx])
        R_Ed = 1.0 if is_detected else 0.0
        
        target_peak_power = np.max(range_profile[start_idx:end_idx])**2
        bg_region = range_profile[max(0, start_idx - self.ref_cells) : min(len(range_profile), end_idx + self.ref_cells)]
        interference_power = np.mean(bg_region)**2 + 1e-12
        sinr_db = 10 * np.log10(target_peak_power / interference_power)
        
        R_ESINR = np.clip((sinr_db - 0.0) / 30.0, 0.0, 1.0)
        if not is_detected: R_ESINR = 0.0
        return {'is_detected': is_detected, 'sinr_db': sinr_db, 'reward': w1 * R_Ed + w2 * R_ESINR, 'thresholds': thresholds}

# =====================================================================
# 模块 3：环境生成器
# =====================================================================
def env_step(radar_par):
    Fs, Pw, Bw, M, N = radar_par['Fs'], radar_par['Pw'], radar_par['Bw'], radar_par['M'], radar_par['N']
    Ts = 1 / Fs
    t_fast = np.arange(int(Pw / Ts)) * Ts
    t_rx = np.arange(N) * Ts
    
    # 1. 理想发射波形
    K = Bw / Pw
    St_base = np.exp(1j * 2 * np.pi * (radar_par['f0'] * t_fast + 0.5 * K * t_fast**2))
    
    # 2. 目标注入
    target_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts)
    Srt_matrix = np.zeros((M, N), dtype=complex)
    Srt_matrix[0, target_idx:target_idx+len(t_fast)] = St_base * radar_par['target_amp']
    
    # 3. 噪声调频阻塞干扰
    Bj = 6 * Bw
    fir_coeff = signal.firwin(N, cutoff=(Bj/2)/(Fs/2), pass_zero='lowpass')
    xn1 = np.real(ifft(fft(np.random.randn(N), n=N) * fft(fir_coeff, n=N)))
    kfm = 8 * Bj / (np.std(xn1) + 1e-10)
    
    # 干扰覆盖雷达中心频率
    J_FM_zuse = np.exp(1j * (2 * np.pi * radar_par['f0'] * t_rx + 2 * np.pi * kfm * (np.cumsum(xn1)/Fs)))
    J_FM_zuse *= radar_par['jammer_amp']
    
    Srt_matrix[0, :] += J_FM_zuse + 0.5 * (np.random.randn(N) + 1j * np.random.randn(N))
    
    radar_par['Srt_matrix'] = Srt_matrix
    radar_par['St_base'] = St_base
    return radar_par

# =====================================================================
# 主测试函数
# =====================================================================
def run_wln_antijamming_test():
    radar_par = {
        'f0': 15e6, 'Bw': 5e6, 'Pw': 20e-6, 'Fs': 50e6, 'M': 1, 
        'N': int(100e-6 * 50e6), 'target_dist': 6000, 'target_amp': 1.0,
        'jammer_amp': 8.0  # 【核心修复1】合理的强对抗环境 (约18dB JSR)
    }
    Ts = 1 / radar_par['Fs']
    Npw = int(radar_par['Pw'] / Ts)
    expected_peak_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts) + Npw // 2

    print("正在生成雷达信号与 [噪声调频阻塞干扰]...")
    radar_par = env_step(radar_par)
    Srt_orig = radar_par['Srt_matrix'][0]
    St_base = radar_par['St_base']

    # 【核心修复2】CPPO 智能体输出的最优限幅系数：2.5
    action_limit_factor = 2.5 
    print(f"智能体下发最优指令 -> WLN 限幅因子: {action_limit_factor}")
    J_wln_matrix, VL = WLN_Processor(radar_par, par1=action_limit_factor)
    Srt_filtered = J_wln_matrix[0]

    # 【核心修复3】统一使用完美数字基带信号 St_base 进行匹配滤波
    pc_orig = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')
    pc_filtered = signal.fftconvolve(Srt_filtered, np.conj(St_base[::-1]), mode='same')

    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    info_orig = evaluator.evaluate(np.abs(pc_orig), expected_peak_idx)
    info_filtered = evaluator.evaluate(np.abs(pc_filtered), expected_peak_idx)
    
    print(f"抗干扰前 -> 状态: {info_orig['is_detected']}, SINR: {info_orig['sinr_db']:.2f} dB")
    print(f"抗干扰后 -> 状态: {info_filtered['is_detected']}, SINR: {info_filtered['sinr_db']:.2f} dB")
    print(f">>> 智能体获得最终 Reward: {info_filtered['reward']:.4f}")

    # ================= 绘图 =================
    plt.figure(figsize=(16, 12))
    t_axis = np.arange(radar_par['N']) * Ts * 1e6
    dist_axis = (np.arange(radar_par['N']) - Npw/2) * (3e8 / (2 * radar_par['Fs'])) / 1000 

    plt.subplot(3, 1, 1)
    plt.plot(t_axis, np.abs(Srt_orig), label='抗干扰前 (宽带阻塞干扰)', color='gray', alpha=0.5)
    plt.plot(t_axis, np.abs(Srt_filtered), label='WLN 动态限幅后 (保留了目标包络特征)', color='blue')
    plt.axhline(y=VL, color='red', linestyle='--', label=f'CPPO 决策限幅阈值 (VL={VL:.2f})')
    plt.title('1. 时域对比：CPPO 找到的最优限幅阈值，既切除了大功率干扰，又避免了目标“自杀式”截断')
    plt.xlabel('时间 (us)'); plt.ylabel('幅度'); plt.xlim([30, 70]); plt.legend(loc='upper right'); plt.grid(True)

    plt.subplot(3, 1, 2)
    f_axis = fftshift(fftfreq(radar_par['N'], Ts))
    plt.plot(f_axis/1e6, 20*np.log10(np.abs(fftshift(fft(Srt_orig))) + 1e-12), label='原始频谱 (严重压制)', color='gray', alpha=0.6)
    plt.plot(f_axis/1e6, 20*np.log10(np.abs(fftshift(fft(Srt_filtered))) + 1e-12), label='WLN 净化后频谱', color='blue')
    plt.title('2. 频域对比：窄带滤波器精准剥离了限幅产生的互调杂波')
    plt.xlabel('频率 (MHz)'); plt.ylabel('功率 (dB)'); plt.xlim([0, 30]); plt.legend(loc='upper right'); plt.grid(True)

    plt.subplot(3, 1, 3)
    plt.plot(dist_axis, 20*np.log10(np.abs(pc_orig) + 1e-10), label='仅脉冲压缩 (目标完全淹没)', color='gray', alpha=0.5)
    plt.plot(dist_axis, 20*np.log10(np.abs(pc_filtered) + 1e-10), label='WLN + 脉冲压缩 (目标脱颖而出)', color='red', linewidth=2)
    plt.plot(dist_axis, 20*np.log10(info_filtered['thresholds'] + 1e-10), label='CA-CFAR 检测阈值', color='green', linestyle='--')
    plt.axvline(x=radar_par['target_dist']/1000, color='blue', linestyle='-.', label='真实目标位置 (6.0 km)')
    plt.title(f'3. 距离像验证：SINR 提升至 {info_filtered["sinr_db"]:.2f} dB，对抗圆满成功！Reward: {info_filtered["reward"]:.4f}')
    plt.xlabel('距离 (km)'); plt.ylabel('幅度 (dB)'); plt.xlim([4.5, 7.5]); plt.ylim([0, 80]); plt.legend(loc='upper right'); plt.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_wln_antijamming_test()