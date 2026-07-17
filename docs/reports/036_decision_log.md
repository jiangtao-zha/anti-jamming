# Task 036 Decision Log

## Stage 0 — 2026-07-18

- Status: `COMPLETED`
- Freeze commit: `9853ded` (`phase1-036-stage0-freeze-baseline`).
- Decision: current `adapt_filter` remains a retained `ORACLE_UPPER_BOUND / LEGACY BASELINE`; fair version is `NOT_IMPLEMENTED`.
- Evidence: `results/phase1/task036/stage0/` and `docs/reports/036_stage0_baseline_freeze.md`.
- Next gate: complete Stage 1 oracle audit before changing algorithm code.

## Stage 1 — 2026-07-18

- Status: `COMPLETED`
- Result commit: `8cc4662` (`phase1-036-stage1-oracle-audit`).
- Decision: `C_CURRENT_ALGORITHM_REQUIRES_TARGET_ALIGNMENT_ORACLE`.
- Evidence: `results/phase1/task036/stage1/` and `docs/reports/036_stage1_oracle_audit.md`.
- Next gate: run fixed-IQ offset, missing-index, and multi-position sensitivity experiments in Stage 2.

## Stage 2 — 2026-07-18

- Status: `COMPLETED`
- Result commit: `0d9ea1e` (`phase1-036-stage2-oracle-sensitivity`).
- Decision: `ORACLE_DEPENDENCE_CONFIRMED`.
- Evidence: `results/phase1/task036/stage2/` and `docs/reports/036_stage2_sensitivity_analysis.md`.
- Next gate: design at least three observable-only alternatives in Stage 3; do not tune the legacy oracle implementation.

## Stage 3 — 2026-07-18

- Status: `COMPLETED`
- Result commit: `d2bb5a8` (`phase1-036-stage3-fair-design`).
- Decision: `OPEN_FOR_ISOLATED_PROTOTYPES_A_AND_B`; C remains exploratory and D remains the formal rejection option.
- Evidence: `results/phase1/task036/stage3/` and `docs/reports/036_stage3_fair_design.md`.
- Next gate: implement only isolated A/B prototypes with fit/apply separation and mandatory Identity fallback.

## Stage 4 — 2026-07-18

- Status: `COMPLETED`
- Result commit: `22cb399` (`phase1-036-stage4-fair-prototype`).
- Decision: `PROTOTYPE_GATE_PASS_A_AND_B`; both prototypes proceed to calibration.
- Evidence: `results/phase1/task036/stage4/` and `docs/reports/036_stage4_prototype_result.md`.
- Next gate: search at most 40 deduplicated calibration configurations; freeze any selected candidate before held-out.

## Stage 5 — 2026-07-18

- Status: `COMPLETED`
- Result commit: pending until the Stage 5 calibration artifact commit is created.
- Decision: `NO_CALIBRATION_QUALIFIED; REJECTION_CONFIRMATION_ONLY`.
- Frozen rejection-confirmation prototype: `A_k3_c0.05_r0.001`; it is not a fair candidate.
- Evidence: `results/phase1/task036/stage5/` and `docs/reports/036_stage5_calibration_result.md`.
- Next gate: run held-out seeds only for Identity, Oracle upper bound, and the frozen unqualified prototype.
