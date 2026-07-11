# Task 030：Phase 1 基线快照

## 1. 任务结论

已完成当前分支在 Phase 1 新修改前的基线快照。未修改算法代码、雷达环境、RL、reward 或测试脚本。

快照对应：

- 分支：`algorithm_design_0711`
- HEAD：`917e261 022-step5-complete-algorithm-validation`
- Task 030 提交：`c11892d phase1-030-baseline-snapshot`
- 远端：`origin/algorithm_design_0711`，执行快照时与本地同步
- Python：3.12.13
- NumPy/SciPy/PyTorch：2.4.5 / 1.17.1 / 2.12.0

原始 Git 和测试输出保存在：

```text
results/phase1/baseline/
```

## 2. 修改前工作区状态

工作区没有已修改或已暂存文件，但存在两个未跟踪路径：

- `.codex/`：本地工具目录，未纳入本任务提交；
- `docs/tasks/phase1_master_plan.md`：本任务输入文档，当前未跟踪。

Task 030 新生成的报告和 `results/phase1/baseline/` 将纳入本任务提交。

## 3. 当前物理基线

### 3.1 `RadarEnvironment.DEFAULT_RADAR_PARAMS`

| 参数 | 当前值 |
|---|---:|
| `f0` | 15 MHz |
| `Bw` | 5 MHz |
| `Pw` | 20 us |
| `Fs` | 50 MHz |
| `M` | 1 |
| `N` | 5000 |
| `target_dist` | 6000 m |
| `target_amp` | 1.0 |
| `jammer_amp` | 8.0 |

运行时 `target_idx` 由环境根据 `1.5 * Pw * Fs` 计算为 1500，不是默认参数字典字段。

### 3.2 `JammerLoader.DEFAULT_RADAR_PARAMS`

```text
C=3e8, f0=15MHz, T=20us, Tr=100us, B=5MHz, Fs=50MHz
```

### 3.3 RL `Config`

```text
f0=15MHz, Bw=5MHz, Pw=10us, Fs=25MHz,
Tr=100us, target_dist=6000m, JSR_dB=10, noise_var=0.1,
state_len=1024
```

`Config` 没有 `M` 或 `N` 类属性。RL 仍未与统一物理基线对齐。

## 4. 干扰注册表

### 4.1 `JammerLoader` 支持的 10 种名称

```text
FMZuse
FMNoiseAimedJam
FMNoiseSaopin
AMNoiseGaiJam
RGPO
ISDJ
SMSP
NoiseProductJamming
NoiseConvolutionJamming
SliceCombineJam
```

### 4.2 统一综合测试默认列表

`unified_framework.py` 的默认列表包含 9 种：

```text
FMZuse, RGPO, ISDJ, SMSP, NoiseProductJamming,
NoiseConvolutionJamming, FMNoiseSaopin,
FMNoiseAimedJam, AMNoiseGaiJam
```

`SliceCombineJam` 不在默认列表中。

### 4.3 RL 干扰列表

RL `Config.jammer_list` 包含 9 种：

```text
FMNoiseAimedJam, FMZuse, AMNoiseGaiJam, FMNoiseSaopin,
ISDJ, SMSP, NoiseProductJamming, NoiseConvolutionJamming, RGPO
```

RL 不包含 `SliceCombineJam`。

## 5. 抗干扰注册表

### 5.1 active adapter 注册表：8 种

```text
WLN
FrequencyDomainCanceller
adapt_filter
wave_agile
Frequency_agile
frft_filter
qpzh
FastSlowTimeProcessor
```

### 5.2 统一综合测试默认列表：6 种

```text
WLN, FrequencyDomainCanceller, adapt_filter,
frft_filter, qpzh, FastSlowTimeProcessor
```

`wave_agile` 和 `Frequency_agile` 不在该默认列表中。

### 5.3 RL 抗干扰列表：6 种

与统一综合测试默认列表相同。RL 当前没有动作选择 `wave_agile` 和 `Frequency_agile`。

## 6. 测试命令与结果

### 6.1 `validate_algorithms.py`

命令：

```bash
./.venv/bin/python validate_algorithms.py
```

进程退出码为 0，脚本汇总为 **10/10 配对 PASS**：

| 配对 | SINR 改善 |
|---|---:|
| `SliceCombineJam` / `FastSlowTimeProcessor` | +0.01 +/- 0.08 dB |
| `SMSP` / `FastSlowTimeProcessor` | -0.02 +/- 0.00 dB |
| `AMNoiseGaiJam` / `FrequencyDomainCanceller` | +0.04 +/- 0.05 dB |
| `FMNoiseSaopin` / `Frequency_agile` | -0.02 +/- 0.01 dB |
| `ISDJ` / `FastSlowTimeProcessor` | -0.02 +/- 0.00 dB |
| `FMZuse` / `WLN` | -0.03 +/- 0.04 dB |
| `RGPO` / `wave_agile` | +0.35 +/- 0.04 dB |
| `FMNoiseAimedJam` / `frft_filter` | -0.28 +/- 0.06 dB |
| `NoiseConvolutionJamming` / `adapt_filter` | +1.41 +/- 0.50 dB |
| `NoiseProductJamming` / `adapt_filter` | +1.11 +/- 0.48 dB |

该脚本的 PASS 只表示其宽松阈值通过，不能证明专用算法优于 identity。

### 6.2 `run_correctness_tests.py`

命令：

```bash
./.venv/bin/python run_correctness_tests.py
```

进程退出码为 0，但脚本内部汇总为：

```text
总计 10 项：通过 5，警告 1，失败 4
```

失败项：

1. `FastSlowTimeProcessor` / `SliceCombineJam`：`SliceCombineJam.__init__()` 不接受 `Fs`；
2. `FastSlowTimeProcessor` / `SMSP`：同一 loader 初始化异常；
3. `FastSlowTimeProcessor` / `ISDJ`：同一 loader 初始化异常；
4. `frft_filter` / `FMNoiseAimedJam`：`anti_jamming.frft_filter` 缺少 `test_frft_filter`。

警告项：

- `wave_agile` / `RGPO`：平均 SINR 从 5.83 dB 降至 2.89 dB，恶化 2.94 dB。

其他通过项包括 WLN/FDC/adapt_filter/Frequency_agile；这些通过仍不代表物理正确性已经验证。

## 7. 当前已知失败与风险

- RL 物理参数仍为 `Pw=10us, Fs=25MHz`，与统一环境 `Pw=20us, Fs=50MHz` 不一致。
- RL 和统一默认列表均遗漏 `SliceCombineJam`。
- `SliceCombineJam` 标准 loader 接口不兼容 `Fs`，导致 correctness 测试无法覆盖真实算法链路。
- correctness 测试调用缺失的 `test_frft_filter`，FrFT 专用测试未执行。
- `run_correctness_tests.py` 以进程退出码 0 结束，但内部仍报告 4 项失败；后续不能只依据 shell exit code 判断通过。
- 当前基线是单脉冲 `M=1`，不能评价 FSTP 的慢时间能力。
- 现有测试多以检测率不下降和 SINR 阈值判定，尚未系统验证 JSR 标定、距离误差、假峰和专用算法优越性。

## 8. 验收判断

Task 030 的“建立可对比基线快照”条件满足：状态、参数、注册表、测试原始输出和已知失败项均已保存。

本任务没有修改算法代码，也没有启动训练。下一步应严格进入 Task 031；在 Task 031 获得确认前，不执行 Task 032 或后续任务。

## 9. 原始文件

```text
results/phase1/baseline/git_status.txt
results/phase1/baseline/git_branch.txt
results/phase1/baseline/git_log_15.txt
results/phase1/baseline/git_remote.txt
results/phase1/baseline/config_and_registry.txt
results/phase1/baseline/validate_algorithms.stdout.txt
results/phase1/baseline/run_correctness_tests.stdout.txt
```
