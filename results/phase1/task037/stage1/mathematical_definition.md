# Task 037 Stage 1 — FrFT mathematical definition

The audited implementation is `anti_jamming.frft_filter.myfrft`.  It uses a
finite-dimensional spectral fractional power of the centered orthonormal DFT
`U`, not the former chirp-convolution translation.  The order-angle relation
is `theta = pi*a/2`; orders are reduced modulo 4.

For this finite grid, `a=0` is identity, `a=1` is the centered unitary DFT,
`a=2` is `U^2` (the finite-grid circular/centered reversal), `a=3` is
`U^3`, and `a=4` is identity.  The implementation constructs the four
projectors of `U` and applies the eigenphase `exp(-j*pi*k*a/2)` to each.
This makes the convention explicit without claiming a continuously scaled
Ozaktas LFM focusing order.

## Numerical audit

- Maximum inverse relative error: `8.705e-16`
- Maximum period-4 relative error: `9.891e-16`
- Maximum energy error: `1.110e-15`
- Edge cases: `5/5 PASS`
- Chirp validation: the numeric scan is reported, but a continuous theoretical
  order is `NOT_IDENTIFIABLE_WITHOUT_CONTINUOUS_SCALING` under this discrete
  spectral convention.  No order is silently treated as ground truth.
- Oracle/input audit: `PASS`

The old implementation's chirp-convolution index/shift convention failed the
same energy and inverse tests in the Stage 1 pre-fix baseline.  The core fix is
limited to `myfrft`; mask calibration and candidate dispatch are not changed
in this stage.

The periodic distance used by later diagnostics is
`d4(a,b) = min_k |a-b+4k|`, with the search interval documented per result.
