import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class RGPO:
    """
    距离拖引欺骗干扰。
    对应 MATLAB 脚本：距离拖引欺骗干扰（单目标静止）。
    生成多个脉冲的干扰序列，但最终输出第10个脉冲的干扰与目标回波合成的信号。
    """

    def __init__(self, C=3e8, f0=50e6, T=24e-6, Tr=100e-6, B=20e6, N_pulses=16):
        """
        参数:
            C        : 光速 (m/s)
            f0       : 中心频率 (Hz)
            T        : 脉宽/采样时间 (s)
            Tr       : 脉冲重复周期 (s)
            B        : 信号带宽 (Hz)
            N_pulses : 发射的脉冲数（用于构造拖引时序）
        """
        self.C = C
        self.f0 = f0
        self.T = T
        self.Tr = Tr
        self.B = B
        self.K = B / T
        self.N_pulses = N_pulses

        # 系统采样率
        self.Fs = 2 * (B + f0)
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)          # 脉内点数

    def rectpuls(self, t, width):
        """矩形脉冲，在 [0, width) 内为 1。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, JSR_dB=None, noise_var=0.1, A=1.8, tuoyin=1e-6):
        """
        生成第10个脉冲时刻的复合信号。

        参数:
            R_target : 目标真实距离 (m)
            JSR_dB   : 干信比 (dB)，保留参数以统一接口（未使用）
            noise_var: 白噪声方差系数
            A        : 干扰与LFM信号的幅值比（原脚本中 A=1.8）
            tuoyin   : 每个脉冲的拖引时延增量 (s)，对应拖引速度

        返回:
            signal   : 复合信号 (复数数组，长度 N2)
            X_t      : 距离轴 (m)
            jam_info : 字典，包含干扰参数信息
        """
        R = R_target
        # --- 时间轴（一个 PRP）---
        N2 = np.ceil(self.Tr / self.Ts).astype(int)
        # 观测时间轴：从 0+2R/C 到 Tr+2R/C
        t1 = np.linspace(0 + 2 * R / self.C, self.Tr + 2 * R / self.C, N2)
        td = t1 - 2 * R / self.C

        # --- 目标回波 ---
        window_srt = self.rectpuls(td - self.T, self.T)
        Srt = window_srt * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                         2 * np.pi * self.f0 * (td - self.T)))

        # --- 构造 N_pulses 个脉冲的干扰序列 ---
        # 每个脉冲对应一个拖引时延 delta_t
        delta_t = np.zeros(self.N_pulses)
        for i in range(1, self.N_pulses + 1):   # i 从 1 到 N_pulses
            if i <= 2:
                delta_t[i-1] = 0                     # 停拖期
            elif i <= 12:
                delta_t[i-1] = tuoyin * (i - 2)       # 拖引期（线性增加）
            else:
                delta_t[i-1] = delta_t[i-2]           # 保持期

        # 生成每个脉冲的干扰信号（但只取第10个脉冲用于最终输出）
        # 注意：原脚本中 temp 是 N_pulses x N2 的矩阵，每行是一个脉冲的干扰信号
        # 我们这里直接计算第10个脉冲的干扰信号，避免存储大矩阵
        i_target = 10   # 指定输出第10个脉冲
        delta_t_i = delta_t[i_target - 1]   # 拖引时延

        # 干扰信号的表达式：A * rectpuls(td - T/2 - delta_t_i, T) * exp(...)
        window_jam = self.rectpuls(td - self.T/2 - delta_t_i, self.T)
        jam_signal = A * window_jam * \
                     np.exp(1j * (np.pi * self.K * (td - self.T/2 - delta_t_i) ** 2 +
                                  2 * np.pi * self.f0 * (td - self.T/2 - delta_t_i)))

        # --- 加性白噪声 ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- 合成信号 ---
        J_RGPO = Srt + jam_signal + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        # 计算拖引对应的距离偏移
        delta_R = delta_t_i * self.C / 2   # 由于是往返时延，距离偏移 = (c * delta_t_i) / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'RGPO',
            'delta_R': delta_R,
            'i_target': i_target,
            'A': A,
            'tuoyin': tuoyin,
            'delta_t_i': delta_t_i,
            'JSR_dB': JSR_dB,
            'noise_var': noise_var,
            'R_target': R_target,
            'target_signal': Srt,
            'noise_signal': noise,
            'f0': self.f0,
            'T': self.T,
            'B': self.B,
            'Tr': self.Tr,
            'Fs': self.Fs
        }

        return J_RGPO, X_t, jam_info

if __name__ == "__main__":
    jammer = RGPO()
    # 测试不同的目标距离（但拖引效果与距离有关吗？脚本中目标静止，R=10000，我们可尝试不同R）
    R_list = [8000, 10000, 12000]  # 米

    plt.figure(figsize=(18, 12))

    for i, R in enumerate(R_list, 1):
        J, X_t, jam_info = jammer.generate(R, noise_var=0.1, A=1.8, tuoyin=1e-6)
        delta_R = jam_info['delta_R']
        i_target = jam_info['i_target']

        # 时域实部
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m\ndelta_R (第{i_target}脉冲) = {delta_R:.1f} m')
        plt.grid(True)

        # 频谱
        plt.subplot(3, 3, 3*i-1)
        f = np.fft.fftshift(np.fft.fftfreq(len(J), d=jammer.Ts))
        spec = np.fft.fftshift(np.fft.fft(J))
        plt.plot(f/1e6, 20*np.log10(np.abs(spec) + 1e-12))
        plt.xlabel('频率 (MHz)')
        plt.ylabel('幅度 (dB)')
        plt.title('频谱')
        plt.grid(True)
        plt.xlim([-100, 100])

        # 时频图
        plt.subplot(3, 3, 3*i)
        f_spec, t_spec, Zxx = signal.spectrogram(J, fs=jammer.Fs,
                                                  nperseg=256, noverlap=128)
        t_start = 0 + 2 * R / jammer.C
        t_end = jammer.Tr + 2 * R / jammer.C
        t_actual = t_start + t_spec
        dist_axis = (t_actual - jammer.T/2) * jammer.C / 2

        plt.imshow(10*np.log10(np.abs(Zxx) + 1e-12),
                   aspect='auto',
                   extent=(dist_axis[0], dist_axis[-1],
                           f_spec[0]/1e6, f_spec[-1]/1e6),
                   origin='lower', cmap='jet')
        plt.xlabel('距离 (m)')
        plt.ylabel('频率 (MHz)')
        plt.title('时频图')
        plt.colorbar(label='功率 (dB)')

    plt.tight_layout()
    plt.show()