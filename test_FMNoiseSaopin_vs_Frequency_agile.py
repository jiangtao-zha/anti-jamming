import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift
from anti_jamming.Frequency_agile import FrequencyAgileRadar
from jamming.FMNoiseSaopin import FMNoiseSaopin

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

class UnifiedEvaluator:
    def __init__(self, guard_cells=4, ref_cells=20, Pfa=1e-5):
        self.guard_cells = guard_cells
        self.ref_cells = ref_cells
        self.Pfa = Pfa

    def ca_cfar_fast(self, mag):
        N = len(mag)
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
        
        target_region_det = detections[start_idx:end_idx]
        is_detected = np.any(target_region_det)
        R_Ed = 1.0 if is_detected else 0.0
        
        target_peak_power = np.max(range_profile[start_idx:end_idx])**2
        bg_region = range_profile[max(0, start_idx - self.ref_cells) : min(len(range_profile), end_idx + self.ref_cells)]
        interference_power = np.mean(bg_region)**2 + 1e-12
        sinr_db = 10 * np.log10(target_peak_power / interference_power)
        
        R_ESINR = np.clip((sinr_db - 0.0) / 30.0, 0.0, 1.0)
        if not is_detected: R_ESINR = 0.0
            
        reward = w1 * R_Ed + w2 * R_ESINR
        return {'is_detected': is_detected, 'sinr_db': sinr_db, 'reward': reward, 'thresholds': thresholds}

def generate_isrj_jamming(ref_signal, repeats=4):
    """间歇采样转发干扰"""
    N = len(ref_signal)
    slice_len = N // (repeats * 2)
    jamming = np.zeros(N, dtype=complex)
    for i in range(repeats):
        start = i * (slice_len * 2)
        # 干扰机侦察截获一小段，然后重复转发
        jamming[start : start + slice_len] = ref_signal[:slice_len]
    return jamming

def run_agile_antijamming_test():
    # 1. 统一雷达参数
    C = 3.0e8
    Pw, Bw = 20e-6, 20e6
    fs = 4.0 * Bw
    Ts = 1.0 / fs
    Nwid = int(100e-6 / Ts) 
    t0 = np.arange(Nwid) * Ts
    
    radar_par = {
        'PRF': 1000, 'Pw': Pw, 'Bw': Bw, 'Range': 6000, 
        'Rmin': 1000, 'Rmax': 15000, 'PulseNum': 1, 'Nwid': Nwid, 
        'f0': 15e6, 'Vt': 150, 'Npw': int(Pw / Ts), 'fc': 10e9, 't0': t0
    }

    print("正在生成 Costas-LFM 频率捷变雷达波形...")
    radar = FrequencyAgileRadar(radar_par)
    wave_data = radar.generate(seq_type=1)
    St = wave_data['St'][0]
    Npw = len(St)
    
    # 2. 【核心修复 1】生成绝对相干的完美干净回波
    target_idx = int((radar_par['Range'] * 2 / C) / Ts)
    Srti_clean = np.zeros(Nwid, dtype=complex)
    Srti_clean[target_idx : target_idx + Npw] = St * 1.0
    
    # 3. 注入混合干扰
    # A. 间歇采样干扰 (侦察雷达头部信号后重复转发)
    J_isrj_base = generate_isrj_jamming(St, repeats=4)
    J_isrj_rx = np.zeros(Nwid, dtype=complex)
    jammer_delay_idx = target_idx - 50 # 干扰机提前一点点
    J_isrj_rx[jammer_delay_idx : jammer_delay_idx + len(J_isrj_base)] = J_isrj_base * 5.0 
    
    # B. 使用统一的 FMNoiseSaopin 类生成扫频干扰
    jammer = FMNoiseSaopin(
        C=C, f0=radar_par['f0'], T=Pw, Tr=100e-6, B=Bw
    )
    
    # 生成干扰信号
    J_FM, X_t, jam_info = jammer.generate(
        R_target=radar_par['Range'],
        JSR_dB=15,  # 适当的干信比
        noise_var=0.1
    )
    
    # 从总信号中提取纯干扰部分
    target_signal = jam_info['target_signal']
    noise_signal = jam_info['noise_signal']
    J_sweep = J_FM - target_signal - noise_signal
    
    # 调整干扰幅度并截取合适长度
    J_sweep = J_sweep[:min(len(J_sweep), Nwid)]
    if len(J_sweep) < Nwid:
        # 如果干扰信号较短，扩展到Nwid长度
        J_sweep_extended = np.zeros(Nwid, dtype=complex)
        J_sweep_extended[:len(J_sweep)] = J_sweep
        J_sweep = J_sweep_extended
    
    # 调整幅度
    J_sweep_rx = J_sweep * 1.5 / np.max(np.abs(J_sweep) + 1e-10)
    
    # 合成环境
    noise = 0.5 * (np.random.randn(Nwid) + 1j * np.random.randn(Nwid))
    Srti_jammed = Srti_clean + J_isrj_rx + J_sweep_rx + noise

    # 4. 智能体动作：执行脉冲压缩
    clean_pc = signal.fftconvolve(Srti_clean, np.conj(St[::-1]), mode='same')
    jammed_pc = signal.fftconvolve(Srti_jammed, np.conj(St[::-1]), mode='same')
    
    profile_clean = np.abs(clean_pc)
    profile_jammed = np.abs(jammed_pc)

    # 5. 评价与反馈
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)
    expected_peak_idx = target_idx + Npw // 2 # 补偿 matched filter 引入的半脉宽延迟
    
    info_clean = evaluator.evaluate(profile_clean, expected_peak_idx)
    info_jammed = evaluator.evaluate(profile_jammed, expected_peak_idx)
    
    print(f"抗干扰评价 -> 检测状态: {info_jammed['is_detected']}, SINR: {info_jammed['sinr_db']:.2f} dB, Reward: {info_jammed['reward']:.4f}")

    # 6. 绘图展示
    plt.figure(figsize=(16, 12))
    dist_axis = (np.arange(Nwid) - Npw // 2) * (C / (2 * fs)) / 1000 

    # 图 1
    plt.subplot(3, 1, 1)
    nperseg = int((Pw / 10) / Ts) // 2 
    f_stft, t_stft, Zxx = signal.spectrogram(Srti_jammed, fs=fs, window='hann', nperseg=nperseg, noverlap=nperseg-2, return_onesided=False)
    f_stft, Zxx = fftshift(f_stft), fftshift(Zxx, axes=0)
    
    plt.pcolormesh(t_stft * 1e6, f_stft / 1e6, 10 * np.log10(np.abs(Zxx) + 1e-10), shading='auto', cmap='jet')
    plt.title('1. 接收窗信号时频图：Costas 目标被强力扫频干扰与间歇采样假目标覆盖')
    plt.xlabel('时间 (us)'); plt.ylabel('频率 (MHz)')
    plt.ylim([0, radar_par['f0']/1e6 + Bw/1e6 + 5])

    # 图 2 (注意这次的峰值有多完美)
    plt.subplot(3, 1, 2)
    plt.plot(dist_axis, 20*np.log10(profile_clean + 1e-10), label='信号幅度 (干净环境)', color='blue')
    plt.plot(dist_axis, 20*np.log10(info_clean['thresholds'] + 1e-10), label='CA-CFAR 阈值', color='green', linestyle='--')
    plt.axvline(x=6.0, color='red', linestyle='-.', label='真实目标位置 (6.0 km)')
    plt.title('2. 理想相干条件下的 Costas 脉冲压缩基准 (展现经典的图钉型锐利尖峰)')
    plt.ylabel('幅度 (dB)')
    plt.xlim([4.5, 7.5]); plt.ylim([0, 100]); plt.legend(); plt.grid(True)

    # 图 3
    plt.subplot(3, 1, 3)
    plt.plot(dist_axis, 20*np.log10(profile_jammed + 1e-10), label='信号幅度 (强干扰抗击后)', color='red')
    plt.plot(dist_axis, 20*np.log10(info_jammed['thresholds'] + 1e-10), label='CA-CFAR 阈值', color='green', linestyle='--')
    plt.axvline(x=6.0, color='blue', linestyle='-.', label='真实目标位置 (6.0 km)')
    plt.title(f'3. 频率捷变抗击扫频与 ISRJ 验证：干扰因频率失配被散焦，目标强势凸显！Reward: {info_jammed["reward"]:.4f}')
    plt.xlabel('距离 (km)'); plt.ylabel('幅度 (dB)')
    plt.xlim([4.5, 7.5]); plt.ylim([0, 100]); plt.legend(); plt.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_agile_antijamming_test()