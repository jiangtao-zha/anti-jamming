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
# 默认配置训练
python -m rl_framework.train

# 自定义参数
python -m rl_framework.train --episodes 2000 --lr 1e-4 --state_mode raw_iq

# 中断恢复
python -m rl_framework.train --resume rl_framework/checkpoints/ppo_ep500.pt

# 使用距离像模式
python -m rl_framework.train --state_mode range_profile --state_len 512
```

### 评估

```bash
# 评估最佳模型（对比无抗干扰、随机算法、PPO 智能体）
python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_best.pt

# 只评估指定干扰类型
python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_best.pt --jammer FMZuse

# 增加评估回合数
python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_final.pt --num_episodes 50
```

### TensorBoard

```bash
tensorboard --logdir runs/rl_anti_jam
```

## 文件结构

```
rl_framework/
├── config.py          # 所有可调参数（雷达、PPO 超参、状态/动作空间等）
├── environment.py     # MDP 环境（状态预处理、动作解码、奖励计算）
├── ppo_agent.py       # PPO 模型（CNN 特征提取 + Actor-Critic + tanh squashing）
├── train.py           # 训练主循环（支持日志、保存、恢复）
├── evaluate.py        # 评估脚本（多策略对比）
├── utils.py           # 工具函数（缓冲区、预处理、SINR 计算、动作解码）
├── checkpoints/       # 模型保存目录（自动创建）
└── README.md          # 本文件
```

## 状态空间

| 模式 | 输入形状 | 描述 |
|------|---------|------|
| `raw_iq` | `(2, L)` | 原始 IQ 信号双通道，L=1024（可配） |
| `range_profile` | `(1, L)` | 脉冲压缩后距离像幅度，L=1024（可配） |

辅助信息：干扰类型 one-hot 向量（长度 = 干扰类型数），在 PPO 特征提取阶段与 CNN 输出拼接。

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

- `SINR_after - SINR_before`：抗干扰前后的 SINR 改善 (dB)
- `w_detect`：检测成功附加奖励
- 权重在 `config.py` 中可调

## 关键配置项

在 `config.py` 的 `Config` 类中修改：

```python
# 雷达参数（降低以缩短信号长度）
Fs = 25e6          # 采样率 Hz
Pw = 10e-6         # 脉宽 s
state_len = 1024   # 状态长度

# PPO 超参数
lr = 3e-4          # 学习率
gamma = 0.99       # 折扣因子
eps_clip = 0.2     # PPO 裁剪范围
K_epochs = 10      # 更新轮数

# 训练
max_episodes = 5000
steps_per_episode = 8
```

## 命令行参数

```
--episodes     最大训练回合数
--steps        每回合脉冲数
--lr           学习率
--state_mode   raw_iq 或 range_profile
--state_len    状态长度
--seed         随机种子
--device       auto / cpu / cuda
--resume       从 checkpoint 恢复
--no_tensorboard  禁用 TensorBoard
```
