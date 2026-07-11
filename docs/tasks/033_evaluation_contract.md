# Task 033：建立 Phase 1 抗干扰算法评价契约

## 目标

建立统一算法输出评价接口，统一计算 SINR、Pd、距离/峰误差、目标峰损伤、假峰和运行成本；加入 Identity 基线，区分“可运行”和“有效”。

## 输入边界

评价 API 只接收目标模板、before/after IQ 和 radar config，不接收 jammer 类型、真实 jammer 分量或环境 `target_idx`。算法矩阵调用同样不把这些信息放入 `radar_par`。

## 指标

```text
sinr_before_db, sinr_after_db, delta_sinr_db
detected_before, detected_after, Pd
peak_index, peak_error, range_error
target_peak_loss_db
false_peak_count, true_false_peak_ratio, max_false_peak_db
runtime_ms, memory_usage_bytes
```

目标参考峰由理想目标模板的匹配滤波峰推导，匹配滤波后的目标窗口外使用 CA-CFAR 和局部峰统计假峰。

## 矩阵

```text
7 jammers × 6 algorithms (Identity/WLN/FDC/adapt_filter/FrFT/qpzh)
× JSR [0,10,20,30] × 20 seeds = 3360 cases
```

## 禁止事项

不修改任何 jammer、抗干扰算法、JSR、reward、PPO、state 或动作空间；不执行 Task 034。
