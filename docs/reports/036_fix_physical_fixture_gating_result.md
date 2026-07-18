# Task 036-fix Final Result — Physical Fixture, Effective Gating, and Status Closure

Date: 2026-07-18  
Finalize commit: `c1c7c68` (`phase1-036-fix-finalize`)  
Status: `COMPLETED_LOCAL_PUSH_PENDING`  
Decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`

## 1. Why the old fixture was not physically consistent

The earlier multi-position experiment zero-filled and translated the entire received record. That moves and truncates the target, jammer, and noise together, changing component energy, noise realization, and edge support at the same time. It is retained only as `WHOLE_RECORD_TRANSLATION_STRESS`, not as formal target-distance robustness evidence.

## 2. Formal fixture construction

The new fixture generates separate target, jammer, and noise components for each `jammer × JSR × seed`. For every target center it embeds the template at the requested center, applies the jammer-specific position rule, reuses the same noise realization, and recomposes `received = target + jammer + noise`. Safe centers are `1000, 1500, 2500, 3500, 4000`; target support is checked for no truncation. Stage B produced 800 validation rows: 700 jammer rows `PASS`, 100 NoJammer rows `NO_JAMMER_NOT_APPLICABLE`, and 0 failures.

## 3. Jammer position rules

The policy is derived from the active component-generation code and is recorded in `stageB/jammer_position_policy.csv`:

- `NoiseProductJamming` and `NoiseConvolutionJamming`: `TARGET_COUPLED_COMPONENT_SHIFT`; the jammer component is rebuilt at the moved target position.
- `AMNoiseGaiJam`, `FMNoiseAimedJam`, `FMNoiseSaopin`, `SMSP`, and `FMZuse`: `TARGET_INDEPENDENT_COMPONENT_FIXED`; the same jammer realization is reused across target positions.
- `NoJammer`: target plus the fixed noise realization, with no jammer component.

Target energy, noise energy, target-independent jammer energy, measured/requested JSR, finite values, shapes, and target support passed the fixture checks. Same-seed positions reuse the same noise realization.

## 4. Why the old confidence definition failed

The old `peak_confidence = response[best] / max(response)` normalizes the selected maximum by itself. It is therefore approximately one by construction and cannot distinguish a credible target peak from a false or ambiguous peak. The old low thresholds consequently provided ineffective gating.

## 5. Effective confidence and Identity gating

The fair prototype now combines five fixed, observable, unit-interval components: peak-to-background ratio, top-1/top-2 margin, peak prominence, peak-width consistency against the known template autocorrelation, and local-to-global energy ratio. Fixed weights are `0.25, 0.25, 0.20, 0.15, 0.15`; the threshold is `0.80`. Gating returns Identity for low confidence, missing candidates, invalid edge proximity, abnormal condition number, or a non-finite/too-small output proxy. No evaluation truth or target-erased metric enters fitting.

Stage C covered clean target, NoJammer, low/mid/high JSR, false-peak-dominant, ambiguous, and pure-noise cases. It had 16 trials, interface failures `0`, all component values in `[0,1]`, and fallback ratio `8/16 = 0.5`, proving fallback is neither always off nor always on. The false-peak-dominant case remains an intentionally documented high-confidence wrong-observable case; gating is a confidence mechanism, not an oracle truth detector.

## 6. Candidate deduplication and calibration

The nominal matrix contained `8` candidates. Diagnostic behavior signatures reduced this to `4` effective candidates. Calibration used seeds `9000..9019`, JSR `0/10/20/30`, Stage B physical positions, and target/negative controls. It produced 9,600 trial rows and 96 candidate×jammer×JSR aggregates after aggregation across seed×position. No candidate met the preregistered qualification gates. The frozen representative `B_k3_c0.8_r0.001` is a rejection-confirmation representative, not a selected candidate.

## 7. Independent held-out aggregation and comparison

Held-out used new seeds `9100..9149`, the same physical positions, target jammers `NoiseProductJamming` and `NoiseConvolutionJamming`, negative controls `NoJammer`, `AMNoiseGaiJam`, `FMNoiseAimedJam`, `FMNoiseSaopin`, `SMSP`, and `FMZuse`, and JSR `0/10/20/30`. Formal qualification was evaluated per `jammer × JSR` after pooling `seed × target_position`; position rows were retained only for robustness analysis. The run contains 24,000 trial rows and 96 aggregate rows.

The frozen fair representative had held-out fallback ratio `0.490125`, interface failures `0`, and fair target-erased rows `0`. For both target jammers, only JSR 10 passed the target-jammer condition; JSR 20 and 30 fell back to Identity with zero improvement and zero Pd in this rejection-confirmation run. Identity and the legacy true-target-index implementation remain comparison baselines; the legacy implementation is explicitly Oracle-only and is not a fair candidate.

## 8. Final eligibility and retained conclusions

Final decision: `ORACLE_UPPER_BOUND_ONLY_CONFIRMED`.

- legacy `adapt_filter`: `ORACLE_UPPER_BOUND_ONLY`, `BLOCKED_ORACLE`;
- fair prototype: `REJECTED_EXPERIMENTAL`;
- `rl_eligible=false`;
- `candidate_matrix_eligible=false`;
- `fair_registered=false`;
- `rl_action_space_modified=false`;
- fallback remains `Identity`;
- no RL training was started and Task 037 was not started.

The original Task 036 Oracle conclusion is retained. The corrected findings are that formal position evidence must use component recomposition, calibration candidates must be deduplicated by behavior, and held-out qualification must count distinct JSR conditions rather than position rows.

## 9. Regression and remote status

Regression results are saved under `results/phase1/task036_fix/stageF/`: `validate_algorithms.py` exited `0` with interface PASS `800/800`, and `run_correctness_tests.py` exited `0` with failures `0`. The legacy `anti_jamming/adapt_filter.py` hash remains the Stage A baseline hash.

The historical Task 036 status is corrected to `COMPLETED_REMOTE_SYNCED`, with `previous_push_attempt=BLOCKED_BY_TENANT_SECURITY_POLICY` and `later_manual_push=true`; the old failure evidence remains intact. The new Task 036-fix commits are currently `PENDING_FINAL_PUSH` and must be verified by matching local and remote SHA before this status becomes complete.
