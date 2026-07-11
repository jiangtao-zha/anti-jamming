# Phase 1 Blocked Issues

## Task 033：adapt_filter oracle dependency

`validate_evaluation.py` deliberately does not put `target_idx`, `jam_info`,
or the true jammer signal into the algorithm `radar_par`. However,
`anti_jamming/adapters.py:adapt_filter_adapter` still constructs an adapted
parameter dictionary with `target_idx=radar_par.get('target_idx', 0)`, and the
core `anti_jamming/adapt_filter.py` uses that value to align its projection
template.

Therefore:

- the evaluation matrix records `adapt_filter` execution results;
- `adapt_filter` is marked `blocked_for_fair_comparison` in
  `results/phase1/evaluation/oracle_check.csv`;
- its matrix performance must not be interpreted as a fair no-oracle result;
- this task does not modify `adapt_filter`, in accordance with the task
  boundary.
