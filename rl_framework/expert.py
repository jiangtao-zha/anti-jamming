"""
rl_framework/expert.py
======================
基于领域知识的固定规则策略（非学习型）。
根据干扰类型 one-hot 直接返回预定义的（算法, 固定参数）。
"""

import numpy as np
from rl_framework.config import DEFAULT_EXPERT_RULES


class ExpertPolicy:
    """
    领域专家策略。

    接口与 PPOAgent.select_action() 兼容:
        select_action(state_dict) -> (discrete_idx, continuous_vals, log_prob=0.0, value=0.0)
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.jammer_list = list(cfg.jammer_list)
        self.antijam_list = list(cfg.antijam_list)
        # 若 cfg.expert_rules 为空或未设置，使用默认规则
        self.rules = dict(cfg.expert_rules) if cfg.expert_rules else dict(DEFAULT_EXPERT_RULES)
        self.max_continuous = cfg.max_continuous_dim

        # 构建快速查找表：jammer_name -> (discrete_idx, continuous_array)
        self._lookup = {}
        for jname, (algo_name, cont_vals) in self.rules.items():
            if algo_name in self.antijam_list:
                disc_idx = self.antijam_list.index(algo_name)
            else:
                disc_idx = 0
            cont = np.array(cont_vals, dtype=np.float32)
            if len(cont) < self.max_continuous:
                cont = np.pad(cont, (0, self.max_continuous - len(cont)),
                               constant_values=0.5)
            elif len(cont) > self.max_continuous:
                cont = cont[:self.max_continuous]
            self._lookup[jname] = (disc_idx, cont)

        # 默认兜底
        self._default = (
            0,
            np.full(self.max_continuous, 0.5, dtype=np.float32),
        )

    def select_action(self, state_dict, evaluate=False):
        """
        根据干扰 one-hot 查表返回预定义动作。

        参数:
            state_dict : {'signal': ..., 'jammer_onehot': np.array}

        返回:
            discrete_idx    : int
            continuous_vals : np.array (max_continuous_dim,)
            log_prob        : 0.0 (确定性策略)
            value           : 0.0
        """
        onehot = state_dict['jammer_onehot']
        jam_idx = int(np.argmax(onehot))
        jam_name = self.jammer_list[jam_idx] if jam_idx < len(self.jammer_list) else None

        disc_idx, cont_vals = self._lookup.get(jam_name, self._default)
        return disc_idx, cont_vals.copy(), 0.0, 0.0

    def update(self, buffer):
        """空方法（专家策略无需训练）。"""
        pass

    def save(self, filepath):
        """空方法。"""
        pass

    def load(self, filepath):
        """空方法。"""
        pass
