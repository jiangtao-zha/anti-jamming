import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, ifft
plt.rcParams['font.sans-serif'] = ['SimHei'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号

class AMNoiseGaiJam:
    """
    生成单个 PRP 内的复合信号：目标回波 + 噪声调幅干扰(AM noise) + 白噪声。
    对应 MATLAB 函数 AMnoise_gai_jam。
    """

    def __init__(self, C=3e8, f0=50e6, T=24e-6, Tr=100e-6, B=20e6):
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
        self.K = B / T          # 调频斜率

        # 统一系统采样率
        self.Fs = 2 * (B + f0)
        self.Ts = 1 / self.Fs
        self.Nsys = round(T / self.Ts)          # 脉内点数

    def rectpuls(self, t, width):
        """生成矩形脉冲，与 MATLAB rectpuls 行为一致：在 [0, width) 内为 1，其余为 0。"""
        return np.where((t >= 0) & (t < width), 1.0, 0.0)

    def rms(self, x):
        """计算复信号的 RMS 值 (均方根)"""
        return np.sqrt(np.mean(np.abs(x) ** 2))

    def generate(self, R_target, JSR_dB=12, noise_var=0.1):
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
        N2 = np.ceil(self.Tr / self.Ts).astype(int)          # PRP 内点数
        t1 = np.linspace(2 * R / self.C, self.Tr + 2 * R / self.C, N2)   # 观测时间轴
        td = t1 - 2 * R / self.C                                        # 往返延时对齐的时间

        # --- 目标回波 ---
        # 矩形窗位置：rectpuls(td - T, T)
        window = self.rectpuls(td - self.T, self.T)
        St = window * np.exp(1j * (np.pi * self.K * (td - self.T) ** 2 +
                                    2 * np.pi * self.f0 * (td - self.T)))

        # --- 噪声调幅干扰 ---
        m = 1               # 调制度
        f1 = self.f0        # 干扰载频
        phi = np.pi / 6     # 初相

        # 随机选取干扰带宽 (2~5 倍信号带宽)
        Bj = np.random.randint(2, 6) * self.B
        detlf = Bj / 2      # 低通截止频率

        # 干扰脉内时间轴
        t_jam = np.linspace(0, self.T, self.Nsys)

        # 设计低通滤波器 (FIR)
        # 归一化截止频率 = detlf / (Fs/2)
        cutoff = detlf / (self.Fs / 2)
        # firwin 设计长度为 Nsys 的滤波器（阶数 Nsys-1）
        fir_coeff = signal.firwin(numtaps=self.Nsys, cutoff=cutoff, pass_zero='lowpass')
        # 获取滤波器频率响应 (Nsys 点 FFT)
        Hlp = fft(fir_coeff, n=self.Nsys)

        # 生成高斯白噪声，并滤波得到带限噪声
        noise_band = np.random.randn(self.Nsys) + 1j * np.random.randn(self.Nsys)  # 复噪声
        # 频域相乘 (循环卷积)
        xn1 = ifft(fft(noise_band, n=self.Nsys) * Hlp)
        xn1 = np.real(xn1)  # 取实部（应为实数，但消除微小虚部）

        # 生成 AM 干扰
        wn2 = (1 + m * xn1) * np.exp(1j * (2 * np.pi * f1 * t_jam + phi))

        # --- 加性白噪声 (PRP 长度) ---
        noise = np.random.randn(N2) * np.sqrt(noise_var)

        # --- JSR 标定 ---
        P_sig = self.rms(St) ** 2
        P_jam_now = self.rms(wn2) ** 2
        scale = np.sqrt((10 ** (JSR_dB / 10) * P_sig) / max(P_jam_now, np.finfo(float).eps))
        wn2 = scale * wn2

        # --- 将干扰插入到 PRP 时间线上 ---
        J_AM = np.zeros(N2, dtype=complex)
        idx_start = round((self.T / 2) * self.Fs)      # Python 索引从 0 开始
        idx_end = min(idx_start + self.Nsys - 1, N2 - 1)
        len_ins = max(0, idx_end - idx_start + 1)
        if len_ins > 0:
            J_AM[idx_start:idx_end + 1] = wn2[:len_ins]

        # --- 合成信号 ---
        J_AM = J_AM + St + noise

        # --- 距离轴 ---
        X_t = (t1 - self.T / 2) * self.C / 2

        # --- 干扰信息字典 ---
        jam_info = {
            'jammer_type': 'AMNoiseGaiJam',
            'bandwidth': Bj,
            'JSR_dB': JSR_dB,
            'noise_var': noise_var,
            'R_target': R_target,
            'target_signal': St,     # 目标回波信号
            'noise_signal': noise,   # 噪声信号
            'f0': self.f0,
            'T': self.T,
            'B': self.B,
            'Tr': self.Tr,
            'Fs': self.Fs
        }
        
        return J_AM, X_t, jam_info


if __name__ == "__main__":
    # 创建实例（可替换为其他干扰类）
    jammer = AMNoiseGaiJam()   # 可换为 FMNoiseAimedJam() 或 FMSweepJam()

    # 测试不同的目标距离
    R_list = [1000, 5000, 10000]  # 米

    plt.figure(figsize=(18, 12))   # 调整画布大小适应三列

    for i, R in enumerate(R_list, 1):
        # 生成复合信号
        J_AM, X_t, jam_info = jammer.generate(R)
        Bj = jam_info['bandwidth']

        # ---------- 第1列：时域幅度 ----------
        plt.subplot(3, 3, 3*i-2)
        plt.plot(X_t, np.abs(J_AM))
        plt.xlabel('距离 (m)')
        plt.ylabel('幅度')
        plt.title(f'R_target = {R} m (Bj = {Bj/1e6:.2f} MHz)')
        plt.grid(True)

        # ---------- 第2列：频谱 ----------
        plt.subplot(3, 3, 3*i-1)
        f = np.fft.fftshift(np.fft.fftfreq(len(J_AM), d=jammer.Ts))
        spec = np.fft.fftshift(np.fft.fft(J_AM))
        plt.plot(f/1e6, 20*np.log10(np.abs(spec) + 1e-12))
        plt.xlabel('频率 (MHz)')
        plt.ylabel('幅度 (dB)')
        plt.title('频谱')
        plt.grid(True)
        plt.xlim([-100, 100])

        # ---------- 第3列：时频图 ----------
        plt.subplot(3, 3, 3*i)
        # 计算短时傅里叶变换
        f_spec, t_spec, Zxx = signal.spectrogram(J_AM, fs=jammer.Fs,
                                                  nperseg=256, noverlap=128)
        # 将时间轴转换为距离轴（t_spec 是时间，需要映射到距离）
        # 信号的观测时间轴 t1 对应 X_t，但 spectrogram 返回的时间 t_spec 是相对于信号起始的，
        # 我们需要将其转换到与 X_t 相同的尺度。
        # 简便方法：利用 X_t 的第一个值和最后一个值进行线性映射
        t_start = 2*R/jammer.C          # 观测起始时间（与 t1 起点对应）
        t_end = jammer.Tr + 2*R/jammer.C
        # t_spec 范围是 [0, len(J_AM)/Fs]，对应实际时间范围 [t_start, t_end]
        t_actual = t_start + t_spec
        dist_axis = (t_actual - jammer.T/2) * jammer.C/2   # 转换为距离（与 X_t 公式一致）

        plt.imshow(10*np.log10(np.abs(Zxx) + 1e-12),
                   aspect='auto',
                   extent=[dist_axis[0], dist_axis[-1], f_spec[0]/1e6, f_spec[-1]/1e6],
                   origin='lower', cmap='jet')
        plt.xlabel('距离 (m)')
        plt.ylabel('频率 (MHz)')
        plt.title('时频图')
        plt.colorbar(label='功率 (dB)')

    plt.tight_layout()
    plt.show()