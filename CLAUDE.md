# CLAUDE.md — Agent 工作规则

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
jammer = JammerClass(C=3e8, f0=15e6, T=24e-6, Tr=100e-6, B=5e6)
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
