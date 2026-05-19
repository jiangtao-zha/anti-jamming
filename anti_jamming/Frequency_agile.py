import numpy as np
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif']
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

def test_frequency_agile(seed=None):
    """
    测试频率捷变雷达（FrequencyAgileRadar）抗干扰策略。
    使用项目标准干扰生成器加载 FMNoiseSaopin、ISDJ。
    对比标准 LFM 与 Costas-LFM 频率捷变波形在相同干扰下的检测性能。

    参数:
        seed: 随机种子（None表示随机）

    返回:
        dict: {jammer_type: {'before': info, 'after': info, 'sinr_improvement': float}}
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    if seed is not None:
        np.random.seed(seed)

    from unified_framework import RadarEnvironment, JammerLoader, UnifiedEvaluator
    from scipy import signal as sig

    # 频率捷变雷达参数（与类内部默认一致）
    Pw = 20e-6
    Bw = 20e6
    f0 = 15e6
    fs = 4.0 * Bw  # 80 MHz
    Ts = 1.0 / fs
    Range = 6000
    tau = 2 * Range / 3e8
    Npw = int(Pw / Ts)
    Nwid = int(100e-6 / Ts)
    t0 = np.arange(0, Nwid) * Ts

    agile_par = {
        'PRF': 1000, 'Pw': Pw, 'Bw': Bw, 'Range': Range,
        'Rmin': 1000, 'Rmax': 15000, 'PulseNum': 1,
        'Nwid': Nwid, 'f0': f0, 'Vt': 150,
        'Npw': Npw, 'fc': 10e9, 't0': t0
    }

    agile_radar = FrequencyAgileRadar(agile_par)
    wave_data = agile_radar.generate(seq_type=1)

    St_agile = wave_data['St'][0]   # Costas-LFM 发射信号 (Npw)
    Srti_agile = wave_data['Srti'][0]  # Costas-LFM 接收回波 (Nwid)

    # 标准纯 LFM（与 agile 同参数）
    t_tx = np.linspace(-Pw / 2, Pw / 2, Npw)
    K = Bw / Pw
    St_lfm = np.exp(1j * 2 * np.pi * (f0 * t_tx + 0.5 * K * t_tx**2))

    t_rx = t0 - tau
    rect = np.where(np.abs(t_rx) <= Pw / 2, 1.0, 0.0)
    Srti_lfm = rect * np.exp(1j * 2 * np.pi * (f0 * t_rx + 0.5 * K * t_rx**2))

    # 目标在距离像中的索引（匹配滤波后峰值位置）
    target_idx = int(tau / Ts) + Npw // 2

    jammer_types = ['FMNoiseSaopin', 'ISDJ']
    results = {}

    for jt in jammer_types:
        jammer = JammerLoader.load(jt)
        J_signal, _, _ = jammer.generate(R_target=Range, JSR_dB=10, noise_var=0.1)

        # 截取/补零干扰信号到 Nwid 长度
        J = np.zeros(Nwid, dtype=complex)
        jlen = min(len(J_signal), Nwid)
        J[:jlen] = J_signal[:jlen]

        noise = 0.3 * (np.random.randn(Nwid) + 1j * np.random.randn(Nwid))

        # --- "处理前"：标准 LFM + 干扰 ---
        pc_before = sig.fftconvolve(Srti_lfm + J + noise,
                                    np.conj(St_lfm[::-1]), mode='same')

        # --- "处理后"：频率捷变 Costas-LFM + 干扰 ---
        pc_after = sig.fftconvolve(Srti_agile + J + noise,
                                   np.conj(St_agile[::-1]), mode='same')

        evaluator = UnifiedEvaluator()
        info_before = evaluator.evaluate(np.abs(pc_before), target_idx)
        info_after = evaluator.evaluate(np.abs(pc_after), target_idx)

        results[jt] = {
            'before': info_before,
            'after': info_after,
            'sinr_improvement': info_after['sinr_db'] - info_before['sinr_db']
        }

        print(f"\n{'='*55}")
        print(f"  测试: Frequency_agile vs {jt}")
        print(f"  处理前(LFM): 检测={info_before['is_detected']}, SINR={info_before['sinr_db']:.2f} dB")
        print(f"  处理后(Costas): 检测={info_after['is_detected']}, SINR={info_after['sinr_db']:.2f} dB")
        print(f"  SINR改善: {info_after['sinr_db'] - info_before['sinr_db']:.2f} dB")
        print(f"{'='*55}")

    return results


def run_visual_test():
    """
    频率捷变雷达（FrequencyAgileRadar）的可视化测试。
    对比标准 LFM 与 Costas-LFM 波形，展示在 FMNoiseSaopin / ISDJ 干扰下的效果。
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from unified_framework import RadarEnvironment, JammerLoader
    from scipy import signal

    Pw = 20e-6
    Bw = 20e6
    f0 = 15e6
    fs = 4.0 * Bw
    Ts = 1.0 / fs
    Range = 6000
    tau = 2 * Range / 3e8
    Npw = int(Pw / Ts)
    Nwid = int(100e-6 / Ts)
    t0 = np.arange(0, Nwid) * Ts

    agile_par = {
        'PRF': 1000, 'Pw': Pw, 'Bw': Bw, 'Range': Range,
        'Rmin': 1000, 'Rmax': 15000, 'PulseNum': 1,
        'Nwid': Nwid, 'f0': f0, 'Vt': 150,
        'Npw': Npw, 'fc': 10e9, 't0': t0
    }

    agile_radar = FrequencyAgileRadar(agile_par)
    wave_data = agile_radar.generate(seq_type=1)

    St_agile = wave_data['St'][0]
    Srti_agile = wave_data['Srti'][0]

    t_tx = np.linspace(-Pw / 2, Pw / 2, Npw)
    K = Bw / Pw
    St_lfm = np.exp(1j * 2 * np.pi * (f0 * t_tx + 0.5 * K * t_tx ** 2))

    t_rx = t0 - tau
    rect = np.where(np.abs(t_rx) <= Pw / 2, 1.0, 0.0)
    Srti_lfm = rect * np.exp(1j * 2 * np.pi * (f0 * t_rx + 0.5 * K * t_rx ** 2))

    target_idx = int(tau / Ts) + Npw // 2

    jammer_types = ['FMNoiseSaopin', 'ISDJ']

    for jt in jammer_types:
        np.random.seed(42)
        jammer = JammerLoader.load(jt)
        J_signal, _, _ = jammer.generate(R_target=Range, JSR_dB=10, noise_var=0.1)

        J = np.zeros(Nwid, dtype=complex)
        jlen = min(len(J_signal), Nwid)
        J[:jlen] = J_signal[:jlen]

        noise = 0.3 * (np.random.randn(Nwid) + 1j * np.random.randn(Nwid))

        pc_before = signal.fftconvolve(Srti_lfm + J + noise,
                                       np.conj(St_lfm[::-1]), mode='same')
        pc_after = signal.fftconvolve(Srti_agile + J + noise,
                                      np.conj(St_agile[::-1]), mode='same')

        fig, axes = plt.subplots(2, 3, figsize=(18, 10))

        # (a) 发射波形对比（实部）
        axes[0, 0].plot(t_tx * 1e6, np.real(St_lfm), label='标准LFM', alpha=0.7)
        axes[0, 0].plot(t_tx * 1e6, np.real(St_agile), label='Costas-LFM', alpha=0.7)
        axes[0, 0].set_xlabel('时间 (μs)')
        axes[0, 0].set_ylabel('实部')
        axes[0, 0].set_title(f'(a) 发射波形对比 — {jt}')
        axes[0, 0].legend()
        axes[0, 0].grid(True)

        # (b) 发射波形频谱
        freq_tx = np.fft.fftfreq(Npw, 1 / fs)
        freq_tx_shift = np.fft.fftshift(freq_tx)
        spec_lfm = np.fft.fftshift(np.abs(np.fft.fft(St_lfm)))
        spec_agile = np.fft.fftshift(np.abs(np.fft.fft(St_agile)))
        axes[0, 1].plot(freq_tx_shift / 1e6, 20 * np.log10(spec_lfm + 1e-10),
                        label='标准LFM', alpha=0.7)
        axes[0, 1].plot(freq_tx_shift / 1e6, 20 * np.log10(spec_agile + 1e-10),
                        label='Costas-LFM', alpha=0.7)
        axes[0, 1].set_xlabel('频率 (MHz)')
        axes[0, 1].set_ylabel('幅度 (dB)')
        axes[0, 1].set_title(f'(b) 发射波形频谱 — {jt}')
        axes[0, 1].legend()
        axes[0, 1].grid(True)

        # (c) 回波时频图（LFM + 干扰）
        nperseg = min(256, Nwid // 4)
        f_spec, t_spec, Zxx = signal.stft(Srti_lfm + J + noise, fs=fs, nperseg=nperseg)
        im1 = axes[0, 2].pcolormesh(t_spec * 1e6, f_spec / 1e6, np.abs(Zxx),
                                     shading='gouraud', cmap='jet')
        axes[0, 2].set_xlabel('时间 (μs)')
        axes[0, 2].set_ylabel('频率 (MHz)')
        axes[0, 2].set_title(f'(c) 回波时频图（LFM + {jt}）')
        plt.colorbar(im1, ax=axes[0, 2])

        # (d) 回波时频图（Costas-LFM + 干扰）
        f_spec2, t_spec2, Zxx2 = signal.stft(Srti_agile + J + noise, fs=fs, nperseg=nperseg)
        im2 = axes[1, 0].pcolormesh(t_spec2 * 1e6, f_spec2 / 1e6, np.abs(Zxx2),
                                     shading='gouraud', cmap='jet')
        axes[1, 0].set_xlabel('时间 (μs)')
        axes[1, 0].set_ylabel('频率 (MHz)')
        axes[1, 0].set_title(f'(d) 回波时频图（Costas-LFM + {jt}）')
        plt.colorbar(im2, ax=axes[1, 0])

        # (e) 脉压距离像-线性
        range_axis = np.arange(len(pc_before)) * 3e8 / (2 * fs)
        axes[1, 1].plot(range_axis, np.abs(pc_before), label='标准LFM', alpha=0.7)
        axes[1, 1].plot(range_axis, np.abs(pc_after), label='Costas-LFM', alpha=0.7)
        axes[1, 1].set_xlabel('距离 (m)')
        axes[1, 1].set_ylabel('幅度')
        axes[1, 1].set_title(f'(e) 脉压距离像 — {jt}')
        axes[1, 1].legend()
        axes[1, 1].grid(True)

        # (f) 脉压距离像-dB
        axes[1, 2].plot(range_axis, 20 * np.log10(np.abs(pc_before) + 1e-10),
                        label='标准LFM', alpha=0.7)
        axes[1, 2].plot(range_axis, 20 * np.log10(np.abs(pc_after) + 1e-10),
                        label='Costas-LFM', alpha=0.7)
        axes[1, 2].set_xlabel('距离 (m)')
        axes[1, 2].set_ylabel('幅度 (dB)')
        axes[1, 2].set_title(f'(f) 脉压距离像 (dB) — {jt}')
        axes[1, 2].legend()
        axes[1, 2].grid(True)

        plt.tight_layout()
        plt.suptitle(f'频率捷变雷达 vs {jt}', fontsize=14, y=1.02)
        plt.show()


if __name__ == "__main__":
    run_visual_test()