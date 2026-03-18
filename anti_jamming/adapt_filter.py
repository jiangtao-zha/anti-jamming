import numpy as np

def adapt_filter(radar_par, par1=0.0, par2=None):
    """
    自相关/自适应滤波干扰抑制函数 (基于信号子空间投影)
    
    参数:
        radar_par: 字典，包含:
            'St1': 发射信号参考模板 (1D 或 2D array)
            'Srt_temp': 接收到的回波信号矩阵 (PulseNum x Nsamples)
        par1: 正则化因子，添加到分母中以稳定逆运算或控制滤波强度 (默认 0.0)
        par2: 备用参数
        
    返回:
        y: 滤波之后的输出信号矩阵
    """
    # 确保信号是二维数组，方便进行矩阵转置和乘法 (1 x N)
    s = np.atleast_2d(radar_par['St1'])
    r = np.atleast_2d(radar_par['Srt_temp'])
    
    # ---------------------------------------------------------
    # 方法一：严格按照 MATLAB 公式构建投影矩阵 Ps (原代码逻辑)
    # 适用条件：采样点数 N 较小。如果 N 很大(例如10000)，会生成 10000x10000 的复数矩阵，消耗大量内存
    # ---------------------------------------------------------
    sH = s.conj().T  # 共轭转置 (N x 1)
    
    # 计算标量分母：s * s^H (结果是一个 1x1 的矩阵，取其标量值)
    s_inner = (s @ sH)[0, 0] 
    
    # 引入正则化因子 par1
    inv_term = 1.0 / (s_inner + par1)
    
    # 构建投影算子 Ps = s^H * inv_term * s  (维度: N x N)
    Ps = sH @ (inv_term * s)
    
    # 应用滤波：y = r * Ps (维度: M x N)
    y = r @ Ps
    
    # ---------------------------------------------------------
    # 方法二：数学等效的内存优化实现 (推荐在大型仿真中使用)
    # 结合结合律：y = r * (s^H * inv_term * s) = (r * s^H) * inv_term * s
    # 这样避免了生成 N x N 的 Ps 矩阵，全过程只有向量运算
    # ---------------------------------------------------------
    # weight = (r @ sH) * inv_term  # (M x 1) 的列向量，代表每个脉冲在 s 上的投影系数
    # y_opt = weight @ s            # (M x N) 的输出矩阵
    
    return y

import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fft, fftshift, fftfreq
from scipy import signal

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 如果你将上面的函数保存在 adapt_filter.py 中，请取消注释下一行
# from adapt_filter import adapt_filter

def generate_noise_fm_jamming(t, fc, B_jam):
    """生成简单的噪声调频干扰"""
    noise = np.random.randn(len(t))
    # 积分生成相位路径
    phase_noise = 2 * np.pi * B_jam * np.cumsum(noise) * (t[1]-t[0])
    return np.exp(1j * (2 * np.pi * fc * t + phase_noise))

def run_test():
    # 1. 物理参数设置
    f0 = 15e6
    Bw = 10e6
    Pw = 10e-6
    Fs = 50e6
    Ts = 1 / Fs
    
    Npw = int(Pw / Ts)
    t = np.linspace(0, Pw, Npw, endpoint=False)
    
    # 2. 生成 LFM 模板 (参考信号)
    K = Bw / Pw
    St = np.exp(1j * 2 * np.pi * (f0 * t + 0.5 * K * t**2))
    
    # 3. 生成极强的噪声调频干扰 (JSR ≈ 20dB)
    J_amplitude = 10.0
    B_jam = 15e6 # 干扰带宽
    Jamming = J_amplitude * generate_noise_fm_jamming(t, f0, B_jam)
    
    # 加入高斯白噪声
    Noise = 0.5 * (np.random.randn(Npw) + 1j * np.random.randn(Npw))
    
    # 构造受干扰的接收信号
    Srt = St + Jamming + Noise
    
    # 封装参数
    radar_par = {
        'St1': St,
        'Srt_temp': Srt
    }
    
    # 4. 执行自适应投影滤波
    # 这里我们设置正则化参数 par1 = 0.1
    print("正在执行自适应/自相关滤波...")
    y_filtered = adapt_filter(radar_par, par1=0.1)
    
    # 提取单脉冲 (降维以便绘图)
    Srt_1d = Srt
    y_filtered_1d = y_filtered[0]
    
    # 5. 执行脉冲压缩对比 (匹配滤波)
    def matched_filter(sig, ref):
        h = np.conj(ref[::-1])
        return signal.convolve(sig, h, mode='same')
        
    pc_clean = matched_filter(St, St)
    pc_jammed = matched_filter(Srt_1d, St)
    pc_filtered = matched_filter(y_filtered_1d, St)
    
    # ================= 绘图展示 =================
    plt.figure(figsize=(15, 10))
    
    # --- 1. 时域信号对比 ---
    plt.subplot(3, 1, 1)
    plt.plot(t * 1e6, np.real(Srt_1d), label='受干扰接收信号 (实部)', color='gray', alpha=0.6)
    plt.plot(t * 1e6, np.real(St), label='原始干净波形 (隐藏在干扰中)', linewidth=2)
    plt.plot(t * 1e6, np.real(y_filtered_1d), label='自适应滤波后恢复的波形', color='red', linestyle='--')
    plt.title('1. 时域幅度对比：自适应投影算子的提纯效果')
    plt.xlabel('时间 (us)')
    plt.ylabel('幅度')
    plt.legend()
    plt.grid(True)
    
    # --- 2. 频域频谱对比 ---
    plt.subplot(3, 1, 2)
    f_axis = fftshift(fftfreq(Npw, Ts))
    spec_jam = 20 * np.log10(np.abs(fftshift(fft(Srt_1d))) + 1e-10)
    spec_fil = 20 * np.log10(np.abs(fftshift(fft(y_filtered_1d))) + 1e-10)
    spec_clean = 20 * np.log10(np.abs(fftshift(fft(St))) + 1e-10)
    
    plt.plot(f_axis / 1e6, spec_jam, label='滤波前频谱 (强噪声调频)', color='gray')
    plt.plot(f_axis / 1e6, spec_fil, label='滤波后频谱', color='red')
    plt.plot(f_axis / 1e6, spec_clean, label='理想参考频谱', color='blue', linestyle=':')
    plt.title('2. 频域对比：干扰能量的剥离')
    plt.xlabel('频率 (MHz)')
    plt.ylabel('功率 (dB)')
    plt.legend()
    plt.grid(True)
    
    # --- 3. 脉冲压缩结果验证 ---
    plt.subplot(3, 1, 3)
    norm_factor = np.max(np.abs(pc_clean))
    
    plt.plot(t * 1e6, 20*np.log10(np.abs(pc_jammed)/norm_factor + 1e-10), label='受干扰信号直接脉压', color='gray')
    plt.plot(t * 1e6, 20*np.log10(np.abs(pc_filtered)/norm_factor + 1e-10), label='自适应滤波后脉压', color='red', linewidth=2)
    plt.plot(t * 1e6, 20*np.log10(np.abs(pc_clean)/norm_factor + 1e-10), label='理想无干扰脉压', color='blue', linestyle=':')
    
    plt.title('3. 脉冲压缩距离像：验证抗干扰是否成功')
    plt.xlabel('脉内时间 (us) -> 距离对应')
    plt.ylabel('归一化幅度 (dB)')
    plt.ylim([-40, 5])
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_test()