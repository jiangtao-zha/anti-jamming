# Task 031：统一 Phase 1 物理环境与配置来源

## 目标

建立唯一的 Phase 1 单脉冲雷达物理配置来源，统一统一仿真框架、JammerLoader、测试脚本和 RL 环境的物理参数；保持完整物理信号长度，并将固定长度 RL state 构造与物理信号生成解耦。

## 统一基线

```text
f0=15MHz, Bw=5MHz, Pw=20us, Fs=50MHz,
Tr=100us, M=1, target_dist=6000m,
target_amp=1.0, noise_var=0.1, JSR_dB=10
```

`N=round(Tr*Fs)=5000`，`state_len=1024` 仅用于 RL 输入变换。

## 允许范围

- 新增集中配置模块；
- 修改 `unified_framework.py`、`rl_framework/config.py`、`rl_framework/environment.py`；
- 修改 Loader 默认参数来源和相关测试脚本；
- 新增配置一致性、shape、确定性和 RL smoke test。

## 禁止范围

不修改抗干扰算法、干扰功率/JSR、reward、PPO、Actor/Critic、动作空间、多脉冲、RGPO、Frequency Agile、Wave Agile 或 FSTP；不训练 RL，不执行 Task 032。

## target_idx 定义

干扰器输出数组的时间原点是绝对目标延迟 `target_delay=2*target_dist/C`。目标信号位于该数组原点之后的 `[Pw,2Pw)`，因此数组内目标中心为 `round(1.5*Pw*Fs)=1500`。绝对 `target_delay` 与数组内 `target_idx` 分开保存，禁止把绝对延迟再次加到 delay-relative 数组索引。

## 验收

验证统一配置、完整接收 shape `(1,5000)`、RL state shape `(2,1024)`、确定性、无 oracle state transform，并回归运行 `validate_no_jammer.py`、`validate_algorithms.py`、`run_correctness_tests.py` 和配置一致性测试。保存原始输出到 `results/phase1/environment/`，提交 `phase1-031-unify-physical-environment`。
