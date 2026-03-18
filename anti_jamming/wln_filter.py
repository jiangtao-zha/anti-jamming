import numpy as np
from scipy import signal

def WLN(radar_par, par1=0.6, par2=6):
    """
    宽-限-窄(WLN)抗干扰处理
    
    参数:
        radar_par: 字典类型，包含以下键:
            'Srt_temp': 回波信号矩阵 (num_pulses, num_samples)，支持复数
            'St1': 模板信号向量 (1D array)
            'f0': 载频 (Hz)
            'Bw': 信号带宽 (Hz)
        par1: 限幅因子 (默认0.6)
        par2: 滤波器阶数 (默认6)
        
    返回:
        J_wln: 处理后的回波矩阵
        St_wln: 处理后的模板向量
    """
    # 提取参数
    Srt = np.atleast_2d(radar_par['Srt_temp']) # 确保是二维数组
    St = np.asarray(radar_par['St1'])
    f0 = radar_par['f0']
    B = radar_par['Bw']
    
    wid_factor = 2.0
    nar_factor = 1.0
    order_wide = int(par2)
    order_narrow = int(par2)
    
    # 计算采样率与奈奎斯特频率
    Fs = radar_par.get('Fs', 2 * (B + f0))
    Nyq = Fs / 2.0
    
    # --- (1) 宽带带通滤波器设计 ---
    Bwid = wid_factor * B
    f_lo_w = max(1.0, f0 - Bwid / 2.0)
    f_hi_w = min(Nyq - 1.0, f0 + Bwid / 2.0)
    
    # SciPy 的 butter 默认接受归一化频率 (0 到 1 对应 0 到 Nyquist)
    b_bw, a_bw = signal.butter(order_wide, [f_lo_w / Nyq, f_hi_w / Nyq], btype='bandpass')
    
    # 对模板应用宽带滤波 (零相位滤波)
    St_w = signal.filtfilt(b_bw, a_bw, St)
    
    # 计算限幅阈值（基于模板的中位数绝对偏差估算）
    Vs_est = np.median(np.abs(St_w)) / 0.6745
    VL = par1 * 1.48
    
    # --- (2) 窄带带通滤波器设计 ---
    Bnar = nar_factor * B
    f_lo_n = max(1.0, f0 - Bnar / 2.0)
    f_hi_n = min(Nyq - 1.0, f0 + Bnar / 2.0)
    b_bn, a_bn = signal.butter(order_narrow, [f_lo_n / Nyq, f_hi_n / Nyq], btype='bandpass')
    
    # --- (3) 初始化输出矩阵 ---
    num_pulses, num_samples = Srt.shape
    J_wln = np.zeros_like(Srt)
    eps = np.finfo(float).eps # 机器精度，防止除零
    
    # 对每个脉冲进行处理
    for i in range(num_pulses):
        J = Srt[i, :]
        
        # a. 宽带带通
        J_w = signal.filtfilt(b_bw, a_bw, J)
        
        # b. 限幅 (np.minimum 相当于 MATLAB 的 min(1, 数组))
        gain = np.minimum(1.0, VL / (np.abs(J_w) + eps))
        J_lim = J_w * gain
        
        # c. 窄带带通
        J_wln[i, :] = signal.filtfilt(b_bn, a_bn, J_lim)
        
    # 对模板应用窄带滤波
    St_wln = signal.filtfilt(b_bn, a_bn, St_w)
    
    return J_wln, St_wln

import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, fftshift, fftfreq

# 确保中文字体正常显示
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 导入刚才写的函数 (如果你把上面代码保存在 wln_filter.py 里，可以使用 import)
# from wln_filter import WLN 

def generate_test_signal():
    """生成测试用的 LFM 信号和受干扰信号"""
    f0 = 10e6    # 载频 10 MHz
    Bw = 5e6     # 带宽 5 MHz
    T = 10e-6    # 脉宽 10 us
    
    Fs = 2 * (f0 + Bw) # 采样率 30 MHz
    t = np.arange(0, T, 1/Fs)
    
    # 1. 生成纯净的 LFM 模板信号 (复信号)
    K = Bw / T
    St = np.exp(1j * 2 * np.pi * (f0 * t + 0.5 * K * t**2))
    
    # 2. 生成受干扰的回波信号 (添加强脉冲干扰和底噪)
    Srt_temp = np.copy(St)
    # 模拟底噪
    Srt_temp += 0.1 * (np.random.randn(len(t)) + 1j * np.random.randn(len(t)))
    # 模拟强突发脉冲干扰 (幅度是真实信号的 10 倍)
    jam_indices = [int(len(t)*0.2), int(len(t)*0.5), int(len(t)*0.8)]
    for idx in jam_indices:
        Srt_temp[idx:idx+5] += 10.0 * np.exp(1j * np.random.rand()) 
        
    # 打包成 radar_par 字典
    radar_par = {
        'Srt_temp': Srt_temp.reshape(1, -1), # 变形为 (1, N) 的单脉冲矩阵
        'St1': St,
        'f0': f0,
        'Bw': Bw
    }
    return radar_par, Fs, t

def run_test():
    # 获取测试数据
    radar_par, Fs, t = generate_test_signal()
    
    # 运行 WLN 算法 (设置限幅因子 par1=1.5, 滤波阶数 par2=6)
    J_wln, St_wln = WLN(radar_par, par1=1.5, par2=6)
    
    # 提取处理前后的第一个脉冲
    original_signal = radar_par['Srt_temp'][0]
    processed_signal = J_wln[0]
    
    # ================= 绘图对比 =================
    plt.figure(figsize=(12, 8))
    
    # 1. 时域幅度对比
    plt.subplot(2, 1, 1)
    plt.plot(t * 1e6, np.abs(original_signal), label='处理前 (含强脉冲干扰)', alpha=0.7)
    plt.plot(t * 1e6, np.abs(processed_signal), label='WLN 处理后', linewidth=2)
    plt.title('时域幅度对比 (展示限幅效果)')
    plt.xlabel('时间 (us)')
    plt.ylabel('幅度')
    plt.legend()
    plt.grid(True)
    
    # 2. 频域频谱对比
    plt.subplot(2, 1, 2)
    f_axis = fftshift(fftfreq(len(t), 1/Fs))
    spec_orig = 20 * np.log10(np.abs(fftshift(fft(original_signal))) + 1e-10)
    spec_proc = 20 * np.log10(np.abs(fftshift(fft(processed_signal))) + 1e-10)
    
    plt.plot(f_axis / 1e6, spec_orig, label='处理前', alpha=0.7)
    plt.plot(f_axis / 1e6, spec_proc, label='WLN 处理后', linewidth=2)
    plt.title('频域特性对比 (展示带通滤波效果)')
    plt.xlabel('频率 (MHz)')
    plt.ylabel('功率 (dB)')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_test()