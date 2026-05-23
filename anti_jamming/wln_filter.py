import numpy as np
from scipy import signal

def WLN(radar_par, par1=0.6, par2=6):
    """
    宽-限-窄(WLN)抗干扰处理
    
    参数:
        radar_par: 字典类型，包含以下键:
            'Srt_temp': 回波信号矩阵 (num_pulses, num_samples)，支持复数
            'St1': 模板信号向量 (1D array)
            'f0': 载频 (Hz)
            'Bw': 信号带宽 (Hz)
        par1: 限幅因子 (默认0.6)
        par2: 滤波器阶数 (默认6)
        
    返回:
        J_wln: 处理后的回波矩阵
        St_wln: 处理后的模板向量
    """
    # 提取参数
    Srt = np.atleast_2d(radar_par['Srt_temp']) # 确保是二维数组
    St = np.asarray(radar_par['St1'])
    f0 = radar_par['f0']
    B = radar_par['Bw']
    
    wid_factor = 2.0
    nar_factor = 1.0
    order_wide = int(par2)
    order_narrow = int(par2)
    
    # 计算采样率与奈奎斯特频率
    Fs = radar_par.get('Fs', 2 * (B + f0))
    Nyq = Fs / 2.0

    # LFM chirp 瞬时频率范围: [f0, f0+B]，中心频率 f0 + B/2
    fc = f0 + B / 2.0

    # --- (1) 宽带带通滤波器设计 ---
    Bwid = wid_factor * B
    f_lo_w = max(1.0, fc - Bwid / 2.0)
    f_hi_w = min(Nyq - 1.0, fc + Bwid / 2.0)
    
    # SciPy 的 butter 默认接受归一化频率 (0 到 1 对应 0 到 Nyquist)
    b_bw, a_bw = signal.butter(order_wide, [f_lo_w / Nyq, f_hi_w / Nyq], btype='bandpass')
    
    # 对模板应用宽带滤波 (零相位滤波)
    St_w = signal.filtfilt(b_bw, a_bw, St)

    # 限幅阈值：基于模板幅度估计，par1 控制阈值相对信号水平的倍数
    Vs_est = np.median(np.abs(St_w)) / 0.6745
    VL = par1 * Vs_est
    
    # --- (2) 窄带带通滤波器设计 ---
    Bnar = nar_factor * B
    f_lo_n = max(1.0, fc - Bnar / 2.0)
    f_hi_n = min(Nyq - 1.0, fc + Bnar / 2.0)
    b_bn, a_bn = signal.butter(order_narrow, [f_lo_n / Nyq, f_hi_n / Nyq], btype='bandpass')
    
    # --- (3) 初始化输出矩阵 ---
    num_pulses, num_samples = Srt.shape
    J_wln = np.zeros_like(Srt)
    eps = np.finfo(float).eps # 机器精度，防止除零
    
    # 对每个脉冲进行处理
    for i in range(num_pulses):
        J = Srt[i, :]
        
        # a. 宽带带通
        J_w = signal.filtfilt(b_bw, a_bw, J)
        
        # b. 限幅 (np.minimum 相当于 MATLAB 的 min(1, 数组))
        gain = np.minimum(1.0, VL / (np.abs(J_w) + eps))
        J_lim = J_w * gain
        
        # c. 窄带带通
        J_wln[i, :] = signal.filtfilt(b_bn, a_bn, J_lim)
        
    # 对模板应用窄带滤波
    St_wln = signal.filtfilt(b_bn, a_bn, St_w)
    
    return J_wln, St_wln

def test_wln(seed=None):
    """
    测试 WLN（宽-限-窄滤波器）抗干扰算法。
    使用项目标准干扰生成器加载 FMZuse（噪声调频阻塞干扰）。

    参数:
        seed: 随机种子（None表示随机）

    返回:
        dict: {'FMZuse': {'before': info, 'after': info, 'sinr_improvement': float}}
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    if seed is not None:
        np.random.seed(seed)

    from unified_framework import RadarEnvironment, JammerLoader, UnifiedEvaluator
    from anti_jamming.adapters import get_antijam_func

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    antijam_type = 'WLN'
    jammer_types = ['FMZuse']

    results = {}
    for jt in jammer_types:
        jammer = JammerLoader.load(jt)
        env = RadarEnvironment(radar_params)
        radar_par = env.generate_with_jammer(jammer)

        St_base = radar_par['St_base']
        Srt_orig = radar_par['Srt_matrix'][0]

        # 处理前：匹配滤波
        pc_before = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')

        # 应用 WLN 抗干扰（使用默认参数）
        antijam_func = get_antijam_func(antijam_type)
        processed_signal, processed_template = antijam_func(radar_par)

        # 处理后：匹配滤波
        Srt_after = processed_signal[0] if processed_signal.ndim == 2 else processed_signal
        pc_after = signal.fftconvolve(Srt_after, np.conj(processed_template[::-1]), mode='same')

        # CA-CFAR 评估
        evaluator = UnifiedEvaluator()
        target_idx = radar_par['target_idx']
        info_before = evaluator.evaluate(np.abs(pc_before), target_idx)
        info_after = evaluator.evaluate(np.abs(pc_after), target_idx)

        results[jt] = {
            'before': info_before,
            'after': info_after,
            'sinr_improvement': info_after['sinr_db'] - info_before['sinr_db']
        }

        print(f"\n{'='*55}")
        print(f"  测试: {antijam_type} vs {jt}")
        print(f"  处理前: 检测={info_before['is_detected']}, SINR={info_before['sinr_db']:.2f} dB")
        print(f"  处理后: 检测={info_after['is_detected']}, SINR={info_after['sinr_db']:.2f} dB")
        print(f"  SINR改善: {info_after['sinr_db'] - info_before['sinr_db']:.2f} dB")
        print(f"{'='*55}")

    return results


def run_visual_test():
    """
    WLN 宽-限-窄滤波器的可视化测试。
    生成时域对比、频域频谱对比、脉冲压缩距离像对比图。
    """
    import sys, os
    import matplotlib.pyplot as plt
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False

    from unified_framework import RadarEnvironment, JammerLoader
    from anti_jamming.adapters import get_antijam_func
    from scipy import signal

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    jammer = JammerLoader.load('FMZuse')
    env = RadarEnvironment(radar_params)
    radar_par = env.generate_with_jammer(jammer)

    St_base = radar_par['St_base']
    Srt_orig = radar_par['Srt_matrix'][0]
    Fs = radar_params['Fs']

    # 处理前：匹配滤波
    pc_before = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')

    # WLN 处理
    antijam_func = get_antijam_func('WLN')
    processed_signal, processed_template = antijam_func(radar_par)
    Srt_after = processed_signal[0] if processed_signal.ndim == 2 else processed_signal
    pc_after = signal.fftconvolve(Srt_after, np.conj(processed_template[::-1]), mode='same')

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # (a) 时域对比
    t = np.arange(len(Srt_orig)) / Fs
    t2 = np.arange(len(Srt_after)) / Fs
    axes[0, 0].plot(t * 1e6, np.abs(Srt_orig), label='处理前', alpha=0.7)
    axes[0, 0].plot(t2 * 1e6, np.abs(Srt_after), label='WLN处理后', alpha=0.7)
    axes[0, 0].set_xlabel('时间 (μs)')
    axes[0, 0].set_ylabel('幅度')
    axes[0, 0].set_title('(a) 时域信号对比')
    axes[0, 0].legend()
    axes[0, 0].grid(True)

    # (b) 频域频谱对比
    freq = np.fft.fftfreq(len(Srt_orig), 1 / Fs)
    freq_shift = np.fft.fftshift(freq)
    spec_before = np.fft.fftshift(np.abs(np.fft.fft(Srt_orig)))
    spec_after = np.fft.fftshift(np.abs(np.fft.fft(Srt_after)))
    axes[0, 1].plot(freq_shift / 1e6, 20 * np.log10(spec_before + 1e-10), label='处理前', alpha=0.7)
    axes[0, 1].plot(freq_shift / 1e6, 20 * np.log10(spec_after + 1e-10), label='WLN处理后', alpha=0.7)
    axes[0, 1].set_xlabel('频率 (MHz)')
    axes[0, 1].set_ylabel('幅度 (dB)')
    axes[0, 1].set_title('(b) 频域频谱对比')
    axes[0, 1].legend()
    axes[0, 1].grid(True)

    # (c) 脉压距离像（线性）
    range_axis = np.arange(len(pc_before)) * 3e8 / (2 * Fs)
    axes[1, 0].plot(range_axis, np.abs(pc_before), label='处理前', alpha=0.7)
    axes[1, 0].plot(range_axis, np.abs(pc_after), label='WLN处理后', alpha=0.7)
    axes[1, 0].set_xlabel('距离 (m)')
    axes[1, 0].set_ylabel('幅度')
    axes[1, 0].set_title('(c) 脉冲压缩距离像对比')
    axes[1, 0].legend()
    axes[1, 0].grid(True)

    # (d) 脉压距离像（dB）
    axes[1, 1].plot(range_axis, 20 * np.log10(np.abs(pc_before) + 1e-10), label='处理前', alpha=0.7)
    axes[1, 1].plot(range_axis, 20 * np.log10(np.abs(pc_after) + 1e-10), label='WLN处理后', alpha=0.7)
    axes[1, 1].set_xlabel('距离 (m)')
    axes[1, 1].set_ylabel('幅度 (dB)')
    axes[1, 1].set_title('(d) 脉冲压缩距离像 (dB) 对比')
    axes[1, 1].legend()
    axes[1, 1].grid(True)

    plt.tight_layout()
    plt.suptitle('WLN 宽-限-窄滤波器 vs FMZuse 调频阻塞干扰', fontsize=14, y=1.02)
    plt.show()


if __name__ == "__main__":
    run_visual_test()