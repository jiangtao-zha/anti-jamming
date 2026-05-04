"""
rl_framework/ppo_agent.py
==========================
PPO (Proximal Policy Optimization) 智能体。

网络结构:
  1D-CNN 特征提取器 → 拼接干扰 one-hot → Actor / Critic 共享特征
  Actor:  FC → tanh → 分叉（离散 logits + 连续 mean/log_std）
  Critic: FC → tanh → 标量 V

连续动作采用 tanh-squashing + 对数概率校正（参考 antijamming_ppo.py）。
"""

import torch
import torch.nn as nn
from torch.distributions import Categorical, MultivariateNormal
import numpy as np

_epsilon = 1e-6


# =====================================================================
# 1. 1D-CNN 特征提取器
# =====================================================================
class FeatureExtractor(nn.Module):
    """
    处理原始信号 (1D CNN) 并与干扰 one-hot 拼接。

    输入:
        signal       : (batch, channels, L)   channels=2 (raw_iq) 或 1 (range_profile)
        jammer_onehot: (batch, J)
    输出:
        feature      : (batch, conv_out_dim + J)
    """

    def __init__(self, in_channels, state_len, conv_out_dim=256):
        super().__init__()
        self.conv_out_dim = conv_out_dim

        # 1D 卷积网络：逐步降采样至固定维度
        self.conv = nn.Sequential(
            # (B, C, L) -> (B, 16, L/4)
            nn.Conv1d(in_channels, 16, kernel_size=11, stride=4, padding=5),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            # -> (B, 32, ~L/12)
            nn.Conv1d(16, 32, kernel_size=7, stride=3, padding=3),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            # -> (B, 64, ~L/48)
            nn.Conv1d(32, 64, kernel_size=5, stride=2, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            # -> (B, 128, ~L/96)
            nn.Conv1d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            nn.Flatten(),
        )

        # 自适应线性层：将 flatten 后的特征投射到 conv_out_dim
        # 先做一次 forward 推算 flatten 维度
        self._flat_dim = None
        self.fc = None

        # 注册一个 dummy forward 来计算 flatten 维度
        self._in_channels = in_channels
        self._state_len = state_len

    def _init_fc(self, flat_dim):
        """延迟初始化全连接层（知道 flatten 维度后）。"""
        if self.fc is None:
            self.fc = nn.Sequential(
                nn.Linear(flat_dim, self.conv_out_dim),
                nn.ReLU(),
            )
            self._flat_dim = flat_dim

    def forward(self, signal, jammer_onehot):
        """
        参数:
            signal        : (batch, channels, L)
            jammer_onehot : (batch, J)
        返回:
            feature : (batch, conv_out_dim + J)
        """
        x = self.conv(signal)
        if self.fc is None:
            self._init_fc(x.shape[1])
            # 移至同一设备
            self.fc = self.fc.to(x.device)
        conv_feat = self.fc(x)  # (B, conv_out_dim)
        feature = torch.cat([conv_feat, jammer_onehot], dim=1)
        return feature


# =====================================================================
# 2. Actor 网络
# =====================================================================
class Actor(nn.Module):
    """
    混合动作空间 Actor：
      - 离散动作: Categorical (选择抗干扰算法)
      - 连续动作: MultivariateNormal + tanh squashing → [0, 1]
    """

    def __init__(self, feature_dim, num_discrete, num_continuous,
                 hidden_dim=128, log_std_min=-20, log_std_max=2):
        super().__init__()
        self.num_discrete = num_discrete
        self.num_continuous = num_continuous
        self.log_std_min = log_std_min
        self.log_std_max = log_std_max

        self.shared = nn.Sequential(
            nn.Linear(feature_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )

        # 离散动作头
        self.discrete_head = nn.Linear(hidden_dim, num_discrete)

        # 连续动作头 (mean + log_std)
        self.continuous_mean_head = nn.Linear(hidden_dim, num_continuous)
        self.continuous_log_std_head = nn.Linear(hidden_dim, num_continuous)

    def forward(self, feature):
        """
        返回:
            discrete_dist    : Categorical
            continuous_mean  : (B, num_continuous)，经 tanh 的 mean
            continuous_std   : (B, num_continuous)
        """
        x = self.shared(feature)

        # 离散
        discrete_logits = self.discrete_head(x)
        discrete_dist = Categorical(logits=discrete_logits)

        # 连续 — tanh-squashing 的 mean
        mean = torch.tanh(self.continuous_mean_head(x))  # (-1, 1)

        log_std = self.continuous_log_std_head(x)
        log_std = torch.clamp(log_std, min=self.log_std_min, max=self.log_std_max)
        std = torch.exp(log_std)

        return discrete_dist, mean, std

    def sample_action(self, feature):
        """
        采样动作并计算 corrected log prob (tanh squashing)。

        返回:
            discrete_action     : (B,) long
            continuous_action   : (B, num_continuous) float in [0, 1]
            log_prob            : (B,) float
        """
        discrete_dist, mean, std = self.forward(feature)

        # 离散采样
        discrete_action = discrete_dist.sample()

        # 连续采样: 从 base Gaussian 采样 → tanh → 缩放到 [0,1]
        base_dist = MultivariateNormal(mean, torch.diag_embed(std))
        pre_squash = base_dist.sample()
        squashed = torch.tanh(pre_squash)
        continuous_action = 0.5 * (squashed + 1.0)

        # --- 对数概率 + tanh 校正 ---
        base_log_prob = base_dist.log_prob(pre_squash)
        log_prob_correction = torch.log(1 - squashed.pow(2) + _epsilon)
        continuous_log_prob = base_log_prob - log_prob_correction.sum(axis=-1)

        discrete_log_prob = discrete_dist.log_prob(discrete_action)

        total_log_prob = continuous_log_prob + discrete_log_prob

        return discrete_action, continuous_action, total_log_prob

    def evaluate_action(self, feature, discrete_action, continuous_action):
        """
        给定 (feature, action)，重新计算 log_prob 和 entropy（用于 PPO 更新）。

        参数:
            feature            : (B, feature_dim)
            discrete_action    : (B,) long
            continuous_action   : (B, num_continuous) float in [0, 1]

        返回:
            log_prob  : (B,) 新对数概率
            entropy   : (B,) 总熵
        """
        discrete_dist, mean, std = self.forward(feature)
        base_dist = MultivariateNormal(mean, torch.diag_embed(std))

        # 反向变换: [0,1] -> (-1,1) -> atanh -> pre-squash
        neg1_1 = continuous_action * 2.0 - 1.0
        pre_squash = torch.atanh(torch.clamp(neg1_1, -1 + _epsilon, 1 - _epsilon))

        # base log prob
        base_log_prob = base_dist.log_prob(pre_squash)
        # tanh 校正
        log_prob_correction = torch.log(1 - neg1_1.pow(2) + _epsilon)
        continuous_log_prob = base_log_prob - log_prob_correction.sum(axis=-1)

        discrete_log_prob = discrete_dist.log_prob(discrete_action)

        total_log_prob = continuous_log_prob + discrete_log_prob

        # 熵
        continuous_entropy = base_dist.entropy()
        discrete_entropy = discrete_dist.entropy()
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
    PPO-Clip 智能体，封装 FeatureExtractor + Actor + Critic。
    """

    def __init__(self, cfg, signal_shape, num_jammers):
        """
        参数:
            cfg           : Config 实例
            signal_shape  : (channels, L)
            num_jammers   : int，干扰 one-hot 维度
        """
        self.cfg = cfg
        self.device = self._resolve_device(cfg.device)

        in_channels = signal_shape[0]
        num_discrete = len(cfg.antijam_list)
        num_continuous = cfg.max_continuous_dim
        self.feature_dim = cfg.conv_out_dim + num_jammers

        # 网络
        self.feature_extractor = FeatureExtractor(
            in_channels=in_channels,
            state_len=signal_shape[1],
            conv_out_dim=cfg.conv_out_dim,
        ).to(self.device)

        self.actor = Actor(
            feature_dim=self.feature_dim,
            num_discrete=num_discrete,
            num_continuous=num_continuous,
            hidden_dim=cfg.fc_hidden_dim,
            log_std_min=cfg.log_std_min,
            log_std_max=cfg.log_std_max,
        ).to(self.device)

        self.critic = Critic(
            feature_dim=self.feature_dim,
            hidden_dim=cfg.fc_hidden_dim,
        ).to(self.device)

        # 优化器
        self.optimizer = torch.optim.Adam(
            list(self.feature_extractor.parameters()) +
            list(self.actor.parameters()) +
            list(self.critic.parameters()),
            lr=cfg.lr,
        )

        # 超参数
        self.gamma = cfg.gamma
        self.gae_lambda = cfg.gae_lambda
        self.eps_clip = cfg.eps_clip
        self.K_epochs = cfg.K_epochs
        self.minibatch_size = cfg.minibatch_size
        self.entropy_coef = cfg.entropy_coef
        self.value_clip = cfg.value_clip
        self.value_clip_eps = cfg.value_clip_eps
        self.max_grad_norm = cfg.max_grad_norm

        # 训练统计
        self.actor_loss_val = 0.0
        self.critic_loss_val = 0.0

    @staticmethod
    def _resolve_device(device_str):
        if device_str == 'auto':
            return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        return torch.device(device_str)

    # -----------------------------------------------------------------
    # 动作选择 (推理用)
    # -----------------------------------------------------------------
    def select_action(self, state_dict):
        """
        根据状态选择动作（无梯度）。

        参数:
            state_dict : {'signal': np.array, 'jammer_onehot': np.array}

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
        continuous_vals = continuous_action.cpu().squeeze(0).numpy()
        return discrete_idx, continuous_vals, log_prob.cpu().item(), value.cpu().item()

    # -----------------------------------------------------------------
    # PPO 更新
    # -----------------------------------------------------------------
    def update(self, buffer):
        """
        使用 buffer 中的数据进行 PPO-Clip 更新。

        参数:
            buffer : RolloutBuffer 实例
        """
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

        # ---- GAE 计算 ----
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

        # 优势归一化
        adv_mean = advantages.mean()
        adv_std = advantages.std() + 1e-8
        advantages = (advantages - adv_mean) / adv_std

        # ---- 多 epoch mini-batch 更新 ----
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

                # 前向
                feature = self.feature_extractor(mb_signals, mb_onehots)
                new_logprobs, entropy = self.actor.evaluate_action(
                    feature, mb_discrete, mb_continuous)
                new_values = self.critic(feature).squeeze(-1)

                # PPO ratio
                ratios = torch.exp(new_logprobs - mb_logprobs)

                # Actor loss (clipped surrogate)
                surr1 = ratios * mb_advantages
                surr2 = torch.clamp(ratios, 1 - self.eps_clip,
                                    1 + self.eps_clip) * mb_advantages
                actor_loss = -torch.min(surr1, surr2).mean() - self.entropy_coef * entropy.mean()

                # Critic loss (可选 value clipping)
                if self.value_clip:
                    clipped_values = old_values[mb_idx] + torch.clamp(
                        new_values - old_values[mb_idx],
                        -self.value_clip_eps, self.value_clip_eps)
                    critic_loss = torch.max(
                        nn.functional.mse_loss(new_values, mb_returns),
                        nn.functional.mse_loss(clipped_values, mb_returns)
                    )
                else:
                    critic_loss = nn.functional.mse_loss(new_values, mb_returns)

                # 反向
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

            # 记录第一轮 epoch 的 loss
            if epoch == 0:
                self.actor_loss_val = actor_loss.item()
                self.critic_loss_val = critic_loss.item()

        buffer.clear()

    # -----------------------------------------------------------------
    # 保存 / 加载
    # -----------------------------------------------------------------
    def save(self, filepath):
        torch.save({
            'feature_extractor': self.feature_extractor.state_dict(),
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
            'optimizer': self.optimizer.state_dict(),
        }, filepath)

    def load(self, filepath):
        checkpoint = torch.load(filepath, map_location=self.device)
        self.feature_extractor.load_state_dict(checkpoint['feature_extractor'])
        self.actor.load_state_dict(checkpoint['actor'])
        self.critic.load_state_dict(checkpoint['critic'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
