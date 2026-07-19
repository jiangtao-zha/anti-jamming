# Task 037 Stage 5 — FrFT Calibration

日期：2026-07-18

状态：`SKIPPED_BY_DECISION_GATE`

Stage 3 Oracle 上界失败，Stage 4 没有可观测原型，因此不运行 calibration、不生成 nominal candidates、不做行为去重，也不选择 held-out candidate。Stage 5 summary 明确设置 `heldout_mode=REJECTION_CONFIRMATION_ONLY`，candidate matrix 和 RL 资格均为 false。

按任务要求，`results/phase1/task037/stage5/` 保存空的候选/聚合 CSV、skip summary 和 selected-candidate JSON。复现入口：

```bash
MPLCONFIGDIR=/tmp/task037-mpl .venv/bin/python scripts/run_task037.py --stage calibration
```

Git 分支：`algorithm_design_0711`。

规定提交：`a95e16d`（`phase1-037-stage5-calibration-skipped`）。
