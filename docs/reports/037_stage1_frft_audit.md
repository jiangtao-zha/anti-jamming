# Task 037 Stage 1 — FrFT 数学、实现和数值正确性审计

日期：2026-07-18

状态：`COMPLETED`

阶段提交：`TBD`（由本阶段记录提交回填）

## 结论

Stage 1 Gate：`PASS`。

审计确认旧的 chirp-convolution `myfrft` 在 Stage 0 基线上的非整数阶变换不满足能量保持和逆变换要求，因此执行了任务允许的最小核心正确性修复。当前实现改为有限维、中心化、正交 DFT `U` 的谱分数幂定义。修复只修改 `anti_jamming/frft_filter.py:myfrft`，没有修改 FrFT adapter 的 mask、搜索范围、雷达/干扰数学、评价指标或 RL。

## 实际定义

令 `theta = pi*a/2`，阶数按 4 周期规约。当前有限网格定义为：

```text
a=0: I
a=1: centered unitary DFT U
a=2: U^2（有限网格中心化/循环反转）
a=3: U^3
a=4: I
```

非整数阶由 `U` 的四个谱投影子空间和相位 `exp(-j*pi*k*a/2)` 构造。该实现的归一化是 `norm='ortho'`，因此在有限维数值空间中保持二范数。报告明确不把这个离散谱定义表述为带连续尺度参数的 Ozaktas LFM 聚集公式。

## 测试与结果

- 测试信号：impulse、single tone、linear chirp、reverse chirp、random complex noise、Phase 1 target template。
- 长度：8、15、16、31、32、64，以及 1000、5000 的随机复向量。
- 非整数阶：0.37、0.73、1.21；长向量追加 0.731。
- `property_tests.csv`：92/92 PASS，inverse、period-4、energy、finite-output 和输入不变性均通过。
- 最大 inverse relative error：`8.705e-16`。
- 最大 period-4 relative error：`9.891e-16`。
- 最大 energy error：`1.110e-15`。
- 边界测试：zero signal、empty input、错误维度、NaN order、Inf order，5/5 PASS；空输入和错误输入均受控抛出 `ValueError`。
- `chirp_order_validation.csv` 已对 linear chirp、reverse chirp 和 Phase 1 template 完成数值阶数扫描。由于当前定义是有限维 DFT 谱分数幂，连续 LFM 理论阶数还缺少连续坐标尺度，结果标记为 `NOT_IDENTIFIABLE_WITHOUT_CONTINUOUS_SCALING`，没有把数值最优阶数冒充理论真值。
- `oracle_input_audit.csv`：runtime whitelist、静态 forbidden access audit、输出 shape/finite 检查全部 PASS。FrFT adapter 未从输入中读取目标位置、jammer 类型、JSR 或真值分量。

完整结果在 `results/phase1/task037/stage1/`，包括数学定义、实现清单、性质表、chirp 阶数验证、Oracle input audit、summary 和 stdout/stderr。

## 设计对应关系

1. 旧实现的核心数值错误由最小修改修正；没有在本阶段调 mask。
2. 阶数周期、整数阶退化、归一化和 inverse 均由实际代码测试而非只在文档中声称。
3. `d4(a,b)=min_k |a-b+4k|` 已记录，后续 Stage 2/3 只能使用周期阶数距离。
4. FrFT adapter 仍是可观测输入路径；本阶段没有把 target index、jammer label 或 JSR 传入算法。

## 未解决问题和风险

- 该有限维谱定义不提供连续 Ozaktas 坐标尺度下的 LFM 理论聚集阶数；Stage 2 必须以实测 separability diagnostics 验证是否仍有可用的目标/干扰可分离性。
- 当前 adapter 的目标/接收阶数扫描和 mask 逻辑没有在本阶段获得性能资格；不能据此进入 RL。
- 如果 Stage 2 证明修复后的 FrFT 域没有稳定可分离性，必须停止 FrFT candidate 资格评估，而不能恢复旧的不正确实现。

## 复现

```bash
MPLCONFIGDIR=/tmp/task037-mpl .venv/bin/python scripts/run_task037.py --stage audit
```

Stage 1 runner 在已有非空结果目录时拒绝覆盖；本地调试若需重跑必须显式使用 `--overwrite`，正式结果目录仍按 stage 独立保存。
