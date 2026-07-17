# Task 036 Stage 1：Oracle 依赖与算法原理审计

## 结论

Stage 1 决策门为 **C：当前 adapt_filter 实现本质依赖目标模板的已知位置对齐**。这不等于预先判定所有 observable-only 重构不可行；它判定的是：删除 `target_idx` 后，当前 rank-one 投影不再是同一个公平算法。Stage 2 仍需通过固定 IQ、偏移和多目标位置实验验证敏感性，Stage 3 再设计独立的公平方案。

## 实际调用链

统一契约路径为：`utils.test_contract._whitelist_radar_par` → `get_antijam_func('adapt_filter')` → `adapt_filter_adapter` → `anti_jamming.adapt_filter.adapt_filter` → 输出 `(M,N)` IQ 与原 `St_base`。

适配器实际构造：

```python
adapted['St1'] = radar_par['St_base']
adapted['Srt_temp'] = radar_par['Srt_matrix']
adapted['target_idx'] = radar_par.get('target_idx', 0)
```

`utils.test_contract` 的公平白名单只保留 `C/f0/Bw/Pw/Fs/Tr/M/N/Srt_matrix/St_base`，所以公平调用并未传入 `target_idx`；但是 adapter 仍静默填充 `0`。统一框架和 RL 环境的 legacy 路径则把环境产生的真实 `target_idx` 保留在完整 `radar_par` 中，当前 RL action registry 仍包含 `adapt_filter`。

## 数学含义

在 `N_s=1000`、`N_r=5000` 时，核心以 `offset=max(0,target_idx-500)` 把短模板嵌入全长接收窗。然后以 `s` 表示嵌入后的模板，构造

\[
P_s=s^H(s s^H+\lambda)^{-1}s, \qquad y=rP_s.
\]

对于单脉冲和 `par1=0`，这是把接收 IQ 投影到对齐模板的 rank-one 信号子空间；`par1` 只改变投影缩放，`par2` 不参与计算。代码没有估计干扰协方差、没有训练子空间、没有 distortionless target constraint，也没有 confidence gating/fallback。因此它更准确地是“已知位置的目标模板投影”，而不是位置无关的自适应干扰子空间估计器。

## Oracle 分类

- `Srt_matrix`：`OBSERVABLE`；
- `St_base` 与公开 `C/f0/Bw/Pw/Fs/Tr/M/N`：`KNOWN_SYSTEM_PARAMETER`；
- 真 `target_idx`：`HARD_ORACLE`，决定模板时移；
- 缺失 `target_idx` 的默认 `0`：`SOFT_ORACLE/HIDDEN_ASSUMPTION`，形成固定接收位置假设；
- `target_dist`、`target_start_idx`、jammer label、`jam_info`、真实 jammer signal、requested/measured JSR：公平算法输入中的 `HARD_ORACLE_FORBIDDEN`；
- `par2`：`UNUSED_LEGACY_FIELD`；
- `test_adapt_filter` 和 `UnifiedEvaluator` 中的真实 `target_idx`：`ORACLE_EVALUATION_ONLY`，不能进入 fair fit/apply。

完整字段清单见 [dependency_inventory.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage1/dependency_inventory.csv) 和 [oracle_classification.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage1/oracle_classification.csv)。

## 目标损伤机制

正确 index 时，Phase 1 的目标脉冲区间为 `1000..1999`，与嵌入模板重合；错误 index 或默认 0 时，保留子空间移到窗口前部。因为 `y=rP_s` 会删除模板正交方向，真实目标被移出保留子空间后会被严重抑制，目标峰和 Pd 下降。这解释了 Task 034-fix3 中 8 个 adapt_filter rows 全部 `TARGET_ERASED` 的现象，但最终敏感性强度仍由 Stage 2 的同 IQ 实验确认。

## RL 影响范围

`rl_framework/config.py` 的 `antijam_list` 仍包含 `adapt_filter`，`decode_action` 仍解码其 `par1`，`AntiJamEnv.step` 仍将当前完整 `radar_par` 传给 adapter。Task 036 禁止修改 RL action space，因此本阶段只记录 removal requirement，不做删除。

## 代码修改与风险

Stage 1 未修改算法或其他运行代码。当前风险包括：核心主动分配 `N×N` 复投影矩阵，Phase 1 `N=5000` 时内存约 400 MB；`par2` 是名义参数；公平白名单虽阻止真值进入，但 adapter 默认 0 仍造成隐藏位置假设。

## 阶段证据

- [call_graph.md](/Users/jiangtao/anti_jamming/results/phase1/task036/stage1/call_graph.md)
- [math_model.md](/Users/jiangtao/anti_jamming/results/phase1/task036/stage1/math_model.md)
- [summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage1/summary.json)
- [Task 034-fix3 reference](/Users/jiangtao/anti_jamming/results/phase1/task034_fix3/performance_contract/performance_results.csv)
