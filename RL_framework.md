```markdown
# 任务：构建抗干扰强化学习（PPO）智能体框架

## 背景
你有一个雷达抗干扰仿真系统，目录结构如下：
- `anti_jamming/`：内含 8 种抗干扰算法（WLN、频域对消、自适应滤波、波形捷变、频率捷变、FrFT 滤波、切片重组、快慢时间处理）。通过 `adapters.py` 中的适配器提供统一调用接口，形如 `antijam_func(radar_par, **kwargs)`，返回 `(processed_signal, processed_template)`。
- `jamming/`：内含 9 种干扰样式（FMZuse、RGPO、ISDJ、SMSP、噪声乘积、噪声卷积、FMNoiseSaopin、FMNoiseAimedJam、AMNoiseGaiJam）。通过 `JammerLoader` 动态加载，生成干扰信号的三元组 `(j_signal, range_axis, info_dict)`。
- `unified_framework.py`：提供 `RadarEnvironment` 类，可生成匹配滤波模板、多脉冲回波矩阵，并嵌入干扰。
- 你手头有一个参考文件 `antijamming_ppo.py`，实现了基于 CNN 特征提取的 PPO（Actor‑Critic，离散+连续混合动作空间），包含 tanh 压缩连续动作、对数概率校正等关键技巧，但原来是为另一个任务写的。你需要基于该代码的思想重构并扩展，使其适配当前雷达抗干扰场景。

## 任务目标
在项目根目录下新建文件夹 `rl_framework/`，在其中实现一个强化学习框架，用于训练抗干扰智能体。智能体**直接观察雷达接收到的原始时域复数信号**，自主选择抗干扰算法及其参数，以最大化抗干扰后的 SINR 改善。

### 核心设计
1. **状态空间**（可配置，默认为原始 IQ 模式）  
   - **主模式 `raw_iq`**：使用原始复数时域信号的实部和虚部作为双通道输入，形状 `(2, L)`，其中 `L` 是固定的时间点数（通过调整雷达参数保证 ≤1024）。预处理：对每个通道单独做减去均值除以标准差的归一化。  
   - **辅助信息**：在特征提取阶段将**干扰类型 one‑hot**（长度等于配置中可用干扰的数量）与卷积特征拼接，帮助网络区分场景。  
   - **备选模式 `range_profile`**：采用脉冲压缩后的距离像幅度谱（长度固定为 `state_len`，同样可拼接干扰 one‑hot），以便对比实验。两种模式由 `config.py` 中的 `state_mode` 切换。

2. **动作空间**：混合动作空间，参考提供的 `antijamming_ppo.py`。  
   - **离散动作**：选择一种抗干扰算法（具体列表在 `config.py` 中可配）。  
   - **连续动作**：对应所选算法的参数，统一归一化到 `[0, 1]`，由环境解码映射到实际参数范围（例如 WLN 的阈值、FrFT 的旋转阶数和掩膜宽度等）。每个算法最多 2 个连续参数（具体由配置决定）。  
   - **网络输出**：Actor 同时输出离散动作的 logits 和每个连续参数的均值/对数标准差（经 tanh 压缩到 `[0,1]`），并计算相应的对数概率（包含 tanh 校正）。

3. **奖励**：抗干扰后 SINR 减去抗干扰前 SINR（单位 dB）。可附加一个小的检测成功奖励，均需在 `config.py` 中配置权重。

4. **回合与步**：一个完整脉冲接收 → 抗干扰处理 → 评估为一步。一个回合包含固定数量的脉冲（如 8～16），每个脉冲可独立决策。干扰样式在一个回合内保持不变或按概率缓慢变化，回合结束后返回累计奖励或平均 SINR 改善。

5. **PPO 算法**：实现完整的 PPO‑Clip，包含 GAE 优势估计、多 epoch 小批量更新、价值裁剪。特征提取网络使用 1D 卷积处理信号部分，然后与干扰 one‑hot 拼接。

6. **集成现有模块**：
   - 使用 `jamming/` 中的类生成干扰，通过 `JammerLoader` 动态加载。
   - 使用 `anti_jamming/adapters.py` 中的 `get_antijam_func(action_name)` 获得抗干扰函数。
   - 复用 `unified_framework.py` 中的 `RadarEnvironment` 生成基带波形和匹配滤波模板，但需调整雷达参数以缩短时域信号长度。

7. **信号长度控制**：为保证原始 IQ 输入维度在 `L ≤ 1024`，建议调整雷达参数，例如：降低采样率 `Fs` 至 20~30 MHz，缩短脉宽 `Pw` 至 5~10 μs，接收窗限制在目标存在区间。具体可配置，并在环境初始化时自动处理。

## 输出文件结构
```
rl_framework/
├── config.py          # 所有可调参数（雷达参数、干扰/抗干扰列表、PPO超参数、状态模式等）
├── environment.py     # 抗干扰MDP环境（状态预处理、动作解码、奖励计算、重置/步进）
├── ppo_agent.py       # PPO模型类（特征提取器、Actor、Critic、select_action、update）
├── train.py           # 训练主循环（支持TensorBoard日志、模型保存、中断恢复）
├── evaluate.py        # 评估脚本（对比：无抗干扰、随机算法、PPO智能体的SINR和检测率）
├── utils.py           # 经验回放缓冲区、归一化工具、参数解码辅助函数
├── README.md          # 使用说明（如何运行训练和评估、状态动作空间描述、配置修改方法）
└── 总结报告.md        # 设计总结与实验结果分析
```

## 详细实现指引

### environment.py
- 初始化时加载雷达参数、可用干扰与抗干扰列表、状态模式 `state_mode`（`'raw_iq'` 或 `'range_profile'`）。
- `reset()`：随机选择干扰类型（或按配置的概率），调用 `RadarEnvironment` 生成受干扰回波矩阵 `Srt_matrix`（维度 `(1, N)` 或 `(M, N)`，此处可先使用单脉冲 `M=1`）。根据 `state_mode` 提取状态向量：  
  - `raw_iq`：取 `Srt_matrix[0]`，分离实部/虚部 → 形状 `(2, N)`；归一化每个通道（`(x - mean)/std`）；若 `N > L`，则截取目标附近一段或下采样至 `L`；若 `N < L`，则零填充。  
  - `range_profile`：先做匹配滤波得到距离像幅度，截取/缩放至固定长度 `L`。  
  同时维护当前干扰的 one‑hot 向量（维度 = `len(jammer_list)`），存储在环境属性中，但不直接拼入状态数组（将在 PPO 特征提取时拼接）。状态字典返回 `{'signal': state_array, 'jammer_onehot': onehot_array}`，或直接返回一个拼接后的向量（建议在 PPO 模型内部进行拼接，环境只返回原始分量）。
- `step(action)`：  
  - 从动作解析出离散算法索引和连续参数（解码需依据配置中每个算法的参数映射，解码函数放在 `utils.py`）。  
  - 调用对应抗干扰适配器处理回波，得到 `processed_signal`。  
  - 计算处理前后的 SINR（复用 `JamSuppressionEvaluator` 或自行实现匹配滤波后峰值信噪比）。  
  - 奖励 = `sinr_after - sinr_before`（可加检测项）。  
  - 更新回合计数器，若回合结束则 `done = True`。  
  - 返回 `(next_state, reward, done, info)`，其中 `next_state` 是基于同一个脉冲处理后的新接收信号？注意：抗干扰是对当前脉冲的处理，处理完此脉冲后回合可能尚未结束，但下一个脉冲的接收信号应由环境重新生成（可保持不变干扰参数，或用新干扰）。这里建议**每步处理一个脉冲，然后环境生成下一个脉冲的状态**，即 `step` 返回的是处理后的奖励和下一个未处理脉冲的状态。也可以设计为：一个回合只有一个抗干扰动作，处理一批脉冲的平均。选择简单方案：每步一个脉冲，处理完即生成下一个脉冲的状态。
- `render()`：可选，用于调试时绘制时域波形或距离像。

### ppo_agent.py
- 特征提取器 `FeatureExtractor`：  
  - 若 `state_mode='raw_iq'`，信号部分形状 `(batch, 2, L)` → 1D Conv 网络（参考提供的 `antijamming_ppo.py` 的卷积结构，但需调整输入通道为 2，输出特征维度可设为 256）。  
  - 若 `state_mode='range_profile'`，信号部分形状 `(batch, 1, L)` → 类似 1D Conv。  
  - 同时接收 `jammer_onehot`（形状 `(batch, J)`），与卷积特征拼接得到 `(batch, conv_dim+J)`。  
- Actor 网络：输入拼接特征 → 两层全连接（含 Tanh） → 分叉：  
  - 离散动作 logits → `(batch, num_antijam_algos)`  
  - 连续动作均值 → `(batch, max_continuous_dim)`，经 Tanh 输出（训练时作为 squashed 动作的均值，实际采样时再经 Tanh + 缩放至 [0,1]）  
  - 连续动作对数标准差 → `(batch, max_continuous_dim)`，用 clamp 保证数值稳定。  
  注意：只有被选中的离散动作对应的连续参数有效，其余可以忽略或掩膜。网络可以始终输出所有连续参数，环境在解码时根据离散动作选取需要的维度。  
- Critic 网络：输入拼接特征 → 全连接 → 输出标量 V。
- `select_action(state_dict)`：返回动作元组（离散索引, 连续参数数组）、对数概率、价值。
- `evaluate_action(state_dict, discrete_idx, continuous_vals)`：返回新对数概率、熵，用于更新时计算比率。
- `update(buffer)`：实现 PPO‑Clip，包含 GAE 计算、优势归一化、多 epoch 小批量更新。
- 保存/加载模型权重（包含优化器状态）。

### config.py
建议包含以下配置类或字典：
```python
class Config:
    # 雷达参数（可调小以缩短信号长度）
    f0 = 15e6          # 载频 Hz
    B = 5e6            # 带宽 Hz
    Pw = 10e-6         # 脉宽 s
    Fs = 25e6          # 采样率 Hz（降到 25MHz，信号点数约 250+接收窗）
    Tr = 100e-6        # 脉冲重复周期
    target_dist = 6000 # 目标距离 m
    # 信号处理
    state_mode = 'raw_iq'               # 'raw_iq' 或 'range_profile'
    state_len = 1024                    # 固定状态长度
    jammer_list = ['FMNoiseAimedJam', 'FMZuse', 'AMNoiseGaiJam', ...]
    antijam_list = ['WLN', 'FrequencyDomainCanceller', 'adapt_filter', 'frft_filter', 'FastSlowTimeProcessor']
    # 每个算法的连续参数维度和映射范围： { algo: (dim, [[low1,high1], [low2,high2]]) }
    algo_param_map = {
        'WLN': (1, [[0.1, 1.6]]),
        'frft_filter': (2, [[0.8, 1.2], [20, 200]]),
        ...
    }
    # PPO 超参数
    lr = 3e-4
    gamma = 0.99
    gae_lambda = 0.95
    eps_clip = 0.2
    K_epochs = 10
    minibatch_size = 64
    # 训练
    max_episodes = 5000
    steps_per_episode = 8  # 每回合脉冲数
    # 日志
    log_dir = 'runs/'
```

### train.py
- 解析 config，初始化环境、PPO 模型、SummaryWriter。
- 循环 episodes：重置环境获得初始状态 → for t in range(steps_per_episode)：选择动作 → 执行动作 → 存储元组 → 更新状态 → 若回合结束或步数到则 break → 进行 PPO 更新 → 清空 buffer → 记录日志。
- 定期保存模型。

### evaluate.py
- 加载训练好的模型，固定雷达参数和干扰列表，循环测试若干回合。
- 对于每个干扰类型，分别计算：  
  - NoJammer（无干扰）时的基准 SINR  
  - 使用抗干扰前（原始受干扰信号）的 SINR  
  - 随机选择抗干扰算法的平均 SINR  
  - PPO 智能体选择的平均 SINR  
- 输出表格和简要分析。

### utils.py
- `RolloutBuffer` 类（类似参考代码）。
- 参数解码函数 `decode_action(algo_idx, continuous_vals, config)`，返回 `(algo_name, param_dict)`。
- 状态预处理函数 `preprocess_raw_iq(signal, target_len)` 和 `preprocess_range_profile(signal, template, target_len)`。
- SINR 计算函数（可通过匹配滤波后峰值与旁瓣平均计算）。

## 总结报告要求（总结报告.md）
1. MDP 设计阐述：为何选择原始 IQ 信号作为状态输入，动作空间设计，奖励函数选择原因。
2. 网络结构图（可用文字描述）与 PPO‑Clip 更新公式。
3. 与现有工程结合的接口说明：如何加载干扰和抗干扰模块，适配器调用方式。
4. 预期实验结果（可作假设性描述，如预期训练曲线趋势，不同模式对比）。
5. 局限性讨论：例如强干扰下时域信号淹没目标的困难、动作空间离散连续混合带来的探索挑战、训练时间需求等，并提供潜在改进方向（如加入循环网络、注意力机制、多脉冲上下文）。

## 参考
提供的 `antijamming_ppo.py` 实现了混合动作空间 PPO 的核心技巧，特别是连续动作的 tanh 压缩和对数概率校正，应仔细参考并整合。

---

请严格按照上述要求实现全部代码，确保代码在 Python 3.8+、PyTorch >=1.10 环境下可运行，并处理好与现有模块的相对导入。
```