# Algorithm Reconstruction Progress

## Summary

Goal 022 的目标是先修复单脉冲接收端抗干扰算法的理论一致性，再进入 RL 重训。当前严格遵循阶段顺序，暂不修改 `rl_framework/`、PPO、reward、环境建模，以及暂缓的 FSTP/RGPO/Frequency Agile/Wave Agile。

## Current Phase

**Phase 5：综合算法矩阵验证与最终报告准备**

Phase 0 记录系统已建立。Phase 1 adapt_filter 审查、Phase 2 FDC 重构、Phase 3 FrFT 重构和 Phase 4 时域切片重构均已完成，当前进入综合矩阵验证与最终报告准备。

## Completed

- Phase 0：创建本进度记录文件。
- Phase 1：完成 adapt_filter 审查，确认 `target_idx`/理想模板 oracle 依赖，并完成三 seed 对照实验。
- Phase 2：active FDC 改为基于基带 improper/AM 伪协方差特征、共轭对称分量估计和软抵消；不再使用 `target_idx` 或模板频谱差值。
- Phase 3：FrFT 改为基于接收观测的活动窗口估计，同时扫描模板与接收窗口的 FrFT 集中特征；使用目标 chirp 阶数构建局部软掩膜，不再读取 `target_idx`。
- Phase 4：`qpzh` 改为基于接收匹配峰估计活动窗口、局部相干度检测和时域模板重构；不再进行频谱分段抑制，也不读取 `target_idx`。
- 已完成 Task 020 仓库状态审计和 Task 021 算法理论缺口分析。

## In Progress

- 准备综合算法矩阵验证，重点区分“接口/理论修复”和“性能优于 identity”；Phase 5 尚未修改代码。

## Pending

- Phase 2：FDC 理论重构。
- Phase 3：FrFT 目标/干扰斜率分离。
- Phase 4：SliceCombine/ISDJ 时域结构处理。
- Phase 5：综合算法矩阵验证和最终报告。

## Experiment Results

Phase 1：JSR=20dB、NoiseProductJamming/NoiseConvolutionJamming、seed=[42,123,456]。

- identity：SINR 均值分别为 5.289dB、7.073dB。
- 带 `target_idx` 的当前 projection：两类均为约 11.462dB，检测 3/3。
- 去掉 `target_idx` 的 projection：两类均为约 9.744dB，检测 0/3。
- 详细过程和限制见 `docs/reports/022_adapt_filter_audit.md`。
- 该实验只证明 oracle 敏感性，不把去掉 `target_idx` 的简单版本当作最终公平算法。

Phase 2：AM/非 AM 对照，JSR=20dB、seed=`42 + trial*1000`、10 trials。

| 干扰 | identity SINR | 旧 active FDC | 新 active FDC | 新 FDC Pd |
|---|---:|---:|---:|---:|
| `AMNoiseGaiJam` | 10.074 ± 0.447dB | 11.101 ± 0.328dB | **10.584 ± 0.397dB** | 100% |
| `FMNoiseAimedJam` | 7.728 ± 1.516dB | 7.922 ± 1.643dB | 7.741 ± 1.515dB | 30% |

- 新 FDC 相对 identity 在 AM 场景平均提升约 `+0.510dB`。
- 非 AM FM 场景与 identity 基本一致，AM 置信度门控未造成明显额外损失。
- 新 FDC 暂时低于旧 active FDC，失败/性能差异已保留，不能宣称已优于旧实现。
- `validate_algorithms.py` 重新运行结果为 `10/10 PASS`，其中 AMNoiseGaiJam/FDC 平均改善 `+0.04 ± 0.05dB`；该脚本判定宽松，不能替代 Phase 2 对照实验。

Phase 3：JSR=20dB、seed=[42,123,456,789,1024]，比较 identity、FrFT 和 adapt_filter。

| 干扰 | identity SINR | 新 FrFT SINR | 新 FrFT Pd | 说明 |
|---|---:|---:|---:|---|
| `SMSP` | 7.590 ± 0.032dB | 7.321 ± 0.028dB | 0% | 接收窗口最佳阶数与目标阶数分离，但当前软掩膜仍损失目标/未恢复检测 |
| `FMNoiseSaopin` | 11.468 ± 0.032dB | 11.169 ± 0.026dB | 100% | 保持检测，SINR 有约 0.30dB 负收益 |

- FrFT 代码语义已从“全记录模板 + `target_idx` oracle”改为“匹配滤波估计活动窗口 + 模板/接收阶数扫描”。
- 该阶段未宣称性能优于 identity；现有结果说明阶数差异检测已经进入处理链，但掩膜设计仍需在 Phase 5 的矩阵验证中继续校准。
- `validate_algorithms.py` 仍为 `10/10 PASS`，其中原有 FMNoiseAimedJam/FrFT 配对为 `-0.28 ± 0.06dB`；PASS 仅表示未触发宽松阈值。

Phase 4：JSR=20dB、seed=[42,123,456]，比较 identity 与新的时域 `qpzh`。

| 干扰 | identity SINR | 新 `qpzh` SINR | 差值 | 结论 |
|---|---:|---:|---:|---|
| `SMSP` | 7.605dB | 9.052dB | +1.448dB | 局部相干度切片重构产生正向收益 |
| `ISDJ` | 9.613dB | 7.707dB | -1.906dB | 转发片段与目标模板相干，当前判别误重构 |

- Phase 4 已完成代码层面的时域化，但不能宣称 ISDJ 已解决；当前环境把多次转发压在单条观测中，不能用该结果证明慢时间算法有效。
- `SliceCombineJam` 仍存在统一 loader/参数接口问题，本阶段没有修改 jammer 构造函数或环境建模；其专用矩阵验证需单独修复接口后进行。

## Known Issues

- 当前统一物理基线与 RL 默认 `Pw/Fs` 不一致。
- 当前 `adapt_filter` 通过 `target_idx` 对齐短模板；该信息不是接收端自然观测量，后续应区分 oracle/estimated/no-align 三种基线。
- 当前 `adapt_filter` 实际构造 `N×N` 投影矩阵，N 较大时有内存风险。
- Phase 2 已完成；后续不得把 FDC 与 FrFT 阶段混改。
- 新 FDC 仍需在更高 JSR、不同 AM 带宽和非 AM 负控下扩展验证；当前 10 seed 结果只完成最小验收。
- 新 FrFT 仍需改进目标保真与 SMSP 处理收益；当前结果只能证明无 `target_idx` 的可运行实现和接收阶数分析，不足以证明专用算法优于通用基线。
- 新 `qpzh` 的 ISDJ 误检/误重构仍未解决，需要在最终矩阵中记录局部相干度、重构片段比例和目标保真度。
- Phase 5 需要覆盖所有 active 算法的无 oracle 检查、统一接口检查、identity 对照和现有验证脚本；完成后才能判断 Goal 022 是否可结束。
