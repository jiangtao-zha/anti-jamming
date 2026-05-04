"""
rl_framework/agent_factory.py
=============================
智能体工厂函数：根据 Config 中的 agent_type / input_mode 创建对应的智能体实例。
"""

from rl_framework.expert import ExpertPolicy
from rl_framework.ppo_agent import PPOAgent


def create_agent(cfg, signal_shape, num_jammers):
    """
    根据 cfg.agent_type 创建智能体。

    参数:
        cfg           : Config 实例
        signal_shape  : (channels, L)
        num_jammers   : int, 干扰 one-hot 维度

    返回:
        PPOAgent 或 ExpertPolicy 实例
    """
    agent_type = cfg.agent_type

    if agent_type == 'expert':
        return ExpertPolicy(cfg)

    elif agent_type in ('cppo', 'std_ppo'):
        # input_mode 从 cfg 读取，默认:
        #   cppo    → 'signal_and_jammer'
        #   std_ppo → 'jammer_only'
        input_mode = getattr(cfg, 'input_mode', None)
        if input_mode is None:
            input_mode = 'signal_and_jammer' if agent_type == 'cppo' else 'jammer_only'

        cont = cfg.continuous_action
        return PPOAgent(
            signal_shape=signal_shape,
            num_jammers=num_jammers,
            cfg=cfg,
            input_mode=input_mode,
            continuous_action=cont,
        )

    else:
        raise ValueError(
            f"Unknown agent_type: {agent_type}. "
            f"Expected 'cppo', 'std_ppo', or 'expert'."
        )
