# Task 033-fix2：建立独立目标保真度评价分支

## 1. 问题说明

Task 033-fix 的 `clean_target_response_loss_db` 仍是在 `received=target+jammer+noise` 经算法处理后，读取目标位置响应并与 clean target 比较。该值混合了目标响应、残余干扰、噪声和算法处理结果，不能严格表示算法本身对目标的固有保真度。

## 2. 新指标数学定义

对同一个 algorithm，增加独立输入分支：

```text
clean_target_signal -> algorithm -> processed_clean_target
```

令 `A(x)` 为 `x` 与局部发射模板匹配滤波后的理想参考峰响应：

```text
target_only_response_change_db
    = 20log10(A(processed_clean_target) / A(clean_target_signal))
```

接近 0 表示不改变 clean target；小于 0 表示削弱，大于 0 表示增强。

## 3. 实现方式

新增：

```python
evaluate_target_preservation(
    target_signal,
    processed_target,
    radar_config,
)
```

`validate_evaluation.py` 对每个 `Jammer×Algorithm×JSR×Seed` 执行两次算法：

1. 原始分支：`received=target+jammer+noise`；
2. target-only 分支：`Srt_matrix=clean target`。

两次 `radar_par` 都不包含 `target_idx`、`jam_info` 或真实 jammer signal。`Jammer` 名称只用于结果分组，不进入算法输入。

污染 received 分支的旧指标保留但改名为：

```text
processed_reference_response_vs_clean_db
```

该字段只用于诊断，不参与推荐结论。推荐规则改用 `target_only_response_change_db`。

## 4. v2 vs v3 区别

| 项目 | evaluation_v2 | evaluation_v3 |
|---|---|---|
| 结果目录 | `results/phase1/evaluation_v2/` | `results/phase1/evaluation_v3/` |
| case 数 | 3360 | 3360 |
| 目标保护指标 | contaminated target response | target-only response change |
| 旧参考指标 | `clean_target_response_loss_db` | `processed_reference_response_vs_clean_db` |
| 推荐依据 | contaminated clean loss | target-only response change |
| 逐 JSR | 有 | 有，保留并扩展 target-only CI |

v2 目录没有覆盖，v3 全部结果和原始 stdout 均已保存。

## 5. v3 结果摘要

| Jammer | Algorithm | 平均 delta SINR | target-only change | Pd after | 结论 |
|---|---|---:|---:|---:|---|
| `FMZuse` | WLN | +1.43dB | +1.75dB | 0.75 | Recommended |
| `FMZuse` | FrFT | -0.18dB | -0.34dB | 0.61 | Harmful/Not demonstrated |
| `AMNoiseGaiJam` | FDC | +0.05dB | 0.00dB | 0.61 | Neutral |
| `FMNoiseSaopin` | WLN | +5.83dB | +1.75dB | 1.00 | Recommended |
| `SMSP` | qpzh | +0.98dB | 0.00dB | 0.50 | Recommended |
| `NoiseProductJamming` | qpzh | +3.82dB | 0.00dB | 0.53 | Recommended |

Identity 的 target-only change 约为 0dB。`adapt_filter` 的 target-only change 约 -0.29dB，但仍因内部 `target_idx` 依赖标记为 `Blocked oracle-risk`，不参与公平推荐。

完整结果：

```text
results/phase1/evaluation_v3/metrics.csv
results/phase1/evaluation_v3/summary.csv
results/phase1/evaluation_v3/algorithm_matrix.csv
results/phase1/evaluation_v3/algorithm_jsr_matrix.csv
results/phase1/evaluation_v3/identity_baseline.csv
```

## 6. 推荐规则

`Recommended` 同时要求：

1. `mean(delta_SINR) > 0.2dB`；
2. delta SINR 95% CI 下界不低于 0；
3. `Pd_after >= Pd_before`；
4. `target_only_response_change_db > -1dB`。

污染分支的 `processed_reference_response_vs_clean_db` 不参与该规则。

## 7. 对算法排序影响

本任务没有修改任何算法，因此没有改变算法输出本身。评价排序会发生语义上的变化：原先可能把污染 received 中的残余 jammer 响应误认为目标损伤，v3 改用 clean target-only 响应后，目标保真度和抗干扰效果被分开报告。正式结论必须以逐 JSR v3 矩阵为准，不能把 v2 的旧字段与 v3 的新字段混用。

## 8. 是否发现目标损伤算法

在 target-only 分支中，FrFT 平均约 `-0.34dB`，adapt_filter 约 `-0.29dB`，说明这些算法存在可测的 clean target 响应变化；WLN 平均约 `+1.75dB`，表现为响应增强而非损伤。adapt_filter 因 oracle 风险不做公平结论。是否属于可接受损伤仍由逐 JSR 的 CI 和后续算法专项任务判断。

## 9. 验收结果

- target-only branch：满足；
- 不使用 oracle 信息：满足，算法输入不含 `target_idx/jammer signal/jammer type`；
- 输出 `target_only_response_change_db`：满足；
- Recommended 使用新指标：满足；
- `evaluation_v3`：3360 cases、接口通过率 100%；
- v2 未覆盖：满足；
- 未修改任何算法、jammer、JSR、RL 或 reward：满足。

## 10. Git

分支：`algorithm_design_0711`

主提交：`8d36689 phase1-033-fix2-target-preservation`
