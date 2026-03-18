"""
统一简洁的调用框架，用于连接干扰和抗干扰模块，并使用统一评价函数进行评估。

主要组件：
1. RadarEnvironment: 生成雷达信号（目标）和干扰信号
2. AntiJammingProcessor: 应用抗干扰处理
3. UnifiedEvaluator: 评估处理前后的性能
4. UnifiedFramework: 主类，协调整个流程

示例用法:
    framework = UnifiedFramework(
        jammer_type='FMZuse',
        antijam_type='WLN',
        radar_params={...}
    )
    results = framework.run()
"""

import numpy as np
from scipy import signal
from scipy.fft import fft, fftshift, ifft, fftfreq
import importlib
import sys
import os
import matplotlib.pyplot as plt

# =====================================================================
# 统一评价函数 (从 test_FMZuse_VS_wln_filter.py 复制并稍作修改)
# =====================================================================
class UnifiedEvaluator:
    def __init__(self, guard_cells=4, ref_cells=20, Pfa=1e-5):
        self.guard_cells = guard_cells
        self.ref_cells = ref_cells
        self.Pfa = Pfa

    def ca_cfar_fast(self, mag):
        alpha = self.Pfa ** (-1.0 / (2 * self.ref_cells)) - 1
        kernel_size = 1 + 2 * self.guard_cells + 2 * self.ref_cells
        kernel = np.ones(kernel_size)
        kernel[self.ref_cells : self.ref_cells + 2 * self.guard_cells + 1] = 0
        kernel = kernel / (2 * self.ref_cells)
        mu = signal.correlate(mag, kernel, mode='same', method='fft')
        threshold = alpha * mu
        return mag > threshold, threshold

    def evaluate(self, range_profile, target_idx, w1=0.5, w2=0.5):
        detections, thresholds = self.ca_cfar_fast(range_profile)
        tol = 10 
        start_idx, end_idx = max(0, target_idx - tol), min(len(range_profile), target_idx + tol + 1)
        
        is_detected = np.any(detections[start_idx:end_idx])
        R_Ed = 1.0 if is_detected else 0.0
        
        target_peak_power = np.max(range_profile[start_idx:end_idx])**2
        bg_region = range_profile[max(0, start_idx - self.ref_cells) : min(len(range_profile), end_idx + self.ref_cells)]
        interference_power = np.mean(bg_region)**2 + 1e-12
        sinr_db = 10 * np.log10(target_peak_power / interference_power)
        
        R_ESINR = np.clip((sinr_db - 0.0) / 30.0, 0.0, 1.0)
        if not is_detected: R_ESINR = 0.0
        return {'is_detected': is_detected, 'sinr_db': sinr_db, 'reward': w1 * R_Ed + w2 * R_ESINR, 'thresholds': thresholds}


# =====================================================================
# 雷达环境生成器
# =====================================================================
class RadarEnvironment:
    """生成雷达信号（目标）和干扰信号"""
    
    DEFAULT_RADAR_PARAMS = {
        'f0': 15e6,         # 中心频率 (Hz)
        'Bw': 5e6,          # 带宽 (Hz)
        'Pw': 20e-6,        # 脉宽 (s)
        'Fs': 50e6,         # 采样率 (Hz)
        'M': 1,             # 脉冲数
        'N': int(100e-6 * 50e6),  # 采样点数
        'target_dist': 6000, # 目标距离 (m)
        'target_amp': 1.0,   # 目标幅度
        'jammer_amp': 8.0,   # 干扰幅度
    }
    
    def __init__(self, radar_params=None):
        self.radar_params = self.DEFAULT_RADAR_PARAMS.copy()
        if radar_params:
            self.radar_params.update(radar_params)
        
        # 计算派生参数
        self.Ts = 1 / self.radar_params['Fs']
        self.Npw = int(self.radar_params['Pw'] / self.Ts)
        # 计算目标在距离像中的索引位置
        target_range = self.radar_params['target_dist']
        time_delay = target_range * 2 / 3e8  # 往返时间延迟
        range_bin = int(time_delay / self.Ts)
        self.target_idx = range_bin + self.Npw // 2
        
    def generate_target_signal(self):
        """生成理想发射波形（LFM）"""
        Fs = self.radar_params['Fs']
        Pw = self.radar_params['Pw']
        f0 = self.radar_params['f0']
        Bw = self.radar_params['Bw']
        
        Ts = 1 / Fs
        t_fast = np.arange(int(Pw / Ts)) * Ts
        K = Bw / Pw
        St_base = np.exp(1j * 2 * np.pi * (f0 * t_fast + 0.5 * K * t_fast**2))
        return St_base
    
    def generate_with_jammer(self, jammer):
        """
        使用指定的干扰器生成复合信号
        
        参数:
            jammer: 干扰器实例，需有 generate 方法
        
        返回:
            radar_par: 字典，包含 Srt_matrix, St_base, 目标索引等
        """
        # 生成目标信号
        St_base = self.generate_target_signal()
        
        # 调用干扰器的 generate 方法
        # 假设干扰器需要目标距离和 JSR 等参数
        # 这里简化处理，实际可能需要根据干扰器类型调整
        try:
            # 尝试使用干扰器的默认参数
            J_compound, X_t, jam_info = jammer.generate(
                R_target=self.radar_params['target_dist'],
                JSR_dB=10,  # 默认干信比
                noise_var=0.1
            )
        except Exception as e:
            # 如果失败，尝试其他调用方式
            print(f"干扰器生成失败: {e}")
            # 生成一个简单的干扰信号作为备用
            N = self.radar_params['N']
            J_compound = np.zeros(N, dtype=complex)
            jam_info = {}
        
        # 构建 Srt_matrix（假设干扰器返回的复合信号已经包含目标和干扰）
        # 但为了通用性，我们可能需要在干扰器返回的信号基础上添加目标信号
        # 这里假设干扰器返回的是复合信号（目标+干扰+噪声）
        M = self.radar_params['M']
        N = self.radar_params['N']
        Srt_matrix = np.zeros((M, N), dtype=complex)
        
        # 将复合信号放入矩阵（如果是单脉冲）
        if len(J_compound) >= N:
            Srt_matrix[0, :] = J_compound[:N]
        else:
            Srt_matrix[0, :len(J_compound)] = J_compound
        
        # 构建雷达参数字典
        radar_par = self.radar_params.copy()
        radar_par['Srt_matrix'] = Srt_matrix
        radar_par['St_base'] = St_base
        radar_par['target_idx'] = self.target_idx
        radar_par['jam_info'] = jam_info
        
        return radar_par
    
    def generate_without_jammer(self, noise_level=0.5):
        """
        生成无干扰的雷达信号（仅目标信号+噪声）
        
        参数:
            noise_level: 噪声幅度系数（默认0.5）
        
        返回:
            radar_par: 字典，包含 Srt_matrix, St_base, 目标索引等
        """
        # 生成目标信号
        St_base = self.generate_target_signal()
        
        # 雷达参数
        M = self.radar_params['M']
        N = self.radar_params['N']
        target_amp = self.radar_params['target_amp']
        Ts = self.Ts
        Npw = self.Npw
        
        # 计算目标位置索引
        target_range = self.radar_params['target_dist']
        time_delay = target_range * 2 / 3e8  # 往返时间延迟
        range_bin = int(time_delay / Ts)
        
        # 创建信号矩阵
        Srt_matrix = np.zeros((M, N), dtype=complex)
        
        # 注入目标信号
        pulse_start = range_bin
        pulse_end = min(range_bin + Npw, N)
        pulse_length = pulse_end - pulse_start
        
        if pulse_length > 0:
            # 确保目标信号不会超出矩阵范围
            if pulse_length <= len(St_base):
                Srt_matrix[0, pulse_start:pulse_end] = St_base[:pulse_length] * target_amp
            else:
                Srt_matrix[0, pulse_start:pulse_end] = np.concatenate([
                    St_base, 
                    np.zeros(pulse_length - len(St_base), dtype=complex)
                ]) * target_amp
        
        # 添加高斯白噪声
        noise = noise_level * (np.random.randn(N) + 1j * np.random.randn(N))
        Srt_matrix[0, :] += noise
        
        # 构建雷达参数字典
        radar_par = self.radar_params.copy()
        radar_par['Srt_matrix'] = Srt_matrix
        radar_par['St_base'] = St_base
        radar_par['target_idx'] = self.target_idx
        radar_par['jam_info'] = {'type': 'NoJammer', 'noise_level': noise_level}
        
        return radar_par


# =====================================================================
# 抗干扰处理器
# =====================================================================
class AntiJammingProcessor:
    """加载并应用抗干扰算法"""
    
    def __init__(self, antijam_type='WLN'):
        self.antijam_type = antijam_type
        self.process_func = self._load_antijam_function()
    
    def _load_antijam_function(self):
        """动态加载抗干扰函数"""
        try:
            if self.antijam_type == 'WLN':
                # 从 anti_jamming.wln_filter 导入 WLN 函数
                from anti_jamming.wln_filter import WLN
                return WLN
            elif self.antijam_type == 'FrequencyDomainCanceller':
                from anti_jamming.FrequencyDomainCanceller import FrequencyDomainCanceller
                return FrequencyDomainCanceller
            elif self.antijam_type == 'adapt_filter':
                from anti_jamming.adapt_filter import adapt_filter
                return adapt_filter
            elif self.antijam_type == 'wave_agile':
                from anti_jamming.wave_agile import WaveAgileRadar
                return WaveAgileRadar
            elif self.antijam_type == 'Frequency_agile':
                from anti_jamming.Frequency_agile import FrequencyAgileRadar
                return FrequencyAgileRadar
            elif self.antijam_type == 'frft_filter':
                from anti_jamming.frft_filter import frft_anti_jamming
                return frft_anti_jamming
            elif self.antijam_type == 'qpzh':
                from anti_jamming.qpzh import SliceCombineJam
                return SliceCombineJam
            elif self.antijam_type == 'FastSlowTimeProcessor':
                from anti_jamming.FastSlowTimeProcessor import FastSlowTimeProcessor
                return FastSlowTimeProcessor
            else:
                raise ValueError(f"未知的抗干扰类型: {self.antijam_type}")
        except ImportError as e:
            print(f"无法加载抗干扰模块 {self.antijam_type}: {e}")
            # 返回一个空处理函数作为备用
            def dummy_processor(radar_par, **kwargs):
                return radar_par['Srt_matrix'], radar_par['St_base']
            return dummy_processor
    
    def process(self, radar_par, **kwargs):
        """应用抗干扰处理"""
        # 创建适配的雷达参数字典，确保包含抗干扰函数所需的键
        radar_par_adapted = radar_par.copy()
        
        # 确保存在抗干扰函数可能需要的键
        if 'Srt_matrix' in radar_par_adapted and 'Srt_temp' not in radar_par_adapted:
            radar_par_adapted['Srt_temp'] = radar_par_adapted['Srt_matrix']
        if 'St_base' in radar_par_adapted and 'St1' not in radar_par_adapted:
            radar_par_adapted['St1'] = radar_par_adapted['St_base']
        
        # 调用抗干扰函数
        # 注意：不同的抗干扰函数可能需要不同的参数
        try:
            if self.antijam_type in ['WLN', 'FrequencyDomainCanceller', 'adapt_filter', 
                                     'wave_agile', 'Frequency_agile', 'frft_filter', 'qpzh']:
                # 这些函数通常接受 radar_par 和可选参数
                processed_signal, processed_template = self.process_func(radar_par_adapted, **kwargs)
            elif self.antijam_type == 'FastSlowTimeProcessor':
                # 可能需要不同的调用方式
                processed_signal = self.process_func(radar_par_adapted, **kwargs)
                processed_template = radar_par_adapted['St_base']
            else:
                processed_signal, processed_template = self.process_func(radar_par_adapted, **kwargs)
        except Exception as e:
            print(f"抗干扰处理失败: {e}")
            # 返回原始信号
            processed_signal = radar_par['Srt_matrix']
            processed_template = radar_par['St_base']
        
        return processed_signal, processed_template


# =====================================================================
# 干扰器加载器
# =====================================================================
class JammerLoader:
    """加载干扰器类"""
    
    @staticmethod
    def load(jammer_type, **kwargs):
        """加载干扰器类并创建实例"""
        # 处理无干扰情况
        if jammer_type is None or jammer_type in ['None', 'NoJammer', 'no_jammer', '']:
            # 返回无干扰器
            class NoJammer:
                def __init__(self, **kwargs):
                    self.jammer_type = 'NoJammer'
                
                def generate(self, R_target, JSR_dB=10, noise_var=0.1):
                    # 返回空信号，表示无干扰
                    N = 5000  # 默认长度，实际会在环境中被覆盖
                    signal = np.zeros(N, dtype=complex)
                    return signal, np.arange(N), {'type': 'NoJammer'}
            return NoJammer(**kwargs)
        
        try:
            if jammer_type == 'FMZuse':
                from jamming.FMZuse import FMZuse
                return FMZuse(**kwargs)
            elif jammer_type == 'RGPO':
                from jamming.RGPO import RGPO
                return RGPO(**kwargs)
            elif jammer_type == 'ISDJ':
                from jamming.ISDJ import ISDJ
                return ISDJ(**kwargs)
            elif jammer_type == 'SMSP':
                from jamming.SMSP import SMSP
                return SMSP(**kwargs)
            elif jammer_type == 'NoiseProductJamming':
                from jamming.NoiseProductJamming import NoiseProductJamming
                return NoiseProductJamming(**kwargs)
            elif jammer_type == 'NoiseConvolutionJamming':
                from jamming.NoiseConvolutionJamming import NoiseConvolutionJamming
                return NoiseConvolutionJamming(**kwargs)
            elif jammer_type == 'FMNoiseSaopin':
                from jamming.FMNoiseSaopin import FMNoiseSaopin
                return FMNoiseSaopin(**kwargs)
            elif jammer_type == 'FMNoiseAimedJam':
                from jamming.FMNoiseAimedJam import FMNoiseAimedJam
                return FMNoiseAimedJam(**kwargs)
            elif jammer_type == 'AMNoiseGaiJam':
                from jamming.AMNoiseGaiJam import AMNoiseGaiJam
                return AMNoiseGaiJam(**kwargs)
            else:
                raise ValueError(f"未知的干扰类型: {jammer_type}")
        except ImportError as e:
            print(f"无法加载干扰模块 {jammer_type}: {e}")
            # 返回一个虚拟干扰器
            class DummyJammer:
                def generate(self, R_target, JSR_dB=10, noise_var=0.1):
                    N = 1000
                    signal = np.zeros(N, dtype=complex)
                    return signal, np.arange(N), {}
            return DummyJammer()


# =====================================================================
# 统一框架主类
# =====================================================================
class UnifiedFramework:
    """
    统一调用框架
    
    示例:
        framework = UnifiedFramework(
            jammer_type='FMZuse',
            antijam_type='WLN',
            radar_params={'f0': 15e6, 'Bw': 5e6, ...}
        )
        results = framework.run()
    """
    
    def __init__(self, jammer_type='FMZuse', antijam_type='WLN', 
                 radar_params=None, evaluator_params=None):
        """
        初始化框架
        
        参数:
            jammer_type: 干扰类型（字符串）
            antijam_type: 抗干扰类型（字符串）
            radar_params: 雷达参数字典（可选）
            evaluator_params: 评估器参数字典（可选）
        """
        self.jammer_type = jammer_type
        self.antijam_type = antijam_type
        
        # 加载干扰器
        self.jammer = JammerLoader.load(jammer_type)
        
        # 初始化抗干扰处理器
        self.antijam_processor = AntiJammingProcessor(antijam_type)
        
        # 初始化雷达环境
        self.environment = RadarEnvironment(radar_params)
        
        # 初始化评估器
        eval_params = evaluator_params or {}
        self.evaluator = UnifiedEvaluator(**eval_params)
        
        # 存储结果
        self.results = {}
    
    def _is_no_jammer(self):
        """检查是否为无干扰情况"""
        return (self.jammer_type is None or 
                str(self.jammer_type).lower() in ['none', 'nojammer', 'no_jammer', ''])
    
    def run(self, antijam_kwargs=None):
        """
        运行完整的干扰-抗干扰-评估流程
        
        参数:
            antijam_kwargs: 传递给抗干扰处理的额外参数
        
        返回:
            results: 包含原始和处理后结果的字典
        """
        antijam_kwargs = antijam_kwargs or {}
        
        # 1. 生成雷达信号（根据是否有干扰）
        if self._is_no_jammer():
            print(f"无干扰仿真，仅生成目标信号")
            radar_par = self.environment.generate_without_jammer()
        else:
            print(f"生成干扰: {self.jammer_type}")
            radar_par = self.environment.generate_with_jammer(self.jammer)
        
        # 2. 应用抗干扰处理
        print(f"应用抗干扰: {self.antijam_type}")
        processed_signal, processed_template = self.antijam_processor.process(
            radar_par, **antijam_kwargs
        )
        
        # 3. 匹配滤波
        print("进行匹配滤波...")
        St_base = radar_par['St_base']
        Srt_orig = radar_par['Srt_matrix'][0]  # 取第一个脉冲
        
        # 原始信号匹配滤波
        pc_orig = signal.fftconvolve(Srt_orig, np.conj(St_base[::-1]), mode='same')
        
        # 处理后的信号匹配滤波
        # 确保 processed_signal 是 numpy 数组
        if not isinstance(processed_signal, np.ndarray):
            try:
                # 尝试转换为 numpy 数组
                processed_signal = np.array(processed_signal)
            except:
                # 如果转换失败，使用原始信号
                print("警告: 抗干扰处理器返回的信号无法转换为 numpy 数组，使用原始信号")
                processed_signal = Srt_orig
        
        # 提取第一个脉冲（如果信号是2D矩阵）
        if processed_signal.ndim == 2:
            Srt_filtered = processed_signal[0]
        else:
            Srt_filtered = processed_signal
        
        pc_filtered = signal.fftconvolve(Srt_filtered, np.conj(St_base[::-1]), mode='same')
        
        # 4. 评估
        print("进行评估...")
        target_idx = radar_par['target_idx']
        info_orig = self.evaluator.evaluate(np.abs(pc_orig), target_idx)
        info_filtered = self.evaluator.evaluate(np.abs(pc_filtered), target_idx)
        
        # 5. 存储结果
        self.results = {
            'original': {
                'signal': Srt_orig,
                'range_profile': pc_orig,
                'evaluation': info_orig
            },
            'processed': {
                'signal': Srt_filtered,
                'range_profile': pc_filtered,
                'evaluation': info_filtered
            },
            'radar_params': radar_par,
            'jammer_type': self.jammer_type,
            'antijam_type': self.antijam_type
        }
        
        # 6. 打印摘要
        print("\n" + "="*50)
        print("抗干扰前 -> 检测: {}, SINR: {:.2f} dB, Reward: {:.4f}".format(
            info_orig['is_detected'], info_orig['sinr_db'], info_orig['reward']))
        print("抗干扰后 -> 检测: {}, SINR: {:.2f} dB, Reward: {:.4f}".format(
            info_filtered['is_detected'], info_filtered['sinr_db'], info_filtered['reward']))
        print("="*50)
        
        return self.results
    
    def get_summary(self):
        """获取结果摘要"""
        if not self.results:
            return "尚未运行，请先调用 run() 方法"
        
        orig = self.results['original']['evaluation']
        proc = self.results['processed']['evaluation']
        
        summary = f"""
干扰类型: {self.jammer_type}
抗干扰类型: {self.antijam_type}

抗干扰前:
  检测成功: {orig['is_detected']}
  SINR: {orig['sinr_db']:.2f} dB
  Reward: {orig['reward']:.4f}

抗干扰后:
  检测成功: {proc['is_detected']}
  SINR: {proc['sinr_db']:.2f} dB
  Reward: {proc['reward']:.4f}

SINR 改善: {proc['sinr_db'] - orig['sinr_db']:.2f} dB
Reward 改善: {proc['reward'] - orig['reward']:.4f}
        """
        return summary

    def visualize(self, save_path=None, show_plot=True):
        """
        可视化抗干扰前后的信号对比
        
        参数:
            save_path: 保存图片的路径（可选）
            show_plot: 是否显示图表（默认True）
        """
        if not self.results:
            print("尚未运行，请先调用 run() 方法")
            return
        
        # 获取结果数据
        orig = self.results['original']
        proc = self.results['processed']
        radar_par = self.results['radar_params']
        
        # 雷达参数
        Ts = 1 / radar_par['Fs']
        N = radar_par['N']
        Npw = int(radar_par['Pw'] / Ts)
        target_dist = radar_par['target_dist']
        
        # 信号
        Srt_orig = orig['signal']
        Srt_filtered = proc['signal']
        pc_orig = orig['range_profile']
        pc_filtered = proc['range_profile']
        
        # 评估信息
        info_orig = orig['evaluation']
        info_filtered = proc['evaluation']
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建图形
        plt.figure(figsize=(16, 12))
        
        # 时间轴（微秒）
        t_axis = np.arange(N) * Ts * 1e6
        
        # 距离轴（千米）
        dist_axis = (np.arange(N) - Npw/2) * (3e8 / (2 * radar_par['Fs'])) / 1000
        
        # 1. 时域对比
        plt.subplot(3, 1, 1)
        plt.plot(t_axis, np.abs(Srt_orig), label='抗干扰前 (原始信号)', color='gray', alpha=0.5)
        plt.plot(t_axis, np.abs(Srt_filtered), label='抗干扰后 (处理后信号)', color='blue')
        # 如果有VL（限幅阈值）信息，可以添加
        # plt.axhline(y=VL, color='red', linestyle='--', label=f'限幅阈值 (VL={VL:.2f})')
        plt.title(f'1. 时域对比：{self.jammer_type} 干扰 vs {self.antijam_type} 抗干扰')
        plt.xlabel('时间 (us)')
        plt.ylabel('幅度')
        plt.xlim([30, 70])  # 聚焦在目标区域
        plt.legend(loc='upper right')
        plt.grid(True)
        
        # 2. 频域对比
        plt.subplot(3, 1, 2)
        f_axis = fftshift(fftfreq(N, Ts))
        plt.plot(f_axis/1e6, 20*np.log10(np.abs(fftshift(fft(Srt_orig))) + 1e-12), 
                 label='原始频谱', color='gray', alpha=0.6)
        plt.plot(f_axis/1e6, 20*np.log10(np.abs(fftshift(fft(Srt_filtered))) + 1e-12), 
                 label='处理后频谱', color='blue')
        plt.title('2. 频域对比：抗干扰处理对频谱的影响')
        plt.xlabel('频率 (MHz)')
        plt.ylabel('功率 (dB)')
        plt.xlim([0, 30])  # 聚焦在雷达频段
        plt.legend(loc='upper right')
        plt.grid(True)
        
        # 3. 距离像对比
        plt.subplot(3, 1, 3)
        plt.plot(dist_axis, 20*np.log10(np.abs(pc_orig) + 1e-10), 
                 label='抗干扰前距离像', color='gray', alpha=0.5)
        plt.plot(dist_axis, 20*np.log10(np.abs(pc_filtered) + 1e-10), 
                 label='抗干扰后距离像', color='red', linewidth=2)
        plt.plot(dist_axis, 20*np.log10(info_filtered['thresholds'] + 1e-10), 
                 label='CA-CFAR 检测阈值', color='green', linestyle='--')
        plt.axvline(x=target_dist/1000, color='blue', linestyle='-.', 
                   label=f'真实目标位置 ({target_dist/1000:.1f} km)')
        plt.title(f'3. 距离像验证：SINR 提升至 {info_filtered["sinr_db"]:.2f} dB，Reward: {info_filtered["reward"]:.4f}')
        plt.xlabel('距离 (km)')
        plt.ylabel('幅度 (dB)')
        plt.xlim([4.5, 7.5])  # 聚焦在目标距离附近
        plt.ylim([0, 80])
        plt.legend(loc='upper right')
        plt.grid(True)
        
        plt.tight_layout()
        
        # 保存图像
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"图表已保存到: {save_path}")
        
        # 显示图像
        if show_plot:
            plt.show()
        else:
            plt.close()


# =====================================================================
# 便捷函数
# =====================================================================
def run_simulation(jammer_type='FMZuse', antijam_type='WLN', 
                   radar_params=None, evaluator_params=None,
                   antijam_kwargs=None):
    """
    便捷函数：运行一次仿真
    
    返回:
        results: 仿真结果字典
    """
    framework = UnifiedFramework(
        jammer_type=jammer_type,
        antijam_type=antijam_type,
        radar_params=radar_params,
        evaluator_params=evaluator_params
    )
    return framework.run(antijam_kwargs=antijam_kwargs)


def batch_simulation(configs):
    """
    批量运行多个仿真配置
    
    参数:
        configs: 配置列表，每个元素为字典，包含 jammer_type, antijam_type 等
    
    返回:
        结果列表
    """
    results = []
    for i, config in enumerate(configs):
        print(f"\n运行配置 {i+1}/{len(configs)}")
        print(f"干扰: {config.get('jammer_type', 'FMZuse')}, "
              f"抗干扰: {config.get('antijam_type', 'WLN')}")
        
        try:
            result = run_simulation(**config)
            results.append(result)
        except Exception as e:
            print(f"配置 {i+1} 失败: {e}")
            results.append(None)
    
    return results


def run_comprehensive_tests(jammer_types=None, antijam_types=None, 
                           radar_params=None, evaluator_params=None,
                           antijam_kwargs_map=None, save_plots=False, 
                           output_dir='./results'):
    """
    运行全面的干扰-抗干扰组合测试
    
    参数:
        jammer_types: 干扰类型列表（默认使用所有可用类型）
        antijam_types: 抗干扰类型列表（默认使用所有可用类型）
        radar_params: 雷达参数字典
        evaluator_params: 评估器参数字典
        antijam_kwargs_map: 抗干扰参数映射，格式为 {antijam_type: kwargs_dict}
        save_plots: 是否保存可视化图表
        output_dir: 输出目录
        
    返回:
        results_dict: 字典，键为 (jammer_type, antijam_type)，值为结果字典
    """
    # 默认干扰类型列表
    if jammer_types is None:
        jammer_types = [
            'FMZuse', 'RGPO', 'ISDJ', 'SMSP', 
            'NoiseProductJamming', 'NoiseConvolutionJamming',
            'FMNoiseSaopin', 'FMNoiseAimedJam', 'AMNoiseGaiJam'
        ]
    
    # 默认抗干扰类型列表
    if antijam_types is None:
        antijam_types = [
            'WLN', 'FrequencyDomainCanceller', 'adapt_filter',
            'wave_agile', 'Frequency_agile', 'frft_filter',
            'qpzh', 'FastSlowTimeProcessor'
        ]
    
    # 创建输出目录
    if save_plots and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    results_dict = {}
    total_combinations = len(jammer_types) * len(antijam_types)
    current = 0
    
    for jammer_type in jammer_types:
        for antijam_type in antijam_types:
            current += 1
            print(f"\n{'='*60}")
            print(f"测试组合 {current}/{total_combinations}: {jammer_type} 干扰 vs {antijam_type} 抗干扰")
            print(f"{'='*60}")
            
            # 获取抗干扰参数（如果有）
            antijam_kwargs = None
            if antijam_kwargs_map and antijam_type in antijam_kwargs_map:
                antijam_kwargs = antijam_kwargs_map[antijam_type]
            
            try:
                # 运行仿真
                result = run_simulation(
                    jammer_type=jammer_type,
                    antijam_type=antijam_type,
                    radar_params=radar_params,
                    evaluator_params=evaluator_params,
                    antijam_kwargs=antijam_kwargs
                )
                
                # 存储结果
                key = (jammer_type, antijam_type)
                results_dict[key] = result
                
                # 如果保存图表，创建可视化
                if save_plots:
                    # 创建框架实例用于可视化
                    framework = UnifiedFramework(
                        jammer_type=jammer_type,
                        antijam_type=antijam_type,
                        radar_params=radar_params,
                        evaluator_params=evaluator_params
                    )
                    framework.results = result
                    
                    # 生成文件名
                    filename = f"{jammer_type}_vs_{antijam_type}.png"
                    filepath = os.path.join(output_dir, filename)
                    
                    # 保存图表（不显示）
                    framework.visualize(save_path=filepath, show_plot=False)
                    print(f"图表已保存: {filepath}")
                    
                # 打印摘要
                orig = result['original']['evaluation']
                proc = result['processed']['evaluation']
                print(f"抗干扰前: 检测={orig['is_detected']}, SINR={orig['sinr_db']:.2f} dB, Reward={orig['reward']:.4f}")
                print(f"抗干扰后: 检测={proc['is_detected']}, SINR={proc['sinr_db']:.2f} dB, Reward={proc['reward']:.4f}")
                print(f"SINR改善: {proc['sinr_db'] - orig['sinr_db']:.2f} dB, Reward改善: {proc['reward'] - orig['reward']:.4f}")
                
            except Exception as e:
                print(f"组合 {jammer_type} vs {antijam_type} 失败: {e}")
                results_dict[(jammer_type, antijam_type)] = None
    
    # 打印总体统计
    print(f"\n{'='*60}")
    print("全面测试完成!")
    print(f"{'='*60}")
    
    successful = sum(1 for v in results_dict.values() if v is not None)
    failed = total_combinations - successful
    
    print(f"成功: {successful}/{total_combinations}, 失败: {failed}")
    
    # 计算平均改善
    sinr_improvements = []
    reward_improvements = []
    
    for key, result in results_dict.items():
        if result is not None:
            orig = result['original']['evaluation']
            proc = result['processed']['evaluation']
            sinr_improvements.append(proc['sinr_db'] - orig['sinr_db'])
            reward_improvements.append(proc['reward'] - orig['reward'])
    
    if sinr_improvements:
        print(f"平均 SINR 改善: {np.mean(sinr_improvements):.2f} dB")
        print(f"平均 Reward 改善: {np.mean(reward_improvements):.4f}")
    
    return results_dict


# =====================================================================
# 主函数（示例）
# =====================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='运行干扰-抗干扰测试')
    parser.add_argument('--comprehensive', action='store_true', 
                       help='运行全面测试（所有干扰和抗干扰组合）')
    parser.add_argument('--quick', action='store_true', 
                       help='运行快速测试（单个组合）')
    parser.add_argument('--save-plots', action='store_true', 
                       help='保存可视化图表')
    parser.add_argument('--output-dir', default='./results', 
                       help='输出目录（默认: ./results）')
    args = parser.parse_args()
    
    # 自定义雷达参数（可选）
    custom_radar_params = {
        'f0': 15e6,
        'Bw': 5e6,
        'Pw': 20e-6,
        'Fs': 50e6,
        'target_dist': 6000,
        'jammer_amp': 8.0
    }
    
    # 抗干扰参数映射（根据需要调整）
    antijam_kwargs_map = {
        'WLN': {'par1': 2.5, 'par2': 6},
        # 其他抗干扰类型的参数可以在这里添加
    }
    
    # 默认运行全面测试，除非指定了 --quick
    if args.quick or not args.comprehensive:
        print("开始运行快速测试...")
        
        # 运行单个仿真
        results = run_simulation(
            jammer_type='FMNoiseAimedJam',
            antijam_type='WLN',
            radar_params=custom_radar_params,
            antijam_kwargs={'par1': 2.5, 'par2': 6}
        )
        
        # 打印摘要
        framework = UnifiedFramework('FMZuse', 'WLN', custom_radar_params)
        framework.results = results
        print(framework.get_summary())
        
        # 可视化
        framework.visualize(save_path='./quick_test.png' if args.save_plots else None)
        
    else:
        print("开始运行全面测试...")
        print("这将测试所有干扰和抗干扰组合，可能需要一些时间...")
        
        # 运行全面测试
        results_dict = run_comprehensive_tests(
            radar_params=custom_radar_params,
            antijam_kwargs_map=antijam_kwargs_map,
            save_plots=args.save_plots,
            output_dir=args.output_dir
        )
        
        # 生成总结报告
        print("\n" + "="*60)
        print("全面测试总结报告")
        print("="*60)
        
        # 找出效果最好的组合
        best_improvement = -float('inf')
        best_key = None
        
        for key, result in results_dict.items():
            if result is not None:
                orig = result['original']['evaluation']
                proc = result['processed']['evaluation']
                improvement = proc['reward'] - orig['reward']
                
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_key = key
        
        if best_key:
            print(f"\n最佳抗干扰组合: {best_key[0]} 干扰 vs {best_key[1]} 抗干扰")
            print(f"Reward 改善: {best_improvement:.4f}")
            
            # 显示最佳组合的详细信息
            best_result = results_dict[best_key]
            orig = best_result['original']['evaluation']
            proc = best_result['processed']['evaluation']
            print(f"抗干扰前: 检测={orig['is_detected']}, SINR={orig['sinr_db']:.2f} dB, Reward={orig['reward']:.4f}")
            print(f"抗干扰后: 检测={proc['is_detected']}, SINR={proc['sinr_db']:.2f} dB, Reward={proc['reward']:.4f}")
        
        print("\n测试完成！")