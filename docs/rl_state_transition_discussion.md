# RL 马尔可夫状态转移模型：讨论记录

> 日期: 2026-05-21
> 状态: Reward 设计已确定，r_t 定义待解决
> 关联文档: [jammer_markov_model.md](jammer_markov_model.md), [episode_improvement_proposals.md](episode_improvement_proposals.md)

---

## 一、模型概览

### 1.1 核心思想

干扰机根据雷达抗干扰的**效果**动态切换干扰策略：
- 抗干扰有效 → 干扰机被迫**降级**（从精确欺骗到粗暴压制）
- 抗干扰无效 → 干扰机**维持或恢复**（保持或回到更精确的策略）
- 干扰机降级到底 → **放弃**（S6 终止态）

### 1.2 状态定义

```
S1(精准欺骗) → S2 → S3(瞄准压制) → S4 → S5(粗暴覆盖) → S6(干扰放弃)

← 干扰机首选策略               干扰机被迫降级              干扰失败 →
```

| 状态 | 代号 | 含义 | 干扰类型 | 特征 |
|------|------|------|---------|------|
| S1 | 脉内采样欺骗 | 最精确的干扰策略 | ISDJ, SMSP | 功率低、精度高 |
| S2 | 脉间采样欺骗 | 跨脉冲欺骗 | RGPO | 中等精度 |
| S3 | 瞄准式压制 | 针对特定频段 | FMNoiseAimedJam, AMNoiseGaiJam | 功率集中、频段窄 |
| S4 | 覆盖式压制 | 宽带扫频/阻塞 | FMZuse, FMNoiseSaopin | 功率分散、覆盖宽 |
| S5 | 信号结构污染 | 直接污染信号结构 | NoiseProductJamming, NoiseConvolutionJamming | 最隐蔽 |
| S6 | 干扰放弃 | 终止态 | 无 | Episode 结束 |

### 1.3 Agent 目标

把干扰从 S1 一路推到 S6（干扰放弃）。

---

## 二、Episode 设计

### 2.1 方案选择

| 方案 | 描述 | 结论 |
|------|------|------|
| 无限（直到 S6） | 无上界，训练时间不可控 | **不采用** |
| 固定 N 步 + S6 bonus | 到 S6 后继续空转 | **不采用** |
| **固定上限 + S6 提前终止** | `done = (S==S6) or (step>=max_steps)` | **采用** |

### 2.2 Episode 流程

```
reset():
  1. 初始状态 S_init (随机 S1-S5)
  2. 从 S_init 中随机选一个干扰器
  3. 生成含干扰脉冲 → 返回 state

step(action):
  1. 解码 action → (算法, 参数)
  2. 抗干扰处理 → SINR_before, SINR_after
  3. 计算 r_t
  4. 基于 r_t 采样新状态
  5. 若 S_new == S6 → done = True
  6. 否则从新状态选干扰器，生成下一个脉冲
  7. 返回 (state, reward, done, info)

max_steps = 16
```

---

## 三、Reward 设计（已确定）

### 3.1 设计原则

三个防刷分机制各管一块，协同工作：

```
访问上限: 防止反复刷 R_dense → "用完就没了，只能往前走"
步惩罚:   防止拖延           → "每步都花钱，别磨蹭"
新最高:   防止重复拿状态奖励  → "去过的地方不再给分"
```

### 3.2 最终公式

```python
state_visits[S_new] += 1
prev_max_state = max_state
max_state = max(max_state, S_new)

# ① R_dense: 基础抗干扰能力（有访问上限，允许负值）
if state_visits[S_new] <= 3:
    R_dense = (SINR_after - SINR_before) * 1.0    # 可正可负
else:
    R_dense = 0                                      # 超过3次不再奖励

# ② R_step: 能量惩罚（驱动 agent 尽快结束）
R_step = -1.0

# ③ R_progress: 状态推进奖励（只认新最高状态）
R_progress = max(0, S_new - prev_max_state) * 3.0

# ④ R_terminal: S6 终极奖励
R_terminal = 15.0 if S_new == 6 else 0

R_total = R_dense + R_step + R_progress + R_terminal
```

### 3.3 权重汇总

| 组件 | 权重 | 单次范围 | 作用 |
|------|------|---------|------|
| R_dense | 1.0 /dB | -5 ~ +10 | 学抗干扰，上限3次/状态 |
| R_step | -1.0 /步 | 固定 -1 | 驱动速度，防拖延 |
| R_progress | 3.0 /状态 | +3 ~ +15 | 驱动推进，只认新纪录 |
| R_terminal | 15.0 | 0 或 +15 | 终极目标 |

量级关系: **R_terminal > R_progress (total) > R_dense (per step) > R_step**

### 3.4 策略验证

| 策略 | R_dense | R_step | R_progress | R_terminal | **Total** |
|------|---------|--------|-----------|-----------|----------|
| **A: 推到 S6 (5步)** | 5×5=25 | -5 | 5×3=15 | 15 | **50** |
| B: S1↔S2 震荡 (16步) | 3×8+3×6=42 | -16 | 3 | 0 | 29 |
| C: 在 S1 刷分 (16步) | 3×8=24 | -16 | 0 | 0 | 8 |
| D: 推到 S3 停滞 (16步) | 3×5+3×4+3×3=36 | -16 | 9 | 0 | 29 |

**排序: A(50) >> B=D(29) >> C(8)**

### 3.5 设计讨论记录

#### 讨论过的方案

1. **R_state 升级+降级- (方案A)**: `R_state = (S_new - S_old) * w`
   - 每轮震荡净收益 = 0，但配合 R_dense 仍可刷分 → **不采用**

2. **R_dense 衰减 (方案B)**: `R_dense = SINR / visit_count`
   - 永远不到 0，可能不够激进 → **不采用**

3. **访问上限 (方案C)**: 每个状态只奖励固定次数
   - 简洁，硬截止 → **采用**

4. **步惩罚 (方案D)**: 每步固定扣分
   - 鼓励速度，防拖延 → **采用**

#### 最终选择: C + D 组合

- 访问上限防止 R_dense 刷分
- 步惩罚防止拖延和震荡
- 两者单独用都不够（详见 3.6），组合效果最佳

### 3.6 为什么步惩罚不能单独用

极端检验：agent 在 S1 和 S2 都很擅长时

```
策略 A: 推到 S6 (5步)
  R_dense: 5×5×w = 25w,  R_step: -5c
  R_progress: 15,  R_terminal: 20
  Total = 25w - 5c + 35

策略 B: S1↔S2 震荡 (16步，无访问上限)
  R_dense: 16×7×w = 112w,  R_step: -16c
  R_progress: 3
  Total = 112w - 16c + 3
```

A > B 需要: 11c > 87w - 32
- 若 w=1.0: c > 5.0 → 步惩罚比 SINR 改善还大 → R_dense 净收益为负 → 学不到东西
- 若 w=0.5: c > 1.4 → 可行但 R_dense 太弱

**结论**: 步惩罚单独用要么防不住刷分，要么压死学习信号。与访问上限组合用才能两全。

---

## 四、转移概率模型

### 4.1 归一化公式（已验证）

对非边界状态 i ∈ {2, 3, 4}：

```
P_stay     = 0.4                      # 固定
P_escalate = 0.6 × r_t               # 降级概率（向 S6 方向）
P_deescalate = 0.6 × (1 - r_t)       # 恢复概率（向 S1 方向）

# 降级分配: 邻近 70%, 跳跃 30%
P(i → i+1) = 0.42 × r_t
P(i → i+2) = 0.18 × r_t

# 恢复分配: 邻近 70%, 跳跃 30%
P(i → i-1) = 0.42 × (1-r_t)
P(i → i-2) = 0.18 × (1-r_t)

验证: 0.4 + 0.42r + 0.18r + 0.42(1-r) + 0.18(1-r) = 1.0 ✓
```

### 4.2 边界处理

| 状态 | 处理 |
|------|------|
| S1 | 无恢复方向 → 恢复概率并入 P_stay |
| S5 | 降级方向只有 S6: P(S5→S6) = 0.6 × r_t |
| S6 | 终止态，无转移 |

---

## 五、r_t 定义的问题（核心待解决）

### 当前定义

```
r_t = max(0, SINR_after - SINR_before) / max(|SINR_before|, ε)
r_t ∈ [0, 1]
```

### 问题 1: 跨状态的 r_t 不可比

不同状态的 SINR_before 天然不同，同样的抗干扰努力得到完全不同的 r_t：

```
S1 (欺骗):     SINR_before = -3 dB,  改善 +3 dB → r_t = 3/3  = 1.0
S4 (宽带压制): SINR_before = -20 dB, 改善 +8 dB → r_t = 8/20 = 0.4
```

agent 在 S4 做出了 8 dB 的巨大改善，r_t 只有 0.4；在 S1 只改善了 3 dB，r_t 却是满分。

**后果**: 困难状态（SINR_before 低）更难降级 → agent 在最难的地方反而推进最慢。这与设计意图相反。

### 问题 2: SINR 同时驱动 reward 和转移

reward = f(SINR)，转移概率也 = f(SINR)。

- agent 改善 SINR → 同时拿 reward + 触发状态变化
- 两个机制耦合在同一个信号上
- agent 可能无法区分"做对了"和"触发环境变化"的区别

### 问题 3: 极端情况

| 情况 | 后果 |
|------|------|
| SINR_before ≈ 0 | r_t 爆炸 → 需要 ε 保护 |
| 改善量 > \|SINR_before\| | r_t > 1 → 截断，丢失区分度 |
| SINR_before > 0 | 公式物理意义改变（信号已比干扰强） |

### 改进方向（待讨论）

**方向 A: 状态归一化**
```
r_t = SINR_improvement / benchmark_improvement[S_current]
```
每个状态用最优算法的表现作为基准归一化。S4 的 benchmark 大，同样的改善在 S4 得到更高的 r_t。

**方向 B: 用检测结果替代 SINR**
```
r_t = 1 if target_detected_after else 0
```
最简单，但完全离散。

**方向 C: 用 SINR_after 绝对值**
```
r_t = sigmoid(SINR_after - threshold)
```
直接看抗干扰后能不能检测到目标。

**方向 D: 多指标加权**
```
r_t = α × normalized_sinr_improvement + β × detection_success
```
结合连续和离散指标。

---

## 六、其他待解决问题

### 6.1 S5→S6 的可达性

如果 S5（信号结构污染）本身很难对抗，r_t 在 S5 总是低 → agent 永远到不了 S6 → R_terminal 形同虚设。

**需要验证**: S5 的最优抗干扰算法是否确实能有效改善 SINR。

### 6.2 随机性导致不公平

转移是概率采样。agent 做得很好（r_t=0.9），但运气差采样到反向转移。

**可能的改进**:
- 用确定性软转移：r_t > threshold 就一定前进
- 或温度参数控制随机性

### 6.3 起始状态分布

如果总从 S1 开始，弱 agent 在 S1 反复失败，16 步都在 S1，学不到其他状态的特征。

**方案**:
- 训练时随机 S1-S5
- 评估时从 S1 开始（测试完整降级能力）

### 6.4 Episode 长度

max_steps = 16 是否足够？
- S1→S6 最少 5 步（完美降级）
- 考虑反向转移，实际需要 10-15 步
- 16 步可能偏紧，但太长影响训练速度

---

## 七、论文叙事框架（草案）

### 标题方向

"Signal-Aware Reinforcement Learning for Adaptive Radar Anti-Jamming in Non-Stationary Environments"

### 叙事逻辑

```
1. 问题
   现代干扰机是自适应的——它会评估抗干扰效果并调整策略

2. 现有方法的局限
   RL 抗干扰研究假设干扰是静态的 → 策略是查找表 → 面对自适应干扰失效

3. 我们的贡献
   (a) 建模: 马尔可夫干扰状态转移模型（S1→S6 降级链）
   (b) 方法: CPPO 架构利用信号特征实现参数自适应
   (c) 发现: 在非平稳环境中，信号感知能力是鲁棒策略的关键

4. 实验设计
   实验1: 静态环境 baseline → CPPO ≈ stdPPO
   实验2: 马尔可夫环境 → CPPO >> stdPPO
   实验3: 消融 — CPPO 去掉 CNN → 退化到 ≈ stdPPO
   实验4: 泛化测试

5. 核心论证
   为什么 CPPO 更好？
   - stdPPO: one-hot 告诉你"是什么干扰类型" → 固定参数
   - CPPO: one-hot + 信号特征 → 自适应参数 + 感知干扰强度
   - 在状态频繁切换的环境中，信号感知带来更快的适应速度
```

### 关键消融实验

证明确实是 CNN 信号特征在起作用：
- CPPO (CNN + one-hot) vs CPPO-no-CNN (only one-hot) vs stdPPO (only one-hot)
- 如果 CPPO-no-CNN ≈ stdPPO，说明 CNN 是关键
- 如果 CPPO >> CPPO-no-CNN，说明信号特征是非平稳环境中的核心优势
