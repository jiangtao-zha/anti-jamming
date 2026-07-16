import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class SliceCombineJam:
    """
    切片组合干扰。
    对应 MATLAB 脚本：切片组合干扰。
    """

    def __init__(self, C=3e8, f0=50e6, T=24e-6, Tr=100e-6, B=20e6, Fs=None):
        """
        参数:
            C  : 光速 (m/s)
            f0 : 中心频率 (Hz)
            T  : 脉宽/采样时间 (s)
            Tr : 脉冲重复周期 (s)
            B  : 雷达信号带宽 (Hz)
            Fs : 可选系统采样率，仅用于统一接口参数映射
        """
        self.C = C
        self.f0 = f0
        self.T = T
        self.Tr = Tr
        self.B = B
        self.K = B / T

        # 系统采样率
        self.Fs = float(Fs) if Fs is not None else 2 * (B + f0)
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)          # 脉内点数

    def rectpuls(self, t, width):
        """矩形脉冲，在 [0, width) 内为 1。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, m=4, n=3, JSR_dB=2, noise_var=0.1):
        """
        生成复合信号。

        参数:
            R_target : 目标距离 (m)
            m        : 信号截取的段数
            n        : 每个子脉冲复制的次数
            JSR_dB   : 干信比 (dB)
            noise_var: 白噪声方差系数

        返回:
            J_CI_jam : 复合信号 (复数数组，长度 N2)
            X_t      : 距离轴 (m)
            tao_a    : 切片宽度 (s)
        """
        R = R_target
        N2 = np.ceil(self.Tr / self.Ts).astype(int)
        t1 = np.linspace(0 + 2 * R / self.C, self.Tr + 2 * R / self.C, N2)
        td = t1 - 2 * R / self.C

        # --- 发射信号 (用于干扰构造) ---
        t = np.linspace(0, self.T, self.Nsys)
        St = np.exp(1j * (np.pi * self.K * t**2 + 2 * np.pi * self.f0 * t))

        # --- 目标回波 ---
        window_srt = self.rectpuls(td - self.T, self.T)   # 注意：脚本中用 td - T/1，即 td - T
        Srt = window_srt * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                         2 * np.pi * self.f0 * (td - self.T)))

        # --- 切片组合干扰生成 ---
        tao_a = self.T / (m * n)                     # 切片宽度
        # 构造原始切片和（pt）
        pt = np.zeros(self.Nsys, dtype=complex)
        for i in range(1, m+1):
            # 矩形窗中心在 (i-1)*n*tao_a，宽度 tao_a
            window = self.rectpuls(t - (i-1)*n*tao_a - tao_a/2, tao_a)
            pt += St * window

        # 复制并循环移位
        shift_step = int(np.ceil(tao_a / self.Ts))    # 每个复制步的采样点数
        J_CI = np.zeros(self.Nsys, dtype=complex)
        for i in range(1, n+1):
            shift = (i-1) * shift_step
            J_CI += np.roll(pt, shift)                 # 循环右移

        # --- JSR 标定 ---
        P_sig = self.rms(St) ** 2
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig * self.Nsys) /
                        max(np.sum(np.abs(J_CI) ** 2), np.finfo(float).eps))
        J_CI = scale * J_CI

        # --- 加性白噪声 ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- 将干扰插入到 PRP ---
        J_CI_jam = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_CI_jam[idx_start:idx_end + 1] = J_CI[:len_ins]

        # --- 合成信号 ---
        J_CI_jam = J_CI_jam + Srt + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        return J_CI_jam, X_t, tao_a
    

if __name__ == "__main__":
    jammer = SliceCombineJam()
    R_list = [1000, 5000, 10000]  # 米

    plt.figure(figsize=(18, 12))

    for i, R in enumerate(R_list, 1):
        J, X_t, tao_a = jammer.generate(R, m=4, n=3, JSR_dB=2, noise_var=0.1)

        # 时域实部
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m\ntao_a = {tao_a*1e6:.2f} μs')
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
                   extent=[dist_axis[0], dist_axis[-1],
                           f_spec[0]/1e6, f_spec[-1]/1e6],
                   origin='lower', cmap='jet')
        plt.xlabel('距离 (m)')
        plt.ylabel('频率 (MHz)')
        plt.title('时频图')
        plt.colorbar(label='功率 (dB)')

    plt.tight_layout()
    plt.show()
