# Task 036：adapt_filter 公平性重构与最终结果

## 1. 目标与边界

目标是审计 `adapt_filter` 的 oracle 依赖，设计 observable-only fair prototype，在冻结的数据契约下完成 calibration 与 held-out，最后决定是否进入 RL。任务明确禁止修改 jammer、JSR、evaluation contract、FDC、WLN、FrFT、qpzh、FSTP、RL/PPO、reward、state 和 action space；本任务遵守该边界。

## 2. 当前算法数学与调用链

当前核心计算为

```text
St1 = radar_par['St1']
Srt_temp = radar_par['Srt_temp']
s = aligned target template selected with target_idx
Ps = sᴴ (s sᴴ + par1 I)^−1 s
y = r Ps
```

在当前 `M=1` 的实际路径中，这是把记录投影到一个由已知、已对齐目标模板构造的 rank-one 子空间。调用链为 `rl_framework/config.py → adapters.get_antijam_func('adapt_filter') → adapt_filter_adapter → anti_jamming/adapt_filter.py`；adapter 会无条件构造 `target_idx=radar_par.get('target_idx', 0)`，缺失时静默退到 0。因而 full radar path 可暴露真值，公平白名单则会落入错误默认位置。Stage 1 静态 audit、Stage 2 固定 IQ 偏移/缺失索引/多位置结果共同确认 `C_CURRENT_ALGORITHM_REQUIRES_TARGET_ALIGNMENT_ORACLE`。

## 3. Sensitivity 与位置依赖

Stage 2 使用 NPJ、NCJ、NoJammer、AMNoiseGaiJam、FMNoiseAimedJam、JSR `0/10/20/30dB`、seeds `5000..5019`、五个目标中心和真值/偏移/固定 0/缺失模式。Active core 与代数等价实现的 spot check 最大归一化差异为 `7.77e-15`。真值对齐时 NPJ JSR=10 约 `+21.25dB`，错误偏移扩大到 ±32 后转为约 `-3.64/-9.86dB`，固定 0/缺失约 `-9.11dB`；中后部目标位置还出现 target erase。这不是可接受的 fair 输入行为。

## 4. Fair 设计与原型

Stage 3 评估了四个方向：A 为 observable-only Top-K 延迟估计加受保护 rank-one projection；B 为多假设 observable-only projection 加 stability selection；C 为 Hankel robust covariance/constraint 探索项；D 为正式拒绝/保留 Oracle。由于当前 `M=1`，C 的协方差收益无法确认；选 A/B 做隔离 prototype，保留 mandatory Identity fallback、fit/apply 分离和禁止字段检查。Stage 4 在 5 个 jammer、JSR `0/10/20/30`、10 seeds、三个位置上完成 600 cases、2,400 rows，接口失败、Oracle 输入失败和 fair target erase 均为 0。

## 5. Calibration

Stage 5 预先去重得到 16 个候选（A 8、B 8，少于 40 上限），使用 target jammer NPJ/NCJ、负控 NoJammer/AMNoiseGaiJam/FMNoiseAimedJam/FMNoiseSaopin/SMSP、JSR `0/5/10/20/30`、seeds `7000..7029` 和五个位置，共 84,000 raw rows。16 个候选均接口通过、Oracle input 通过、TARGET_ERASED=0，NoJammer target-only response 约为零；但目标 jammer 高 JSR 的位置 spread 约 `10.21dB`，超过 `<5dB`，因此 `calibration_qualified_count=0`。排名第一的 `A_k3_c0.05_r0.001` 仅作为冻结的 held-out 拒绝确认对象，不是候选。

## 6. Held-out

Stage 6 使用完全分离的 seeds `8000..8049`，8 个 jammer、4 个 JSR、5 个位置和 Identity/Oracle/Fair 三类对象，共 24,000 条逐试验记录、480 个聚合组。所有接口均通过；Fair target-only `TARGET_ERASED=0`，NoJammer target-only change 为 `-8.69e-06dB`；独立 Oracle 目标保真也无 erase，约 `-8.69e-05dB`。

NPJ/NCJ 的 Fair Delta SINR 在 JSR=10dB 仍为正（分别 `19.397/21.085dB`），但 JSR=20/30dB 分别为 `-8.845/-12.279dB` 和 `-10.239/-15.166dB`。Fair 的位置 spread 为 `12.5568dB`，再次超过 `<5dB` 门槛；Oracle upper bound 在这些条件下约为 `21.6–30.4dB`，只用于上界对照，不是公平结论。

## 7. 目标保护、估计器、fallback 与负控

Fair prototype 没有目标擦除，目标-only 保护和 Identity fallback 门通过；held-out 中 fallback 计数为 0，说明该冻结候选确实在尝试 observable estimation，而不是靠 Identity 伪造通过。负控显示没有明显 target-only 损伤，但目标 jammer 高 JSR 的性能与位置鲁棒性仍失败，因此负控不能替代目标场景资格门。

## 8. RL 与 candidate matrix

最终决策为 `ORACLE_UPPER_BOUND_ONLY`：`adapt_filter` 保留为显式 Oracle upper bound / legacy baseline；`anti_jamming/adapt_filter_fair.py` 作为隔离研究代码保留，`fair_algorithm_registered=false`、`candidate_matrix_eligible=false`、`rl_eligible=false`。RL action space、PPO、reward、state 和 registry 均未修改。observable-only fallback 为 Identity。未开始长时间训练。

## 9. 风险与未解决问题

- Fair A/B 在本任务矩阵中行为接近，无法证明设计间优越性。
- 当前 `M=1` 仍不足以验证多脉冲/协方差型设计。
- legacy `adapt_filter` 的 registry 条目仍存在，但已在本任务结果中标为 Oracle-only；未来是否移除或重标必须另开任务。
- 既有 SliceCombine/FrFT/FSTP/RL 相关 blocked issue 未在本任务扩大修复。

## 10. 交付物与 Git

阶段提交依次为：`9853ded`、`8cc4662`、`0d9ea1e`、`d2bb5a8`、`22cb399`、`b623a01`、`47efff3`、`e389085`、`c0bdbcd`、`421c3ea`、`4eda312`、`4dad3e9`；最终 push 的远端 SHA 在 [git_remote_verification.txt](/Users/jiangtao/anti_jamming/results/phase1/task036/git_remote_verification.txt) 中记录。分支为 `algorithm_design_0711`。阶段清单、决策日志、stdout/stderr、原始 CSV/JSON 和复现实验入口均已保存。
