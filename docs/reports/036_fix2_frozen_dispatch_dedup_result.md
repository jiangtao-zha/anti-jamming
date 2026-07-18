# Task 036-fix2 Final Result — Frozen Dispatch, Behavior Deduplication, and Corrected Held-out Evidence

Date: 2026-07-18
Status: `COMPLETED_LOCAL_PUSH_BLOCKED`
Finalize commit: `a416f34` (`phase1-036-fix2-finalize`)
Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`

## 1. Historical invalidity and scope

Stage A audited the previous Task 036-fix result without reopening the legacy `adapt_filter` Oracle conclusion. The previous calibration froze `B_k3_c0.8_r0.001` (`design=B`), but the previous held-out Stage E called `fit_adapt_filter_fair`, which is design A. The old Stage E files remain unchanged as historical evidence and are classified as `INVALID_FROZEN_CANDIDATE_DISPATCH`; they are not used as valid frozen-candidate evidence.

The legacy `anti_jamming/adapt_filter.py` was not modified. Its baseline SHA-256 remains `19a4ede113428d7ad0528f133a2274cf38480075241c7a2b365f9ee8bbcdba34`. No jammer, JSR definition, evaluation fixture, confidence rule, RL/PPO code, or action space was changed.

## 2. Unified dispatch and behavior identity

Stage B introduced one shared dispatch layer used by calibration and held-out:

- design A → `fit_adapt_filter_fair`;
- design B → `fit_adapt_filter_fair_multihypothesis`.

The dispatch contract validates the design/function pair before and after fitting, records the candidate parameters, and fails on a mismatch. The negative mismatch test passed, and all calibration and held-out rows recorded `dispatch_status=PASS` with zero mismatches.

Behavior signatures now contain only actual observable behavior: estimated target-index sequence, fallback sequence, confidence quantized to six decimals, and a normalized processed-output hash. Candidate ID, design, fit-function name, fit status, gate reasons, and algorithm description are excluded from identity. Canonical representative priority is A before B, smaller `top_k`, higher threshold, smaller regularization, then candidate ID.

## 3. Stage B calibration and frozen representative

The nominal matrix had 8 candidates. With the corrected signature, it reduced to 2 effective behavior equivalence classes. Calibration used seeds `9000..9019`, the existing physical Stage B fixture, and produced 4,800 trial rows and 48 jammer×JSR aggregate rows. No candidate passed the preregistered qualification gates.

The held-out representative was the canonical rejection representative `A_k3_c0.8_r0.001` in `EQ_001`. Its class contains `A_k3_c0.8_r0.001`, `A_k5_c0.8_r0.001`, `B_k3_c0.8_r0.001`, and `B_k5_c0.8_r0.001`. Choosing A follows the declared canonical priority; it is not a claim that A outperformed B. The frozen candidate file SHA-256 is `e978164f6ca18480f9f0578a4cf421dd7df8b6e1f811e447c88ac9646e3ebe0b`.

## 4. Corrected held-out evidence

Stage C used new seeds `9200..9249`. The physical fixture, candidate identity, Oracle comparison, and fair comparison rules were held fixed. The old `9100..9149` run is invalid historical evidence and is not pooled with the corrected run.

Formal aggregation is jammer×JSR across seed×target-position, with position robustness retained separately. The corrected run contains 24,000 per-trial rows, 96 jammer×JSR aggregate rows, and 480 position rows. It has zero interface failures, zero dispatch mismatches, zero target-erased fair rows, and fallback ratio `0.495375`.

For both target jammers, only one JSR condition passed the target-jammer criterion:

- `NoiseProductJamming`: passing JSR count `1`;
- `NoiseConvolutionJamming`: passing JSR count `1`.

The required two distinct JSR conditions were therefore not met. Identity, legacy Oracle, and fair candidate rows remain separately labeled; no fair candidate was promoted from this rejection-confirmation run.

## 5. Final decision and eligibility

The only permitted conclusion is `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`.

- legacy `adapt_filter`: Oracle upper bound only;
- fair prototype: `REJECTED_EXPERIMENTAL`;
- `rl_eligible=false`;
- `candidate_matrix_eligible=false`;
- `fair_registered=false`;
- `rl_action_space_modified=false`;
- fallback remains Identity;
- no long training was started and Task 037 was not started.

`FAIR_CANDIDATE` is not an allowed conclusion for this run. A conditional research-only conclusion is also unnecessary because the corrected evidence confirms the Oracle-only status.

## 6. Regression and reproducibility

Stage D saved stdout/stderr and summaries under `results/phase1/task036_fix2/stageD/`:

- `validate_algorithms.py`: exit `0`, interface PASS `800`, FAIL `0`;
- `run_correctness_tests.py`: exit `0`, loader `10`, adapter `10`, no-jammer `10`, failures `0`;
- rerunning dedup after held-out was correctly blocked with exit `1`;
- legacy algorithm hash remained unchanged.

Each stage has an independent report, result directory, stdout, stderr, manifest entry, and commit:

- Stage A: `1f69bcb` / `8151b05`, audit and record;
- Stage B: `29c143c` / `2aba817`, dispatch, deduplication, and calibration;
- Stage C: `00ad699` / `2dc3df1`, corrected held-out and record;
- Stage D: `a416f34` / `PENDING_RECORD_COMMIT`, finalization and record.

## 7. Git and remote status

The historical Task 036-fix state is recorded as manually synchronized at local/tracking head `cb7eac7a9e544b6785e1c7bd117e48a99012b59f`; its earlier automatic push rejection and verification evidence remain preserved. Direct SSH remote verification is unavailable under the current tenant policy, so the tracking ref and manual-sync record are reported explicitly rather than treated as a new live remote probe.

Task 036-fix2 finalization and record commits are complete: `a416f34` and `a6b12f6`. The single push attempt was issued from commit `a6b12f67e4f263a9905da8c5143ac0387594757a` and rejected by tenant security policy before execution. Direct `git ls-remote` verification also failed with `ssh: connect to host github.com port 22: Operation not permitted`; therefore fix2 is explicitly `PUSH_BLOCKED_BY_POLICY`, no remote SHA is claimed, and the later local status-closure commit is `04c4eb8`. Raw evidence is saved under `results/phase1/task036_fix2/`. Task 037 was not started.
