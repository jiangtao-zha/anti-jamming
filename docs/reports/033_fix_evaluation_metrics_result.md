# Task 033-fix：校准 Phase 1 评价指标实现

## 1. 修改原因

Task 033 的 `true_false_peak_ratio` 实际是 false/true，却使用了相反方向的命名；`target_peak_loss_db` 混合了处理前 jammer 和目标响应；CA-CFAR 使用幅度域近似公式且边缘固定除以 40；聚合结果跨 JSR 平均并缺少稳定性区间。

## 2. 指标变化前后

| 旧字段/逻辑 | 新字段/逻辑 |
|---|---|
| `true_false_peak_ratio` | `false_true_peak_ratio = A_false,max / A_target` |
| `target_peak_loss_db` | `target_window_peak_change_db`，明确表示 before/after 目标窗口最大响应变化 |
| 无 clean target 指标 | `clean_target_response_loss_db = 20log10(A_processed,target/A_clean,target)` |
| 幅度域 alpha=`sqrt(-4log(Pfa)/pi)` | 功率域 alpha=`N_ref*(Pfa**(-1/N_ref)-1)` |
| 固定 2×reference_cells | 每个 CUT 动态统计有效左右 reference cells |
| 仅 mean | mean、sample std、95% CI half-width |
| 跨 JSR 一个结论 | 新增 `algorithm_jsr_matrix.csv`，每个 Jammer×Algorithm×JSR 独立结论 |

旧 `results/phase1/evaluation/` 保留不覆盖；新结果保存到 `results/phase1/evaluation_v2/`。

## 3. CFAR 数学定义

对脉压幅度 `A` 先转功率 `P=A^2`。对于每个 CUT，动态收集左右 guard cells 外的有效 reference cells，令有效数量为 `N_ref`：

```text
P_ref = mean(P_reference)
alpha = N_ref * (Pfa ** (-1/N_ref) - 1)
threshold_power = alpha * P_ref
detection = P_cut > threshold_power
```

边缘 CUT 的 `N_ref` 小于中心，阈值系数按实际数量计算，不固定除以 40。

## 4. Clean target reference

评价器只使用 target template、received before/after 和 radar config。理想 target 与局部模板匹配得到 `reference_peak`；处理后在该参考峰的响应与 clean target 的同位置响应比较，得到 `clean_target_response_loss_db`。没有读取 `target_idx`、jammer 类型或真实 jammer signal。

## 5. Monte Carlo Pfa 验证

命令：

```bash
./.venv/bin/python validate_cfar.py --trials 10000 --output results/phase1/evaluation_v2/cfar_pfa.csv
```

结果：

| requested Pfa | measured Pfa | error | trials | reference cells |
|---:|---:|---:|---:|---:|
| 0.00010000 | 0.00011172 | 0.00001172 | 10000 | 20..40 |

该结果未调整公式强行匹配；误差处于 Monte Carlo 统计波动范围内。

## 6. 新评价矩阵

命令：

```bash
./.venv/bin/python validate_evaluation.py --seeds 20 --output-dir results/phase1/evaluation_v2
```

结果：3360 cases、168 个逐 JSR 聚合行、42 个 Jammer×Algorithm 聚合行、接口通过率 100%。

新增/更新文件：

```text
metrics.csv
summary.csv
identity_baseline.csv
algorithm_matrix.csv
algorithm_jsr_matrix.csv
algorithm_applicability_matrix.csv
oracle_check.csv
```

`summary.csv` 包含 `DeltaSINR_std_dB`、`DeltaSINR_ci95_dB`、`CleanTargetLoss_std_dB`、`CleanTargetLoss_ci95_dB` 和 `Pd_after_ci95`。

## 7. 逐 JSR 结论

逐 JSR 结果显示跨 JSR 平均确实会隐藏强度差异。例如 `FMZuse/WLN` 的 delta SINR 从 JSR=0 的约 `-1.12dB` 到 JSR=20 的约 `+2.82dB`；`AMNoiseGaiJam/FDC` 在 JSR=0 约 `+0.22dB`、JSR=20 约 `+0.06dB`。因此后续算法校准必须使用 `algorithm_jsr_matrix.csv`，不能只看跨 JSR 总平均。

`adapt_filter` 仍标记为 oracle-risk，不能依据其高 delta SINR 参与公平排名。

## 8. PASS 规则

`Recommended` 同时要求：

1. `mean(delta_SINR) > 0.2dB`；
2. 95% CI 下界不低于 0；
3. Pd 不下降；
4. `clean_target_response_loss_db > -1dB`。

`Conditional` 要求 Pd 不下降且假峰或 peak error 改善。其余情况标记为 `Neutral`、`Harmful/Not demonstrated` 或 `Interface FAIL`。

## 9. 与旧评价差异

- 旧结果仍保留在 `results/phase1/evaluation/`，未覆盖；
- 新 CFAR 是功率域且边缘感知，检测率和 false peak 统计不应与旧幅度域结果直接混用；
- 新 clean target loss 会揭示“目标窗口峰变化”和“相对理想目标响应损失”的差异；
- 逐 JSR 结论替代跨 JSR 单一结论，算法的推荐范围可能随 JSR 改变；
- 未修改算法，因此差异来自评价定义校准，不代表算法本身发生变化。

## 10. 回归测试

v2 输出目录中保存：

- `validate_no_jammer.py`：9/9 PASS；
- `validate_algorithms.py`：9/10 PASS，FMNoiseAimedJam/FrFT 失败；
- `run_correctness_tests.py`：4 通过、1 警告、5 失败；既有 SliceCombine/FrFT 问题和统一 JSR 强度回归仍保留。

## 11. 验收结果

- false peak 字段语义已修正；
- target window change 与 clean target loss 已分离；
- CFAR 理论定义和 Monte Carlo 验证已完成；
- 边缘 reference cell 已按实际数量处理；
- 逐 JSR 矩阵和统计稳定性已生成；
- 未修改任何算法、jammer、JSR、RL 或 reward。

## 12. Git

分支：`algorithm_design_0711`

主提交：`6aef067 phase1-033-fix-evaluation-metrics`
