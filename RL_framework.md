```markdown
# 任务：添加训练曲线对比绘图脚本

## 背景
当前工程 `rl_framework/` 已包含：
- `train.py`：使用 PPO 算法训练智能体，记录日志到 TensorBoard（`runs/` 目录）。
- `run_comparison.py`：测试训练好的模型并生成不同干扰下的 SINR 改善柱状图。
- `config.py`、`ppo_agent.py`、`agent_factory.py` 等：支持 CPPO、Standard PPO、Expert 三种策略。

你希望在得到模型之前，能够直观对比 **训练过程中不同算法的学习曲线**（例如平均回合奖励、SINR 改善等），以便分析收敛速度和最终性能。现有 `run_comparison.py` 只针对训练完毕的模型做最终测试，缺少“训练过程对比图”。

## 目标
新增一个脚本或扩展原有功能，实现：
1. **在训练期间记录关键指标**：除了 TensorBoard 外，每个回合结束时将 `平均奖励` 或 `平均 SINR 改善` 以 `.csv` 或 `.npz` 形式保存，便于离线绘图。
2. **创建 `plot_training_curves.py`**：能够加载多个训练日志（例如 CPPO 和 Standard PPO 的日志文件），绘制训练曲线对比图，至少包含：
   - X 轴：训练回合数（或环境步数）
   - Y 轴：平滑后的平均回合奖励（或平均 SINR 改善）
   - 两条曲线：CPPO、Standard PPO（如果用 Expert 则其奖励为固定值，可画水平线）
3. **图表样式**：坐标轴标签、图例、网格、标题（例如“PPO vs CPPO 训练曲线”），保存为 PNG 文件。
4. **集成到现有工作流**：可以在训练结束后直接调用绘图，或通过单独的 CLI 命令运行。

## 具体要求

### 1. 修改 `train.py`（若必要）
如果当前训练脚本只写入 TensorBoard 而没有保存结构化数据，请添加：
- 在每个回合结束后，将 `episode_reward` 或 `avg_sinr_improvement` 等指标追加到一个列表，并在训练完成（或中断）时保存这些数据到 `.npz` 或 `.csv` 文件，文件名包含 `agent_type` 和时间戳，例如 `training_history_cppo.npz`。
- 保存的数据结构应包含：`rewards`（每个回合的平均奖励）、`sinr_improvements`（每个回合的平均 SINR 改善）、`actor_losses` 等。

### 2. 新建 `rl_framework/plot_training_curves.py`
该脚本应：
- 接受命令行参数：
  - `--log_files`：多个日志文件路径（`.npz` 或 `.csv`），每个文件对应一个训练 run。
  - `--labels`：对应图例标签，默认从文件名推断。
  - `--metric`：要绘制的指标名称（`reward` 或 `sinr_improvement`），默认 `reward`。
  - `--smooth`：平滑窗口大小（移动平均），默认 10。
  - `--output`：输出图片路径，默认 `training_curves.png`。
  - `--title`：图表标题。
- 功能：
  - 加载每个日志文件，提取指定指标的原始数据。
  - 对原始数据进行滑动平均平滑。
  - 使用 matplotlib 绘制曲线对比图，不同策略用不同颜色。
  - 若提供了 `--expert_value` 参数，可额外绘制一条水平虚线表示 Expert 策略的固定性能。
  - 显示网格、图例，并保存图片。

### 3. 更新 `README.md`（简要）
在文档中说明如何运行训练并生成对比曲线，例如：
```bash
python train.py --agent_type cppo --save_history
python train.py --agent_type std_ppo --save_history
python plot_training_curves.py --log_files training_history_cppo.npz training_history_std_ppo.npz --labels CPPO "Standard PPO"
```

### 4. 边界情况处理
- 如果某个日志文件缺失，给出警告并跳过。
- 确保平滑窗口不超过数据长度。
- 支持 `.csv` 格式（用 pandas 或纯 numpy 读取，第一列为回合，第二列为指标值）。

## 交付物
- 修改后的 `train.py`（如果原版未保存历史数据）。
- 新增 `rl_framework/plot_training_curves.py`。
- 更新 `rl_framework/README.md` 相关部分。
- 所有代码应有适当注释。

## 验证
运行下列命令，应生成对比图：
```bash
# 假设已有两个训练历史文件
python plot_training_curves.py --log_files hist_cppo.npz hist_std.npz --metric reward --smooth 10 --title "Training Curve: Reward"
```

请严格按照上述要求实现。
```