import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.fft import fft, fftshift, fftfreq

plt.rcParams['font.sans-serif'] = ['SimHei'] # 设置中文字体
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

# ==========================================================
# 测试验证脚本
# ==========================================================
def run_wave_agile_test():
    C = 3.0e8
    Pw = 20e-6
    Bw = 20e6
    fs = 4.0 * Bw
    Ts = 1.0 / fs
    
    # 构建接收时间轴 (0 到 100 us)
    Nwid = int(100e-6 / Ts)
    t0 = np.arange(0, Nwid) * Ts
    
    # 初始化雷达参数 (产生 6 个脉冲，以便看清两轮完整的波形切换)
    mradar = {
        'PRF': 1000,
        'Pw': Pw,
        'Bw': Bw,
        'Range': 6000,
        'Rmin': 1000,
        'Rmax': 15000,
        'PulseNum': 6,  
        'Nwid': Nwid,
        'f0': 0,
        'Vt': 300, # 目标速度 300m/s
        'Npw': int(Pw / Ts),
        't0': t0
    }

    print("正在生成波形捷变雷达信号...")
    radar = WaveAgileRadar(mradar)
    wave_data = radar.generate(wave_mode=1)
    
    # ==========================================
    # 绘图展示
    # ==========================================
    plt.figure(figsize=(16, 12))

    # --- 1. 时域：前三个不同波形脉冲的实部对比 ---
    plt.subplot(3, 1, 1)
    colors = ['blue', 'green', 'orange']
    labels = ['脉冲 1 (K=1.3)', '脉冲 2 (K=0.7)', '脉冲 3 (K=1.1)']
    
    # 由于时域重叠看不清细节，我们在图中错开展示它们的中心切片
    center_idx = radar.Npw // 2
    slice_len = 200 # 取中心附近200个点
    
    for i in range(3):
        # 取每个脉冲的一小段以看清频率疏密变化
        sig_slice = np.real(wave_data['St'][i, center_idx:center_idx+slice_len])
        plt.plot(sig_slice + i*2.5, label=labels[i], color=colors[i]) # 加偏移量以分开显示
        
    plt.title('1. 脉间波形捷变：前三个脉冲的时域细节 (观察不同斜率导致的疏密差异)')
    plt.ylabel('幅度 (附加偏移)')
    plt.yticks([]) # 隐藏 Y 轴刻度，因为加了偏移
    plt.legend(loc='upper right')
    plt.grid(True, alpha=0.3)

    # --- 2. 频域：前三个波形的频谱差异 ---
    plt.subplot(3, 1, 2)
    f_axis = fftshift(fftfreq(mradar['Npw'], Ts))
    for i in range(3):
        spec = fftshift(fft(wave_data['St'][i, :]))
        spec_dB = 20 * np.log10(np.abs(spec) + 1e-10)
        plt.plot(f_axis / 1e6, spec_dB, label=labels[i], color=colors[i], alpha=0.8)
        
    plt.title('2. 频域对比：不同调频斜率和加窗导致的不同带宽与频谱包络')
    plt.xlabel('频率 (MHz)')
    plt.ylabel('功率 (dB)')
    plt.xlim([-40, 40])
    plt.ylim([0, 80])
    plt.legend()
    plt.grid(True)

    # --- 3. 时频图：串联的发射脉冲序列 ---
    # 为了在时频图上看出明显的脉冲交替，我们将前 6 个脉冲串接起来
    # 为了绘图美观，脉冲间补充等长的静默期(零)
    plt.subplot(3, 1, 3)
    pulse_train = np.array([])
    zero_pad = np.zeros(mradar['Npw'])
    for i in range(mradar['PulseNum']):
        pulse_train = np.concatenate((pulse_train, wave_data['St'][i, :], zero_pad))
        
    # 计算 STFT
    nperseg = 128
    f_stft, t_stft, Zxx = signal.spectrogram(pulse_train, fs=fs, window='hann', 
                                         nperseg=nperseg, noverlap=nperseg-16,
                                         return_onesided=False)
    
    # 修复复数折叠的关键代码
    f_stft = fftshift(f_stft)
    Zxx = fftshift(Zxx, axes=0)
    Zxx_dB = 10 * np.log10(np.abs(Zxx) + 1e-10)
    
    plt.pcolormesh(t_stft * 1e6, f_stft / 1e6, Zxx_dB, shading='auto', cmap='jet')
    plt.colorbar(label='功率密度 (dB/Hz)')
    plt.title('3. 时频域分析 (Spectrogram)：脉冲间斜率跳变的全局宏观视角')
    plt.xlabel('时间 (us)')
    plt.ylabel('频率 (MHz)')
    # 基带信号，观察正负半轴
    plt.ylim([-30, 30]) 

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_wave_agile_test()