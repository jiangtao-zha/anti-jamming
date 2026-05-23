# 016: 修复抗干扰算法效果 — 马尔可夫状态转移模型前置条件

> 优先级: **高（阻塞马尔可夫模型实现）**
> 状态: **D类已完成，配对策略待决定，转入 017**
> 创建: 2026-05-21
> 更新: 2026-05-23
> 后续: `docs/tasks/017-fix-antijam-algorithms.md`

## 已完成

### D类修复：全局采样率不匹配（2026-05-23）

- 9个干扰器 `__init__` 添加 `Fs=None` 参数
- `JammerLoader.DEFAULT_RADAR_PARAMS` 添加 `Fs=50e6`
- `rl_framework/environment.py` 传入 `cfg.Fs`
- ISDJ SINR_before 从 -157dB 恢复到 +5dB
- 全部 10 对配对通过验证

### 全算法扫描结果

adapt_filter 对所有 9 种干扰器均为最优（+5.82 ~ +7.91 dB, 100% 检测率）。
frft_filter 为第二优（+3.4 ~ +5.7 dB）。
WLN/FDC/FSTP/wave_agile/Frequency_agile 效果差或无效。

## 待决定

- 配对策略（全部 adapt_filter vs 混合配对）
- 详见 `docs/tasks/017-fix-antijam-algorithms.md`
