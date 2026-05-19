import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class SMSP:
    """
    频谱弥散（SMSP）干扰。
    对应 MATLAB 函数 SMSP_jam.m。
    """

    def __init__(self, C=3e8, f0=15e6, T=24e-6, Tr=100e-6, B=5e6):
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
        self.T = T
        self.Tr = Tr
        self.B = B
        self.K = B / T

        # 系统采样率（统一使用）
        self.Fs = 2 * (B + f0)
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)          # 脉内点数

    def rectpuls(self, t, width):
        """矩形脉冲，在 [0, width) 内为 1。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, JSR_dB=2, noise_var=0.1, N_num=4, Aj=1.8):
        """
        生成复合信号。

        参数:
            R_target : 目标距离 (m)
            JSR_dB   : 干信比 (dB)
            noise_var: 白噪声方差系数
            N_num    : 子脉冲数（默认4）
            Aj       : 子脉冲幅度（默认1.8）

        返回:
            signal   : 复合信号 (复数数组，长度 N2)
            X_t      : 距离轴 (m)
            jam_info : 字典，包含干扰参数信息
        """
        R = R_target
        N2 = np.ceil(self.Tr / self.Ts).astype(int)
        t1 = np.linspace(2 * R / self.C, self.Tr + 2 * R / self.C, N2)
        td = t1 - 2 * R / self.C

        # --- 目标回波 ---
        window = self.rectpuls(td - self.T, self.T)
        St = window * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                    2 * np.pi * self.f0 * (td - self.T)))

        # --- SMSP干扰生成 ---
        t_jam = np.linspace(0, self.T, self.Nsys)
        Tj = self.T / N_num                     # 子脉冲宽度
        Kj = N_num * self.K                      # 子脉冲调频斜率
        Shepin = np.zeros(self.Nsys, dtype=complex)

        for i in range(1, N_num + 1):
            tau_i = (i - 1) * Tj + Tj / 2        # 子脉冲中心时刻
            s_i = Aj * self.rectpuls(t_jam - tau_i, Tj) * \
                  np.exp(1j * (np.pi * Kj * (t_jam - tau_i) ** 2 +
                               2 * np.pi * self.f0 * (t_jam - tau_i)))
            Shepin += s_i

        # --- 加性白噪声 ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- JSR标定 ---
        P_sig = self.rms(St) ** 2
        P_jam = self.rms(Shepin) ** 2
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig) / max(P_jam, np.finfo(float).eps))
        Shepin = scale * Shepin

        # --- 插入PRP ---
        J_SMSP = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_SMSP[idx_start:idx_end + 1] = Shepin[:len_ins]

        # --- 合成 ---
        J_SMSP = J_SMSP + St + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'SMSP',
            'bandwidth': self.B,  # 雷达信号带宽
            'JSR_dB': JSR_dB,
            'noise_var': noise_var,
            'R_target': R_target,
            'target_signal': St,
            'noise_signal': noise,
            'f0': self.f0,
            'T': self.T,
            'B': self.B,
            'Tr': self.Tr,
            'Fs': self.Fs,
            'N_num': N_num,
            'Aj': Aj,
            'Tj': self.T / N_num,
            'Kj': N_num * self.K
        }
        
        return J_SMSP, X_t, jam_info

if __name__ == "__main__":
    jammer = SMSP()
    R_list = [1000, 5000, 10000]  # 米

    plt.figure(figsize=(18, 12))

    for i, R in enumerate(R_list, 1):
        J, X_t, jam_info = jammer.generate(R, JSR_dB=2, noise_var=0.1, N_num=4, Aj=1.8)
        B = jam_info['bandwidth']

        # 时域实部
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m')
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
        t_start = 2 * R / jammer.C
        t_end = jammer.Tr + 2 * R / jammer.C
        t_actual = t_start + t_spec
        dist_axis = (t_actual - jammer.T/2) * jammer.C / 2

        plt.imshow(10*np.log10(np.abs(Zxx) + 1e-12),
                   aspect='auto',
                   extent=[dist_axis[0], dist_axis[-1],
                           f_spec[0]/1e6, f_spec[-1]/1e6],
                   origin='lower', cmap='jet')
        plt.xlabel('距离 (m)')
        plt.ylabel('频率 (MHz)')
        plt.title('时频图')
        plt.colorbar(label='功率 (dB)')

    plt.tight_layout()
    plt.show()