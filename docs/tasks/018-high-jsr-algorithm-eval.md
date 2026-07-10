# 018: 高 JSR 场景算法评测

> 优先级: **P0**
> 状态: **已完成**
> 创建: 2026-07-07
> 关联: `ROADMAP.md` P0

## 目标

在最新物理基线下重新评测高干信比场景，判断 JSR=20/30 dB 是否能拉开抗干扰算法差异，并为后续马尔可夫状态转移模型和 RL 训练选择合适场景。

最新物理基线固定为：

- `f0=15MHz`
- `Bw=5MHz`
- `Pw=20us`
- `Fs=50MHz`
- `N=5000`
- `target_dist=6000m`
- `target_idx=1500`
- `M=1`

## 实验矩阵

- JSR: `20dB`, `30dB`
- trials: 每个组合 10 次独立随机种子，默认 `seed=42 + trial * 1000`
- 干扰器: roadmap 当前 9 种干扰器
  - `ISDJ`
  - `SMSP`
  - `RGPO`
  - `FMZuse`
  - `FMNoiseAimedJam`
  - `AMNoiseGaiJam`
  - `FMNoiseSaopin`
  - `NoiseProductJamming`
  - `NoiseConvolutionJamming`
- 抗干扰算法: 当前 8 种适配器
  - `WLN`
  - `FrequencyDomainCanceller`
  - `adapt_filter`
  - `frft_filter`
  - `qpzh`
  - `FastSlowTimeProcessor`
  - `wave_agile`
  - `Frequency_agile`

## 执行前改动

新增可复现实验入口 `run_high_jsr_eval.py`：

- CLI 支持 `--jsr 20 30`, `--trials 10`, `--seed 42`, `--output-dir`
- 不依赖脚本内硬编码 JSR，所有正式结果记录命令行参数
- 固定使用最新物理基线，避免回退到旧 `Pw/Fs/target_idx`
- 对单个算法失败做记录，不中断整轮矩阵

输出文件放入独立目录，例如 `experiment_results/high_jsr_eval_20260707/`：

- `summary.csv`: 每个 `JSR × jammer × antijam` 的均值/标准差/检测率/错误数
- `summary.json`: 同样数据的结构化版本，包含配置元数据
- `summary.md`: 便于回填 `ROADMAP.md` 的 Markdown 表格

## 验收标准

- 冒烟命令 `--jsr 20 --trials 1` 可以完成并生成三种输出文件
- 正式矩阵 `JSR=20/30dB × 9干扰 × 8算法 × 10 trials` 完整产出
- 每个组合至少记录：
  - `SINR_before_mean/std`
  - `SINR_after_mean/std`
  - `SINR_improvement_mean/std/min/max`
  - `det_rate_before/after`
  - `error_count`
- 结果能明确回答：
  - 高 JSR 是否比 JSR=10dB 更能拉开算法差异
  - 每种干扰下的最佳算法是否稳定
  - 哪些干扰状态适合进入马尔可夫转移模型

## 风险与边界

- 本任务只评测算法表现，不修改算法实现。
- `M=1` 下 `FastSlowTimeProcessor` 的多脉冲优势无法体现，结果需按单脉冲限制解释。
- 暂不混入 P2 修复；如果 `decode_action` 或动作空间问题影响 RL，不在本评测任务中处理。

## 执行记录

正式命令：

```bash
.venv/bin/python run_high_jsr_eval.py \
  --jsr 20 30 --trials 10 --seed 42 \
  --output-dir experiment_results/high_jsr_eval_20260710
```

结果文件：

- `experiment_results/high_jsr_eval_20260710/summary.csv`
- `experiment_results/high_jsr_eval_20260710/summary.json`
- `experiment_results/high_jsr_eval_20260710/summary.md`

验收结果：

- 完成 `144/144` 个组合，每个组合 `10/10` 次有效试验。
- 总错误数为 `0`，CSV 共 `144` 条组合汇总记录。
- JSR=20dB 时，`adapt_filter` 在 ISDJ、SMSP、FMNoiseAimedJam、NoiseProductJamming、NoiseConvolutionJamming 上已有较明显提升；JSR=30dB 时差异进一步扩大，部分组合提升超过 `6dB`。
- RGPO 和 FMNoiseSaopin 在当前 `M=1`、评价口径下的算法差异仍较小，适合先作为弱区分状态或后续补充多脉冲评测。
- 结果支持将 ISDJ、SMSP、FMNoiseAimedJam、AMNoiseGaiJam、NoiseProductJamming、NoiseConvolutionJamming 作为优先马尔可夫状态候选；RGPO/FMNoiseSaopin 需谨慎解释，不能仅凭本次单脉冲结果断言算法不可区分。
