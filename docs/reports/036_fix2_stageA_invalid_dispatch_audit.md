# Task 036-fix2 Stage A — Invalid Frozen Candidate Dispatch Audit

Status: `COMPLETED`  
Result commit: `1f69bcb` (`phase1-036-fix2-stageA-audit-invalid-dispatch`)

## Frozen evidence

The current Task 036-fix result is preserved under `results/phase1/task036_fix/`. The frozen Stage D rejection-confirmation candidate is `B_k3_c0.8_r0.001`, with `design=B`. Its source file hash and the old Stage E result hashes are recorded in `results/phase1/task036_fix2/stageA/file_hashes.txt`.

## Invalid dispatch

The old Stage E implementation directly called `fit_adapt_filter_fair(...)`, which is the A design. It did not dispatch from the frozen candidate's `design` field and therefore executed A while claiming to evaluate frozen B. The expected B function is `fit_adapt_filter_fair_multihypothesis(...)`. This is recorded as:

```text
old_stageE_status = INVALID_FROZEN_CANDIDATE_DISPATCH
Stage D froze design B
Stage E executed design A
```

The old held-out results are historical evidence only and are not used for Task 036-fix2 qualification.

## Behavior-signature audit

The old Stage D signature payload also included `fit_status` and serialized `gate_reasons`. Those fields contain implementation/status metadata and can differ across A/B even when estimated index, fallback, confidence, and processed output are identical. Task 036-fix2 will remove those metadata fields from equivalence identity and retain them only as diagnostics.

## Baseline and preservation

Branch: `algorithm_design_0711`  
HEAD: `cb7eac7a9e544b6785e1c7bd117e48a99012b59f`  
Tracking ref: `cb7eac7a9e544b6785e1c7bd117e48a99012b59f`  
The direct remote query is unavailable because SSH access is blocked by policy; no push is performed in Stage A. Legacy `adapt_filter` remains `ORACLE_UPPER_BOUND_ONLY`, and the prior Task 036-fix push-failure evidence is retained.
