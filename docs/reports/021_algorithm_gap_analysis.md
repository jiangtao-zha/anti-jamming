# Task 021：抗干扰算法理论一致性审查与重构规划

审查日期：2026-07-11  
前置报告：`docs/reports/020_repository_state_audit.md`  
修改范围：仅新增本报告；未修改代码、参数、reward、PPO、ROADMAP，未启动训练。

## 1. 当前算法体系总结

当前系统实际上混合了三类对象：

1. **单脉冲接收端滤波器**：WLN、FDC、adapt_filter、active FrFT、active qpzh。
2. **需要多脉冲或时间序列的处理器**：FSTP、理论上的 RGPO 轨迹处理。
3. **理论上应改变后续发射波形的主动策略**：Frequency Agile、Wave Agile。

但统一适配器把三类对象都压成同一个接口：

```text
radar_par(M×N received signal) -> processed_signal(M×N), processed_template
```

这对第一类算法是自然接口，对第二类算法是不完整接口，对第三类算法则改变了问题定义。当前 RL 又只暴露 6 个接收端/多脉冲名称，不包含两个 agile 名称，见 `rl_framework/config.py:69-90`。

因此当前“8 种抗干扰算法”是项目适配器数量，而不是 RL 中可以公平比较的 8 个同层级动作。

代码事实依据：

- 适配器注册表：`anti_jamming/adapters.py:407-415`。
- RL 动作列表：`rl_framework/config.py:69-76`。
- 统一接口处理：`unified_framework.py:236-250`。
- RL 环境实际动作调用：`rl_framework/environment.py:146-175`。

### 分类结论

| 类别 | 当前成员 | 当前是否适合直接作为同一离散动作 |
|---|---|---|
| 接收端单脉冲处理 | WLN、FDC、adapt_filter、FrFT、qpzh | 基本可以，但必须先统一参数、输入输出和评价指标 |
| 多脉冲处理 | FSTP | 当前环境 `M=1`，不应作为有效的单脉冲动作 |
| 主动发射策略 | Frequency Agile、Wave Agile | 不应直接作为当前接收端后处理动作；需要跨脉冲环境 |

## 2. 干扰模型审查

### 2.1 共同模型事实

统一环境使用 `Pw=20us/Fs=50MHz/N=5000/target_dist=6000/M=1`，目标索引为 `round(1.5*Pw*Fs)=1500`，见 `unified_framework.py:73-98`。

RL 默认仍使用 `Pw=10us/Fs=25MHz`，环境中 `N=int(Tr*Fs)` 并硬编码 `M=1`，见 `rl_framework/config.py:32-41` 和 `rl_framework/environment.py:47-60`。因此 RL 派生目标索引为 375，不是 1500。

除 RGPO 外，当前 10 种模型基本都在 `generate()` 中根据目标功率使用 `JSR_dB` 做一次缩放；但大多数返回的是“目标 + 干扰 + 加性噪声”复合数组，而不是独立的三个分量。`jam_info` 保存目标和噪声的情况较多，却没有统一保存最终干扰分量，无法直接逐类复核实际 JSR。

### 2.2 10 种干扰的理论结构

| 干扰 | 理论结构 | 当前实现事实 | 对后续算法设计的影响 |
|---|---|---|---|
| `FMZuse` | 宽带噪声调频阻塞，主要是宽带/频率扩散压制 | 随机 `Bj=6~9B` 的 FM 阻塞，缩放后插入单 PRP，并叠加实高斯噪声 | 适合先验证带宽选择、WLN 或时频抑制；不应把它当作窄带 AM 干扰 |
| `FMNoiseAimedJam` | 瞄准载频的窄带 FM 噪声，目标与干扰调频结构可能不同 | `f1=f0`，随机 `kfm`，单 PRP，JSR 有缩放 | 只有在目标/干扰斜率差异被显式保留时，FrFT 才有理论依据 |
| `FMNoiseSaopin` | 时间变化的扫频覆盖干扰 | 扫频 FM 复合信号，单 PRP，JSR 有缩放 | 适合时频跟踪或频率占用检测；当前接收端简单凹陷不等于频率捷变 |
| `AMNoiseGaiJam` | 载频附近 AM 噪声，具有调幅边带/正负频率关系 | AM 噪声经过缩放插入，JSR 有缩放 | 适合真正的共轭对称估计/对消；模板频谱差值不是同一理论模型 |
| `RGPO` | DRFM 复制目标并跨脉冲逐步拖引距离 | 内部生成 `N_pulses=16`，但固定取第 10 个脉冲；`JSR_dB` 被忽略，幅度固定 `A=1.8` | 必须有多脉冲轨迹和距离误差指标；当前单脉冲 SINR 不能评价 RGPO 成功与否 |
| `ISDJ` | 间歇采样/转发，多个采样片段形成结构化欺骗 | 默认 `M=4` 次转发，最终封装为单 PRP 一维输出，JSR 有缩放 | 需要时域采样片段、假目标结构或多脉冲特征；单纯频谱抑制不足 |
| `SMSP` | 子脉冲调频斜率/频谱弥散，匹配滤波后形成弥散能量 | 默认 `N_num=4` 的结构合成，单 PRP 输出，JSR 有缩放 | 可用 FrFT 或快慢时间分析，但必须保留斜率/子脉冲结构 |
| `NoiseProductJamming` | LFM 与窄带复噪声乘积，污染目标信号结构 | 内部复噪声与 LFM 相乘，JSR 有缩放；加性 PRP 噪声为实噪声 | adapt_filter 获益有代码依据，但它依赖已知模板，需防止把先验投影当作公平基线 |
| `NoiseConvolutionJamming` | LFM 与复噪声循环卷积，产生宽带结构污染 | 频域循环卷积后缩放，单 PRP 输出，JSR 有缩放 | 适合子空间/匹配结构评估；仍需独立记录干扰功率 |
| `SliceCombineJam` | 时域切片、复制、循环移位和组合 | 直接类会生成切片复制并缩放，但标准 `JammerLoader` 传入 `Fs` 时构造失败；第三返回值是 `tao_a` 而非 `jam_info` | 当前无法作为标准矩阵实验对象；修复接口后应优先使用时域结构算法 |

### 2.3 干扰模型的可信度结论

**已确认的风险**：

- `RGPO` 的 JSR 参数不是物理强度控制量，不能与其他 9 种干扰直接横向比较。
- `RGPO`、ISDJ、SMSP 虽然内部有多次转发/子脉冲结构，统一 `RadarEnvironment` 仍只把一维复合结果写入 `Srt_matrix[0,:]`，见 `unified_framework.py:136-145`。
- `SliceCombineJam` 的标准加载路径不可用；任务 020 中 `validate_algorithms.py` 的特殊 loader 绕过了这个问题，不能证明统一接口已修复。
- 统一环境的 `M>1` 不会填充真实的多脉冲回波矩阵，因此不能基于当前环境声称已经验证了多脉冲算法。

## 3. 抗干扰算法审查

### 3.1 当前 active 实现与理论目标

| 算法 | 理论目标 | 当前 active 实现 | 一致性结论 |
|---|---|---|---|
| `WLN` | 宽带提取、限幅/压缩、窄带清理强干扰 | `wln_filter.WLN` 使用宽/窄 Butterworth，并按接收幅度分位数做 μ 律压缩，见 `anti_jamming/wln_filter.py:39-95` | **部分一致**。流程一致，但阈值不是文档中的模板功率公式 |
| `FDC` | 利用 AM 干扰正负频率的共轭结构估计并对消 | active `fdc_adapter` 计算 `max(|R|-|T|,0)`，按频谱 excess 生成 gain，见 `anti_jamming/adapters.py:48-91` | **不一致**。是通用模板频谱抑制器，不是 AM 共轭对消 |
| `adapt_filter` | 投影到已知雷达信号子空间，抑制正交干扰 | `sH @ s` 构造 NxN 投影矩阵并做 `r @ Ps`，见 `anti_jamming/adapt_filter.py:17-60` | **理论基本一致，但有强先验**。模板和 `target_idx` 已知，可能形成 oracle 优势 |
| `FrFT` | 目标和干扰具有不同调频率，在不同 FrFT 阶数域分离 | active adapter 只从目标模板扫描最优阶数，并对接收信号使用模板软 mask，见 `anti_jamming/adapters.py:227-270` | **不充分**。没有显式估计干扰斜率，也没有目标/干扰双峰或双阶数分离 |
| `qpzh` | 检测时域切片污染并定位/重构真实信号 | active adapter 按 FFT 频谱分段比较模板/接收能量并衰减，见 `anti_jamming/adapters.py:276-327` | **不一致**。时间结构被替换为频域分段抑制；`n` 参数也未使用 |
| `FSTP` | 快时间脉压 + 慢时间 Doppler/RD 域通道抑制 | `M<2` 走频谱减法；`M>=2` 虽计算 RD 结果，但最后仍返回 `_apply_spectral_subtraction`，见 `anti_jamming/adapters.py:333-356` | **当前不应作为有效单脉冲动作**；多脉冲输出链也未闭合 |
| `Frequency Agile` | 通过后续发射脉冲频率变化使瞄准式干扰失配 | active adapter 做接收频谱阈值凹陷，见 `anti_jamming/adapters.py:175-221` | **名实不一致**。这是接收端后处理，不会影响下一脉冲干扰机响应 |
| `Wave Agile` | 通过后续脉冲波形变化抵抗 DRFM 复制 | active adapter 做接收端脉压、gain 加权和逆脉压，见 `anti_jamming/adapters.py:119-169` | **名实不一致**。没有改变发射波形、干扰响应或下一状态 |

### 3.2 对重点算法的判断

#### FDC：需要重写，但应先冻结接口边界

当前 active FDC 不能证明对 AM 干扰使用了共轭对称关系。旧 `FrequencyDomainCanceller` 类仍保留 `use_fitted_freq` 和默认 `f0=40MHz`，见 `anti_jamming/FrequencyDomainCanceller.py:7-19`，但统一 adapter 并不调用该类的 `cancel()`。

因此后续应先做一个明确选择：

- **方案 A：真正实现 AM 共轭对消**，输入输出和载频估计由 active adapter 统一负责；或
- **方案 B：承认它是通用频谱抑制器**，改名、改文档和重新选择适用干扰。

不能继续同时保留“AM 专用 FDC”名称和“模板频谱差值”实现。

#### FrFT：需要从“模板 mask”升级为“目标/干扰可分离验证”

当前实现的 `a_opt` 来源于模板，不是干扰估计。它可以保留已知 LFM 模板能量，但并不能证明干扰因不同调频率而被分开。理论上需要同时测量：

```text
目标在 a_target 域的集中度
干扰在 a_jam 域的集中度
两者在同一域的能量重叠
```

只有在不同斜率导致可重复的域内分离时，才能把 FrFT 称为 SMSP/FM 瞄准干扰的专用算法。

#### qpzh：当前应视为通用频域分段抑制器

active 代码没有按时间采样片段识别、定位和重构。它也没有使用 `n` 阈值，只有 `m` 影响频谱段数。因此它不具备当前文档中“切片结构识别与时域重构”的证据。后续若要对 SliceCombine/ISDJ 做专用算法，应保留切片边界、循环移位和目标模板重构信息。

#### FSTP：当前应暂时从 RL 单脉冲动作中移除或标记不可用

FSTP 的核心输入是 `M×N` 多脉冲矩阵，但 RL 环境硬编码 `M=1`。此时动作虽然存在，实际效果只是 `_apply_spectral_subtraction`，并不是 FSTP 理论目标。即使把 `M` 改为大于 1，也需要让 RD 域 `Filtered_RD` 结果回到统一评价链，才能验证算法。

#### adapt_filter：收益真实存在，但不能直接当作“通用算法优越性”

它对多个噪声/结构污染干扰有稳定收益，原因有两层：

1. 信号子空间投影确实适合与已知 LFM 模板不相关的噪声污染。
2. active 适配器把 `target_idx` 用于把短模板放到接收窗口已知位置，见 `anti_jamming/adapters.py:97-113` 和 `anti_jamming/adapt_filter.py:21-31`；这给了它额外的目标位置先验。

因此它在当前 reward 下成为强基线是合理的，但它的优势不能直接说明其他专用算法“理论无效”。应先在相同模板、相同位置先验和独立干扰分量评价下比较。

## 4. 理论匹配矩阵

矩阵中的“理论最佳”是根据当前干扰结构和算法理论目标给出的候选，不代表当前代码已经实现或已被实验确认。

| 干扰 | 理论最佳抗干扰算法 | 当前算法 | 是否匹配 | 修改建议 |
|---|---|---|---|---|
| `FMZuse` | WLN、时频/宽带抑制 | WLN 配对存在 | 部分匹配 | 先统一带宽、阈值和实际 JSR；WLN 可作为第一类接收滤波基线 |
| `FMNoiseAimedJam` | FrFT/时频斜率分离；若是固定瞄准也可做窄带抑制 | FrFT active 为模板 soft mask | 理论动机匹配，代码实现不充分 | 增加目标/干扰 FrFT 集中度和斜率分离验证，再决定是否重写 |
| `FMNoiseSaopin` | 时频跟踪、频率占用抑制；主动频率捷变需跨脉冲 | Frequency_agile active 为接收频谱凹陷 | 不匹配 | 先改成明确的接收时频算法，或建立真正跨脉冲 agile 环境；不能用当前 adapter 代表发射捷变 |
| `AMNoiseGaiJam` | AM 共轭对称频域对消 | FDC 模板频谱差值 | 不匹配 | 重写为 AM 结构估计/对消，或重命名为通用频域抑制 |
| `RGPO` | 多脉冲距离轨迹检测、波形/频率捷变、轨迹门抑制 | wave_agile 接收后处理 | 不匹配 | 先实现多脉冲 RGPO 轨迹和距离误差评价，再讨论 Wave Agile |
| `ISDJ` | 时域采样片段识别、FSTP/多脉冲结构处理、DRFM 失配策略 | FSTP 在 M=1 退化，qpzh 为频域 mask | 不匹配 | 先保留采样片段结构；拆分“片段识别”和“多脉冲 RD”两个问题 |
| `SMSP` | FrFT 斜率分离或多脉冲 RD 域处理 | FSTP M=1 降级；FrFT 不显式估计干扰斜率 | 部分匹配但未证实 | 做多脉冲/FrFT 对照实验，确认弥散能量的真实可分离特征 |
| `NoiseProductJamming` | 信号子空间/结构投影、自相关或匹配结构恢复 | adapt_filter 配对 | 基本匹配 | 保留作为结构投影基线；补独立 jammer 功率和模板先验对照 |
| `NoiseConvolutionJamming` | 信号子空间/匹配结构恢复、循环卷积抑制 | adapt_filter 配对 | 基本匹配 | 保留作为结构投影基线；验证不同卷积噪声带宽下是否稳定 |
| `SliceCombineJam` | 时域切片识别、边界检测、片段重构；多脉冲时可配合 FSTP | FSTP 配对但标准 loader 失败，qpzh active 为频域 mask | 不匹配且当前不可复现 | 先修统一构造接口，再设计时域切片重构；不要先调 PPO |

### 矩阵总体结论

当前真正“理论与 active 代码基本同层级”的主要是：

- WLN 对 FMZuse 的宽带/强峰抑制；
- adapt_filter 对 NoiseProduct/NoiseConvolution 的已知模板子空间投影。

FDC、FrFT、qpzh 是“理论方向合理但 active 实现不等价”；FSTP、Frequency Agile、Wave Agile 是“接口层级不匹配”。

## 5. RL 策略收缩原因分析

RL 最终偏向 `adapt_filter` 和少数算法，不应先归结为 PPO 学习率或网络结构问题。当前代码提供了多个更直接的原因。

### 5.1 reward 的区分度被检测奖励压平

RL 环境实际使用：

```text
sinr_before = local_peak_sinr(current_radar_par)
sinr_after  = local_peak_sinr(processed_par)
reward = 1.0 * (sinr_after - sinr_before)
       + 2.0 * I(sinr_after > 5dB)
```

代码位置：`rl_framework/environment.py:156-183`。

在统一 JSR=10dB 基线中，匹配滤波后很多干扰的 SINR 已约 10~11dB。于是大量动作都获得同样的 `+2`，算法差异只剩小幅局部 `ΔSINR`。这会让策略学习成“选择历史平均 ΔSINR 最高的动作”，而不是学习目标/干扰结构。

### 5.2 adapt_filter 在当前评价下确实占优

Task 018 的高 JSR 结果显示，`adapt_filter` 在 ISDJ、SMSP、FMNoiseAimedJam、AMNoiseGaiJam、NoiseProductJamming、NoiseConvolutionJamming 等多个组合上经常产生正向收益，JSR=30dB 时部分组合超过 6dB。其他算法在很多组合上接近 0 或为负。

这不是纯粹的 PPO 偏好，而是当前 active 结果矩阵给出了明确的统计优势。问题在于该优势还混入了：

- 已知模板；
- 已知 `target_idx` 对齐；
- 对目标窗口峰值的局部评价；
- 没有假目标/距离误差惩罚。

因此 adapt_filter 既有合理的结构投影收益，也有可能因评价和先验而被高估。

### 5.3 动作空间包含“名义动作”和“无效参数”

当前 RL `Config.antijam_list` 只有 6 个动作：WLN、FDC、adapt_filter、FrFT、qpzh、FSTP。

实际参数链存在以下失效：

| 动作 | 失效原因 |
|---|---|
| FDC | `decode_action` 输出 `use_fitted_freq/f0_fixed`，active `fdc_adapter` 只读 `cancellation_strength`，所以动作连续值不改变 active FDC |
| qpzh | `decode_action` 输出 `m,n=3`，active 代码只使用 `m`，`n` 不参与 mask |
| FSTP | 当前环境 M=1，始终走谱减退化分支，`limit_factor` 不影响实际结果 |
| Frequency/Wave Agile | 不在 RL action list；README 的 8 算法数量与 RL 动作空间不是同一集合 |
| 所有算法 | Actor 统一输出 1 个连续维，即使某些动作无参数或当前参数不生效 |

这会造成“连续动作探索有概率损失，但不一定改变结果”，使 PPO 的连续分布学习信号变差；同时有效的离散动作更容易收缩到少数稳定选项。

### 5.4 单脉冲环境无法提供时序算法的学习信号

`AntiJamEnv` 固定 `M=1`，一个 episode 内只是重复生成相同类型的 jammer，见 `rl_framework/environment.py:189-194`。因此：

- FSTP 没有慢时间维度；
- RGPO 没有拖引轨迹；
- Frequency/Wave Agile 没有“本次动作影响下一脉冲”的机制；
- Markov 状态不会转移。

在这种环境中，只有接收端单脉冲算法能稳定产生即时 reward，RL 偏向 adapt_filter 是环境设计的自然结果。

### 5.5 异常回退会掩盖无效算法

`AntiJammingProcessor.process()` 捕获异常后返回原始信号，见 `unified_framework.py:236-250`；RL 环境的 adapter 调用也在异常时回退到原始信号，见 `rl_framework/environment.py:160-168`。

因此一个算法不可用时，环境不会给出明确的失败状态或惩罚，可能只表现为 `ΔSINR≈0`。这会让无效动作看起来像“中性算法”，而不是可诊断的错误。

### 5.6 RL 策略收缩的因果排序

按影响强度判断：

1. **最高影响**：物理参数不一致，旧结果和当前结果不可直接比较。
2. **最高影响**：reward 的 `SINR + 固定检测奖励` 不能描述欺骗干扰，且检测奖励在高基线下饱和。
3. **高影响**：FDC/FSTP/qpzh 的动作参数或核心输出未生效。
4. **高影响**：单脉冲环境不支持多脉冲和主动策略。
5. **中高影响**：adapt_filter 使用已知目标模板和 `target_idx`，在当前指标下自然成为强基线。
6. **中等影响**：连续动作维度对所有算法统一，造成无参数/失效参数探索噪声。
7. **尚未能归因**：PPO 的网络表达能力、学习率、熵系数。必须在上述环境和算法契约修复后再单独评估。

## 6. 算法重构优先级

### 第一优先级：必须修复，否则实验没有意义

#### P0.1 统一物理参数和干扰接口

目标：统一 `Pw=20us/Fs=50MHz/N=5000/target_idx=1500/Tr=100us`，并确保 jammer 构造和 `generate()` 使用同一组参数。

必须包括：

- RL `Config` 与 `RadarEnvironment` 对齐；
- `target_idx` 只保留一个派生来源并增加断言；
- `SliceCombineJam` 接入标准 loader；
- 对 RGPO 明确“JSR 标定”或“固定幅度模型”的二选一；
- 各 jammer 返回统一的 target/jammer/noise 功率统计，至少能复核实际 JSR；
- 明确 `M` 是雷达脉冲数还是 jammer 内部转发/子脉冲数。

验收重点：逐类生成信号、检查 shape、时间对齐、实际功率比和 `jam_info` schema，不运行 RL 长训练。

#### P0.2 重建可解释的评估指标

当前 `compute_sinr_db` 将目标窗口包含进背景均值，且 reward 不评价欺骗效果。下一版应区分：

- 真实目标检测率；
- 假目标检测率/数量；
- 虚警数；
- 目标距离估计误差；
- RGPO 跟踪/拖引轨迹误差；
- post-processing SINR 作为辅助指标，而不是唯一目标。

验收重点：纯目标、纯干扰、目标+干扰三个受控输入的指标方向正确；每个指标可解释。

#### P0.3 修正动作契约

动作空间应按“算法类型”拆层：

- 第一阶段只让 RL 选择真正的单脉冲接收处理器；
- FSTP、Frequency Agile、Wave Agile 暂不作为当前单脉冲动作；
- 每个算法只暴露真实使用的参数维度；
- 对每个参数做输出敏感性测试；
- active adapter 异常不能静默当成正常 identity 结果，应进入 `info/error` 或显式失败惩罚。

### 第二优先级：提升算法物理正确性

#### P1.1 AM-FDC

实现真正的 AM 结构估计/共轭对消，明确载频单位是 Hz 还是 rad/s，删除 active adapter 与旧类的语义分叉。验证应包含 AM 干扰、非 AM 干扰和无干扰三组对照，避免通用频谱抑制器在所有场景都被误称为 FDC。

#### P1.2 FrFT 目标/干扰斜率分离

保留模板阶数作为参考，但增加干扰候选阶数或调频率估计，比较目标与干扰在 FrFT 域的集中度、重叠度和恢复后的匹配峰。只有通过这组证据后，才决定 FrFT 是否作为 FMNoiseAimedJam/SMSP 的专用动作。

#### P1.3 SliceCombine/ISDJ 时域结构处理

先修复 SliceCombine 的统一接口，再设计片段边界检测、循环移位识别和模板重构。qpzh 若保留为频域分段算法，应改名或单独记录，不能继续代表时域切片重构。

#### P1.4 adapt_filter 公平性基线

保留 adapt_filter，但增加以下对照：

- 不使用 `target_idx` 的自动模板对齐；
- 不同模板先验强度；
- 独立 jammer/noise 功率；
- 对目标、假目标、距离误差的完整评价。

目的不是削弱 adapt_filter，而是分离“理论投影收益”和“先验/评价口径收益”。

### 第三优先级：复杂时序环境

#### P2.1 RGPO 多脉冲环境

RGPO 必须输出真实 `M×N` 脉冲序列，保留每个脉冲的拖引距离，并在评价中加入轨迹误差。固定第 10 脉冲只能作为单元测试，不应作为 RL 环境的完整 RGPO。

#### P2.2 FSTP 闭环

让 RD 域 `Filtered_RD` 或其逆变换结果真正进入后续评价；明确输出是 `M×N` 时域矩阵还是一维距离像，并设计 M=1 的显式不可用状态，而不是静默降级。

#### P2.3 Frequency Agile / Wave Agile

建立跨脉冲接口：

```text
当前观测 -> agent 选择主动策略 -> 下一脉冲波形/频率改变
          -> jammer 响应 -> 新观测和状态转移
```

在该环境完成前，不应把接收端凹陷/脉压后处理宣传为主动 agile 策略。

### 第四优先级：重新训练和 PPO 调优

只有 P0/P1 完成并通过受控实验后，才进入：

1. 新物理基线下的 CPPO/stdPPO 短冒烟；
2. 单脉冲接收算法动作的重新训练；
3. 多脉冲 Markov 环境下的主动策略训练；
4. 最后才比较 PPO 网络、学习率、熵系数和特征提取器。

当前不建议直接用旧动作空间和旧 reward 做 Task 019 正式训练。

## 7. 推荐下一阶段任务列表

建议按以下顺序建立后续任务文件，不在本报告中实施：

### Task 022：统一物理参数和 jammer contract

- 对齐 RL/统一环境到同一基线；
- 修复 `SliceCombineJam` loader 接口；
- 统一输出 shape、`jam_info` 和功率统计；
- 明确 RGPO 的 JSR 语义；
- 添加逐类 JSR/时间对齐/shape 审计脚本。

### Task 023：重建 evaluator 与欺骗干扰指标

- 修正目标单元与参考单元的 SINR 计算；
- 增加真实目标、假目标、虚警、距离误差和 RGPO 轨迹指标；
- 设计分离的接收压制 reward 与欺骗 reward；
- 保留旧指标作为兼容对照，不立即删除。

### Task 024：重构接收端算法契约与 RL action space

- 只保留实际可用的单脉冲接收算法作为第一阶段动作；
- 修正 FDC/qpzh/FSTP 参数传递；
- 为每个参数增加敏感性和异常传播测试；
- 统一错误处理，禁止静默 identity 回退。

### Task 025：AM-FDC 理论实现与专用验证

- 共轭对称 AM 干扰估计；
- 载频单位和估计误差定义；
- AM/非 AM/无干扰对照实验。

### Task 026：FrFT 斜率分离验证与实现决策

- 目标/干扰调频率可控生成；
- FrFT 集中度和重叠度指标；
- 决定 active FrFT 是保留、重写还是降级为通用滤波器。

### Task 027：SliceCombine/ISDJ 时域结构恢复

- 切片边界和间歇采样识别；
- 模板片段重构；
- 与频域 qpzh、adapt_filter 做同指标对照。

### Task 028：多脉冲 RGPO/FSTP/主动 agile 环境

- 真实 `M×N` 数据流；
- RGPO 轨迹与状态转移；
- Frequency/Wave Agile 改变下一脉冲，而非后处理当前信号；
- 在此任务完成前，不进入主动策略 RL 正式训练。

### Task 029：基于新契约的 RL 重训

- 仅在 022~028 相关验收通过后执行；
- 先短冒烟，再单 seed 基线，最后正式 CPPO/stdPPO 比较；
- 记录最后 10/20 轮 reward、SINR、检测率及欺骗指标。

## 最终结论

当前 RL 策略收缩到 `adapt_filter` 和少数动作，主要不是 PPO 本身学坏，而是环境在即时局部 `ΔSINR` 上奖励一个在多个干扰上确实有效、且拥有目标模板/位置先验的通用投影器；同时 FDC、qpzh、FSTP 的参数或核心处理没有完整生效，主动 agile 算法也没有进入真实跨脉冲问题。

因此后续正确顺序是：

```text
物理参数/JSR/接口统一
    -> 评价与欺骗指标重建
    -> 接收算法和动作空间契约修复
    -> 专用算法理论实现
    -> 多脉冲/主动策略环境
    -> RL 重训与 PPO 调优
```

在这条链路完成前，任何新的长时间 RL 训练结果都只能说明当前简化 reward 下的策略偏好，不能作为完整抗干扰算法优劣结论。
