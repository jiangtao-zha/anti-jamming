# Task 036 Stage 7：最终集成决策

## 决策

最终决策为 `ORACLE_UPPER_BOUND_ONLY`。当前 `adapt_filter` 保留为带明确标签的 legacy Oracle upper bound / research baseline；`adapt_filter_fair.py` 保留为隔离研究原型，但未成为 `FAIR_CANDIDATE`，不进入 RL candidate matrix，也不注册到 action registry。

## 原因

Stage 1–2 已证明 legacy 路径依赖目标对齐信息 `target_idx`。Stage 5 没有 calibration-qualified candidate；Stage 6 在完全冻结的 held-out 集合上确认，Fair A 在 JSR=20/30dB 的目标 jammer 条件下出现负收益，位置 spread 为 `12.5568dB`，超过 `<5dB` 门槛。虽然 Fair target-only protection、NoJammer 控制和接口门通过，但不足以支持 RL 纳入。

## 集成范围

本阶段没有改动 jammer、评估契约、FDC、WLN、FrFT、qpzh、FSTP、RL/PPO、reward、state 或 action space。现有 registry 中的 legacy `adapt_filter` 未被静默升级为 fair 实现；任何未来删除或重标该 Oracle action 的工作必须另开任务审查。observable-only fallback 为 Identity。

## 证据

- [final_decision.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage7/final_decision.json)
- [registry_status.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage7/registry_status.json)
- [036_stage6_heldout_result.md](/Users/jiangtao/anti_jamming/docs/reports/036_stage6_heldout_result.md)
