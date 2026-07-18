# Task 037 Stage 0 — FrFT Baseline Freeze and Historical State Correction

Date: 2026-07-18
Status: `COMPLETED`
Commit: `PENDING_STAGE0_COMMIT`

## Baseline objects

Identity is frozen as `received → received`. Current FrFT is frozen at `anti_jamming/frft_filter.py:myfrft` and `anti_jamming/adapters.py:frft_adapter`, registered as `frft_filter`. Its default adapter search is `a∈[0.75,1.35]` with 25 evenly spaced orders and `mask_threshold=0.1`; activity-window localization uses the received/template matched-filter peak. The future observable-only candidate is `NOT_IMPLEMENTED` and cannot replace the Current FrFT baseline.

The baseline implementation, adapter, evaluation contract, and current formal matrix were not modified. The current formal matrix contains 160 FrFT interface rows, all `PASS`, with zero oracle-input failures. Existing aggregate evidence records negative FrFT deltas for both `FMNoiseAimedJam` and `FMNoiseSaopin` at most JSR conditions; this is a frozen observation, not a new experiment.

## Historical Task 036-fix2 status

The historical automatic push failure remains preserved. The later manual synchronization is recorded as `COMPLETED_REMOTE_SYNCED` at tracking/remote SHA `7fe8b146fe34b6667061c844bd3e1887e6fe5fa2`. Direct SSH verification remains unavailable under the tenant policy, so the tracking ref plus manual-sync record is explicitly used as the SHA basis.

## Path-only correction

Only the old Task 036-fix2 low-level runner defaults were corrected, without rerunning that task:

- `scripts/task036_fix_stageD.py` defaults to `results/phase1/task036_fix2/stageB`;
- `scripts/task036_fix_stageE.py` defaults to `results/phase1/task036_fix2/stageC`.

No jammer, JSR contract, radar configuration, evaluation metric, FrFT algorithm, RL/PPO, reward, state, or action space was changed. Task 038 was not started.

## Evidence

Baseline metadata, hashes, Git state, historical status, stdout/stderr, and the stage manifest are under `results/phase1/task037/stage0/`. The pre-edit file hashes are recorded in `file_hashes.txt`.

## Next gate

Proceed to Stage 1 only: audit the actual FrFT definition, numerical properties, order periodicity, and Oracle-input boundary. Do not tune a mask in Stage 1.
