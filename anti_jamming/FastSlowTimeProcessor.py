import numpy as np
from scipy import signal
from scipy.fft import fft, fftshift
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

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
        # 1. 快时间域脉压
        PC_matrix = self.pulse_compression(Srt_matrix, ref_signal)
        
        # 2. 慢时间域 FFT
        window = np.hamming(self.M)[:, None]
        RD_matrix = fftshift(fft(PC_matrix * window, axis=0), axes=0)
        Filtered_RD = RD_matrix.copy()

        # 3. 评估多普勒通道能量
        doppler_energy = np.mean(np.abs(RD_matrix), axis=1)
        global_median_energy = np.median(doppler_energy)
        
        # 识别被干扰严重污染的通道 (整行识别)
        jammed_channels = doppler_energy > (global_median_energy * self.limit_factor)
        noise_floor = np.median(np.abs(RD_matrix))

        # 【核心修复 2：整行通道切除】
        for m in range(self.M):
            if jammed_channels[m]:
                # 一旦通道被切片干扰霸占，直接将整个通道“挖空”，替换为系统底噪
                # 斩草除根，杜绝任何裙边旁瓣在后续投影中作祟
                Filtered_RD[m, :] = (np.random.randn(self.N) + 
                                     1j * np.random.randn(self.N)) * (noise_floor / np.sqrt(2))

        # 4. 投影回一维距离像用于检测
        range_profile_before = np.max(np.abs(RD_matrix), axis=0)
        range_profile_after = np.max(np.abs(Filtered_RD), axis=0)

        return RD_matrix, Filtered_RD, range_profile_before, range_profile_after

# ==========================================
# 闭环测试脚本
# ==========================================
def generate_isrj_jamming(ref_signal, repeats=4):
    N = len(ref_signal)
    slice_len = N // (repeats * 2)
    jamming = np.zeros(N, dtype=complex)
    sig_slice = ref_signal[:slice_len]
    for i in range(repeats):
        start = i * (slice_len * 2)
        end = start + slice_len
        if end <= N:
            jamming[start:end] = sig_slice
    return jamming

def run_test():
    f0, Bw, Pw, Fs = 10e6, 5e6, 20e-6, 40e6
    Ts = 1 / Fs
    M, N, Npw = 16, int(100e-6 / Ts), int(Pw / Ts)
    t_fast = np.arange(0, Npw) * Ts
    
    K = Bw / Pw
    St_base = np.exp(1j * 2 * np.pi * (f0 * t_fast + 0.5 * K * t_fast**2))
    Srt_matrix = np.zeros((M, N), dtype=complex)
    
    # 真实目标参数
    target_dist = 6000 # 6.0 km
    target_delay_idx = int((target_dist * 2 / 3e8) / Ts) # 理论应为 1600
    target_fd = 500 
    
    # 伴随干扰机参数
    jammer_delay_idx = target_delay_idx - 50 
    jammer_fd = -800 
    
    J_base = generate_isrj_jamming(St_base, repeats=4)
    
    for m in range(M):
        phase_target = np.exp(1j * 2 * np.pi * target_fd * (m * 1e-3)) 
        phase_jammer = np.exp(1j * 2 * np.pi * jammer_fd * (m * 1e-3))
        
        # 目标注入 (能量极弱)
        Srt_matrix[m, target_delay_idx:target_delay_idx+Npw] += St_base * phase_target * 1.0
        # 切片干扰注入 (能量极强)
        Srt_matrix[m, jammer_delay_idx:jammer_delay_idx+Npw] += J_base * phase_jammer * 20.0
        # 底噪
        Srt_matrix[m, :] += 0.5 * (np.random.randn(N) + 1j * np.random.randn(N))

    processor = FastSlowTimeProcessor(num_pulses=M, num_samples=N, limit_factor=3.0)
    RD_orig, RD_filtered, profile_before, profile_after = processor.process(Srt_matrix, St_base)

    # ================= 绘图展示 =================
    plt.figure(figsize=(16, 10))
    
    # 【核心修复 1：X轴距离校准】扣除匹配滤波带来的 Pw/2 延迟
    # Npw/2 对应的距离偏移刚好被减掉，使峰值回归真实的 6.00km
    dist_axis = (np.arange(N) - Npw/2) * (3e8 / (2 * Fs)) / 1000 
    
    plt.subplot(2, 2, 1)
    # 使用 extent 将二维图的 X 轴也映射为真实的距离(km)
    extent = [dist_axis[0], dist_axis[-1], 0, M-1]
    plt.imshow(20*np.log10(np.abs(RD_orig) + 1e-10), aspect='auto', cmap='jet', origin='lower', extent=extent)
    plt.title('1. 抗干扰前 R-D 图 (目标与干扰在多普勒域分离)')
    plt.xlabel('距离 (km)')
    plt.ylabel('多普勒通道索引')
    
    plt.subplot(2, 2, 2)
    plt.imshow(20*np.log10(np.abs(RD_filtered) + 1e-10), aspect='auto', cmap='jet', origin='lower', extent=extent)
    plt.title('2. 抗干扰后 R-D 图 (干扰通道被整行彻底挖空填平)')
    plt.xlabel('距离 (km)')
    
    plt.subplot(2, 1, 2)
    plt.plot(dist_axis, 20*np.log10(profile_before + 1e-10), label='仅快时间一维处理 (虚假目标群横行)', color='gray', alpha=0.8)
    plt.plot(dist_axis, 20*np.log10(profile_after + 1e-10), label='快慢时间联合抗干扰 (真实目标精准凸显)', color='red', linewidth=2.5)
    
    plt.axvline(x=target_dist/1000, color='blue', linestyle='--', label=f'真实目标位置 ({target_dist/1000:.2f} km)')
    
    plt.title('3. 距离像检测验证：彻底粉碎切片组合欺骗')
    plt.xlabel('距离 (km)')
    plt.ylabel('能量 (dB)')
    plt.xlim([4, 10]) # 只看 4km 到 10km 的核心交战区
    plt.ylim([0, 80])
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_test()