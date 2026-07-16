# Task 034-fix：统一算法测试契约与修复验证入口

## 目标

修复 Phase 1 算法测试入口，严格区分 Interface 与 Performance，保证 SliceCombine、FrFT、oracle 风险和 M=1 FSTP 的结果可追溯，并让进程退出码只反映接口/基础设施失败。

## 必读文件

- `AGENTS.md`、`ROADMAP.md`
- Task 030-034 报告及 `phase1_blocked_issues.md`
- `validate_algorithms.py`
- `run_correctness_tests.py`
- `unified_framework.py`
- `utils/jammer_interface.py`
- `anti_jamming/adapters.py`
- `anti_jamming/qpzh.py`
- `anti_jamming/frft_filter.py`
- `anti_jamming/FastSlowTimeProcessor.py`

## 修改范围

允许修改 loader/compatibility adapter、测试脚本、测试辅助函数、测试输出和文档。禁止修改任何 jammer 波形、JSR、Phase 1 配置、抗干扰算法实现、evaluation 指标、RL/reward/action space。

## 固定契约

- Interface：`PASS` 或 `FAIL`，检查调用、shape、complex dtype、NaN/Inf、输入不可变和公平输入。
- Performance：`RECOMMENDED`、`CONDITIONAL`、`NEUTRAL`、`HARMFUL`、`BLOCKED_ORACLE`、`NOT_APPLICABLE`、`INTERFACE_FAIL`。
- 每个算法 case 使用同 seed、同 jammer、同 JSR 的 Identity 对照。
- `adapt_filter` 固定 `BLOCKED_ORACLE`；`M=1` 的 FSTP 固定 `NOT_APPLICABLE_MULTIPULSE`。
- FrFT 必须通过 active adapter；性能负值不能伪装成接口失败。
- 进程非零退出仅表示 Interface FAIL 或测试基础设施异常。

## 测试矩阵

JSR `0/10/20/30 dB`，seeds `42..51`，覆盖任务指定的 FDC、FrFT、qpzh、FSTP、adapt_filter、WLN 配对。

## 输出与验收

输出至 `results/phase1/task034_fix/`，生成 interface/performance/combined 结果、SliceCombine smoke、FrFT adapter test、原始 stdout/stderr 和 JSON 汇总。新增初始审计和最终报告，不启动 RL、不进入 Task 035。
