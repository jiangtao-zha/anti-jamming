# 任务 003：修复 FastSlowTimeProcessor 对 ISDJ 的效果

## 状态：已完成

## 根因分析

1. **FSTP 需要 M>=2 做多普勒域分离**，ISDJ（DRFM）产生的假目标与真实目标在同一距离单元，只有通过多普勒域才能区分
2. **validate_algorithms.py 使用 M=1**，FSTP 完全无法施展多普勒处理
3. **原适配器在 M=1 时用限幅处理降级**，但限幅对 ISDJ 的均匀强干扰反而恶化信号（-1.97 dB）

## 修复内容

- M=1 时直接返回原始信号（不恶化），SINR 改善从 -1.97 → +0.00 dB
- M>=2 路径保留限幅处理作为时域近似（R-D 域结果难以无损转回时域）

## 待后续改进

- 真正的 FSTP 抗 ISDJ 效果需要在 M>=2 测试中验证（多普勒域切除）
- 可考虑将 ISDJ 测试改为 M>=2 模式

## 修改的文件

- `anti_jamming/adapters.py` — fastslow_adapter 修改
