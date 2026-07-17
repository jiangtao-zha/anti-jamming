# Task 036 Stage 6：Held-out 拒绝确认

## 实验边界

Stage 5 未产生满足预注册门槛的 fair candidate，因此 Stage 6 按“拒绝确认”模式运行，不进行候选选择。冻结对象为 `A_k3_c0.05_r0.001`，候选文件 SHA-256 为 `8239f488543210984c1b87b554e10ada3d1dff73f63f105a83d36534a214be50`，来源 commit 为 `b623a01`。Held-out seeds 为 `8000..8049`，目标中心为 `500/1250/2500/3750/4500`，JSR 为 `0/10/20/30dB`，与 calibration 完全分离；held-out 后未调参、未换候选。

比较对象为 Identity、保留的 legacy `adapt_filter`（仅作带真值 target_idx 的 Oracle upper bound）和冻结的 observable-only A prototype。Fair 输入只包含公开 radar 参数、IQ 记录和模板；Oracle 的目标保真度使用独立的纯目标输入计算，避免把 jammer 场景输出误当作目标参考。

## 结果

共完成 `8 × 4 × 50 × 5 × 3 = 24,000` 个逐对象结果（CSV 含表头 24,001 行），所有比较对象的接口失败数为 0；Fair 的 `TARGET_ERASED=0`、fallback=0，NoJammer target-only response change 均值为 `-8.6859e-06dB`。Oracle 的独立目标保真统计也为 `TARGET_ERASED=0`，均值约 `-8.6858e-05dB`。

目标 jammer 的 Delta SINR（跨五个位置的均值；括号为位置最小/最大值）如下：

| jammer | JSR | Identity | Oracle upper bound | 冻结 Fair A |
|---|---:|---:|---:|---:|
| NPJ | 10 | 0.000 | 21.601 | 19.397 (18.148/20.260) |
| NPJ | 20 | 0.000 | 28.104 | -8.845 (-13.473/6.413) |
| NPJ | 30 | 0.000 | 29.875 | -12.279 (-17.613/2.499) |
| NCJ | 10 | 0.000 | 22.275 | 21.085 (18.232/22.309) |
| NCJ | 20 | 0.000 | 28.888 | -10.239 (-15.092/2.878) |
| NCJ | 30 | 0.000 | 30.422 | -15.166 (-17.642/-6.457) |

Fair 在 JSR=10dB 仍有正收益，但在 JSR=20/30dB 的目标 jammer 条件普遍转为负收益；位置 spread 为 `12.5568dB`，超过预注册 `<5dB` 门槛。负控也未发现目标-only 损伤，但这不能抵消目标 jammer 高 JSR 和位置鲁棒性失败。

## 阶段决策

`ORACLE_UPPER_BOUND_ONLY`。当前 legacy `adapt_filter` 只能作为 Oracle upper bound / research baseline 保留；冻结 Fair prototype 不具备进入 RL action registry 或 candidate matrix 的资格。fallback 仍为 Identity，未修改 jammer、评估契约、RL/PPO、reward、state 或 action space。

## 证据

- [summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage6/summary.json)
- [per_trial_results.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage6/per_trial_results.csv)
- [aggregate_results.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage6/aggregate_results.csv)
- [oracle_upper_bound_comparison.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage6/oracle_upper_bound_comparison.csv)
- [position_robustness.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage6/position_robustness.csv)
