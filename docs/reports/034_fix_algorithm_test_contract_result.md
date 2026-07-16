# Task 034-fix：统一算法测试契约与修复验证入口

## 1. 原测试系统问题

初始审计见 `docs/reports/034_fix_test_contract_initial_audit.md`。主要问题：

- `validate_algorithms.py` 使用旧 `UnifiedEvaluator` 和 `-1 dB` 宽松性能阈值，把调用成功与性能有效混在一起；
- `AntiJammingProcessor.process()` 捕获算法异常后返回原信号，可能隐藏接口失败；
- `run_correctness_tests.py` 依赖过期的 `test_frft_filter`，且内部失败不影响进程退出码；
- `JammerLoader` 向 `SliceCombineJam` 传入其不支持的 `Fs`；
- `adapt_filter` 的高收益不能作为无 oracle 公平结果；
- `FSTP` 的 `M=1` fallback 不能代表慢时间算法有效。

## 2. 修改文件列表

- `utils/jammer_interface.py`：新增 legacy tuple jammer 的 dict API 兼容 wrapper；
- `unified_framework.py`：SliceCombine、ISDJ 使用兼容 wrapper；
- `anti_jamming/qpzh.py`：SliceCombine 构造函数增加可选 `Fs`，只做接口参数映射，不改波形公式；
- `utils/test_contract.py`：新增统一 Interface/Performance contract 和矩阵 runner；
- `validate_algorithms.py`：改为统一 contract 入口；
- `run_correctness_tests.py`：改为统一 contract 兼容入口；
- `docs/tasks/034_fix_algorithm_test_contract.md`；
- `docs/reports/034_fix_test_contract_initial_audit.md`；
- `docs/reports/phase1_blocked_issues.md`、`docs/reports/phase1_progress.md`；
- `results/phase1/task034_fix/`：完整结果和原始 stdout/stderr。

未修改 FDC、WLN、FrFT、qpzh、adapt_filter、FSTP 算法逻辑，未修改 jammer 波形、JSR、Phase 1 配置、evaluation、RL、reward 或 PPO。

## 3. SliceCombine 接口修复方式

`SliceCombineJam` 仍保留原有 `generate(R_target, m, n, JSR_dB, noise_var)` 和波形实现。构造函数现在接受可选 `Fs`，由 loader 传入统一配置的采样率。

由于 legacy `generate()` 只返回 composite tuple、不提供分离 target/noise 组件，新增 `LegacyTupleJammerAdapter`：

- 新 API 支持 `target_signal/config/jsr_db/seed`；
- 输出 `target/jammer/noise/received` 统一 shape；
- `noise` 缺失时显式为零；
- metadata 标记 `legacy/unified-JSR-blocked`；
- 不把该路径的 JSR 结果作为公平性能结论。

ISDJ 同样通过该 wrapper 进入统一接口，避免相同的 tuple API 失败。

## 4. FrFT 测试入口修复方式

删除了对不存在的 `test_frft_filter` 的依赖。统一 contract 直接调用：

```python
get_antijam_func('frft_filter')(radar_par, mask_threshold=0.1)
```

专项结果保存在 `frft_adapter_test.csv`，检查了 shape、complex dtype、有限值、输入不可变性和不传递 `target_idx/jammer label`。

## 5. Interface Contract 定义

每个 algorithm case 检查：

- active adapter 调用成功；
- 输出 shape 与 `(M, N)` 一致；
- 输出为 complex 数组；
- 无 NaN/Inf；
- target-only 分支同样满足接口；
- 输入数组未被修改；
- adapter 输入使用白名单，不含 `target_idx`、jammer type、真实 jammer signal 或 `jam_info`。

接口状态只有 `PASS` 和 `FAIL`。失败保存 `exception_type`、`exception_message` 和 `traceback_summary`。

## 6. Performance Contract 定义

性能状态为：

```text
RECOMMENDED
CONDITIONAL
NEUTRAL
HARMFUL
BLOCKED_ORACLE
NOT_APPLICABLE_MULTIPULSE
INTERFACE_FAIL
```

判定沿用 Task 033-fix2 的 delta SINR、95% CI、Pd、target-only response、peak error 和 false peak 契约，没有降低阈值。`adapt_filter` 固定 `BLOCKED_ORACLE`；`FSTP` 在 `M=1` 固定 `NOT_APPLICABLE_MULTIPULSE`。

## 7. 退出码规则

- 所有预期 algorithm case Interface PASS：进程退出 0；
- 存在 Interface FAIL、生成失败或测试基础设施异常：进程退出非 0；
- `HARMFUL`、`BLOCKED_ORACLE`、`NOT_APPLICABLE_MULTIPULSE` 只属于性能/适用性结论，不导致接口退出失败。

本次最终输出：Interface 800 PASS、0 FAIL，两个入口均退出 0。

## 8. 测试矩阵

10 个配对 × 4 个 JSR × 10 个 seeds（42..51）：

```text
AMNoiseGaiJam/FDC
FMNoiseAimedJam/FrFT
FMNoiseSaopin/FrFT
SMSP/qpzh
ISDJ/qpzh
SliceCombineJam/FSTP
SMSP/FSTP
NoiseProductJamming/adapt_filter
NoiseConvolutionJamming/adapt_filter
FMZuse/WLN
```

共 400 个 algorithm cases，每个 case 有同 seed、同 jammer、同 JSR 的 Identity 对照。

## 9. Interface 结果

| 项目 | 结果 |
|---|---:|
| algorithm cases | 400 |
| Identity 对照 cases | 400 |
| Interface PASS records | 800 |
| Interface FAIL records | 0 |
| generation failures | 0 |
| process exit code | 0 |

SliceCombine smoke：四个输出均为 `(5000,)` complex、无 NaN/Inf；JSR 状态为 `legacy/unified-JSR-blocked`。FrFT smoke：输入/输出均为 `(1,5000)` complex，无 NaN/Inf，输入未改变。

## 10. Performance 结果

跨全部 JSR 聚合的状态数量：

| 状态 | 数量 |
|---|---:|
| RECOMMENDED | 10 |
| CONDITIONAL | 9 |
| NEUTRAL | 0 |
| HARMFUL | 5 |
| BLOCKED_ORACLE | 8 |
| NOT_APPLICABLE_MULTIPULSE | 8 |
| INTERFACE_FAIL | 0 |

代表性逐 JSR 结论：

- FDC/AMNoiseGaiJam：JSR 0、10 为 `RECOMMENDED`；JSR 20 为 `CONDITIONAL`；JSR 30 为 `HARMFUL`；
- FrFT：接口全部 PASS，性能状态随 JSR 为 CONDITIONAL/HARMFUL，负收益没有被误报为接口失败；
- qpzh/SMSP：JSR 0/10/20 为 `RECOMMENDED`，JSR 30 为 `CONDITIONAL`；
- qpzh/ISDJ：JSR 0/10 为 `RECOMMENDED`，JSR 20/30 为 `HARMFUL`；
- WLN/FMZuse：JSR 0 为 `CONDITIONAL`，JSR 10/20/30 为 `RECOMMENDED`。

详细字段包括 Identity/algorithm SINR、delta SINR、Pd、peak error、false peak、target-only response、runtime 和 memory，保存在 `performance_results.csv` 和 `combined_results.csv`。

## 11. adapt_filter oracle 状态

`adapt_filter` 的 8 个 Jammer×JSR 聚合均为 `BLOCKED_ORACLE`。它的接口运行结果仍被保留，公平排名和 RECOMMENDED 统计均不使用这些结果。原因和代码位置继续记录在 `docs/reports/phase1_blocked_issues.md`。

## 12. FSTP 适用性说明

当前 Phase 1 配置为 `M=1`。FSTP adapter 的 fallback 可以运行，接口状态为 PASS，但 8 个 FSTP 聚合全部标记 `NOT_APPLICABLE_MULTIPULSE`，不能解释为慢时间域能力验证通过。

## 13. 剩余失败项与告警

- 当前没有 Interface FAIL；
- FrFT、FDC、qpzh 在部分 JSR 下的性能负值是真实性能结论，保留在结果中；
- SliceCombine 和 ISDJ 已能通过接口，但 SliceCombine 的分离组件和统一 JSR 仍 blocked；
- 运行期间 `evaluate_target_preservation` 对极低响应出现 `divide by zero` RuntimeWarning，结果仍被写入，未伪造成接口失败；
- 旧的其他 correctness 配对和 legacy 测试入口不再作为本任务的判定来源，统一结果以 `task034_fix` 为准。

## 14. 是否允许进入 Task 035

测试基础设施层面满足 Task 034-fix 验收：接口和性能已分离，退出码可信，结果可追溯。算法层面仍有 FDC JSR30、FrFT 和 qpzh 高 JSR 的性能问题，且 adapt_filter/FSTP 有明确适用性限制。根据审查门禁，当前只允许 ChatGPT 审查 Task 034-fix，不自动开始 Task 035。

## 15. Git

分支：`algorithm_design_0711`

主提交：待提交后回填。
