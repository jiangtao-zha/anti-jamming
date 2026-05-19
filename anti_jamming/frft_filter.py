import numpy as np
from scipy.fft import fft, ifft

def frft_anti_jamming(radar_par, a1, a2, w=100, u1_target=None, u2_target=None):
    """
    基于分数阶傅里叶变换(FrFT)的雷达回波抗干扰处理

    参数:
        radar_par  : 字典，需包含 PulseNum, Nwid, Npw, St (模板), Srt_temp (受干扰回波)
        a1, a2     : 相邻脉冲的 FrFT 分数阶阶数
        w          : 分数阶域中用于提取目标的掩膜宽度 (默认100)
        u1_target  : a1 阶数下目标在 FrFT 域的峰值位置（None 则用 argmax）
        u2_target  : a2 阶数下目标在 FrFT 域的峰值位置（None 则用 argmax）

    返回:
        X_filtered_time  : 抗干扰后的时域回波矩阵
        Srpc_range_after : 抗干扰并脉压后的距离像 (一维数组)
    """
    PulseNum = radar_par['PulseNum']
    Nwid = radar_par['Nwid']
    Npw = radar_par['Npw']

    # 脉冲压缩准备 (匹配滤波器)
    Nfft = 2**int(np.ceil(np.log2(Nwid + Npw - 1)))
    Sw = fft(radar_par['St'][0, :], n=Nfft)

    # --- 1. 对所有脉冲进行 FrFT 变换 ---
    X_frft_a1 = np.zeros((PulseNum, Nwid), dtype=complex)
    X_frft_a2 = np.zeros((PulseNum, Nwid), dtype=complex)

    for n in range(PulseNum):
        X_frft_a1[n, :] = myfrft(radar_par['Srt_temp'][n, :], a1)
        X_frft_a2[n, :] = myfrft(radar_par['Srt_temp'][n, :], a2)

    # --- 2. 在 FrFT 域进行峰值掩膜滤波 (Masking) ---
    X_filtered_time = np.zeros((PulseNum, Nwid), dtype=complex)
    filter_count = np.zeros(PulseNum)

    for n in range(PulseNum - 1):
        Xa = X_frft_a1[n, :]
        Xb = X_frft_a2[n+1, :]

        # 使用模板引导的峰值位置（抗干扰时干扰可能比目标更强）
        u1_star = u1_target if u1_target is not None else np.argmax(np.abs(Xa))
        u2_star = u2_target if u2_target is not None else np.argmax(np.abs(Xb))

        mask1 = np.zeros(Nwid)
        mask2 = np.zeros(Nwid)

        # 构建矩形掩膜 (抠出目标，过滤干扰)
        i1 = max(0, u1_star - w // 2)
        j1 = min(Nwid, u1_star + w // 2 + 1)
        i2 = max(0, u2_star - w // 2)
        j2 = min(Nwid, u2_star + w // 2 + 1)

        mask1[i1:j1] = 1.0
        mask2[i2:j2] = 1.0

        Xa_f = Xa * mask1
        Xb_f = Xb * mask2

        # 逆 FrFT 变回时域
        x_n = myfrft(Xa_f, -a1)
        x_np1 = myfrft(Xb_f, -a2)

        X_filtered_time[n, :] += x_n
        filter_count[n] += 1
        X_filtered_time[n+1, :] += x_np1
        filter_count[n+1] += 1

    # 重叠区域平均化
    for n in range(PulseNum):
        if filter_count[n] > 0:
            X_filtered_time[n, :] /= filter_count[n]
            
    # --- 3. 抗干扰后的脉冲压缩 ---
    Srpc_after = np.zeros((PulseNum, Nwid), dtype=complex)
    for n in range(PulseNum):
        # 补零至 Nfft 长度进行快速卷积
        Srw = fft(np.pad(X_filtered_time[n, :], (0, Nfft - Nwid)), n=Nfft)
        Sot = ifft(Srw * np.conj(Sw), n=Nfft)
        Srpc_after[n, :] = Sot[:Nwid]
        
    # 多脉冲非相干积累
    Srpc_range_after = np.abs(np.sum(Srpc_after, axis=0))
    
    return X_filtered_time, Srpc_range_after

# =====================================================================
# 以下为经典的 Ozaktas FrFT 算法的 Python 等效实现
# =====================================================================
def myfrft(f, a):
    f = np.asarray(f, dtype=complex).flatten()
    N = len(f)
    shft = (np.arange(N) + int(np.fix(N / 2))) % N
    sN = np.sqrt(N)
    a = a % 4
    
    # 基础边界条件
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
        
    # 角度规约
    if a > 2.0:
        a = a - 2
        f = np.flipud(f)
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
    
    # 插值函数与快速卷积
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
        xint = fconv(y, np.sinc(idx)) # np.sinc 内置了 pi
        return xint[2*Nx - 3 : 4*Nx - 4]

    # 插值与补零
    f = np.concatenate((np.zeros(N - 1), interp(f), np.zeros(N - 1)))
    
    # 乘积 Chirp
    idx1 = np.arange(-2*N + 2, 2*N - 1)
    chrp = np.exp(-1j * np.pi / N * tana2 / 4 * (idx1**2))
    f = chrp * f
    
    # 卷积 Chirp
    c = np.pi / N / sina / 4
    idx2 = np.arange(-(4*N - 4), 4*N - 3)
    Faf = fconv(np.exp(1j * c * (idx2**2)), f)
    
    # 截取有效区间并反求 Chirp
    Faf = Faf[4*N - 4 : 8*N - 7] * np.sqrt(c / np.pi)
    Faf = chrp * Faf
    
    # 抽取与相位补偿
    Faf = np.exp(-1j * (1 - a) * np.pi / 4) * Faf[N - 1 : 3*N - 2 : 2]
    
    return Faf

def run_visual_test():
    """
    FrFT 分数阶傅里叶变换滤波器的可视化测试。
    展示时域、FrFT 域、脉冲压缩距离像在 FMNoiseAimedJam 干扰下的变化。
    """
    import sys, os
    import matplotlib.pyplot as plt
    from scipy import signal as sig
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False

    from unified_framework import RadarEnvironment, JammerLoader
    from anti_jamming.adapters import get_antijam_func

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    M = 4
    N = radar_params['N']
    Fs = radar_params['Fs']
    Pw = radar_params['Pw']
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_dist = radar_params['target_dist']
    target_amp = radar_params['target_amp']
    target_delay = target_dist * 2 / 3e8
    target_delay_idx = int(target_delay / Ts)
    target_idx = target_delay_idx + Npw // 2
    noise_var = radar_params.get('noise_var', 0.1)
    noise_level = np.sqrt(noise_var)

    np.random.seed(42)
    env = RadarEnvironment(radar_params)
    St_base = env.generate_target_signal()
    jammer = JammerLoader.load('FMNoiseAimedJam')

    J_signal, _, _ = jammer.generate(
        R_target=target_dist,
        JSR_dB=radar_params.get('JSR_dB', 10),
        noise_var=radar_params.get('noise_var', 0.1)
    )

    Srt_matrix = np.zeros((M, N), dtype=complex)
    for m in range(M):
        doppler_phase = np.exp(1j * 2 * np.pi * 200 * m * 1e-3)
        Srt_matrix[m, target_delay_idx:target_delay_idx + Npw] += \
            St_base[:min(Npw, N - target_delay_idx)] * target_amp * doppler_phase
        if len(J_signal) >= N:
            Srt_matrix[m, :] += J_signal[:N]
        else:
            Srt_matrix[m, :len(J_signal)] += J_signal
        Srt_matrix[m, :] += noise_level * (np.random.randn(N) + 1j * np.random.randn(N))

    # 处理前：第一个脉冲匹配滤波
    pc_before = sig.fftconvolve(Srt_matrix[0], np.conj(St_base[::-1]), mode='same')

    # FrFT 处理
    radar_par = {
        'Srt_matrix': Srt_matrix, 'St_base': St_base,
        'target_idx': target_idx, 'Fs': Fs, 'Pw': Pw, 'M': M, 'N': N,
    }
    antijam_func = get_antijam_func('frft_filter')
    processed_signal, processed_template = antijam_func(radar_par)
    Srt_after = processed_signal[0] if processed_signal.ndim == 2 else processed_signal
    pc_after = sig.fftconvolve(Srt_after, np.conj(processed_template[::-1]), mode='same')

    # 计算最优 FrFT 阶数用于可视化
    a_vals = np.linspace(0.8, 1.2, 50)
    best_a, best_energy = 1.0, 0
    for a in a_vals:
        x_frft = myfrft(Srt_matrix[0], a)
        e = np.max(np.abs(x_frft))
        if e > best_energy:
            best_energy = e
            best_a = a

    # --- 绘图 ---
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    # (a) 时域对比
    t = np.arange(N) / Fs
    axes[0, 0].plot(t * 1e6, np.abs(Srt_matrix[0]), label='处理前', alpha=0.7)
    axes[0, 0].plot(t[:len(Srt_after)] * 1e6, np.abs(Srt_after), label='FrFT处理后', alpha=0.7)
    axes[0, 0].set_xlabel('时间 (μs)')
    axes[0, 0].set_ylabel('幅度')
    axes[0, 0].set_title(f'(a) 时域信号对比（脉冲1）')
    axes[0, 0].legend()
    axes[0, 0].grid(True)

    # (b) FrFT 域（处理前）
    x_frft_before = myfrft(Srt_matrix[0], best_a)
    u_axis = np.arange(len(x_frft_before))
    axes[0, 1].plot(u_axis, np.abs(x_frft_before), label=f'处理前 (a={best_a:.3f})', alpha=0.7)
    axes[0, 1].set_xlabel('FrFT 域索引 u')
    axes[0, 1].set_ylabel('幅度')
    axes[0, 1].set_title(f'(b) FrFT 域频谱（处理前, 最优阶数 a={best_a:.3f}）')
    axes[0, 1].legend()
    axes[0, 1].grid(True)

    # (c) FrFT 域（处理后）
    x_frft_after = myfrft(Srt_after, best_a)
    axes[0, 2].plot(u_axis, np.abs(x_frft_after), label=f'处理后 (a={best_a:.3f})', alpha=0.7)
    axes[0, 2].set_xlabel('FrFT 域索引 u')
    axes[0, 2].set_ylabel('幅度')
    axes[0, 2].set_title(f'(c) FrFT 域频谱（处理后）')
    axes[0, 2].legend()
    axes[0, 2].grid(True)

    # (d) 脉压距离像-线性
    range_axis = np.arange(len(pc_before)) * 3e8 / (2 * Fs)
    axes[1, 0].plot(range_axis, np.abs(pc_before), label='处理前', alpha=0.7)
    axes[1, 0].plot(range_axis, np.abs(pc_after), label='FrFT处理后', alpha=0.7)
    axes[1, 0].set_xlabel('距离 (m)')
    axes[1, 0].set_ylabel('幅度')
    axes[1, 0].set_title('(d) 脉压距离像对比')
    axes[1, 0].legend()
    axes[1, 0].grid(True)

    # (e) 脉压距离像-dB
    axes[1, 1].plot(range_axis, 20 * np.log10(np.abs(pc_before) + 1e-10), label='处理前', alpha=0.7)
    axes[1, 1].plot(range_axis, 20 * np.log10(np.abs(pc_after) + 1e-10), label='FrFT处理后', alpha=0.7)
    axes[1, 1].set_xlabel('距离 (m)')
    axes[1, 1].set_ylabel('幅度 (dB)')
    axes[1, 1].set_title('(e) 脉压距离像对比 (dB)')
    axes[1, 1].legend()
    axes[1, 1].grid(True)

    # (f) FrFT 阶数扫描能量
    energies = []
    for a in a_vals:
        x_frft_scan = myfrft(Srt_matrix[0], a)
        energies.append(np.max(np.abs(x_frft_scan)))
    axes[1, 2].plot(a_vals, energies, 'b-o', markersize=3)
    axes[1, 2].axvline(x=best_a, color='r', linestyle='--', label=f'最优 a={best_a:.3f}')
    axes[1, 2].set_xlabel('FrFT 阶数 a')
    axes[1, 2].set_ylabel('峰值能量')
    axes[1, 2].set_title('(f) FrFT 阶数扫描')
    axes[1, 2].legend()
    axes[1, 2].grid(True)

    plt.tight_layout()
    plt.suptitle('FrFT 分数阶傅里叶变换滤波器 vs FMNoiseAimedJam 瞄频干扰', fontsize=14, y=1.02)
    plt.show()


if __name__ == "__main__":
    run_visual_test()