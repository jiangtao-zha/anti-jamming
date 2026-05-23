import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class FMNoiseAimedJam:
    """
    生成单个 PRP 内的复合信号：目标回波 + 噪声调频干扰(FM noise) + 白噪声。
    对应 MATLAB 函数 FMnoise_aimed_jam（脚本形式）。
    修正了采样率不一致的问题：将干扰重采样到系统采样率 Fs 后再插入。
    """

    def __init__(self, C=3e8, f0=15e6, T=24e-6, Tr=100e-6, B=5e6, Fs=None, **kwargs):
        """
        参数:
            C  : 光速 (m/s)
            f0 : 中心频率 (Hz)
            T  : 脉宽/采样时间 (s)
            Tr : 脉冲重复周期 (s)
            B  : 信号带宽 (Hz)
            Fs : 采样率 (Hz)，None 时使用内部默认 2*(B+f0)
        """
        self.C = C
        self.f0 = f0
        self.T = T
        self.Tr = Tr
        self.B = B
        self.K = B / T          # 调频斜率

        # 系统统一采样率（与第一个函数一致）
        self.Fs = Fs if Fs is not None else 2 * (B + f0)
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)          # 脉内点数（系统采样率下）

    def rectpuls(self, t, width):
        """生成矩形脉冲，与 MATLAB rectpuls 行为一致：在 [0, width) 内为 1，其余为 0。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        """计算复信号的 RMS 值 (均方根)"""
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, JSR_dB=2, noise_var=0.01):
        """
        生成复合信号。

        参数:
            R_target : 目标距离 (m)
            JSR_dB   : 干信比 (dB)
            noise_var: 白噪声方差系数

        返回:
            J_FM   : 复合信号 (复数数组，长度 N2)
            X_t    : 距离轴 (m)
            Bj     : 干扰带宽 (Hz)
            kfm    : 调频斜率 (Hz)
        """
        # --- 时间轴（一个 PRP）---
        R = R_target
        N2 = np.ceil(self.Tr / self.Ts).astype(int)          # PRP 内点数
        t1 = np.linspace(2 * R / self.C, self.Tr + 2 * R / self.C, N2)   # 观测时间轴
        td = t1 - 2 * R / self.C                                        # 往返延时对齐的时间

        # --- 目标回波 ---
        window = self.rectpuls(td - self.T, self.T)
        St = window * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                    2 * np.pi * self.f0 * (td - self.T)))

        # --- 噪声调频干扰（瞄准式）---
        # 随机选取干扰带宽 (2~5 倍信号带宽)
        Bj = np.random.randint(2, 6) * self.B
        f1 = self.f0                # 干扰载频
        # 干扰采样率（为了满足干扰带宽）
        fs = 2 * (Bj + f1)          # 干扰采样频率
        N = int(self.T * fs)         # 干扰脉内采样点数（根据干扰采样率）

        # 低通滤波器截止频率
        detlf = Bj / 2
        # 设计 FIR 低通滤波器并获取其频率响应
        # firwin 设计长度为 N 的滤波器（阶数 N-1）
        fir_coeff = signal.firwin(numtaps=N, cutoff=detlf/(fs/2), pass_zero='lowpass')
        Hlp = fft(fir_coeff, n=N)

        # 生成高斯白噪声（实数），并滤波得到带限噪声 xn1
        noise_raw = np.random.randn(N)
        xn1 = ifft(fft(noise_raw, n=N) * Hlp)
        xn1 = np.real(xn1)           # 取实部（应为实数）

        # 调频斜率（随机 5~7 MHz，单位 Hz）
        kfm = (np.random.rand() * 2 + 5) * 1e6

        # 噪声积分（模拟调频相位）
        sigma_xn1 = np.cumsum(xn1) / fs   # 积分近似 ∫n(t)dt

        # 干扰时间轴（按干扰采样率）
        t_jam = np.linspace(0, self.T, N)

        # 噪声调频干扰表达式
        FM_MZ = np.exp(1j * (2 * np.pi * f1 * t_jam +
                              2 * np.pi * kfm * sigma_xn1 +
                              np.pi / 2))

        # --- JSR 标定（在干扰信号原始采样率下进行）---
        P_sig = self.rms(St) ** 2
        P_jam_now = self.rms(FM_MZ) ** 2
        # 计算缩放因子（与 MATLAB 公式一致）
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig * N) / max(np.sum(np.abs(FM_MZ) ** 2), np.finfo(float).eps))
        FM_MZ = scale * FM_MZ

        # --- 将干扰重采样到系统采样率 Fs ---
        # 重采样后点数应为 Nsys
        FM_MZ_resampled = signal.resample(FM_MZ, self.Nsys)

        # --- 加性白噪声 (PRP 长度) ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- 将干扰插入到 PRP 时间线上 ---
        J_FM = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)      # 插入起始索引（0-based）
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_FM[idx_start:idx_end + 1] = FM_MZ_resampled[:len_ins]

        # --- 合成信号 ---
        J_FM = J_FM + St + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'FMNoiseAimedJam',
            'Bj': Bj,
            'kfm': kfm,
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

        return J_FM, X_t, jam_info
    
if __name__ == "__main__":
    # 创建实例
    jammer = FMNoiseAimedJam()

    # 测试不同的目标距离
    R_list = [1000, 5000, 10000]  # 米

    plt.figure(figsize=(18, 12))   # 适应三列布局

    for i, R in enumerate(R_list, 1):
        J_FM, X_t, jam_info = jammer.generate(R, JSR_dB=2, noise_var=0.01)
        Bj = jam_info['Bj']
        kfm = jam_info['kfm']

        # ---------- 第1列：时域实部 ----------
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J_FM))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m\nBj = {Bj/1e6:.2f} MHz, kfm = {kfm/1e6:.2f} MHz')
        plt.grid(True)

        # ---------- 第2列：频谱 ----------
        plt.subplot(3, 3, 3*i-1)
        f = np.fft.fftshift(np.fft.fftfreq(len(J_FM), d=jammer.Ts))
        spec = np.fft.fftshift(np.fft.fft(J_FM))
        plt.plot(f/1e6, 20*np.log10(np.abs(spec) + 1e-12))
        plt.xlabel('频率 (MHz)')
        plt.ylabel('幅度 (dB)')
        plt.title('频谱')
        plt.grid(True)
        plt.xlim([-100, 100])

        # ---------- 第3列：时频图 ----------
        plt.subplot(3, 3, 3*i)
        # 计算短时傅里叶变换
        f_spec, t_spec, Zxx = signal.spectrogram(J_FM, fs=jammer.Fs,
                                                  nperseg=256, noverlap=128)
        # 将时间轴转换为距离轴
        # 实际观测时间范围：[2R/C, Tr+2R/C]
        t_start = 2 * R / jammer.C
        t_end = jammer.Tr + 2 * R / jammer.C
        t_actual = t_start + t_spec                     # 对应的实际时间
        dist_axis = (t_actual - jammer.T / 2) * jammer.C / 2   # 转换为距离

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