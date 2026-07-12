# Task 034：FDC 与 AMNoiseGaiJam 专用抗干扰校准

## 1. 当前 FDC 原理分析

初始审查见 `docs/reports/034_fdc_initial_analysis.md`。统一评测实际调用 `anti_jamming/adapters.py` 的 `fdc_adapter`，而不是旧 `FrequencyDomainCanceller.cancel()` 类。Current FDC 已使用下变频、pseudo-covariance 和共轭对称分量，但其对消模板直接由完整 received signal 构造，没有显式的独立 `J_hat`，固定频带保护也不能保证目标保护。

## 2. 修改原因

为了形成可比较的三组基线，保留 Current FDC 不覆盖，在 adapter 中新增 `FrequencyDomainCancellerCalibrated`：

1. 用 received IQ 与雷达模板的匹配响应估计目标位置；
2. 从接收信号中减去该目标估计，得到残差；
3. 在下变频残差中计算 improper/pseudo-covariance；
4. 构造 AM 实包络对应的共轭对称分量作为 `J_hat`；
5. 使用 `strength/(1+regularization)` 对 `J_hat` 做正则化抵消。

估计位置来自输入信号本身，算法没有读取 `target_idx`、jammer label、jammer signal 或 `jam_info`。

## 3. 数学模型

AM 干扰近似为：

```text
j(t) = a_real(t) exp(j(2*pi*f0*t + phi))
```

下变频后，伪协方差统计为：

```text
r = sum(z(t)^2) / (sum(|z(t)|^2) + eps)
```

相位估计为 `phi_hat = angle(r)/2`，AM 分量估计为：

```text
j_hat_bb(t) = 0.5 * (z(t) + exp(j*2*phi_hat) conj(z(t)))
y_bb(t) = x_bb(t) - strength/(1+lambda) * confidence * j_hat_bb(t)
```

其中 `confidence` 对 improper ratio 做固定范围归一化，`lambda` 为 regularization。该路径不是固定高能频点删除。

## 4. 修改文件

- `anti_jamming/adapters.py`：新增 `calibrated_fdc_adapter` 及注册名 `FrequencyDomainCancellerCalibrated`；Current FDC 未改写。
- `run_fdc_calibration.py`：新增 baseline、参数搜索、AM 主矩阵和非 AM 负测试入口；使用白名单构造 adapter 输入。
- `docs/tasks/034_fdc_am_calibration.md`：任务记录。
- `docs/reports/034_fdc_initial_analysis.md`：修改前实现审查。
- `docs/reports/034_fdc_am_calibration_result.md`：本报告。

未修改 jammer、JSR、radar config、evaluation、RL、reward、state 或 action space。

## 5. 参数范围与选择

搜索范围：

| 参数 | 搜索值 |
|---|---|
| `cancellation_strength` | 0.2, 0.4, 0.6, 0.8, 1.0 |
| `regularization` | 0.05, 0.15, 0.30 |
| 场景 | AMNoiseGaiJam, JSR=20dB, 20 seeds |

按 JSR=20 dB 主场景的平均 delta SINR 和 target-only 约束选择：

```text
cancellation_strength=1.0
regularization=0.05
```

该参数选择没有挑选单个 seed；全部 20 seeds 参与聚合。完整搜索结果见 `results/phase1/fdc/parameter_search/summary.csv`。

## 6. AMNoiseGaiJam 结果

正式矩阵为 4 个 JSR、20 seeds，使用 Identity、Current_FDC、New_FDC。下表是 New FDC 与 Current FDC 的主要结果：

| JSR | Current delta SINR | New delta SINR | Pd before -> after | New target-only change |
|---:|---:|---:|---:|---:|
| 0 dB | +0.265 dB | **+3.433 dB** | 1.00 -> 1.00 | -0.011 dB |
| 10 dB | +0.485 dB | **+4.990 dB** | 1.00 -> 1.00 | -0.011 dB |
| 20 dB | -0.042 dB | **+4.529 dB** | 0.05 -> 1.00 | -0.011 dB |
| 30 dB | -0.862 dB | -4.466 dB | 0.00 -> 0.15 | -0.011 dB |

跨 4 个 JSR 平均：

- Identity：delta SINR `0.000 dB`，Pd `0.5125 -> 0.5125`；
- Current FDC：delta SINR `-0.038 dB`，Pd `0.5125 -> 0.6625`；
- New FDC：delta SINR `+2.121 dB`，Pd `0.5125 -> 0.7875`。

结论：New FDC 在 JSR 0/10/20 dB 已形成相对 Identity 和 Current FDC 的专用优势；JSR 30 dB 出现明显退化和较大方差，不能宣称全 JSR 通过。高 JSR 退化很可能与强 AM 残差导致模板位置估计失配有关，但这属于后续假设，当前只记录为风险，不把它写成已证实原因。

## 7. 非 AM 负测试

非 AM 场景结果保存在 `results/phase1/fdc/negative_results/metrics.csv` 和 `final_matrix.csv`。New FDC 的 delta SINR：

| 干扰 | JSR=0 | JSR=10 | JSR=20 | JSR=30 |
|---|---:|---:|---:|---:|
| FMZuse | +0.000 | +0.014 | +0.025 | +0.005 |
| FMNoiseAimedJam | +0.053 | +0.155 | +0.037 | -0.019 |
| NoiseProductJamming | +0.457 | +0.953 | +0.086 | -0.188 |

New FDC 的 target-only response change 在这些场景均约 `-0.011 dB`，没有发现严重目标损伤。NoiseProductJamming 在 JSR 10/20 dB 的 false peak 均值分别由 0.40/0.35 变为 0.50/0.55，存在轻微假峰增加风险，但不是大面积异常；因此 New FDC 不应作为该类干扰的专用算法。

## 8. target preservation

target-only 分支对每个 case 单独执行：

```text
clean target -> same FDC -> target_only_response_change_db
```

20 seeds、4 JSR 的 New FDC 均约 `-0.011 dB`，95% CI 很小，满足 `>-1 dB`。这证明当前参数下算法在 clean target-only 输入上没有明显损伤；它不能抵消 JSR=30 dB contaminated branch 的性能退化结论。

## 9. 与 Identity 比较

Identity 作为 Baseline 0 保存在 `results/phase1/fdc/baseline/metrics.csv` 和 `am_results/metrics.csv`。Current FDC 作为 Baseline 1，New FDC 作为 Baseline 2。三者均使用 Task 033-fix2 的 `delta_sinr_db`、Pd、peak error、false peak、`target_only_response_change_db` 和 runtime 字段。

## 10. 是否形成专用优势

**部分形成，尚未完全通过验收。**

- AM JSR 0/10/20：满足平均收益、Pd 不下降和目标保护要求；
- AM JSR 30：New FDC 退化，未满足高 JSR 稳定性要求；
- 非 AM：未出现明显目标损伤，但 NoiseProductJamming 假峰有轻微上升；
- 公平性：adapter 输入使用白名单，不含 `target_idx`、jammer 类型、真实 jammer signal 或 `jam_info`；
- 理论闭环：New FDC 已显式构造 AM 共轭分量估计并抵消，但尚未用独立 jammer ground truth 证明 `J_hat` 的估计误差。

因此 Task 034 的代码和实验基础已完成，但算法验收应标记为“AM 中等 JSR 通过，高 JSR 待修复”，不应直接进入更高层 RL 使用。

## 11. 测试命令和结果

```bash
./.venv/bin/python run_fdc_calibration.py --seeds 20 --output-dir results/phase1/fdc
```

结果：parameter search 15 组、AM 240 cases、非 AM 720 cases，所有结果保存成功。

```bash
./.venv/bin/python validate_algorithms.py
```

结果：9/10 配对 PASS；既有 `FMNoiseAimedJam/frft_filter` 失败保留，FDC/AM 配对通过。

```bash
./.venv/bin/python run_correctness_tests.py
```

结果：内部 4 PASS、1 WARN、5 FAIL。FDC/AM 配对为 PASS；其余失败为既有 SliceCombine loader、FrFT 测试入口和其他算法问题，未在本任务扩大范围。

```bash
./.venv/bin/python -m py_compile anti_jamming/adapters.py run_fdc_calibration.py
```

结果：通过。

## 12. 未解决问题与风险

- JSR=30 dB 的 New FDC 明显退化，当前不能作为全强度稳定算法；
- 当前 FDC 与旧 `FrequencyDomainCanceller` 类仍是两套实现，旧类默认 `f0=40e6` 的历史语义未在本任务删除；
- 评测使用模板匹配定位目标，虽然不读取 target_idx，但高 JSR 下定位鲁棒性仍需单独验证；
- 本任务没有修改统一 evaluation 或 RL，因此没有更新 RL 动作映射；
- NoiseProductJamming 的假峰变化提示 New FDC 不应泛化为万能抑制器。

## 13. Git

分支：`algorithm_design_0711`

主提交：`b6966ee phase1-034-fdc-am-calibration`
