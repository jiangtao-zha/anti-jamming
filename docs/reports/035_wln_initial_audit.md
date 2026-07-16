# Task 035：WLN 初始审计

## 1. 当前调用链

`utils/test_contract.py` 使用白名单构造 `Srt_matrix`、`St_base` 和物理接收参数，调用 `get_antijam_func('WLN')`；adapter 将字段映射为 `Srt_temp`、`St1`、`f0`、`Bw`、`Fs`，再调用 `anti_jamming.wln_filter.WLN`。当前审计没有修改算法。

## 2. 当前处理流程

对每个脉冲，WLN 依次执行：

1. 设计中心为 `f0 + Bw/2` 的固定宽带 Butterworth band-pass，带宽为 `2*Bw`；
2. 对接收 IQ 做宽带零相位滤波；
3. 以接收幅度的 95 分位乘 `max(2*par1, 1.5)` 建立阈值；
4. 对幅度执行固定 `mu=5` 的 μ 律压缩，保留原相位；
5. 以 `1.5*Bw` 的固定窄带 Butterworth 再滤波；
6. 模板也经过宽带和窄带零相位滤波后作为输出模板。

## 3. 参数含义

- adapter 默认 `par1=0.3`，Task 034 配对也显式使用 `par1=0.3`；它只影响接收幅度 percentile 阈值的倍率，代码中的模板噪声估计 `Vs_est`/`VL` 当前未参与输出。
- `par2=6` 是宽带和窄带 Butterworth 的阶数，当前两级使用相同阶数。
- core `WLN` 函数签名默认 `par1=0.6`，但公平 adapter 默认覆盖为 `0.3`；Task 035 baseline 以 adapter/contract 的 `0.3, 6` 为准。

## 4. 可观测特征与 FMZuse 匹配

当前使用的特征是接收幅度 percentile、幅度/相位分解以及固定载频/带宽滤波。它没有显式估计 FM 调频率、瞬时频率轨迹或 FM 统计量，因此与 FMZuse 的理论匹配是间接的：宽窄带限制和非线性压缩可能抑制宽带高幅度 FM 污染，但不能证明检测到了 FM 结构。

## 5. 已确认问题

- 算法对所有输入无条件执行两级滤波和 μ 律压缩；低 JSR 时目标和噪声同样经过该处理，可能解释 JSR=0 dB 的负收益。
- 限幅阈值依赖接收信号自身的 95 分位，随 JSR 和噪声尺度变化；没有稳定的相对干扰检测或 bypass/gating。
- 固定频带可能损伤目标有效频谱边缘；六阶零相位滤波还可能放大边界/瞬态效应。
- `Vs_est`/`VL` 是未使用的历史参数路径，不能被当作当前限幅机制的证据。
- 当前没有发现 `target_idx`、`target_dist`、`target_start_idx`、jammer label、真实 jammer signal 或 measured JSR 输入。

## 6. JSR=0 dB 损伤解释

代码事实是：WLN 在低 JSR 仍无条件滤波和压缩，且输出模板也改变；没有低干扰 bypass。合理推断是目标主瓣/噪声在固定频带和 nonlinear mapping 后的匹配响应下降，导致约 `-1.13 dB` 的 baseline 损伤。该原因需要 calibration/diagnostic 结果验证，不能仅凭代码视为最终因果结论。

## 7. Baseline 冻结信息

- branch：`algorithm_design_0711`
- baseline commit：`fe5a2e1b89ab20ad1b039054a4094a2bc63df6f2`
- adapter 参数：`par1=0.3, par2=6`
- `anti_jamming/wln_filter.py` SHA256：`9a51ec990f2b023df42667dfc3a4d3428fe44876b897d53eec97cd18d6aad470`
- `anti_jamming/adapters.py` SHA256：`424b019a3bd43a7929e4ae695a22d1527851942fc06eac331ddaf68c8c8e264b`
