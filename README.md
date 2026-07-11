# 雷达抗干扰仿真与强化学习框架

基于 PPO 的雷达智能抗干扰决策系统。包含 **10 种干扰样式**、**8 种抗干扰算法**、统一的仿真评估框架，以及强化学习智能体自动选择抗干扰策略的训练流水线。

## 项目结构

```
anti_jamming/
├── jamming/                        # 干扰信号生成模块
│   ├── __init__.py                 #   干扰类型注册表 (JAMMER_TYPES)
│   ├── FMZuse.py                   #   FM 噪声调频阻塞干扰
│   ├── FMNoiseAimedJam.py          #   FM 噪声调频瞄准式干扰
│   ├── FMNoiseSaopin.py            #   扫频噪声干扰
│   ├── AMNoiseGaiJam.py            #   AM 噪声调幅压制干扰
│   ├── RGPO.py                     #   距离门拖引欺骗干扰
│   ├── ISDJ.py                     #   间歇采样直接转发干扰 (DRFM)
│   ├── SMSP.py                     #   频谱弥散干扰
│   ├── NoiseProductJamming.py      #   噪声乘积干扰
│   ├── NoiseConvolutionJamming.py  #   噪声卷积干扰
│   └── SliceCombineJam.py          #   切片组合干扰
│
├── anti_jamming/                   # 抗干扰算法模块
│   ├── __init__.py                 #   抗干扰适配器导出
│   ├── adapters.py                 #   统一适配器注册表 (8 个适配器)
│   ├── wln_filter.py               #   宽-限-窄滤波器
│   ├── FrequencyDomainCanceller.py #   频域对消器
│   ├── adapt_filter.py             #   自适应滤波器 (子空间投影)
│   ├── frft_filter.py              #   分数阶傅里叶变换滤波器
│   ├── FastSlowTimeProcessor.py    #   快慢时间联合处理器
│   ├── Frequency_agile.py          #   频率捷变雷达 (Costas-LFM)
│   ├── wave_agile.py               #   波形捷变雷达
│   ├── qpzh.py                     #   切片重组抗干扰 (分段限幅)
│   └── JamSuppressionEvaluator.py  #   抗干扰效果评估器
│
├── rl_framework/                   # 强化学习训练框架
│   ├── config.py                   #   参数配置 (雷达 / PPO / 网络)
│   ├── environment.py              #   MDP 环境 (AntiJamEnv)
│   ├── ppo_agent.py                #   PPO 网络 (1D-CNN + 混合动作空间)
│   ├── expert.py                   #   领域专家规则策略
│   ├── agent_factory.py            #   智能体工厂 (CPPO / StdPPO / Expert)
│   ├── train.py                    #   训练主循环
│   ├── evaluate.py                 #   单策略评估
│   ├── run_comparison.py           #   多策略综合对比
│   ├── plot_training_curves.py     #   训练曲线对比绘图
│   ├── utils.py                    #   工具函数
│   └── checkpoints/                #   模型权重 & 训练历史
│
├── unified_framework.py            # 统一仿真框架 (RadarEnvironment + UnifiedEvaluator)
├── validate_algorithms.py          # 干扰-抗干扰配对正确性测试
├── validate_no_jammer.py           # 无干扰基准测试
├── run_correctness_tests.py        # 批量正确性测试 (5 次独立试验)
│
├── algorithm_docs/                 # 算法技术文档
│   ├── jam_*.md                    #   各干扰样式原理与参数说明
│   └── antijam_*.md                #   各抗干扰算法原理与参数说明
│
├── docs/tasks/                     # 任务实施文档
└── requirements.txt                #   依赖
```

## 干扰样式 (10 种)

| 类型 | 名称 | 原理 |
|------|------|------|
| 压制干扰 | FMZuse (FM调频阻塞) | 宽带噪声调频遮蔽，带宽 6-10x 信号带宽 |
| 压制干扰 | FMNoiseAimedJam (FM调频瞄准) | 窄带瞄准载频，集中功率高效压制 |
| 压制干扰 | FMNoiseSaopin (扫频噪声) | 载频线性扫描叠加噪声调频，覆盖范围广 |
| 压制干扰 | AMNoiseGaiJam (AM调幅) | 对载波幅度调制，频谱以载频对称 |
| 压制干扰 | SMSP (频谱弥散) | 子脉冲增大调频斜率，匹配滤波后弥散为假目标群 |
| 压制干扰 | NoiseProductJamming (噪声乘积) | LFM 与窄带噪声逐点相乘，随机分布假目标 |
| 压制干扰 | NoiseConvolutionJamming (噪声卷积) | LFM 与白噪声频域循环卷积，宽带遮蔽 |
| 压制/欺骗 | SliceCombineJam (切片组合) | 时域切片复制循环移位拼接 |
| 欺骗干扰 | RGPO (距离门拖引) | 复制 LFM 并逐步增加转发延迟 |
| 欺骗干扰 | ISDJ (间歇采样转发) | DRFM 式间歇采样转发，对称假目标群 |

## 抗干扰算法 (8 种)

| 算法 | 类型 | 原理 | 典型适用场景 |
|------|------|------|-------------|
| WLN (宽-限-窄) | 滤波 | 宽带滤波 -> 非线性限幅 -> 窄带滤波 | 调频阻塞干扰 |
| FrequencyDomainCanceller (频域对消) | 频域处理 | 利用 AM 干扰频谱共轭对称性对消 | 调幅干扰 |
| adapt_filter (自适应滤波) | 子空间投影 | 接收信号投影到发射信号子空间 | 卷积/乘积干扰 |
| frft_filter (FrFT 滤波) | 域变换 | 最优分数阶域掩膜提取目标 | 具有不同调频斜率的干扰 |
| FastSlowTimeProcessor (快慢时间) | 多维处理 | 距离-多普勒矩阵中切除干扰通道 | 切片/弥散干扰 |
| Frequency_agile (频率捷变) | 发射策略 | Costas 编码脉冲内跳频 | 瞄准式干扰 |
| wave_agile (波形捷变) | 发射策略 | 脉冲间切换不同 LFM/NLFM 波形 | DRFM 干扰 |
| qpzh (切片重组) | 滤波 | 分段限幅衰减突发干扰 | 脉冲切片类干扰 |

## 统一接口设计

所有干扰和抗干扰模块遵循标准化接口，便于组合测试。

### 干扰标准接口

```python
jammer = JammerClass(C=3e8, f0=15e6, T=20e-6, Tr=100e-6, B=5e6)
composite_signal, range_axis, info_dict = jammer.generate(R_target, JSR_dB=10, noise_var=0.1)
```

### 抗干扰标准接口

```python
processed_signal, processed_template = antijam_func(radar_par, par1=0.6, par2=6)
```

### 使用统一框架

```python
from unified_framework import run_simulation

results = run_simulation(
    jammer_type='FMZuse',
    antijam_type='WLN',
    radar_params={'f0': 15e6, 'Bw': 5e6, 'Pw': 20e-6, 'Fs': 50e6, 'target_dist': 6000},
    antijam_kwargs={'par1': 2.5, 'par2': 6}
)

print(f"抗干扰前: SINR={results['original']['evaluation']['sinr_db']:.2f} dB")
print(f"抗干扰后: SINR={results['processed']['evaluation']['sinr_db']:.2f} dB")
```

## 强化学习框架

基于 PPO (Proximal Policy Optimization) 训练智能体，使其自主观察雷达信号、选择抗干扰算法并调优参数。

### MDP 设计

- **状态空间**: 原始 IQ 时域信号 (实部+虚部双通道, shape `(2, 1024)`) + 干扰类型 one-hot 向量
- **动作空间**: 混合动作空间
  - 离散动作: 选择抗干扰算法 (6 种可选)
  - 连续动作: 算法参数 (最多 2 维，归一化到 [0,1])
- **奖励函数**: `reward = w_sinr * (SINR_after - SINR_before) + w_detect * I(detection)`

### 网络结构

```
输入信号 (B, 2, 1024) + one-hot (B, J)
        |
   1D-CNN 特征提取 (4 层 Conv1d + BN + ReLU + MaxPool)
        |
   全连接 -> 256 维特征
        |
   +---+---+
   |       |
Actor    Critic
(离散+连续混合输出)  (标量 V(s))
```

### 三种智能体

| 类型 | 输入 | 说明 |
|------|------|------|
| CPPO | 信号 CNN 特征 + one-hot | 利用原始信号信息，效果最好 |
| Standard PPO | 仅 one-hot | 小 MLP，不使用信号信息，作为消融实验 |
| Expert | - | 基于领域规则的固定策略，作为性能基线 |

### 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 训练 CPPO 智能体
python -m rl_framework.train --agent_type cppo --episodes 300

# 训练 Standard PPO
python -m rl_framework.train --agent_type std_ppo --episodes 300

# 评估模型
python -m rl_framework.evaluate --model rl_framework/checkpoints/ppo_best.pt

# 多策略对比
python rl_framework/run_comparison.py

# 绘制训练曲线
python rl_framework/plot_training_curves.py \
    --log_files rl_framework/checkpoints/training_history_cppo.npz \
                   rl_framework/checkpoints/training_history_std_ppo.npz \
    --labels CPPO "Standard PPO"
```

## 正确性测试结果

详见 `ROADMAP.md` 第一节"当前基线"。最新结果（CA-CFAR 修复后，检测率有区分度）。

## 依赖

```
numpy
scipy
torch
matplotlib
```

可选: `tensorboard` (训练日志可视化)

## 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| f0 | 15 MHz | 雷达中心频率 |
| Bw | 5 MHz | 信号带宽 |
| Pw | 20 us | 脉冲宽度 |
| Fs | 50 MHz | 采样率 |
| JSR_dB | 10 dB | 干信比 |
| target_dist | 6000 m | 目标距离 |
