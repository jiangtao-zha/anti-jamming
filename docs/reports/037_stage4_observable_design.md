# Task 037 Stage 4 — Observable FrFT 原型设计

日期：2026-07-18

状态：`SKIPPED_BY_DECISION_GATE`

Stage 3 的 Oracle upper bound 在 `SMSP` 和 `FMNoiseSaopin` 上均失败，未满足同时保留目标、提高 ΔSINR、维持 Pd 和位置鲁棒性的门槛。因此不设计或实现 observable-only FrFT 原型，不新增 candidate，不修改 adapter、action space 或 RL。

按任务要求，`results/phase1/task037/stage4/` 仍保存空的设计/烟测 CSV、skip metadata 和 summary。复现入口：

```bash
MPLCONFIGDIR=/tmp/task037-mpl .venv/bin/python scripts/run_task037.py --stage prototype
```

Git 分支：`algorithm_design_0711`。

规定提交：`c42012d`（`phase1-037-stage4-observable-prototype-skipped`）。
