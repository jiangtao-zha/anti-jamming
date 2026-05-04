import torch
import torch.nn as nn
from torch.distributions import MultivariateNormal, Categorical
import numpy as np
from torch.utils.tensorboard import SummaryWriter
import datetime

# from env_test import MonsterNeutralizerEnv

epsilon = 1e-6
LOG_STD_MAX = 2
LOG_STD_MIN = -20


# --- 1. 定义 Actor 和 Critic 网络 ---
# Actor-Critic 网络是 PPO 的基础。Actor 负责决定动作，Critic 负责评估状态的价值。


class BaseFeatureExtractor(nn.Module):
    def __init__(self, one_hot_class_num=4, conv_out_feature_dim=508, feature_dim=160001):
        super(BaseFeatureExtractor, self).__init__()
        self.conv_out_feature_dim = conv_out_feature_dim
        self.one_hot_class_num = one_hot_class_num

        self.model = nn.Sequential(
            # 输入: (B, 1, 16001)
            nn.Conv1d(in_channels=1, out_channels=16, kernel_size=11,
                      stride=4, padding=5),  #
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            nn.Conv1d(in_channels=16, out_channels=32, kernel_size=7,
                      stride=3, padding=3),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            nn.Conv1d(in_channels=32, out_channels=64, kernel_size=5,
                      stride=2, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            nn.Conv1d(in_channels=64, out_channels=128, kernel_size=3,
                      stride=1, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2),

            # --- 最终层 ---
            nn.Flatten(),

            # 线性投射层
            nn.Linear(512, self.conv_out_feature_dim),
            nn.ReLU()
        )

    def forward(self, state_batch):
        # state_batch 是一个 (批量大小, 2049) 的张量

        # 提取离散类型 (第一列)
        discrete_type = state_batch[:, 0].long()
        # 提取连续信号 (从第二列到末尾)
        continuous_signal = state_batch[:, 1:]

        # --- 处理离散部分 ---
        # 注意：这里直接操作张量，不要用 torch.tensor() 重建
        one_hot_label = torch.nn.functional.one_hot(
            discrete_type, num_classes=self.one_hot_class_num
        ).float()  # 确保是 float 类型

        # --- 处理连续部分 ---
        # Conv1d 需要 (批量大小, 通道数, 长度) 的输入
        # 我们需要给它增加一个通道维度
        signal_with_channel = continuous_signal.unsqueeze(1)
        conv_features = self.model(signal_with_channel)

        # --- 融合特征 ---
        return torch.cat((one_hot_label, conv_features), dim=1)


class Actor(nn.Module):
    """
    策略网络 (Actor)
    - 对于连续动作空间，输出高斯分布的均值和标准差。
    - 对于离散动作空间，输出每个动作的概率。
    """

    def __init__(self, conv_out_feature_dim, continue_action_dim=2, dicrete_action_dim=7):
        super(Actor, self).__init__()

        self.continue_action_dim = continue_action_dim
        self.dicrete_action_dim = dicrete_action_dim

        self.model = nn.Sequential(nn.Linear(conv_out_feature_dim, 64),
                                   nn.Tanh(),
                                   nn.Linear(64, 64),
                                   nn.Tanh()
                                   )

        self.continue_mean_head = nn.Linear(64, continue_action_dim)
        self.continue_log_std_head = nn.Linear(64, continue_action_dim)

        self.dicrete_action_head = nn.Linear(64, dicrete_action_dim)

    def forward(self, feature):
        """
        前向传播
        输入: state
        输出: 一个动作的概率分布 (torch.distributions)
        """
        x = self.model(feature)

        mean = torch.tanh(self.continue_mean_head(x))

        log_std = self.continue_log_std_head(x)
        log_std = torch.clamp(log_std, min=LOG_STD_MIN, max=LOG_STD_MAX)
        std = torch.exp(log_std)

        continue_dist = MultivariateNormal(mean, torch.diag_embed(std))

        dicrete_action_logits = self.dicrete_action_head(x)
        dicrete_dist = Categorical(logits=dicrete_action_logits)

        return dicrete_dist, continue_dist

    def evaluate_action(self, feature, dicrete_action, continue_action):
        dicrete_dist, continue_dist = self.forward(feature)
        # 1. "反向"变换：将 [0, 1] 的动作还原到 (-1, 1)，再用 atanh 还原到 pre_squash 空间
        #    为了数值稳定性，在 atanh 前裁剪一下
        action_neg1_1 = (continue_action * 2) - 1
        pre_squash_action = torch.atanh(torch.clamp(
            action_neg1_1, -1 + epsilon, 1 - epsilon))
        # 2. 计算 pre_squash 动作的对数概率
        base_log_prob = continue_dist.log_prob(pre_squash_action)
        # 3. 根据变量替换公式，计算修正项并修正对数概率
        #    log_prob = log_prob_base - log(1 - tanh(pre_squash_action)^2)
        log_prob_correction = torch.log(1 - action_neg1_1.pow(2) + epsilon)
        continue_action_logprobs = base_log_prob - \
                                   log_prob_correction.sum(axis=-1)

        continue_dist_entropy = continue_dist.entropy()

        dicrete_action_logprobs = dicrete_dist.log_prob(dicrete_action)
        dicrete_action_entropy = dicrete_dist.entropy()

        action_action_logprobs = continue_action_logprobs + dicrete_action_logprobs
        action_entropy = continue_dist_entropy + dicrete_action_entropy

        return action_action_logprobs, action_entropy


class Critic(nn.Module):
    """
    价值网络 (Critic)
    - 评估输入状态的价值 (V-value)
    """

    def __init__(self, conv_out_feature_dim):
        super(Critic, self).__init__()

        self.model = nn.Sequential(nn.Linear(conv_out_feature_dim, 64),
                                   nn.Tanh(),
                                   nn.Linear(64, 64),
                                   nn.Tanh(),
                                   nn.Linear(64, 1)
                                   )

    def forward(self, feature):
        """
        前向传播
        输入: feature
        输出: 该 feature 的价值 (一个标量)
        """

        value = self.model(feature)

        return value


# --- 2. 定义经验存储 ---
# PPO 是 On-Policy 算法, 它收集一个完整的轨迹(rollout), 然后用这些数据进行更新, 之后就丢弃这些数据。

class RolloutBuffer:
    def __init__(self):
        # 初始化列表来存储一个轨迹中的所有信息
        self.actions = []
        self.states = []
        self.logprobs = []  # 动作的对数概率
        self.rewards = []
        self.dones = []  # 轨迹是否结束
        self.values = []  # 每个状态的 V-value

    def clear(self):
        # 在每次更新后，清空所有存储
        del self.actions[:]
        del self.states[:]
        del self.logprobs[:]
        del self.rewards[:]
        del self.dones[:]
        del self.values[:]

    def store(self, state, action, logprob, reward, done, value):
        """
        将一步的经验数据存入缓冲区
        """
        self.states.append(state)
        self.actions.append(action)
        self.logprobs.append(logprob)
        self.rewards.append(reward)
        self.dones.append(done)
        self.values.append(value)

    def get_data(self):
        """
        在轨迹结束后，准备用于训练的数据。
        将列表转换为 torch.Tensor。
        """

        states = torch.tensor(np.array(self.states), dtype=torch.float32)
        actions = torch.tensor(np.array(self.actions), dtype=torch.float32)
        logprobs = torch.tensor(np.array(self.logprobs), dtype=torch.float32)
        rewards = torch.tensor(np.array(self.rewards), dtype=torch.float32)
        dones = torch.tensor(np.array(self.dones), dtype=torch.float32)
        values = torch.tensor(np.array(self.values), dtype=torch.float32)

        return states, actions, logprobs, rewards, dones, values


# --- 3. 定义 PPO 主类 ---

class PPO:
    def __init__(self, conv_feature_dim, onehot_freature_dim, continue_action_dim, dicrete_action_dim,
                 lr_feature_extractor, lr_actor, lr_critic, gamma, K_epochs, eps_clip, device, minibatch_size,
                 gae_lambda=0.95):
        # --- 初始化超参数 ---
        self.device = device
        self.gamma = gamma  # 折扣因子
        self.K_epochs = K_epochs  # 更新模型的轮数
        self.gae_lambda = gae_lambda
        self.eps_clip = eps_clip  # PPO裁剪范围
        self.minibatch_size = minibatch_size
        self.conv_out_feature_dim = 508

        self.actor_loss = 0
        self.critic_loss = 0

        # --- 初始化 Actor-Critic 特征提取网络 ---
        self.actor = Actor(self.conv_out_feature_dim + onehot_freature_dim,
                           continue_action_dim, dicrete_action_dim).to(device)
        self.critic = Critic(self.conv_out_feature_dim +
                             onehot_freature_dim).to(device)
        self.feature_extractor = BaseFeatureExtractor(
            onehot_freature_dim, self.conv_out_feature_dim).to(device)

        # --- 初始化优化器 ---
        self.feature_extractor_optimizer = torch.optim.Adam(
            self.feature_extractor.parameters(), lr=lr_feature_extractor)
        self.actor_optimizer = torch.optim.Adam(
            self.actor.parameters(), lr=lr_actor)
        self.critic_optimizer = torch.optim.Adam(
            self.critic.parameters(), lr=lr_critic)

        # --- 初始化经验缓冲区 ---
        self.buffer = RolloutBuffer()

    def select_action(self, state_tensor):
        """
        根据当前状态选择一个动作
        输入: state (numpy array)
        输出: action, action_logprob, state_value
        """
        with torch.no_grad():
            # print(f"DEBUG: state_tensor shape is {state_tensor.shape}")
            feature_tensor = self.feature_extractor(state_tensor)

            dicrete_dist, continue_dist = self.actor(feature_tensor)
            state_value = self.critic(feature_tensor)
            # 1. 从基础高斯分布中采样 (pre-squash)
            pre_squash_continue_action = continue_dist.sample()
            # 2. 使用 tanh 压缩，并缩放到 [0, 1]
            squashed_continue_action = torch.tanh(pre_squash_continue_action)
            final_continue_action = 0.5 * (squashed_continue_action + 1)

            dicrete_action = dicrete_dist.sample().unsqueeze(0)
            # --- 合并动作与对数概率 ---
            action = torch.cat((dicrete_action, final_continue_action), dim=1)
            # 3. 计算修正后的对数概率

            base_log_prob = continue_dist.log_prob(pre_squash_continue_action)
            log_prob_correction = torch.log(
                1 - squashed_continue_action.pow(2) + epsilon)
            continue_action_logprob = base_log_prob - \
                                      log_prob_correction.sum(axis=-1)

            dicrete_action_logprob = dicrete_dist.log_prob(dicrete_action)
            action_logprob = continue_action_logprob + dicrete_action_logprob

        return action.cpu().squeeze(0).numpy(), action_logprob.cpu().item(), state_value.squeeze(0).cpu().item()


    def update(self, writer):
        """
        更新策略网络和价值网络
        """
        old_states, old_actions, old_logprobs, old_rewards, old_dones, old_values = self.buffer.get_data()
        old_states = old_states.to(self.device)
        old_actions = old_actions.to(self.device)
        old_logprobs = old_logprobs.to(self.device)
        old_rewards = old_rewards.to(self.device)
        old_dones = old_dones.to(self.device)
        old_values = old_values.to(self.device)

        advantages = torch.zeros(old_states.shape[0], device=self.device)
        last_advantage = 0
        for t in reversed(range(old_actions.shape[0])):
            if t == old_actions.shape[0] - 1:
                next_non_terminal = 1.0 - old_dones[t]
                next_value = 0
            else:
                next_non_terminal = 1.0 - old_dones[t]
                next_value = old_values[t + 1]

            delta = old_rewards[t] + self.gamma * \
                    next_value * next_non_terminal - old_values[t]

            last_advantage = delta + self.gamma * \
                             self.gae_lambda * next_non_terminal * last_advantage
            advantages[t] = last_advantage

        returns = advantages + old_values

        advantages = (advantages - advantages.mean()) / \
                     (advantages.std() + 1e-8)
        # --- 3. 在 K 个 epochs 内，使用 mini-batch 更新网络 ---
        batch_size = old_states.shape[0]
        for i in range(self.K_epochs):

            # 创建一个随机的索引排列
            indices = torch.randperm(batch_size)

            # 定义 mini-batch 大小
            minibatch_size = self.minibatch_size  # 这是一个常见的超参数

            # 遍历所有 mini-batch
            for start in range(0, batch_size, minibatch_size):
                end = start + minibatch_size
                minibatch_indices = indices[start:end]

                # 从原始数据中选取 mini-batch
                minibatch_states = old_states[minibatch_indices]
                minibatch_actions = old_actions[minibatch_indices]
                minibatch_logprobs = old_logprobs[minibatch_indices]
                minibatch_advantages = advantages[minibatch_indices]
                minibatch_returns = returns[minibatch_indices]

                minibatch_feature = self.feature_extractor(minibatch_states)

                new_logprobs, dist_entropy = self.actor.evaluate_action(
                    minibatch_feature, minibatch_actions[:, 0], minibatch_actions[:, 1:])

                new_value = self.critic(minibatch_feature)

                ratios = torch.exp(new_logprobs - minibatch_logprobs)

                surr1 = ratios * minibatch_advantages
                surr2 = torch.clamp(ratios, 1 - self.eps_clip,
                                    1 + self.eps_clip) * minibatch_advantages

                actor_loss = -torch.min(surr1, surr2).mean() - \
                             0.01 * dist_entropy.mean()

                critic_loss = nn.MSELoss()(new_value, minibatch_returns.unsqueeze(1))

                self.feature_extractor_optimizer.zero_grad()
                self.actor.zero_grad()
                self.critic.zero_grad()

                total_loss = actor_loss + critic_loss
                total_loss.backward()

                self.feature_extractor_optimizer.step()
                self.actor_optimizer.step()
                self.critic_optimizer.step()

            # 在第一个 epoch 记录损失
            if i == 0:
                self.actor_loss = actor_loss.item()
                self.critic_loss = critic_loss.item()
            # --- 8. 清空缓冲区，为下一次轨迹收集做准备 ---
        self.buffer.clear()


    def save_model(self, filepath):
        """
        保存模型权重
        """
        torch.save({
            'actor_state_dict': self.actor.state_dict(),
            'critic_state_dict': self.critic.state_dict(),
            'feature_extrator_dict': self.feature_extractor.state_dict(),
            'actor_optimizer_state_dict': self.actor_optimizer.state_dict(),
            'critic_optimizer_state_dict': self.critic_optimizer.state_dict(),
            'feature_extractor_optimizer_dict': self.feature_extractor_optimizer.state_dict()
        }, filepath)
        print(f"模型已保存到 {filepath}")


    def load_model(self, filepath):
        """
        加载模型权重
        """
        checkpoint = torch.load(filepath)
        self.actor.load_state_dict(checkpoint['actor_state_dict'])
        self.critic.load_state_dict(checkpoint['critic_state_dict'])
        self.feature_extractor.load_state_dict(
            checkpoint['feature_extrator_dict'])
        self.actor_optimizer.load_state_dict(
            checkpoint['actor_optimizer_state_dict'])
        self.critic_optimizer.load_state_dict(
            checkpoint['critic_optimizer_state_dict'])
        self.feature_extractor_optimizer.load_state_dict(
            checkpoint['feature_extractor_optimizer_dict'])

        print(f"模型已从 {filepath} 加载")


    def predict(self, obs):
        feature = self.feature_extractor(torch.tensor(
            obs, dtype=torch.float32).to(self.device))

        dicrete_dist, continue_dist = self.actor(feature)

        continue_action = continue_dist.sample()
        dicrete_action = dicrete_dist.sample()

        action = torch.cat((dicrete_action, continue_action), dim=1)
        return action

