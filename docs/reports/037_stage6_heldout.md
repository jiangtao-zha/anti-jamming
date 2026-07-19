# Task 037 Stage 6 — Held-out 拒绝确认

日期：2026-07-19

状态：`COMPLETED`

阶段提交：`1b0050d`（`phase1-037-stage6-reject-frft-separability`）

Git 分支：`algorithm_design_0711`

## 最终结论

Stage 6 decision：`REJECTED_NO_USABLE_SEPARABILITY`。

Stage 3 已证明 Oracle 上界失败，Stage 4/5 没有生成 observable candidate；因此 held-out 固定为 `REJECTION_CONFIRMATION_ONLY`。本阶段仍按独立 held-out seeds 完成 Identity、Current FrFT、Oracle reference 和 frozen rejection reference 的对照，不能把任何结果登记为 candidate 或 RL 算法。

## 冻结与数据

- Seeds：`10300..10349`。
- JSR：`0/10/20/30 dB`。
- 目标中心：`1000/1500/2500/3500/4000`。
- 正式 jammer：`SMSP`、`FMNoiseSaopin`。
- 负控：`NoJammer`、`AMNoiseGaiJam`、`FMNoiseAimedJam`、`FMZuse`、`NoiseProductJamming`、`NoiseConvolutionJamming`。
- 8000 个场景；26000 条 per-trial rows，按 algorithm×jammer×JSR 跨 seed×position 聚合。
- held-out 启动前校验 Stage 5 的 selected-candidate 文件 hash：`8a015e3f860296dd3aca796cda326c3703d87c07b3f719b51b1eb7fb9b7d4abb`；状态为 `SKIPPED_BY_DECISION_GATE`。held-out 后没有 calibration。

## 正式对照

`Current_FrFT` 使用 whitelist-only receiver input 和冻结 `mask_threshold=0.1`；没有把 target position、jammer label、JSR 或真值分量传给 adapter。`Oracle_FrFT_UpperBound` 仅在两个正式 jammer 上提供 Stage 3 的真实 target-protection reference，带有 `ORACLE_DIAGNOSTIC_ONLY;NOT_FAIR;NOT_RL_ELIGIBLE`。由于 Stage 4 没有 prototype，`FROZEN_REJECTION_CONFIRMATION` 明确复用 Current FrFT 作为 rejected observable reference，不是假装存在新 candidate。

正式 held-out 的代表性结果：

| jammer | JSR | Current FrFT ΔSINR | Current target-only | Oracle ΔSINR | Oracle Pd / Identity |
|---|---:|---:|---:|---:|---:|
| SMSP | 10 | -0.002 dB | -0.005 dB | -0.704 dB | 0.60 / 0.80 |
| SMSP | 20 | +0.005 dB | -0.005 dB | -0.222 dB | 0.60 / 0.60 |
| SMSP | 30 | +0.004 dB | -0.005 dB | +0.047 dB | 0.60 / 0.60 |
| FMNoiseSaopin | 10 | -0.003 dB | -0.005 dB | -0.921 dB | 0.948 / 0.94 |
| FMNoiseSaopin | 20 | -0.002 dB | -0.005 dB | -0.970 dB | 0.868 / 0.924 |
| FMNoiseSaopin | 30 | +0.004 dB | -0.005 dB | -0.969 dB | 0.80 / 0.86 |

Current FrFT 的 held-out 行为接近 Identity，目标损伤很小，但没有任何有意义的抑制收益；Oracle reference 也没有形成可用上界。负控和 NoJammer 结果保存在 `aggregate_results.csv`，不用于制造正结论。

## 资格状态

```json
{
  "decision": "REJECTED_NO_USABLE_SEPARABILITY",
  "observable_candidate_registered": false,
  "candidate_matrix_eligible": false,
  "rl_eligible": false,
  "fallback": "Identity"
}
```

Stage 038 不启动；RL/action space 不修改。当前 FrFT 仅保留为历史 baseline 和对照对象。

## 输出与复现

结果在 `results/phase1/task037/stage6/`：`heldout_metadata.json`、`per_trial_results.csv`、`aggregate_results.csv`、`order_diagnostics.csv`、`mask_diagnostics.csv`、`target_preservation.csv`、`oracle_comparison.csv`、`final_decision.json`、`summary.json`、stdout/stderr。

```bash
MPLCONFIGDIR=/tmp/task037-mpl .venv/bin/python scripts/run_task037.py --stage heldout
```
