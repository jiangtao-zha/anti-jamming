# Task 036-fix Stage C：有效 Confidence 与 Identity Gating

## 旧定义的问题

旧 A 方案将 `response[best] / max(response)` 作为 `peak_confidence`。因为 `best` 本来就是 response 最大峰，该量天然接近 1，`0.05/0.12` 的阈值几乎不会触发 fallback。Stage C 没有沿用这个定义。

## 新定义

fair 模块现在固定使用五个仅由接收 IQ、已知模板和公开参数得到的组件，每个组件均裁剪到 `[0,1]`：

| 组件 | 权重 | 含义 |
|---|---:|---|
| peak-to-background | 0.25 | 峰值相对候选外背景中位数的可观测优势 |
| top-1/top-2 margin | 0.25 | 第一候选与第二候选的相对间隔 |
| peak prominence | 0.20 | `find_peaks` 峰 prominence 相对峰值 |
| peak-width consistency | 0.15 | 接收匹配峰宽度与模板自相关峰宽度的一致性 |
| local-to-global | 0.15 | 候选局部响应能量占全局响应能量 |

综合 confidence 为固定加权和，默认 threshold 为 `0.80`。模板自相关只由 `St_base` 计算，不使用真实目标位置。

## Gating

满足任一条件时返回原样 Identity：confidence 低于阈值、无候选峰、候选靠近合法中心边界、condition number 非法/过大、输出 matched-response proxy 非有限或低于 `0.05`。返回状态统一为 `FALLBACK_IDENTITY_*`，并保留 `confidence_components`、`gate_reasons`、估计位置和 evaluation-only 误差字段。

## Gating 有效性测试

测试包含 clean target、NPJ JSR=0/10/30、NoJammer、false-peak-dominant、双峰 ambiguity 和 pure noise，共 8 类 × A/B = 16 trials。接口失败为 0，所有 confidence components 均在 `[0,1]`。clean/NoJammer 和低 JSR 场景可通过；高 JSR、双峰 ambiguity 与 pure noise 触发 fallback；false peak 主导时可观测 confidence 很高但估计误差为 2000 samples，明确记录为“高置信错误候选”，说明 confidence 是可解释的观测一致性而非评价真值。

总 fallback 为 `8/16=0.5`，既不是恒为 0，也不是恒为 1。各 case 的 fallback 分布、confidence、估计误差和 gate reason 见 [confidence_cases.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageC/confidence_cases.csv) 与 [fallback_analysis.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageC/fallback_analysis.csv)；组件明细见 [confidence_components.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageC/confidence_components.csv)。

## 阶段决策

`GATING_DESIGN_PASS`：fallback ratio 在 `(0,1)`，无 forbidden input、无接口失败，进入 Stage D。高置信 false peak 的风险保留给后续物理 fixture calibration/held-out 拒绝确认，不用评价标签在 fit 阶段修正。
