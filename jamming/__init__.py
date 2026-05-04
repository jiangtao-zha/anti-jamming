"""
干扰信号生成模块包。

所有干扰类遵循标准接口:
    jammer = JammerClass(C=3e8, f0=15e6, T=24e-6, Tr=100e-6, B=5e6)
    composite_signal, range_axis, info_dict = jammer.generate(R_target, JSR_dB=10, noise_var=0.1)
"""

JAMMER_TYPES = [
    'FMZuse',
    'RGPO',
    'ISDJ',
    'SMSP',
    'NoiseProductJamming',
    'NoiseConvolutionJamming',
    'FMNoiseSaopin',
    'FMNoiseAimedJam',
    'AMNoiseGaiJam',
    'SliceCombineJam',
]
