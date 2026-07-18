# Task 036-fix2 Decision Log

## Stage A — 2026-07-18

- Status: `COMPLETED`; result commit `1f69bcb` (`phase1-036-fix2-stageA-audit-invalid-dispatch`).
- Decision: `INVALID_FROZEN_CANDIDATE_DISPATCH`; old Task 036-fix results are preserved as historical evidence.
- Stage D froze `B_k3_c0.8_r0.001` (`design=B`), while old Stage E called `fit_adapt_filter_fair` (`design=A`).
- Old behavior signatures included `fit_status` and `gate_reasons`; these are metadata, not behavior identity.
- Evidence: `results/phase1/task036_fix2/stageA/` and `docs/reports/036_fix2_stageA_invalid_dispatch_audit.md`.
- Next stage: unified dispatch, behavior-only deduplication, and recalibration.

## Stage B — 2026-07-18

- Status: `COMPLETED`; result commit `29c143c` (`phase1-036-fix2-stageB-dispatch-behavior-dedup`).
- Decision: `DISPATCH_AND_BEHAVIOR_DEDUP_PASS`; 8 nominal candidates reduced to 2 effective behavior classes.
- Dispatch: A→`fit_adapt_filter_fair`, B→`fit_adapt_filter_fair_multihypothesis`; mismatch `0`, interface failures `0`, oracle input failures `0`, negative mismatch test `PASS`.
- Calibration: seeds `9000..9019`, 4,800 trial rows, 48 aggregates, no qualified candidate.
- Canonical rejection representative: `A_k3_c0.8_r0.001` in `EQ_001`; the equivalent class contains four A/B members.
- Evidence: `results/phase1/task036_fix2/stageB/` and `docs/reports/036_fix2_stageB_dispatch_dedup_result.md`.
- Next stage: new held-out seeds `9200..9249` using the frozen Stage B representative.

## Stage C — 2026-07-18

- Status: `COMPLETED`; result commit `00ad699` (`phase1-036-fix2-stageC-confirm-oracle-only`).
- Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`.
- Corrected held-out uses frozen `A_k3_c0.8_r0.001`, design A, `fit_adapt_filter_fair`, and new seeds `9200..9249`; old `9100..9149` remains invalid dispatch history.
- Evidence: 24,000 trial rows, 96 aggregates, 480 position rows, dispatch mismatches `0`, interface failures `0`, fair target-erased rows `0`, fallback ratio `0.495375`.
- Passing JSR counts: `NoiseProductJamming=1`, `NoiseConvolutionJamming=1`; no target jammer meets the required two distinct passing JSR conditions.
- Evidence: `results/phase1/task036_fix2/stageC/` and `docs/reports/036_fix2_stageC_corrected_heldout_result.md`.
- Next stage: final status, regression, record commit, and remote verification.

## Stage D — 2026-07-18

- Status: `COMPLETED`; result commit `a416f34` (`phase1-036-fix2-finalize`).
- Regression: `validate_algorithms.py` exit `0` with interface PASS `800/800`; `run_correctness_tests.py` exit `0` with failures `0`; post-held-out dedup lock exited `1` as expected.
- Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`; `FAIR_CANDIDATE` is prohibited and all RL eligibility flags remain false.
- Historical Task 036-fix status is recorded as manually synchronized at tracking/remote head `7fe8b146`; old automatic push failure evidence remains preserved.
- Evidence: `results/phase1/task036_fix2/stageD/`, `docs/reports/036_fix2_frozen_dispatch_dedup_result.md`, and the stage manifest.
- Record commit: `a6b12f6` (`phase1-036-fix2-record-commit`).
- Initial push result: `PUSH_BLOCKED_BY_POLICY`; push-attempt commit `a6b12f6`, with original tracking ref `cb7eac7`; later manual synchronization is recorded at `7fe8b146fe34b6667061c844bd3e1887e6fe5fa2`. Direct SSH verification remains unavailable with `Operation not permitted`.
- Evidence: `results/phase1/task036_fix2/git_push_stdout.txt`, `git_push_stderr.txt`, and `git_remote_verification.txt`.
- Next stage: none; Task 037 remains not started.
