# Task 033：建立 Phase 1 抗干扰算法评价契约

## 1. 当前评价问题

现有 `UnifiedEvaluator`/验证脚本主要返回单次 SINR 和检测状态，背景区域包含目标邻域，缺少目标峰损伤、全局峰偏移、假峰和计算成本。因此“代码运行”和“算法有效”没有被严格区分。

## 2. 指标定义

新增 `utils/evaluation.py`，统一输出：

- `sinr_before_db`、`sinr_after_db`、`delta_sinr_db`；
- `detected_before/after`，跨 seed 聚合为 `Pd`；
- 全局脉压峰 `peak_index`、`peak_error`、`range_error_m`；
- 目标窗口峰值变化 `target_peak_loss_db`；
- 目标窗口外 CA-CFAR 局部峰 `false_peak_count`、`true_false_peak_ratio`、`max_false_peak_db`；
- `runtime_ms`、`memory_usage_bytes`。

功率背景定义为脉压 profile 中排除目标参考窗口和 reference cells 后的平均平方幅度：

```text
SINR = 10 log10(target_peak_power / mean(background_power))
delta_SINR = SINR_after - SINR_before
target_peak_loss = 20 log10(A_after / A_before)
range_error_m = abs(peak_index - reference_peak) * C / (2 Fs)
```

检测使用幅度域 CA-CFAR：`alpha = sqrt(-4 log(Pfa) / pi)`。参考峰由理想目标数组与局部发射模板的匹配滤波峰推导，不从 `radar_par['target_idx']` 读取。

## 3. API 设计

```python
evaluate_algorithm_output(
    target_signal,
    received_before,
    processed_after,
    radar_config,
    runtime_ms=None,
    memory_usage_bytes=None,
)
```

该 API 不接收 jammer 类型、真实 jammer signal 或 `target_idx`。目标模板允许为局部 pulse 或 full receive-window target，内部统一到完整数组。

## 4. 修改文件列表

新增：

- `utils/evaluation.py`
- `validate_evaluation.py`
- `docs/tasks/033_evaluation_contract.md`
- `docs/reports/033_evaluation_contract_result.md`
- `docs/reports/phase1_blocked_issues.md`

修改：

- `docs/reports/phase1_progress.md`

未修改任何 jammer、抗干扰算法、JSR、reward、PPO、state 或动作空间。

## 5. 测试矩阵

正式命令：

```bash
./.venv/bin/python validate_evaluation.py --seeds 20 --output-dir results/phase1/evaluation
```

矩阵规模：`7 jammer × 6 algorithm × 4 JSR × 20 seed = 3360 cases`。

结果：`3360` cases，`168` summary rows，`42` jammer×algorithm rows，接口通过率 `100%`。

输出包括 `metrics.csv`、`summary.csv`、`identity_baseline.csv`、`algorithm_matrix.csv`、`algorithm_applicability_matrix.csv` 和 `oracle_check.csv`。

## 6. Identity 结果

| Jammer | Identity Pd |
|---|---:|
| `FMZuse` | 0.700 |
| `FMNoiseAimedJam` | 0.525 |
| `FMNoiseSaopin` | 1.000 |
| `AMNoiseGaiJam` | 0.513 |
| `SMSP` | 0.488 |
| `NoiseProductJamming` | 0.325 |
| `NoiseConvolutionJamming` | 0.363 |

完整 Identity 基线见 `results/phase1/evaluation/identity_baseline.csv`。

## 7. 当前算法性能矩阵

下表为跨 JSR/seed 的平均 `delta_SINR_dB`；完整 Pd、峰误差、假峰和目标峰损伤见 `algorithm_matrix.csv`。

| Jammer | WLN | FDC | adapt_filter* | FrFT | qpzh |
|---|---:|---:|---:|---:|---:|
| `FMZuse` | +1.43 | +0.00 | +18.14 | -0.18 | +1.43 |
| `FMNoiseAimedJam` | +1.25 | -0.00 | +22.35 | -0.24 | -1.17 |
| `FMNoiseSaopin` | +5.83 | +0.00 | +20.33 | -0.09 | +3.34 |
| `AMNoiseGaiJam` | +1.31 | +0.05 | +19.62 | -0.07 | +0.01 |
| `SMSP` | +1.34 | -0.00 | +26.00 | +0.01 | +0.98 |
| `NoiseProductJamming` | +1.88 | -0.02 | +22.29 | -0.05 | +3.82 |
| `NoiseConvolutionJamming` | +1.40 | +0.00 | +24.48 | -0.22 | -1.49 |

`adapt_filter*` 不能作为公平无 oracle 结果使用，见第 9 节。

## 8. PASS/FAIL 规则

- Interface Pass：无异常、shape 正确、无 NaN/Inf，并记录 runtime/内存；
- Recommended：平均 SINR 提升至少 0.2dB、Pd 不下降、目标峰损伤不低于 -1dB；
- Conditional：Pd 不下降且假峰数或峰误差改善；
- Neutral：SINR 近中性、Pd 不下降、目标峰未明显损伤；
- Harmful/Not demonstrated：Pd 下降、目标峰损伤过大或无有效指标改善；
- Interface FAIL：无法运行或输出非法。

这些分类只属于评价契约，不会修改算法或训练 reward。

## 9. 已发现问题

`validate_evaluation.py` 没有向任何算法传递 `target_idx`、`jam_info` 或真实 jammer signal；但 `adapt_filter_adapter` 内部仍会在缺少字段时注入 `target_idx=0`，核心投影依赖该值。因此：

- `oracle_check.csv` 标记 `adapt_filter_target_idx_dependency=True` 和 `blocked_for_fair_comparison`；
- `docs/reports/phase1_blocked_issues.md` 已记录；
- 矩阵保留 adapt_filter 运行结果，但不将其 +18~26dB 结果解释为公平算法优势；
- 本任务不修改 adapt_filter。

## 10. 回归测试

结果文件已保存到 `results/phase1/evaluation/`：

- `validate_no_jammer.py`：9/9 PASS；
- `validate_algorithms.py`：9/10 PASS，FMNoiseAimedJam/FrFT 失败；
- `run_correctness_tests.py`：内部 4 通过、1 警告、5 失败，包含既有 SliceCombine loader/FrFT 测试入口问题，以及统一 JSR 后的强干扰回归。

## 11. Task 033 验收结果

- 统一评价 API：满足；
- 统一指标输出：满足；
- Identity 基线：满足；
- 多 jammer/JSR/seed 矩阵：满足，3360 cases；
- algorithm applicability matrix：满足；
- 可区分接口可运行与性能有效：满足；
- oracle 风险已检查并记录；
- 未修改任何算法实现：满足。

## 12. Git

分支：`algorithm_design_0711`

Task 033 主提交：`d3933d3 phase1-033-evaluation-contract`
