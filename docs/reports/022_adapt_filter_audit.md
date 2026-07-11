# Task 022 Phase 1：adapt_filter 审查

审查日期：2026-07-11  
前置报告：`docs/reports/020_repository_state_audit.md`、`docs/reports/021_algorithm_gap_analysis.md`  
状态：Phase 1 已完成，未修改 `anti_jamming/adapt_filter.py` 或其他代码。

## 当前实现

调用链为：

```text
AntiJamEnv / unified evaluator
    -> adapt_filter_adapter()
    -> adapt_filter()
    -> template padding + signal-subspace projection
```

代码位置：适配器 `anti_jamming/adapters.py:97-113`，核心算法 `anti_jamming/adapt_filter.py:3-60`。

当前步骤：

1. `St_base` 是由 `RadarEnvironment.generate_target_signal()` 生成的已知 LFM 模板。
2. `Srt_matrix` 是接收矩阵，当前统一环境和 RL 环境通常是 `(1, N)`。
3. 当模板长度 `N_s` 小于接收长度 `N_r` 时，代码读取 `radar_par['target_idx']`，设置 `offset = target_idx - N_s//2`，把短模板放入长度为 `N_r` 的全长向量。
4. 计算 `sH = s.conj().T`、`Ps = sH @ (1/(s @ sH + par1) * s)`，最后执行 `y = r @ Ps`，输出 shape 与 `Srt_temp` 相同。

## 理论模型

该实现对应已知参考波形的秩一信号子空间投影：

```text
y = r · sᴴ · (s · sᴴ + λ)^(-1) · s
```

当目标回波是已知模板的延迟/缩放版本、干扰与模板相关性较低时，投影会保留目标相关分量并压制正交分量。这解释了它对 `NoiseProductJamming` 和 `NoiseConvolutionJamming` 的收益。

但真实接收端通常不能直接获得目标在接收窗口中的精确 `target_idx`。当前实现不是只使用已知发射波形，而是额外使用了由仿真环境提供的目标位置先验。

## Oracle 信息审查

### 是否使用真实 `target_idx`

是。`adapt_filter_adapter()` 明确把 `radar_par['target_idx']` 传给核心函数；核心函数在模板长度不匹配时用它计算 padding offset。

### 是否使用真实目标模板

是。`St_base` 是环境直接生成的理想发射 LFM，并非接收端从观测数据估计的模板。使用已知发射波形本身可以是合理的匹配滤波假设，但必须与其他算法保持相同先验条件。

### 是否使用真实目标参数

间接使用。代码没有读取目标距离变量来构造 projection，但通过 `target_idx` 使用了由 `Pw/Fs` 和仿真时间轴推导的真实目标位置。

### 是否使用真实干扰类型或 jammer 参数

核心 `adapt_filter()` 没有读取 jammer 类型、JSR 或干扰参数。适配器只传递模板、接收信号和 `target_idx`。它没有直接使用干扰标签，但仍依赖目标位置 oracle。

### 是否存在信息泄漏

存在。当前 `target_idx=1500` 并不是从当前接收信号估计出来的，而是 `RadarEnvironment` 直接写入 `radar_par` 的仿真真值，见 `unified_framework.py:93-98`、`147-153`。在 RL/统一评测中，adapt_filter 可以得到其他算法不一定拥有的精确对齐信息。

## 对照实验

### 实验设置

- 物理参数：统一环境默认基线，`Pw=20us`、`Fs=50MHz`、`N=5000`、`target_idx=1500`。
- JSR：20dB；噪声：`noise_var=0.1`。
- 干扰：`NoiseProductJamming`、`NoiseConvolutionJamming`。
- seed：42、123、456。
- 评价：`UnifiedEvaluator(guard_cells=4, ref_cells=20, Pfa=1e-4)`，匹配滤波后目标窗口 SINR/检测。
- 对照：identity、当前带 `target_idx` 的 projection、去掉 `target_idx` 的 projection。

“去掉 `target_idx`”不是最终算法方案，而是用于测量当前实现对位置先验的敏感性：模板会落在默认 offset=0，而不是根据真值对齐。

### 结果

| 干扰 | identity SINR 均值 | 带 `target_idx` | 去掉 `target_idx` | 带先验检测 | 无先验检测 |
|---|---:|---:|---:|---:|---:|
| `NoiseProductJamming` | 5.289dB | **11.462dB** | 9.744dB | 3/3 | 0/3 |
| `NoiseConvolutionJamming` | 7.073dB | **11.462dB** | 9.744dB | 3/3 | 0/3 |

逐 seed 结果显示：

- 带 `target_idx` 的 projection 两种干扰下均稳定得到约 11.462dB。
- 去掉 `target_idx` 后两种干扰均约 9.744dB，且 6 次对照中的检测均失败。
- identity 在不同噪声 realization 下分别为 4.04~6.15dB 和 4.91~8.93dB。

该实验不是算法优劣的最终结论，因为“无 `target_idx`”版本没有做任何接收端延迟估计；但它直接证明当前实现的收益显著依赖模板位置对齐，不能把 11.462dB 全部归因于 projection 本身。

## 优势来源

当前 adapt_filter 的优势来自三部分：

1. **理论有效性**：对于与已知 LFM 模板不相关的复噪声乘积/卷积污染，信号子空间投影具有合理的抑制方向。
2. **目标模板先验**：使用完整理想 `St_base`，而不是从接收数据估计模板。
3. **目标位置先验**：使用真值 `target_idx` 把短模板放到接收窗口的正确位置。

此外，代码实际构造 `N×N` 复数投影矩阵 `Ps`，注释中给出的内存优化公式只是注释，没有被执行。以 `N=5000` 计，单个 complex128 矩阵约 400MB，还需要额外的输入、临时矩阵和乘法内存。

## 是否公平

当前不完全公平。

### 公平之处

- 没有读取 jammer 类型或 JSR 来选择算法。
- 没有直接使用 jammer 的干扰分量。
- 对任意输入都执行同一个 projection 公式。

### 不公平之处

- `target_idx` 是仿真真值，不是从当前接收观测估计得到的量。
- active 评测中其他算法也可能使用 `target_idx` 构造模板 mask，但不同算法对该先验的依赖方式不同，未进行统一先验分层对照。
- 当前 SINR 评价只看固定目标窗口附近的峰值，没有统计假目标、虚警和距离误差；这会放大“把能量投影回已知目标模板”的收益。
- 背景均值切片包含目标窗口，指标本身不是严格的目标/干扰分离 SINR。

## 是否需要修改

需要，但不是立即删除或否定 adapt_filter。建议分两步。

### 第一步：建立公平基线

新增审计/测试逻辑而不是立即改算法公式：

- `oracle_align`：保留当前真值 `target_idx` 路径，作为上限参考；
- `estimated_align`：仅用接收观测和已知发射模板估计延迟；
- `fixed_or_no_align`：不使用目标位置先验，作为下限参考；
- identity：原始接收信号基线。

四种模式必须在相同 jammer、JSR、噪声和评价指标下比较，并记录失败和检测结果。

### 第二步：替换高内存实现

在公平性测试确定后，可把显式 `Ps` 改成等价的向量公式：

```text
weight = (r @ sH) / (s @ sH + λ)
y = weight @ s
```

这属于数值/内存实现修复，不应与 FDC、FrFT 或 RL 修改混在同一个阶段。

## 推荐定位

当前建议把 adapt_filter 定位为：

> **已知发射模板条件下的信号子空间投影基线**，而不是无先验的通用最优抗干扰算法。

在后续矩阵中应同时报告 identity、oracle-aligned adapt_filter、estimated-aligned adapt_filter 和其他专用算法。只有这样才能区分算法本身的投影收益、目标位置先验带来的收益，以及评价指标对局部目标峰值的偏好。

## Phase 1 结论

- 当前 adapt_filter 的数学方向合理，尤其适合已知 LFM 模板与结构噪声污染的场景。
- 当前实现明确使用 `target_idx` 和理想 `St_base`，存在仿真 oracle 信息，不满足“禁止使用 oracle 信息”的后续重构约束。
- 对照实验显示位置先验会显著影响检测和 SINR，因此 Task 021 中关于 RL 偏向 adapt_filter 的判断得到直接实验支持。
- 暂不修改 adapt_filter 代码，先把公平性基线和指标契约纳入后续任务。
- Phase 2 FDC 尚未开始。
