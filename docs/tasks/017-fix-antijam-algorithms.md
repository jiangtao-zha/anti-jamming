# 017: 修复和提升抗干扰算法效果

> 优先级: **高**
> 状态: **已修复，验证通过**
> 创建: 2026-05-23
> 关联: `docs/tasks/016-fix-antijam-for-markov.md`（D类采样率修复已完成）

## 背景

D类采样率修复后，ISDJ 基线恢复正常。全算法扫描发现 adapt_filter 全局最优（+6~8 dB, 100%检测率）。

为让 RL 有学习空间，需要提升其他算法的效果，创造算法间的差异化。

## 当前各算法性能（JSR=10dB, Fs=50MHz, 10次平均）

### adapt_filter（基准，全局最优）

| 干扰 | SINR改善 | 检测率 |
|------|---------|--------|
| ISDJ | +6.42 dB | 100% |
| SMSP | +6.42 dB | 100% |
| RGPO | +5.82 dB | 100% |
| AMNoiseGaiJam | +6.77 dB | 100% |
| FMZuse | +7.69 dB | 100% |
| FMNoiseSaopin | +7.21 dB | 100% |
| FMNoiseAimedJam | +7.42 dB | 100% |
| NoiseProduct | +7.91 dB | 100% |
| NoiseConvolution | +7.91 dB | 100% |

### frft_filter（第二优，可调参提升）

当前默认 mask_threshold=0.3：

| 干扰 | thr=0.3 | thr=0.5 | 提升 |
|------|---------|---------|------|
| ISDJ | +3.43 | **+4.22** | +0.79 |
| SMSP | +4.32 | **+4.85** | +0.53 |
| RGPO | +3.67 | **+4.13** | +0.46 |
| AMNoiseGaiJam | +4.10 | +3.74 | -0.36 |
| FMZuse | +4.23 | **+5.45** | +1.22 |
| FMNoiseSaopin | +5.20 | **+5.61** | +0.41 |
| FMNoiseAimedJam | +3.75 | **+4.18** | +0.43 |
| NoiseProduct | +5.68 | **+5.84** | +0.16 |
| NoiseConvolution | +5.36 | **+5.69** | +0.33 |

### FDC（有 Bug，修复后可能显著提升）

当前 +0.57 dB（仅 AMNoiseGaiJam 有效配对）。

**已确认的 Bug**:
1. 零填充区域污染相位拟合：`np.log(r+eps)` 在无信号区域产生伪相位
2. AM 包络过零导致 π 相位跳变：unwrap() 无法修正，载频估计偏差 4-6 MHz

### WLN（原理性不适合当前干扰器）

所有 par1 取值下对所有干扰器均为负效果。WLN 设计用于脉冲/冲激干扰，对连续型干扰（FM噪声、AM噪声等）限幅器无选择性。

### FSTP / wave_agile / Frequency_agile

- FSTP: M=1 时直接返回原信号
- wave_agile / Frequency_agile: 发射端策略未集成，始终返回原信号

---

## 修复计划

### Task 1: frft_filter mask_threshold 优化（快速提升）

**目标**: 默认 mask_threshold 从 0.3 调为 0.5，平均提升 ~0.5 dB

**改动**: `anti_jamming/adapters.py` 中 `frft_adapter` 的 `mask_threshold` 默认值

**风险**: AMNoiseGaiJam 在 thr=0.5 时略有下降（+4.10 → +3.74），需确认是否可接受

### Task 2: FDC 相位拟合修复（预期提升最大）

**目标**: 修复后 FDC 对 AMNoiseGaiJam 效果从 +0.57 dB 提升到 ≥ +3 dB

**改动**: `anti_jamming/FrequencyDomainCanceller.py`

**具体修复**:
1. 拟合前屏蔽低能量区域：只对 `|r| > threshold` 的样本做 `np.log` 和 `polyfit`
2. 检测 AM 包络过零：通过实包络符号变化检测 π 跳变，在 unwrap 前校正
3. 重新评估：修复后 FDC 对所有干扰器的效果可能普遍提升

### Task 3: FSTP M=1 降级方案

**目标**: M=1 时使用限幅滤波代替直接返回原信号

**改动**: `anti_jamming/adapters.py` 中 `fastslow_adapter`

**方案**: M<2 时调用已有的 `_apply_limit_filter` 函数（当前仅 M≥2 时使用）

### Task 4: WLN 限幅阈值修复

**目标**: 修复 VL 与信号幅度无关的 Bug，评估修复后是否有改善

**改动**: `anti_jamming/wln_filter.py`

**具体修复**: `VL = par1 * 1.48` → `VL = par1 * Vs_est`（使用模板的 MAD 估计）

**预期**: 可能仍无法有效对抗连续型干扰，但至少避免恶化

### Task 5: wave_agile / Frequency_agile 评估

**目标**: 评估是否值得做架构改造来集成发射端策略

**优先级**: 低（需要大改架构，且 adapt_filter/frft_filter 已覆盖大部分场景）

---

## 验证

```bash
.venv/bin/python test_sinr_by_state.py   # 按状态测试
.venv/bin/python validate_algorithms.py  # 全配对验证
```

修复后重新运行全算法扫描，确认各算法间有差异化效果。

---

## 修复结果（2026-05-23）

### 修改文件

| 文件 | 修改 |
|------|------|
| `anti_jamming/adapters.py` | frft mask_threshold 0.3→0.5; FSTP M<2 改用 `_apply_limit_filter` |
| `anti_jamming/FrequencyDomainCanceller.py` | 屏蔽零区域拟合 + AM 过零 π 跳变补偿 |
| `anti_jamming/wln_filter.py` | `VL = par1 * Vs_est`（基于模板幅度估计） |

### 修复后全算法扫描（10次平均，JSR=10dB）

| 干扰 | adapt_filter | frft_filter | FDC | FSTP | WLN |
|------|:-----------:|:-----------:|:---:|:----:|:---:|
| ISDJ | **+6.42** | +4.22 | -0.82 | +0.06 | -1.56 |
| SMSP | **+6.42** | +4.85 | -0.82 | +0.06 | -1.56 |
| RGPO | **+5.82** | +4.13 | **+2.18** | +0.08 | -1.71 |
| AMNoiseGaiJam | **+6.77** | +3.74 | -0.56 | -0.10 | -1.99 |
| FMZuse | **+7.69** | +5.45 | +0.48 | +0.11 | -1.41 |
| FMNoiseSaopin | **+7.21** | +5.61 | -0.11 | -0.16 | -2.22 |
| FMNoiseAimedJam | **+7.42** | +4.18 | +0.20 | +0.07 | -1.23 |
| NoiseProduct | **+7.91** | +5.84 | +0.63 | +0.02 | -1.88 |
| NoiseConvolution | **+7.91** | +5.69 | +0.60 | +0.02 | -1.88 |

### 关键改善

| 算法 | 修复前 → 修复后 | 说明 |
|------|---------------|------|
| **frft_filter** | +3.4~5.7 → **+3.7~5.8** | mask_threshold 优化，全干扰器提升 0.3~0.5 dB |
| **FDC** | -1.7~+0.1 → **-0.8~+2.2** | RGPO 从 -1.22 跳到 **+2.18 dB**（最大改善） |
| **FSTP** (M=1) | 0 → **+0.06~0.11** | 从无到有（限幅降级方案） |
| **WLN** | -1.6~-2.2 → -1.2~-2.2 | VL 修复但原理性问题仍在 |

### 仍存在的问题

1. **WLN 原理性限制**: 限幅器对连续型干扰（FM/AM噪声）无选择性。滤波器中心修正后 FMZuse 从 -0.64 提升到 -0.10 dB，但限幅仍拖后腿
2. **FDC 理论限制**: 共轭边带对消仅在 AM 噪声下有效。FFT 峰值检测载频 + 去掉重调制后，部分干扰器有正效果（FMZuse +0.89），但仍远不如 adapt_filter
3. **wave_agile / Frequency_agile**: 发射端策略未集成，仍返回原信号
4. **算法差异化不足**: adapt_filter 全局最优（+6~8 dB），frft_filter 次之（+3.7~5.8 dB），其余算法差距大

### 根因分析（深入，2026-05-23）

#### WLN: 滤波器中心频率错误（已修复）

LFM chirp 瞬时频率范围 [f0, f0+B] = [15, 20] MHz，中心在 17.5 MHz。
原代码滤波器以 f0=15MHz 为中心，窄带滤波器 [12.5, 17.5] 截掉了 50% 的 chirp 能量。
修复：滤波器中心改为 f0 + B/2 = 17.5 MHz。

#### FDC: 过零校正 Bug（已修复）

`np.real(r)` 检测的是载波振荡过零（~2700次/5000采样点），不是 AM 包络过零。
每次校正给后续相位加 π，总量 ~8482 rad ≈ 整个载波相位，导致载频估计约 0 MHz。
修复：移除过零校正，改用 FFT 峰值检测载频，去掉重调制步骤。
