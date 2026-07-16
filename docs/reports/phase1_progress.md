# Phase 1 Progress

## Current Task

Task 034-fix2：公平输入与 Jammer Contract 状态传播已完成，等待审查。

主提交：`65ba5c9 phase1-034-fix2-fair-input-jammer-contract`

## Completed Tasks

- Task 030：记录 Git 状态、物理参数、干扰/抗干扰注册表、RL 列表和现有测试输出。
- Task 031：建立唯一配置源，统一完整物理信号长度和 RL state transform，并完成回归测试。
- Task 032：建立 7 个 jammer 的公共 wrapper、统一 JSR 计算和 280 case 验证矩阵。
- Task 033：建立统一评价 API、Identity 基线和 3360 case 算法适用矩阵。
- Task 033-fix：修正 false peak/target loss 语义，改用边缘感知功率 CA-CFAR，增加 Pfa 验证、逐 JSR 矩阵和 CI。
- Task 033-fix2：增加 target-only response preservation 分支，保留污染参考响应诊断字段，生成 evaluation_v3。
- Task 034：新增 Current/New FDC 对照、AM 参数搜索和非 AM 负测试；JSR=0/10/20 通过，JSR=30 高方差退化已记录。
- Task 034-fix：统一 Interface/Performance 状态、修复 SliceCombine/FrFT 入口、保存同 seed Identity 对照并修正退出码。
- Task 034-fix2：移除算法输入中的 `target_dist` 等 oracle 字段，传播 unified/legacy Jammer Contract 状态，隔离性能矩阵与 correctness regression。

## In Progress

- 无。Task 035 尚未开始。

## Pending

- Task 031：统一物理环境。
- Task 032：统一干扰接口与 JSR。
- Task 033：统一评价指标和测试契约。
- Task 034-039：按 `docs/tasks/phase1_master_plan.md` 严格顺序执行。

## Latest Experiment

- `validate_algorithms.py`：10/10 配对 PASS，原始输出见 `results/phase1/baseline/validate_algorithms.stdout.txt`。
- `run_correctness_tests.py`：5 通过、1 警告、4 失败，原始输出见 `results/phase1/baseline/run_correctness_tests.stdout.txt`。
- 统一物理环境：`f0=15MHz, Bw=5MHz, Pw=20us, Fs=50MHz, M=1, N=5000`。
- Task 030 基线中的 RL 默认环境：`Pw=10us, Fs=25MHz, JSR=10dB, state_len=1024`。
- Task 031 配置一致性：PASS；完整信号 `(1,5000)`，RL state `(2,1024)`。
- Task 031 无干扰验证：9/9 PASS；算法验证：10/10 PASS。
- Task 031 correctness：5 通过、1 警告、4 失败，失败项与 Task 030 相同。
- Task 032 JSR：7 jammer × 4 JSR × 10 seeds，280/280 PASS，最大误差约 0dB。
- Task 032 回归：无干扰 9/9 PASS；算法配对 9/10 PASS；correctness 内部 4 通过、1 警告、5 失败。
- Task 033 矩阵：3360/3360 接口 case 成功，168 summary rows，42 applicability rows。
- Task 033 回归：无干扰 9/9 PASS；算法配对 9/10 PASS；correctness 内部 4 通过、1 警告、5 失败。
- Task 033-fix CFAR：10000 trials，requested Pfa=1e-4，measured Pfa=1.1172e-4，reference cells=20..40。
- Task 033-fix 矩阵：3360/3360 接口 case 成功，结果保存到 `results/phase1/evaluation_v2/`。
- Task 033-fix2 矩阵：3360/3360 接口 case 成功，结果保存到 `results/phase1/evaluation_v3/`。
- Task 034 FDC：AM 240 cases、非 AM 720 cases、15 组参数搜索，结果保存到 `results/phase1/fdc/`。
- Task 034-fix：400 algorithm cases、400 Identity 对照，Interface 800/800 PASS，结果保存到 `results/phase1/task034_fix/`。

## Blocked Issues

- `SliceCombineJam` loader 不接受统一传入的 `Fs`。
- FrFT correctness 测试引用缺失的 `test_frft_filter`。
- RL 与统一物理基线不一致；Task 031 之前不开始训练。
- 当前 `M=1` 不足以验证 FSTP 多脉冲能力。
- `SliceCombineJam` loader 接口问题和 FrFT 测试入口问题保留，未在 Task 031 扩大范围修复。
- 统一 JSR 后 `FMNoiseAimedJam/frft_filter` 出现性能回归，需由 Task 033 的测试契约统一处理，不能回退 JSR 定义。
- `adapt_filter` 仍依赖内部 `target_idx`，已标记为公平矩阵 blocked/oracle-risk。
- Task 033-fix 未改变算法排序逻辑，只将结论拆为逐 JSR 并增加统计稳定性；`adapt_filter` oracle 风险继续保留。
- Task 033-fix2：Recommended 改用 `target_only_response_change_db`，`adapt_filter` 继续标记 oracle-risk。
- Task 034：New FDC 在 AM JSR=0/10/20 dB 形成收益，JSR=30 dB 退化；暂不作为全 JSR 稳定算法进入 RL。
- Task 034-fix：性能状态已与接口状态分离；adapt_filter=BLOCKED_ORACLE，FSTP(M=1)=NOT_APPLICABLE_MULTIPULSE。
- Task 034-fix2：400 性能 cases 接口全部通过；ISDJ/qpzh 为 `BLOCKED_JAMMER_CONTRACT`，SliceCombine/FSTP 保留 `NOT_APPLICABLE_MULTIPULSE` 并记录 `LEGACY_JSR_BLOCKED`；公平排名过滤 legacy 与 oracle 结果。

## Latest Commit

Task 030：`c11892d phase1-030-baseline-snapshot`
Task 031：`da9deb4 phase1-031-unify-physical-environment`
Task 032：`0136a1d phase1-032-unify-jammer-jsr`
Task 033：`d3933d3 phase1-033-evaluation-contract`
Task 033-fix：`6aef067 phase1-033-fix-evaluation-metrics`
Task 033-fix2：`8d36689 phase1-033-fix2-target-preservation`
Task 034：`b6966ee phase1-034-fdc-am-calibration`
Task 034-fix：`5f565ec phase1-034-fix-algorithm-test-contract`
Task 034-fix2：`65ba5c9 phase1-034-fix2-fair-input-jammer-contract`
