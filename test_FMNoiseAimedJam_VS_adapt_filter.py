import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft, fftshift, fftfreq
from jamming.FMNoiseAimedJam import FMNoiseAimedJam

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# =====================================================================
# 模块 1：Ozaktas 快速分数阶傅里叶变换 (FrFT) 核心算法
# =====================================================================
def myfrft(f, a):
    """经典的 Ozaktas 离散分数阶傅里叶变换"""
    f = np.asarray(f, dtype=complex).flatten()
    N = len(f)
    shft = (np.arange(N) + int(np.fix(N / 2))) % N
    sN = np.sqrt(N)
    a = a % 4
    
    if a == 0: return f
    if a == 2: return np.flipud(f)
    if a == 1:
        Faf = np.zeros(N, dtype=complex)
        Faf[shft] = fft(f[shft]) / sN
        return Faf
    if a == 3:
        Faf = np.zeros(N, dtype=complex)
        Faf[shft] = ifft(f[shft]) * sN
        return Faf
        
    if a > 2.0: a, f = a - 2, np.flipud(f)
    if a > 1.5:
        a = a - 1
        f_temp = np.zeros(N, dtype=complex)
        f_temp[shft] = fft(f[shft]) / sN
        f = f_temp
    if a < 0.5:
        a = a + 1
        f_temp = np.zeros(N, dtype=complex)
        f_temp[shft] = ifft(f[shft]) * sN
        f = f_temp

    alpha = a * np.pi / 2
    tana2 = np.tan(alpha / 2)
    sina = np.sin(alpha)
    
    def fconv(x, y):
        N_conv = len(x) + len(y) - 1
        P = 2**int(np.ceil(np.log2(N_conv)))
        z = ifft(fft(x, n=P) * fft(y, n=P))
        return z[:N_conv]

    def interp(x):
        Nx = len(x)
        y = np.zeros(2 * Nx - 1, dtype=x.dtype)
        y[0::2] = x
        idx = np.arange(-(2*Nx - 3), 2*Nx - 2) / 2.0
        xint = fconv(y, np.sinc(idx)) 
        return xint[2*Nx - 3 : 4*Nx - 4]

    f = np.concatenate((np.zeros(N - 1), interp(f), np.zeros(N - 1)))
    idx1 = np.arange(-2*N + 2, 2*N - 1)
    chrp = np.exp(-1j * np.pi / N * tana2 / 4 * (idx1**2))
    f = chrp * f
    c = np.pi / N / sina / 4
    idx2 = np.arange(-(4*N - 4), 4*N - 3)
    Faf = fconv(np.exp(1j * c * (idx2**2)), f)
    Faf = Faf[4*N - 4 : 8*N - 7] * np.sqrt(c / np.pi)
    Faf = chrp * Faf
    Faf = np.exp(-1j * (1 - a) * np.pi / 4) * Faf[N - 1 : 3*N - 2 : 2]
    return Faf

# =====================================================================
# 模块 2：FrFT 抗干扰处理器 (Action 执行器)
# =====================================================================
def FrFT_Processor(Srt_rx, a_opt, mask_width):
    """
    基于 FrFT 的掩膜滤波抗干扰
    参数:
        mask_width: 掩膜宽度 w (RL 智能体输出的连续动作)
    """
    N = len(Srt_rx)
    
    # 1. 变换到最优分数阶域
    Xa = myfrft(Srt_rx, a_opt)
    
    # 2. 寻找峰值并施加矩形掩膜
    u_star = np.argmax(np.abs(Xa))
    mask = np.zeros(N)
    
    # 防止索引越界
    i_start = max(0, u_star - mask_width // 2)
    i_end = min(N, u_star + mask_width // 2 + 1)
    mask[i_start:i_end] = 1.0
    
    Xa_filtered = Xa * mask
    
    # 3. 逆 FrFT 变回时域
    Srt_filtered = myfrft(Xa_filtered, -a_opt)
    
    return Srt_filtered, Xa, mask, u_star

# =====================================================================
# 模块 3：统一评价函数 Evaluator
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
        return mag > alpha * mu, alpha * mu

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
# 模块 4：环境生成器 (生成瞄准式噪声调频干扰)
# =====================================================================
def env_step(radar_par):
    Fs, Pw, Bw, N = radar_par['Fs'], radar_par['Pw'], radar_par['Bw'], radar_par['N']
    Ts = 1 / Fs
    Npw = int(Pw / Ts)
    t_fast = np.arange(Npw) * Ts
    t_rx = np.arange(N) * Ts
    
    # 1. 雷达发射波形 (LFM)
    K = Bw / Pw
    St_base = np.exp(1j * 2 * np.pi * (radar_par['f0'] * t_fast + 0.5 * K * t_fast**2))
    
    # 2. 目标回波
    target_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts)
    Srt_rx = np.zeros(N, dtype=complex)
    Srt_rx[target_idx:target_idx+Npw] = St_base * radar_par['target_amp']
    
    # 3. 使用统一的 FMNoiseAimedJam 类生成瞄准式噪声调频干扰
    jammer = FMNoiseAimedJam(
        C=3e8, f0=radar_par['f0'], T=Pw, Tr=100e-6, B=Bw
    )
    
    # 注意：jammer.Fs 可能与当前 Fs 不同，需要处理采样率匹配
    J_FM, X_t, jam_info = jammer.generate(
        R_target=radar_par['target_dist'],
        JSR_dB=20,  # 高干信比模拟强干扰
        noise_var=0.04
    )
    
    # 从干扰信号中提取干扰部分（不含目标回波和噪声）
    # jam_info 中包含 target_signal 和 noise_signal
    target_signal = jam_info['target_signal']
    noise_signal = jam_info['noise_signal']
    
    # 干扰信号 = 总信号 - 目标回波 - 噪声
    J_Aimed = J_FM - target_signal - noise_signal
    
    # 调整干扰幅度
    J_Aimed *= radar_par['jammer_amp'] / np.max(np.abs(J_Aimed) + 1e-10)
    
    # 将干扰添加到接收信号中
    # 注意：需要确保长度匹配
    len_to_use = min(len(J_Aimed), len(Srt_rx))
    Srt_rx[:len_to_use] += J_Aimed[:len_to_use]
    
    # 添加额外的噪声
    noise = 0.2 * (np.random.randn(N) + 1j * np.random.randn(N))
    Srt_rx += noise
    
    return Srt_rx, St_base

# =====================================================================
# 主测试函数
# =====================================================================
def run_frft_antijamming_test():
    radar_par = {
        'f0': 15e6, 'Bw': 5e6, 'Pw': 20e-6, 'Fs': 40e6, 
        'N': int(100e-6 * 40e6), 'target_dist': 6000, 
        'target_amp': 1.0, 'jammer_amp': 12.0 # 极强的瞄准式干扰
    }
    Ts = 1 / radar_par['Fs']
    Npw = int(radar_par['Pw'] / Ts)
    expected_peak_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts) + Npw // 2

    print("正在生成雷达信号与 [瞄准式噪声调频干扰]...")
    Srt_orig, St_base = env_step(radar_par)

    # 1. 自动搜索最优分数阶 a_opt (根据纯净模板)
    # 在实际系统中，雷达发射的 K 是已知的，a_opt 可以直接查表，这里用快速搜索模拟
    a_vals = np.linspace(0.8, 1.2, 41)
    peaks = [np.max(np.abs(myfrft(St_base, a))) for a in a_vals]
    a_opt = a_vals[np.argmax(peaks)]
    print(f"解析到目标最优分数阶 a_opt = {a_opt:.4f}")

    # 2. 智能体执行动作：FrFT 掩膜滤波
    # 模拟 Actor 输出连续动作：掩膜宽度 mask_width = 30
    action_mask_width = 30
    print(f"智能体下发最优指令 -> FrFT 掩膜宽度 w = {action_mask_width}")
    
    Srt_filtered, Xa_jammed, mask, u_star = FrFT_Processor(Srt_orig, a_opt, action_mask_width)

    # 3. 脉冲压缩
    pc_orig = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')
    pc_filtered = signal.fftconvolve(Srt_filtered, np.conj(St_base[::-1]), mode='same')

    # 4. 评价与反馈
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    info_orig = evaluator.evaluate(np.abs(pc_orig), expected_peak_idx)
    info_filtered = evaluator.evaluate(np.abs(pc_filtered), expected_peak_idx)
    
    print(f"抗干扰前 -> 状态: {info_orig['is_detected']}, SINR: {info_orig['sinr_db']:.2f} dB")
    print(f"抗干扰后 -> 状态: {info_filtered['is_detected']}, SINR: {info_filtered['sinr_db']:.2f} dB")
    print(f">>> 智能体获得最终 Reward: {info_filtered['reward']:.4f}")

    # ================= 绘图 =================
    plt.figure(figsize=(16, 12))
    dist_axis = (np.arange(radar_par['N']) - Npw/2) * (3e8 / (2 * radar_par['Fs'])) / 1000 

    # 图 1：分数阶傅里叶域 (最核心的物理展示)
    plt.subplot(3, 1, 1)
    Xa_clean = myfrft(np.pad(St_base, (radar_par['N'] - Npw)//2), a_opt) # 对齐画个参考
    plt.plot(np.abs(Xa_jammed), label=f'受干扰信号在 a={a_opt:.3f} 域 (干扰能量弥散)', color='gray', alpha=0.7)
    
    # 标出 Mask 区域
    plt.axvspan(u_star - action_mask_width//2, u_star + action_mask_width//2, color='red', alpha=0.3, label=f'智能体决策掩膜 (w={action_mask_width})')
    plt.plot(np.abs(Xa_jammed * mask), label='掩膜提取出的目标能量', color='red')
    
    plt.title(f'1. 分数阶傅里叶域 (FrFT) 对比：LFM 目标聚集成峰，FM 干扰被摊平剥离')
    plt.xlabel('FrFT 采样点索引'); plt.ylabel('幅度'); plt.legend(loc='upper right'); plt.grid(True)

    # 图 2：接收信号时频图
    plt.subplot(3, 1, 2)
    nperseg = int((radar_par['Pw'] / 8) / Ts) // 2 
    f_stft, t_stft, Zxx = signal.spectrogram(Srt_orig, fs=radar_par['Fs'], window='hann', nperseg=nperseg, noverlap=nperseg-2, return_onesided=False)
    f_stft, Zxx = fftshift(f_stft), fftshift(Zxx, axes=0)
    plt.pcolormesh(t_stft * 1e6, f_stft / 1e6, 10 * np.log10(np.abs(Zxx) + 1e-10), shading='auto', cmap='jet')
    plt.title('2. 接收窗时频图：瞄准式干扰完全覆盖了雷达的中心频率和工作带宽 (传统滤波器失效)')
    plt.xlabel('时间 (us)'); plt.ylabel('频率 (MHz)'); plt.ylim([0, 30])

    # 图 3：最终距离像验证
    plt.subplot(3, 1, 3)
    plt.plot(dist_axis, 20*np.log10(np.abs(pc_orig) + 1e-10), label='仅脉冲压缩 (真实目标完全淹没)', color='gray', alpha=0.5)
    plt.plot(dist_axis, 20*np.log10(np.abs(pc_filtered) + 1e-10), label='FrFT 掩膜提纯 + 脉压 (目标脱颖而出)', color='red', linewidth=2)
    plt.plot(dist_axis, 20*np.log10(info_filtered['thresholds'] + 1e-10), label='CA-CFAR 检测阈值', color='green', linestyle='--')
    plt.axvline(x=radar_par['target_dist']/1000, color='blue', linestyle='-.', label='真实目标位置 (6.0 km)')
    
    plt.title(f'3. 距离像检测验证：降维打击成功，SINR 跃升至 {info_filtered["sinr_db"]:.2f} dB！Reward: {info_filtered["reward"]:.4f}')
    plt.xlabel('距离 (km)'); plt.ylabel('幅度 (dB)'); plt.xlim([4.5, 7.5]); plt.ylim([0, 80]); plt.legend(loc='upper right'); plt.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_frft_antijamming_test()