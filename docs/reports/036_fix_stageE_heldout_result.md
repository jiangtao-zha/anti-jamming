# Task 036-fix Stage E — Independent Held-out Rejection Confirmation

Date: 2026-07-18  
Status: `COMPLETED`  
Result commit: pending

## Scope

Stage E evaluated the frozen Stage D rejection-confirmation representative `B_k3_c0.8_r0.001`. No candidate was selected by calibration, so this run remained `REJECTION_CONFIRMATION_ONLY`; no post-held-out tuning was performed.

The held-out fixture used the Stage B physical component-recomposition path, with target centers `1000, 1500, 2500, 3500, 4000`, independent component rules, and new seeds `9100..9149`. The formal aggregation is by `jammer × JSR`, across `seed × target_position`. Position-level rows were retained only for robustness inspection.

## Comparators and results

Each trial records Identity, the legacy true-target-index Oracle upper bound, and the frozen observable-only fair representative. The run contains 24,000 trial rows, 96 jammer×role×JSR aggregate rows, and 480 position rows. Interface failures are `0`; fair target-erased rows are `0`.

For the target jammers, the frozen fair representative produced the following formal aggregates:

| Jammer | JSR | Delta SINR mean (dB) | 95% CI half-width (dB) | Pd mean | Fallback | Position spread (dB) |
|---|---:|---:|---:|---:|---:|---:|
| NoiseProductJamming | 0 | 12.276 | 0.074 | 1.000 | 0.000 | 0.023 |
| NoiseProductJamming | 10 | 16.906 | 1.073 | 0.808 | 0.204 | 0.911 |
| NoiseProductJamming | 20 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| NoiseProductJamming | 30 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| NoiseConvolutionJamming | 0 | 13.389 | 0.065 | 1.000 | 0.000 | 0.034 |
| NoiseConvolutionJamming | 10 | 9.033 | 1.333 | 0.520 | 0.584 | 0.915 |
| NoiseConvolutionJamming | 20 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| NoiseConvolutionJamming | 30 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |

The zero Delta SINR and zero Pd at high JSR reflect the frozen fair prototype falling back to Identity in those conditions; this is a failure to establish a stable useful operating region, not evidence of candidate eligibility.

## Decision

`ORACLE_UPPER_BOUND_ONLY_CONFIRMED`.

Both target jammers have only one passing JSR condition among `10/20/30`, while the requirement is at least two distinct JSR conditions after aggregation over seed and physical target position. The fair prototype remains rejected experimental work. The legacy `adapt_filter` conclusion remains `ORACLE_UPPER_BOUND_ONLY`.

The following remain false and unchanged: `rl_eligible`, `candidate_matrix_eligible`, `fair_registered`, and `rl_action_space_modified`. The frozen fair representative is not registered as a candidate and must not enter RL evaluation.

Evidence: `results/phase1/task036_fix/stageE/`, including `final_decision.json`, `aggregate_by_jammer_jsr.csv`, `position_robustness.csv`, `fallback_analysis.csv`, and `oracle_comparison.csv`.
