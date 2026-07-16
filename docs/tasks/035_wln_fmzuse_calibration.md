# Task 035：WLN ↔ FMZuse 专用算法校准

本任务只校准 WLN 与 FMZuse 的匹配关系。禁止修改 jammer、JSR、Phase 1 evaluation contract、其他抗干扰算法和 RL。

## 阶段门禁

1. 先审计 `anti_jamming/wln_filter.py` 与 WLN adapter，冻结 Current WLN。
2. calibration seeds 使用 `1000..1019`，held-out seeds 使用 `2000..2049`，不得混用。
3. 参数搜索不超过 30 组，保存全部组合；held-out 候选冻结后只运行一次。
4. 正式 FMZuse 使用 JSR `0/10/20/30`；负控使用 AMNoiseGaiJam、FMNoiseAimedJam、FMNoiseSaopin、SMSP、NoiseProductJamming 的 JSR `10/20/30`。
5. 结果必须包含 Identity、Current WLN、Candidate，以及统一 contract 指标、oracle audit、Jammer Contract 和资源成本。

## 验收

根据 held-out 结果判定 `RECOMMENDED`、`CONDITIONAL` 或 `REJECTED`，同时给出安全/不适用 JSR 区间和 RL candidate 资格。不得为通过验收而降低既有阈值。
