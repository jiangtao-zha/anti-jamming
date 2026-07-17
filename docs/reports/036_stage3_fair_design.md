# Task 036 Stage 3：Observable-only 公平方案设计

## 设计门结论

Stage 3 已完成。当前 legacy `adapt_filter` 不被覆盖；它继续作为 Oracle upper bound/legacy baseline。基于 Stage 1 数学审计和 Stage 2 固定 IQ 敏感性证据，提出三个真正 observable-only 的公平方向，并额外保留正式拒绝选项：

1. **A：Top-K observable delay estimator + protected rank-one projection**。从 `Srt_matrix` 与 `St_base` 的 matched-filter 峰、峰形、chirp 相位一致性和局部支持度产生候选位置；只用 observable score 估计置信度。选中候选后以模板投影保留已知目标方向，低置信度/病态时 Identity fallback。
2. **B：Observable multi-hypothesis projection with stability selection**。保留多个候选位置并分别生成受保护输出；用输出模板相关度、有限性、条件数、假峰代理和对小位置扰动的稳定性做无真值选择，不用评价 peak error/Pd 选候选。
3. **C：Hankel robust covariance with template-protection constraint**。不依赖单一目标位置，利用滑动/Hankel 数据矩阵、robust covariance、diagonal loading 与 `wᴴs=1` 的模板保护约束估计干扰子空间。该方向理论上更位置无关，但冻结实验为 `M=1`，统计支持不足且数值风险高。

正式拒绝选项 D 为：不实现伪公平版本，只保留 current implementation 作为 `ORACLE_UPPER_BOUND_ONLY`，Identity 作为安全 fallback，并把 RL removal requirement 留给后续任务。

## 评分与选择

评分维度为 Fairness、Target protection、Jammer separability、Position robustness、Implementation risk、Numerical stability、Runtime、Interpretability，详见 [design_scores.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage3/design_scores.csv)。选择 A、B 进入 Stage 4；C 作为记录完整的 research-only 方向不进入本任务原型；D 保留为最终可能结论。

选择 A/B 的原因是：两者都能在不读取真值的条件下显式记录 estimated position/confidence、执行 fit/apply 分离、保护模板方向并在低置信度时回退 Identity；A 偏向单一可解释候选，B 偏向多假设稳定性。C 虽不需要单一目标位置，但在单脉冲 `M=1` 条件下无法可靠支撑高维 covariance，不能在未验证前冒充可行方案。

## 共同公平输入契约

允许输入：`C/f0/Bw/Pw/Fs/Tr/M/N/Srt_matrix/St_base`。禁止输入：`target_idx`、`target_start_idx`、`target_dist`、`target_range`、jammer label、`jam_info`、真实 jammer signal、requested/measured JSR 和评价真值。候选位置必须由接收 IQ 独立估计，不能用真实位置修正。

## 目标保护与 fit/apply

- A/B 的 fit 返回候选位置、置信度、投影/模型系数、条件数、正则化和诊断信息；apply 只使用 fit 返回模型，不读取评价字段。
- 不允许直接使用 `I - ssᴴ/(sᴴs)` 把目标模板投影掉；若使用模板投影，必须保留模板方向或采用 distortionless/保护约束。
- confidence 低、候选对小偏移不稳定、矩阵病态、模板能量为零、输出非有限时，输出 Identity 并记录 fallback。

## 阶段决策

Stage 4 gate 为 `OPEN_FOR_ISOLATED_PROTOTYPES_A_AND_B`。这不是对公平候选的预判；Stage 4 smoke、Stage 5 calibration 和 Stage 6 held-out 必须继续以 Identity、Oracle upper bound 和冻结 fair candidate 进行比较。若 A/B 均不能过 calibration gate，仍应走 D 的 `ORACLE_UPPER_BOUND_ONLY` 结论。

## 证据

- [design_candidates.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage3/design_candidates.csv)
- [design_scores.csv](/Users/jiangtao/anti_jamming/results/phase1/task036/stage3/design_scores.csv)
- [selected_designs.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage3/selected_designs.json)
- [summary.json](/Users/jiangtao/anti_jamming/results/phase1/task036/stage3/summary.json)
