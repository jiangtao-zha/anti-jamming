import numpy as np
from scipy.fft import fft, ifft

def frft_anti_jamming(radar_par, a1, a2, w=100):
    """
    基于分数阶傅里叶变换(FrFT)的雷达回波抗干扰处理
    
    参数:
        radar_par : 字典，需包含 PulseNum, Nwid, Npw, St (模板), Srt_temp (受干扰回波)
        a1, a2    : 相邻脉冲的 FrFT 分数阶阶数
        w         : 分数阶域中用于提取目标的掩膜宽度 (默认100)
    
    返回:
        X_filtered_time  : 抗干扰后的时域回波矩阵
        Srpc_range_after : 抗干扰并脉压后的距离像 (一维数组)
    """
    PulseNum = radar_par['PulseNum']
    Nwid = radar_par['Nwid']
    Npw = radar_par['Npw']
    
    # 脉冲压缩准备 (匹配滤波器)
    Nfft = 2**int(np.ceil(np.log2(Nwid + Npw - 1)))
    Sw = fft(radar_par['St'][0, :], n=Nfft)
    
    # --- 1. 对所有脉冲进行 FrFT 变换 ---
    X_frft_a1 = np.zeros((PulseNum, Nwid), dtype=complex)
    X_frft_a2 = np.zeros((PulseNum, Nwid), dtype=complex)
    
    for n in range(PulseNum):
        X_frft_a1[n, :] = myfrft(radar_par['Srt_temp'][n, :], a1)
        X_frft_a2[n, :] = myfrft(radar_par['Srt_temp'][n, :], a2)
        
    # --- 2. 在 FrFT 域进行峰值掩膜滤波 (Masking) ---
    X_filtered_time = np.zeros((PulseNum, Nwid), dtype=complex)
    filter_count = np.zeros(PulseNum)
    
    for n in range(PulseNum - 1):
        Xa = X_frft_a1[n, :]
        Xb = X_frft_a2[n+1, :]
        
        # 寻找目标在 FrFT 域的能量聚集峰值
        u1_star = np.argmax(np.abs(Xa))
        u2_star = np.argmax(np.abs(Xb))
        
        mask1 = np.zeros(Nwid)
        mask2 = np.zeros(Nwid)
        
        # 构建矩形掩膜 (抠出目标，过滤干扰)
        i1 = max(0, u1_star - w // 2)
        j1 = min(Nwid, u1_star + w // 2 + 1)
        i2 = max(0, u2_star - w // 2)
        j2 = min(Nwid, u2_star + w // 2 + 1)
        
        mask1[i1:j1] = 1.0
        mask2[i2:j2] = 1.0
        
        Xa_f = Xa * mask1
        Xb_f = Xb * mask2
        
        # 逆 FrFT 变回时域
        x_n = myfrft(Xa_f, -a1)
        x_np1 = myfrft(Xb_f, -a2)
        
        X_filtered_time[n, :] += x_n
        filter_count[n] += 1
        X_filtered_time[n+1, :] += x_np1
        filter_count[n+1] += 1
        
    # 重叠区域平均化
    for n in range(PulseNum):
        if filter_count[n] > 0:
            X_filtered_time[n, :] /= filter_count[n]
            
    # --- 3. 抗干扰后的脉冲压缩 ---
    Srpc_after = np.zeros((PulseNum, Nwid), dtype=complex)
    for n in range(PulseNum):
        # 补零至 Nfft 长度进行快速卷积
        Srw = fft(np.pad(X_filtered_time[n, :], (0, Nfft - Nwid)), n=Nfft)
        Sot = ifft(Srw * np.conj(Sw), n=Nfft)
        Srpc_after[n, :] = Sot[:Nwid]
        
    # 多脉冲非相干积累
    Srpc_range_after = np.abs(np.sum(Srpc_after, axis=0))
    
    return X_filtered_time, Srpc_range_after

# =====================================================================
# 以下为经典的 Ozaktas FrFT 算法的 Python 等效实现
# =====================================================================
def myfrft(f, a):
    f = np.asarray(f, dtype=complex).flatten()
    N = len(f)
    shft = (np.arange(N) + int(np.fix(N / 2))) % N
    sN = np.sqrt(N)
    a = a % 4
    
    # 基础边界条件
    if a == 0: return f
    if a == 2: return np.flipud(f)
    if a == 1:
        Faf = np.zeros(N, dtype=complex)
        Faf[shft] = fft(f[shft]) / sN
        return Faf
    if a == 3:
        Faf = np.zeros(N, dtype=complex)
        Faf[shft] = ifft(f[shft]) * sN
        return Faf
        
    # 角度规约
    if a > 2.0:
        a = a - 2
        f = np.flipud(f)
    if a > 1.5:
        a = a - 1
        f_temp = np.zeros(N, dtype=complex)
        f_temp[shft] = fft(f[shft]) / sN
        f = f_temp
    if a < 0.5:
        a = a + 1
        f_temp = np.zeros(N, dtype=complex)
        f_temp[shft] = ifft(f[shft]) * sN
        f = f_temp

    alpha = a * np.pi / 2
    tana2 = np.tan(alpha / 2)
    sina = np.sin(alpha)
    
    # 插值函数与快速卷积
    def fconv(x, y):
        N_conv = len(x) + len(y) - 1
        P = 2**int(np.ceil(np.log2(N_conv)))
        z = ifft(fft(x, n=P) * fft(y, n=P))
        return z[:N_conv]

    def interp(x):
        Nx = len(x)
        y = np.zeros(2 * Nx - 1, dtype=x.dtype)
        y[0::2] = x
        idx = np.arange(-(2*Nx - 3), 2*Nx - 2) / 2.0
        xint = fconv(y, np.sinc(idx)) # np.sinc 内置了 pi
        return xint[2*Nx - 3 : 4*Nx - 4]

    # 插值与补零
    f = np.concatenate((np.zeros(N - 1), interp(f), np.zeros(N - 1)))
    
    # 乘积 Chirp
    idx1 = np.arange(-2*N + 2, 2*N - 1)
    chrp = np.exp(-1j * np.pi / N * tana2 / 4 * (idx1**2))
    f = chrp * f
    
    # 卷积 Chirp
    c = np.pi / N / sina / 4
    idx2 = np.arange(-(4*N - 4), 4*N - 3)
    Faf = fconv(np.exp(1j * c * (idx2**2)), f)
    
    # 截取有效区间并反求 Chirp
    Faf = Faf[4*N - 4 : 8*N - 7] * np.sqrt(c / np.pi)
    Faf = chrp * Faf
    
    # 抽取与相位补偿
    Faf = np.exp(-1j * (1 - a) * np.pi / 4) * Faf[N - 1 : 3*N - 2 : 2]
    
    return Faf

import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import fftshift, fftfreq
from scipy import signal
# 从刚才保存的文件中导入函数
from frft_filter import frft_anti_jamming, myfrft

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

def generate_lfm_and_jamming():
    # 1. 物理参数设置
    f0 = 10e6
    Bw = 5e6
    Pw = 10e-6
    Fs = 40e6
    Ts = 1 / Fs
    
    # 设置接收窗与目标
    Nwid = int(50e-6 / Ts)
    Npw = int(Pw / Ts)
    PulseNum = 2
    
    t_tx = np.linspace(0, Pw, Npw, endpoint=False)
    t_rx = np.linspace(0, 50e-6, Nwid, endpoint=False)
    
    # 2. 生成 LFM 模板
    K = Bw / Pw
    St_base = np.exp(1j * 2 * np.pi * (f0 * t_tx + 0.5 * K * t_tx**2))
    St = np.tile(St_base, (PulseNum, 1))
    
    # 3. 生成包含延时的真实回波
    target_delay = 20e-6
    delay_idx = int(target_delay / Ts)
    S_clean = np.zeros((PulseNum, Nwid), dtype=complex)
    for i in range(PulseNum):
        S_clean[i, delay_idx:delay_idx+Npw] = St_base
        
    # 4. 生成强压制式单频/噪声干扰 (JSR = 20dB)
    Jamming = np.zeros((PulseNum, Nwid), dtype=complex)
    for i in range(PulseNum):
        # 叠加一个极强的扫频干扰或单频干扰
        J_cw = 10 * np.exp(1j * 2 * np.pi * (f0 + 1e6) * t_rx)
        J_noise = 2 * (np.random.randn(Nwid) + 1j * np.random.randn(Nwid))
        Jamming[i, :] = J_cw + J_noise
        
    Srt_temp = S_clean + Jamming
    
    radar_par = {
        'PulseNum': PulseNum,
        'Nwid': Nwid,
        'Npw': Npw,
        'St': St,
        'Srt_temp': Srt_temp,
        'S_clean': S_clean # 仅作对比用
    }
    return radar_par, Fs, t_rx

def find_optimal_frft_order(sig):
    """自动扫描寻找使得 LFM 能量最集中的最优 FrFT 阶数"""
    a_vals = np.linspace(0.8, 1.2, 50)
    peaks = []
    for a in a_vals:
        peaks.append(np.max(np.abs(myfrft(sig, a))))
    return a_vals[np.argmax(peaks)]

def run_test():
    radar_par, Fs, t_rx = generate_lfm_and_jamming()
    
    # 获取第一脉冲，提取干净回波以寻找最佳 FrFT 阶数
    clean_sig = radar_par['S_clean'][0, :]
    jammed_sig = radar_par['Srt_temp'][0, :]
    
    print("正在扫描最优分数阶阶数...")
    a_opt = find_optimal_frft_order(clean_sig)
    print(f"找到最优阶数 a_opt = {a_opt:.4f}")
    
    print("正在执行 FrFT 掩膜抗干扰...")
    # 设置掩膜宽度 w=50 (根据目标峰值的锐度微调)
    X_filtered, Srpc_after = frft_anti_jamming(radar_par, a_opt, a_opt, w=50)
    
    # 提取第一脉冲的处理结果作图
    filtered_sig = X_filtered[0, :]
    
    # ================= 绘图展示 =================
    plt.figure(figsize=(16, 12))
    
    # 1. 时域对比 (淹没与重现)
    plt.subplot(3, 2, 1)
    plt.plot(t_rx * 1e6, np.real(jammed_sig), label='受干扰波形 (实部)', alpha=0.6)
    plt.plot(t_rx * 1e6, np.real(clean_sig), label='理想无干扰目标', linewidth=2)
    plt.title('1. 时域：目标完全被干扰淹没')
    plt.xlabel('时间 (us)')
    plt.ylabel('幅度')
    plt.legend()
    
    plt.subplot(3, 2, 2)
    plt.plot(t_rx * 1e6, np.real(clean_sig), label='理想无干扰目标', alpha=0.6)
    plt.plot(t_rx * 1e6, np.real(filtered_sig), label='FrFT抗干扰后恢复波形', color='red')
    plt.title('2. 时域：掩膜提取后重构的目标信号')
    plt.xlabel('时间 (us)')
    plt.legend()

    # 2. 分数阶傅里叶域对比 (核心逻辑展示)
    plt.subplot(3, 1, 2)
    # 将包含干扰的信号变到 a_opt 域
    F_jammed = myfrft(jammed_sig, a_opt)
    F_clean = myfrft(clean_sig, a_opt)
    
    plt.plot(np.abs(F_jammed), label='含干扰信号在 a_opt 域', color='gray', alpha=0.8)
    plt.plot(np.abs(F_clean), label='干净目标在 a_opt 域 (呈现极致峰值)', color='blue', linewidth=1.5)
    
    # 绘制掩膜范围
    u_star = np.argmax(np.abs(F_jammed))
    w = 50
    plt.axvspan(u_star - w//2, u_star + w//2, color='red', alpha=0.2, label='算法提取 Mask 区域')
    
    plt.title(f'3. 分数阶傅里叶域 (a={a_opt:.4f})：目标聚集成峰，干扰被铺平')
    plt.xlabel('FrFT 采样点索引')
    plt.ylabel('幅度')
    plt.legend()
    
    # 3. 脉冲压缩结果 (最终目的)
    plt.subplot(3, 1, 3)
    # 计算未抗干扰的脉冲压缩
    Nfft = 2**int(np.ceil(np.log2(radar_par['Nwid'] + radar_par['Npw'] - 1)))
    Sw = fft(radar_par['St'][0, :], n=Nfft)
    Srw_jammed = fft(np.pad(jammed_sig, (0, Nfft - radar_par['Nwid'])), n=Nfft)
    Srpc_jammed = ifft(Srw_jammed * np.conj(Sw), n=Nfft)[:radar_par['Nwid']]
    
    plt.plot(t_rx * 1e6, 20*np.log10(np.abs(Srpc_jammed) + 1e-10), label='受干扰直接脉压 (目标丢失)', color='gray')
    plt.plot(t_rx * 1e6, 20*np.log10(Srpc_after/2 + 1e-10), label='FrFT抗干扰后脉压 (峰值凸显)', color='red', linewidth=2)
    
    plt.title('4. 脉冲压缩距离像：抗干扰效能验证')
    plt.xlabel('延迟时间 (us) -> 对应距离')
    plt.ylabel('归一化幅度 (dB)')
    plt.ylim([-20, 100])
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_test()