# Task 034-fix2：公平输入与 Jammer Contract 状态传播结果

## 1. 审查发现的问题

- 原 `_whitelist_radar_par` 将 `target_dist` 传入算法，构成目标位置相关 oracle 风险。
- `ISDJ` 与 `SliceCombineJam` 的 legacy JSR 状态只存在于 metadata，聚合结果仍可能被解释为正常性能结论。
- `validate_algorithms.py` 与 `run_correctness_tests.py` 重复运行完整性能矩阵并覆盖同一目录。
- target-only 响应完全消失时的 dB 计算可能产生普通 NaN/警告，无法明确表达目标被抹除。

## 2. 公平输入白名单

允许的雷达字段为：`C`、`f0`、`Bw`、`Pw`、`Fs`、`Tr`、`M`、`N`，以及由测试契约构造的 `Srt_matrix`、`St_base`。

禁止字段包括：`target_idx`、`target_start_idx`、`target_dist`、`target_range`、`jammer_type`、`jam_info`、`true_jammer_signal`、`jammer_signal`、`requested_jsr_db`、`measured_jsr_db`、`jsr_status`。调用前自动审计这些字段；发现时返回 `ORACLE_INPUT_LEAK` 和 `FAIL`。

## 3. Jammer Contract 定义

`Phase1JammerAdapter` 传播分离的 target/jammer/noise 分量、requested/measured JSR 和 `unified/pass` 状态。`LegacyTupleJammerAdapter` 明确传播 `legacy/unified-JSR-blocked`、无独立 components 和 `measured_jsr_db=None`。

测试层归一化为：

- `UNIFIED_JSR_PASS`：有独立分量且 requested/measured JSR 有效；
- `LEGACY_JSR_BLOCKED`：legacy 状态、缺少分量或 measured JSR 缺失；
- `GENERATION_FAIL`：生成阶段异常或数值无效。

## 4. 状态传播链路

```text
JammerAdapter metadata/top-level fields
        -> _generate_case
        -> raw interface rows and case metrics
        -> performance_results.csv / combined_results.csv
        -> jammer_contract_results.csv / fair_ranking_results.csv / test_summary.json
```

每个性能聚合行包含 contract status、requested/measured/error、可比较性、探索性和公平排名资格。

## 5. 性能状态优先级

```text
INTERFACE_FAIL
BLOCKED_ORACLE
NOT_APPLICABLE_MULTIPULSE
BLOCKED_JAMMER_CONTRACT
normal performance status
```

因此 `ISDJ/qpzh` 变为 `BLOCKED_JAMMER_CONTRACT`；`SliceCombineJam/FSTP` 保留 `NOT_APPLICABLE_MULTIPULSE`，同时显式记录 `LEGACY_JSR_BLOCKED`。两者均不进入公平排名。

## 6. target preservation 数值修正

target-only matched-filter peak 小于等于 `1e-12` 时，输出 `target_only_response_change_db=-inf`、`target_only_response_change_is_finite=false` 和 `target_preservation_status=TARGET_ERASED`。该状态在统一性能分类中为 `HARMFUL`，但不会覆盖更高优先级的 oracle、multipulse 或 jammer-contract 阻塞状态。

## 7. 两个测试入口的职责

- `validate_algorithms.py`：运行 10 个配对 × 4 个 JSR × 10 个 seed 的完整 Interface + Performance contract，输出到 `performance_contract/`。
- `run_correctness_tests.py`：运行 10 个 loader smoke、10 个 adapter smoke、10 个 NoJammer regression 和 4 个边界检查，输出到 `correctness_regression/`；性能负收益不导致 correctness 失败。

## 8. 最终测试结果和退出码

性能矩阵：400 cases，算法与 Identity interface rows 共 800，`interface_fail=0`，`generation_failures=0`，进程退出码 0。contract 聚合为 32 个 `UNIFIED_JSR_PASS`、8 个 `LEGACY_JSR_BLOCKED`；公平排名资格为 20 个聚合行。

correctness regression：loader 10、adapter 10、NoJammer 10、边界 4，失败数 0，进程退出码 0。

原始输出和 CSV 位于：

```text
results/phase1/task034_fix2/
```

## 9. 未解决问题与风险

- legacy `ISDJ`/`SliceCombineJam` 仍不能用于统一 JSR 的公平排名；本任务只传播状态，没有改写其波形或 JSR。
- `adapt_filter` 仍因内部 target_idx 依赖标记为 `BLOCKED_ORACLE`。
- `M=1` 下 FSTP 仍不代表真实快慢时间处理。
- Matplotlib 在当前受限环境产生缓存目录警告，但不影响测试结果。

## 10. 是否允许进入 Task 035

代码和验证入口已满足本任务边界，是否进入 Task 035 仍需 ChatGPT 审查本报告、Git diff 和 commit。

## 11. Git 信息

- 分支：`algorithm_design_0711`
- 主提交 SHA：待主提交完成后回填
