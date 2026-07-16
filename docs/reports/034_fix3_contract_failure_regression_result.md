# Task 034-fix3：Contract Failure 与回归证据结果

## 1. 修复内容

- `validate_algorithms.py` 的 summary 新增 `interface_failures`、`generation_exceptions`、`contract_generation_failures`、`oracle_input_failures`、`correctness_failures`；contract generation 或 oracle 输入失败会使退出码为 1。
- correctness regression 现在对 10 个算法配对分别真实调用 empty IQ、错误 shape IQ、NaN IQ，记录 `call_attempted`、interface 状态和异常信息。
- 聚合目标保护状态按 `TARGET_ERASED > TARGET_ATTENUATED > TARGET_PRESERVED` 计算。
- NoJammer 改为 `NO_JAMMER_NOT_APPLICABLE`，requested/measured/error JSR 均为空，不参与可比较性。

## 2. 正式测试证据

性能矩阵：400 cases，800 interface rows，`interface_failures=0`、`generation_exceptions=0`、`contract_generation_failures=0`、`oracle_input_failures=0`、退出码 0。

correctness regression：loader 10、adapter 10、NoJammer 10；边界 33 条，其中 30 条为真实算法调用，`boundary_call_attempts=30`、`correctness_failures=0`、退出码 0。

正式证据保存于：

```text
results/phase1/task034_fix3/
```

包括完整性能 CSV、correctness CSV、summary JSON、stdout/stderr 和故障 probe。

## 3. Failure probe 证据

故障注入结果保存于 `results/phase1/task034_fix3/contract_failure_probes/summary.json`：

| Probe | contract failures | oracle failures | exit code |
|---|---:|---:|---:|
| generation failure | 10 | 0 | 1 |
| oracle input leak | 0 | 10 | 1 |

这两组 probe 证明异常状态不会继续以退出码 0 结束。

## 4. NoJammer 与 target preservation

NoJammer loader row 为 `NO_JAMMER_NOT_APPLICABLE`，没有指定 JSR。正式性能矩阵中的 target-only 聚合保留抹除状态；`adapt_filter` 组为 `TARGET_ERASED`，但性能主状态仍按既有优先级为 `BLOCKED_ORACLE`。

## 5. 未解决问题

- legacy ISDJ/SliceCombine 仍不能参与统一 JSR 公平排名。
- adapt_filter 的算法 oracle 依赖和 M=1 下 FSTP 不适用状态仍保持原样。
- 本任务没有修改算法、jammer、评价阈值或 RL。

## 6. Git 信息

- 分支：`algorithm_design_0711`
- 主提交 SHA：`9df3072`
