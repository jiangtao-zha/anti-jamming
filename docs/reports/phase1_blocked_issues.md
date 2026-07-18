# Phase 1 Blocked Issues

## Task 033：adapt_filter oracle dependency

`validate_evaluation.py` deliberately does not put `target_idx`, `jam_info`,
or the true jammer signal into the algorithm `radar_par`. However,
`anti_jamming/adapters.py:adapt_filter_adapter` still constructs an adapted
parameter dictionary with `target_idx=radar_par.get('target_idx', 0)`, and the
core `anti_jamming/adapt_filter.py` uses that value to align its projection
template.

Therefore:

- the evaluation matrix records `adapt_filter` execution results;
- `adapt_filter` is marked `blocked_for_fair_comparison` in
  `results/phase1/evaluation/oracle_check.csv`;
- its matrix performance must not be interpreted as a fair no-oracle result;
- this task does not modify `adapt_filter`, in accordance with the task
  boundary.

## Task 034-fix：测试契约状态

- `SliceCombineJam` 已通过 `LegacyTupleJammerAdapter` 兼容统一调用；其旧模型没有分离 target/noise 组件，因此 smoke 结果标记 `legacy/unified-JSR-blocked`，不作为统一 JSR 性能结论。
- FrFT correctness 已改为直接走 active `get_antijam_func('frft_filter')`，不再依赖缺失的历史 `test_frft_filter` 入口。
- `validate_algorithms.py` 和 `run_correctness_tests.py` 现在共用 Interface/Performance contract；接口异常才导致非零退出，性能 HARMFUL、BLOCKED_ORACLE 和 NOT_APPLICABLE 不再伪装成接口失败。
- FSTP 在当前 Phase 1 `M=1` 矩阵中固定标记 `NOT_APPLICABLE_MULTIPULSE`，仅记录其 fallback 能运行。

## Task 034-fix2：公平输入与 Jammer Contract

- 性能契约白名单已移除 `target_dist`，并在算法调用前检查目标位置、jammer 信息、真实 jammer signal 和 JSR 结果字段。
- `ISDJ` 与 `SliceCombineJam` 的 legacy JSR 结果只能作为 exploratory-only 保存，不能进入公平排名；其聚合状态为 `LEGACY_JSR_BLOCKED`。
- `SliceCombineJam/FSTP` 同时保留 `NOT_APPLICABLE_MULTIPULSE`，不能解释为多脉冲算法性能结论。
- `adapt_filter` 仍存在内部 target_idx 依赖，继续保持 `BLOCKED_ORACLE`，本任务没有修改算法。

## Task 034-fix3：Contract Failure 与回归证据

- 正式矩阵中 contract/oracle failure 计数为 0；故障注入 probe 已证明 `GENERATION_FAIL` 和 oracle leak 都返回非零退出码。
- correctness 已真实调用 empty、错误 shape 和 NaN IQ，不能将静态 helper 结果当作边界通过证据。
- NoJammer 不声明 requested/measured JSR，状态为 `NO_JAMMER_NOT_APPLICABLE`。

## Task 035：WLN ↔ FMZuse

- Current/Candidate WLN 的 FMZuse 正收益没有形成专用性；held-out 负控平均收益在 JSR=10/20/30 均高于 FMZuse，specificity gap 全部为负。
- JSR=0 dB 的约 1 dB 负收益在 calibration 和 held-out 重复出现；当前 WLN 无 observable gating/bypass。
- Task 035 最终状态为 `REJECTED`，WLN 不进入最终 RL candidate matrix；后续若重启，应单独设计并预注册 gating 与新的 held-out 集。

## Task 036：adapt_filter Fair candidate rejected

- Stage 1–2 confirmed that the current `adapt_filter` requires target alignment `target_idx`; it remains `ORACLE_UPPER_BOUND_ONLY` and is not a fair comparison result.
- All 16 calibration candidates failed the preregistered qualification gates, primarily position robustness and high-JSR target-jammer performance.
- The frozen held-out rejection-confirmation prototype preserved the target-only response but failed high-JSR target-jammer performance and the `<5dB` position-spread gate; final status is `ORACLE_UPPER_BOUND_ONLY`.
- No Fair implementation was registered in RL and no action-space change was made. A future registry removal/relabeling decision for the legacy Oracle action requires a separate reviewed task.

## Task 036-fix：物理 Fixture、有效 Gating 与状态收口

- 正式多位置证据已改为 `PHYSICAL_COMPONENT_RECOMPOSITION`：目标、jammer 和 noise 按物理规则分量重组；旧 whole-record shift 仅保留为 stress 对照。
- 五个可观测 confidence 分量和固定阈值使 Identity fallback 有效触发；Stage C fallback ratio 为 `0.5`，held-out 冻结代表为 `0.490125`，不是恒定 0 或 1。
- 名义 candidate `8` 个按行为签名去重为有效 candidate `4` 个；calibration 没有 candidate 通过，held-out 仅作 rejection confirmation。
- Held-out 按 jammer×JSR 跨 seed×position 聚合；两类目标 jammer 各仅有 `1` 个通过 JSR 条件，因此最终为 `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`。
- legacy adapt_filter 结论保留为 `ORACLE_UPPER_BOUND_ONLY`；Fair prototype 未注册，`rl_eligible=false`、`candidate_matrix_eligible=false`、`rl_action_space_modified=false`。
- 原 Task 036 的历史远端状态已修正记录为 `COMPLETED_REMOTE_SYNCED`；本次 Task 036-fix push 被租户安全策略阻止，状态为 `PUSH_BLOCKED_BY_POLICY`，本地 HEAD 与错误证据已保存。原始 push failure 证据未删除。

## Task 036-fix2：Frozen dispatch 与 held-out 证据修正

- 旧 Task 036-fix Stage D 冻结了设计 B，但旧 Stage E 实际调用设计 A 的 `fit_adapt_filter_fair`；旧 Stage E 结果保留为历史证据，状态为 `INVALID_FROZEN_CANDIDATE_DISPATCH`，不再作为有效 frozen-candidate 结论。
- 修正版统一 dispatch：A→`fit_adapt_filter_fair`，B→`fit_adapt_filter_fair_multihypothesis`；行为签名只包含 estimated index、fallback、量化 confidence 和 processed output hash，candidate/fit/gate 元数据不参与身份。
- 8 个名义候选按真实行为去重为 2 个等价类；Stage B 校准未产生 qualified candidate，A 代表仅作为 canonical rejection representative。
- 修正版 held-out 使用新 seeds `9200..9249`，按 jammer×JSR 跨 seed×position 聚合；两类目标 jammer 各只有 1 个通过 JSR 条件，因此最终只能确认 `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`。
- `rl_eligible=false`、`candidate_matrix_eligible=false`、`fair_registered=false`、`rl_action_space_modified=false`；Task 037 随后独立启动。旧 Task 036-fix2 的手工远端同步记录为 `COMPLETED_REMOTE_SYNCED`，SHA `7fe8b146fe34b6667061c844bd3e1887e6fe5fa2`，原始 push failure evidence 保留。
