# Task 036-fix2 Decision Log

## Stage A — 2026-07-18

- Status: `COMPLETED`; result commit `1f69bcb` (`phase1-036-fix2-stageA-audit-invalid-dispatch`).
- Decision: `INVALID_FROZEN_CANDIDATE_DISPATCH`; old Task 036-fix results are preserved as historical evidence.
- Stage D froze `B_k3_c0.8_r0.001` (`design=B`), while old Stage E called `fit_adapt_filter_fair` (`design=A`).
- Old behavior signatures included `fit_status` and `gate_reasons`; these are metadata, not behavior identity.
- Evidence: `results/phase1/task036_fix2/stageA/` and `docs/reports/036_fix2_stageA_invalid_dispatch_audit.md`.
- Next stage: unified dispatch, behavior-only deduplication, and recalibration.
