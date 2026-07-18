# Task 037 Decision Log

## Stage 0 — 2026-07-18

- Status: `COMPLETED`; result commit `c65d7d1` (`phase1-037-stage0-freeze-frft-baseline`).
- Decision: `BASELINE_FROZEN`; Current FrFT and Identity are preserved, future candidate is `NOT_IMPLEMENTED`.
- Current implementation: `anti_jamming/frft_filter.py:myfrft` plus `anti_jamming/adapters.py:frft_adapter`; default order search `[0.75,1.35]`, 25 points, `mask_threshold=0.1`.
- Existing formal evidence: 160 FrFT interface rows, 160 PASS, oracle input failures 0; existing SMSP/FMNoiseSaopin results remain negative/near-neutral and are not recomputed here.
- Historical Task 036-fix2 state: later manual sync recorded as `COMPLETED_REMOTE_SYNCED`, SHA `7fe8b146fe34b6667061c844bd3e1887e6fe5fa2`; original push failure evidence preserved.
- Path-only correction: old Stage D/E defaults now point to `results/phase1/task036_fix2/stageB` and `stageC`; Task 036-fix2 was not rerun.
- Next stage: Stage 1 mathematical and numerical correctness audit.

## Stage 1 — 2026-07-18

- Status: `COMPLETED`; result commit `b6899b3` (`phase1-037-stage1-frft-correctness-audit`).
- Gate: `PASS`; `property_tests.csv` 92/92 PASS, edge cases 5/5 PASS, Oracle/input audit PASS.
- Core correction: replaced the non-unitary, inverse-inconsistent chirp-convolution translation in `myfrft` with an explicit finite-dimensional spectral fractional power of the centered orthonormal DFT. This is the only algorithm correction in Stage 1.
- Definition: `theta=pi*a/2`, order period 4; `a=0/1/2/3` are `I/U/U^2/U^3`, and `a=4` is `I`.
- Continuous LFM theoretical order: not claimed under this finite-grid spectral convention; the chirp scan records `NOT_IDENTIFIABLE_WITHOUT_CONTINUOUS_SCALING` and passes the audit by making the limitation explicit.
- Oracle boundary: FrFT adapter was called with the whitelist-only receiver dictionary; no forbidden target position, jammer label, JSR, or truth-component access was detected.
- Next stage: Stage 2 separability diagnostics. No RL change is authorized.
