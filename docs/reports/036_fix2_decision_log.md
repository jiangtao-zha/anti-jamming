# Task 036-fix2 Decision Log

## Stage A — 2026-07-18

- Status: `COMPLETED`; result commit `1f69bcb` (`phase1-036-fix2-stageA-audit-invalid-dispatch`).
- Decision: `INVALID_FROZEN_CANDIDATE_DISPATCH`; old Task 036-fix results are preserved as historical evidence.
- Stage D froze `B_k3_c0.8_r0.001` (`design=B`), while old Stage E called `fit_adapt_filter_fair` (`design=A`).
- Old behavior signatures included `fit_status` and `gate_reasons`; these are metadata, not behavior identity.
- Evidence: `results/phase1/task036_fix2/stageA/` and `docs/reports/036_fix2_stageA_invalid_dispatch_audit.md`.
- Next stage: unified dispatch, behavior-only deduplication, and recalibration.

## Stage B — 2026-07-18

- Status: `COMPLETED`; result commit pending.
- Decision: `DISPATCH_AND_BEHAVIOR_DEDUP_PASS`; 8 nominal candidates reduced to 2 effective behavior classes.
- Dispatch: A→`fit_adapt_filter_fair`, B→`fit_adapt_filter_fair_multihypothesis`; mismatch `0`, interface failures `0`, oracle input failures `0`, negative mismatch test `PASS`.
- Calibration: seeds `9000..9019`, 4,800 trial rows, 48 aggregates, no qualified candidate.
- Canonical rejection representative: `A_k3_c0.8_r0.001` in `EQ_001`; the equivalent class contains four A/B members.
- Evidence: `results/phase1/task036_fix2/stageB/` and `docs/reports/036_fix2_stageB_dispatch_dedup_result.md`.
- Next stage: new held-out seeds `9200..9249` using the frozen Stage B representative.
