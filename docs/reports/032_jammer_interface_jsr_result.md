# Task 032：统一 Phase 1 干扰接口与 JSR 定义

## 1. 修改前问题

Task 030/031 已确认各 jammer 在内部自行解释和缩放 JSR：不同模型使用脉内功率、完整数组功率或模型专用中间量，返回值通常只有复合信号，无法直接复核独立 jammer 功率。因此同样写成 `JSR=20dB` 不保证跨模型公平。

## 2. 修改方案

新增 `utils/jammer_interface.py` 的 `Phase1JammerAdapter`：

1. 以 legacy `JSR=0` 调用物理模型，保留模型原有波形结构；
2. 从 legacy `target_signal`、`noise_signal` 和 composite 提取 raw jammer；
3. 调用 `utils/jsr_validation.scale_to_jsr()` 统一缩放；
4. 返回 `target/jammer/noise/received/requested_jsr_db/measured_jsr_db/metadata`；
5. 保留旧 `generate(R_target=..., JSR_dB=..., noise_var=...)` 三元组接口，避免扩大 Task 032 的调用链变更。

`JammerLoader` 仅对 7 个纳入范围的 jammer 返回 wrapper；RGPO、ISDJ、SliceCombineJam 仍走原有路径。

## 3. JSR 数学定义

```text
P(x) = mean(abs(x[n])**2)
JSR_dB = 10*log10(P(jammer) / P(target))
P_jammer_target = P(target) * 10**(requested_jsr_db/10)
alpha = sqrt(P_jammer_target / P(raw_jammer))
scaled_jammer = alpha * raw_jammer
received = target + scaled_jammer + noise
```

功率在完整、等长、含零填充的接收数组上计算；噪声不计入 JSR 分子。

## 4. 修改文件列表

### 新增

- `utils/__init__.py`
- `utils/jsr_validation.py`
- `utils/jammer_interface.py`
- `validate_jsr.py`
- `docs/tasks/032_unify_jammer_interface.md`
- `docs/reports/032_jammer_interface_jsr_result.md`

### 修改

- `unified_framework.py`：7 个 Phase 1 jammer 接入 wrapper；`RadarEnvironment.generate_with_jammer()` 使用组件化接口，保留暂缓 jammer 的 legacy 分支。
- `docs/reports/phase1_progress.md`：记录 Task 032 状态。

### 未修改

- 7 个 jammer 的物理模型公式、内部结构和噪声模型；
- RGPO、ISDJ、SliceCombineJam；
- 所有抗干扰算法、reward、PPO、动作空间、state 和雷达参数。

## 5. 七种 jammer 验证矩阵

测试配置：

```text
Jammers = 7
JSR = [0, 10, 20, 30] dB
Seeds = 42..51，共 10 个
总 case = 7 * 4 * 10 = 280
```

结果文件：

```text
results/phase1/jammer_validation/jsr_measurement.csv
results/phase1/jammer_validation/power_statistics.csv
results/phase1/jammer_validation/failed_cases.csv
```

## 6. JSR 测量结果

| Jammer | Cases | 最大绝对误差 | 最小时域相关 | 最小频谱相关 |
|---|---:|---:|---:|---:|
| `FMZuse` | 40 | 3.6e-15 dB | 0.9999999999999957 | 0.9999999999999998 |
| `FMNoiseAimedJam` | 40 | 3.6e-15 dB | 0.9999999999999976 | 0.9999999999999998 |
| `FMNoiseSaopin` | 40 | 3.6e-15 dB | 0.9999999999999957 | 0.9999999999999997 |
| `AMNoiseGaiJam` | 40 | 1.8e-15 dB | 0.9999999999999977 | 0.9999999999999998 |
| `SMSP` | 40 | 0 dB | 0.9999999999999977 | 0.9999999999999998 |
| `NoiseProductJamming` | 40 | 3.6e-15 dB | 0.9999999999999977 | 0.9999999999999997 |
| `NoiseConvolutionJamming` | 40 | 3.6e-15 dB | 0.9999999999999977 | 0.9999999999999998 |

总结果：`280/280` 成功，最大绝对误差 `<0.2dB`，失败案例 CSV 只有表头。

## 7. 特殊干扰检查

- `NoiseProductJamming`：乘积干扰先按 legacy 输出拆分，统一缩放后测得 JSR 精确；噪声功率不进入 JSR 分子。
- `NoiseConvolutionJamming`：循环卷积后的 raw jammer 直接测量，统一缩放消除了卷积增益差异。
- `AMNoiseGaiJam`：缩放发生在完整 AM composite 拆分之后，只改变整体幅度；频谱相关保持 1。
- `SMSP`：子脉冲结构不重构，raw/scaled 时域和频谱相关保持 1。

## 8. 波形结构是否改变

没有改变。每个代表样本保存于：

```text
results/phase1/jammer_validation/<jammer>_seed42_jsr20.npz
```

其中同时包含 `raw_jammer` 和 `scaled_jammer`。由于 scaled jammer 只是 raw jammer 的正实数幅度缩放，归一化时域相关和幅度频谱相关均约为 1。

## 9. 回归测试

执行命令：

```bash
./.venv/bin/python -m py_compile utils/jsr_validation.py utils/jammer_interface.py unified_framework.py validate_jsr.py
./.venv/bin/python validate_jsr.py
./.venv/bin/python validate_no_jammer.py
./.venv/bin/python validate_algorithms.py
./.venv/bin/python run_correctness_tests.py
```

结果：

- `validate_jsr.py`：PASS，280/280，最大误差约 `0dB`；
- `validate_no_jammer.py`：9/9 PASS；
- `validate_algorithms.py`：9/10 PASS，`FMNoiseAimedJam/frft_filter` 失败；
- `run_correctness_tests.py`：进程退出码 0，内部 4 项通过、1 项警告、5 项失败。

## 10. 失败案例与回归解释

统一 JSR 后，旧模型原先按脉内功率缩放的 `JSR=10dB` 被改为完整接收数组平均功率定义，实际注入 jammer 功率变为严格的目标功率 10 倍。因此在相同脚本 JSR=10dB 下，部分算法的历史 SINR/检测率会变化。

具体新增/变化：

- `validate_algorithms.py` 的 `FMNoiseAimedJam/frft_filter` 检测率 `70% -> 50%`，该测试进程返回 1；
- `run_correctness_tests.py` 仍有 SliceCombine loader 三项和 FrFT 测试入口一项既有失败，并新增 Frequency Agile/FrFT 受更高统一干扰强度影响的失败。

这些回归不是通过改算法或 JSR 定义规避；原始输出已保存。Task 032 不修改算法，也不将旧不一致的功率结果继续当作公平基线。

## 11. 已知问题

- RGPO、ISDJ、SliceCombineJam 仍未接入本 wrapper；分别留给多脉冲/相干欺骗/接口任务。
- 旧 jammer 类直接实例化时仍可自行解释其 `JSR_dB`；Phase 1 标准路径应通过 `JammerLoader` 使用 wrapper。
- 旧测试脚本的 PASS/FAIL 阈值未为统一 JSR 重新设计；Task 033 负责统一评价契约。

## 12. Task 032 验收结果

- 7 个 Phase 1 jammer 统一接口：满足；
- 输出 target/jammer/noise/received：满足；
- JSR 统一定义且误差 `<0.2dB`：满足；
- raw/scaled 结构保持：满足；
- 不使用 oracle：满足；
- 回归输出已保存：满足，既有/新增失败已明确记录；
- 未修改算法、JSR 之外的物理模型、reward、PPO、state：满足。

## 13. Git

分支：`algorithm_design_0711`

提交 SHA：`0136a1d phase1-032-unify-jammer-jsr`
