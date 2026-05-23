# ROADMAP.md — Agent 项目状态与任务路线图

> Agent 启动必读：CLAUDE.md（规则）+ 本文件（状态+任务）。
> 人类详细文档：`README.md`、`algorithm_docs/`、`docs/tasks/`。

---

## 一、当前基线（JSR=10dB, M=1, Fs=50MHz, 10次平均）

无干扰基准：SINR ≈ 11.40 dB，检测率 100%。

### 采样率修复后的基线（2026-05-23 更新）

| # | 干扰 | 抗干扰 | SINR前→后 | 检测前→后 | 状态 |
|---|------|--------|----------|----------|------|
| 1 | NoiseConvolutionJamming | adapt_filter | 3.33→11.46 (+8.13) | 0→100% | 优秀 |
| 2 | NoiseProductJamming | adapt_filter | 3.33→11.46 (+8.13) | 0→100% | 优秀 |
| 3 | FMNoiseAimedJam | frft_filter | 4.33→7.63 (+3.30) | 0→20% | 良好 |
| 4 | FMZuse | WLN | 2.83→1.86 (-0.97) | 0→0% | 恶化 |
| 5 | AMNoiseGaiJam | FDC | 4.28→4.85 (+0.57) | 0→0% | 微弱 |
| 6 | RGPO | wave_agile | 5.48→5.48 (+0.00) | 0→0% | 无效果 |
| 7 | SMSP | FastSlowTimeProcessor | 5.09→5.09 (+0.00) | 0→5% | 无效果 |
| 8 | FMNoiseSaopin | Frequency_agile | 3.45→3.45 (+0.00) | 0→0% | 无效果 |
| 9 | ISDJ | FastSlowTimeProcessor | 5.09→5.09 (+0.00) | 5%→5% | 无效果 |
| 10 | SliceCombineJam | FastSlowTimeProcessor | — | — | 未测 |

### adapt_filter 全局最优发现（2026-05-23）

**adapt_filter（子空间投影）对所有 9 种干扰器均为最优算法**（+5.82 ~ +7.91 dB, 100% 检测率）。

| 干扰 | adapt_filter | frft_filter(2nd) | 当前配对算法 |
|------|:-----------:|:----------------:|:----------:|
| ISDJ | **+6.42 dB** | +3.43 dB | FSTP: 0 |
| SMSP | **+6.42 dB** | +4.32 dB | FSTP: 0 |
| RGPO | **+5.82 dB** | +3.67 dB | wave_agile: 0 |
| AMNoiseGaiJam | **+6.77 dB** | +4.10 dB | FDC: +0.57 |
| FMZuse | **+7.69 dB** | +4.23 dB | WLN: -0.97 |
| FMNoiseSaopin | **+7.21 dB** | +5.20 dB | Frequency_agile: 0 |
| FMNoiseAimedJam | **+7.42 dB** | +3.75 dB | frft_filter: +3.30 |
| NoiseProduct | **+7.91 dB** | +5.68 dB | adapt_filter: +8.13 |
| NoiseConvolution | **+7.91 dB** | +5.36 dB | adapt_filter: +8.13 |

**对马尔可夫模型的影响**: 所有状态可达性问题直接解决，但 RL 策略学习可能过于平凡（agent 永远选 adapt_filter）。详见 `docs/tasks/016-fix-antijam-for-markov.md`。

---

## 二、RL 训练状态

训练配置：300 episodes × 8 steps/episode，JSR=10dB，6种算法可选。

| 指标 | CPPO (CNN+one-hot) | stdPPO (仅one-hot) | 差值 |
|------|-------------------|-------------------|------|
| 最终10轮 Reward | 11.49 | 9.95 | +1.54 |
| 最终10轮 SINR改善 | 10.99 dB | 9.45 dB | +1.54 dB |
| 最终10轮 检测率 | 98.75% | 91.25% | +7.5% |

### CPPO vs stdPPO 架构差异

唯一区别在 FeatureExtractor：
- CPPO：1D-CNN(IQ 2×1024) → 247维 + one-hot 9维 = 256维
- stdPPO：MLP(one-hot 9→128→128→256) = 256维
- Actor/Critic 完全相同，都输出离散动作 + 连续参数

### CPPO 优势不明显的原因

1. **参数空间失效**：frft_filter 适配器自动扫描阶数，RL 的 a1/w 参数被忽略；FDC decode_action 硬编码 f0=40e6
2. **CNN 过度压缩**：1024点输入→~2点输出（4层 stride+pooling），丢失99.8%时间信息
3. **z-score 归一化**：破坏幅度信息，CNN 无法区分干扰强度
4. **Checkpoint 覆盖**：所有保存的 .pt 文件都是 stdPPO（jammer_only），CPPO 模型权重已丢失

---

## 三、关键架构事实

### 采样率修复（2026-05-23 完成）

- 9个干扰器 `__init__` 添加 `Fs=None` 参数，传入雷达 Fs
- `JammerLoader.DEFAULT_RADAR_PARAMS` 添加 `Fs=50e6`
- `rl_framework/environment.py` 传入 `cfg.Fs`
- ISDJ SINR_before 从 -157dB 恢复到 +5dB

### 适配器参数映射（RL→算法）

| 算法 | RL连续参数 | 实际被使用 | 问题 |
|------|-----------|-----------|------|
| WLN | par1 [0.1, 2.5] | 是 | 对 FMZuse 效果为负 |
| FDC | use_fitted [0,1] | 是（二值） | 相位拟合被零填充区破坏 |
| adapt_filter | par1 [-1, 1] | 是 | 全局最优，可能过于强势 |
| frft_filter | a1 [0.8,1.2], w [20,200] | **否，全部忽略** | 适配器自动扫描阶数 |
| qpzh | m [2,10], n [2,8] | 是 | — |
| FSTP | limit_factor [1.5,5] | M=1时直接返回原信号 | — |
| wave_agile | — | **否** | 发射端策略，radar_par['wave_radar']从未设置 |
| Frequency_agile | — | **否** | 同上 |

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

### 状态-干扰映射与可达性（采样率修复后）

| 状态 | 干扰 | 当前配对 | 当前效果 | adapt_filter效果 | 能推进？ |
|------|------|---------|---------|-----------------|---------|
| S1 | ISDJ | FSTP | 0 dB | **+6.42 dB, 100%** | 能(换配对) |
| S1 | SMSP | FSTP | 0 dB | **+6.42 dB, 100%** | 能(换配对) |
| S2 | RGPO | wave_agile | 0 dB | **+5.82 dB, 100%** | 能(换配对) |
| S3 | FMNoiseAimedJam | frft_filter | +3.30 dB | **+7.42 dB, 100%** | 能 |
| S3 | AMNoiseGaiJam | FDC | +0.57 dB | **+6.77 dB, 100%** | 能(换配对) |
| S4 | FMZuse | WLN | -0.97 dB | **+7.69 dB, 100%** | 能(换配对) |
| S4 | FMNoiseSaopin | Frequency_agile | 0 dB | **+7.21 dB, 100%** | 能(换配对) |
| S5 | NoiseProduct | adapt_filter | +8.13 dB | +8.13 dB | 能 |
| S5 | NoiseConvolution | adapt_filter | +8.13 dB | +8.13 dB | 能 |

### Reward 设计（已确定）

```
R_total = R_dense + R_step + R_progress + R_terminal

R_dense:     SINR改善 × 1.0  (上限3次/状态，允许负值)
R_step:      -1.0 / 步        (能量惩罚，驱动速度)
R_progress:  新最高状态 × 3.0  (只认新纪录，防震荡)
R_terminal:  +15.0            (到达 S6)
```

### 待解决

- **配对策略**: adapt_filter 全局最优，但会导致 RL 策略过于平凡
- **r_t 跨状态不可比**: 不同状态 SINR 改善范围差异大（+5.8 ~ +8.1 dB）
- 详细设计: `docs/rl_state_transition_discussion.md`

---

## 五、待办项（按优先级）

### P0：修复和提升其他抗干扰算法（已完成）

> 详见 `docs/tasks/017-fix-antijam-algorithms.md`

- [x] **Task 1: frft_filter mask_threshold 优化**（0.3→0.5，全干扰器提升 ~0.3-0.5 dB）
- [x] **Task 2: FDC 相位拟合修复**（屏蔽零区域 + AM 过零处理，RGPO: -1.22→+2.18 dB）
- [x] **Task 3: FSTP M=1 降级方案**（M<2 时调用 `_apply_limit_filter`，0→+0.06 dB）
- [x] **Task 4: WLN 限幅阈值修复**（`VL = par1 * Vs_est`，原理性问题仍在）

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

- [x] **001** ISDJ 配对修正（Frequency_agile → FastSlowTimeProcessor）
- [x] **002** frft_filter 重写（全长度模板扫描 + 阈值掩膜，+0.00 → +4.46 dB）
- [x] **003** FSTP/ISDJ M=1 保护（消除 -1.97 dB 恶化）
- [x] **004** WLN 默认参数优化（par1 0.6→0.3）
- [x] **005** FDC 载频修正（使用 radar_par 中的实际载频）
- [x] **006** CA-CFAR alpha 公式修正（幅度域正确公式）
- [x] **007** RL 检测奖励阈值修正（`sinr_after > 5.0 dB`）
- [x] **马尔可夫模型设计**：5状态降级链 + Reward 4组件 + Episode 方案 C
- [x] **016 根因分析**：确认全局采样率不匹配是核心系统性问题
- [x] **D类修复**：采样率不匹配修复（干扰器 Fs 对齐到雷达 Fs）
- [x] **全算法扫描**：发现 adapt_filter 对所有干扰器均为最优算法
- [x] **017 算法修复**：frft_filter 优化 + FDC 相位修复 + FSTP M=1 降级 + WLN 阈值修复

---

*最后更新：2026-05-23*
