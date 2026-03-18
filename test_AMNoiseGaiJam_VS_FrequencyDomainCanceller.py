import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from jamming.AMNoiseGaiJam import AMNoiseGaiJam
from anti_jamming.FrequencyDomainCanceller import FrequencyDomainCanceller

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

def matched_filter(rx_signal, tx_replica):
    """
    脉冲压缩 (匹配滤波) 函数
    tx_replica: 理想的发射信号副本 (未加干扰和延迟)
    """
    # 匹配滤波器的冲激响应是发射信号的时间反转共轭
    h = np.conj(tx_replica[::-1])
    # 线性卷积
    pc_out = signal.convolve(rx_signal, h, mode='same')
    return pc_out

def run_verification():
    # 1. 参数设置
    R_target = 6000  # 设定目标距离 6km
    JSR = 15         # 干信比 15dB (较强干扰)
    
    # 2. 实例化干扰机并生成信号
    print("正在生成雷达回波与 AM 噪声干扰...")
    jammer = AMNoiseGaiJam()
    J_AM, X_t, jam_info = jammer.generate(R_target, JSR_dB=JSR, noise_var=0.1)
    Bj = jam_info['bandwidth']
    St = jam_info['target_signal']
    noise = jam_info['noise_signal']
    
    # 获取理想的发射副本（通过提取 St 中非零的有效脉冲部分）
    # 为了简化匹配滤波，我们直接用带有正确延迟的 St 作为参考，观察自相关峰值
    tx_replica = St 

    # 3. 实例化频域对消器并执行抗干扰
    print("正在执行频域对消算法...")
    Srt_matrix = np.array([J_AM])  # 转换为单脉冲矩阵格式
    # 注意：在强干扰下，设 use_fitted_freq=False 强制使用先验载频，对消成功率更高
    # canceller = FrequencyDomainCanceller(use_fitted_freq=False, f0=2*np.pi*jammer.f0)
    canceller = FrequencyDomainCanceller(use_fitted_freq=False, f0=2*np.pi*jammer.f0)
    cancelled_matrix = canceller.cancel(Srt_matrix, jammer.Fs)
    cancelled_sig = cancelled_matrix[0]

    # 4. 执行脉冲压缩 (核心验证环节)
    print("正在执行脉冲压缩...")
    # 对干净信号(理想情况)、受干扰信号、抗干扰后信号分别做匹配滤波
    pc_clean = matched_filter(St, tx_replica)
    pc_jammed = matched_filter(J_AM, tx_replica)
    pc_cancelled = matched_filter(cancelled_sig, tx_replica)

    # 5. 绘图对比结果
    plt.figure(figsize=(15, 10))

    # --- 时域幅度对比 (直观感受) ---
    plt.subplot(2, 2, 1)
    plt.plot(X_t, np.abs(St), label='干净目标', alpha=0.7)
    plt.plot(X_t, np.abs(J_AM), label='受干扰回波', alpha=0.5)
    plt.plot(X_t, np.abs(cancelled_sig), label='对消后回波', linewidth=1.5)
    plt.xlabel('距离 (m)')
    plt.ylabel('时域幅度')
    plt.title('接收信号时域对比')
    plt.legend()
    plt.grid(True)

    # --- 频谱对比 ---
    plt.subplot(2, 2, 2)
    f_axis = np.fft.fftshift(np.fft.fftfreq(len(J_AM), d=jammer.Ts))
    spec_jam = np.fft.fftshift(np.fft.fft(J_AM))
    spec_canc = np.fft.fftshift(np.fft.fft(cancelled_sig))
    plt.plot(f_axis/1e6, 20*np.log10(np.abs(spec_jam) + 1e-12), label='对消前')
    plt.plot(f_axis/1e6, 20*np.log10(np.abs(spec_canc) + 1e-12), label='对消后')
    plt.xlabel('频率 (MHz)')
    plt.ylabel('功率 (dB)')
    plt.title('接收信号频谱对比')
    plt.xlim([0, 100])
    plt.legend()
    plt.grid(True)

    # --- 脉冲压缩结果对比 (决定性证据) ---
    plt.subplot(2, 1, 2)
    # 归一化处理方便对比
    norm_factor = np.max(np.abs(pc_clean))
    plt.plot(X_t, 20*np.log10(np.abs(pc_clean)/norm_factor + 1e-10), label='理想无干扰脉压', linestyle='--')
    plt.plot(X_t, 20*np.log10(np.abs(pc_jammed)/norm_factor + 1e-10), label='受干扰脉压 (目标淹没)')
    plt.plot(X_t, 20*np.log10(np.abs(pc_cancelled)/norm_factor + 1e-10), label='对消后脉压 (目标凸显)', color='red')
    
    plt.xlabel('距离 (m)')
    plt.ylabel('归一化幅度 (dB)')
    plt.title('脉冲压缩 (匹配滤波) 结果对比 - 验证是否成功抗干扰')
    # 限制 y 轴范围，更清晰地看底噪和峰值
    plt.ylim([-60, 5])
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_verification()