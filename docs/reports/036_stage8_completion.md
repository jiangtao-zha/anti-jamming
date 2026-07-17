# Task 036 Stage 8：收尾与可复现性

Task 036 的 Stage 0–8 本地交付已完成。最终结论为 `ORACLE_UPPER_BOUND_ONLY`，没有 fair candidate 进入 RL，也没有开始长时间训练。完整阶段证据由 `results/phase1/task036/stage_manifest.json`、`results/phase1/task036/task_summary.json` 和各 stage 子目录保存。最终外部 push 已尝试但被租户安全策略阻断，远端未宣称同步成功。

可复现入口为 [run_adapt_filter_fairness.py](/Users/jiangtao/anti_jamming/scripts/run_adapt_filter_fairness.py)，支持 `audit`、`sensitivity`、`prototype`、`calibration`、`heldout` 和 `all`。Held-out runner 只接受 Stage 5 已冻结的 rejection-confirmation 状态，不允许在 held-out 后重新调参。

阶段结果与最终解释见 [036_adapt_filter_fairness_result.md](/Users/jiangtao/anti_jamming/docs/reports/036_adapt_filter_fairness_result.md)。push 尝试的 stdout、stderr 和远端 SHA 记录在 `results/phase1/task036/git_push_stdout.txt`、`git_push_stderr.txt`、`git_remote_verification.txt`。
