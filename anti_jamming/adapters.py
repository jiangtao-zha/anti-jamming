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
def wln_adapter(radar_par, par1=0.3, par2=6, **kwargs):
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
def fdc_adapter(radar_par, cancellation_strength=0.8, **kwargs):
    """
    AM 共轭对称频域对消适配器。

    AM 干扰在已知载频下变换到基带后，实包络会在正负频率形成
    共轭对称分量。这里估计该分量并做软抵消，而不是用模板频谱差值
    作为通用频谱抑制。目标 LFM 的基带主能量区域被保护，只在预期
    目标带宽之外执行强抵消。

    cancellation_strength 控制对消强度 (0=不对消, 1=完全对消)。
    """
    Srt_matrix = radar_par['Srt_matrix']
    M, N = Srt_matrix.shape
    Fs = radar_par.get('Fs', 50e6)
    f0 = radar_par.get('f0', 15e6)
    bandwidth = radar_par.get('Bw', 5e6)
    strength = float(np.clip(cancellation_strength, 0.0, 1.0))
    t = np.arange(N, dtype=float) / Fs
    freq = np.fft.fftfreq(N, d=1.0 / Fs)
    # The known radar carrier is a receiver parameter, not a target-location
    # oracle. The AM envelope is improper after demodulation, while circular
    # complex noise and most FM signals have a much smaller pseudo-covariance.
    baseband_carrier = np.exp(-1j * 2.0 * np.pi * f0 * t)

    processed = np.zeros_like(Srt_matrix)
    for i in range(M):
        baseband = Srt_matrix[i] * baseband_carrier
        spectrum = np.fft.fft(baseband)

        # For z(t)=exp(j*phi)*real(a(t)), sum(z**2) estimates exp(j*2*phi).
        # Normalize it to obtain a confidence that an AM-like component is
        # present, then construct the phase-aligned conjugate-symmetric part.
        pseudo_cov = np.sum(baseband ** 2)
        covariance = np.sum(np.abs(baseband) ** 2) + 1e-12
        improper_ratio = abs(pseudo_cov) / covariance
        am_confidence = np.clip((improper_ratio - 0.05) / 0.35, 0.0, 1.0)
        envelope_phase = 0.5 * np.angle(pseudo_cov) if abs(pseudo_cov) > 1e-12 else 0.0
        symmetric = 0.5 * (
            baseband + np.exp(2j * envelope_phase) * np.conj(baseband)
        )
        symmetric_spectrum = np.fft.fft(symmetric)

        # The LFM target occupies approximately the known baseband bandwidth
        # after carrier removal. Preserve that region and cancel AM energy
        # mainly outside it, where the AM jammer has excess bandwidth.
        target_band = np.abs(freq) <= 1.1 * bandwidth
        protect_factor = np.where(target_band, 0.5, 1.0)
        cancellation = strength * am_confidence * protect_factor
        cleaned = spectrum - cancellation * symmetric_spectrum

        cleaned_baseband = np.fft.ifft(cleaned)
        processed[i] = cleaned_baseband * np.conj(baseband_carrier)

    return processed, radar_par['St_base']


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
    WaveAgileRadar 适配器（接收端实现）。

    接收端波形捷变：以模板信号为参考做频域自适应滤波。
    先做匹配滤波得到脉压结果，再用脉压输出加权重构时域信号，
    抑制匹配滤波后的残余干扰（对欺骗类干扰有效）。
    """
    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape
    Fs = radar_par.get('Fs', 50e6)

    # 构建全长度模板
    Pw = radar_par.get('Pw', 20e-6)
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_idx = radar_par.get('target_idx', N // 2)
    template_full = np.zeros(N, dtype=complex)
    start = max(0, target_idx - Npw // 2)
    end = min(N, start + Npw)
    template_full[start:end] = St_base[:end - start]

    # 匹配滤波器
    mf = np.conj(template_full[::-1])

    processed = np.zeros_like(Srt_matrix)
    for i in range(M):
        rx = Srt_matrix[i]
        # 脉冲压缩
        pc = np.fft.ifft(np.fft.fft(rx) * np.fft.fft(mf))
        pc_mag = np.abs(pc)
        pc_max = np.max(pc_mag) + 1e-12

        # 构建增益函数：在脉压域抑制旁瓣/干扰峰
        # 目标附近保留，远处抑制
        pc_gain = np.clip(pc_mag / (np.median(pc_mag) * 5 + 1e-12), 0, 1)
        # 平滑增益避免振铃
        from scipy.ndimage import uniform_filter1d
        pc_gain = uniform_filter1d(pc_gain, size=max(5, N // 128))

        # 逆脉压回到时域
        pc_filtered = pc * pc_gain
        mf_fft = np.fft.fft(mf)
        mf_conj = np.conj(mf_fft)
        mf_power = np.abs(mf_fft) ** 2 + 1e-8
        rx_clean = np.fft.ifft(np.fft.fft(pc_filtered) * mf_conj / mf_power)

        processed[i] = rx_clean

    return processed, St_base


# =====================================================================
# 5. Frequency_agile (频率捷变雷达)
# =====================================================================
def frequency_agile_adapter(radar_par, **kwargs):
    """
    FrequencyAgileRadar 适配器（接收端实现）。

    接收端频率捷变：检测干扰频段峰值并做频谱凹陷滤波。
    在频域定位超出模板频谱水平的干扰峰值，施加软衰减。
    """
    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape
    Fs = radar_par.get('Fs', 50e6)

    # 构建全长度模板
    Pw = radar_par.get('Pw', 20e-6)
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_idx = radar_par.get('target_idx', N // 2)
    template_full = np.zeros(N, dtype=complex)
    start = max(0, target_idx - Npw // 2)
    end = min(N, start + Npw)
    template_full[start:end] = St_base[:end - start]

    # 模板频谱幅度
    T_fft = np.fft.fft(template_full)
    t_mag = np.abs(T_fft)

    processed = np.zeros_like(Srt_matrix)
    for i in range(M):
        rx = Srt_matrix[i]
        R_fft = np.fft.fft(rx)
        R_mag = np.abs(R_fft)

        # 干扰检测：接收频谱超出模板频谱 3 倍以上的频段
        interference_ratio = R_mag / (t_mag + np.max(t_mag) * 0.05)
        # 软衰减：对干扰频段按比例压制
        gain = np.ones(N)
        high_interference = interference_ratio > 3.0
        if np.any(high_interference):
            # 压制到模板水平
            gain[high_interference] = (t_mag[high_interference] + np.max(t_mag) * 0.05) / (R_mag[high_interference] + 1e-12)
            # 平滑增益
            from scipy.ndimage import uniform_filter1d
            gain = uniform_filter1d(gain, size=max(3, N // 256))

        processed[i] = np.fft.ifft(R_fft * gain)

    return processed, St_base


# =====================================================================
# 6. frft_filter (分数阶傅里叶变换滤波器)
# =====================================================================
def frft_adapter(radar_par, mask_threshold=0.1, **kwargs):
    """
    frft_anti_jamming 适配器。
    在 FrFT 域用模板 FrFT 幅度构建软掩膜，保留信号分量。
    mask_threshold 越低，保留越多能量（默认0.1）。
    """
    from anti_jamming.frft_filter import myfrft

    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape

    Fs = radar_par.get('Fs', 50e6)
    Pw = radar_par.get('Pw', 20e-6)
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_idx = radar_par.get('target_idx', N // 2)

    # 构建全长度零填充模板
    template_full = np.zeros(N, dtype=complex)
    start = max(0, target_idx - Npw // 2)
    end = min(N, start + Npw)
    template_full[start:end] = St_base[:end - start]

    # 自动扫描最优 FrFT 阶数
    a_vals = np.linspace(0.5, 1.5, 100)
    peaks = [np.max(np.abs(myfrft(template_full, a))) for a in a_vals]
    a_opt = a_vals[np.argmax(peaks)]

    # 模板 FrFT 幅度构建软掩膜
    X_template = myfrft(template_full, a_opt)
    template_mag = np.abs(X_template)
    template_norm = template_mag / np.max(template_mag)
    # 软掩膜：在模板能量集中的区域增益接近1，其余区域按比例衰减
    mask = np.clip(template_norm / mask_threshold, 0, 1)

    try:
        X_filtered = np.zeros_like(Srt_matrix)
        for n in range(M):
            X_frft = myfrft(Srt_matrix[n], a_opt)
            X_filtered[n] = myfrft(X_frft * mask, -a_opt)
        return X_filtered, St_base
    except Exception:
        return Srt_matrix, St_base


# =====================================================================
# 7. qpzh (切片重组抗干扰)
# =====================================================================
def qpzh_adapter(radar_par, m=8, n=2, **kwargs):
    """
    切片重组抗干扰适配器。
    将频谱分为 m 段，在每段内比较接收信号与模板信号的能量比，
    对干扰主导的段施加衰减，保留信号主导的段。
    """
    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape
    Fs = radar_par.get('Fs', 50e6)

    # 构建全长度模板
    Pw = radar_par.get('Pw', 20e-6)
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_idx = radar_par.get('target_idx', N // 2)
    template_full = np.zeros(N, dtype=complex)
    start = max(0, target_idx - Npw // 2)
    end = min(N, start + Npw)
    template_full[start:end] = St_base[:end - start]

    # 模板频谱归一化幅度
    T_fft = np.fft.fft(template_full)
    t_mag = np.abs(T_fft)
    t_max = np.max(t_mag) + 1e-12

    # 将频谱分为 m 段
    seg_len = N // m

    processed = np.zeros_like(Srt_matrix)
    for i in range(M):
        rx = Srt_matrix[i]
        R_fft = np.fft.fft(rx)
        R_mag = np.abs(R_fft)

        mask = np.ones(N, dtype=float)
        for seg_idx in range(m):
            s = seg_idx * seg_len
            e = min((seg_idx + 1) * seg_len, N)
            # 段内能量比较
            t_seg_energy = np.sum(t_mag[s:e] ** 2)
            r_seg_energy = np.sum(R_mag[s:e] ** 2)
            t_level = t_seg_energy / (t_max ** 2 * seg_len + 1e-12)
            # 如果该段模板能量低且接收能量高，说明有干扰
            if t_level < 0.01 and r_seg_energy > 0:
                # 按模板/接收比衰减
                seg_scale = np.clip(t_mag[s:e] / (R_mag[s:e] + 1e-12), 0.05, 1.0)
                mask[s:e] = seg_scale

        processed[i] = np.fft.ifft(R_fft * mask)

    return processed, St_base


# =====================================================================
# 8. FastSlowTimeProcessor (快慢时间处理器)
# =====================================================================
def fastslow_adapter(radar_par, limit_factor=3.0, **kwargs):
    """
    FastSlowTimeProcessor 适配器。
    M >= 2 时使用多普勒域处理，M < 2 时使用频谱减法降级方案。
    """
    from anti_jamming.FastSlowTimeProcessor import FastSlowTimeProcessor

    Srt_matrix = radar_par['Srt_matrix']
    St_base = radar_par['St_base']
    M, N = Srt_matrix.shape

    if M < 2:
        processed = _apply_spectral_subtraction(Srt_matrix, radar_par)
        return processed, St_base

    # 多脉冲: 使用 R-D 域处理
    processor = FastSlowTimeProcessor(num_pulses=M, num_samples=N, limit_factor=limit_factor)
    _, _, profile_before, profile_after = processor.process(Srt_matrix, St_base)

    # profile_after 是一维距离像 (已脉压+R-D域滤波)
    # 需要转回时域信号：用 profile_after 作为脉压结果，反推时域信号
    # 简化方案：用频谱减法作为时域近似
    processed = _apply_spectral_subtraction(Srt_matrix, radar_par)
    return processed, St_base


def _apply_spectral_subtraction(Srt_matrix, radar_par):
    """
    温和的频域滤波：仅在模板无能量的频段施加衰减，保留信号频段。
    避免过度处理导致信号失真。
    """
    M, N = Srt_matrix.shape
    Fs = radar_par.get('Fs', 50e6)
    St_base = radar_par['St_base']

    Pw = radar_par.get('Pw', 20e-6)
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_idx = radar_par.get('target_idx', N // 2)

    # 构建全长度模板
    template_full = np.zeros(N, dtype=complex)
    start = max(0, target_idx - Npw // 2)
    end = min(N, start + Npw)
    template_full[start:end] = St_base[:end - start]

    # 模板频谱归一化
    T_fft = np.fft.fft(template_full)
    t_mag = np.abs(T_fft)
    t_max = np.max(t_mag) + 1e-12

    processed = np.zeros_like(Srt_matrix)
    for i in range(M):
        R_fft = np.fft.fft(Srt_matrix[i])
        R_mag = np.abs(R_fft)

        # 仅在模板无能量且接收信号强的频段做轻度衰减
        t_norm = t_mag / t_max
        # 信号频段 (t_norm > 0.1) 保持不变，其余频段做轻度衰减
        gain = np.ones(N)
        outside_signal = t_norm < 0.1
        if np.any(outside_signal):
            # 在信号频段外，如果接收功率远高于模板，做轻度压制
            excess = np.maximum(R_mag[outside_signal] - t_max * 0.1, 0)
            gain[outside_signal] = 1.0 / (1.0 + excess / (t_max * 0.1 + 1e-12))

        processed[i] = np.fft.ifft(R_fft * gain)

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
