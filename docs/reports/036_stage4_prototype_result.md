# Task 036 Stage 4：隔离公平原型结果

## 实现范围

Stage 4 实现并验证两个不覆盖 legacy 的原型：

- `anti_jamming.adapt_filter_fair.fit_adapt_filter_fair/apply_adapt_filter_fair`：方案 A，Top-K matched-filter 候选、可观测 margin/peak confidence、选中模板方向的保护投影；
- `anti_jamming.adapt_filter_fair.fit_adapt_filter_fair_multihypothesis/apply_adapt_filter_fair`：方案 B，多假设候选投影、observable stability score 选择。

两者均显式拆分 fit/apply。fit 返回 estimated index、confidence、filter coefficients、condition number、regularization、fit status 和 diagnostics；apply 只读取 model 与观测 IQ。禁止字段检查位于 fair 模块入口，出现 `target_idx`、`target_dist`、jammer metadata、真实 jammer signal 或 JSR metadata 即抛出受控错误。

低 confidence、零能量模板、非有限输入、错误 shape、病态/非有限输出均走 Identity fallback 或返回受控 Interface FAIL；不静默使用评价真值。legacy `anti_jamming.adapt_filter` 和 `adapt_filter_adapter` 没有被覆盖或修改。

## Smoke 矩阵

使用 jammers `NoiseProductJamming`、`NoiseConvolutionJamming`、`NoJammer`、`AMNoiseGaiJam`、`FMNoiseAimedJam`，JSR `0/10/20/30dB`，seeds `6000..6009`，目标中心 `500/1500/3500`，共 600 cases。每个 case 同时保存 Identity、当前 true-index oracle、fair A、fair B，共 2,400 rows。

## Stage 4 决策门结果

- Interface：`0` failures；
- fair oracle-input failures：`0`；
- fair TARGET_ERASED：`0`；
- NoJammer：target-only change 约 `-0.00009dB`，状态保留；
- 目标位置改变：A/B 在三位置均可运行，未完全崩溃；
- 目标 jammer：NPJ/NCJ 在 JSR=10 的三个位置均为正 Delta SINR，具备继续 calibration 的最低证据；
- 平均运行时间：A 约 `0.77ms`，B 约 `2.41ms`，仅为原型 smoke 统计；
- oracle 结果只作 upper bound，未进入 fair ranking。

A/B 在本 smoke 数据上经常选择相同的强 matched-filter 候选，不能据此宣称 B 已优于 A；两者都必须进入 calibration，并在 held-out 前冻结。

## 证据

- [prototype_metadata.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage4/prototype_metadata.json)
- [per_trial_results.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage4/per_trial_results.csv)
- [aggregate_results.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage4/aggregate_results.csv)
- [estimator_diagnostics.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage4/estimator_diagnostics.csv)
- [interface_results.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage4/interface_results.csv)
- [summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage4/summary.json)

## 未解决问题

Stage 4 只证明原型可运行、无 forbidden input、目标未被直接抹除，并非公平候选资格证明。高 JSR、false peak、位置误差和负控特异性仍需 Stage 5 calibration；calibration 通过前不运行正式 held-out。
