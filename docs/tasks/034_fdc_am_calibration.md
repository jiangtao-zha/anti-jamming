# Task 034：FDC 与 AMNoiseGaiJam 专用抗干扰校准

## 目标

验证并校准 `FrequencyDomainCanceller` 对 `AMNoiseGaiJam` 的理论匹配，使用 Task 033-fix2 的统一评价指标，比较 Identity、当前 FDC 和改进 FDC。

## 范围

- 允许修改 FDC 实现、FDC 参数、FDC 测试脚本和 Task 034 报告。
- 禁止修改 jammer、JSR、radar config、evaluation、RL、reward、state 和 action space。
- FDC 不得接收 `target_idx`、`jammer_signal` 或 `jammer_type`；允许使用接收 IQ、雷达模板和物理配置。

## 实验矩阵

- AM 主场景：`AMNoiseGaiJam`，JSR `0/10/20/30 dB`，至少 20 seeds。
- 非目标负测试：`FMZuse`、`FMNoiseAimedJam`、`NoiseProductJamming`。
- 算法：`Identity`、`Current_FDC`、`New_FDC`。
- 指标：delta SINR、Pd、peak error、false peak、`target_only_response_change_db`、runtime。

## 输出

结果写入 `results/phase1/fdc/`，分为 `baseline/`、`parameter_search/`、`am_results/`、`negative_results/` 和 `final_matrix.csv`。初始分析写入 `docs/reports/034_fdc_initial_analysis.md`，最终结果写入 `docs/reports/034_fdc_am_calibration_result.md`。

## 验收

AM 场景相对 Identity 有稳定改善、Pd 不下降且目标-only 响应变化大于 -1 dB；非 AM 场景无明显目标损伤或假峰异常；报告记录参数搜索、代码事实、测试命令和未解决风险。
