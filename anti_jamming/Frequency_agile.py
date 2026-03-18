import numpy as np
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
class FrequencyAgileRadar:
    """
    频率捷变抗干扰雷达仿真，使用 Costas-LFM 和子匹配滤波。
    对应 MATLAB 函数 frequency_agile.m
    """

    def __init__(self, radar_par):
        """
        初始化雷达参数。

        radar_par : dict 包含以下字段：
            PRF      : 脉冲重复频率 (Hz)
            Pw       : 脉宽 (s)
            Bw       : 带宽 (Hz)
            Range    : 初始目标距离 (m)
            Rmin     : 最小距离 (m)
            Rmax     : 最大距离 (m)
            PulseNum : 脉冲数
            Nwid     : 接收窗采样点数
            f0       : 中心频率 (Hz)
            Vt       : 目标径向速度 (m/s) (正为靠近)
            Npw      : 脉冲内采样点数
            fc       : 载频？实际上fc与f0可能相同，但用于多普勒计算
            t0       : 接收窗时间向量 (1xNwid)
        """
        self.C = 3.0e8
        self.PRF = radar_par['PRF']
        self.PRT = 1.0 / self.PRF
        self.Pw = radar_par['Pw']
        self.Bw = radar_par['Bw']
        self.fs = 4.0 * self.Bw               # 采样频率
        self.Ts = 1.0 / self.fs
        self.Range = radar_par['Range']
        self.Rmin = radar_par['Rmin']
        self.Rmax = radar_par['Rmax']
        self.PulseNum = radar_par['PulseNum']
        self.Nwid = radar_par['Nwid']          # 接收窗采样点数
        self.f0 = radar_par['f0']
        self.Vt = radar_par['Vt']
        self.Npw = radar_par['Npw']            # 脉冲内采样点数
        self.fc = radar_par['fc']               # 用于多普勒计算
        self.t0 = radar_par['t0']               # 接收窗时间向量 (1xNwid)

        # 派生参数
        self.T = self.Pw
        self.B = self.Bw
        self.K = self.B / self.T                # 调频斜率
        self.M = 10                              # 子脉冲数（固定为10）
        self.delta_t = self.T / self.M
        self.delta_f = self.B / self.M
        self.Nfft = self.Nwid + self.Npw - 1     # FFT点数

    def _costas_sequence(self, seq_type):
        """
        根据输入类型返回 Costas 序列（长度为10）。
        seq_type : 1,2,3 或其他
        """
        if seq_type == 1:
            return np.array([1, 2, -2, 1, -4, 3, -2, 2, 3, 5])
        elif seq_type == 2:
            return np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        elif seq_type == 3:
            return np.array([1, 2, 2, 3, 5, 4, 9, 6, 3, 6])
        else:
            return np.array([1, 2, 1, 3, 5, 6, 7, 3, 3, 6])

    def generate(self, seq_type=1, RCS=1.0):
        """
        生成所有脉冲的发射信号和回波。

        参数:
            seq_type : Costas序列类型 (1,2,3或其他)
            RCS      : 雷达散射截面积 (默认1)

        返回:
            wave_radar : dict 包含所有雷达数据和信号
        """
        wave_radar = {}
        wave_radar['zhudong_antijamming'] = 2
        wave_radar['kfm'] = None                 # 原代码未赋值，保留
        wave_radar['C'] = self.C
        wave_radar['PRT'] = self.PRT
        wave_radar['Pw'] = self.Pw
        wave_radar['Bw'] = self.Bw
        wave_radar['fs'] = self.fs
        wave_radar['Ts'] = self.Ts
        wave_radar['Range'] = self.Range
        wave_radar['Rmin'] = self.Rmin
        wave_radar['Rmax'] = self.Rmax
        wave_radar['PulseNum'] = self.PulseNum
        wave_radar['Nwid'] = self.Nwid
        wave_radar['f0'] = self.f0
        wave_radar['Vt'] = self.Vt
        wave_radar['M'] = self.M
        wave_radar['Npw'] = self.Npw
        wave_radar['Nfft'] = self.Nfft
        wave_radar['fc'] = self.fc
        wave_radar['delta_t'] = self.delta_t
        wave_radar['delta_f'] = self.delta_f

        # 选择Costas序列
        c = self._costas_sequence(seq_type)

        # 时间向量（以脉冲中心为参考，长度 Npw）
        tref = np.linspace(-self.Pw/2, self.Pw/2, self.Npw)

        # 初始化存储
        St_sub = []                     # 每个脉冲的子脉冲参考 (PulseNum x M x Npw)
        St = np.zeros((self.PulseNum, self.Npw), dtype=complex)
        Srti = np.zeros((self.PulseNum, self.Nwid), dtype=complex)
        tau = np.zeros(self.PulseNum)   # 每个脉冲的时延

        for i in range(self.PulseNum):
            # 动态目标距离 (考虑速度，目标靠近为正)
            Rtm = self.Range - self.Vt * i * self.PRT
            tau[i] = 2 * Rtm / self.C
            fd = 2 * self.Vt * self.fc / self.C   # 多普勒频率 (假设fc为载频)

            # 生成当前脉冲的 M 个子脉冲参考信号 (无时延、无多普勒)
            St_sub_i = np.zeros((self.M, self.Npw), dtype=complex)
            for m in range(self.M):
                # 子脉冲中心时间 (以脉冲中心为0点)
                center = (2*(m+1) - 1) * self.delta_t / 2 - self.Pw/2
                t_rel = tref - center
                rect = np.abs(t_rel) <= self.delta_t / 2
                lfm_phase = np.exp(1j * np.pi * self.K * t_rel**2)
                # 载波部分：原中心频率 f0 加上 Costas 频率步进
                carrier_phase = np.exp(1j * 2 * np.pi * self.f0 * tref) * \
                                np.exp(1j * 2 * np.pi * self.delta_f * (c[m] - (self.M+1)/2) * tref)
                St_sub_i[m, :] = rect * lfm_phase * carrier_phase

            # 复合发射信号（参考）
            St[i, :] = np.sum(St_sub_i, axis=0)

            # 存储子脉冲参考
            St_sub.append(St_sub_i)

            # 生成回波信号 (考虑时延和多普勒)
            for m in range(self.M):
                center = (2*(m+1) - 1) * self.delta_t / 2 - self.Pw/2
                t_rel = self.t0 - tau[i] - center
                rect = np.abs(t_rel) <= self.delta_t / 2
                lfm_phase = np.exp(1j * np.pi * self.K * t_rel**2)
                # 载波部分：增加了多普勒频移 fd
                carrier_phase = np.exp(1j * 2 * np.pi * (self.f0 + self.delta_f * (c[m] - (self.M+1)/2) + fd) * t_rel)
                Srti[i, :] += RCS * rect * lfm_phase * carrier_phase

        wave_radar['tau'] = tau
        wave_radar['St'] = St
        wave_radar['St_sub'] = St_sub        # 列表，每个元素是 M x Npw 的数组
        wave_radar['Srti'] = Srti
        wave_radar['tref'] = tref
        wave_radar['t0'] = self.t0

        return wave_radar

import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift, fftfreq

# 假设你的 FrequencyAgileRadar 类已经定义在上方
# from your_module import FrequencyAgileRadar 

def run_agile_radar_test():
    # ==========================================
    # 1. 参数初始化 (构建雷达物理环境)
    # ==========================================
    C = 3.0e8
    Pw = 20e-6             # 脉宽 20us (适当加长以便在时频图中看得更清晰)
    Bw = 20e6              # 总带宽 20MHz
    fs = 4.0 * Bw          # 采样率 80MHz
    Ts = 1.0 / fs
    
    Range = 6000           # 目标距离 6km
    tau = 2 * Range / C    # 目标回波时延 40us
    
    # 接收窗设置 (观察 0 到 100us 的时间段)
    Twid = 100e-6
    Nwid = int(Twid / Ts)
    t0 = np.arange(0, Nwid) * Ts
    
    radar_par = {
        'PRF': 1000,             # 脉冲重复频率 1kHz
        'Pw': Pw,
        'Bw': Bw,
        'Range': Range,
        'Rmin': 1000,
        'Rmax': 15000,
        'PulseNum': 1,           # 测试中我们只看单个脉冲
        'Nwid': Nwid,            # 接收窗点数
        'f0': 15e6,              # 中频载频 15MHz
        'Vt': 150,               # 目标径向速度 150m/s
        'Npw': int(Pw / Ts),     # 脉内采样点数 (1600点)
        'fc': 10e9,              # 射频载频 10GHz (X波段，用于计算多普勒)
        't0': t0                 # 接收时间轴
    }

    # ==========================================
    # 2. 实例化并生成信号
    # ==========================================
    print("正在生成 Costas-LFM 频率捷变雷达信号...")
    radar = FrequencyAgileRadar(radar_par)
    
    # 使用 seq_type=2 (线性跳频序列 [1,2,3...10]) 或 1 (伪随机序列) 来对比
    # 这里用 seq_type=1 最能体现 Costas 伪随机跳频的抗干扰魅力
    wave_data = radar.generate(seq_type=1, RCS=1.0)
    
    # 提取第一个脉冲的数据
    St = wave_data['St'][0]          # 发射信号 (长度为 Npw)
    Srti = wave_data['Srti'][0]      # 接收回波信号 (长度为 Nwid)
    tref = wave_data['tref']         # 发射信号的时间轴
    t_rx = wave_data['t0']           # 接收窗的时间轴

    # ==========================================
    # 3. 绘图展示 (时域、频域、时频域)
    # ==========================================
    plt.figure(figsize=(16, 10))

    # --- 图 1：时域幅度 (Tx 与 Rx 的延迟关系) ---
    plt.subplot(2, 2, 1)
    # 发射信号的绝对时间轴 (假设在 t=0 处发射)
    t_tx_actual = tref + Pw/2 
    plt.plot(t_tx_actual * 1e6, np.real(St), label='发射信号 (实部)', alpha=0.8)
    plt.plot(t_rx * 1e6, np.real(Srti), label=f'接收回波 (距离={Range}m)', color='red', alpha=0.7)
    plt.xlabel('时间 (us)')
    plt.ylabel('幅度')
    plt.title('1. 时域波形 (展现测距时延)')
    plt.legend()
    plt.grid(True)

    # --- 图 2：频域频谱 (发射信号) ---
    plt.subplot(2, 2, 2)
    # 计算发射信号的频谱
    f_axis = fftshift(fftfreq(len(St), Ts))
    St_spec = fftshift(fft(St))
    St_spec_dB = 20 * np.log10(np.abs(St_spec) + 1e-10)
    
    plt.plot(f_axis / 1e6, St_spec_dB, color='purple')
    plt.xlabel('频率 (MHz)')
    plt.ylabel('功率 (dB)')
    plt.title(f'2. 发射信号频谱 (中心频率 {radar_par["f0"]/1e6}MHz, 总带宽 {Bw/1e6}MHz)')
    plt.xlim([-5, radar_par['f0']/1e6 + Bw/1e6 + 20])
    plt.grid(True)

    # --- 图 3：时频图 (Spectrogram) - 频率捷变的核心 ---
    # --- 图 3：时频图 (Spectrogram) - 频率捷变的核心 ---
    plt.subplot(2, 1, 2)
    # 设置 STFT 参数
    nperseg = int((Pw / radar.M) / Ts) // 2 
    
    # 明确指定 return_onesided=False 以获取完整的复信号双边谱
    f_stft, t_stft, Zxx = signal.spectrogram(St, fs=fs, window='hann', 
                                             nperseg=nperseg, noverlap=nperseg-2,
                                             return_onesided=False)
    
    # 【核心修复】：对频率轴和时频矩阵进行 fftshift，使其变成单调递增序列
    f_stft = fftshift(f_stft)
    Zxx = fftshift(Zxx, axes=0)
    
    # 转换为 dB 并绘制
    Zxx_dB = 10 * np.log10(np.abs(Zxx) + 1e-10)
    
    # 现在 f_stft 是单调递增的，pcolormesh 可以正常渲染了
    plt.pcolormesh(t_stft * 1e6, f_stft / 1e6, Zxx_dB, shading='auto', cmap='jet')
    
    # 添加子脉冲分割线辅助观察
    for m in range(radar.M + 1):
        plt.axvline(x=(m * radar.delta_t) * 1e6, color='white', linestyle='--', alpha=0.5)
        
    plt.colorbar(label='功率密度 (dB/Hz)')
    plt.xlabel('脉内时间 (us)')
    plt.ylabel('频率 (MHz)')
    plt.title('3. 时频域分析 (Spectrogram) - 观察 Costas 序列跳频与 LFM 调频特征')
    
    # 因为加上了负频，我们将 Y 轴显示范围调整为 0 到 稍大于最高频率即可
    plt.ylim([0, radar_par['f0']/1e6 + Bw/1e6 + 5])

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_agile_radar_test()