# Task 036-fix Stage A：现有结果冻结

## 冻结状态

Task 036-fix 在 `c8909c45d4c8ed92acd58996fdc4698e74afb19b`、分支 `algorithm_design_0711` 上启动。只读校验显示 `origin/algorithm_design_0711` 当前 SHA 同为 `c8909c45d4c8ed92acd58996fdc4698e74afb19b`；因此旧的 `COMPLETED_LOCAL_PUSH_BLOCKED` 记录需要在本任务末尾修正为远端已同步，但原始 push 失败证据不能删除。

legacy `anti_jamming/adapt_filter.py`、legacy adapter 和原 Task 036 的 `ORACLE_UPPER_BOUND_ONLY` 决策均冻结，不重新开放 Oracle 结论。原始证据目录 `results/phase1/task036/` 只读保留；本任务使用独立目录 `results/phase1/task036_fix/`。

当前工作树中的 Task 034-fix3 CSV 修改、`.codex/` 和 `docs/tasks/phase1_master_plan.md` 均属于既有或无关状态，不纳入 Stage A commit。

## 固定 hash 与证据

目标源文件和旧结果 hash 见 [file_hashes.txt](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageA/file_hashes.txt)，Git 状态见 [git_status.txt](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageA/git_status.txt)，结构化基线见 [baseline_metadata.json](/Users/jiangtao/anti_jamming/results/phase1/task036_fix/stageA/baseline_metadata.json)。

明确状态：

```text
legacy_decision = ORACLE_UPPER_BOUND_ONLY
legacy_decision_reopened = false
current_remote_synced = true
previous_push_attempt = BLOCKED_BY_TENANT_SECURITY_POLICY
later_manual_push = true
```

下一阶段建立物理一致的目标位置 fixture；不得继续把 whole-record translation 作为正式位置鲁棒性证据。
