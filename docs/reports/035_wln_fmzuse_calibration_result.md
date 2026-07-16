# Task 035：WLN ↔ FMZuse 专用算法校准结果

## 1. 执行结论

最终状态：**REJECTED**。

Current WLN 和 calibration 选出的 `par1=1.0, par2=6` 候选在 FMZuse JSR=10/20/30 dB 上可以产生正 Delta SINR，但负控干扰上的平均收益更高，specificity gap 全部为负；JSR=0 dB 仍有明显负收益。因此不能证明 WLN 利用了 FMZuse 独有结构，也不具备进入最终 RL candidate matrix 的资格。

推荐适用 JSR 区间：**无**。后续若保留该算法，只能作为通用候选进行独立审查，不能以 FMZuse 专用算法进入 RL。

## 2. 当前 WLN 原理

当前流程是固定宽带 Butterworth band-pass、接收幅度 95 分位阈值的 μ 律软限幅、固定窄带 Butterworth band-pass；模板也经过相同两级滤波。`par1` 控制 percentile 阈值倍率，`par2` 同时控制两级滤波器阶数。当前没有 FM 调频率估计、瞬时频率轨迹提取或 FM 结构检测。

详细审计见 `docs/reports/035_wln_initial_audit.md`。

## 3. Baseline 与数据拆分

- Identity：不处理 received；
- Current WLN：adapter 参数 `par1=0.3, par2=6`；
- Candidate：`par1=1.0, par2=6`；
- calibration：seeds `1000..1019`，JSR `0/5/10/20/30`，9 个参数组合；
- held-out FMZuse：seeds `2000..2049`，JSR `0/10/20/30`；
- held-out negative controls：AMNoiseGaiJam、FMNoiseAimedJam、FMNoiseSaopin、SMSP、NoiseProductJamming，seeds `2000..2029`，JSR `10/20/30`。

所有结果均使用 Task 034-fix3 的白名单、target-only、Jammer Contract 和 Interface/Performance 评价路径；所有正式 rows 的 oracle audit 为 PASS、Jammer Contract 为 `UNIFIED_JSR_PASS`。

## 4. Calibration 搜索

全部 9 组组合均保存于 `results/phase1/task035/calibration/candidate_ranking.csv`。综合分数同时扣除低 JSR 负收益、目标保护损失和假峰增加，最高组合为：

```text
par1=1.0, par2=6, score=0.1351
```

这只是 calibration 选择，held-out 结果没有用于再次调参。

## 5. FMZuse held-out 结果

| Algorithm | JSR | Delta SINR mean | 95% CI half-width | Pd Identity -> Algorithm | Target-only change |
|---|---:|---:|---:|---:|---:|
| Current WLN | 0 | -1.093 | 0.031 | 1.00 -> 1.00 | +1.754 dB |
| Current WLN | 10 | +1.153 | 0.034 | 1.00 -> 1.00 | +1.754 dB |
| Current WLN | 20 | +2.983 | 0.141 | 0.52 -> 0.52 | +1.754 dB |
| Current WLN | 30 | +2.875 | 0.249 | 0.00 -> 0.10 | +1.754 dB |
| Candidate | 0 | -0.887 | 0.028 | 1.00 -> 1.00 | +2.885 dB |
| Candidate | 10 | +1.057 | 0.030 | 1.00 -> 1.00 | +2.885 dB |
| Candidate | 20 | +2.550 | 0.125 | 0.52 -> 0.52 | +2.885 dB |
| Candidate | 30 | +2.368 | 0.213 | 0.00 -> 0.04 | +2.885 dB |

Candidate 在 10/20/30 dB 满足正收益和 target-only 数值门槛，但 JSR=30 的绝对 Pd 仍很低，且这些收益不具备专用性。

## 6. 非 FMZuse 负控与专用性

Held-out specificity 定义为 FMZuse gain 减去 5 个负控的平均 gain。候选结果：

| JSR | FMZuse gain | Negative-control mean | Specificity gap |
|---:|---:|---:|---:|
| 10 | +1.057 dB | +2.218 dB | -1.161 dB |
| 20 | +2.550 dB | +3.496 dB | -0.946 dB |
| 30 | +2.368 dB | +3.040 dB | -0.672 dB |

Current WLN 的对应 specificity gap 为 `-1.326/-1.017/-0.584 dB`。FMNoiseSaopin 等负控上的收益尤其大，说明当前 WLN 更像通用频带/幅度处理器，而非 FMZuse 专用检测器。负控中所有结果均为统一 JSR、Interface PASS、oracle PASS；未使用 legacy jammer。

## 7. JSR=0 dB 退化

代码事实：低 JSR 时仍无条件执行两级固定频带滤波和 μ 律压缩，没有依据接收 IQ 判断“无需处理”的 bypass/gating。Calibration 与 held-out 均复现约 `-1 dB` 损伤，说明该风险不是单一 seed 偶然现象。合理解释是目标/噪声也被固定滤波和非线性变换处理；本任务未引入 gating，因此不把未验证的因果细节写成结论。

## 8. 目标保护、资源和契约

Current/Candidate 的 held-out target-only response 均为正，状态为 `TARGET_PRESERVED`；peak error 和 false peak 字段已保存在 aggregate/per-trial CSV。所有 FMZuse 与负控正式 rows 的 `interface_status=PASS`、`oracle_input_status=PASS`、`jammer_contract_status=UNIFIED_JSR_PASS`。runtime 约 2.1~2.3 ms，memory 约 0.84 MB，详见 CSV。

## 9. 结果证据

```text
results/phase1/task035/
├── baseline/
├── calibration/
├── heldout_fmzuse/
├── negative_controls/
├── diagnostics/
├── task_summary.json
├── stdout.txt
└── stderr.txt
```

关键 CSV、JSON、stdout 和 stderr 均纳入 Git；held-out 结果冻结后没有继续调参。

## 10. 未解决问题

- 若未来重新研究 WLN，应单独设计并预注册无 oracle gating，再使用新的 held-out 集；本任务不继续修改。
- WLN 仍可作为通用算法研究对象，但不能宣称 FMZuse 专用优势或加入最终 RL candidate matrix。
- 本任务没有修改 jammer、JSR、evaluation contract、其他算法或 RL。

## 11. Git 信息

- 分支：`algorithm_design_0711`
- 主提交 SHA：`7de5855`
