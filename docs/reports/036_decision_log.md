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
- Result commit: `b623a01` (`phase1-036-stage5-calibration`).
- Decision: `NO_CALIBRATION_QUALIFIED; REJECTION_CONFIRMATION_ONLY`.
- Frozen rejection-confirmation prototype: `A_k3_c0.05_r0.001`; it is not a fair candidate.
- Evidence: `results/phase1/task036/stage5/` and `docs/reports/036_stage5_calibration_result.md`.
- Next gate: run held-out seeds only for Identity, Oracle upper bound, and the frozen unqualified prototype.

## Stage 6 — 2026-07-18

- Status: `COMPLETED`; rejection-confirmation mode only.
- Result commit: `47efff3` (`phase1-036-stage6-heldout-evaluation`); candidate source remains `b623a01` and candidate SHA is frozen in `results/phase1/task036/stage6/summary.json`.
- Decision: `ORACLE_UPPER_BOUND_ONLY`.
- Evidence: `results/phase1/task036/stage6/` and `docs/reports/036_stage6_heldout_result.md`.
- Key gate result: Fair target-only protection passed (`TARGET_ERASED=0`, NoJammer change approximately zero), but high-JSR target-jammer performance and position robustness failed; position spread is `12.5568dB`.
- Next gate: record final integration decision without registering the Fair prototype in RL.

## Stage 7 — 2026-07-18

- Status: `COMPLETED`; integration decision recorded without RL/action-space changes.
- Result commit: `c0bdbcd` (`phase1-036-stage7-reject-fair-adapt-filter`).
- Decision: `ORACLE_UPPER_BOUND_ONLY`; legacy `adapt_filter` retained as Oracle baseline, Fair prototype not registered and not candidate-matrix eligible.
- Evidence: `results/phase1/task036/stage7/` and `docs/reports/036_stage7_final_decision.md`.
- Next gate: complete Stage 8 final summary, reproducibility entry point, and repository progress/blocked-issue records.

## Stage 8 — 2026-07-18

- Status: `COMPLETED`; final summary, reproducibility entry point, progress update and blocked-issue update written.
- Result commit: `4eda312` (`phase1-036-adapt-filter-fairness-decision`); the Stage 8 record commit follows this metadata update.
- Decision: `ORACLE_UPPER_BOUND_ONLY`; Task 037 was not started.
- Evidence: `docs/reports/036_adapt_filter_fairness_result.md`, `docs/reports/036_stage8_completion.md`, `results/phase1/task036/`.
