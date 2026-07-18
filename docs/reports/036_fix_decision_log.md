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

- Status: `COMPLETED`; result commit pending.
- Decision: `PHYSICAL_FIXTURE_GATE_PASS`.
- Formal fixture: `PHYSICAL_COMPONENT_RECOMPOSITION`; old whole-record translation is `WHOLE_RECORD_TRANSLATION_STRESS` only.
- Evidence: `results/phase1/task036_fix/stageB/` and `docs/reports/036_fix_stageB_physical_position_fixture.md`.
- Validation: 700 jammer rows `PASS`, 100 NoJammer rows `NO_JAMMER_NOT_APPLICABLE`, 0 failures; target/noise/jammer energy and JSR checks pass.
- Next stage: effective observable confidence and Identity gating.
