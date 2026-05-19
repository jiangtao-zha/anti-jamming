# 任务 002：修复 frft_filter 对 FMNoiseAimedJam 的效果

## 状态：已完成

## 修复内容

### 根因分析
1. **FrFT 阶数扫描用了短模板（1000点）而非全长信号（5000点）**→ 阶数偏差（1.07 vs 1.30）
2. **原算法用 argmax 找峰值，但 JSR=10dB 时干扰峰值更高**→ 掩膜中心偏到干扰上
3. **原掩膜宽度 w=100 太宽，而目标在 FrFT 域只集中在 5-10 个点**→ 泄漏大量干扰
4. **M=1 时直接跳过 FrFT 处理**→ 单脉冲场景完全无效

### 修复方案
1. 全长度零填充模板自动扫描 FrFT 最优阶数（范围扩大到 [0.5, 1.5]）
2. 用模板 FrFT 幅度阈值自动生成掩膜（>0.3 * max 的点保留）
3. 支持单脉冲 FrFT 滤波（不再要求 M>=2）
4. 统一使用模板引导的掩膜，不再依赖 argmax

### 修改的文件
- `anti_jamming/adapters.py` — frft_adapter 完全重写
- `anti_jamming/frft_filter.py` — frft_anti_jamming 增加 u1_target/u2_target 参数

## 测试结果
- 10 次试验平均 SINR 改善: **+4.46 ± 2.15 dB**
- 从 +0.00 dB 提升到 +4.46 dB
- 其他配对无退化
