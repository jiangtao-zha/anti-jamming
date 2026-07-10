# 019: 基于新基线重新训练 RL 模型

> 优先级: **P0**
> 状态: **待执行**
> 创建: 2026-07-07
> 关联: `ROADMAP.md` P0、`docs/tasks/018-high-jsr-algorithm-eval.md`

## 背景

旧 CPPO/stdPPO 训练结果基于旧 `target_idx=2500`。最新基线已修正为 `target_idx=1500`，同时 `JammerLoader.T` 与 `Pw` 对齐到 20us，JSR=10dB 下匹配滤波后 SINR 已显著提高。因此旧训练曲线和 CPPO/stdPPO 差距不能作为当前结论。

另一个执行前发现：`rl_framework/config.py` 当前默认仍是 `Pw=10us, Fs=25MHz`，而 roadmap 最新基线是 `Pw=20us, Fs=50MHz`。重训必须显式同步物理基线，否则会得到第三套不可比较的结果。

## 目标

在最新物理基线下，先完成第一版低成本重训，得到新 baseline：

- CPPO: CNN IQ 特征 + jammer one-hot
- stdPPO: 仅 jammer one-hot
- JSR: `20dB`
- seed: `42`
- 训练长度: `300 episodes × 8 steps/episode`

第一版目标不是最终统计显著结论，而是确认在修正后的目标索引和高 JSR 条件下，CPPO 与 stdPPO 是否仍表现出可观察差异。

## 训练配置

物理基线：

- `f0=15MHz`
- `Bw=5MHz`
- `Pw=20us`
- `Fs=50MHz`
- `Tr=100us`
- `N=5000`
- `target_dist=6000m`
- `target_idx=1500`
- `JSR_dB=20`
- `noise_var=0.1`

PPO 配置沿用现有默认：

- `episodes=300`
- `steps_per_episode=8`
- `lr=3e-4`
- `gamma=0.99`
- `gae_lambda=0.95`
- `eps_clip=0.2`
- `K_epochs=10`

## 执行前改动

为 `rl_framework/train.py` 增加最小 CLI 覆盖：

- `--jsr`
- `--pw_us`
- `--fs_mhz`

为 `run_repeated_experiments.py` 增加参数透传：

- `--repeats`
- `--episodes`
- `--jsr`
- `--pw_us`
- `--fs_mhz`
- `--save_dir`

默认输出目录使用独立路径，避免覆盖旧 checkpoint：

```bash
experiment_results/rl_retrain_20260707_jsr20/
```

建议正式命令：

```bash
.venv/bin/python run_repeated_experiments.py \
  --repeats 1 \
  --episodes 300 \
  --jsr 20 \
  --pw_us 20 \
  --fs_mhz 50 \
  --save_dir experiment_results/rl_retrain_20260707_jsr20
```

## 验收标准

冒烟测试：

- CPPO 和 stdPPO 各能以 `episodes=2` 完成
- 输出目录中能生成模型、训练历史和曲线图
- 日志中确认 `JSR=20dB`, `Pw=20us`, `Fs=50MHz`

正式训练：

- CPPO 和 stdPPO 均完成 300 episodes
- 每个 agent 生成：
  - `training_history_<agent>.npz`
  - `ppo_final.pt`
  - `ppo_best.pt` 或保存间隔模型
  - 训练曲线图
- 汇总最后 10/20 轮：
  - reward
  - SINR improvement
  - detect rate
  - CPPO - stdPPO 差值

## 风险与边界

- 本任务暂不修 P2 的 RL 动作空间和 `decode_action` 问题。
- 如果 P2 问题导致训练结果明显不可解释，应记录为阻塞风险，并暂停正式结论。
- 单 seed 结果只作为第一版新 baseline，不作为最终统计显著结论。
- 若 20dB 下检测率长期饱和或完全失败，应结合 018 的高 JSR 评测结果重新选择训练 JSR。

