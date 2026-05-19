import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class FrequencyDomainCanceller:
    """
    频域对消干扰抑制算法（适用于噪声调幅干扰）。
    对应 MATLAB 函数 Frequency_domain_cancel.m。
    """

    def __init__(self, use_fitted_freq=True, f0 = 4.0 * 10.0e6):
        """
        参数:
            use_fitted_freq : 是否使用相位拟合估计的载频，若为 False 则使用固定值 (40e6 rad/s)
        """
        self.use_fitted_freq = use_fitted_freq
        self.f0 = f0

    def cancel(self, Srt, fs):
        """
        对输入的多脉冲信号矩阵进行频域对消。

        参数:
            Srt : numpy.ndarray, 形状 (num_pulses, num_samples)，每行为一个脉冲的复信号（含干扰）
            fs  : float, 采样频率 (Hz)

        返回:
            y   : numpy.ndarray, 形状同 Srt，对消后的信号（基带）
        """
        num_pulses, num_samples = Srt.shape
        y = np.zeros((num_pulses, num_samples), dtype=complex)

        eps = 1e-8  # 避免 log(0)

        for i in range(num_pulses):
            r = Srt[i, :].copy()
            N = len(r)
            t = np.arange(N) / fs

            # 添加微小扰动避免 log(0)
            small = eps * (np.abs(r) < eps) * (1 + 1j)
            r = r + small

            # --- 步骤1：计算对数虚部（缠绕相位）---
            log_r = np.log(r)
            I = np.imag(log_r)  # 缠绕相位

            # --- 步骤2：解缠绕并线性拟合估计载频和初相 ---
            I_unwrap = np.unwrap(I)
            p = np.polyfit(t, I_unwrap, 1)  # p[0]*t + p[1]

            if self.use_fitted_freq:
                omega_hat = p[0]          # 拟合斜率 (rad/s)
                phi_hat = p[1]             # 截距 (rad)
            else:
                # 固定值 (与原MATLAB代码一致)
                omega_hat = self.f0  # 40e6 rad/s
                phi_hat = 0.0

            # 确保载频为正（频率不能为负）
            if omega_hat < 0:
                omega_hat = -omega_hat
                phi_hat = -phi_hat

            # --- 步骤3：解调（下变频到基带）---
            demod = np.exp(-1j * (omega_hat * t + phi_hat))
            y_temp = r * demod

            # --- 步骤4：FFT到频域 ---
            Y = fft(y_temp)

            # 确定正负频率索引（考虑奇偶长度）
            dc_idx = 0  # Python 索引从0开始
            num_side = (N - 1) // 2
            pos_idx = np.arange(1, num_side + 1)          # 正频率索引（除DC外）
            neg_idx = np.arange(N - num_side, N)          # 负频率索引

            # 如果N为偶数，记录Nyquist索引
            if N % 2 == 0:
                nyquist_idx = N // 2

            Y_pos = Y[pos_idx]
            Y_neg = Y[neg_idx]

            # 计算正负侧功率
            power_pos = np.sum(np.abs(Y_pos) ** 2)
            power_neg = np.sum(np.abs(Y_neg) ** 2)

            Y_new = np.zeros(N, dtype=complex)

            if power_pos > power_neg:
                # 正侧功率大，假设信号在正侧，使用负侧作为参考
                Y_neg_flip = Y_neg[::-1]   # 翻转负侧以匹配正侧频率顺序
                Y_new[pos_idx] = Y_pos - np.conj(Y_neg_flip)  # Y_R - Y_L^*
                # 负侧置零
                # Y_new[neg_idx] = 0  默认已是0
            else:
                # 负侧功率大或相等，假设信号在负侧，使用正侧作为参考
                Y_pos_flip = Y_pos[::-1]
                Y_new[neg_idx] = Y_neg - np.conj(Y_pos_flip)  # Y_L - Y_R^*
                # 正侧置零

            # 移除DC分量
            Y_new[dc_idx] = 0

            # 如果N为偶数，抑制Nyquist分量
            if N % 2 == 0:
                Y_new[nyquist_idx] = 0

            # --- 步骤5：IFFT回时域（基带信号）---
            y_out = ifft(Y_new)
            
            y_out = y_out * np.exp(1j * (omega_hat * t + phi_hat))
            # 不进行重调制（原代码注释掉了重调制步骤）
            y[i, :] = y_out

        return y



def test_frequency_domain_canceller(seed=None):
    """
    测试频域对消器（FrequencyDomainCanceller）抗干扰算法。
    使用项目标准干扰生成器加载 AMNoiseGaiJam（噪声调幅干扰）。

    参数:
        seed: 随机种子（None表示随机）

    返回:
        dict: {'AMNoiseGaiJam': {'before': info, 'after': info, 'sinr_improvement': float}}
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
    antijam_type = 'FrequencyDomainCanceller'
    jammer_types = ['AMNoiseGaiJam']

    results = {}
    for jt in jammer_types:
        jammer = JammerLoader.load(jt)
        env = RadarEnvironment(radar_params)
        radar_par = env.generate_with_jammer(jammer)

        St_base = radar_par['St_base']
        Srt_orig = radar_par['Srt_matrix'][0]

        # 处理前：匹配滤波
        pc_before = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')

        # 应用频域对消抗干扰（使用默认参数）
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
    频域对消器（FrequencyDomainCanceller）的可视化测试。
    生成时域对比、频域频谱对比、短时傅里叶变换时频图对比。
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from unified_framework import RadarEnvironment, JammerLoader
    from anti_jamming.adapters import get_antijam_func
    from scipy import signal

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    jammer = JammerLoader.load('AMNoiseGaiJam')
    env = RadarEnvironment(radar_params)
    radar_par = env.generate_with_jammer(jammer)

    St_base = radar_par['St_base']
    Srt_orig = radar_par['Srt_matrix'][0]
    Fs = radar_params['Fs']

    # 处理前：匹配滤波
    pc_before = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')

    # 频域对消处理
    antijam_func = get_antijam_func('FrequencyDomainCanceller')
    processed_signal, processed_template = antijam_func(radar_par)
    Srt_after = processed_signal[0] if processed_signal.ndim == 2 else processed_signal
    pc_after = signal.fftconvolve(Srt_after, np.conj(processed_template[::-1]), mode='same')

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    # (a) 时域-实部
    t = np.arange(len(Srt_orig)) / Fs
    axes[0, 0].plot(t * 1e6, np.real(Srt_orig), label='处理前', alpha=0.7)
    axes[0, 0].plot(t * 1e6, np.real(Srt_after), label='对消处理后', alpha=0.7)
    axes[0, 0].set_xlabel('时间 (μs)')
    axes[0, 0].set_ylabel('实部')
    axes[0, 0].set_title('(a) 时域信号对比（实部）')
    axes[0, 0].legend()
    axes[0, 0].grid(True)

    # (b) 时域-包络
    axes[0, 1].plot(t * 1e6, np.abs(Srt_orig), label='处理前', alpha=0.7)
    axes[0, 1].plot(t * 1e6, np.abs(Srt_after), label='对消处理后', alpha=0.7)
    axes[0, 1].set_xlabel('时间 (μs)')
    axes[0, 1].set_ylabel('幅度')
    axes[0, 1].set_title('(b) 时域信号对比（包络）')
    axes[0, 1].legend()
    axes[0, 1].grid(True)

    # (c) 频域频谱
    freq = np.fft.fftfreq(len(Srt_orig), 1 / Fs)
    freq_shift = np.fft.fftshift(freq)
    spec_before = np.fft.fftshift(np.abs(np.fft.fft(Srt_orig)))
    spec_after = np.fft.fftshift(np.abs(np.fft.fft(Srt_after)))
    axes[0, 2].plot(freq_shift / 1e6, 20 * np.log10(spec_before + 1e-10), label='处理前', alpha=0.7)
    axes[0, 2].plot(freq_shift / 1e6, 20 * np.log10(spec_after + 1e-10), label='对消处理后', alpha=0.7)
    axes[0, 2].set_xlabel('频率 (MHz)')
    axes[0, 2].set_ylabel('幅度 (dB)')
    axes[0, 2].set_title('(c) 频域频谱对比')
    axes[0, 2].legend()
    axes[0, 2].grid(True)

    # (d) 时频图-处理前
    nperseg = min(256, len(Srt_orig) // 4)
    f_spec, t_spec, Zxx_before = signal.stft(Srt_orig, fs=Fs, nperseg=nperseg)
    im1 = axes[1, 0].pcolormesh(t_spec * 1e6, f_spec / 1e6, np.abs(Zxx_before),
                                  shading='gouraud', cmap='jet')
    axes[1, 0].set_xlabel('时间 (μs)')
    axes[1, 0].set_ylabel('频率 (MHz)')
    axes[1, 0].set_title('(d) 时频图（处理前）')
    plt.colorbar(im1, ax=axes[1, 0])

    # (e) 时频图-处理后
    f_spec2, t_spec2, Zxx_after = signal.stft(Srt_after, fs=Fs, nperseg=nperseg)
    im2 = axes[1, 1].pcolormesh(t_spec2 * 1e6, f_spec2 / 1e6, np.abs(Zxx_after),
                                  shading='gouraud', cmap='jet')
    axes[1, 1].set_xlabel('时间 (μs)')
    axes[1, 1].set_ylabel('频率 (MHz)')
    axes[1, 1].set_title('(e) 时频图（对消处理后）')
    plt.colorbar(im2, ax=axes[1, 1])

    # (f) 脉压距离像对比
    range_axis = np.arange(len(pc_before)) * 3e8 / (2 * Fs)
    axes[1, 2].plot(range_axis, 20 * np.log10(np.abs(pc_before) + 1e-10), label='处理前', alpha=0.7)
    axes[1, 2].plot(range_axis, 20 * np.log10(np.abs(pc_after) + 1e-10), label='对消处理后', alpha=0.7)
    axes[1, 2].set_xlabel('距离 (m)')
    axes[1, 2].set_ylabel('幅度 (dB)')
    axes[1, 2].set_title('(f) 脉冲压缩距离像对比')
    axes[1, 2].legend()
    axes[1, 2].grid(True)

    plt.tight_layout()
    plt.suptitle('频域对消器 vs AMNoiseGaiJam 噪声调幅干扰', fontsize=14, y=1.02)
    plt.show()


if __name__ == "__main__":
    run_visual_test()