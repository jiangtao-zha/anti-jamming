# Stage 1 call graph

```mermaid
flowchart TD
    A[Phase1 radar/jammer generation] --> B[full radar_par]
    B -->|fair contract whitelist| C[observable radar_par: Srt_matrix + St_base + public config]
    B -->|legacy/unified framework and RL| D[full radar_par including target_idx]
    C --> E[get_antijam_func('adapt_filter')]
    D --> E
    E --> F[adapt_filter_adapter]
    F --> G[St1 = St_base; Srt_temp = Srt_matrix]
    G --> H[target_idx = radar_par.get('target_idx', 0)]
    H --> I[pad/shift St1 to full receive window]
    I --> J[rank-one template projection Ps]
    J --> K[processed IQ = Srt_temp @ Ps]
    K --> L[contract/evaluation or RL reward]
```

## Edge semantics

- In the fair contract, `utils.test_contract._whitelist_radar_par` removes `target_idx`, `target_start_idx`, `target_dist`, jammer metadata, signal truth and JSR metadata before calling the adapter.
- The adapter nevertheless inserts `target_idx=0` via `radar_par.get('target_idx', 0)`. This is an implicit fixed-position assumption, not an estimate from IQ.
- In the unified framework and current RL environment, `RadarEnvironment.generate_with_jammer` stores the simulator's `target_idx` in `radar_par`; selecting the current RL action therefore exposes that truth to the adapter.
- The current core does not estimate a covariance or jammer subspace. It aligns the known target template and projects the entire received record onto that one-dimensional template direction.
- `target_idx` used by `UnifiedEvaluator` or the legacy `test_adapt_filter` helper is evaluation truth and must remain outside a fair fit/apply path.
