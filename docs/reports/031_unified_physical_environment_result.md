# Task 031：统一 Phase 1 物理环境与配置来源

## 1. 任务结论

Task 031 已完成。仓库现在有唯一的 Phase 1 雷达物理配置源：`configs/phase1_radar.py`。

已实现：

- 统一框架、JammerLoader、RL 配置和相关测试脚本使用同一组物理参数；
- `N=5000` 从 `round(Tr*Fs)` 派生，不再为 `state_len=1024` 修改 `Pw/Fs`；
- RL 使用完整 `(1,5000)` 接收信号，再通过独立 `preprocess_raw_iq` 变换为 `(2,1024)` state；
- `target_delay_s`、目标脉冲起点和 `target_idx` 的坐标定义已明确；
- 未修改算法、JSR 标定、reward、PPO、动作空间、多脉冲环境或训练流程。

Task 032 及后续任务未开始。

## 2. 修改前问题

Task 030 确认 RL `Config` 使用 `Pw=10us, Fs=25MHz`，统一框架使用 `Pw=20us, Fs=50MHz`。RL 环境通过 `N=int(Tr*cfg.Fs)` 生成不同长度的物理信号，因此 `state_len=1024` 间接改变了物理问题。

此外，`RadarEnvironment.DEFAULT_RADAR_PARAMS`、`JammerLoader.DEFAULT_RADAR_PARAMS` 和多个测试脚本各自维护硬编码参数，存在来源分裂。

## 3. 唯一物理配置

权威配置文件：`configs/phase1_radar.py`

```python
{
    'C': 3e8,
    'f0': 15e6,
    'Bw': 5e6,
    'Pw': 20e-6,
    'Fs': 50e6,
    'Tr': 100e-6,
    'M': 1,
    'target_dist': 6000.0,
    'target_amp': 1.0,
    'noise_var': 0.1,
    'JSR_dB': 10,
}
```

通过 `get_phase1_radar_params()` 返回深拷贝，运行时覆盖不会修改权威常量。通过 `get_phase1_jammer_params()` 集中完成 `Pw -> T`、`Bw -> B` 字段转换。

## 4. 派生参数公式

```text
N                 = round(Tr * Fs) = 5000
pulse_samples     = round(Pw * Fs) = 1000
target_delay_s    = 2 * target_dist / C = 40 us
target_start_idx  = round(Pw * Fs) = 1000
target_idx        = target_start_idx + round(0.5 * Pw * Fs) = 1500
```

### target_idx 最终定义

干扰器生成的观测数组 `J_compound` 的时间轴从绝对目标延迟 `target_delay_s=2R/C` 开始，数组索引 0 不是绝对时间 0。目标回波位于相对时间 `[Pw, 2Pw)`，因此目标中心在数组内为 `1.5*Pw`，即 1500 点。

因此：

- `target_delay_s` 表示物理绝对往返延迟；
- `target_idx` 表示 delay-relative 接收数组中的目标中心；
- 不把 `target_delay_s*Fs` 再加到 `target_idx`，避免重复计算绝对延迟。

`generate_without_jammer()` 已同步使用 `target_start_idx=1000`，与 `generate_with_jammer()` 的坐标一致。该修改解决了无干扰路径原先使用绝对 `range_bin=2000` 而 jammer 路径使用相对坐标的问题。

## 5. 修改文件列表

### 新增

- `configs/__init__.py`
- `configs/phase1_radar.py`
- `validate_phase1_environment.py`
- `docs/tasks/031_unify_physical_environment.md`
- `docs/reports/031_unified_physical_environment_result.md`

### 修改

- `unified_framework.py`：统一 `RadarEnvironment` 和 `JammerLoader` 默认值；统一派生参数；修正无干扰路径坐标。
- `rl_framework/config.py`：物理参数引用 Phase 1 配置，保留 `state_len=1024`。
- `rl_framework/environment.py`：完整物理参数通过配置源初始化，state 继续由独立预处理函数生成。
- `validate_no_jammer.py`、`validate_algorithms.py`：读取集中配置。
- `run_high_jsr_eval.py`、`test_sinr_by_state.py`：读取集中配置，保留各自 JSR/实验覆盖。
- `AGENTS.md`、`CLAUDE.md`、`README.md`、`jamming/__init__.py`：修正示例中的 `T=24us` 为 `T=20us`。
- `docs/reports/phase1_progress.md`：记录 Task 031 状态。

### 明确未修改

- `anti_jamming/` 算法实现，包括 FrFT、FDC、WLN、adapt_filter、qpzh、FSTP、Frequency Agile、Wave Agile；
- `jamming/` 干扰模型内部实现和 JSR 标定；
- PPO、Actor/Critic、reward、动作空间、训练流程；
- `SliceCombineJam` 构造函数接口；该问题保留为既有阻塞项。

## 6. RL 完整信号与 state transform

RL `AntiJamEnv` 现在通过 `get_phase1_radar_params()` 创建完整雷达环境：

```text
Srt_matrix: (1, 5000) complex
             |
             v
preprocess_raw_iq(rx_signal, state_len=1024)
             |
             v
state['signal']: (2, 1024) float32
```

`preprocess_raw_iq` 只接收完整 IQ 和目标长度，不读取 `target_idx`、`jam_info`、真实目标位置或 jammer 类型。保留了现有网络接口和 `state_len`，没有修改网络结构。

## 7. 搜索到的硬编码位置

搜索原始参数关键词的完整结果保存在：

```text
results/phase1/environment/hardcoded_parameter_search.txt
```

处理情况：

| 位置 | 处理 |
|---|---|
| `unified_framework.py` 默认参数 | 已改为配置源 |
| `unified_framework.py` CLI 示例参数 | 已改为配置源 |
| `rl_framework/config.py` 的 `Pw/Fs` | 已改为配置源 |
| `rl_framework/environment.py` 的 `N` | 已改为派生参数 |
| `validate_no_jammer.py` | 已改为配置源 |
| `validate_algorithms.py` | 已改为配置源 |
| `run_high_jsr_eval.py` | 已改为配置源，JSR 仍由实验参数覆盖 |
| `test_sinr_by_state.py` | 已改为配置源 |
| `anti_jamming/adapters.py` fallback 默认值 | 未改；属于算法适配器内部兼容 fallback，未改变本任务的环境配置来源 |
| 各 `jamming/*.py` 构造函数默认 `T=24us` | 未改；JammerLoader 会显式传入 `T=20us`，修改内部默认属于干扰模型范围 |
| `anti_jamming/qpzh.py` 的 SliceCombine 默认参数 | 未改；接口/模型问题留给后续任务 |
| `rl_framework/总结报告.md` 历史示例 | 未改，保留历史记录 |

## 8. 实际执行命令

```bash
./.venv/bin/python -m py_compile configs/phase1_radar.py unified_framework.py rl_framework/config.py rl_framework/environment.py validate_phase1_environment.py validate_no_jammer.py validate_algorithms.py run_high_jsr_eval.py test_sinr_by_state.py
./.venv/bin/python validate_phase1_environment.py
./.venv/bin/python validate_no_jammer.py
./.venv/bin/python validate_algorithms.py
./.venv/bin/python run_correctness_tests.py
```

原始输出：

```text
results/phase1/environment/config_snapshot.txt
results/phase1/environment/config_consistency_test.txt
results/phase1/environment/validate_no_jammer.stdout.txt
results/phase1/environment/validate_algorithms.stdout.txt
results/phase1/environment/run_correctness_tests.stdout.txt
results/phase1/environment/rl_environment_smoke_test.txt
results/phase1/environment/git_diff_stat.txt
results/phase1/environment/hardcoded_parameter_search.txt
```

## 9. 测试结果

- 配置一致性测试：PASS；验证统一配置、派生参数、`(1,5000)`、`(2,1024)`、确定性和 state transform 无 oracle。
- RL environment smoke test：PASS；完整物理信号 `(1,5000)`，state `(2,1024)`。
- `validate_no_jammer.py`：9/9 算法 PASS。
- `validate_algorithms.py`：10/10 配对 PASS。
- `run_correctness_tests.py`：进程退出码 0，内部仍为 5 通过、1 警告、4 失败，与 Task 030 基线相同。

## 10. 回归差异

新增配置一致性和 RL smoke test 均通过。统一配置后，RL 的 `Pw/Fs/N` 已从 `10us/25MHz/2500` 变为 `20us/50MHz/5000`，这是本任务预期差异。

既有 correctness 失败仍为：SliceCombineJam loader 的 `Fs` 参数异常三项，以及 FrFT 缺失 `test_frft_filter` 一项；既有 Wave Agile 警告仍存在。没有新增与配置统一相关的异常。

## 11. 未解决问题

- `SliceCombineJam` 标准 loader 接口仍不兼容 `Fs`，不在本任务修改范围内。
- 各 jammer 类自身默认参数仍保留历史 `T=24us`，但标准 Loader 路径显式覆盖为 `T=20us`。
- state transform 当前仍是中心截窗/补零，不代表最终最优表示；本任务只要求解耦和可复现。
- RL jammer one-hot 仍作为状态字段存在；本任务只保证 IQ 固定长度 transform 不读取 jammer 真值。
- 当前仍为 `M=1`，不评价多脉冲处理。

## 12. 验收判断

Task 031 的 10 项验收条件满足。没有修改算法、JSR、reward、PPO 或训练流程；测试原始输出已保存；当前停止，不执行 Task 032。

## 13. Git

分支：`algorithm_design_0711`

提交：`da9deb4 phase1-031-unify-physical-environment`

提交前已执行 `git diff --check`、`git diff --stat` 和相关文件 diff 检查。
