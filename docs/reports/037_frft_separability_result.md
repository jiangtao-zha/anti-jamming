# Task 037 — FrFT 域目标—干扰可分离性、抑制上界与动作资格总报告

日期：2026-07-19

最终决策：`REJECTED_NO_USABLE_SEPARABILITY`

## 1. 数学定义与数值正确性

当前 `myfrft` 使用有限维 centered unitary DFT 的谱分数幂，`theta=pi*a/2`，阶数 4 周期；`a=0/1/2/3` 为 `I/U/U^2/U^3`，`a=4` 为 `I`。Stage 1 的 92/92 性质测试、5/5 边界测试和 Oracle input audit 全部通过，最大 inverse error `8.705e-16`、最大 period-4 error `9.891e-16`、最大 energy error `1.110e-15`。连续 LFM 理论聚集阶数在该离散谱定义下未被冒充为已知真值。

## 2. 分量级可分离性

Stage 2 使用 seeds `10000..10029`、JSR `0/10/20/30`、五个目标中心和 1000-sample 局部窗口，完成 4800 个分量重组 cases。正式 `SMSP`/`FMNoiseSaopin` 的 peak order gap median/q25 均为 `1.90/1.90`，同阶域 overlap median 均为 `0.000`；因此进入 Oracle 诊断。补充 jammer 单独保存，未混入正式公平结论。所有真实分量只在 diagnostics runner 内使用。

## 3. Oracle 上界

Stage 3 使用 seeds `10100..10119`，四种阶数策略×四种 Oracle mask，共 12800 trials。最乐观的 target-protection mask 已收紧为真实 target FrFT 能量累计 90% 的硬支持，但两个正式 jammer 均没有任何聚合同时满足 ΔSINR mean>1 dB、CI 下界≥0、Pd 不低于 Identity、target-only>-1 dB、无 TARGET_ERASED 和 position spread<5 dB。因此 `oracle_upper_bound=FAILED`。

## 4. Observable prototype 与 calibration

Oracle 失败后 Stage 4/5 均 `SKIPPED_BY_DECISION_GATE`。没有实现伪原型、没有运行 calibration、没有生成候选或行为等价类；held-out 模式固定为 `REJECTION_CONFIRMATION_ONLY`。

## 5. Held-out 与对照

Stage 6 使用 seeds `10300..10349`，正式 jammer 加六类负控，8000 场景、26000 trial rows。Current FrFT 的正式 held-out ΔSINR 约为 `-0.003..+0.005 dB`，target-only change 约 `-0.005 dB`，即接近 Identity 但没有专用抑制收益。Stage 3 Oracle reference 也未形成有用上界。NoJammer/负控和 target preservation 均已保存。

## 6. 最终动作资格

```json
{
  "decision": "REJECTED_NO_USABLE_SEPARABILITY",
  "observable_candidate_registered": false,
  "candidate_matrix_eligible": false,
  "rl_eligible": false,
  "fallback": "Identity"
}
```

不进入 candidate matrix，不进入 RL，不修改 action space；不启动 Task 038。Current FrFT 仅作为历史 baseline 保留。

## 7. 阶段提交

`c65d7d1` Stage 0；`b6899b3` Stage 1；`4ed22df` Stage 2；`d2f2cb5` Stage 3；`37dc370` Stage 4 skipped；`de67528` Stage 5 skipped；`a9d16e8` Stage 6；`1406b49` Stage 7 finalize；record commit 在本报告提交链中补录。

## 8. Regression

`validate_algorithms.py` exit 0，Interface `800/800`；`run_correctness_tests.py` exit 0，Failures `0`。证据文件位于 `results/phase1/task037/stage7/`。

## 9. 远端

record commit 已完成：本地 `a7b00fe2a35fd645f652600531f2794da484ad6a`。真实 push 被 GitHub pre-receive file-size policy 拒绝，因为 `results/phase1/task037/stage2/per_order_metrics.csv` 为 130.34 MB；远端仍为 `7fe8b146fe34b6667061c844bd3e1887e6fe5fa2`。最终状态为 `PUSH_BLOCKED_BY_POLICY`、`REMOTE_NOT_SYNCHRONIZED`，没有伪造同步。
