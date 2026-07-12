# Task 034：FDC 初始实现分析

## 1. 审查范围

审查了 `anti_jamming/FrequencyDomainCanceller.py`、`anti_jamming/adapters.py`、`jamming/AMNoiseGaiJam.py`、`configs/phase1_radar.py` 和统一评价调用链。当前分支为 `algorithm_design_0711`，本报告只记录修改前事实。

## 2. 当前存在两条 FDC 实现

### 旧类实现

`FrequencyDomainCanceller.cancel()` 位于 `anti_jamming/FrequencyDomainCanceller.py:7-111`。它逐脉冲 FFT，比较正负频率总功率，选择一侧作为主侧，并用另一侧共轭翻转后相减，随后把另一侧、DC 和 Nyquist 置零。该类保留 `use_fitted_freq` 和默认 `f0=40e6`，但统一 adapter 不调用它。

### 当前 active adapter

统一路径实际调用 `anti_jamming/adapters.py:48-101` 的 `fdc_adapter`：

1. 读取 `Fs/f0/Bw`，用已知雷达载频下变频；
2. 对整段接收信号计算 `sum(baseband**2)` 与能量比，作为 AM-like `am_confidence`；
3. 将整段信号构造为相位对齐的共轭对称分量；
4. 对该分量做 FFT，并按 `cancellation_strength * am_confidence` 从原频谱相减；
5. 仅按 `abs(freq) <= 1.1*Bw` 给固定 0.5 保护，其余频段全强度对消；
6. IFFT 后重新上变频，返回原 `St_base`。

因此当前实现已经包含 AM 共轭对称假设，不是单纯 `FFT + 固定 mask + IFFT`；但它也没有显式估计独立的 `J_hat(f)`，其对消模板来自整个 `received_signal`。

## 3. 与 AMNoiseGaiJam 的匹配

`AMNoiseGaiJam` 在 `jamming/AMNoiseGaiJam.py:70-114` 生成：

```text
(1 + m * real_lowpass_noise) * exp(j(2*pi*f0*t + phi))
```

并按 JSR 标定后插入接收时间轴。下变频后，AM 分量理论上接近带限实值包络，因此 pseudo-covariance 和共轭对称结构是合理检测特征。

但目标是复 LFM，且同样位于已知载频附近。对整段 `received` 计算全局 pseudo-covariance 会把目标、噪声和 AM 干扰混在一起，可能误触发或错误估计 phase。当前固定 `target_band` 只按频率保护，并不识别目标实际时域占用，也不构成严格的目标保护。

## 4. 已确认风险

| 风险 | 代码事实 | 影响 |
|---|---|---|
| 未形成独立 jammer 估计 | `symmetric` 由完整 `baseband` 构造，未得到 `J_hat` | 目标分量可能被当作 AM 干扰对消 |
| 静态保护带 | `protect_factor` 仅由 `Bw` 和频率决定 | 目标与干扰重叠时无法按时域/模板保护 |
| 全局统计不稳 | `pseudo_cov` 是整段单次累加 | 噪声、目标和脉冲空窗会改变 confidence |
| 两套实现语义分裂 | 旧类与 adapter 算法不同 | 文档、直接调用和统一评测结果不可直接等同 |
| 参数范围有限 | active adapter 只使用 `cancellation_strength` | 载频与保护带没有独立搜索接口 |

## 5. Oracle 检查

当前 active `fdc_adapter` 不读取 `target_idx`、`jammer_type`、`jam_info` 或真实 jammer signal；只读取 `Srt_matrix` 和物理配置中的 `f0/Fs/Bw`。旧 `FrequencyDomainCanceller` 类也没有目标位置输入。使用已知雷达 `f0/Bw` 属于配置输入，不是目标位置 oracle。

## 6. 修改决策

需要新增一条可复现实验路径，并在不改变公共 adapter 接口的前提下实现 New FDC。改进方向是：用 AM 的下变频实包络/共轭对称统计构造 `J_hat`，显式加入模板保护或正则化，记录 `confidence` 和参数；同时保留当前 FDC 作为 `Current_FDC` baseline，不覆盖旧结果。

## 7. 初始结论

当前 FDC 具备 AM 理论的局部形式，但尚未证明“检测 AM 结构 -> 估计干扰 -> 抵消”的完整闭环。Task 034 后续实验必须同时检查 AM 专用收益、target-only 保真度和非 AM 负测试，不能只看 SINR。
