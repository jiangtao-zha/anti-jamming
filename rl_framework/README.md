# 雷达抗干扰强化学习框架 (rl_framework)

基于 PPO (Proximal Policy Optimization) 的雷达抗干扰智能体训练框架。
智能体直接观察原始 IQ 时域信号，自主选择抗干扰算法及其参数，最大化 SINR 改善。

## 快速开始

### 环境依赖

```
Python >= 3.8
PyTorch >= 1.10
numpy
scipy
matplotlib (可视化)
tensorboard (可选，用于训练日志)
```

### 训练

```bash
# 默认配置训练 CPPO
python -m rl_framework.train

# 训练 Standard PPO（不使用干扰 one-hot 信息）
python -m rl_framework.train --agent_type std_ppo

# 自定义参数
python -m rl_framework.train --episodes 2000 --lr 1e-4

# 训练并保存训练历史（用于训练曲线对比）
python -m rl_framework.train --agent_type cppo --save_history
python -m rl_framework.train --agent_type std_ppo --save_history

# 中断恢复
python -m rl_framework.train --resume rl_framework/checkpoints/ppo_ep500.pt

# 使用距离像模式
python -m rl_framework.train --state_mode range_profile --state_len 512
```

### 训练曲线对比

```bash
# 先训练两种策略并保存历史
python -m rl_framework.train --agent_type cppo --save_history
python -m rl_framework.train --agent_type std_ppo --save_history

# 绘制对比曲线（默认指标为 reward）
python plot_training_curves.py --log_files checkpoints/training_history_cppo.npz checkpoints/training_history_std_ppo.npz --labels CPPO "Standard PPO"

# 绘制 SINR 改善曲线，附带 Expert 水平线
python plot_training_curves.py --log_files checkpoints/training_history_cppo.npz checkpoints/training_history_std_ppo.npz --metric sinr_improvement --smooth 15 --expert_value 2.5 --title "SINR Improvement"
```

### 评估

```bash
# 评估 CPPO 模型
python -m rl_framework.evaluate --model checkpoints/ppo_best.pt

# 评估 Expert 策略（不需要模型文件）
python -m rl_framework.evaluate --agent_type expert

# 评估 Standard PPO
python -m rl_framework.evaluate --agent_type std_ppo --model checkpoints/std_ppo_best.pt

# 只评估指定干扰类型
python -m rl_framework.evaluate --model checkpoints/ppo_best.pt --jammer FMZuse
```

### 综合对比

```bash
# 对比四种策略（需提供 PPO 权重文件）
python run_comparison.py --cppo_weights cppo_best.pt --std_ppo_weights std_ppo_best.pt

# 仅对比 Expert vs 无处理（不需要权重）
python run_comparison.py

# 自定义回合数和输出
python run_comparison.py --episodes 100 --output_plot comparison.png
```

### TensorBoard

```bash
tensorboard --logdir runs/rl_anti_jam
```

## 文件结构

```
rl_framework/
├── config.py               # 所有可调参数 + 预设配置 (CPPO/StdPPO/Expert)
├── environment.py          # MDP 环境
├── ppo_agent.py            # PPO 模型（支持 input_mode: signal_and_jammer / jammer_only）
├── expert.py               # 领域专家规则策略
├── agent_factory.py         # 智能体工厂函数
├── train.py                # 训练主循环（实时绘图 + 历史保存）
├── evaluate.py             # 单策略评估
├── run_comparison.py       # 多策略综合对比（柱状图 + 表格）
├── plot_training_curves.py # 训练曲线对比绘图
├── utils.py                # 工具函数
├── checkpoints/           # 模型 & 训练历史保存目录
└── README.md               # 本文件
```

## 智能体类型

| 类型 | input_mode | 说明 | 配置 |
|------|-----------|------|------|
| CPPO | `signal_and_jammer` | 原始信号 CNN 特征 + 干扰 one-hot → 混合动作空间 | `--agent_type cppo` |
| Standard PPO | `jammer_only` | 仅干扰 one-hot → 小 MLP → 混合动作空间（不使用原始信号） | `--agent_type std_ppo` |
| Expert | — | 基于领域规则的固定策略（不训练） | `--agent_type expert` |

## 状态空间

| 模式 | 输入形状 | 描述 |
|------|---------|------|
| `raw_iq` | `(2, L)` | 原始 IQ 信号双通道，L=1024（可配） |
| `range_profile` | `(1, L)` | 脉冲压缩后距离像幅度，L=1024（可配） |

通过 `config.py` 中 `state_mode` 切换模式。

## 动作空间

混合动作空间：

- **离散动作**：选择抗干扰算法（WLN、频域对消、自适应滤波、FrFT 滤波、切片重组、快慢时间处理）
- **连续动作**：所选算法的参数，统一归一化到 `[0, 1]`，每个算法最多 2 个连续参数

| 算法 | 连续参数 | 范围 |
|------|---------|------|
| WLN | par1 (阈值) | [0.1, 2.5] |
| FrequencyDomainCanceller | use_fitted_freq | [0, 1] |
| adapt_filter | par1 | [-1.0, 1.0] |
| frft_filter | a1 (FrFT 阶数), w (掩膜宽度) | [0.8, 1.2], [20, 200] |
| qpzh | m (分段数), n (阈值倍数) | [2, 10], [2, 8] |
| FastSlowTimeProcessor | limit_factor | [1.5, 5.0] |

## 奖励函数

```
reward = w_sinr * (SINR_after - SINR_before) + w_detect * I(SINR_after > threshold)
```

## 命令行参数 (train.py)

```
--episodes         最大训练回合数
--steps            每回合脉冲数
--lr               学习率
--state_mode       raw_iq 或 range_profile
--state_len        状态长度
--agent_type       cppo / std_ppo / expert
--save_history    训练结束后保存 .npz 历史文件
--seed             随机种子
--device           auto / cpu / cuda
--resume           从 checkpoint 恢复
--no_tensorboard    禁用 TensorBoard
--plot_interval    实时刷新图表的间隔（回合数）
```

## 命令行参数 (plot_training_curves.py)

```
--log_files        训练历史文件 (.npz/.csv)，可指定多个
--labels           图例标签（默认从文件名推断）
--metric           指标名 (reward / sinr_improvement / detect_rate 等)
--smooth           移动平均窗口大小，默认 10
--output           输出图片路径
--title            图表标题
--expert_value     Expert 固定性能（绘制水平虚线）
```
