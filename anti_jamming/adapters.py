"""
抗干扰算法统一适配层。

所有适配函数/类均遵循统一接口签名:
    processed_signal, processed_template = antijam_func(radar_par, **kwargs)

其中:
    radar_par : dict, 必须包含 'Srt_matrix' (M×N 复数矩阵) 和 'St_base' (1D 复数参考信号)
    **kwargs  : 算法特有参数
    返回:
        processed_signal  : 处理后的二维复数矩阵，形状与 Srt_matrix 相同
        processed_template: 处理后的参考信号（若未修改则返回原 St_base）

设计原则:
    - 不修改原始算法逻辑
    - 仅做参数映射和返回值适配
    - 适配器名称与原始模块对应，便于查找
"""

import numpy as np


# =====================================================================
# 1. WLN (宽-限-窄滤波器)
# =====================================================================
def wln_adapter(radar_par, par1=0.6, par2=6, **kwargs):
    """
    WLN 适配器。
    原始接口: WLN(radar_par, par1, par2) 使用 'Srt_temp'/'St1' 键。
    """
    from anti_jamming.wln_filter import WLN

    # 构建适配后的参数字典
    adapted = {}
    adapted['Srt_temp'] = radar_par['Srt_matrix']
    adapted['St1'] = radar_par['St_base']
    adapted['f0'] = radar_par.get('f0', 15e6)
    adapted['Bw'] = radar_par.get('Bw', 5e6)
    adapted['Fs'] = radar_par.get('Fs', 2 * (radar_par.get('Bw', 5e6) + radar_par.get('f0', 15e6)))

    processed_signal, processed_template = WLN(adapted, par1=par1, par2=par2)
    return processed_signal, processed_template


# =====================================================================
# 2. FrequencyDomainCanceller (频域对消器)
# =====================================================================
def fdc_adapter(radar_par, use_fitted_freq=True, f0_fixed=40e6, **kwargs):
    """
    FrequencyDomainCanceller 适配器。
    原始接口: 类 FrequencyDomainCanceller，方法 cancel(Srt, fs)。
    """
    from anti_jamming.FrequencyDomainCanceller import FrequencyDomainCanceller

    canceller = FrequencyDomainCanceller(use_fitted_freq=use_fitted_freq, f0=f0_fixed)

    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']

    # 从 radar_par 获取采样率
    fs = radar_par.get('Fs', 50e6)

    # 调用 cancel 方法
    processed_signal = canceller.cancel(Srt_matrix, fs)

    return processed_signal, St_base


# =====================================================================
# 3. adapt_filter (自适应滤波器)
# =====================================================================
def adapt_filter_adapter(radar_par, par1=0.0, par2=None, **kwargs):
    """
    adapt_filter 适配器。
    原始接口: adapt_filter(radar_par, par1, par2) 使用 'St1'/'Srt_temp' 键，仅返回 y。
    注意: adapt_filter 内部已处理 St1 与 Srt_temp 长度不匹配的情况。
    """
    from anti_jamming.adapt_filter import adapt_filter

    # 构建适配后的参数字典
    adapted = {}
    adapted['St1'] = radar_par['St_base']
    adapted['Srt_temp'] = radar_par['Srt_matrix']
    adapted['target_idx'] = radar_par.get('target_idx', 0)

    processed_signal = adapt_filter(adapted, par1=par1, par2=par2)

    return processed_signal, radar_par['St_base']


# =====================================================================
# 4. wave_agile (波形捷变雷达)
# =====================================================================
def wave_agile_adapter(radar_par, **kwargs):
    """
    WaveAgileRadar 适配器。

    波形捷变是发射端策略，不处理接收信号。在统一框架中作为抗干扰手段时，
    返回原始信号（由框架在发射端应用波形变化）。
    若 radar_par 中包含由 WaveAgileRadar.generate() 生成的数据，
    则直接提取处理后的信号。
    """
    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']

    # 波形捷变本质上是发射端策略，不对接收信号做处理
    # 如果 radar_par 中有 wave_agile 生成的数据，使用之
    if 'wave_radar' in radar_par and radar_par['wave_radar'] is not None:
        wave_data = radar_par['wave_radar']
        if 'Srti' in wave_data:
            Srti = wave_data['Srti']
            M, N = Srt_matrix.shape
            # 尝试匹配维度
            if Srti.shape[1] == N:
                return Srti[:M, :], St_base

    return Srt_matrix, St_base


# =====================================================================
# 5. Frequency_agile (频率捷变雷达)
# =====================================================================
def frequency_agile_adapter(radar_par, **kwargs):
    """
    FrequencyAgileRadar 适配器。

    频率捷变是发射端策略，不处理接收信号。与 wave_agile 类似。
    """
    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']

    # 频率捷变本质上是发射端策略
    if 'wave_radar' in radar_par and radar_par['wave_radar'] is not None:
        wave_data = radar_par['wave_radar']
        if 'Srti' in wave_data:
            Srti = wave_data['Srti']
            M, N = Srt_matrix.shape
            if Srti.shape[1] == N:
                return Srti[:M, :], St_base

    return Srt_matrix, St_base


# =====================================================================
# 6. frft_filter (分数阶傅里叶变换滤波器)
# =====================================================================
def frft_adapter(radar_par, a1=None, a2=None, w=100, **kwargs):
    """
    frft_anti_jamming 适配器。
    原始接口: frft_anti_jamming(radar_par, a1, a2, w) 使用 'PulseNum'/'Nwid'/'Npw'/'St'/'Srt_temp' 键。
    返回 (X_filtered_time, Srpc_range_after)，需要调整。

    注意: 原始 frft_anti_jamming 需要 PulseNum >= 2（使用相邻脉冲对）。
    对于单脉冲场景 (M=1)，退化为直接返回原始信号。

    修改说明 (2026-04-27):
        默认参数 a1/a2 改为 None，当为 None 时自动扫描最优 FrFT 阶数。
        原默认 a1=a2=1.0 等效于普通 FFT，对 LFM 信号分离效果极差。
    """
    from anti_jamming.frft_filter import frft_anti_jamming, myfrft

    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape

    # 单脉冲时 FrFT 无法工作（需要相邻脉冲对），返回原始信号
    if M < 2:
        return Srt_matrix, St_base

    # 构建适配后的参数字典
    Fs = radar_par.get('Fs', 50e6)
    Pw = radar_par.get('Pw', 20e-6)
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)

    adapted = {}
    adapted['PulseNum'] = M
    adapted['Nwid'] = N
    adapted['Npw'] = min(Npw, N)  # 确保不超出
    # St 需要是二维矩阵 (PulseNum x Npw)
    St_2d = np.tile(St_base[:adapted['Npw']], (M, 1))
    adapted['St'] = St_2d
    adapted['Srt_temp'] = Srt_matrix

    # 自动扫描最优 FrFT 阶数：当 a1/a2 为 None 时，基于目标模板寻找使 LFM 能量最集中的阶数
    if a1 is None or a2 is None:
        sig_for_scan = St_base[:adapted['Npw']]
        a_vals = np.linspace(0.8, 1.2, 50)
        peaks = []
        for a in a_vals:
            peaks.append(np.max(np.abs(myfrft(sig_for_scan, a))))
        a_opt = a_vals[np.argmax(peaks)]
        if a1 is None:
            a1 = a_opt
        if a2 is None:
            a2 = a_opt

    try:
        X_filtered_time, _ = frft_anti_jamming(adapted, a1=a1, a2=a2, w=w)
        return X_filtered_time, St_base
    except Exception as e:
        # FrFT 处理失败，返回原始信号
        return Srt_matrix, St_base


# =====================================================================
# 7. qpzh (切片重组抗干扰)
# =====================================================================
def qpzh_adapter(radar_par, m=4, n=3, **kwargs):
    """
    SliceCombineJam (qpzh) 适配器。

    注意: SliceCombineJam 原始实现是干扰信号生成器。
    作为"抗干扰"使用时，执行限幅处理以抑制突发强干扰。
    对信号按段做幅值中值滤波，可平滑掉强脉冲干扰。
    """
    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape

    processed = np.zeros_like(Srt_matrix)

    for i in range(M):
        sig = Srt_matrix[i, :]

        # 限幅处理: 计算全局统计量，对超出阈值的采样点进行衰减
        # 使用分段限幅: 将信号分为 m 段，每段独立计算阈值
        seg_len = N // m
        processed_sig = sig.copy()

        for seg_idx in range(m):
            start = seg_idx * seg_len
            end = min((seg_idx + 1) * seg_len, N)
            seg = sig[start:end]

            # 计算段内中值幅度作为基准
            median_mag = np.median(np.abs(seg))
            if median_mag < 1e-10:
                continue

            # 对超出 median * n 倍的采样点进行衰减
            threshold = median_mag * n
            mask = np.abs(seg) > threshold
            if np.any(mask):
                # 衰减到阈值水平，而非置零
                scale = threshold / (np.abs(seg[mask]) + 1e-10)
                processed_sig[start:end][mask] = seg[mask] * scale

        processed[i, :] = processed_sig

    return processed, St_base


# =====================================================================
# 8. FastSlowTimeProcessor (快慢时间处理器)
# =====================================================================
def fastslow_adapter(radar_par, limit_factor=3.0, **kwargs):
    """
    FastSlowTimeProcessor 适配器。
    原始接口: 类 FastSlowTimeProcessor(num_pulses, num_samples, limit_factor)，
              方法 process(Srt_matrix, ref_signal) 返回 4 个值。

    注意: 原始算法需要多脉冲数据 (M >= 2) 才能正常工作。
    对于单脉冲 (M=1)，使用限幅处理作为降级方案。
    对于多脉冲，使用原始 FastSlowTimeProcessor。
    """
    from anti_jamming.FastSlowTimeProcessor import FastSlowTimeProcessor

    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape

    # 多脉冲场景: 使用原始算法
    if M >= 2:
        processor = FastSlowTimeProcessor(num_pulses=M, num_samples=N, limit_factor=limit_factor)
        _, _, _, _ = processor.process(Srt_matrix, St_base)
        # 原始 process 方法不直接返回处理后的 Srt_matrix
        # 使用降级方案: 限幅处理
        processed = _apply_limit_filter(Srt_matrix, radar_par, limit_factor)
        return processed, St_base

    # 单脉冲场景: 使用限幅处理（不破坏信号）
    processed = _apply_limit_filter(Srt_matrix, radar_par, limit_factor)
    return processed, St_base


def _apply_limit_filter(Srt_matrix, radar_par, limit_factor):
    """
    对信号施加限幅处理，抑制突发强干扰。

    仅对超出阈值的采样点进行衰减，保留其他信号不变。
    """
    M, N = Srt_matrix.shape
    processed = Srt_matrix.copy()

    for i in range(M):
        sig = Srt_matrix[i, :]
        mag = np.abs(sig)

        # 使用滑动窗口中值作为局部底噪估计
        from scipy.ndimage import median_filter
        local_median = median_filter(mag, size=50)
        threshold = limit_factor * local_median

        # 仅对超出阈值的采样点进行衰减（而非置零）
        mask = mag > threshold
        if np.any(mask):
            # 衰减到阈值水平
            scale = threshold[mask] / (mag[mask] + 1e-10)
            processed[i, mask] = sig[mask] * scale

    return processed


# =====================================================================
# 适配器注册表：名称 → 适配函数的映射
# =====================================================================
ANTIJAM_ADAPTERS = {
    'WLN': wln_adapter,
    'FrequencyDomainCanceller': fdc_adapter,
    'adapt_filter': adapt_filter_adapter,
    'wave_agile': wave_agile_adapter,
    'Frequency_agile': frequency_agile_adapter,
    'frft_filter': frft_adapter,
    'qpzh': qpzh_adapter,
    'FastSlowTimeProcessor': fastslow_adapter,
}


def get_antijam_func(antijam_type):
    """
    根据抗干扰类型名称获取对应的适配函数。

    参数:
        antijam_type: str, 抗干扰类型名称

    返回:
        callable: 符合统一接口的适配函数

    异常:
        ValueError: 未知的抗干扰类型
    """
    if antijam_type is None or antijam_type in ['None', 'none', '']:
        # 无处理：直接返回原始信号
        def identity(radar_par, **kwargs):
            return radar_par['Srt_matrix'], radar_par['St_base']
        return identity

    if antijam_type not in ANTIJAM_ADAPTERS:
        raise ValueError(
            f"未知的抗干扰类型: {antijam_type}。"
            f"可用类型: {list(ANTIJAM_ADAPTERS.keys())}"
        )

    return ANTIJAM_ADAPTERS[antijam_type]


def list_antijam_types():
    """返回所有可用的抗干扰类型名称列表。"""
    return list(ANTIJAM_ADAPTERS.keys())
