import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class ISDJ:
    """
    生成单个 PRP 内的复合信号：目标回波 + 间歇采样直接转发干扰 + 白噪声。
    对应 MATLAB 脚本：间歇采样直接转发干扰。
    """

    def __init__(self, C=3e8, f0=15e6, T=24e-6, Tr=100e-6, B=5e6, **kwargs):
        """
        参数:
            C  : 光速 (m/s)
            f0 : 中心频率 (Hz)
            T  : 脉宽/采样时间 (s)
            Tr : 脉冲重复周期 (s)
            B  : 雷达信号带宽 (Hz)
        """
        self.C = C
        self.f0 = f0
        self.fc = f0  # 内部兼容别名
        self.T = T
        self.Tr = Tr
        self.B = B
        self.K = B / T

        # 系统采样率 (与脚本一致：3倍带宽)
        self.Fs = 3 * B
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)          # 脉内点数

    def rectpuls(self, t, width):
        """矩形脉冲，在 [0, width) 内为 1。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, M=4, JSR_dB=10, noise_var=0.1):
        """
        生成复合信号。

        参数:
            R_target : 目标距离 (m)
            M        : 转发次数
            JSR_dB   : 干信比 (dB)
            noise_var: 白噪声方差系数

        返回:
            J_ISRJ : 复合信号 (复数数组，长度 N2)
            X_t    : 距离轴 (m)
            Tj     : 干扰采样时宽 (s)
        """
        # --- 时间轴（一个 PRP）---
        R = R_target
        N2 = np.ceil(self.Tr / self.Ts).astype(int)
        # 观测时间轴：从 0+2R/C 到 Tr+2R/C
        t1 = np.linspace(0 + 2 * R / self.C, self.Tr + 2 * R / self.C, N2)
        td = t1 - 2 * R / self.C

        # --- 目标回波 ---
        # 注意：脚本中 Srt 使用 td - T/1 (T/1 就是 T)，矩形窗宽度 T
        window_srt = self.rectpuls(td - self.T, self.T)
        Srt = window_srt * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                         2 * np.pi * self.f0 * (td - self.T)))

        # --- 发射信号 (用于功率参考和干扰构造) ---
        t = np.linspace(0, self.T, self.Nsys)
        St = self.rectpuls(t - self.T/2, self.T) * \
             np.exp(1j * 2 * np.pi * (self.f0 * t + (self.K/2) * t**2))

        # --- 间歇采样直接转发干扰生成 ---
        Tj = self.T / (2 * M)                     # 干扰采样时宽
        # 构造一个延时 Tj 的 LFM 信号 St2 (用于转发片段)
        St2 = self.rectpuls(t - Tj - self.T/2, self.T) * \
              np.exp(1j * 2 * np.pi * (self.f0 * (t - Tj) + (self.K/2) * (t - Tj)**2))

        ISRJ_direct = np.zeros(self.Nsys, dtype=complex)
        for i in range(1, M+1):
            # 矩形窗位置：中心在 (2i-1)*Tj，宽度 Tj
            # 注意 MATLAB 的 rectpuls(t - (2i-1)*Tj - Tj/2, Tj) 等价于以 (2i-1)*Tj 为中心
            window = self.rectpuls(t - (2*i-1)*Tj - Tj/2, Tj)
            ISRJ_direct += window * St2

        # --- JSR 标定 ---
        P_sig = self.rms(St) ** 2                 # 以发射信号功率为基准
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig * self.Nsys) /
                        max(np.sum(np.abs(ISRJ_direct) ** 2), np.finfo(float).eps))
        ISRJ_direct = scale * ISRJ_direct

        # --- 加性白噪声 ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- 将干扰插入到 PRP 时间线上 ---
        J_ISRJ = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_ISRJ[idx_start:idx_end + 1] = ISRJ_direct[:len_ins]

        # --- 合成信号 ---
        J_ISRJ = J_ISRJ + Srt + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'ISDJ',
            'Tj': Tj,
            'M': M,
            'JSR_dB': JSR_dB,
            'noise_var': noise_var,
            'R_target': R_target,
            'target_signal': Srt,
            'noise_signal': noise,
            'f0': self.f0,
            'fc': self.fc,  # 向后兼容别名
            'T': self.T,
            'B': self.B,
            'Tr': self.Tr,
            'Fs': self.Fs
        }

        return J_ISRJ, X_t, jam_info
    
if __name__ == "__main__":
    jammer = ISDJ()
    R_list = [1000, 5000, 10000]  # 米

    plt.figure(figsize=(18, 12))

    for i, R in enumerate(R_list, 1):
        J, X_t, jam_info = jammer.generate(R, M=4, JSR_dB=10, noise_var=0.1)
        Tj = jam_info['Tj']

        # 时域实部
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m\nTj = {Tj*1e6:.2f} μs')
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