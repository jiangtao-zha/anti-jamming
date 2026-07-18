# Task 036-fix2 Stage B — Dispatch and Behavior Deduplication

Status: `COMPLETED`  
Result commit: pending

## Changes

Task 036-fix2 adds the shared `scripts/task036_fix_dispatch.py` entry point. It maps design A to `fit_adapt_filter_fair` and design B to `fit_adapt_filter_fair_multihypothesis`, validates the mapping before and after each fit, and records candidate ID, design, fit function, parameters, and dispatch status. A design/function mismatch raises `CandidateDispatchMismatch` and produces a nonzero stage result; the negative mismatch assertion passed.

Stage D and Stage E now use this shared function. No fair algorithm implementation, confidence formula, fixture, JSR contract, evaluation metric, or RL file was changed.

## Behavior identity

The behavior signature hash is based only on the fixed diagnostic bank's actual outputs:

```text
estimated_target_idx sequence
fallback sequence
quantized confidence sequence
normalized processed-output hash sequence
```

The signature excludes `candidate_id`, design name, fit function name, `fit_status`, `gate_reasons`, and algorithm/report metadata. Those fields remain available in diagnostic/dispatch CSVs but cannot split equivalence classes.

Canonical representative priority is deterministic:

```text
design A → smaller top_k → higher threshold → smaller regularization → candidate_id
```

## Results

The calibration seeds remain `9000..9019`; this stage changed only dispatch and behavior classification. There are 8 nominal candidates, 2 effective behavior classes, 4,800 calibration trial rows, 48 aggregate rows, and 0 qualified candidates. The frozen rejection-confirmation representative is:

```text
A_k3_c0.8_r0.001
design=A
equivalence_class=EQ_001
members=A_k3_c0.8_r0.001, A_k5_c0.8_r0.001,
        B_k3_c0.8_r0.001, B_k5_c0.8_r0.001
```

The second class is the corresponding threshold-0.65 group. The Stage B gate passed: dispatch mismatches `0`, interface failures `0`, oracle input failures `0`, negative mismatch test `PASS`, and effective count `2 <= 8`.

Evidence: `results/phase1/task036_fix2/stageB/`, especially `dispatch_validation.csv`, `behavior_signatures.csv`, `equivalence_classes.csv`, `effective_candidates.csv`, `candidate_ranking.csv`, `selected_candidate.json`, and `summary.json`.
