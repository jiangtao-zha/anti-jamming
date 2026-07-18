# Task 036-fix2 Stage C — Corrected Independent Held-out Result

Status: `COMPLETED`  
Result commit: pending  
Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`

## Frozen candidate and dispatch

Stage B froze the canonical representative `A_k3_c0.8_r0.001`, selected from an equivalence class whose members include both A and B implementations with identical diagnostic behavior. Stage C loaded only `results/phase1/task036_fix2/stageB/selected_candidate.json`, verified its SHA256, and dispatched it through the shared function:

```text
candidate_design = A
fit_function_name = fit_adapt_filter_fair
dispatch_status = PASS
dispatch_mismatch_count = 0
```

The old Task 036-fix Stage E results using seeds `9100..9149` remain `INVALID_DISPATCH_HISTORICAL_EVIDENCE`; they are not used for this decision. The corrected held-out uses new seeds `9200..9249`.

## Experiment and aggregation

The physical component-recomposition fixture and safe target centers `1000, 1500, 2500, 3500, 4000` are unchanged from Task 036-fix. The run compares Identity, the legacy true-target-index Oracle upper bound, and the frozen fair representative across the two target jammers, six negative controls, and JSR `0/10/20/30`. Formal qualification is aggregated by `jammer × JSR` across `seed × target_position`; position rows are retained only for robustness inspection.

The run contains 24,000 per-trial rows, 96 aggregate rows, and 480 position rows. Interface failures are `0`, dispatch mismatches are `0`, and fair target-erased rows are `0`. The fallback ratio is `0.495375`.

## Target-jammer results

| Jammer | JSR | Delta SINR mean (dB) | 95% CI half-width (dB) | Pd mean | Fallback | Position spread (dB) |
|---|---:|---:|---:|---:|---:|---:|
| NoiseProductJamming | 0 | 12.196 | 0.090 | 1.000 | 0.000 | 0.045 |
| NoiseProductJamming | 10 | 15.257 | 1.148 | 0.736 | 0.264 | 0.476 |
| NoiseProductJamming | 20 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| NoiseProductJamming | 30 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| NoiseConvolutionJamming | 0 | 13.283 | 0.082 | 1.000 | 0.000 | 0.029 |
| NoiseConvolutionJamming | 10 | 8.214 | 1.275 | 0.540 | 0.608 | 0.869 |
| NoiseConvolutionJamming | 20 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| NoiseConvolutionJamming | 30 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |

At JSR 20 and 30 the frozen fair representative falls back to Identity in this rejection-confirmation run; that does not establish a useful fair operating region. Each target jammer has only one passing condition among JSR `10/20/30`, below the required two distinct conditions.

## Decision and eligibility

The corrected evidence confirms `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`. The legacy implementation remains `ORACLE_UPPER_BOUND_ONLY` and is comparison-only. The fair prototype remains rejected experimental work. `rl_eligible=false`, `candidate_matrix_eligible=false`, `fair_registered=false`, and `rl_action_space_modified=false`. No post-held-out candidate selection or tuning occurred; the runner writes a held-out lock containing the frozen candidate hash.

Evidence: `results/phase1/task036_fix2/stageC/`, including `heldout_metadata.json`, `per_trial_results.csv`, `aggregate_by_jammer_jsr.csv`, `position_robustness.csv`, `fallback_analysis.csv`, `oracle_comparison.csv`, `dispatch_validation.csv`, `final_decision.json`, `summary.json`, `stdout.txt`, and `stderr.txt`.
