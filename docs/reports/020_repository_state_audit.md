# 任务 020：当前仓库状态审查报告

审查日期：2026-07-11  
审查范围：代码、文档、统一仿真框架、RL 环境、现有测试  
修改范围：仅新增本报告，未修改算法、参数、RL 环境、ROADMAP 或测试代码。

## 1. Git 状态

执行了任务要求的命令：

```bash
git status
git branch --show-current
git log --oneline -10
git remote -v
```

结果：

| 项目 | 结果 |
|---|---|
| 当前分支 | `master` |
| 当前 HEAD | `6cf97921250b12ddeb67e5187c2d9d82c09d6795` |
| 远端 | `origin -> git@github.com:jiangtao-zha/anti-jamming.git` |
| 远端默认分支 | 远端实际存在 `origin/main`；本地未设置 `origin/HEAD` symbolic ref |
| 工作区 | 干净，`git status` 无未提交修改 |
| 本地/远端 | `HEAD` 与 `origin/main` 均为 `6cf9792`，当前一致 |

最近相关提交：

```text
6cf9792 results: preserve high JSR evaluation summary
785eb10 merge: preserve remote repository history
df97c86 docs: add collaboration protocol and high JSR evaluation
75d6119 修复target_idx对齐和T/Pw一致性，重写4个抗干扰适配器
77da099 算法修复与基线建立：采样率对齐、4算法Bug修复、全扫描基线
185e79d 工程整理：修复CA-CFAR检测、重构文档体系、清理冗余文件
2d04e27 std PPO 和专家策略初步完成，待调优
09ce4f2 CPPO工程初步完成，能够plot出图
```

结论属于 A 类：Git 状态由命令直接确认。审查过程中未执行 `reset`、`checkout`、`rebase`、`merge` 或删除操作，也未启动训练。

## 2. 文档与代码一致性结论

### A. 已由代码确认

- 统一仿真框架 `RadarEnvironment.DEFAULT_RADAR_PARAMS` 使用 `f0=15MHz`、`Bw=5MHz`、`Pw=20us`、`Fs=50MHz`、`M=1`、`N=5000`、`target_dist=6000m`，目标索引由 `round(1.5 * Pw * Fs)` 得到 1500，见 `unified_framework.py:73-98`。
- `JammerLoader` 的常规默认构造参数为 `T=20us`、`Tr=100us`、`B=5MHz`、`Fs=50MHz`，见 `unified_framework.py:256-286`。
- RL `Config` 仍使用 `Pw=10us`、`Fs=25MHz`，见 `rl_framework/config.py:32-41`；RL 环境固定 `M=1`，并以 `int(cfg.Tr * cfg.Fs)` 计算 `N`，见 `rl_framework/environment.py:47-60`。
- RL 当前可用干扰是 9 种、可用抗干扰算法是 6 种，见 `rl_framework/config.py:50-76`；不是 README 所称的 8 种 RL 可选算法。
- `Frequency_agile` 和 `wave_agile` 在统一适配器中是接收端后处理：前者做频谱凹陷，后者做匹配滤波、脉压域增益和逆脉压，见 `anti_jamming/adapters.py:119-221`。
- `FastSlowTimeProcessor` 在 `M<2` 时直接走频谱减法；`M>=2` 时虽然计算了 RD 域结果，但适配器最终仍返回 `_apply_spectral_subtraction`，没有把 `profile_after` 转回输出信号，见 `anti_jamming/adapters.py:333-356`。
- `SliceCombineJam` 通过 `JammerLoader.load()` 会收到 `Fs` 参数，但其构造函数不接受 `Fs`，导致标准加载路径抛出 `TypeError`，见 `unified_framework.py:305-322` 和 `anti_jamming/qpzh.py:13-32`。
- 当前 RL 奖励不是 `UnifiedEvaluator` 的 CA-CFAR reward，而是 `SINR_after - SINR_before` 加上 `SINR_after > 5dB` 的固定检测奖励，见 `rl_framework/environment.py:156-183`。

### B. 文档声明但代码未确认

- ROADMAP 将 `018` 标为完成并记录了高 JSR 全矩阵结果；本次审查确认结果文件存在，但不把历史实验结果等同于算法物理正确性。
- ROADMAP 的“采样率修复”“所有算法不再严重恶化”等结论只能说明当时测试口径下的结果，不能证明当前 10 种干扰均已统一、所有参数均被实际使用。
- README 和 `algorithm_docs/` 描述 `Frequency_agile`、`wave_agile` 是发射端主动捷变策略；当前统一适配器实际是接收端信号处理，因此该设计声明没有被当前调用链确认。
- `algorithm_docs/antijam_FrequencyDomainCanceller.md` 描述了 AM 共轭对消和固定载频选项，但当前统一 RL/评测路径使用的是 `fdc_adapter` 的模板频谱差值方法，不是该类的完整 `cancel()` 路径。
- `algorithm_docs/antijam_frft_filter.md` 描述的是相邻多脉冲、两个 FrFT 阶数和矩形 mask；当前统一适配器采用模板自动扫描阶数和软 mask，属于不同实现。

### C. 明确不一致或风险

- README/ROADMAP 的最新物理基线与 RL 默认配置不一致：`Pw/Fs` 分别为 `20us/50MHz` 与 `10us/25MHz`。按 RL 当前公式，RL 的 `target_idx` 实际为 `round(1.5*10us*25MHz)=375`，不是最新基线的 1500。
- 统一框架的 `generate_with_jammer()` 对 `M>1` 只把干扰器返回的一维信号写入 `Srt_matrix[0,:]`，其余脉冲保持零，见 `unified_framework.py:136-145`；因此统一环境并未真正支持多脉冲回波矩阵。
- `UnifiedFramework.__init__()` 加载 jammer 时没有把用户传入的 `radar_params` 继续传给 `JammerLoader`，见 `unified_framework.py:370-392`。自定义 `Pw/Fs` 时，环境和 jammer 可能再次分裂。
- `RadarEnvironment.generate_without_jammer()` 使用真实时延 `range_bin` 写目标，而 `RadarEnvironment.target_idx` 仍按 1.5 个脉宽计算，见 `unified_framework.py:177-208`；无干扰路径存在目标注入位置与评价索引来源不同的风险。
- `AntiJammingProcessor.process()` 捕获所有算法异常后返回原始信号，见 `unified_framework.py:236-250`，调用方可能把“算法失败”当成“算法结果”。

## 3. 雷达参数对齐表

下表把文档、统一仿真环境、RL config 和 jammer loader/类默认分开记录。`jammer 默认值`优先指类构造函数默认值；实际经 `JammerLoader` 构造时通常被 `T=20us/Fs=50MHz` 覆盖。

| 参数 | 文档值 | `rl_framework/config.py` | 统一仿真环境 | `JammerLoader` | 是否一致 |
|---|---:|---:|---:|---:|---|
| `f0` | 15MHz | 15MHz | 15MHz | 15MHz | 一致 |
| `Bw/B` | 5MHz | 5MHz | 5MHz | 5MHz | 一致，`SliceCombineJam` 类默认另为 20MHz |
| `Pw/T` | 20us | **10us** | 20us | 20us | **不一致** |
| `Fs` | 50MHz | **25MHz** | 50MHz | 50MHz | **不一致** |
| `Tr` | README 未列，ROADMAP/任务为 100us | 100us | 默认字典未显式列出，调用方通常传入/使用 100us | 100us | 基本一致，但来源分散 |
| `M` | ROADMAP 为 1 | Config 未定义，环境硬编码 1 | 1 | jammer 内部各自含义不同 | RL/统一环境为单脉冲 |
| `N` | 5000 | RL 环境计算为 `Tr*Fs=2500` | 5000 | 各类按 `Tr/Ts` 计算；正常 loader 下为 5000 | **RL 不一致** |
| `target_dist` | 6000m | 6000m | 6000m | 由 `generate(R_target)` 传入 | 一致 |
| `target_idx` | 最新基线 1500 | 未存储，按当前 RL 参数派生为 375 | `round(1.5*Pw*Fs)=1500` | jammer 不统一存储，`RGPO` 输出 `i_target=10` | **不一致/来源分散** |
| `JSR_dB` | 10dB 基线，任务 018 为 20/30dB | 10dB | 默认回退 10dB，可由 radar params 覆盖 | 各 `generate` 接收，RGPO 忽略 | **RGPO 不一致** |
| `noise_var` | 0.1 | 0.1 | 默认回退 0.1 | 各 `generate` 接收，部分类默认不同 | 调用路径通常为 0.1 |

参数来源的代码定位：`RadarEnvironment` 为 `unified_framework.py:73-98`，`generate_with_jammer` 为 `unified_framework.py:130-153`，`JammerLoader` 为 `unified_framework.py:256-326`，RL 参数为 `rl_framework/config.py:28-41`，RL 环境组装为 `rl_framework/environment.py:47-60`、`111-122`。

## 4. 10 种干扰器审查表

动态审查以 `f0=15MHz, B=5MHz, T=20us, Tr=100us, Fs=50MHz, R=6000m, JSR=20dB` 调用标准 loader。前 9 种均返回 `(5000,) complex128`；`SliceCombineJam` 的标准 loader 路径直接报错。

| 干扰 | 输出 shape | 是否使用 `JSR_dB` | 强度标定 | 单/多脉冲 | `jam_info` | 与文档/风险 |
|---|---|---|---|---|---|---|
| `FMZuse` | `(5000,)` complex | 是 | 先生成带限实噪声并 FM 调制，再按目标功率和能量缩放；`Bj=6~9B` | 单 PRP 输出 | dict，含目标、加性噪声、`Bj/f1/JSR` | 复合信号正确可运行；噪声注入为实高斯 |
| `FMNoiseAimedJam` | `(5000,)` complex | 是 | 窄带 FM 噪声按目标功率/干扰能量缩放，随后重采样到系统 Fs | 单 PRP 输出 | dict，含目标、噪声、`Bj/kfm/JSR` | 名称/文档基本一致；默认 JSR=2、noise=0.01 只是类默认，环境会覆盖 |
| `FMNoiseSaopin` | `(5000,)` complex | 是 | 扫频 FM 干扰按目标功率/能量缩放，再插入 PRP | 单 PRP 输出 | dict，含目标、噪声、`bandwidth/kfm/JSR` | 有 `generate_jam_only`，但统一环境调用完整复合输出 |
| `AMNoiseGaiJam` | `(5000,)` complex | 是 | AM 噪声按目标功率/RMS 缩放 | 单 PRP 输出 | dict，含目标、噪声、`bandwidth/JSR` | 代码有 AM 生成，但统一 active FDC 不使用旧 AM 共轭对消类 |
| `RGPO` | `(5000,)` complex | **否** | 固定 `A=1.8` 与 `tuoyin=1us`，`JSR_dB` 仅为兼容参数 | 内部生成 `N_pulses=16`，但固定返回第 10 个脉冲 | dict，含 `i_target=10`、`delta_R`、目标、噪声 | **明确不满足 JSR 标定；文档/代码都承认只返回第 10 脉冲** |
| `ISDJ` | `(5000,)` complex | 是 | 4 次转发结构叠加后统一缩放 | 内部 `M=4` 次转发，输出单 PRP | dict，含目标、噪声、`M/Tj/JSR` | `M` 是转发次数，不是环境脉冲数 |
| `SMSP` | `(5000,)` complex | 是 | 多子脉冲频谱弥散合成后按目标功率缩放 | 默认 `N_num=4`，输出单 PRP | dict，含目标、噪声、`N_num/Aj/JSR` | 多子脉冲结构被封装进一个一维复合输出 |
| `NoiseProductJamming` | `(5000,)` complex | 是 | LFM 与窄带复噪声相乘后 RMS 缩放 | 单 PRP 输出 | dict，含目标、噪声、`bw/ord/JSR` | 内部噪声是复高斯；PRP 加性噪声是实高斯 |
| `NoiseConvolutionJamming` | `(5000,)` complex | 是 | LFM 与复高斯噪声循环卷积后 RMS 缩放 | 单 PRP 输出 | dict，含目标、噪声、`JSR` | 内部为复噪声卷积；输出没有独立 jammer/noise 数组 |
| `SliceCombineJam` | 标准 loader **无法生成**；直接类默认约 140MHz 采样 | 直接类实现有缩放 | 切片复制、循环移位后按目标功率缩放 | 单 PRP 输出 | 第三返回值是 `tao_a` 浮点数，不是 dict | **构造函数不接收 `Fs`，与统一 loader 接口不一致；默认 f0=50MHz/B=20MHz/T=24us 也偏离最新基线** |

共同事实：各 jammer 的返回值通常是“目标 + 干扰 + 加性噪声”的复合一维数组，并非独立的 target/jammer/noise 三分量。`jam_info` 中虽然保存了 `target_signal` 和 `noise_signal`，但绝大多数没有保存独立的已缩放干扰数组，因此无法仅从统一输出直接做严格的干扰功率复核。`RGPO` 是唯一明确绕过 `JSR_dB` 的十种干扰之一；`SliceCombineJam` 另有接口和默认参数问题。

## 5. 8 种抗干扰算法审查表

当前 8 种适配器注册于 `anti_jamming/adapters.py:407-415`。下表描述统一实际调用链，不把旧的算法文档或同名测试函数当作 active implementation。

| 名称 | 当前真实实现 | 输入域 / 输出域 | 使用参数 | 理论目标 | 名实一致性 |
|---|---|---|---|---|---|
| `WLN` | `wln_adapter` 调 `wln_filter.WLN`；宽带 Butterworth -> 接收幅度 95 分位数阈值的 μ 律压缩 -> 窄带 Butterworth | 时域复信号矩阵 -> 同 shape 时域复矩阵；模板也被滤波 | `par1`、`par2` 均影响处理 | 宽限窄滤除带外/强峰干扰 | 基本一致，但实现阈值是接收信号分位数，和文档中的模板 `VL` 公式不同 |
| `FrequencyDomainCanceller` | active adapter 不是旧 `FrequencyDomainCanceller.cancel()`；在频域计算 `max(|R|-|T|,0)`，对超出模板部分施加 gain | 时域输入 -> FFT gain -> 时域输出 | `cancellation_strength` 实际使用；`use_fitted_freq/f0_fixed` 被吞掉 | 频谱过量分量抑制 | **不一致**：不是 AM 共轭对称对消；旧类仍有 40MHz 默认值，见 `anti_jamming/FrequencyDomainCanceller.py:13-19` |
| `adapt_filter` | 用已对齐模板构造 `Ps=s^H(inv_term)s`，执行 `r@Ps` | 时域矩阵 -> 时域矩阵 | `par1` 使用，`par2` 未使用；`target_idx` 用于补零偏移 | 发射模板子空间投影 | 部分一致；对 `target_idx` 的先验位置依赖造成 oracle/信息泄漏风险；代码实际构造 NxN 矩阵 |
| `frft_filter` | active adapter 扫描 100 个阶数，取模板 FrFT 峰值最大阶数；按模板 FrFT 幅度构造软 mask，再对每个输入脉冲变换、掩膜、逆变换 | 时域复矩阵 -> FrFT 域 -> 时域复矩阵 | `mask_threshold` 实际使用 | 在目标模板集中的变换域保留能量 | 部分一致；没有显式估计/分离干扰调频斜率，且与旧多脉冲 `a1/a2/w` 实现不同 |
| `FastSlowTimeProcessor` | `M<2` 为模板频谱外的温和谱减；`M>=2` 计算 RD 域和通道切除，但适配器丢弃 `profile_after`，最终仍返回谱减结果 | 时域矩阵 -> active 输出仍是时域矩阵 | `limit_factor` 仅传给 RD 处理；当前 M=1 时完全无效 | 多脉冲 RD 域干扰通道抑制 | **不一致/不完整**：M=1 是降级方案；M>=2 的实际输出也没有使用 RD 结果 |
| `Frequency_agile` | 根据模板频谱定位 `R_mag/(T_mag+offset)>3` 的频点，软衰减并平滑 gain | 时域复矩阵 -> 频域凹陷 -> 时域复矩阵 | 无有效公开参数 | 文档目标是 Costas 发射频率捷变 | **名称/设计不一致**：统一路径不改变发射波形 |
| `wave_agile` | 模板构造匹配滤波器，输入做脉压；按脉压幅度/中位数生成 gain，逆脉压重构接收信号 | 时域复矩阵 -> 脉压域 -> 时域复矩阵 | 无有效公开参数 | 文档目标是脉冲间波形捷变 | **名称/设计不一致**：统一路径是接收端后处理 |
| `qpzh` | 将 FFT 频谱分成 m 段，按模板和接收频谱能量比较，对模板能量低的段按 `t_mag/R_mag` 衰减 | 时域复矩阵 -> 分段频域 mask -> 时域复矩阵 | `m` 使用；`n` 接口存在但 active adapter 未使用 | 文档称分段限幅/突发干扰抑制 | **部分不一致**：不是文档描述的时域中值×n 限幅，也不是切片重构 |

## 6. RL 动作与参数传递表

调用链为：

```text
PPO Actor -> discrete_idx/continuous_vals
          -> AntiJamEnv.step()
          -> decode_action()
          -> get_antijam_func()
          -> adapter
          -> algorithm implementation
```

对应位置：`rl_framework/ppo_agent.py:269-295`、`rl_framework/environment.py:146-175`、`rl_framework/utils.py:217-266`、`anti_jamming/adapters.py:407-415`。

| 离散动作 | 对应算法 | 连续范围 | decode 后参数 | active 算法是否真实使用 |
|---:|---|---|---|---|
| 0 | `WLN` | `par1: [0.1,2.5]` | `par1`，固定 `par2=6` | 是 |
| 1 | `FrequencyDomainCanceller` | `[0,1]` | `use_fitted_freq`、`f0_fixed=2π*cfg.f0` | **否**；active adapter只接收 `cancellation_strength`，且 `**kwargs` 被忽略，实际固定默认 `0.8` |
| 2 | `adapt_filter` | `par1: [-1,1]` | `par1`、`par2=None` | `par1` 是，`par2` 否 |
| 3 | `frft_filter` | `mask_threshold: [0.1,0.8]` | `mask_threshold` | 是，当前 active adapter使用该参数 |
| 4 | `qpzh` | `m: [2,10]` | 整数 `m`、固定 `n=3.0` | `m` 是，`n` **否** |
| 5 | `FastSlowTimeProcessor` | `limit_factor: [1.5,5.0]` | `limit_factor` | 当前 RL 环境 M=1，实际不生效；多脉冲路径中才传入 RD 处理 |

额外确认：

- README 的“8 种算法”是项目总适配器数量；RL `Config.antijam_list` 只有 6 种，未包含 `Frequency_agile`、`wave_agile`。
- `max_continuous_dim=1`，所以 RL 没有真正的多连续参数动作；qpzh 的 `n` 被固定，FDC 的动作参数事实上失效。
- stdPPO 在 `AntiJamEnv.step()` 中先用 `algo_default_params` 替换连续动作，再解码，见 `rl_framework/environment.py:146-154`。但 FDC 默认值仍会被 active adapter 忽略。
- 当前代码中 `decode_action` 没有 `f0=40e6` 硬编码，而是 `2π*config.f0`；但旧 `FrequencyDomainCanceller` 类仍默认 `f0=40e6`，且该旧类与 active adapter 并行存在，形成语义混淆。

## 7. 评估与奖励公式

### RL 环境实际 SINR

`rl_framework/utils.py:163-195` 的实际公式是：

1. `compressed = fftconvolve(rx_signal, conj(ref_signal[::-1]), mode='same')`。
2. 目标窗口为 `target_idx-10 : target_idx+10`，取窗口内最大幅度平方：

   ```text
   target_peak_power = max(abs(compressed[target_idx-10:target_idx+10]))^2
   ```

3. 背景区域为窗口前后各 `ref_cells=20` 个采样点，但切片从 `start-ref_cells` 到 `end+ref_cells`，**包含目标窗口本身**：

   ```text
   bg_mean = mean(abs(compressed[bg_start:bg_end]))^2 + 1e-12
   SINR_dB = 10*log10(target_peak_power/bg_mean)
   ```

因此这不是严格排除目标单元后的干扰/噪声功率估计，而是包含目标峰值的局部均值估计。

### 统一 CA-CFAR 评价器

`unified_framework.py:30-64` 的 `UnifiedEvaluator` 才使用 CA-CFAR：

- 默认 `Pfa=1e-5`，许多评测脚本显式传 `Pfa=1e-4`；RL config 的 `cfar_pfa=1e-5` 没有被 `AntiJamEnv.step()` 使用。
- `guard_cells=4`、`ref_cells=20`。
- 幅度域阈值系数 `alpha=sqrt(-4*ln(Pfa)/π)`。
- 检测是目标窗口内任一 CFAR 点超过阈值。
- SINR 同样取目标窗口最大峰值，并用目标窗口邻域均值计算。

### RL reward

`rl_framework/environment.py:177-183`：

```text
sinr_improvement = sinr_after - sinr_before
detect_bonus = 2, if sinr_after > 5 dB, else 0
reward = 1.0 * sinr_improvement + detect_bonus
```

当前没有实现：

- 最大假目标或假目标数量统计；
- 虚警数量；
- 距离估计误差；
- RGPO 轨迹误差；
- 欺骗目标与真实目标的区分；
- 状态转移或 Markov 状态降级。

策略收缩的代码证据：

1. `Config` 默认 JSR=10dB，统一修正基线的匹配滤波后 SINR 已约 10~11dB；许多样本因此天然满足 `sinr_after > 5`，动作都获得同一个 +2 检测奖励。
2. 环境只优化局部 `ΔSINR`，没有假目标惩罚或距离误差奖励，见 `environment.py:177-204`。
3. 一个 episode 内干扰类型保持不变，下一步只是重新生成同一个 jammer，见 `environment.py:189-194`；不存在文档中设计的状态转移链。
4. `run_comparison.py` 和 `evaluate.py` 也以 `compute_sinr_from_radar_par` 和 `sinr_after > 5` 作为核心指标，见 `rl_framework/run_comparison.py:61-104`、`rl_framework/evaluate.py:54-79`。

## 8. 测试结果

### `validate_algorithms.py`

命令：

```bash
.venv/bin/python validate_algorithms.py
```

实际结果：`10/10` 配对通过，摘要如下：

| 配对 | 检测率前->后 | SINR 改善 |
|---|---:|---:|
| SliceCombineJam / FastSlowTimeProcessor | 0% -> 0% | +0.01 ± 0.08dB |
| SMSP / FastSlowTimeProcessor | 100% -> 100% | -0.02 ± 0.00dB |
| AMNoiseGaiJam / FDC | 100% -> 100% | -0.17 ± 0.12dB |
| FMNoiseSaopin / Frequency_agile | 100% -> 100% | -0.02 ± 0.01dB |
| ISDJ / FastSlowTimeProcessor | 100% -> 100% | -0.02 ± 0.00dB |
| FMZuse / WLN | 100% -> 100% | -0.03 ± 0.04dB |
| RGPO / wave_agile | 100% -> 100% | +0.35 ± 0.04dB |
| FMNoiseAimedJam / frft_filter | 100% -> 100% | +0.03 ± 0.16dB |
| NoiseConvolution / adapt_filter | 100% -> 100% | +1.41 ± 0.50dB |
| NoiseProduct / adapt_filter | 100% -> 100% | +1.11 ± 0.48dB |

该脚本在 `validate_algorithms.py:76-87` 的判定条件只是“后检测率不下降且平均 SINR 改善不低于 -1dB”，不能证明专用算法优于通用算法、不能验证严格 JSR 标定，也不能验证多脉冲行为。它对 `SliceCombineJam` 使用了特殊 loader，绕过了标准 `JammerLoader.load()` 的 `Fs` 冲突，见 `validate_algorithms.py:125-134`。

### `run_correctness_tests.py`

命令：

```bash
.venv/bin/python run_correctness_tests.py
```

实际结果：共 10 项，`5 PASS / 1 WARN / 4 FAIL`。

- PASS：WLN/FMZuse、FDC/AMNoiseGaiJam、adapt_filter/NoiseConvolution、adapt_filter/NoiseProduct，以及部分基础配对。
- WARN：`wave_agile vs RGPO`，5 次平均 SINR 从 5.83dB 降到 2.89dB，改善 `-2.94dB`，检测率前后均为 0%。
- FAIL：`FastSlowTimeProcessor` 对 `SliceCombineJam`、`SMSP`、`ISDJ` 的测试路径均遇到 `SliceCombineJam.__init__() got an unexpected keyword argument 'Fs'`；`frft_filter` 测试因 `anti_jamming.frft_filter` 没有 `test_frft_filter` 函数而导入失败。

这个测试套件只验证既定测试函数能否运行及其宽松判定，不能证明物理正确性、统一 JSR 标定、专用算法优越性或真实多脉冲环境行为。测试中出现的 matplotlib/fontconfig 缓存提示是当前用户缓存目录不可写，不影响上述 Python 结果。

未运行 PPO 训练，符合任务禁止长训练的要求。

## 9. 已确认问题

1. RL 默认物理参数仍是 `Pw=10us/Fs=25MHz`，与最新统一基线 `20us/50MHz` 不一致，派生 `N/target_idx` 也随之不一致。
2. `SliceCombineJam` 无法通过标准 loader 构造，且第三返回值不是标准 `jam_info` 字典。
3. `RGPO` 接收但忽略 `JSR_dB`，使用固定幅度比和固定第 10 脉冲输出。
4. 统一环境的 `M>1` 处理只填充第一个矩阵行；RL 又硬编码为 `M=1`。
5. FSTP 的 active 适配器在 M=1 退化；M>=2 时真正的 RD 域处理结果也没有作为最终输出返回。
6. active FDC 与文档及旧 `FrequencyDomainCanceller` 类不是同一算法；RL 解码的 FDC 参数全部不生效。
7. qpzh 的 active 实现是分段频谱 mask，`n` 参数不生效，与文档的时域中值限幅语义不同。
8. `Frequency_agile`/`wave_agile` 的统一调用链是接收端后处理，不是 README/algorithm_docs 声明的发射端捷变。
9. FrFT active 实现与旧多脉冲测试接口不同；`run_correctness_tests.py` 调用的测试函数不存在。
10. `adapt_filter` 使用已知 `target_idx` 对齐模板，属于强先验；其代码实际构造 NxN 投影矩阵，注释中的内存优化实现没有被采用。
11. RL reward 只看局部 `ΔSINR` 和固定检测奖励，忽略假目标、距离误差、虚警和 RGPO 轨迹，且同一 episode 内没有 Markov 状态转移。
12. RL 的 `cfar_pfa`/`cfar_guard_cells` 没有进入 `AntiJamEnv.step()` 的实际奖励路径；RL 实际使用的是固定 5dB SINR 阈值。

## 10. 尚未确认问题

以下内容不能仅凭当前静态代码和现有测试断言，需要后续单独设计验证实验：

- 每种 jammer 的“实际输出 JSR”在插入窗口、加性噪声和匹配滤波后是否仍等于传入 JSR；当前代码只确认存在缩放公式，未做逐类功率审计。
- RGPO 的固定第 10 脉冲是否符合项目最终物理目标，还是仅为历史测试兼容行为。
- FrFT 模板 mask 是否在目标与干扰调频斜率相近/不同时真正分离；当前实现没有独立的 slope separation 指标。
- `M>=2` 时 FSTP 若改为真实多脉冲输出，RD 通道切除策略是否稳定；当前 active adapter 没有把该结果送回统一评价链。
- 文档中历史高 JSR 结果是否使用了与当前 active adapters 完全相同的参数映射；任务 018 结果文件可以复核数值，但不能替代代码语义审查。
- RL 模型历史 checkpoint 是否与当前 `Config`、动作列表和特征输入维度完全兼容；本任务未加载或训练 checkpoint。

## 11. 后续修改建议，但不实施

1. 先建立单一物理参数来源，明确统一仿真和 RL 是否都采用 `Pw=20us/Fs=50MHz/N=5000/target_idx=1500`，并为 `target_idx` 增加派生值断言。
2. 单独修复 `SliceCombineJam` 的 loader/构造接口，再重新运行测试；不要通过测试脚本特殊分支掩盖标准接口问题。
3. 对 10 种 jammer 增加独立 target/jammer/noise 分量或至少提供可复核功率统计，逐类验证输入 JSR。
4. 决定 FDC、FrFT、qpzh、捷变算法的唯一 active 语义，删除或隔离同名旧实现，避免文档和调用链描述不同算法。
5. 明确 FSTP 的多脉冲契约：环境需要真正生成 `M×N` 脉冲矩阵，适配器需要返回评价链实际使用的处理结果。
6. 重新设计欺骗干扰评价，加入真实目标/假目标检测、距离偏差、虚警和 RGPO 轨迹项，再讨论 Markov/RL reward。
7. RL 动作空间应按算法实际参数维度定义；移除无效连续维度，并为每个 decoded 参数增加“传入值确实影响输出”的测试。
8. 在上述语义稳定后，再做 P0 019 的短冒烟和正式重训；本审查不授权开始长时间训练。

## 审查结论

当前仓库“代码可运行、部分基线测试通过”，但不能视为“文档声明的物理模型和算法设计已全部对齐”。最重要的可信基线是：统一仿真 active 路径与 RL 路径存在参数、动作和评价口径的三重分裂；后续干扰/抗干扰修改前应先处理这些事实边界，避免把旧测试的 PASS 当成算法语义正确。

本任务没有算法修改、参数修改、ROADMAP 修改或训练操作。
