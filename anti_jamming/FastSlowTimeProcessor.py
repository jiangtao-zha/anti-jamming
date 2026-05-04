import numpy as np
from scipy import signal
from scipy.fft import fft, fftshift
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

class FastSlowTimeProcessor:
    def __init__(self, num_pulses, num_samples, limit_factor=3.0):
        self.M = num_pulses
        self.N = num_samples
        self.limit_factor = limit_factor

    def pulse_compression(self, Srt_matrix, ref_signal):
        PC_matrix = np.zeros_like(Srt_matrix, dtype=complex)
        matched_filter = np.conj(ref_signal[::-1])
        for m in range(self.M):
            PC_matrix[m, :] = signal.fftconvolve(Srt_matrix[m, :], matched_filter, mode='same')
        return PC_matrix

    def process(self, Srt_matrix, ref_signal):
        # 1. 快时间域脉压
        PC_matrix = self.pulse_compression(Srt_matrix, ref_signal)
        
        # 2. 慢时间域 FFT
        window = np.hamming(self.M)[:, None]
        RD_matrix = fftshift(fft(PC_matrix * window, axis=0), axes=0)
        Filtered_RD = RD_matrix.copy()

        # 3. 评估多普勒通道能量
        doppler_energy = np.mean(np.abs(RD_matrix), axis=1)
        global_median_energy = np.median(doppler_energy)
        
        # 识别被干扰严重污染的通道 (整行识别)
        jammed_channels = doppler_energy > (global_median_energy * self.limit_factor)
        noise_floor = np.median(np.abs(RD_matrix))

        # 【核心修复 2：整行通道切除】
        for m in range(self.M):
            if jammed_channels[m]:
                # 一旦通道被切片干扰霸占，直接将整个通道“挖空”，替换为系统底噪
                # 斩草除根，杜绝任何裙边旁瓣在后续投影中作祟
                Filtered_RD[m, :] = (np.random.randn(self.N) + 
                                     1j * np.random.randn(self.N)) * (noise_floor / np.sqrt(2))

        # 4. 投影回一维距离像用于检测
        range_profile_before = np.max(np.abs(RD_matrix), axis=0)
        range_profile_after = np.max(np.abs(Filtered_RD), axis=0)

        return RD_matrix, Filtered_RD, range_profile_before, range_profile_after

# ==========================================
# 闭环测试脚本
# ==========================================
def test_fast_slow_time_processor(seed=None):
    """
    测试快慢时间处理器（FastSlowTimeProcessor）抗干扰算法。
    使用项目标准干扰生成器加载 SliceCombineJam、SMSP。
    注意：该算法需要多脉冲数据（M>=2），测试使用 M=8 脉冲。

    修改说明 (2026-04-27):
        由于所有干扰器的 generate() 返回复合信号（目标+干扰+噪声），
        测试中需要从复合信号中分离目标分量，以便对目标施加多普勒相移，
        使目标与干扰在多普勒域可分离，从而验证算法有效性。

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

    # 多脉冲参数
    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    M = 8  # 脉冲数
    N = radar_params['N']
    Fs = radar_params['Fs']
    Pw = radar_params['Pw']
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_dist = radar_params['target_dist']
    target_amp = radar_params['target_amp']

    # 计算目标在距离像中的索引
    target_delay = target_dist * 2 / 3e8
    target_delay_idx = int(target_delay / Ts)
    target_idx = target_delay_idx + Npw // 2

    jammer_types = ['SliceCombineJam', 'SMSP']
    results = {}

    for jt in jammer_types:
        jammer = JammerLoader.load(jt)

        # 用干扰器内部参数复现目标回波分量
        # （所有干扰器的目标回波公式一致: rectpuls + LFM）
        C_jam = jammer.C
        f0_jam = jammer.f0
        T_jam = jammer.T
        Tr_jam = jammer.Tr
        B_jam = jammer.B
        K_jam = B_jam / T_jam
        Fs_jam = jammer.Fs
        Ts_jam = 1.0 / Fs_jam
        N2 = int(np.ceil(Tr_jam / Ts_jam))

        t1 = np.linspace(2 * target_dist / C_jam, Tr_jam + 2 * target_dist / C_jam, N2)
        td = t1 - 2 * target_dist / C_jam

        def _rectpuls(t, width):
            return np.where((t >= 0) & (t < width), 1.0, 0.0)

        window_srt = _rectpuls(td - T_jam, T_jam)
        St_target_echo = window_srt * np.exp(1j * (np.pi * K_jam * (td - T_jam) ** 2 +
                                                  2 * np.pi * f0_jam * (td - T_jam)))

        # 生成 LFM 模板（用于脉冲压缩，使用统一框架的参数）
        env = RadarEnvironment(radar_params)
        St_base = env.generate_target_signal()

        # 生成复合信号（含目标+干扰+噪声），然后分离目标分量得到纯干扰+噪声
        J_composite, _, _ = jammer.generate(
            R_target=target_dist,
            JSR_dB=radar_params.get('JSR_dB', 10),
            noise_var=radar_params.get('noise_var', 0.1)
        )

        # 裁剪或补零到统一长度 N
        def _to_len(sig, length):
            if len(sig) >= length:
                return sig[:length]
            out = np.zeros(length, dtype=complex)
            out[:len(sig)] = sig
            return out

        St_target_N = _to_len(St_target_echo, N)
        J_composite_N = _to_len(J_composite, N)
        J_jamming_only = J_composite_N - St_target_N  # 干扰 + 首次噪声

        # 构建多脉冲信号矩阵：目标有多普勒，干扰无多普勒
        Srt_matrix = np.zeros((M, N), dtype=complex)
        noise_var = radar_params.get('noise_var', 0.1)
        noise_level = np.sqrt(noise_var)
        fd_target = 500  # 目标多普勒频率 Hz

        for m in range(M):
            doppler_phase = np.exp(1j * 2 * np.pi * fd_target * m * 1e-3)
            pulse_noise = noise_level * (np.random.randn(N) + 1j * np.random.randn(N))
            Srt_matrix[m, :] = St_target_N * doppler_phase * target_amp + J_jamming_only + pulse_noise

        # 应用 FastSlowTimeProcessor（直接调用类，不通过适配器）
        processor = FastSlowTimeProcessor(num_pulses=M, num_samples=N)
        RD_orig, RD_filtered, profile_before, profile_after = processor.process(Srt_matrix, St_base)

        # CA-CFAR 评估距离像
        evaluator = UnifiedEvaluator()
        info_before = evaluator.evaluate(profile_before, target_idx)
        info_after = evaluator.evaluate(profile_after, target_idx)

        results[jt] = {
            'before': info_before,
            'after': info_after,
            'sinr_improvement': info_after['sinr_db'] - info_before['sinr_db']
        }

        print(f"\n{'='*55}")
        print(f"  测试: FastSlowTimeProcessor vs {jt} (M={M}脉冲)")
        print(f"  处理前: 检测={info_before['is_detected']}, SINR={info_before['sinr_db']:.2f} dB")
        print(f"  处理后: 检测={info_after['is_detected']}, SINR={info_after['sinr_db']:.2f} dB")
        print(f"  SINR改善: {info_after['sinr_db'] - info_before['sinr_db']:.2f} dB")
        print(f"{'='*55}")

    return results


def run_visual_test():
    """
    快慢时间处理器（FastSlowTimeProcessor）的可视化测试。
    展示 R-D 图和距离像在 SliceCombineJam / SMSP 干扰下的变化。
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from unified_framework import RadarEnvironment, JammerLoader

    radar_params = RadarEnvironment.DEFAULT_RADAR_PARAMS.copy()
    M = 8
    N = radar_params['N']
    Fs = radar_params['Fs']
    Pw = radar_params['Pw']
    Ts = 1.0 / Fs
    Npw = int(Pw / Ts)
    target_dist = radar_params['target_dist']
    target_amp = radar_params['target_amp']
    target_delay = target_dist * 2 / 3e8
    target_delay_idx = int(target_delay / Ts)
    target_idx = target_delay_idx + Npw // 2
    noise_var = radar_params.get('noise_var', 0.1)
    noise_level = np.sqrt(noise_var)
    fd_target = 500

    env = RadarEnvironment(radar_params)
    St_base = env.generate_target_signal()

    jammer_types = ['SliceCombineJam', 'SMSP']

    for jt in jammer_types:
        np.random.seed(42)
        jammer = JammerLoader.load(jt)

        C_jam = jammer.C
        f0_jam = jammer.f0
        T_jam = jammer.T
        Tr_jam = jammer.Tr
        B_jam = jammer.B
        K_jam = B_jam / T_jam
        Fs_jam = jammer.Fs
        Ts_jam = 1.0 / Fs_jam
        N2 = int(np.ceil(Tr_jam / Ts_jam))

        t1 = np.linspace(2 * target_dist / C_jam, Tr_jam + 2 * target_dist / C_jam, N2)
        td = t1 - 2 * target_dist / C_jam

        def _rectpuls(t, width):
            return np.where((t >= 0) & (t < width), 1.0, 0.0)

        window_srt = _rectpuls(td - T_jam, T_jam)
        St_target_echo = window_srt * np.exp(1j * (np.pi * K_jam * (td - T_jam) ** 2 +
                                                   2 * np.pi * f0_jam * (td - T_jam)))

        J_composite, _, _ = jammer.generate(
            R_target=target_dist,
            JSR_dB=radar_params.get('JSR_dB', 10),
            noise_var=radar_params.get('noise_var', 0.1)
        )

        def _to_len(sig, length):
            if len(sig) >= length:
                return sig[:length]
            out = np.zeros(length, dtype=complex)
            out[:len(sig)] = sig
            return out

        St_target_N = _to_len(St_target_echo, N)
        J_composite_N = _to_len(J_composite, N)
        J_jamming_only = J_composite_N - St_target_N

        Srt_matrix = np.zeros((M, N), dtype=complex)
        for m in range(M):
            doppler_phase = np.exp(1j * 2 * np.pi * fd_target * m * 1e-3)
            pulse_noise = noise_level * (np.random.randn(N) + 1j * np.random.randn(N))
            Srt_matrix[m, :] = St_target_N * doppler_phase * target_amp + J_jamming_only + pulse_noise

        processor = FastSlowTimeProcessor(num_pulses=M, num_samples=N)
        RD_orig, RD_filtered, profile_before, profile_after = processor.process(Srt_matrix, St_base)

        # --- 绘图 ---
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # (a) R-D 图（处理前）
        doppler_axis = np.linspace(-M / 2, M / 2, M)
        range_axis_rd = np.arange(N) * 3e8 / (2 * Fs)
        im1 = axes[0, 0].pcolormesh(range_axis_rd, doppler_axis,
                                      20 * np.log10(np.abs(RD_orig) + 1e-10),
                                      shading='auto', cmap='jet')
        axes[0, 0].set_xlabel('距离 (m)')
        axes[0, 0].set_ylabel('多普勒通道')
        axes[0, 0].set_title(f'(a) R-D 图（处理前）— {jt}')
        plt.colorbar(im1, ax=axes[0, 0], label='dB')

        # (b) R-D 图（处理后）
        im2 = axes[0, 1].pcolormesh(range_axis_rd, doppler_axis,
                                      20 * np.log10(np.abs(RD_filtered) + 1e-10),
                                      shading='auto', cmap='jet')
        axes[0, 1].set_xlabel('距离 (m)')
        axes[0, 1].set_ylabel('多普勒通道')
        axes[0, 1].set_title(f'(b) R-D 图（处理后）— {jt}')
        plt.colorbar(im2, ax=axes[0, 1], label='dB')

        # (c) 距离像对比（线性）
        range_axis = np.arange(len(profile_before)) * 3e8 / (2 * Fs)
        axes[1, 0].plot(range_axis, profile_before, label='处理前', alpha=0.7)
        axes[1, 0].plot(range_axis, profile_after, label='处理后', alpha=0.7)
        axes[1, 0].set_xlabel('距离 (m)')
        axes[1, 0].set_ylabel('幅度')
        axes[1, 0].set_title(f'(c) 距离像对比 — {jt}')
        axes[1, 0].legend()
        axes[1, 0].grid(True)

        # (d) 距离像对比（dB）
        axes[1, 1].plot(range_axis, 20 * np.log10(profile_before + 1e-10), label='处理前', alpha=0.7)
        axes[1, 1].plot(range_axis, 20 * np.log10(profile_after + 1e-10), label='处理后', alpha=0.7)
        axes[1, 1].set_xlabel('距离 (m)')
        axes[1, 1].set_ylabel('幅度 (dB)')
        axes[1, 1].set_title(f'(d) 距离像对比 (dB) — {jt}')
        axes[1, 1].legend()
        axes[1, 1].grid(True)

        plt.tight_layout()
        plt.suptitle(f'快慢时间处理器 vs {jt}', fontsize=14, y=1.02)
        plt.show()


if __name__ == "__main__":
    run_visual_test()