import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift
from jamming.RGPO import RGPOJam

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# =====================================================================
# 模块 1：统一评价函数 Evaluator (Reward 计算器)
# =====================================================================
class UnifiedEvaluator:
    def __init__(self, guard_cells=4, ref_cells=30, Pfa=1e-4):
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
        tol = 8 
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

# =====================================================================
# 模块 2：环境生成与对抗引擎 (Env Step)
# =====================================================================
def generate_nlfm_waveform(f0, K, Pw, Fs, win_type='hamming'):
    """生成带有加窗的 LFM/NLFM 波形"""
    t = np.arange(int(Pw * Fs)) / Fs
    sig = np.exp(1j * (np.pi * K * t**2 + 2 * np.pi * f0 * t))
    if win_type == 'hamming':
        sig *= np.hamming(len(t))
    return sig

def simulate_rgpo_env(radar_par, agile_mode=False):
    """
    模拟脉冲交互环境：
    agile_mode = False: 固定波形 (雷达与干扰机使用相同波形)
    agile_mode = True : 脉间波形捷变 (干扰机转发的是上一个脉冲的旧波形)
    """
    Fs, Pw, Bw, N = radar_par['Fs'], radar_par['Pw'], radar_par['Bw'], radar_par['N']
    Ts = 1 / Fs
    Npw = int(Pw / Ts)
    Kref = Bw / Pw
    
    # 定义波形库
    K_curr = 1.3 * Kref if agile_mode else 1.0 * Kref # 当前雷达发射波形的斜率
    K_prev = 0.7 * Kref if agile_mode else 1.0 * Kref # 干扰机截获的旧波形斜率
    
    # 1. 生成雷达发射波形 (盾) 和 干扰机转发波形 (矛)
    St_radar = generate_nlfm_waveform(radar_par['f0'], K_curr, Pw, Fs, win_type='hamming')
    St_jammer = generate_nlfm_waveform(radar_par['f0'], K_prev, Pw, Fs, win_type='hamming')
    
    Srt_rx = np.zeros(N, dtype=complex)
    
    # 2. 真实目标回波注入
    target_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts)
    Srt_rx[target_idx : target_idx + Npw] += St_radar * radar_par['target_amp']
    
    # 3. RGPO 假目标注入 (模拟拖引到了距离真目标 300 米处)
    pull_off_dist = 300 # 拖引距离 300m
    jammer_idx = int(((radar_par['target_dist'] + pull_off_dist) * 2 / 3e8) / Ts)
    Srt_rx[jammer_idx : jammer_idx + Npw] += St_jammer * radar_par['jammer_amp']
    
    # 4. 加底噪
    Srt_rx += 0.2 * (np.random.randn(N) + 1j * np.random.randn(N))
    
    # 5. 接收端执行匹配滤波 (雷达只认自己当前发射的波形 St_radar)
    pc_out = signal.fftconvolve(Srt_rx, np.conj(St_radar[::-1]), mode='same')
    
    return Srt_rx, np.abs(pc_out), target_idx

# =====================================================================
# 主函数：对比测试与强化学习验证
# =====================================================================
def run_rgpo_agile_test():
    radar_par = {
        'f0': 15e6, 'Bw': 10e6, 'Pw': 20e-6, 'Fs': 50e6, 
        'N': int(100e-6 * 50e6), # 100us 接收窗
        'target_dist': 6000, 'target_amp': 1.0,
        'jammer_amp': 10.0 # 假目标能量远大于真目标 (20dB)
    }
    Ts = 1 / radar_par['Fs']
    Npw = int(radar_par['Pw'] / Ts)
    expected_peak_idx = int((radar_par['target_dist'] * 2 / 3e8) / Ts) + Npw // 2
    evaluator = UnifiedEvaluator(guard_cells=4, ref_cells=40, Pfa=1e-4)

    # ---------------------------------------------------------
    # 情境 A：抗干扰前 (采用固定波形，RGPO 欺骗成功)
    # ---------------------------------------------------------
    print(">>> 测试 1: 固定波形 VS 距离拖引 (RGPO)")
    Srt_fixed, profile_fixed, t_idx = simulate_rgpo_env(radar_par, agile_mode=False)
    info_fixed = evaluator.evaluate(profile_fixed, expected_peak_idx)
    print(f"固定波形检测状态: {info_fixed['is_detected']}, SINR: {info_fixed['sinr_db']:.2f} dB, Reward: {info_fixed['reward']:.4f}")

    # ---------------------------------------------------------
    # 情境 B：抗干扰后 (调用离散动作：波形捷变，破解 RGPO)
    # ---------------------------------------------------------
    print(">>> 测试 2: 脉间波形捷变 VS 距离拖引 (RGPO)")
    Srt_agile, profile_agile, t_idx = simulate_rgpo_env(radar_par, agile_mode=True)
    info_agile = evaluator.evaluate(profile_agile, expected_peak_idx)
    print(f"捷变波形检测状态: {info_agile['is_detected']}, SINR: {info_agile['sinr_db']:.2f} dB, Reward: {info_agile['reward']:.4f}")

    # ---------------------------------------------------------
    # 绘图展示
    # ---------------------------------------------------------
    plt.figure(figsize=(16, 12))
    dist_axis = (np.arange(radar_par['N']) - Npw/2) * (3e8 / (2 * radar_par['Fs'])) / 1000 

    # 图 1：接收信号时频图 (直观观察波形的失配)
    plt.subplot(3, 1, 1)
    nperseg = int((radar_par['Pw'] / 8) / Ts) // 2 
    f_stft, t_stft, Zxx = signal.spectrogram(Srt_agile, fs=radar_par['Fs'], window='hann', nperseg=nperseg, noverlap=nperseg-2, return_onesided=False)
    f_stft, Zxx = fftshift(f_stft), fftshift(Zxx, axes=0)
    
    plt.pcolormesh(t_stft * 1e6, f_stft / 1e6, 10 * np.log10(np.abs(Zxx) + 1e-10), shading='auto', cmap='jet')
    plt.title('1. 捷变模式下的时频图：真实目标(左,斜率K2) 与 拖引假目标(右,携带旧波形斜率K1)')
    plt.xlabel('时间 (us)'); plt.ylabel('频率 (MHz)'); plt.ylim([5, 25])

    # 图 2：固定波形下的致命欺骗
    plt.subplot(3, 1, 2)
    plt.plot(dist_axis, 20*np.log10(profile_fixed + 1e-10), label='信号幅度 (假目标能量远超真目标)', color='gray')
    plt.plot(dist_axis, 20*np.log10(info_fixed['thresholds'] + 1e-10), label='CA-CFAR 检测阈值', color='orange', linestyle='--')
    plt.axvline(x=6.0, color='red', linestyle='-.', label='真实目标位置 (6.0 km)')
    plt.axvline(x=6.3, color='black', linestyle=':', label='RGPO假目标 (6.3 km)')
    plt.title(f'2. 抗干扰前：巨大假目标抬升了CFAR阈值，导致真实目标漏警 (Reward: {info_fixed["reward"]:.4f})')
    plt.ylabel('幅度 (dB)'); plt.xlim([5.0, 7.5]); plt.ylim([0, 100]); plt.legend(); plt.grid(True)

    # 图 3：波形捷变的完美反杀
    plt.subplot(3, 1, 3)
    plt.plot(dist_axis, 20*np.log10(profile_agile + 1e-10), label='信号幅度 (假目标被严重散焦)', color='red', linewidth=2)
    plt.plot(dist_axis, 20*np.log10(info_agile['thresholds'] + 1e-10), label='CA-CFAR 检测阈值', color='green', linestyle='--')
    plt.axvline(x=6.0, color='blue', linestyle='-.', label='真实目标位置 (6.0 km)')
    plt.title(f'3. 智能体选择[波形捷变]：旧波形假目标严重失配散焦，真实目标重新夺回检测优势！(Reward: {info_agile["reward"]:.4f})')
    plt.xlabel('距离 (km)'); plt.ylabel('幅度 (dB)'); plt.xlim([5.0, 7.5]); plt.ylim([0, 100]); plt.legend(); plt.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_rgpo_agile_test()