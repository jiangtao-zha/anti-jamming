import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号
class FMNoiseSaopin:
    """
    生成单个 PRP 内的复合信号：目标回波 + 线性扫频+噪声调频复合干扰 + 白噪声。
    对应 MATLAB 脚本：线性扫频干扰（含噪声调频）。
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
        self.Nsys = round(T / self.Ts)          # 脉内点数（系统采样率）

    def rectpuls(self, t, width):
        """生成矩形脉冲，在 [0, width) 内为 1。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        return np.sqrt(np.mean(np.abs(x) ** 2))

        # 在 FMNoiseSaopin 类中添加以下方法
    def generate_jam_only(self, R_target, JSR_dB=8, noise_var=0.05):
        """
        仅生成干扰和噪声，不包含目标回波。
        返回：
            J_only : 干扰+噪声信号 (复数数组，长度 N2)
            X_t    : 距离轴 (m)
            Bj     : 干扰带宽 (Hz)
        """
        R = R_target
        N2 = np.ceil(self.Tr / self.Ts).astype(int)
        t1 = np.linspace(2 * R / self.C, self.Tr + 2 * R / self.C, N2)
        td = t1 - 2 * R / self.C

        # 计算目标回波（仅用于功率参考，不用于叠加）
        window = self.rectpuls(td - self.T, self.T)
        St = window * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                    2 * np.pi * self.f0 * (td - self.T)))

        # --- 干扰生成（与原方法相同）---
        Bj = np.random.randint(2, 6) * self.B
        fs = 5 * Bj
        N = round(self.T * fs)
        f_sweep = np.linspace(10e6, 30e6, N)
        f1 = self.f0 + f_sweep - Bj / 2

        detlf = Bj / 2
        fir_coeff = signal.firwin(numtaps=N, cutoff=detlf/(fs/2), pass_zero='lowpass')
        Hlp = fft(fir_coeff, n=N)
        xn1 = ifft(fft(np.random.randn(N), n=N) * Hlp)
        xn1 = np.real(xn1)

        mfe = 0.015
        kfm = mfe * Bj / (np.std(xn1) + np.finfo(float).eps)
        sigma_xn1 = np.cumsum(xn1) / fs
        t_jam = np.linspace(0, self.T, N)
        FM_SP = 3 * np.exp(1j * (2 * np.pi * f1 * t_jam +
                                2 * np.pi * kfm * sigma_xn1 +
                                np.pi / 6))

        # JSR 标定
        P_sig = self.rms(St) ** 2
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig * N) /
                        max(np.sum(np.abs(FM_SP) ** 2), np.finfo(float).eps))
        FM_SP = scale * FM_SP

        # 重采样
        FM_SP_resampled = signal.resample(FM_SP, self.Nsys)

        # 噪声
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # 插入 PRP（干扰部分）
        J_only = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_only[idx_start:idx_end + 1] = FM_SP_resampled[:len_ins]

        # 加入噪声
        J_only = J_only + noise

        X_t = (t1 - self.T / 2) * self.C / 2
        return J_only, X_t, Bj

    def generate(self, R_target, JSR_dB=8, noise_var=0.05):
        """
        生成复合信号。

        参数:
            R_target : 目标距离 (m)
            JSR_dB   : 干信比 (dB)
            noise_var: 白噪声方差系数

        返回:
            signal   : 复合信号 (复数数组，长度 N2)
            X_t      : 距离轴 (m)
            jam_info : 字典，包含干扰参数信息
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
        # 随机选取干扰带宽 (2~5 倍信号带宽)
        Bj = np.random.randint(2, 6) * self.B
        # 干扰采样率（脚本中用 5*Bj，确保奈奎斯特）
        fs = 5 * Bj
        N = round(self.T * fs)                 # 干扰采样点数

        # 生成线性扫频的载频偏移量：从 10 MHz 到 30 MHz 线性变化
        f_sweep = np.linspace(10e6, 30e6, N)    # 扫频范围（相对于 f0 的偏移）
        # 干扰瞬时载频：f0 + f_sweep - Bj/2 （脚本中公式）
        f1 = self.f0 + f_sweep - Bj / 2

        # 低通滤波器，用于产生带限噪声 xn1
        detlf = Bj / 2
        fir_coeff = signal.firwin(numtaps=N, cutoff=detlf/(fs/2), pass_zero='lowpass')
        Hlp = fft(fir_coeff, n=N)
        xn1 = ifft(fft(np.random.randn(N), n=N) * Hlp)
        xn1 = np.real(xn1)                     # 带限噪声

        # 调频斜率计算
        mfe = 0.015                             # 有效调频指数（固定）
        kfm = mfe * Bj / (np.std(xn1) + np.finfo(float).eps)

        # 噪声积分
        sigma_xn1 = np.cumsum(xn1) / fs

        # 干扰时间轴（干扰采样率）
        t_jam = np.linspace(0, self.T, N)

        # 生成干扰信号：幅度3，相位 = 2π*f1*t + 2π*kfm*∫xn1 dt + π/6
        FM_SP = 3 * np.exp(1j * (2 * np.pi * f1 * t_jam +
                                  2 * np.pi * kfm * sigma_xn1 +
                                  np.pi / 6))

        # --- JSR 标定 ---
        P_sig = self.rms(St) ** 2
        # 注意：MATLAB 中 Amp = sqrt((10^(JSR/10))*P_sig * N / sum(abs(FM_SP).^2))
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig * N) /
                        max(np.sum(np.abs(FM_SP) ** 2), np.finfo(float).eps))
        FM_SP = scale * FM_SP

        # --- 重采样到系统采样率 ---
        FM_SP_resampled = signal.resample(FM_SP, self.Nsys)

        # --- 加性白噪声 ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- 将干扰插入 PRP ---
        J_FM_SP = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_FM_SP[idx_start:idx_end + 1] = FM_SP_resampled[:len_ins]

        # --- 合成 ---
        J_FM_SP = J_FM_SP + St + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'FMNoiseSaopin',
            'bandwidth': Bj,
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
            'kfm': kfm,
            'f1': f1
        }
        
        return J_FM_SP, X_t, jam_info
    
if __name__ == "__main__":
    # 创建干扰实例
    jammer = FMNoiseSaopin()   # 可根据需要替换为 AMNoiseGaiJam 或 FMNoiseAimedJam

    # 测试不同的目标距离
    R_list = [1000, 5000, 10000]  # 米

    # 创建画布：3行3列，每行对应一个距离，三列分别为时域、频谱、时频图
    plt.figure(figsize=(18, 12))

    for i, R in enumerate(R_list, 1):
        # 生成复合信号（以 FMNoiseSaopin 为例）
        J, X_t, jam_info = jammer.generate(R, JSR_dB=8, noise_var=0.05)
        Bj = jam_info['bandwidth']

        # ---------- 第1列：时域实部 ----------
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.real(J))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度 (实部)')
        plt.title(f'R_target = {R} m, Bj = {Bj/1e6:.2f} MHz')
        plt.grid(True)

        # ---------- 第2列：频谱 ----------
        plt.subplot(3, 3, 3*i-1)
        f = np.fft.fftshift(np.fft.fftfreq(len(J), d=jammer.Ts))
        spec = np.fft.fftshift(np.fft.fft(J))
        plt.plot(f/1e6, 20*np.log10(np.abs(spec) + 1e-12))
        plt.xlabel('频率 (MHz)')
        plt.ylabel('幅度 (dB)')
        plt.title('频谱')
        plt.grid(True)
        plt.xlim([-100, 100])

        # ---------- 第3列：时频图 ----------
        plt.subplot(3, 3, 3*i)
        # 计算短时傅里叶变换
        f_spec, t_spec, Zxx = signal.spectrogram(J, fs=jammer.Fs,
                                                  nperseg=256, noverlap=128)
        # 使用 imshow 绘制时频图，并将横轴映射为距离
        plt.imshow(10*np.log10(np.abs(Zxx) + 1e-12),
                   aspect='auto',
                   extent=[X_t[0], X_t[-1], f_spec[0]/1e6, f_spec[-1]/1e6],
                   origin='lower', cmap='jet')
        plt.xlabel('距离 (m)')
        plt.ylabel('频率 (MHz)')
        plt.title('时频图')
        plt.colorbar(label='功率 (dB)')

    plt.tight_layout()
    plt.show()