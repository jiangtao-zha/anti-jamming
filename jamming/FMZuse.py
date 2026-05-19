import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class FMZuse:
    """
    生成单个 PRP 内的复合信号：目标回波 + 噪声调频阻塞式干扰 + 白噪声。
    对应 MATLAB 函数 FM_zuse_jam.m。
    """

    def __init__(self, C=3e8, f0=15e6, T=24e-6, Tr=100e-6, B=5e6):
        """
        参数:
            C  : 光速 (m/s)
            f0 : 中心频率 (Hz)
            T  : 脉宽/采样时间 (s)
            Tr : 脉冲重复周期 (s)
            B  : 信号带宽 (Hz)
        """
        self.C = C
        self.f0 = f0
        self.T = T
        self.Tr = Tr
        self.B = B
        self.K = B / T

        # 系统统一采样率
        self.Fs = 2 * (B + f0)
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)

    def rectpuls(self, t, width):
        """矩形脉冲，在 [0, width) 内为 1。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, JSR_dB=8, noise_var=0.1):
        """
        生成复合信号。

        参数:
            R_target : 目标距离 (m)
            JSR_dB   : 干信比 (dB)
            noise_var: 白噪声方差系数

        返回:
            J_FM_zuse : 复合信号 (复数数组，长度 N2)
            X_t       : 距离轴 (m)
            Bj        : 干扰带宽 (Hz)
            f1        : 干扰中心频率 (Hz)
        """
        # --- 时间轴（一个 PRP）---
        R = R_target
        N2 = np.ceil(self.Tr / self.Ts).astype(int)
        t1 = np.linspace(2 * R / self.C, self.Tr + 2 * R / self.C, N2)
        td = t1 - 2 * R / self.C

        # --- 目标回波 ---
        window = self.rectpuls(td - self.T, self.T)
        St = window * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                    2 * np.pi * self.f0 * (td - self.T)))

        # --- 干扰生成 ---
        # 射频带宽：6~9 倍信号带宽（阻塞式干扰）
        Bj = np.random.randint(6, 10) * self.B
        # 干扰中心频率：在 f0 ± Bj/4 范围内随机偏移
        f1 = self.f0 + np.random.uniform(-Bj/4, Bj/2)   # MATLAB: randi([-Bj/4, Bj/2]) 产生整数，这里用连续均匀分布

        # 干扰内部采样率（满足奈奎斯特）
        fs = 2 * (Bj + f1)
        Nj = round(self.T * fs)          # 干扰脉内采样点数
        t_jam = np.linspace(0, self.T, Nj)

        # 低通滤波器，截止频率 Bj/2，用于产生带限噪声
        detlf = Bj / 2
        fir_coeff = signal.firwin(numtaps=Nj, cutoff=detlf/(fs/2), pass_zero='lowpass')
        Hlp = fft(fir_coeff, n=Nj)
        xn1 = ifft(fft(np.random.randn(Nj), n=Nj) * Hlp)
        xn1 = np.real(xn1)                # 带限噪声

        # 有效调频指数 mfe = 8（固定）
        mfe = 8
        kfm = mfe * Bj / (np.std(xn1) + np.finfo(float).eps)
        sigma_xn1 = np.cumsum(xn1) / fs    # 积分

        # 噪声调频阻塞干扰信号
        FM_zuse = 3 * np.exp(1j * (2 * np.pi * f1 * t_jam +
                                    2 * np.pi * kfm * sigma_xn1 +
                                    np.pi / 6))

        # --- JSR 标定 ---
        P_sig = self.rms(St) ** 2
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig * Nj) /
                        max(np.sum(np.abs(FM_zuse) ** 2), np.finfo(float).eps))
        FM_zuse = scale * FM_zuse

        # --- 重采样到系统采样率 ---
        FM_zuse_resampled = signal.resample(FM_zuse, self.Nsys)

        # --- 加性白噪声 ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- 插入到 PRP ---
        J_FM_zuse = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_FM_zuse[idx_start:idx_end + 1] = FM_zuse_resampled[:len_ins]

        # 合成
        J_FM_zuse = J_FM_zuse + St + noise

        # 距离轴
        X_t = (t1 - self.T / 2) * self.C / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'FMZuse',
            'Bj': Bj,
            'f1': f1,
            'JSR_dB': JSR_dB,
            'noise_var': noise_var,
            'R_target': R_target,
            'target_signal': St,
            'noise_signal': noise,
            'f0': self.f0,
            'T': self.T,
            'B': self.B,
            'Tr': self.Tr,
            'Fs': self.Fs
        }

        return J_FM_zuse, X_t, jam_info

if __name__ == "__main__":
    jammer = FMZuse()
    R_list = [1000, 5000, 10000]  # 米

    plt.figure(figsize=(18, 12))

    for i, R in enumerate(R_list, 1):
        J, X_t, jam_info = jammer.generate(R, JSR_dB=8, noise_var=0.1)
        Bj = jam_info['Bj']
        f1 = jam_info['f1']

        # 时域实部
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m\nBj = {Bj/1e6:.2f} MHz, f1偏移 = {(f1-jammer.f0)/1e6:.2f} MHz')
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
        plt.xlim([-150, 150])   # 因为干扰带宽可能更大，扩展显示范围

        # 时频图
        plt.subplot(3, 3, 3*i)
        f_spec, t_spec, Zxx = signal.spectrogram(J, fs=jammer.Fs,
                                                  nperseg=256, noverlap=128)
        t_start = 2 * R / jammer.C
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