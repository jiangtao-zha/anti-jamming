# Task 037 Stage 2 — FrFT 域分量聚集与可分离性诊断

日期：2026-07-18

状态：`COMPLETED`

阶段提交：`4475ac1`（`phase1-037-stage2-frft-separability-diagnostics`）

Git 分支：`algorithm_design_0711`

## 结论

Stage 2 Gate：`PASS_TO_STAGE3_ORACLE_DIAGNOSTIC`。

在任务指定的正式对象 `SMSP` 和 `FMNoiseSaopin` 上，目标和干扰的 FrFT 最优阶数在粗网格上表现出稳定差异；这只证明“值得做 Oracle 上界实验”，不证明可观测 mask 或 RL 资格。Stage 2 没有调用任何抗干扰 adapter，也没有把真实分量传给算法。

## 实验冻结

- Seeds：`10000..10029`。
- JSR：`0/10/20/30 dB`。
- 目标中心：`1000/1500/2500/3500/4000`。
- 正式 jammer：`SMSP`、`FMNoiseSaopin`。
- 补充 jammer：`NoiseProductJamming`、`NoiseConvolutionJamming`、`NoJammer`、`AMNoiseGaiJam`、`FMNoiseAimedJam`、`FMZuse`；补充结果不作为正式公平结论。
- 物理 fixture：复用 Task 036-fix 的 component-recomposition fixture；每个 jammer×JSR×seed 的 noise realization 在五个目标位置复用，位置只按 fixture policy 重组 target/相关 jammer component。
- 诊断窗口：当前 FrFT adapter 使用的 1000-sample 活动窗口，以目标中心为中心提取；窗口 `[center-500:center+500]`，仅用于 runner 内的真值分量诊断。
- 阶数网格：`[-1.0,1.0]`，step `0.02`；阶差使用 `d4(a,b)=min_k |a-b+4k|`。
- 指标：peak concentration、Top-10 concentration、spectral entropy、support90、half-power peak width；最优阶数分别按 peak/Top-10/entropy 记录。

## 主要结果

`separability_summary.json` 汇总了 4800 个 component-recomposition cases，正式分量阶数曲线共 484800 行。

| 正式 jammer | peak 阶差 median（JSR 10/20/30 聚合） | peak 阶差 q25 | 域重叠 median | 初步判断 |
|---|---:|---:|---:|---|
| SMSP | 1.90 | 1.90 | 0.000 | order/spatial gate PASS |
| FMNoiseSaopin | 1.90 | 1.90 | 0.000 | order/spatial gate PASS |

正式门槛是 median order gap `>0.08`、q25 `>0.04`、overlap `<0.5`；两个正式对象均满足，因此进入 Stage 3 Oracle upper-bound。结果仍标记为 diagnostic-only，不改变算法资格。

补充诊断也写入相同结果目录的 `order_gap_summary.csv`、`domain_overlap.csv` 和 `position_robustness.csv`，但不和正式对象混合聚合。

## 数据边界与解释

1. `target/jammer/noise/received` 真值分量只存在于 Stage 2 runner；没有传入 `frft_adapter` 或任何正式算法。
2. 阶数最优值按周期距离统计，避免把 `-1` 与 `1` 的边界误判成普通距离。
3. 同一 seed 的五个位置共享完整 noise hash；位置鲁棒性在 `position_robustness.csv` 中单独展开。
4. 这是域内结构诊断，不包含处理后 SINR、Pd 或 target-preservation 资格判断；这些只能由 Stage 3 Oracle 和后续 held-out 决定。

## 输出

结果保存于 `results/phase1/task037/stage2/`：

- `per_order_metrics.csv`
- `optimal_orders.csv`
- `order_gap_summary.csv`
- `domain_overlap.csv`
- `position_robustness.csv`
- `separability_summary.json`
- `stdout.txt` / `stderr.txt`

## 复现

```bash
MPLCONFIGDIR=/tmp/task037-mpl .venv/bin/python scripts/run_task037.py --stage separability
```

阶段目录非空时 runner 默认拒绝覆盖；本次正式重跑因修正了错误的 Task 036 formal jammer 分组，使用了显式 `--overwrite`，最终结果只以本报告列出的 `SMSP/FMNoiseSaopin` 分组为准。
