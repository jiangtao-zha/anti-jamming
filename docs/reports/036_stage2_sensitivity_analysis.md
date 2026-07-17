# Task 036 Stage 2：目标位置敏感性与信息泄漏实验

## 状态与数据冻结

Stage 2 已完成。实验固定每个 `jammer × JSR × seed` 生成的同一条接收 IQ，再在记录层做五个目标中心的零填充平移压力测试：`500, 1250, 2500, 3750, 4500`。这是因为当前 Phase 1 的 `get_phase1_radar_params()` 始终从 `Pw/Fs` 派生 `target_idx=1500`，改变 `target_dist` 不会移动 delay-relative 输出；该实现差异已写入 summary，不修改物理配置或 jammer 波形。

矩阵覆盖 `NoiseProductJamming`、`NoiseConvolutionJamming`、`NoJammer`、`AMNoiseGaiJam`、`FMNoiseAimedJam`、`SMSP`，JSR `0/10/20/30dB`，seeds `5000..5019`，共 `38,400` per-trial rows。每个样本比较：真实 index、`±1/±2/±4/±8/±16/±32`、固定 0、确定性随机 index 和缺失 index。真实位置仅留在 runner 的 evaluation 变量中；显式 index 注入的 rows 被标记为诊断路径，不被称为 fair 输入。

## 活跃核心等价性

完整矩阵使用 Stage 1 数学审计证明的结合律等价式：

```text
y = (r @ sᴴ) / (s sᴴ + par1) @ s
```

它与当前 active core 的 `r @ Ps` 输出相同，仅避免每个诊断 mode 物化 `5000×5000` 复矩阵。64 个 active-core spot-check rows 覆盖两个目标 jammer、两个目标中心和全部 diagnostic modes，最大归一化输出差异为 `7.77e-15`。因此全量数值是当前实现的代数等价输出；spot-check 另记录了 active core 的约 `400,258,691` bytes 矩阵内存足迹。

## 主要结果（JSR=10dB）

| 条件 | 正确 index Delta SINR | `±1` | `±4` | `-32/+32` | fixed 0 / missing | fixed/missing TARGET_ERASED |
|---|---:|---:|---:|---:|---:|---:|
| NoiseProductJamming | +21.249 | +21.251/+21.250 | +21.128/+21.087 | -3.635/-9.855 | -9.112 | 60/100 |
| NoiseConvolutionJamming | +22.859 | +22.861/+22.860 | +22.738/+22.697 | -2.025/-8.245 | -8.401 | 60/100 |
| NoJammer | +3.752 | +3.754/+3.753 | +3.631/+3.590 | -21.132/-27.352 | -25.881 | 60/100 |

这里的 aggregate group 跨五个目标位置和 20 个 seeds，共 100 trials。`±1` 与 `±4` 的 SINR 仍可能接近正确 index，但 normalized output difference 已分别约 `0.15–0.20` 和 `0.55–0.70`；`±32`、fixed 0、missing 则出现明显退化。随机 index 在目标 jammer上约 `-190dB`，并有 64/100 个 TARGET_ERASED rows。

## 多目标位置结果

真实 index 路径在五个位置未完全崩溃。NPJ JSR=10 的 Delta SINR 为约 `+21.10..+21.31dB`；NCJ 为约 `+20.32..+23.52dB`。相反，missing/fixed 0 只在前部中心 `500` 恰好对齐默认 offset 0；在中心 `1250` 已约 `-39.33dB`（NPJ）/`-37.12dB`（NCJ），在中心 `2500/3750/4500` 出现目标抹除/非有限结果。这证明默认值不是接收端估计，而是一个只对某一固定前部位置偶然成立的隐藏假设。

## 指标与接口

每个 row 保存 `target_idx_error`、Delta SINR、Pd 代理、peak error、false peak、target-only response change、TARGET_ERASED、normalized output difference、template projection coefficient difference、runtime、active matrix footprint、interface status 和异常字段。完整结果见：

- [per_trial_results.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage2/per_trial_results.csv)
- [aggregate_by_offset.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage2/aggregate_by_offset.csv)
- [aggregate_by_target_position.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage2/aggregate_by_target_position.csv)
- [active_core_equivalence_spot_check.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage2/active_core_equivalence_spot_check.csv)
- [oracle_dependency_summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage2/oracle_dependency_summary.json)
- [summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage2/summary.json)

## Stage 2 决策门

结论为 `ORACLE_DEPENDENCE_CONFIRMED`：当前算法收益和目标保护均高度依赖正确的模板时移；缺失 index 的内部默认值会形成固定位置假设；错误位置在大偏移、多位置和 NoJammer 条件下可导致负收益或目标抹除。Stage 3 仍必须提出至少三种 observable-only 公平设计，并决定是否有方案值得隔离原型；不得把当前正确-index结果直接纳入公平排名。

## 未修改范围

本阶段未修改 `anti_jamming/adapt_filter.py`、adapter、jammer、JSR 定义、评价契约、RL 环境、PPO、reward、state 或 action space。新增的 `scripts/task036_stage2_sensitivity.py` 仅为诊断复现入口。
