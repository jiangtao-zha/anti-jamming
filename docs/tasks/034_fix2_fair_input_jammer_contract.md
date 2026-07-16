# Task 034-fix2：修复公平输入与 Jammer Contract 状态传播

## 目标

修复 Phase 1 测试契约中的公平输入审计和干扰器状态传播问题，并将性能矩阵与 correctness regression 分成两个独立入口。

## 允许修改

- `utils/test_contract.py`
- `utils/jammer_interface.py` 的契约 metadata
- `utils/evaluation.py` 的 target-only 数值状态
- `validate_algorithms.py`
- `run_correctness_tests.py`
- 本任务结果、报告和 Phase 1 状态文档

## 禁止修改

不修改 jammer 波形、JSR 定义、雷达配置、抗干扰算法、评价阈值、RL、reward、state 或 action space；不启动 RL。

## 契约要求

- 算法 radar input 白名单不得包含 `target_dist`、`target_idx`、`jammer_type`、真实 jammer signal 或 JSR 结果字段。
- Jammer contract 明确输出 `UNIFIED_JSR_PASS`、`LEGACY_JSR_BLOCKED` 或 `GENERATION_FAIL`。
- legacy 结果可以保存，但不得进入公平排名。
- target-only 响应完全抹除时输出 `-inf` 和 `TARGET_ERASED`，不输出普通 NaN。
- `validate_algorithms.py` 运行完整性能矩阵；`run_correctness_tests.py` 运行快速 loader、adapter、无干扰和边界回归。

## 验收命令

```bash
MPLCONFIGDIR=/tmp/mplconfig .venv/bin/python validate_algorithms.py
MPLCONFIGDIR=/tmp/mplconfig .venv/bin/python run_correctness_tests.py
```

结果保存到 `results/phase1/task034_fix2/`，完成后停止，不进入 Task 035。
