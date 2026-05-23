# ROADMAP.md — Agent 项目状态与任务路线图

> Agent 启动必读：CLAUDE.md（规则）+ 本文件（状态+任务）。
> 人类详细文档：`README.md`、`algorithm_docs/`、`docs/tasks/`。

---

## 一、当前基线（JSR=10dB, M=1, Fs=50MHz, 5次平均）

### 目标索引修复后的基线（2026-05-23 v2 更新）

**关键修复**: target_idx 从 2500 修正为 1500（干扰器时间轴从 2R/C 开始，信号中心在 1.5·Pw·Fs）；JammerLoader.T 从 24μs 修正为 20μs 匹配 Pw。

修复后基线 SINR ≈ 10~11 dB（全部检测成功），原因是匹配滤波器对 LFM chirp 提供 ~20 dB 处理增益，JSR=10 dB 时输出 SINR ≈ 10 dB。

### 抗干扰算法评测结果

| 算法 | 平均 SINR 改善 | 最佳 | 最差 | 分析 |
|------|:-----------:|:----:|:----:|------|
| adapt_filter | **+0.43 dB** | +1.46 | -0.02 | 子空间投影，最佳 |
| wave_agile | **+0.21 dB** | +0.33 | +0.07 | 脉压域滤波，稳定正向 |
| frft_filter | -0.03 dB | +0.19 | -0.29 | FrFT 域掩膜，近中性 |
| FSTP | -0.03 dB | -0.02 | -0.04 | 频谱减法降级，近中性 |
| qpzh | ±0.00 dB | 0.00 | 0.00 | 分段频谱处理，无影响 |
| Frequency_agile | -0.08 dB | +0.02 | -0.62 | 频谱凹陷，微弱负面 |
| FDC | -0.22 dB | +0.22 | -1.29 | 频域对消，微弱负面 |
| WLN | -0.15 dB | +0.49 | -0.62 | 宽限窄滤波，微弱负面 |

### 按干扰器×算法矩阵（SINR 改善 dB）

| 算法\干扰 | ISDJ | SMSP | RGPO | FMZuse | FMNAJ | AMNGJ | FMNSp | NPJ | NCJ |
|----------|:----:|:----:|:----:|:------:|:-----:|:-----:|:-----:|:---:|:---:|
| adapt_filter | +0.31 | +0.39 | +0.28 | +0.10 | +0.47 | -0.02 | +0.01 | **+1.46** | +0.89 |
| wave_agile | +0.30 | +0.15 | +0.33 | +0.30 | +0.10 | +0.10 | +0.33 | +0.07 | +0.18 |
| frft_filter | -0.05 | -0.04 | -0.01 | -0.09 | +0.02 | -0.29 | -0.08 | +0.19 | +0.10 |
| FSTP | -0.02 | -0.02 | -0.02 | -0.03 | -0.04 | -0.02 | -0.03 | -0.02 | -0.03 |
| qpzh | ±0.00 | ±0.00 | ±0.00 | ±0.00 | ±0.00 | ±0.00 | ±0.00 | ±0.00 | ±0.00 |
| Frequency_agile | -0.62 | -0.02 | -0.02 | -0.02 | -0.00 | -0.04 | -0.02 | -0.00 | +0.02 |
| FDC | -1.29 | +0.22 | -0.09 | -0.08 | -0.03 | -0.17 | -0.17 | +0.11 | -0.44 |
| WLN | -0.38 | -0.62 | -0.35 | -0.03 | -0.16 | -0.09 | -0.08 | +0.49 | -0.09 |

### 基线 SINR（匹配滤波后，无抗干扰处理）

| 干扰 | SINR | 检测 |
|------|:----:|:----:|
| FMNoiseSaopin | +11.45 dB | ✓ |
| FMZuse | +11.37 dB | ✓ |
| ISDJ | +11.23 dB | ✓ |
| RGPO | +11.20 dB | ✓ |
| AMNoiseGaiJam | +11.17 dB | ✓ |
| SMSP | +11.13 dB | ✓ |
| NoiseConvolutionJamming | +11.05 dB | ✓ |
| FMNoiseAimedJam | +10.80 dB | ✓ |
| NoiseProductJamming | +10.37 dB | ✓ |

### 物理分析

匹配滤波器对 LFM chirp 的处理增益 = Pw × Bw = 20μs × 5MHz = 100 (20 dB)。JSR=10 dB 时：
- 输入 SINR ≈ -10 dB（干扰功率 = 10× 信号功率）
- 匹配滤波后 SINR ≈ -10 + 20 = +10 dB（远高于检测门限）

频域线性滤波（带通/陷波）无法进一步提升 SINR，因为匹配滤波器已最优地抑制带外干扰。子空间投影（adapt_filter）利用信号相位结构可获得少量额外增益。

**结论**: JSR=10 dB、单脉冲条件下，抗干扰算法的改善空间有限（≤1 dB）。更高的 JSR 或多脉冲处理会扩大算法差异。

---

## 二、RL 训练状态

训练配置：300 episodes × 8 steps/episode，JSR=10dB，6种算法可选。

| 指标 | CPPO (CNN+one-hot) | stdPPO (仅one-hot) | 差值 |
|------|-------------------|-------------------|------|
| 最终10轮 Reward | 11.49 | 9.95 | +1.54 |
| 最终10轮 SINR改善 | 10.99 dB | 9.45 dB | +1.54 dB |
| 最终10轮 检测率 | 98.75% | 91.25% | +7.5% |

> **注意**: 上述 RL 训练结果基于旧的 target_idx（2500），修正后基线 SINR 显著提高，需要重新训练。

### CPPO vs stdPPO 架构差异

唯一区别在 FeatureExtractor：
- CPPO：1D-CNN(IQ 2×1024) → 247维 + one-hot 9维 = 256维
- stdPPO：MLP(one-hot 9→128→128→256) = 256维
- Actor/Critic 完全相同，都输出离散动作 + 连续参数

---

## 三、关键架构事实

### target_idx 修复（2026-05-23 v2）

- 干扰器时间轴 t1 从 2R/C 开始，信号出现在 td∈[T,2T)，中心在 1.5·Pw·Fs = 1500
- 旧公式 `range_bin + Npw//2 = 2500` 错误地包含绝对时延，现已修正
- 同时修正 JammerLoader.T = 20μs（原 24μs），使模板与信号匹配

### 采样率修复（2026-05-23 完成）

- 9个干扰器 `__init__` 添加 `Fs=None` 参数，传入雷达 Fs
- `JammerLoader.DEFAULT_RADAR_PARAMS` 添加 `Fs=50e6`
- `rl_framework/environment.py` 传入 `cfg.Fs`

### 适配器参数映射（RL→算法）

| 算法 | RL连续参数 | 实际被使用 | 备注 |
|------|-----------|-----------|------|
| WLN | par1 [0.1, 2.5] | 是 | μ律软限幅+宽/窄带通 |
| FDC | cancellation_strength | 是 | 频域对消（重写为Wiener式） |
| adapt_filter | par1 [-1, 1] | 是 | 正则化因子 |
| frft_filter | mask_threshold | 是 | FrFT 软掩膜阈值 |
| qpzh | m, n | 是 | 分段数和阈值系数 |
| FSTP | limit_factor | M≥2时使用 | M=1降级为频谱减法 |
| wave_agile | — | 是 | 脉压域滤波（已重写） |
| Frequency_agile | — | 是 | 频谱凹陷（已重写） |

### CA-CFAR 检测器

- 公式：`alpha = sqrt(-4·ln(Pfa)/π)`，Pfa=1e-4 → alpha=3.42
- 幅度域（非功率域），guard_cells=4, ref_cells=20

---

## 四、马尔可夫状态转移模型（设计中）

### 模型概览

干扰机根据抗干扰效果 r_t 动态降级，agent 目标是推动干扰从 S1 降级到 S6（放弃）。

```
S1(精准欺骗) → S2 → S3(瞄准压制) → S4(覆盖压制) → S5(信号污染) → S6(放弃)
```

### 状态-干扰映射（修正后基线）

| 状态 | 干扰 | 最佳算法 | SINR 改善 |
|------|------|---------|:---------:|
| S1 | ISDJ | adapt_filter | +0.31 dB |
| S1 | SMSP | adapt_filter | +0.39 dB |
| S2 | RGPO | adapt_filter | +0.28 dB |
| S3 | FMNoiseAimedJam | adapt_filter | +0.47 dB |
| S3 | AMNoiseGaiJam | adapt_filter | -0.02 dB |
| S4 | FMZuse | adapt_filter | +0.10 dB |
| S4 | FMNoiseSaopin | wave_agile | +0.33 dB |
| S5 | NoiseProduct | adapt_filter | +1.46 dB |
| S5 | NoiseConvolution | adapt_filter | +0.89 dB |

> **注意**: JSR=10 dB 时算法差异很小。马尔可夫模型需在更高 JSR（如 20~30 dB）下评估，以拉开算法差距。

---

## 五、待办项（按优先级）

### P0：高 JSR 场景算法评测

- [ ] 在 JSR=20/30 dB 下重新评测，验证算法在高干扰下的差异化表现
- [ ] 重新训练 RL 模型（基于修正后的 target_idx）

### P1：马尔可夫模型实现

- [ ] 环境改造: `rl_framework/environment.py` 支持状态转移
- [ ] 配置扩展: `rl_framework/config.py` 新增状态映射和转移参数
- [ ] 训练验证: CPPO vs stdPPO 在马尔可夫环境下的对比

### P2：RL 基础修复

- [ ] **015 RL 动作空间同步**：frft_filter 参数被忽略，需更新 `rl_framework/config.py`
- [ ] **修复 decode_action FDC f0**：`rl_framework/utils.py` 硬编码 f0=40e6，应为 15e6

### P3：CPPO 优势提升

- [ ] CNN 过度压缩修复（1024→2 太少）
- [ ] z-score → 幅度保留归一化

---

## 六、已完成

- [x] **target_idx 修复**：从 2500 修正为 1500，基线 SINR 从 ~3-5 dB 修正为 ~10-11 dB
- [x] **T/Pw 一致性修复**：JammerLoader.T 从 24μs 修正为 20μs，模板与信号匹配
- [x] **001** ISDJ 配对修正
- [x] **002** frft_filter 重写（软掩膜，mask_threshold=0.1）
- [x] **003** FSTP M=1 保护（温和频谱减法降级）
- [x] **004** WLN 参数优化（μ律软限幅 + 宽窄带通 1.5×B）
- [x] **005** FDC 重写（Wiener式频域对消替代基带解调）
- [x] **006** CA-CFAR alpha 公式修正（幅度域正确公式）
- [x] **007** RL 检测奖励阈值修正
- [x] **马尔可夫模型设计**：5状态降级链 + Reward 4组件 + Episode 方案 C
- [x] **016 根因分析**：确认全局采样率不匹配是核心系统性问题
- [x] **D类修复**：采样率不匹配修复（干扰器 Fs 对齐到雷达 Fs）
- [x] **017 算法修复**：所有算法不再严重恶化信号（±0.5 dB 以内）
- [x] **wave_agile/Frequency_agile 重写**：从发射端策略改为接收端处理
- [x] **qpzh 重写**：分段频谱处理（8段，基于模板能量比）

---

*最后更新：2026-05-23 v2*
