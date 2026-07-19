# Task 037 Stage 7 — Final Decision

日期：2026-07-19

状态：`COMPLETED`

## Final decision

`REJECTED_NO_USABLE_SEPARABILITY`。

Stage 3 的 Oracle upper bound 在正式 `SMSP`/`FMNoiseSaopin` 上失败，Stage 4/5 已按门跳过，Stage 6 的独立 held-out 也没有发现可用 observable suppression。Current FrFT 只保留为 baseline；Identity 是拒绝状态下的 fallback。

```text
observable_candidate_registered = false
candidate_matrix_eligible       = false
rl_eligible                     = false
oracle_upper_bound_available    = true
oracle_upper_bound_status       = FAILED
Task 038 started                = false
```

## Regression gate

- `validate_algorithms.py`: exit 0，Interface PASS `800/800`。
- `run_correctness_tests.py`: exit 0，Failures `0`。

原始 stdout/stderr 在 `results/phase1/task037/stage7/` 保存。

## 阶段闭环

Stage 0 冻结 baseline；Stage 1 修复并验证 FrFT 核心数学性质；Stage 2 完成分量级阶数、重叠和位置稳定性诊断；Stage 3 完成真实分量 Oracle 上界并失败；Stage 4/5 显式跳过；Stage 6 完成无候选 held-out rejection confirmation。没有修改 jammer math、JSR、Phase 1 物理配置、评价阈值、RL/PPO、reward、state 或 action space。

规定 Stage 7 提交：`caf51fa`（`phase1-037-stage7-finalize`）；最终 record 提交：`b5e7642`（`phase1-037-record-commit`）。真实 push 已执行但被 GitHub 100 MB 单文件限制阻止；远端未同步，错误和 SHA 证据保存在 `results/phase1/task037/git_push_stderr.txt` 与 `git_remote_verification.txt`。
