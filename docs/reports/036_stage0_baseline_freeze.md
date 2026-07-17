# Task 036 Stage 0：Baseline Freeze

## 状态

Stage 0 已完成。冻结点为分支 `algorithm_design_0711`、HEAD `4c6823616ab2dba82feebf1575e7d08a42ecfc4a`。工作区原有的 `.codex/` 和 `docs/tasks/phase1_master_plan.md` 未跟踪修改被保留，未纳入 Task 036。

## 冻结的公共基线

Phase 1 雷达配置来自 `configs/phase1_radar.py`：`C=3e8`、`f0=15MHz`、`Bw=5MHz`、`Pw=20us`、`Fs=50MHz`、`Tr=100us`、`M=1`、`N=5000`、`target_dist=6000m`、`target_start_idx=1000`、`target_idx=1500`、`JSR=10dB`。Identity 定义为原样返回 `Srt_matrix` 与 `St_base`。

## Current adapt_filter 冻结

当前 adapter 是 `anti_jamming/adapters.py:adapt_filter_adapter`，核心是 `anti_jamming/adapt_filter.py:adapt_filter`。adapter 将 `St_base` 映射为 `St1`、将 `Srt_matrix` 映射为 `Srt_temp`，并无条件执行：

```python
adapted['target_idx'] = radar_par.get('target_idx', 0)
```

核心在模板长度与接收长度不同时用 `target_idx` 计算时移；随后构造

```text
Ps = sᴴ (s sᴴ + par1)^-1 s
y = r Ps
```

因此它保留的是接收信号在已对齐发射模板方向上的投影，而不是在不知道目标位置时估计干扰子空间。`par1` 是标量正则项，`par2` 在当前核心实现中不改变该投影逻辑。

当公平输入移除 `target_idx` 时，adapter 默认为 0；长度为 1000 的模板被放置到接收索引 `0..999`，而 Phase 1 目标实际位于 `1000..1999`。这是隐藏位置假设与目标错位风险的冻结证据。

## Task 034-fix3 参考结果

`results/phase1/task034_fix3/performance_contract/performance_results.csv` 中 adapt_filter 共 8 行（NoiseProductJamming/NoiseConvolutionJamming × JSR 0/10/20/30）。所有行均为 `BLOCKED_ORACLE`、`fair_ranking_eligible=False`、`TARGET_ERASED`、`pd_algorithm=0.0`；平均 Delta SINR 为 `-50.80` 至 `-30.73dB`。这些结果只作为 legacy/fallback 行为的诊断证据，不进入公平排名。

## 阶段决策

1. 保留 current adapt_filter 作为 `ORACLE_UPPER_BOUND / LEGACY BASELINE`，不覆盖、不注册为公平算法。
2. Fair adapt_filter 在冻结点状态为 `NOT_IMPLEMENTED`。
3. Stage 1 必须继续完成调用链、数学形式、Oracle 分类和隐式默认位置审计；Stage 2 必须用同一 IQ 的偏移/缺失位置实验验证敏感性。

## 证据文件

- [baseline_metadata.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage0/baseline_metadata.json)
- [git_status.txt](/Users/jiangtao/anti_jamming/results/phase1/task036/stage0/git_status.txt)
- [file_hashes.txt](/Users/jiangtao/anti_jamming/results/phase1/task036/stage0/file_hashes.txt)
- [task034 performance results](/Users/jiangtao/anti_jamming/results/phase1/task034_fix3/performance_contract/performance_results.csv)

## 未修改范围

Stage 0 未修改 jammer、JSR 定义、评价契约、FDC、WLN、FrFT、qpzh、FSTP、RL 环境、PPO、reward、state 或 action space。
