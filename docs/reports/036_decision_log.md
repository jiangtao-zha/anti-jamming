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
- Result commit: pending until the Stage 2 artifact commit is created.
- Decision: `ORACLE_DEPENDENCE_CONFIRMED`.
- Evidence: `results/phase1/task036/stage2/` and `docs/reports/036_stage2_sensitivity_analysis.md`.
- Next gate: design at least three observable-only alternatives in Stage 3; do not tune the legacy oracle implementation.
