"""
rl_framework/config.py
======================
所有可调参数集中管理：雷达参数、干扰/抗干扰列表、PPO 超参数、状态模式等。
"""

from copy import deepcopy


# =====================================================================
# 领域专家规则（干扰类型 → 推荐算法 + 归一化连续参数）
# =====================================================================
DEFAULT_EXPERT_RULES = {
    'FMNoiseAimedJam':       ('frft_filter',                [0.5, 0.5]),   # a≈1.0, w≈110
    'FMZuse':                ('WLN',                        [0.6]),         # par1≈1.54
    'AMNoiseGaiJam':         ('FrequencyDomainCanceller',   [1.0]),         # use_fitted=True
    'FMNoiseSaopin':         ('adapt_filter',               [0.5]),         # par1≈0.0
    'ISDJ':                  ('FastSlowTimeProcessor',      [0.35]),        # limit≈2.6
    'SMSP':                  ('WLN',                        [0.8]),         # par1≈2.0
    'NoiseProductJamming':   ('FrequencyDomainCanceller',   [1.0]),
    'NoiseConvolutionJamming': ('adapt_filter',             [0.3]),
    'RGPO':                  ('FastSlowTimeProcessor',      [0.5]),
}


class Config:
    # =================================================================
    # 雷达参数（降低以缩短信号长度，保证 state_len <= 1024）
    # =================================================================
    f0 = 15e6               # 载频 Hz
    Bw = 5e6                # 带宽 Hz
    Pw = 10e-6              # 脉宽 s
    Fs = 25e6               # 采样率 Hz
    Tr = 100e-6             # 脉冲重复周期 s
    target_dist = 6000      # 目标距离 m
    target_amp = 1.0        # 目标幅度
    jammer_amp = 8.0        # 干扰幅度（仅用于部分干扰器初始化）
    JSR_dB = 10             # 干信比 dB
    noise_var = 0.1         # 噪声方差

    # =================================================================
    # 信号处理 / 状态空间
    # =================================================================
    state_mode = 'raw_iq'   # 'raw_iq' 或 'range_profile'
    state_len = 1024        # 固定状态长度 L

    # =================================================================
    # 可用干扰列表（名称需与 JammerLoader.load() 兼容）
    # =================================================================
    jammer_list = [
        'FMNoiseAimedJam',
        'FMZuse',
        'AMNoiseGaiJam',
        'FMNoiseSaopin',
        'ISDJ',
        'SMSP',
        'NoiseProductJamming',
        'NoiseConvolutionJamming',
        'RGPO',
    ]
    # 干扰选择概率（等概率默认 None；也可指定 list 与 jammer_list 等长）
    jammer_probs = None

    # =================================================================
    # 可用抗干扰列表（名称需与 adapters.ANTIJAM_ADAPTERS 兼容）
    # =================================================================
    antijam_list = [
        'WLN',
        'FrequencyDomainCanceller',
        'adapt_filter',
        'frft_filter',
        'qpzh',
        'FastSlowTimeProcessor',
    ]

    # 每个算法的连续参数维度和映射范围
    #   key   : 算法名称 (antijam_list 中的)
    #   value : (dim, [[low1, high1], [low2, high2], ...])
    #   dim <= max_continuous_dim；若 dim < max_continuous_dim，
    #   多余的连续参数在解码时忽略
    algo_param_map = {
        'WLN':                       (1, [[0.1,  2.5]]),
        'FrequencyDomainCanceller':  (1, [[0.0,  1.0]]),   # use_fitted_freq: 0=False, 1=True
        'adapt_filter':              (1, [[-1.0, 1.0]]),   # par1
        'frft_filter':               (2, [[0.8,  1.2], [20, 200]]),  # a1, w
        'qpzh':                      (2, [[2,    10],  [2,  8]]),    # m, n
        'FastSlowTimeProcessor':     (1, [[1.5,  5.0]]),   # limit_factor
    }
    max_continuous_dim = 2    # 所有算法中最大的连续参数维度

    # =================================================================
    # PPO 超参数
    # =================================================================
    lr = 3e-4                # 学习率（actor / critic / feature 共用）
    gamma = 0.99             # 折扣因子
    gae_lambda = 0.95        # GAE lambda
    eps_clip = 0.2           # PPO 裁剪范围
    K_epochs = 10            # 每次更新的 epoch 数
    minibatch_size = 64      # mini-batch 大小
    entropy_coef = 0.01      # 熵正则系数
    value_clip = True        # 是否启用价值裁剪
    value_clip_eps = 0.2     # 价值裁剪范围
    max_grad_norm = 0.5      # 梯度裁剪范数

    # =================================================================
    # 网络结构
    # =================================================================
    conv_out_dim = 256       # 1D-CNN 输出特征维度
    fc_hidden_dim = 128      # Actor / Critic 全连接隐藏层维度
    log_std_min = -20        # 连续动作 log_std 下界
    log_std_max = 2          # 连续动作 log_std 上界

    # =================================================================
    # 训练
    # =================================================================
    max_episodes = 300      # 最大训练回合数
    steps_per_episode = 8    # 每回合脉冲数
    save_interval = 100      # 每隔多少回合保存模型
    eval_interval = 50       # 每隔多少回合进行评估
    log_interval = 10        # 每隔多少回合打印日志

    # =================================================================
    # 奖励
    # =================================================================
    reward_sinr_weight = 1.0     # SINR 改善权重 (dB)
    reward_detect_weight = 0.5   # 检测成功附加奖励

    # =================================================================
    # CA-CFAR 评估参数
    # =================================================================
    cfar_guard_cells = 4
    cfar_ref_cells = 20
    cfar_pfa = 1e-5

    # =================================================================
    # 日志 / 路径
    # =================================================================
    log_dir = 'runs/rl_anti_jam'
    model_save_dir = 'rl_framework/checkpoints'
    seed = 42
    device = 'auto'          # 'auto' | 'cpu' | 'cuda'

    # =================================================================
    # 智能体类型
    # =================================================================
    agent_type = 'cppo'            # 'cppo' | 'std_ppo' | 'expert'
    input_mode = 'signal_and_jammer'  # 'signal_and_jammer' | 'jammer_only'
    use_jammer_type = True         # True → 特征拼接 one-hot (CPPO); False → 不拼接 (StdPPO)
                                    # [已废弃] 请使用 input_mode; 仅用于旧 checkpoint 向后兼容
    continuous_action = True       # 是否使用连续动作空间
    expert_rules = {}              # Expert 映射表，默认用 DEFAULT_EXPERT_RULES


class CPPOConfig(Config):
    """CPPO 预设：信号 + 干扰 one-hot → CNN 特征 → 混合动作空间。"""
    agent_type = 'cppo'
    input_mode = 'signal_and_jammer'
    use_jammer_type = True
    continuous_action = True


class StdPPOConfig(Config):
    """Standard PPO 预设：仅干扰 one-hot → 小 MLP → 混合动作空间（不使用原始信号）。"""
    agent_type = 'std_ppo'
    input_mode = 'jammer_only'
    use_jammer_type = False
    continuous_action = True


class ExpertConfig(Config):
    """Expert 预设：固定规则策略（不训练）。"""
    agent_type = 'expert'
    input_mode = 'signal_and_jammer'
    use_jammer_type = False
    continuous_action = True
    expert_rules = {}              # 空字典 → 使用默认 DEFAULT_EXPERT_RULES


def resolve_config(config_or_name):
    """
    从 Config 实例或字符串名称解析出最终的 Config 对象。
    保证 expert_rules 总是有值。

    参数:
        config_or_name : Config 子类 / Config 实例 / str (类名)

    返回:
        Config 实例
    """
    if isinstance(config_or_name, str):
        name = config_or_name
        registry = {
            'Config': Config,
            'CPPOConfig': CPPOConfig,
            'StdPPOConfig': StdPPOConfig,
            'ExpertConfig': ExpertConfig,
        }
        if name not in registry:
            raise ValueError(f"Unknown config name: {name}. Available: {list(registry.keys())}")
        cfg = registry[name]()
    elif isinstance(config_or_name, type) and issubclass(config_or_name, Config):
        cfg = config_or_name()
    elif isinstance(config_or_name, Config):
        cfg = deepcopy(config_or_name)
    else:
        raise TypeError(f"Expected Config/str/class, got {type(config_or_name)}")

    # 确保 expert_rules 有默认值
    if not cfg.expert_rules:
        cfg.expert_rules = DEFAULT_EXPERT_RULES

    return cfg
