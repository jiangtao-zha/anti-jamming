# Task 034-fix3：收紧 Contract Failure 与补齐回归证据

## 目标

确保 Jammer Contract 生成失败、oracle 输入泄漏和 correctness 边界异常都能被明确记录、正确退出，并将结果保存为可审查证据。

## 允许范围

仅修改测试契约、评价状态、测试入口、结果保存和 Phase 1 文档。禁止修改任何 jammer/抗干扰算法、JSR 数学定义、雷达配置、评价阈值和 RL。

## 验收重点

- summary 包含 interface、generation exception、contract generation、oracle 和 correctness failure 计数；失败 contract/oracle 使性能入口返回非零。
- empty、错误 shape、NaN IQ 逐算法真实调用并写入 CSV。
- target preservation 聚合保留 `TARGET_ERASED`、`TARGET_ATTENUATED`、`TARGET_PRESERVED` 的优先级。
- NoJammer 使用 `NO_JAMMER_NOT_APPLICABLE`，不声明 JSR。
- 正式结果、故障注入 probe、stdout/stderr 和报告互相一致并保存到 `results/phase1/task034_fix3/`。

## 测试命令

```bash
MPLCONFIGDIR=/tmp/mplconfig .venv/bin/python validate_algorithms.py
MPLCONFIGDIR=/tmp/mplconfig .venv/bin/python run_correctness_tests.py
```

完成后停止，不进入 Task 035。
