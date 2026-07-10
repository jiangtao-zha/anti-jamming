# High JSR Evaluation Summary

- JSR: 20 dB
- Trials per combination: 1
- Base seed: 42
- Baseline: Pw=20us, Fs=50MHz, target_idx=1500, M=1

| JSR | Jammer | Algorithm | SINR before | SINR after | Improvement | Detect before | Detect after | Errors |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 20 | ISDJ | WLN | 9.669 | 10.436 | 0.767 | 1.000 | 1.000 | 0 |
| 20 | ISDJ | FrequencyDomainCanceller | 9.669 | 7.891 | -1.778 | 1.000 | 0.000 | 0 |
| 20 | ISDJ | adapt_filter | 9.669 | 11.462 | 1.794 | 1.000 | 1.000 | 0 |
| 20 | ISDJ | frft_filter | 9.669 | 9.846 | 0.177 | 1.000 | 1.000 | 0 |
| 20 | ISDJ | qpzh | 9.669 | 9.666 | -0.003 | 1.000 | 1.000 | 0 |
| 20 | ISDJ | FastSlowTimeProcessor | 9.669 | 9.646 | -0.022 | 1.000 | 1.000 | 0 |
| 20 | ISDJ | wave_agile | 9.669 | 9.694 | 0.025 | 1.000 | 1.000 | 0 |
| 20 | ISDJ | Frequency_agile | 9.669 | 6.810 | -2.858 | 1.000 | 0.000 | 0 |
| 20 | SMSP | WLN | 7.647 | 7.784 | 0.137 | 0.000 | 0.000 | 0 |
| 20 | SMSP | FrequencyDomainCanceller | 7.647 | 9.622 | 1.976 | 0.000 | 1.000 | 0 |
| 20 | SMSP | adapt_filter | 7.647 | 11.462 | 3.816 | 0.000 | 1.000 | 0 |
| 20 | SMSP | frft_filter | 7.647 | 7.966 | 0.319 | 0.000 | 0.000 | 0 |
| 20 | SMSP | qpzh | 7.647 | 7.648 | 0.001 | 0.000 | 0.000 | 0 |
| 20 | SMSP | FastSlowTimeProcessor | 7.647 | 7.626 | -0.021 | 0.000 | 0.000 | 0 |
| 20 | SMSP | wave_agile | 7.647 | 7.647 | -0.000 | 0.000 | 0.000 | 0 |
| 20 | SMSP | Frequency_agile | 7.647 | 7.891 | 0.244 | 0.000 | 0.000 | 0 |
| 20 | RGPO | WLN | 11.200 | 10.814 | -0.386 | 1.000 | 1.000 | 0 |
| 20 | RGPO | FrequencyDomainCanceller | 11.200 | 11.106 | -0.094 | 1.000 | 1.000 | 0 |
| 20 | RGPO | adapt_filter | 11.200 | 11.462 | 0.262 | 1.000 | 1.000 | 0 |
| 20 | RGPO | frft_filter | 11.200 | 11.179 | -0.021 | 1.000 | 1.000 | 0 |
| 20 | RGPO | qpzh | 11.200 | 11.198 | -0.002 | 1.000 | 1.000 | 0 |
| 20 | RGPO | FastSlowTimeProcessor | 11.200 | 11.182 | -0.018 | 1.000 | 1.000 | 0 |
| 20 | RGPO | wave_agile | 11.200 | 11.532 | 0.332 | 1.000 | 1.000 | 0 |
| 20 | RGPO | Frequency_agile | 11.200 | 11.187 | -0.013 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | WLN | 10.942 | 10.507 | -0.435 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | FrequencyDomainCanceller | 10.942 | 10.831 | -0.111 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | adapt_filter | 10.942 | 11.462 | 0.521 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | frft_filter | 10.942 | 10.826 | -0.116 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | qpzh | 10.942 | 10.956 | 0.014 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | FastSlowTimeProcessor | 10.942 | 10.912 | -0.030 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | wave_agile | 10.942 | 11.059 | 0.117 | 1.000 | 1.000 | 0 |
| 20 | FMZuse | Frequency_agile | 10.942 | 10.870 | -0.072 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | WLN | 8.823 | 9.367 | 0.544 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | FrequencyDomainCanceller | 8.823 | 9.162 | 0.339 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | adapt_filter | 8.823 | 11.462 | 2.640 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | frft_filter | 8.823 | 9.261 | 0.438 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | qpzh | 8.823 | 8.800 | -0.023 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | FastSlowTimeProcessor | 8.823 | 8.747 | -0.076 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | wave_agile | 8.823 | 8.970 | 0.147 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseAimedJam | Frequency_agile | 8.823 | 9.564 | 0.741 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | WLN | 9.563 | 10.118 | 0.555 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | FrequencyDomainCanceller | 9.563 | 10.586 | 1.023 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | adapt_filter | 9.563 | 11.462 | 1.899 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | frft_filter | 9.563 | 9.237 | -0.326 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | qpzh | 9.563 | 9.541 | -0.022 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | FastSlowTimeProcessor | 9.563 | 9.534 | -0.029 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | wave_agile | 9.563 | 9.626 | 0.063 | 1.000 | 1.000 | 0 |
| 20 | AMNoiseGaiJam | Frequency_agile | 9.563 | 10.103 | 0.540 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | WLN | 11.449 | 11.429 | -0.020 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | FrequencyDomainCanceller | 11.449 | 10.745 | -0.704 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | adapt_filter | 11.449 | 11.462 | 0.014 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | frft_filter | 11.449 | 11.373 | -0.076 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | qpzh | 11.449 | 11.448 | -0.001 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | FastSlowTimeProcessor | 11.449 | 11.412 | -0.037 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | wave_agile | 11.449 | 11.768 | 0.320 | 1.000 | 1.000 | 0 |
| 20 | FMNoiseSaopin | Frequency_agile | 11.449 | 11.279 | -0.170 | 1.000 | 1.000 | 0 |
| 20 | NoiseProductJamming | WLN | 6.155 | 8.059 | 1.904 | 0.000 | 0.000 | 0 |
| 20 | NoiseProductJamming | FrequencyDomainCanceller | 6.155 | 6.579 | 0.424 | 0.000 | 0.000 | 0 |
| 20 | NoiseProductJamming | adapt_filter | 6.155 | 11.462 | 5.308 | 0.000 | 1.000 | 0 |
| 20 | NoiseProductJamming | frft_filter | 6.155 | 6.676 | 0.522 | 0.000 | 0.000 | 0 |
| 20 | NoiseProductJamming | qpzh | 6.155 | 6.147 | -0.008 | 0.000 | 0.000 | 0 |
| 20 | NoiseProductJamming | FastSlowTimeProcessor | 6.155 | 6.000 | -0.154 | 0.000 | 0.000 | 0 |
| 20 | NoiseProductJamming | wave_agile | 6.155 | 6.158 | 0.003 | 0.000 | 0.000 | 0 |
| 20 | NoiseProductJamming | Frequency_agile | 6.155 | 6.840 | 0.686 | 0.000 | 0.000 | 0 |
| 20 | NoiseConvolutionJamming | WLN | 8.933 | 8.825 | -0.108 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | FrequencyDomainCanceller | 8.933 | 9.142 | 0.209 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | adapt_filter | 8.933 | 11.462 | 2.529 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | frft_filter | 8.933 | 9.600 | 0.667 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | qpzh | 8.933 | 8.937 | 0.004 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | FastSlowTimeProcessor | 8.933 | 8.923 | -0.010 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | wave_agile | 8.933 | 8.933 | 0.000 | 1.000 | 1.000 | 0 |
| 20 | NoiseConvolutionJamming | Frequency_agile | 8.933 | 9.524 | 0.591 | 1.000 | 1.000 | 0 |
