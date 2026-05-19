import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift, fftfreq

plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'sans-serif'] # 设置中文字体
plt.rcParams['axes.unicode_minus'] = False # 正常显示负号

class WaveAgileRadar:
    """
    波形捷变抗干扰雷达仿真 (脉冲间波形切换)
    对应 MATLAB 函数 wave_agile.m
    """
    def __init__(self, mradar):
        self.C = 3.0e8
        self.kfm = mradar.get('kfm', 1)
        self.PRF = mradar['PRF']
        self.PRT = 1.0 / self.PRF
        self.Pw = mradar['Pw']
        self.Bw = mradar['Bw']
        self.fs = 4.0 * self.Bw
        self.Ts = 1.0 / self.fs
        
        self.Range = mradar['Range']
        self.Rmin = mradar['Rmin']
        self.Rmax = mradar['Rmax']
        self.PulseNum = mradar['PulseNum']
        
        self.Nwid = mradar['Nwid']
        self.f0 = mradar['f0']  # 基带载频假设为0
        self.Vt = mradar['Vt']
        self.t0 = mradar['t0']  # 接收窗时间序列
        self.Npw = mradar['Npw']
        self.Nfft = self.Nwid + self.Npw - 1
        
        self.Kref = self.Bw / self.Pw  # 参考斜率
        
    def rectpuls(self, t, width):
        """等效 MATLAB 的 rectpuls 函数"""
        return np.where(np.abs(t) <= width / 2.0, 1.0, 0.0)

    # ========================================================
    # 以下两个方法为原 MATLAB 缺失外部函数的替代实现
    # 目的是生成具有不同调制特性的基带信号
    # ========================================================
    def _wave_generate_nlfm_window(self, win_type, t, k_ratio):
        """模拟窗函数调制的非线性调频 (简化为带有幅度加成的 LFM)"""
        K = self.Kref * k_ratio
        phase = np.pi * K * t**2
        sig = np.exp(1j * phase)
        
        # 为了区分，根据类型加上轻微的幅度调制
        if win_type == 'hamming':
            win = np.hamming(len(t))
        elif win_type == 'hanning':
            win = np.hanning(len(t))
        elif win_type == 'kaiser':
            win = np.kaiser(len(t), 5)
        else:
            win = np.ones(len(t))
        return sig * win

    def _wave_generate_nlfm_s_curve(self, k_param, t, k_ratio):
        """模拟 S 曲线 NLFM (引入三次相位项模拟非线性)"""
        K = self.Kref * k_ratio
        # 引入 t^3 项模拟 S 型瞬时频率曲线
        phase = np.pi * K * t**2 + k_param * K * t**3 / self.Pw 
        return np.exp(1j * phase)
    # ========================================================

    def generate(self, wave_mode=1):
        wave_radar = {}
        wave_radar['tau'] = np.zeros(self.PulseNum)
        wave_radar['St'] = np.zeros((self.PulseNum, self.Npw), dtype=complex)
        wave_radar['Srti'] = np.zeros((self.PulseNum, self.Nwid), dtype=complex)
        
        # 脉内时间序列 (长度 Npw)
        tref = np.linspace(-self.Pw/2, self.Pw/2, self.Npw)
        
        # 波形捷变设置 (斜率捷变系数)
        K_set = self.Kref * np.array([1.3, 0.7, 1.1, 0.9])
        
        # 生成四个基信号 (长度 Npw)
        S1_base = self._wave_generate_nlfm_window('hamming', tref, K_set[0]/self.Kref)
        S2_base = self._wave_generate_nlfm_window('hanning', tref, K_set[1]/self.Kref)
        S3_base = self._wave_generate_nlfm_window('kaiser', tref, K_set[2]/self.Kref)
        k_param = 0.0736
        S4_base = self._wave_generate_nlfm_s_curve(k_param, tref, K_set[3]/self.Kref)
        
        # 根据 wave_mode 选择 3 种信号组合
        if wave_mode == 1:
            s_tx_temp = [S1_base, S2_base, S3_base]
        elif wave_mode == 2:
            s_tx_temp = [S1_base, S2_base, S4_base]
        elif wave_mode == 3:
            s_tx_temp = [S1_base, S3_base, S4_base]
        elif wave_mode == 4:
            s_tx_temp = [S2_base, S3_base, S4_base]
        else:
            s_tx_temp = [S1_base, S2_base, S3_base]

        # 生成回波
        for i in range(self.PulseNum):
            # 动态距离 (考虑径向速度)
            Rtm = self.Range - self.Vt * i * self.PRT
            wave_radar['tau'][i] = 2 * Rtm / self.C
            
            # 接收窗内的时间偏移
            td = self.t0 - wave_radar['tau'][i]
            
            # 生成带延迟的接收信号
            S1 = self.rectpuls(td, self.Pw) * self._wave_generate_nlfm_window('hamming', td, K_set[0]/self.Kref)
            S2 = self.rectpuls(td, self.Pw) * self._wave_generate_nlfm_window('hanning', td, K_set[1]/self.Kref)
            S3 = self.rectpuls(td, self.Pw) * self._wave_generate_nlfm_window('kaiser', td, K_set[2]/self.Kref)
            S4 = self.rectpuls(td, self.Pw) * self._wave_generate_nlfm_s_curve(k_param, td, K_set[3]/self.Kref)
            
            if wave_mode == 1:
                Srt = [S1, S2, S3]
            elif wave_mode == 2:
                Srt = [S1, S2, S4]
            elif wave_mode == 3:
                Srt = [S1, S3, S4]
            else:
                Srt = [S2, S3, S4]
            
            # 脉冲间循环切换波形 (Python 索引从0开始，i%3 对应 0,1,2)
            wave_idx = i % 3
            wave_radar['St'][i, :] = s_tx_temp[wave_idx]
            wave_radar['Srti'][i, :] = Srt[wave_idx]
            
        # 生成总回波 (修复了 MATLAB 中 echo_tx 未被正确赋值的 Bug)
        wave_radar['signal_radar'] = wave_radar['Srti'].flatten()
        
        return wave_radar

def test_wave_agile(seed=None):
    """
    测试波形捷变雷达（WaveAgileRadar）抗干扰策略。
    使用项目标准干扰生成器加载 RGPO（距离门拖引干扰）。
    对比标准 LFM 与波形捷变信号在 RGPO 干扰下的检测性能。

    参数:
        seed: 随机种子（None表示随机）

    返回:
        dict: {'RGPO': {'before': info, 'after': info, 'sinr_improvement': float}}
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    if seed is not None:
        np.random.seed(seed)

    from unified_framework import RadarEnvironment, JammerLoader, UnifiedEvaluator
    from scipy import signal as sig

    # 波形捷变雷达参数（与类内部默认一致）
    Pw = 20e-6
    Bw = 20e6
    f0 = 0  # 基带
    fs = 4.0 * Bw  # 80 MHz
    Ts = 1.0 / fs
    Range = 6000
    tau = 2 * Range / 3e8
    Npw = int(Pw / Ts)
    Nwid = int(100e-6 / Ts)
    t0 = np.arange(0, Nwid) * Ts

    mradar = {
        'PRF': 1000, 'Pw': Pw, 'Bw': Bw, 'Range': Range,
        'Rmin': 1000, 'Rmax': 15000, 'PulseNum': 1,
        'Nwid': Nwid, 'f0': f0, 'Vt': 300,
        'Npw': Npw, 't0': t0
    }

    wave_radar = WaveAgileRadar(mradar)
    wave_data = wave_radar.generate(wave_mode=1)

    St_agile = wave_data['St'][0]     # 波形捷变发射信号 (Npw)
    Srti_agile = wave_data['Srti'][0]  # 波形捷变接收回波 (Nwid)

    # 标准纯 LFM（同参数）
    t_tx = np.linspace(-Pw / 2, Pw / 2, Npw)
    K = Bw / Pw
    St_lfm = np.exp(1j * np.pi * K * t_tx**2)

    t_rx = t0 - tau
    rect = np.where(np.abs(t_rx) <= Pw / 2, 1.0, 0.0)
    Srti_lfm = rect * np.exp(1j * np.pi * K * t_rx**2)

    target_idx = int(tau / Ts) + Npw // 2

    jammer_types = ['RGPO']
    results = {}

    for jt in jammer_types:
        jammer = JammerLoader.load(jt)
        J_signal, _, _ = jammer.generate(R_target=Range, JSR_dB=10, noise_var=0.1)

        J = np.zeros(Nwid, dtype=complex)
        jlen = min(len(J_signal), Nwid)
        J[:jlen] = J_signal[:jlen]

        noise = 0.3 * (np.random.randn(Nwid) + 1j * np.random.randn(Nwid))

        # --- "处理前"：标准 LFM + RGPO ---
        pc_before = sig.fftconvolve(Srti_lfm + J + noise,
                                    np.conj(St_lfm[::-1]), mode='same')

        # --- "处理后"：波形捷变 + RGPO ---
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
        print(f"  测试: wave_agile vs {jt}")
        print(f"  处理前(LFM): 检测={info_before['is_detected']}, SINR={info_before['sinr_db']:.2f} dB")
        print(f"  处理后(WaveAgile): 检测={info_after['is_detected']}, SINR={info_after['sinr_db']:.2f} dB")
        print(f"  SINR改善: {info_after['sinr_db'] - info_before['sinr_db']:.2f} dB")
        print(f"{'='*55}")

    return results


def run_visual_test():
    """
    波形捷变雷达（WaveAgileRadar）的可视化测试。
    对比标准 LFM 与波形捷变信号，展示在 RGPO 干扰下的效果。
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from unified_framework import RadarEnvironment, JammerLoader
    from scipy import signal

    Pw = 20e-6
    Bw = 20e6
    f0 = 0
    fs = 4.0 * Bw
    Ts = 1.0 / fs
    Range = 6000
    tau = 2 * Range / 3e8
    Npw = int(Pw / Ts)
    Nwid = int(100e-6 / Ts)
    t0 = np.arange(0, Nwid) * Ts

    mradar = {
        'PRF': 1000, 'Pw': Pw, 'Bw': Bw, 'Range': Range,
        'Rmin': 1000, 'Rmax': 15000, 'PulseNum': 1,
        'Nwid': Nwid, 'f0': f0, 'Vt': 300,
        'Npw': Npw, 't0': t0
    }

    wave_radar = WaveAgileRadar(mradar)
    wave_data = wave_radar.generate(wave_mode=1)

    St_agile = wave_data['St'][0]
    Srti_agile = wave_data['Srti'][0]

    t_tx = np.linspace(-Pw / 2, Pw / 2, Npw)
    K = Bw / Pw
    St_lfm = np.exp(1j * np.pi * K * t_tx ** 2)

    t_rx = t0 - tau
    rect = np.where(np.abs(t_rx) <= Pw / 2, 1.0, 0.0)
    Srti_lfm = rect * np.exp(1j * np.pi * K * t_rx ** 2)

    target_idx = int(tau / Ts) + Npw // 2

    jammer_types = ['RGPO']

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
        axes[0, 0].plot(t_tx * 1e6, np.real(St_agile), label='波形捷变', alpha=0.7)
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
                        label='波形捷变', alpha=0.7)
        axes[0, 1].set_xlabel('频率 (MHz)')
        axes[0, 1].set_ylabel('幅度 (dB)')
        axes[0, 1].set_title(f'(b) 发射波形频谱 — {jt}')
        axes[0, 1].legend()
        axes[0, 1].grid(True)

        # (c) 回波时频图（LFM + RGPO）
        nperseg = min(256, Nwid // 4)
        f_spec, t_spec, Zxx = signal.stft(Srti_lfm + J + noise, fs=fs, nperseg=nperseg)
        im1 = axes[0, 2].pcolormesh(t_spec * 1e6, f_spec / 1e6, np.abs(Zxx),
                                     shading='gouraud', cmap='jet')
        axes[0, 2].set_xlabel('时间 (μs)')
        axes[0, 2].set_ylabel('频率 (MHz)')
        axes[0, 2].set_title(f'(c) 回波时频图（LFM + {jt}）')
        plt.colorbar(im1, ax=axes[0, 2])

        # (d) 回波时频图（波形捷变 + RGPO）
        f_spec2, t_spec2, Zxx2 = signal.stft(Srti_agile + J + noise, fs=fs, nperseg=nperseg)
        im2 = axes[1, 0].pcolormesh(t_spec2 * 1e6, f_spec2 / 1e6, np.abs(Zxx2),
                                     shading='gouraud', cmap='jet')
        axes[1, 0].set_xlabel('时间 (μs)')
        axes[1, 0].set_ylabel('频率 (MHz)')
        axes[1, 0].set_title(f'(d) 回波时频图（波形捷变 + {jt}）')
        plt.colorbar(im2, ax=axes[1, 0])

        # (e) 脉压距离像-线性
        range_axis = np.arange(len(pc_before)) * 3e8 / (2 * fs)
        axes[1, 1].plot(range_axis, np.abs(pc_before), label='标准LFM', alpha=0.7)
        axes[1, 1].plot(range_axis, np.abs(pc_after), label='波形捷变', alpha=0.7)
        axes[1, 1].set_xlabel('距离 (m)')
        axes[1, 1].set_ylabel('幅度')
        axes[1, 1].set_title(f'(e) 脉压距离像 — {jt}')
        axes[1, 1].legend()
        axes[1, 1].grid(True)

        # (f) 脉压距离像-dB
        axes[1, 2].plot(range_axis, 20 * np.log10(np.abs(pc_before) + 1e-10),
                        label='标准LFM', alpha=0.7)
        axes[1, 2].plot(range_axis, 20 * np.log10(np.abs(pc_after) + 1e-10),
                        label='波形捷变', alpha=0.7)
        axes[1, 2].set_xlabel('距离 (m)')
        axes[1, 2].set_ylabel('幅度 (dB)')
        axes[1, 2].set_title(f'(f) 脉压距离像 (dB) — {jt}')
        axes[1, 2].legend()
        axes[1, 2].grid(True)

        plt.tight_layout()
        plt.suptitle(f'波形捷变雷达 vs {jt}', fontsize=14, y=1.02)
        plt.show()


if __name__ == "__main__":
    run_visual_test()