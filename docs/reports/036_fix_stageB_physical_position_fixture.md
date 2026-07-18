# Task 036-fix Stage B：物理一致的目标位置 Fixture

## 原错误与修正

原 Task 036 使用 `received = _shift_record(received_base, center - baseline_center)`。这种 whole-record translation 同时平移并可能截断 target、jammer 和 noise，改变边缘能量及噪声统计，不能作为正式目标距离鲁棒性证据。本阶段将它保留为 `WHOLE_RECORD_TRANSLATION_STRESS` 对照，不用于正式判断。

正式 fixture 对每个 `jammer × JSR × seed` 只生成一次组件 bank，然后在多个中心重组：

```text
received(center) = target(center) + jammer_component(policy, center) + noise(seed)
```

目标使用已知模板嵌入中心位置；noise 数组在同一 jammer × JSR × seed 的所有位置完全复用；组件不通过评价真值或目标标签修正。

## Jammer 位置耦合审计

| jammer | active-code policy | 正式位置规则 |
|---|---|---|
| NoiseProductJamming | `St_pulse × noise` | 随 target 保持相对 gate，平移 jammer component |
| NoiseConvolutionJamming | 与 `St_pulse` 卷积 | 随 target 保持相对 gate，平移 jammer component |
| AMNoiseGaiJam | local `t_jam` waveform | 固定 jammer component，target 独立移动 |
| FMNoiseAimedJam | local jammer time axis | 固定 jammer component，按 active code 依赖而非名称猜测 |
| FMNoiseSaopin | local `t_jam` waveform | 固定 jammer component |
| SMSP | local `tau_i/t_jam` pulses | 固定 jammer component |
| FMZuse | local `t_jam` waveform | 固定 jammer component |
| NoJammer | no jammer component | 仅复用固定 noise |

NPJ/NCJ 的 coupling 判断来自其实际 `St_pulse` 依赖；其余 jammer 的 active component 不读取 target waveform 或 `R_target` 来决定 component placement，因此按 target-independent 处理。规则和代码证据保存在 [jammer_position_policy.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageB/jammer_position_policy.csv)。不确定关系没有被静默猜测。

## Fixture 自检

使用安全中心 `1000/1500/2500/3500/4000`，JSR `0/10/20/30dB`，seeds `6100..6104`，8 个 jammer，共 800 个 validation rows。结果为：有 jammer 的 700 rows 全部 `PASS`；NoJammer 的 100 rows 全部 `NO_JAMMER_NOT_APPLICABLE`；failure 为 0。每个 row 检查 target/noise/jammer/received 能量变化、measured JSR、目标 support、有限性和 shape。目标能量、noise 能量、jammer 能量在容差内保持一致，目标 support 无截断，非 NoJammer 的 JSR error 小于 `1e-9dB`。

组件重组与旧 whole-record stress 的差异见 [fixture_comparison.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageB/fixture_comparison.csv)。完整 validation 见 [fixture_validation.csv](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageB/fixture_validation.csv)。

## 阶段决策

`PHYSICAL_FIXTURE_GATE_PASS`。Stage C 使用本阶段的 component bank 和安全位置，不再调用旧的 whole-record shift 作为正式位置数据。
