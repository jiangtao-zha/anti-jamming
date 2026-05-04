"""
rl_framework/ppo_agent.py
=========================
PPO (Proximal Policy Optimization) 智能体。

网络结构 (根据 input_mode 切换):
  signal_and_jammer:
    1D-CNN 特征提取器 → 拼接干扰 one-hot → Actor / Critic
  jammer_only:
    干扰 one-hot → 小 MLP (Linear → ReLU → Linear → ReLU) → Actor / Critic

  Actor:  FC → tanh → 分叉（离散 logits + 连续 mean/log_std）
  Critic: FC → tanh → 标量 V

连续动作采用 tanh-squashing + 对数概率校正（参考 antijamming_ppo.py）。

input_mode='signal_and_jammer' → CPPO (CNN + one-hot)
input_mode='jammer_only'       → Standard PPO (仅 one-hot MLP)
"""

import torch
import torch.nn as nn
from torch.distributions import Categorical, MultivariateNormal
import numpy as np

_epsilon = 1e-6


# =====================================================================
# 1. 特征提取器 (支持两种 input_mode)
# =====================================================================
class FeatureExtractor(nn.Module):
    """
    根据 input_mode 选择特征提取方式:
      'signal_and_jammer': 1D-CNN 处理信号 + 拼接 one-hot
      'jammer_only':       小 MLP 处理 one-hot（不使用原始信号）

    参数:
        in_channels   : 信号通道数 (仅 signal_and_jammer 使用)
        state_len     : 信号长度   (仅 signal_and_jammer 使用)
        num_jammers   : 干扰类型数  (one-hot 维度)
        output_dim    : 输出特征维度
        input_mode    : 'signal_and_jammer' | 'jammer_only'
    """

    def __init__(self, in_channels=2, state_len=1024, num_jammers=9,
                 output_dim=256, input_mode='signal_and_jammer'):
        super().__init__()
        self.input_mode = input_mode
        self.output_dim = output_dim
        self.num_jammers = num_jammers

        if input_mode == 'signal_and_jammer':
            self.conv_out_dim = output_dim - num_jammers
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 16, kernel_size=11, stride=4, padding=5),
                nn.BatchNorm1d(16),
                nn.ReLU(),
                nn.MaxPool1d(kernel_size=3, stride=2),

                nn.Conv1d(16, 32, kernel_size=7, stride=3, padding=3),
                nn.BatchNorm1d(32),
                nn.ReLU(),
                nn.MaxPool1d(kernel_size=3, stride=2),

                nn.Conv1d(32, 64, kernel_size=5, stride=2, padding=2),
                nn.BatchNorm1d(64),
                nn.ReLU(),
                nn.MaxPool1d(kernel_size=3, stride=2),

                nn.Conv1d(64, 128, kernel_size=3, stride=1, padding=1),
                nn.BatchNorm1d(128),
                nn.ReLU(),
                nn.MaxPool1d(kernel_size=3, stride=2),

                nn.Flatten(),
            )

            self._flat_dim = None
            self.fc = None
            self._in_channels = in_channels
            self._state_len = state_len

            # jammer_only MLP 不需要
            self.mlp = None

        elif input_mode == 'jammer_only':
            # 小 MLP: one-hot (J) → hidden → output_dim
            hidden_dim = 128
            self.mlp = nn.Sequential(
                nn.Linear(num_jammers, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, output_dim),
                nn.ReLU(),
            )
            # CNN 相关占位 (backward compat，不使用)
            self.conv = None
            self.fc = None
            self._flat_dim = None
        else:
            raise ValueError(f"Unknown input_mode: {input_mode}. "
                             f"Expected 'signal_and_jammer' or 'jammer_only'.")

    def _init_fc(self, flat_dim):
        if self.fc is None:
            self.fc = nn.Sequential(
                nn.Linear(flat_dim, self.conv_out_dim),
                nn.ReLU(),
            )
            self._flat_dim = flat_dim

    def forward(self, signal, jammer_onehot=None):
        if self.input_mode == 'signal_and_jammer':
            x = self.conv(signal)
            if self.fc is None:
                self._init_fc(x.shape[1])
                self.fc = self.fc.to(x.device)
            conv_feat = self.fc(x)
            if jammer_onehot is not None:
                return torch.cat([conv_feat, jammer_onehot], dim=1)
            return conv_feat

        elif self.input_mode == 'jammer_only':
            return self.mlp(jammer_onehot)


# =====================================================================
# 2. Actor 网络
# =====================================================================
class Actor(nn.Module):
    """
    混合动作空间 Actor：
      - 离散动作: Categorical
      - 连续动作: MultivariateNormal + tanh squashing → [0, 1]
    """

    def __init__(self, feature_dim, num_discrete, num_continuous,
                 hidden_dim=128, log_std_min=-20, log_std_max=2,
                 continuous_action=True):
        super().__init__()
        self.num_discrete = num_discrete
        self.num_continuous = num_continuous if continuous_action else 0
        self.log_std_min = log_std_min
        self.log_std_max = log_std_max

        self.shared = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )

        self.discrete_head = nn.Linear(hidden_dim, num_discrete)

        if self.num_continuous > 0:
            self.continuous_mean_head = nn.Linear(hidden_dim, self.num_continuous)
            self.continuous_log_std_head = nn.Linear(hidden_dim, self.num_continuous)
        else:
            self.continuous_mean_head = None
            self.continuous_log_std_head = None

    def forward(self, feature):
        x = self.shared(feature)

        discrete_logits = self.discrete_head(x)
        discrete_dist = Categorical(logits=discrete_logits)

        if self.num_continuous > 0:
            mean = torch.tanh(self.continuous_mean_head(x))
            log_std = self.continuous_log_std_head(x)
            log_std = torch.clamp(log_std, min=self.log_std_min, max=self.log_std_max)
            std = torch.exp(log_std)
        else:
            mean = std = None

        return discrete_dist, mean, std

    def sample_action(self, feature):
        discrete_dist, mean, std = self.forward(feature)
        discrete_action = discrete_dist.sample()
        discrete_log_prob = discrete_dist.log_prob(discrete_action)

        if self.num_continuous > 0 and mean is not None:
            base_dist = MultivariateNormal(mean, torch.diag_embed(std))
            pre_squash = base_dist.sample()
            squashed = torch.tanh(pre_squash)
            continuous_action = 0.5 * (squashed + 1.0)

            base_log_prob = base_dist.log_prob(pre_squash)
            log_prob_correction = torch.log(1 - squashed.pow(2) + _epsilon)
            continuous_log_prob = base_log_prob - log_prob_correction.sum(axis=-1)
        else:
            continuous_action = torch.zeros(
                feature.shape[0], 0, device=feature.device, dtype=torch.float32)
            continuous_log_prob = torch.zeros(feature.shape[0], device=feature.device)

        total_log_prob = continuous_log_prob + discrete_log_prob
        return discrete_action, continuous_action, total_log_prob

    def evaluate_action(self, feature, discrete_action, continuous_action):
        discrete_dist, mean, std = self.forward(feature)

        if self.num_continuous > 0 and mean is not None:
            base_dist = MultivariateNormal(mean, torch.diag_embed(std))
            neg1_1 = continuous_action * 2.0 - 1.0
            pre_squash = torch.atanh(torch.clamp(neg1_1, -1 + _epsilon, 1 - _epsilon))
            base_log_prob = base_dist.log_prob(pre_squash)
            log_prob_correction = torch.log(1 - neg1_1.pow(2) + _epsilon)
            continuous_log_prob = base_log_prob - log_prob_correction.sum(axis=-1)
            continuous_entropy = base_dist.entropy()
        else:
            continuous_log_prob = torch.zeros(feature.shape[0], device=feature.device)
            continuous_entropy = torch.zeros(feature.shape[0], device=feature.device)

        discrete_log_prob = discrete_dist.log_prob(discrete_action)
        discrete_entropy = discrete_dist.entropy()

        total_log_prob = continuous_log_prob + discrete_log_prob
        total_entropy = continuous_entropy + discrete_entropy
        return total_log_prob, total_entropy


# =====================================================================
# 3. Critic 网络
# =====================================================================
class Critic(nn.Module):
    """价值网络 V(s)。"""

    def __init__(self, feature_dim, hidden_dim=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, feature):
        return self.net(feature)


# =====================================================================
# 4. PPO 主类
# =====================================================================
class PPOAgent:
    """
    PPO-Clip 智能体。

    input_mode='signal_and_jammer' → CPPO (CNN 提取信号特征 + 拼接 one-hot)
    input_mode='jammer_only'       → Standard PPO (仅 one-hot → 小 MLP)
    """

    def __init__(self, signal_shape, num_jammers, cfg=None, *,
                 use_jammer_type=True, continuous_action=True,
                 input_mode=None):
        if cfg is None:
            from rl_framework.config import Config
            cfg = Config()
        self.cfg = cfg
        self.device = self._resolve_device(cfg.device)
        self.continuous_action = continuous_action

        # 确定 input_mode（显式参数优先，其次 cfg，最后从 use_jammer_type 推断）
        if input_mode is not None:
            self.input_mode = input_mode
        elif hasattr(cfg, 'input_mode') and cfg.input_mode in (
                'signal_and_jammer', 'jammer_only'):
            self.input_mode = cfg.input_mode
        else:
            # 向后兼容：从 use_jammer_type 推断
            self.input_mode = 'signal_and_jammer' if use_jammer_type else 'jammer_only'

        in_channels = signal_shape[0]
        num_discrete = len(cfg.antijam_list)
        num_continuous = cfg.max_continuous_dim if continuous_action else 0

        # feature_dim: signal_and_jammer = conv_out_dim + num_jammers; jammer_only = conv_out_dim
        if self.input_mode == 'signal_and_jammer':
            self.feature_dim = cfg.conv_out_dim + num_jammers
        else:  # jammer_only
            self.feature_dim = cfg.conv_out_dim  # MLP 直接输出此维度

        self.feature_extractor = FeatureExtractor(
            in_channels=in_channels,
            state_len=signal_shape[1],
            num_jammers=num_jammers,
            output_dim=self.feature_dim,
            input_mode=self.input_mode,
        ).to(self.device)

        self.actor = Actor(
            feature_dim=self.feature_dim,
            num_discrete=num_discrete,
            num_continuous=num_continuous,
            hidden_dim=cfg.fc_hidden_dim,
            log_std_min=cfg.log_std_min,
            log_std_max=cfg.log_std_max,
            continuous_action=continuous_action,
        ).to(self.device)

        self.critic = Critic(
            feature_dim=self.feature_dim,
            hidden_dim=cfg.fc_hidden_dim,
        ).to(self.device)

        self.optimizer = torch.optim.Adam(
            list(self.feature_extractor.parameters()) +
            list(self.actor.parameters()) +
            list(self.critic.parameters()),
            lr=cfg.lr,
        )

        self.gamma = cfg.gamma
        self.gae_lambda = cfg.gae_lambda
        self.eps_clip = cfg.eps_clip
        self.K_epochs = cfg.K_epochs
        self.minibatch_size = cfg.minibatch_size
        self.entropy_coef = cfg.entropy_coef
        self.value_clip = cfg.value_clip
        self.value_clip_eps = cfg.value_clip_eps
        self.max_grad_norm = cfg.max_grad_norm
        self.max_continuous_dim = cfg.max_continuous_dim

        self.actor_loss_val = 0.0
        self.critic_loss_val = 0.0

    @staticmethod
    def _resolve_device(device_str):
        if device_str == 'auto':
            return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        return torch.device(device_str)

    def select_action(self, state_dict):
        """
        根据状态选择动作（无梯度）。

        返回:
            discrete_idx    : int
            continuous_vals : np.array (max_continuous_dim,)
            logprob         : float
            value           : float
        """
        signal_t = torch.tensor(
            state_dict['signal'], dtype=torch.float32).unsqueeze(0).to(self.device)
        onehot_t = torch.tensor(
            state_dict['jammer_onehot'], dtype=torch.float32).unsqueeze(0).to(self.device)

        with torch.no_grad():
            feature = self.feature_extractor(signal_t, onehot_t)
            discrete_action, continuous_action, log_prob = self.actor.sample_action(feature)
            value = self.critic(feature)

        discrete_idx = discrete_action.cpu().item()
        if self.continuous_action:
            continuous_vals = continuous_action.cpu().squeeze(0).numpy()
        else:
            continuous_vals = np.zeros(self.max_continuous_dim, dtype=np.float32)
        return discrete_idx, continuous_vals, log_prob.cpu().item(), value.cpu().item()

    def update(self, buffer):
        """使用 buffer 中的数据进行 PPO-Clip 更新。"""
        data = buffer.get_tensors(self.device)
        signals = data['signals']
        onehots = data['jammer_onehots']
        old_discrete = data['discrete_actions']
        old_continuous = data['continuous_actions']
        old_logprobs = data['logprobs']
        rewards = data['rewards']
        dones = data['dones']
        old_values = data['values']

        batch_size = signals.shape[0]

        # GAE
        advantages = torch.zeros(batch_size, device=self.device)
        last_advantage = 0.0
        for t in reversed(range(batch_size)):
            if t == batch_size - 1:
                next_non_terminal = 1.0 - dones[t]
                next_value = 0.0
            else:
                next_non_terminal = 1.0 - dones[t]
                next_value = old_values[t + 1]
            delta = rewards[t] + self.gamma * next_value * next_non_terminal - old_values[t]
            last_advantage = (delta +
                              self.gamma * self.gae_lambda * next_non_terminal * last_advantage)
            advantages[t] = last_advantage

        returns = advantages + old_values
        adv_mean = advantages.mean()
        adv_std = advantages.std() + 1e-8
        advantages = (advantages - adv_mean) / adv_std

        for epoch in range(self.K_epochs):
            indices = torch.randperm(batch_size, device=self.device)
            for start in range(0, batch_size, self.minibatch_size):
                end = start + self.minibatch_size
                mb_idx = indices[start:end]

                mb_signals = signals[mb_idx]
                mb_onehots = onehots[mb_idx]
                mb_discrete = old_discrete[mb_idx]
                mb_continuous = old_continuous[mb_idx]
                mb_logprobs = old_logprobs[mb_idx]
                mb_advantages = advantages[mb_idx]
                mb_returns = returns[mb_idx]

                feature = self.feature_extractor(mb_signals, mb_onehots)
                new_logprobs, entropy = self.actor.evaluate_action(
                    feature, mb_discrete, mb_continuous)
                new_values = self.critic(feature).squeeze(-1)

                ratios = torch.exp(new_logprobs - mb_logprobs)
                surr1 = ratios * mb_advantages
                surr2 = torch.clamp(ratios, 1 - self.eps_clip,
                                    1 + self.eps_clip) * mb_advantages
                actor_loss = -torch.min(surr1, surr2).mean() - self.entropy_coef * entropy.mean()

                if self.value_clip:
                    clipped_values = old_values[mb_idx] + torch.clamp(
                        new_values - old_values[mb_idx],
                        -self.value_clip_eps, self.value_clip_eps)
                    critic_loss = torch.max(
                        nn.functional.mse_loss(new_values, mb_returns),
                        nn.functional.mse_loss(clipped_values, mb_returns))
                else:
                    critic_loss = nn.functional.mse_loss(new_values, mb_returns)

                self.optimizer.zero_grad()
                total_loss = actor_loss + 0.5 * critic_loss
                total_loss.backward()
                nn.utils.clip_grad_norm_(
                    list(self.feature_extractor.parameters()) +
                    list(self.actor.parameters()) +
                    list(self.critic.parameters()),
                    self.max_grad_norm,
                )
                self.optimizer.step()

            if epoch == 0:
                self.actor_loss_val = actor_loss.item()
                self.critic_loss_val = critic_loss.item()

        buffer.clear()

    def save(self, filepath):
        torch.save({
            'feature_extractor': self.feature_extractor.state_dict(),
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'input_mode': self.input_mode,
            'continuous_action': self.continuous_action,
            'use_jammer_type': (self.input_mode == 'signal_and_jammer'),
        }, filepath)

    def load(self, filepath):
        checkpoint = torch.load(filepath, map_location=self.device)

        # 校验 input_mode 一致性（必须在 load_state_dict 之前，否则会得到
        # 不易理解的 missing/unexpected key 错误）
        saved_input_mode = checkpoint.get('input_mode', None)
        if saved_input_mode is not None and saved_input_mode != self.input_mode:
            raise ValueError(
                f"Checkpoint input_mode='{saved_input_mode}' 与当前 "
                f"input_mode='{self.input_mode}' 不一致，无法加载。"
                f"\n  请确保 agent 的 input_mode 与训练时一致。"
                f"\n  checkpoint 路径: {filepath}")

        # 旧 checkpoint 兼容（只有 use_jammer_type 字段，无 input_mode）
        if saved_input_mode is None:
            saved_ujt = checkpoint.get('use_jammer_type', None)
            if saved_ujt is not None:
                inferred = 'signal_and_jammer' if saved_ujt else 'jammer_only'
                if inferred != self.input_mode:
                    raise ValueError(
                        f"旧 checkpoint use_jammer_type={saved_ujt} "
                        f"推断 input_mode='{inferred}'，与当前 "
                        f"input_mode='{self.input_mode}' 不一致，无法加载。"
                        f"\n  请确保 agent 的 input_mode 与训练时一致。"
                        f"\n  checkpoint 路径: {filepath}")

        self.feature_extractor.load_state_dict(checkpoint['feature_extractor'])
        self.actor.load_state_dict(checkpoint['actor'])
        self.critic.load_state_dict(checkpoint['critic'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])

        saved_ca = checkpoint.get('continuous_action', self.continuous_action)
        if saved_ca != self.continuous_action:
            print(f"[warn] checkpoint continuous_action={saved_ca} "
                  f"与当前 continuous_action={self.continuous_action} 不一致")
