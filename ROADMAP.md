# ROADMAP.md — Agent 项目状态与任务路线图

> Agent 启动必读：CLAUDE.md（规则）+ 本文件（状态+任务）。
> 人类详细文档：`README.md`、`algorithm_docs/`、`docs/tasks/`。

---

## 一、当前基线（JSR=10dB, M=1, 10次平均）

无干扰基准：SINR ≈ 11.40 dB，检测率 100%。

| # | 干扰 | 抗干扰 | SINR前→后 | 检测前→后 | 状态 |
|---|------|--------|----------|----------|------|
| 1 | NoiseConvolutionJamming | adapt_filter | 3.85→11.46 (+7.61) | 0→100% | 优秀 |
| 2 | NoiseProductJamming | adapt_filter | 3.85→11.46 (+7.61) | 0→100% | 优秀 |
| 3 | FMNoiseAimedJam | frft_filter | 4.46→8.34 (+3.88) | 0→40% | 良好 |
| 4 | FMZuse | WLN | 1.43→3.44 (+2.01) | 0→0% | 微弱 |
| 5 | AMNoiseGaiJam | FDC | 3.75→4.09 (+0.35) | 0→0% | 微弱 |
| 6 | RGPO | wave_agile | 4.90→4.90 (+0.00) | 0→0% | 无效果 |
| 7 | SMSP | FastSlowTimeProcessor | 4.90→4.90 (+0.00) | 0→0% | 无效果 |
| 8 | FMNoiseSaopin | Frequency_agile | 1.83→1.83 (+0.00) | 0→0% | 无效果 |
| 9 | SliceCombineJam | FastSlowTimeProcessor | 2.38→2.38 (+0.00) | 0→0% | 无效果 |
| 10 | ISDJ | FastSlowTimeProcessor | -157→-157 (+0.00) | 0→0% | 目标淹没 |

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

### 适配器参数映射（RL→算法）

| 算法 | RL连续参数 | 实际被使用 | 问题 |
|------|-----------|-----------|------|
| WLN | par1 [0.1, 2.5] | 是 | par2 固定为6 |
| FDC | use_fitted [0,1] | 是（二值） | decode_action 硬编码 f0=40e6 |
| adapt_filter | par1 [-1, 1] | 是 | — |
| frft_filter | a1 [0.8,1.2], w [20,200] | **否，全部忽略** | 适配器自动扫描阶数 |
| qpzh | m [2,10], n [2,8] | 是 | — |
| FSTP | limit_factor [1.5,5] | M=1时直接返回原信号 | — |

### CA-CFAR 检测器

- 公式：`alpha = sqrt(-4·ln(Pfa)/π)`，Pfa=1e-4 → alpha=3.42
- 幅度域（非功率域），guard_cells=4, ref_cells=20

### 测试框架限制

- M=1（单脉冲）：FSTP/wave_agile/frequency_agile 均需要 M≥2
- ISDJ 在 M=1 下 SINR=-157dB（DRFM完全覆盖目标）

---

## 四、待办项（按优先级）

### P0：RL 基础修复（无回退风险）

- [ ] **015 RL 动作空间同步**：frft_filter 参数被忽略，需更新 `rl_framework/config.py`
- [ ] **修复 decode_action FDC f0**：`rl_framework/utils.py` 硬编码 f0=40e6，应为 15e6

### P1：CPPO 优势提升

- [ ] **014 CPPO vs stdPPO 深入优化**：CNN 架构、信号表示、训练策略
- [ ] CNN 过度压缩修复（1024→2 太少）
- [ ] z-score → 幅度保留归一化
- [ ] 增加训练轮数，独立保存 CPPO/stdPPO checkpoint

### P2：信号处理改进

- [ ] **013 WLN 自适应阈值**（+2.01 dB → 目标 ≥3dB）
- [ ] **012 FDC 算法重写**（+0.35 dB → 目标 ≥2dB）

### P3：架构性改动

- [ ] **011 多脉冲测试框架**（M≥2，解决5组无效配对）
- [ ] **010 ISDJ 抗干扰**（依赖011）

---

## 五、已完成

- [x] **001** ISDJ 配对修正（Frequency_agile → FastSlowTimeProcessor）
- [x] **002** frft_filter 重写（全长度模板扫描 + 阈值掩膜，+0.00 → +4.46 dB）
- [x] **003** FSTP/ISDJ M=1 保护（消除 -1.97 dB 恶化）
- [x] **004** WLN 默认参数优化（par1 0.6→0.3）
- [x] **005** FDC 载频修正（使用 radar_par 中的实际载频）
- [x] **006** CA-CFAR alpha 公式修正（幅度域正确公式）
- [x] **007** RL 检测奖励阈值修正（`sinr_after > 5.0 dB`）

---

*最后更新：2026-05-19*
