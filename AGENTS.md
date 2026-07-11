# AGENTS.md — Agent 工作规则

## ChatGPT ↔ Codex 协作闭环

本项目采用“ChatGPT 负责设计与审查，Codex 负责代码执行”的协作方式。

### 角色分工

- ChatGPT：梳理项目框架和数据流，讨论算法与实验方案，整理任务，审查代码修改、Git diff 和测试结果，并根据审查结果生成下一轮任务。
- Codex：阅读本地代码，追踪真实调用链和 tensor shape，根据任务文件修改代码，运行测试和最小实验，生成执行报告并提交 Git diff/commit。

### 共享文件

```text
AGENTS.md                 # 长期协作与项目规则
ROADMAP.md                # 项目状态、基线与任务优先级
docs/tasks/XXX_*.md       # ChatGPT -> Codex 的结构化任务
docs/reports/XXX_*.md     # Codex -> ChatGPT 的执行报告
```

### 每次任务启动前

1. 阅读 `AGENTS.md`。
2. 阅读 `ROADMAP.md`。
3. 阅读指定的 `docs/tasks/XXX_*.md`。
4. 检查任务涉及的代码、调用链和数据 shape。
5. 设计未确认前，不直接修改代码；若任务文档与当前代码不一致，先报告差异，不自行猜测。

### 任务文件最低要求

每个任务必须明确：目标、必读文件、当前已知事实、修改要求、禁止事项、验收标准和测试命令。

### 实现原则

- 遵循最小修改原则，保持现有接口不变。
- 不做与任务无关的重构，不同时修改多个独立变量。
- 修改算法前确认 tensor shape、数据流、mask、时间对齐和参数传递。
- 必要时增加 assertion、日志或单元测试。
- 对无法确认的内容明确标记，不自行假设。

### 完成任务后的固定交付

每个任务完成后必须：

1. 生成 `docs/reports/XXX_*.md`，至少包含任务结论、实际修改、文件列表、关键逻辑、设计对应关系、测试命令及结果、未解决问题、潜在风险、Git 分支和 commit ID。
2. 提供 `git diff --stat` 和 `git diff`；diff 较大时至少提供任务相关目录的 diff。
3. 记录测试结果和实验输出路径。

### 审查门禁

Codex 修改并测试后不默认视为任务结束。流程为：

```text
Codex 修改并测试 -> 生成 result 报告和 Git diff -> ChatGPT 审查
    -> 通过：进入下一任务
    -> 不通过：生成修复任务
```

在 ChatGPT 审查通过前：

- 不合并到主分支。
- 不开始长时间训练。
- 不继续叠加新的算法改动。

### Git 约定

- 每个任务优先使用独立分支：`task/XXX-task-name`。
- 每个任务尽量对应一个清晰 commit。
- 提交前检查无关修改、测试记录和 result 报告；commit message 应包含任务编号和修改说明。

## 启动流程

1. 读 `ROADMAP.md` 获取项目状态（基线、RL进展、架构事实、任务优先级）
2. 处理具体任务时读 `docs/tasks/XXX.md`

## 项目简介

雷达抗干扰仿真 + RL 框架。10种干扰、8种抗干扰算法、PPO 智能体。

## 编码规范

- Python，依赖：numpy / scipy / torch / matplotlib
- 运行环境：`.venv/bin/python`
- 保持现有接口不变
- 修改算法前先跑测试验证不破坏已有配对

## 关键接口

```python
# 干扰
jammer = JammerClass(C=3e8, f0=15e6, T=20e-6, Tr=100e-6, B=5e6)
composite_signal, range_axis, info_dict = jammer.generate(R_target, JSR_dB=10, noise_var=0.1)

# 抗干扰
processed_signal, processed_template = antijam_func(radar_par, par1=0.3, par2=6)

# RL 训练
.venv/bin/python -m rl_framework.train --agent_type cppo --episodes 300
```

## 测试命令

```bash
.venv/bin/python validate_algorithms.py    # 10组配对验证
.venv/bin/python run_correctness_tests.py  # 正确性测试
```

## 文件导航

| 用途 | 路径 |
|------|------|
| 项目状态与任务 | `ROADMAP.md` |
| 任务详情 | `docs/tasks/` |
| 算法原理 | `algorithm_docs/` |
| 人类阅读入口 | `README.md` |

## 关键参数

| 参数 | 默认值 |
|------|--------|
| f0 | 15 MHz |
| Bw | 5 MHz |
| Pw | 20 μs |
| Fs | 50 MHz |
| JSR_dB | 10 dB |
| target_dist | 6000 m |
