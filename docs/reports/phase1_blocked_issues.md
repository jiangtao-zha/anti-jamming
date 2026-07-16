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
