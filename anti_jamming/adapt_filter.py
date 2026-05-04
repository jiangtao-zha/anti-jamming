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
    
    # 处理维度不匹配: 若 St1 长度 < Srt_temp 长度，在脉冲起始位置对齐后补零
    N_r = r.shape[1]
    N_s = s.shape[1]
    if N_s != N_r:
        s_padded = np.zeros((s.shape[0], N_r), dtype=complex)
        # 将 St1 放在与发射脉冲对应的起始位置
        offset = 0  # 适配器层负责设置正确的偏移
        if 'target_idx' in radar_par:
            offset = max(0, int(radar_par['target_idx']) - N_s // 2)
        end = min(offset + N_s, N_r)
        s_padded[0, offset:end] = s[0, :end - offset]
        s = s_padded
    
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

def test_adapt_filter(seed=None):
    """
    测试自适应滤波器（adapt_filter）抗干扰算法。
    使用项目标准干扰生成器加载 NoiseConvolutionJamming、NoiseProductJamming。

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
    from anti_jamming.adapters import get_antijam_func
    from scipy import signal

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    antijam_type = 'adapt_filter'
    jammer_types = ['NoiseConvolutionJamming', 'NoiseProductJamming']

    results = {}
    for jt in jammer_types:
        jammer = JammerLoader.load(jt)
        env = RadarEnvironment(radar_params)
        radar_par = env.generate_with_jammer(jammer)

        St_base = radar_par['St_base']
        Srt_orig = radar_par['Srt_matrix'][0]

        # 处理前：匹配滤波
        pc_before = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')

        # 应用自适应滤波抗干扰（使用默认参数）
        antijam_func = get_antijam_func(antijam_type)
        processed_signal, processed_template = antijam_func(radar_par)

        # 处理后：匹配滤波
        Srt_after = processed_signal[0] if processed_signal.ndim == 2 else processed_signal
        pc_after = signal.fftconvolve(Srt_after, np.conj(processed_template[::-1]), mode='same')

        # CA-CFAR 评估
        evaluator = UnifiedEvaluator()
        target_idx = radar_par['target_idx']
        info_before = evaluator.evaluate(np.abs(pc_before), target_idx)
        info_after = evaluator.evaluate(np.abs(pc_after), target_idx)

        results[jt] = {
            'before': info_before,
            'after': info_after,
            'sinr_improvement': info_after['sinr_db'] - info_before['sinr_db']
        }

        print(f"\n{'='*55}")
        print(f"  测试: {antijam_type} vs {jt}")
        print(f"  处理前: 检测={info_before['is_detected']}, SINR={info_before['sinr_db']:.2f} dB")
        print(f"  处理后: 检测={info_after['is_detected']}, SINR={info_after['sinr_db']:.2f} dB")
        print(f"  SINR改善: {info_after['sinr_db'] - info_before['sinr_db']:.2f} dB")
        print(f"{'='*55}")

    return results


def run_visual_test():
    """
    自适应滤波器（adapt_filter）的可视化测试。
    分别展示 NoiseConvolutionJamming 和 NoiseProductJamming 两种干扰下的处理效果。
    """
    import sys, os
    import matplotlib.pyplot as plt
    from scipy import signal
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    from unified_framework import RadarEnvironment, JammerLoader
    from anti_jamming.adapters import get_antijam_func

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    jammer_types = ['NoiseConvolutionJamming', 'NoiseProductJamming']

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes_flat = axes.flatten()

    for col, jt in enumerate(jammer_types):
        np.random.seed(42)
        jammer = JammerLoader.load(jt)
        env = RadarEnvironment(radar_params)
        radar_par = env.generate_with_jammer(jammer)

        St_base = radar_par['St_base']
        Srt_orig = radar_par['Srt_matrix'][0]
        Fs = radar_params['Fs']

        pc_before = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')

        antijam_func = get_antijam_func('adapt_filter')
        processed_signal, processed_template = antijam_func(radar_par)
        Srt_after = processed_signal[0] if processed_signal.ndim == 2 else processed_signal
        pc_after = signal.fftconvolve(Srt_after, np.conj(processed_template[::-1]), mode='same')

        # (col*3+0) 时域对比
        t = np.arange(len(Srt_orig)) / Fs
        t2 = np.arange(len(Srt_after)) / Fs
        axes_flat[col * 3].plot(t * 1e6, np.abs(Srt_orig), label='处理前', alpha=0.7)
        axes_flat[col * 3].plot(t2 * 1e6, np.abs(Srt_after), label='自适应滤波后', alpha=0.7)
        axes_flat[col * 3].set_xlabel('时间 (μs)')
        axes_flat[col * 3].set_ylabel('幅度')
        axes_flat[col * 3].set_title(f'({chr(97 + col * 3)}) 时域对比 — {jt}')
        axes_flat[col * 3].legend()
        axes_flat[col * 3].grid(True)

        # (col*3+1) 频域对比
        freq = np.fft.fftfreq(len(Srt_orig), 1 / Fs)
        freq_shift = np.fft.fftshift(freq)
        spec_before = np.fft.fftshift(np.abs(np.fft.fft(Srt_orig)))
        spec_after = np.fft.fftshift(np.abs(np.fft.fft(Srt_after)))
        axes_flat[col * 3 + 1].plot(freq_shift / 1e6, 20 * np.log10(spec_before + 1e-10),
                                    label='处理前', alpha=0.7)
        axes_flat[col * 3 + 1].plot(freq_shift / 1e6, 20 * np.log10(spec_after + 1e-10),
                                    label='自适应滤波后', alpha=0.7)
        axes_flat[col * 3 + 1].set_xlabel('频率 (MHz)')
        axes_flat[col * 3 + 1].set_ylabel('幅度 (dB)')
        axes_flat[col * 3 + 1].set_title(f'({chr(97 + col * 3 + 1)}) 频域频谱 — {jt}')
        axes_flat[col * 3 + 1].legend()
        axes_flat[col * 3 + 1].grid(True)

        # (col*3+2) 脉压距离像
        range_axis = np.arange(len(pc_before)) * 3e8 / (2 * Fs)
        axes_flat[col * 3 + 2].plot(range_axis, 20 * np.log10(np.abs(pc_before) + 1e-10),
                                    label='处理前', alpha=0.7)
        axes_flat[col * 3 + 2].plot(range_axis, 20 * np.log10(np.abs(pc_after) + 1e-10),
                                    label='自适应滤波后', alpha=0.7)
        axes_flat[col * 3 + 2].set_xlabel('距离 (m)')
        axes_flat[col * 3 + 2].set_ylabel('幅度 (dB)')
        axes_flat[col * 3 + 2].set_title(f'({chr(97 + col * 3 + 2)}) 脉压距离像 — {jt}')
        axes_flat[col * 3 + 2].legend()
        axes_flat[col * 3 + 2].grid(True)

    plt.tight_layout()
    plt.suptitle('自适应滤波器（信号子空间投影）抗干扰效果', fontsize=14, y=1.02)
    plt.show()


if __name__ == "__main__":
    run_visual_test()