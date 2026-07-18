# Task 036-fix Stage D：行为去重与小规模 Calibration

## 行为签名去重

Nominal grid 共 8 个组合：A/B × `top_k={3,5}` × `confidence_threshold={0.65,0.80}` × `regularization=0.001`。固定 diagnostic bank 使用物理 fixture、8 个 jammer、JSR `0/20/30dB`、seeds `9000/9001` 和位置 `1000/2500/4000`。每个 candidate 的签名包含 estimated-target 序列、fallback 序列、量化 confidence、fit status 和归一化 processed-output hash。

结果为 `nominal_candidate_count=8`、`effective_candidate_count=4`、`equivalence_class_count=4`。实际 `top_k=3` 与 `top_k=5` 在同 threshold/design 下行为等价，不能仅因名义参数不同重复计权。完整签名见 [behavior_signatures.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageD/behavior_signatures.csv)，等价类见 [equivalence_classes.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageD/equivalence_classes.csv)。

## Calibration 设置与聚合

仅对 4 个 effective representatives 运行小规模 calibration：NPJ、NCJ、NoJammer、AMNoiseGaiJam、FMNoiseAimedJam、SMSP；JSR `0/10/20/30dB`；seeds `9000..9019`；物理位置 `1000/1500/2500/3500/4000`。每个 candidate × jammer × JSR 先跨 20 seeds × 5 positions 聚合，输出 96 个 aggregate rows；原始试验 9,600 行。每行保存 Delta SINR mean/std/CI、Identity/Fair Pd、position spread、fallback ratio、estimation error、target-only change、TARGET_ERASED、Interface 和 oracle audit。

## 资格结果

4 个 representatives 均 Interface PASS、oracle input failures=0、TARGET_ERASED=0、NoJammer target-only protection 通过，fallback ratio 为有效的非恒定 gating 结果。它们在目标 jammer 上最多只有一个不同 JSR 满足正收益/CI/Pd/position gates，均未满足“同一 jammer 至少两个不同 JSR 条件通过”的资格要求；因此 `calibration_qualified_count=0`。

排名第一的 `B_k3_c0.8_r0.001`（score `4.1921dB`，NPJ/NCJ 各 1 个 positive JSR condition）冻结为 `FROZEN_REJECTION_CONFIRMATION`，不称为 selected candidate，held-out 后不得调参或换代表。冻结信息见 [selected_candidate.json](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageD/selected_candidate.json)。

## 阶段决策

`REJECTION_CONFIRMATION_ONLY`。Stage E 只比较 Identity、legacy Oracle upper bound 和这个冻结 fair representative；资格判断必须跨 seed × position 后再按不同 JSR 条件统计，不能把 position rows 当成独立 JSR 通过数。
