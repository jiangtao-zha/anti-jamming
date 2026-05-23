# 参数对比：stdPPO 默认参数 vs 暴力搜索最优参数

> 生成日期: 2026-05-20
> 搜索方式: 归一化 [0.02, 0.98] 均匀 50 点网格搜索
> 确认方式: 每组 5 次取平均

## stdPPO 默认参数（归一化值）

| 算法 | 归一化默认值 | 物理参数含义 |
|------|-------------|-------------|
| WLN | 0.30 | par1=0.82, par2=6 |
| FrequencyDomainCanceller | 0.90 | use_fitted_freq=True |
| adapt_filter | 0.50 | par1=0.0 |
| frft_filter | 0.29 | mask_threshold=0.30 |
| qpzh | 0.25 | m=4, n=3.0 |
| FastSlowTimeProcessor | 0.36 | limit_factor=2.76 |

## 默认 vs 最优 对比表（单次搜索结果）

| # | 干扰 | 算法 | 默认SINR改善 | 最优SINR改善 | 默认参数 | 最优参数 | 优化空间 |
|---|------|------|-------------|-------------|---------|---------|---------|
| 1 | FMNoiseAimedJam | frft_filter | +4.49 dB | **+13.96 dB** | threshold=0.30 | threshold=0.66 | **+9.5 dB** |
| 2 | FMZuse | WLN | -4.54 dB | **+6.31 dB** | par1=0.82 | par1=0.99 | **+10.9 dB** |
| 3 | AMNoiseGaiJam | FDC | -1.83 dB | **+4.60 dB** | fitted=True | fitted=True | **+6.4 dB** |
| 4 | FMNoiseSaopin | adapt_filter | +10.33 dB | +11.68 dB | par1=0.0 | par1=-0.65 | +1.4 dB |
| 5 | ISDJ | FSTP | +0.00 dB | +0.00 dB | limit=2.76 | limit=1.57 | 0 dB |
| 6 | SMSP | WLN | -0.83 dB | **+2.91 dB** | par1=0.82 | par1=0.76 | **+3.7 dB** |
| 7 | NoiseProductJamming | FDC | -2.10 dB | **+3.68 dB** | fitted=True | fitted=**False** | **+5.8 dB** |
| 8 | NoiseConvolutionJamming | adapt_filter | +8.27 dB | **+14.67 dB** | par1=0.0 | par1=0.61 | **+6.4 dB** |
| 9 | RGPO | FSTP | +0.00 dB | +0.00 dB | limit=2.76 | limit=1.57 | 0 dB |

## 确认评测（5 次平均）

| # | 干扰 | 算法 | 默认SINR改善 | 最优SINR改善 | 默认检测率 | 最优检测率 | 差距 |
|---|------|------|-------------|-------------|----------|----------|------|
| 1 | FMNoiseAimedJam | frft_filter | +3.38 dB | **+6.13 dB** | 0% | 40% | **+2.75** |
| 2 | FMZuse | WLN | -1.83 dB | -0.96 dB | 0% | 0% | +0.87 |
| 3 | AMNoiseGaiJam | FDC | +0.32 dB | +0.75 dB | 0% | 0% | +0.42 |
| 4 | FMNoiseSaopin | adapt_filter | **+7.30 dB** | +6.59 dB | 100% | 100% | -0.71 |
| 5 | ISDJ | FSTP | +0.00 dB | +0.00 dB | 20% | 20% | 0.00 |
| 6 | SMSP | WLN | -0.80 dB | -0.41 dB | 0% | 0% | +0.39 |
| 7 | NoiseProductJamming | FDC | **+0.70 dB** | -0.92 dB | 0% | 0% | -1.63 |
| 8 | NoiseConvolutionJamming | adapt_filter | +6.21 dB | **+7.86 dB** | 100% | 100% | **+1.65** |
| 9 | RGPO | FSTP | +0.00 dB | +0.00 dB | 0% | 0% | 0.00 |

## 归一化最优值

| 干扰 | 算法 | 默认norm | 最优norm |
|------|------|---------|---------|
| FMNoiseAimedJam | frft_filter | 0.29 | 0.80 |
| FMZuse | WLN | 0.30 | 0.37 |
| AMNoiseGaiJam | FDC | 0.90 | 0.92 |
| FMNoiseSaopin | adapt_filter | 0.50 | 0.18 |
| ISDJ | FSTP | 0.36 | 0.02 |
| SMSP | WLN | 0.30 | 0.27 |
| NoiseProductJamming | FDC | 0.90 | 0.26 |
| NoiseConvolutionJamming | adapt_filter | 0.50 | 0.80 |
| RGPO | FSTP | 0.36 | 0.02 |

## 分析

1. **单次 vs 多次的差异较大**：干扰器内部有随机性（相位、噪声），单次搜索的最优参数在多次平均后优势缩小
2. **frft_filter vs FMNoiseAimedJam 仍有 +2.75 dB 确认优势**，最优 threshold=0.66 比默认 0.30 好
3. **NoiseConvolutionJamming vs adapt_filter 有 +1.65 dB 确认优势**
4. **FMNoiseSaopin 和 NoiseProductJamming 的默认参数反而优于搜索"最优"**，说明单次搜索的最优值过拟合了随机种子
5. **ISDJ 和 RGPO 用 FSTP 在 M=1（单脉冲）下无效**，参数调不调都没区别
6. 多数配对（FMZuse, AMNoiseGaiJam, SMSP）两种参数下 SINR 都为负，说明这些配对本身效果有限，参数优化的空间被配对质量限制
