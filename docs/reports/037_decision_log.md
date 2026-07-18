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

## Stage 2 — 2026-07-18

- Status: `COMPLETED`; result commit `4ed22df` (`phase1-037-stage2-frft-separability-diagnostics`).
- Gate: `PASS_TO_STAGE3_ORACLE_DIAGNOSTIC`.
- Formal objects: `SMSP` and `FMNoiseSaopin`; supplementary objects are kept separate and are not part of the formal fairness conclusion.
- Configuration: seeds `10000..10029`, JSR `0/10/20/30`, target centers `1000/1500/2500/3500/4000`, coarse orders `[-1,1]` step `0.02`, local 1000-sample diagnostic window.
- Result: both formal jammers pass the preliminary order/spatial gate; peak order-gap median and q25 are `1.90`/`1.90`, and median same-order overlap is `0.000` for both formal objects.
- Boundary: true component data stayed inside the diagnostic runner; no formal adapter was called and no RL eligibility changed.
- Next stage: Stage 3 Oracle upper-bound experiment, explicitly diagnostic-only and not fair/RL-eligible.

## Stage 3 — 2026-07-18

- Status: `COMPLETED`; result commit to be recorded after the stage commit.
- Decision: `ORACLE_UPPER_BOUND_FAILED`; `qualified_rows=0` across 128 aggregate strategy×mask×jammer×JSR rows.
- Experiment: 800 component cases from seeds `10100..10119`, JSR `0/10/20/30`, five target centers; four pre-registered order strategies and four Oracle masks; 12800 trial rows.
- Best observed ΔSINR means stayed below 1 dB. FMNoiseSaopin had some nonnegative CI lower bounds but failed Pd and target-only preservation; SMSP also failed CI/Pd/position or delta requirements.
- Oracle target-protection was strengthened to a hard support retaining 90% cumulative true-target FrFT energy; the conclusion remained `FAILED`.
- Gate consequence: Stage 4 observable prototype and Stage 5 calibration are `SKIPPED_BY_DECISION_GATE`; Stage 6 will only run small rejection confirmation. `candidate_matrix_eligible=false`, `rl_eligible=false`.
