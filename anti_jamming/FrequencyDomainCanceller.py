import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei'] # 设置中文字体
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



if __name__ == "__main__":
    from jamming.AMNoiseGaiJam import AMNoiseGaiJam
    # 创建干扰对象
    jammer = AMNoiseGaiJam()

    # 固定目标距离
    R = 5000  # 米

    # 生成多个脉冲（例如8个脉冲），每个脉冲独立加入干扰（每次随机干扰带宽不同）
    num_pulses = 8
    pulse_list = []
    for _ in range(num_pulses):
        J_AM, X_t, Bj, _, _ = jammer.generate(R, JSR_dB=12, noise_var=0.1)
        pulse_list.append(J_AM)

    # 构建脉冲矩阵 (num_pulses, N2)
    Srt = np.array(pulse_list)
    fs = jammer.Fs

    # 创建对消器实例（使用拟合频率估计）
    canceller = FrequencyDomainCanceller(use_fitted_freq=True)
    y_cancelled = canceller.cancel(Srt, fs)

    # 选择第一个脉冲进行绘图对比
    idx = 0
    original = Srt[idx, :]
    cancelled = y_cancelled[idx, :]

    # 时域实部对比
    plt.figure(figsize=(18, 10))

    plt.subplot(2, 3, 1)
    plt.plot(X_t, np.real(original))
    plt.xlabel('距离 (m)')
    plt.ylabel('幅度 (实部)')
    plt.title('对消前 - 时域实部')
    plt.grid(True)

    plt.subplot(2, 3, 4)
    plt.plot(X_t, np.real(cancelled))
    plt.xlabel('距离 (m)')
    plt.ylabel('幅度 (实部)')
    plt.title('对消后 - 时域实部')
    plt.grid(True)

    # 频谱对比
    f = np.fft.fftshift(np.fft.fftfreq(len(original), d=jammer.Ts))
    spec_orig = np.fft.fftshift(np.fft.fft(original))
    spec_canc = np.fft.fftshift(np.fft.fft(cancelled))

    plt.subplot(2, 3, 2)
    plt.plot(f/1e6, 20*np.log10(np.abs(spec_orig) + 1e-12))
    plt.xlabel('频率 (MHz)')
    plt.ylabel('幅度 (dB)')
    plt.title('对消前 - 频谱')
    plt.grid(True)
    plt.xlim([-100, 100])

    plt.subplot(2, 3, 5)
    plt.plot(f/1e6, 20*np.log10(np.abs(spec_canc) + 1e-12))
    plt.xlabel('频率 (MHz)')
    plt.ylabel('幅度 (dB)')
    plt.title('对消后 - 频谱')
    plt.grid(True)
    plt.xlim([-100, 100])

    # 时频图对比
    plt.subplot(2, 3, 3)
    f_spec, t_spec, Zxx_orig = signal.spectrogram(original, fs=jammer.Fs,
                                                   nperseg=256, noverlap=128)
    t_start = 2 * R / jammer.C
    t_end = jammer.Tr + 2 * R / jammer.C
    t_actual = t_start + t_spec
    dist_axis = (t_actual - jammer.T/2) * jammer.C / 2

    plt.imshow(10*np.log10(np.abs(Zxx_orig) + 1e-12),
               aspect='auto',
               extent=[dist_axis[0], dist_axis[-1],
                       f_spec[0]/1e6, f_spec[-1]/1e6],
               origin='lower', cmap='jet')
    plt.xlabel('距离 (m)')
    plt.ylabel('频率 (MHz)')
    plt.title('对消前 - 时频图')
    plt.colorbar(label='功率 (dB)')

    plt.subplot(2, 3, 6)
    f_spec, t_spec, Zxx_canc = signal.spectrogram(cancelled, fs=jammer.Fs,
                                                   nperseg=256, noverlap=128)
    plt.imshow(10*np.log10(np.abs(Zxx_canc) + 1e-12),
               aspect='auto',
               extent=[dist_axis[0], dist_axis[-1],
                       f_spec[0]/1e6, f_spec[-1]/1e6],
               origin='lower', cmap='jet')
    plt.xlabel('距离 (m)')
    plt.ylabel('频率 (MHz)')
    plt.title('对消后 - 时频图')
    plt.colorbar(label='功率 (dB)')

    plt.tight_layout()
    plt.show()