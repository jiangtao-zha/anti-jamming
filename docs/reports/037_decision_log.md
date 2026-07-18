# Task 037 Decision Log

## Stage 0 — 2026-07-18

- Status: `COMPLETED`; commit pending at report creation.
- Decision: `BASELINE_FROZEN`; Current FrFT and Identity are preserved, future candidate is `NOT_IMPLEMENTED`.
- Current implementation: `anti_jamming/frft_filter.py:myfrft` plus `anti_jamming/adapters.py:frft_adapter`; default order search `[0.75,1.35]`, 25 points, `mask_threshold=0.1`.
- Existing formal evidence: 160 FrFT interface rows, 160 PASS, oracle input failures 0; existing SMSP/FMNoiseSaopin results remain negative/near-neutral and are not recomputed here.
- Historical Task 036-fix2 state: later manual sync recorded as `COMPLETED_REMOTE_SYNCED`, SHA `7fe8b146fe34b6667061c844bd3e1887e6fe5fa2`; original push failure evidence preserved.
- Path-only correction: old Stage D/E defaults now point to `results/phase1/task036_fix2/stageB` and `stageC`; Task 036-fix2 was not rerun.
- Next stage: Stage 1 mathematical and numerical correctness audit.
