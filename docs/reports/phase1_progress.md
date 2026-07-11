# Phase 1 Progress

## Current Task

Task 031：统一 Phase 1 物理环境与配置来源，已完成，等待审查。

## Completed Tasks

- Task 030：记录 Git 状态、物理参数、干扰/抗干扰注册表、RL 列表和现有测试输出。
- Task 031：建立唯一配置源，统一完整物理信号长度和 RL state transform，并完成回归测试。

## In Progress

- 无。Task 032 尚未开始。

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

## Blocked Issues

- `SliceCombineJam` loader 不接受统一传入的 `Fs`。
- FrFT correctness 测试引用缺失的 `test_frft_filter`。
- RL 与统一物理基线不一致；Task 031 之前不开始训练。
- 当前 `M=1` 不足以验证 FSTP 多脉冲能力。
- `SliceCombineJam` loader 接口问题和 FrFT 测试入口问题保留，未在 Task 031 扩大范围修复。

## Latest Commit

Task 030：`c11892d phase1-030-baseline-snapshot`
Task 031：待提交后回填。
