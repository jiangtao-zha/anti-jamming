# Stage 1 mathematical audit

Let `r ∈ C^(M×N_r)` be `Srt_temp` and let `u ∈ C^(1×N_s)` be `St1`. In the Phase 1 baseline, `M=1`, `N_r=5000`, and `N_s=1000`.

When `N_s != N_r`, the implementation creates a zero-padded vector `s ∈ C^(1×N_r)`. Its nonzero interval begins at

```text
offset = max(0, target_idx - floor(N_s/2))
```

and ends at `offset + N_s` subject to clipping. Thus `target_idx` determines the delay alignment of the known pulse template.

The core then computes:

```text
sᴴ = conjugate_transpose(s)
q = s sᴴ = ||s||²
α = 1 / (q + par1)
P_s = sᴴ α s
y = r P_s
```

For `par1=0`, `P_s` is the Hermitian rank-one projector onto the span of `s`; for positive `par1` it is a scaled rank-one projector. The output for each pulse is equivalently

```text
y_i = (r_i sᴴ)/(||s||² + par1) · s.
```

This is not a learned interference covariance filter. It suppresses every component orthogonal to the aligned template and retains the component parallel to the template. The actual code materializes an `N_r × N_r` matrix at lines 46-50; the memory-saving equivalent at lines 53-58 is commented out and is not the active implementation.

`par2` is accepted for interface compatibility but does not enter the expression. No jammer statistics, secondary training cells, adaptive covariance, target-preservation constraint, or output gating is present.

## Consequences

1. With the true Phase 1 index 1500, the 1000-sample template is placed at indices 1000..1999, matching the generated target pulse.
2. With the fair whitelist and adapter fallback index 0, the template is placed at indices 0..999 and the generated target is outside the retained subspace.
3. A location estimate could make a *new* observable algorithm, but simply deleting the truth from this implementation does not preserve the same method's intended behavior.
4. The current method has no theory that identifies the target location from `Srt_matrix`; its only location mechanism is the supplied index/default.
