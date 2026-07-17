# Task 036 Stage 5：Calibration 与结构筛选

## Calibration 设置

Stage 5 已完成。使用目标 jammer `NoiseProductJamming`、`NoiseConvolutionJamming`，负控 `NoJammer`、`AMNoiseGaiJam`、`FMNoiseAimedJam`、`FMNoiseSaopin`、`SMSP`，JSR `0/5/10/20/30dB`，seeds `7000..7029`，目标中心 `500/1250/2500/3750/4500`。预先去重的参数组合共 16 组（A 8 组、B 8 组），低于 40 组上限；未使用 held-out 数据调参。

每个候选保存 target/negative-control、JSR、位置聚合结果，包括 Delta SINR、95% CI、target-only response、TARGET_ERASED、fallback、estimator confidence、估计位置误差、Interface 和 oracle audit。原始候选 trial 共 `84,000` 行，聚合 `2,800` 行。

## Qualification 结果

16 个候选均 `Interface PASS`、`oracle_input_status=PASS`、`TARGET_ERASED=0`，且 NoJammer target-only change 约 `-0.00009dB`。但所有候选的行为在本 calibration 矩阵中几乎相同，目标位置鲁棒性门未通过：目标 jammer 高 JSR 条件的位置 spread 约 `10.21dB`，超过预注册的 `<5dB` 门槛；NPJ/NCJ 在 JSR=20/30 的中后部位置出现稳定负收益。候选在 JSR=0/5/10 有正收益，但这不足以证明在目标 jammer 高强度区间保持位置鲁棒。

因此：

```text
calibration_qualified_count = 0
held-out mode = rejection confirmation only
```

没有候选可以作为 fair candidate 进入性能 held-out。为完成任务规定的 held-out 失败确认，冻结 calibration ranking 第一行 `A_k3_c0.05_r0.001` 作为“最佳但未达门槛”的 rejection-confirmation prototype；该冻结对象不是 FAIR_CANDIDATE，held-out 后禁止调参或换候选。

## 证据

- [calibration_metadata.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/calibration_metadata.json)
- [parameter_search.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/parameter_search.csv)
- [candidate_ranking.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/candidate_ranking.csv)
- [selected_candidate.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/selected_candidate.json)
- [rejected_candidates.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/rejected_candidates.csv)
- [position_robustness.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/position_robustness.csv)
- [summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage5/summary.json)

## 阶段决策

Stage 6 不运行“算法性能候选选择”模式，而运行规定的拒绝确认模式：Identity、current oracle upper bound、冻结的最佳未达标 A prototype。Held-out seeds 固定为 `8000..8049`，与此前所有阶段分离。
