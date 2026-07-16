# Task 034-fix：测试系统初始审计

## 1. 审计范围

检查了 `validate_algorithms.py`、`run_correctness_tests.py`、`unified_framework.py`、`utils/jammer_interface.py`、`anti_jamming/adapters.py`、`anti_jamming/qpzh.py`、`anti_jamming/frft_filter.py` 和 `FastSlowTimeProcessor.py`。当前分支为 `algorithm_design_0711`，审计阶段未修改代码。

## 2. 当前脚本行为

### `validate_algorithms.py`

- 固定 10 个 jammer/algorithm 配对，实际每个配对 JSR=10 dB、10 seeds。
- 使用旧 `UnifiedEvaluator`，不是 Task 033-fix2 的多维评价契约。
- `run_single_trial()` 通过 `AntiJammingProcessor.process()` 调用算法；该类捕获算法异常并返回原始信号，可能把真实接口异常隐藏成“运行成功”。
- 判定只要求 detection 不下降且 delta SINR 不低于 -1 dB，`pass` 同时混合了调用成功和性能结论，无法证明优于 Identity。
- 当前主函数已有 `sys.exit(1)`，但它依据宽松性能 `pass`，不是统一 Interface 状态。

### `run_correctness_tests.py`

- 动态导入各模块中历史测试函数；FrFT 仍引用不存在的 `test_frft_filter`。
- SliceCombine/FSTP 失败发生在 legacy loader 的 `Fs` 构造参数阶段。
- 导入失败、运行异常都被记录为旧式 `FAIL`，未与接口失败和性能不适用分离。
- `__main__` 只调用 `run_all_tests()` 和 `diagnose_failed()`，没有依据汇总状态退出非零，因此内部失败时进程仍可返回 0。

## 3. 已确认接口问题

### SliceCombine

`JammerLoader.load('SliceCombineJam')` 在 `unified_framework.py:312-314` 将 Phase 1 的 `C/f0/T/Tr/B/Fs` 全量传给 `anti_jamming.qpzh.SliceCombineJam`。该 legacy 构造函数只接受 `C/f0/T/Tr/B`，因此 `Fs` 直接触发 `TypeError`。其 `generate()` 也只接受 `R_target/m/n/JSR_dB/noise_var` 并返回 tuple，不支持 Task 032 的 dict API。该问题应在兼容 adapter/loader 层处理，不能修改波形公式。

### FrFT

active adapter 已在 `anti_jamming.adapters.frft_adapter` 注册，输入是 `Srt_matrix/St_base`，输出是二维 processed signal 和 template。过期的模块级 `test_frft_filter` 不存在，测试入口应直接调用 `get_antijam_func('frft_filter')`。

## 4. 当前 PASS 的实际含义

当前 PASS 只能说明旧脚本的宽松条件满足，不能说明：接口没有被吞错、输出未污染输入、算法优于 Identity、target-only 保护满足或结果适用于 M=1/FSTP。特别是 FrFT 的失败是测试入口失败，不是算法性能结论。

## 5. oracle 与适用性事实

- `adapt_filter_adapter` 会向内部算法注入 `target_idx`，公平性能应固定标记 `BLOCKED_ORACLE`，但其接口仍可测试。
- `fastslow_adapter` 在 `M<2` 时调用 `_apply_spectral_subtraction` 降级，不能把 M=1 的运行成功解释成慢时间 FSTP 验证通过，应为 `NOT_APPLICABLE_MULTIPULSE` 并记录 fallback。
- SliceCombine 的 loader/interface 失败属于 Interface FAIL，不属于算法性能失败。

## 6. 修复设计

新增统一 contract helper 和中等规模矩阵脚本：直接调用 active adapter、保存输入副本、白名单传参、同 seed Identity 对照，并分别写出 Interface 与 Performance 状态。修复 `JammerLoader` 的 SliceCombine 最小兼容包装；保留所有算法实现和评价公式不变。旧脚本改为使用统一结果/退出规则，不降低既有性能阈值。
