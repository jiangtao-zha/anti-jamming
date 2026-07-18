# Task 037 Stage 3 — Oracle FrFT 抑制上界实验

日期：2026-07-18

状态：`COMPLETED`

阶段提交：`TBD`（由本阶段记录提交回填）

## 决策

Stage 3 Oracle upper-bound：`FAILED`。

在正式对象 `SMSP` 和 `FMNoiseSaopin` 上，使用真实 target/jammer 分量、真实分量 FrFT 能量和预注册 mask，四种阶数策略×四种 mask 共 12800 个 trial，没有任何 jammer×JSR×strategy×mask 聚合同时满足任务门槛。因此不允许进入 observable FrFT prototype；Stage 4 和 Stage 5 按决策门跳过，Stage 6 只做小规模拒绝确认，最终 FrFT candidate 与 RL 均不合格。

## 预注册 Oracle

阶数策略：

1. `true_target_optimum`：真实 target 分量 peak concentration 最优阶数；
2. `true_jammer_optimum`：真实 jammer 分量 peak concentration 最优阶数；
3. `received_only_optimum`：received 分量 peak concentration 最优阶数；
4. `fixed_theoretical_target_order`：固定 `a=1.0` 的有限网格 Fourier reference。由于 Stage 1 已明确连续 LFM 理论阶数不可由当前谱定义识别，该名称保留任务要求，但不把 `a=1.0` 宣称为连续理论真值。

Mask：

- `oracle_target_protection`：真实 target FrFT 能量累计 90% 的最小 bin 支持的硬 mask；这是对目标保护有利的乐观 Oracle。
- `oracle_jammer_rejection`：`1-0.95*sqrt(Pj/max(Pj))`；
- `oracle_ratio`：`Pt/(Pt+2*Pj+eps)`；
- `oracle_soft_wiener`：`Pt/(Pt+Pj+eps)`。

所有 mask 都在局部 1000-sample FrFT 窗口中处理，再 inverse FrFT 回到时域；真实分量没有传给正式 adapter。每一行带有 `ORACLE_DIAGNOSTIC_ONLY;NOT_FAIR;NOT_RL_ELIGIBLE`。

## 实验配置

- Seeds：`10100..10119`。
- JSR：`0/10/20/30 dB`。
- 目标中心：`1000/1500/2500/3500/4000`。
- 正式 jammer：`SMSP`、`FMNoiseSaopin`。
- 结果：800 component-recomposition cases，12800 per-trial strategy/mask rows，128 aggregate rows。

## 关键失败证据

| jammer | JSR | 该 JSR 最佳 ΔSINR mean | 95% CI 下界 | Pd after / Identity | target-only change | 位置 spread |
|---|---:|---:|---:|---:|---:|---:|
| SMSP | 10 | 0.279 dB | -0.132 dB | 0.80 / 0.80 | -1.934 dB | 6.51 dB |
| SMSP | 20 | -0.095 dB | -0.285 dB | 0.60 / 0.60 | -0.875 dB | 2.29 dB |
| SMSP | 30 | 0.056 dB | -0.165 dB | 0.60 / 0.60 | -0.875 dB | 2.35 dB |
| FMNoiseSaopin | 10 | 0.222 dB | 0.032 dB | 0.92 / 0.97 | -1.579 dB | 1.13 dB |
| FMNoiseSaopin | 20 | 0.380 dB | 0.152 dB | 0.87 / 0.97 | -1.342 dB | 2.19 dB |
| FMNoiseSaopin | 30 | 0.435 dB | 0.175 dB | 0.87 / 0.90 | -1.342 dB | 2.45 dB |

最佳策略仍然没有达到 ΔSINR mean `>1 dB`；FMNoiseSaopin 的部分 CI 下界虽然为正，但 Pd 低于 Identity 且 target-only response 损伤超过 `-1 dB`。SMSP 还出现 CI 下界为负或位置 spread 超限。没有 `TARGET_ERASED` 不能抵消其它门槛失败。

## 决策门对应关系

任务要求同时满足：至少一个 jammer、JSR 10/20/30 中至少两个、ΔSINR mean >1 dB、95% CI 下界≥0、Pd 不低于 Identity、target-only >-1 dB、无 TARGET_ERASED、位置 spread<5 dB。`qualified_rows=0`，因此：

```text
oracle_upper_bound = FAILED
candidate_matrix_eligible = false
rl_eligible = false
```

Stage 4/5 不再设计或校准任何 observable mask；这避免在 Oracle 上界都不成立时继续扩大候选空间。

## 输出与复现

结果在 `results/phase1/task037/stage3/`：

- `oracle_mask_definitions.json`
- `per_trial_results.csv`
- `aggregate_results.csv`
- `target_damage.csv`
- `oracle_upper_bound_summary.json`
- `stdout.txt` / `stderr.txt`

```bash
MPLCONFIGDIR=/tmp/task037-mpl .venv/bin/python scripts/run_task037.py --stage oracle
```
