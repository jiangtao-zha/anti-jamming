# Task 032：统一 Phase 1 干扰接口与 JSR 定义

## 目标

为 Phase 1 的 7 个普通单脉冲 jammer 建立统一 wrapper 接口和统一 JSR 定义：

```text
target_signal + radar_config + requested_jsr_db + seed
    -> target / jammer / noise / received / measured_jsr_db / metadata
```

JSR 定义为完整对齐数组上的平均功率比：

```text
P(x) = mean(abs(x)**2)
JSR_dB = 10*log10(P(jammer)/P(target))
```

## 纳入范围

```text
FMZuse, FMNoiseAimedJam, FMNoiseSaopin, AMNoiseGaiJam,
SMSP, NoiseProductJamming, NoiseConvolutionJamming
```

RGPO、ISDJ、SliceCombineJam 暂缓。

## 禁止事项

不修改 jammer 物理模型公式、干扰结构、噪声模型、抗干扰算法、reward、PPO、动作空间、state 或雷达参数；不训练 RL，不执行 Task 033。

## 实施方案

公共 wrapper 以 legacy `JSR=0` 生成 raw composite，使用 legacy 返回的 target/noise 分量提取 raw jammer，再由 `utils/jsr_validation.py` 统一缩放到 requested JSR。保留旧三元组 `generate(R_target=...)` 兼容接口，供现有环境和测试回归使用。

## 验收

- 7 个 jammer × JSR `[0,10,20,30]` × 10 seeds；
- `abs(measured-requested) < 0.2dB`；
- 保存 raw/scaled representative waveform、功率和结构相关性；
- 回归 `validate_no_jammer.py`、`validate_algorithms.py`、`run_correctness_tests.py`；
- 保存结果到 `results/phase1/jammer_validation/`。
