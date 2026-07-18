# Task 036-fix Decision Log

## Stage A — 2026-07-18

- Status: `COMPLETED`.
- Result commit: `24603f1` (`phase1-036-fix-stageA-freeze`).
- Baseline: local and remote `algorithm_design_0711` both at `c8909c45`.
- Legacy decision retained: `ORACLE_UPPER_BOUND_ONLY`; `legacy_decision_reopened=false`.
- Previous push failure is preserved as historical evidence; current remote sync is confirmed by `git ls-remote`.
- Evidence: `results/phase1/task036_fix/stageA/` and `docs/reports/036_fix_stageA_baseline.md`.
- Next stage: build physical component-recomposition fixture.

## Stage B — 2026-07-18

- Status: `COMPLETED`; result commit `d4618d0` (`phase1-036-fix-stageB-physical-position-fixture`).
- Decision: `PHYSICAL_FIXTURE_GATE_PASS`.
- Formal fixture: `PHYSICAL_COMPONENT_RECOMPOSITION`; old whole-record translation is `WHOLE_RECORD_TRANSLATION_STRESS` only.
- Evidence: `results/phase1/task036_fix/stageB/` and `docs/reports/036_fix_stageB_physical_position_fixture.md`.
- Validation: 700 jammer rows `PASS`, 100 NoJammer rows `NO_JAMMER_NOT_APPLICABLE`, 0 failures; target/noise/jammer energy and JSR checks pass.
- Next stage: effective observable confidence and Identity gating.

## Stage C — 2026-07-18

- Status: `COMPLETED`; result commit `7b13949` (`phase1-036-fix-stageC-effective-gating`).
- Decision: `GATING_DESIGN_PASS`.
- Five fixed observable confidence components replace the tautological max-peak normalization; weights and threshold are recorded in `gating_metadata.json`.
- Validation: 16 A/B cases, interface failures 0, components in `[0,1]`, total fallback `8/16=0.5`.
- Evidence: `results/phase1/task036_fix/stageC/` and `docs/reports/036_fix_stageC_effective_gating.md`.
- Next stage: behavior-signature deduplication and small calibration.

## Stage D — 2026-07-18

- Status: `COMPLETED`; result commit `be8fa2a` (`phase1-036-fix-stageD-dedup-calibration`).
- Decision: `NO_CALIBRATION_QUALIFIED; REJECTION_CONFIRMATION_ONLY`.
- Nominal/effective candidates: `8/4`; calibration rows: `9,600`; aggregate rows: `96`.
- Frozen rejection-confirmation representative: `B_k3_c0.8_r0.001`; it is not a selected candidate.
- Evidence: `results/phase1/task036_fix/stageD/` and `docs/reports/036_fix_stageD_dedup_calibration.md`.
- Next stage: independent held-out rejection confirmation with new seeds `9100..9149`.

## Stage E — 2026-07-18

- Status: `COMPLETED`; result commit `cfe39fc` (`phase1-036-fix-stageE-confirm-oracle-only`).
- Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`.
- Held-out mode: `REJECTION_CONFIRMATION_ONLY`; frozen representative `B_k3_c0.8_r0.001`; seeds `9100..9149`; formal aggregation is jammer×JSR across seed×position.
- Results: 24,000 trial rows, 96 aggregate rows, 480 position rows, interface failures `0`, fair target-erased rows `0`, fallback ratio `0.490125`.
- Passing JSR counts: `NoiseProductJamming=1`, `NoiseConvolutionJamming=1`; neither target jammer reaches the required two distinct passing JSR conditions.
- Evidence: `results/phase1/task036_fix/stageE/` and `docs/reports/036_fix_stageE_heldout_result.md`.
- Next stage: final status, regression, record commit, and remote push verification.

## Stage F — 2026-07-18

- Status: `COMPLETED`; result commit `c1c7c68` (`phase1-036-fix-finalize`).
- Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`; legacy `ORACLE_UPPER_BOUND_ONLY` retained.
- Regression: `validate_algorithms.py` exit `0`, interface `800/800` PASS; `run_correctness_tests.py` exit `0`, failures `0`.
- Eligibility: `rl_eligible=false`, `candidate_matrix_eligible=false`, `fair_registered=false`, `rl_action_space_modified=false`.
- Historical Task 036 push status corrected to `COMPLETED_REMOTE_SYNCED`; original tenant-policy failure evidence remains. New Task 036-fix push was rejected before execution by tenant security policy; status is `PUSH_BLOCKED_BY_POLICY` and the local/remote verification evidence is saved.
- Evidence: `results/phase1/task036_fix/stageF/`, `docs/reports/036_fix_physical_fixture_gating_result.md`, and `scripts/run_task036_fix.py`.
