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
