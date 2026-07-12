# Task 033-fix：校准 Phase 1 评价指标实现

## 目标

修正 Task 033 的指标语义和统计契约：重命名 false/true 峰比，区分目标窗口响应变化与 clean target 响应损失，改用功率域边缘感知 CA-CFAR，增加 Pfa Monte Carlo 验证、逐 JSR 矩阵和均值/std/95% CI。

## 范围

只修改 `utils/evaluation.py`、`validate_evaluation.py`、新增 `validate_cfar.py`、报告和结果输出。禁止修改 jammer、JSR、雷达配置、抗干扰算法、RL、reward、state、PPO。

## 验收

- `false_true_peak_ratio` 替代错误命名；
- 输出 `target_window_peak_change_db` 和 `clean_target_response_loss_db`；
- 使用功率域 CA-CFAR，alpha=`N_ref*(Pfa**(-1/N_ref)-1)`，边缘动态统计有效 reference cells；
- 10,000 trial Pfa 验证；
- `evaluation_v2` 保存 3360 case、逐 JSR matrix 和统计 CI；
- 完成回归测试并提交 `phase1-033-fix-evaluation-metrics`。
