# Goal 022：抗干扰算法层修复与基线重构最终报告

## 1. 任务结论

Goal 022 的单脉冲接收端算法重构阶段已执行到综合验证，完成了：

- `adapt_filter` oracle 依赖审查；
- active FDC 的 AM 特征驱动重构；
- active FrFT 的接收窗口与 chirp 阶数分析重构；
- `qpzh` 的时域切片相干度检测与模板重构；
- 统一验证脚本和阶段性对照实验。

结论不是“所有专用算法都已优于 identity”。当前实现已消除三处 active 算法对 `target_idx` 的直接依赖，但 FrFT 和 qpzh 仍有明确的负收益场景，不能直接开始 RL 重训或宣称算法理论已经完全闭环。

## 2. 实际修改内容

### 2.1 adapt_filter 审查

未重写 `adapt_filter`。确认其在 `anti_jamming/adapt_filter.py` 中使用 `target_idx` 对齐短模板并构造投影矩阵，因此它应作为 oracle/known-template baseline 单独标记，不能作为无先验公平基线。

### 2.2 FDC

文件：`anti_jamming/adapters.py:fdc_adapter`

- 下变频到已知雷达载频基带；
- 计算 pseudo-covariance 与 improperness ratio；
- 构造相位对齐的共轭对称 AM 分量；
- 在目标带宽保护因子下进行软抵消；
- 不再使用 `target_idx` 或模板频谱差值。

### 2.3 FrFT

文件：`anti_jamming/adapters.py:frft_adapter`

- 通过接收信号与发射模板的匹配滤波峰估计活动窗口；
- 扫描模板 FrFT 阶数，得到目标 chirp 阶数；
- 扫描接收活动窗口，获得接收信号最佳集中特征及阶数分离度；
- 在局部窗口应用目标阶数的软掩膜；
- 不读取环境的 `target_idx`。

### 2.4 qpzh

文件：`anti_jamming/adapters.py:qpzh_adapter`

- 从频谱分段抑制改为时域活动窗口估计；
- 按 `m*n` 分片计算局部归一化相干度；
- 对低相干片段使用全窗口复增益乘模板进行重构；
- 多脉冲矩阵按行独立处理，不虚构慢时间信息；
- 不读取 `target_idx`。

## 3. 阶段提交

当前分支：`algorithm_design_0711`

相关提交：

- `bb27f65 022-step1-audit-adapt-filter`
- `d4e72aa 022-step2-rewrite-fdc`
- `26bdbd1 022-step3-rewrite-frft`
- `17322a7 022-step4-reconstruct-time-domain-slices`

## 4. 验证结果

### 4.1 FDC 对照

JSR=20dB、10 trials：

| 干扰 | identity | 新 FDC | 新 FDC Pd |
|---|---:|---:|---:|
| `AMNoiseGaiJam` | 10.074 ± 0.447dB | 10.584 ± 0.397dB | 100% |
| `FMNoiseAimedJam` | 7.728 ± 1.516dB | 7.741 ± 1.515dB | 30% |

AM 场景有约 `+0.51dB` 平均收益，非 AM 场景基本保持 identity。新 FDC 仍低于旧 active FDC 的 AM 结果，不能宣称已经达到最优。

### 4.2 FrFT 对照

JSR=20dB、5 seeds：

| 干扰 | identity | 新 FrFT | Pd |
|---|---:|---:|---:|
| `SMSP` | 7.590 ± 0.032dB | 7.321 ± 0.028dB | 0% |
| `FMNoiseSaopin` | 11.468 ± 0.032dB | 11.169 ± 0.026dB | 100% |

阶数分析已进入代码路径，但当前掩膜会损失目标保真，尚未形成正收益算法。

### 4.3 qpzh 对照

JSR=20dB、3 seeds：

| 干扰 | identity | 新 qpzh | 差值 |
|---|---:|---:|---:|
| `SMSP` | 7.605dB | 9.052dB | +1.448dB |
| `ISDJ` | 9.613dB | 7.707dB | -1.906dB |

SMSP 的时域相干度切片重构有收益；ISDJ 中转发片段与目标 LFM 高度相干，当前检测会误重构。

### 4.4 现有测试脚本

- `validate_algorithms.py`：`10/10 PASS`。该脚本的 PASS 阈值较宽松，不能证明专用算法优于 identity。
- `run_correctness_tests.py`：实际汇总为 5 项通过、1 项警告、4 项失败。
  - 失败：`FastSlowTimeProcessor` 三组因 `SliceCombineJam.__init__()` 不接受 `Fs`；FrFT 因缺少 `test_frft_filter`。
  - 警告：暂缓修改的 `wave_agile` 在 RGPO 上平均 SINR 下降约 `2.94dB`。

## 5. 未解决问题与风险

### 已确认

- `adapt_filter` 仍然是 oracle-sensitive 算法，不能直接用于公平 RL 算法比较。
- RL 默认物理参数仍与统一基线不一致；Goal 022 没有修改 `rl_framework/`。
- `SliceCombineJam` 标准 loader 仍不可用，且其默认物理参数偏离统一基线。
- 环境仍将多次转发/多脉冲干扰压为单脉冲，不能据此评价 FSTP 的慢时间能力。
- FrFT 和 qpzh 虽已进入正确的数据域，但仍存在负收益场景。

### 暂未确认

- 新 FDC 在不同 AM 带宽、JSR=30dB 和更强非 AM 负控下的稳定性。
- 新 FrFT 如何在目标保真和 SMSP 抑制之间选择掩膜强度。
- ISDJ 是否需要可观测的转发延迟/片段周期估计，才能避免把相干转发误判为目标。
- 所有 8 种算法在统一无 oracle 参数和完整矩阵下的最终排序。

## 6. 后续建议

1. 单独创建 SliceCombineJam 接口与物理参数修复任务，修复后再做时域算法矩阵。
2. 为 FrFT 增加目标保真度、局部重构比例和检测率约束，不只优化 SINR。
3. 为 qpzh 增加 ISDJ 的局部相干/延迟结构特征，避免仅用模板相干度判别。
4. 重新定义 `run_correctness_tests.py` 的 FrFT 测试入口，补齐缺失的 `test_frft_filter` 或改为统一 adapter 测试。
5. 在上述问题审查通过前，不开始 RL 重训；暂不修改 reward、动作空间和环境模型。
