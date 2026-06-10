# Changelog

## v0.2.1 — Signal analysis tabs

- Reduced top-level interface to three tabs: Signal Analysis, Export, and Header.
- Moved single-signal, multi-signal, ringdown, before-after, and V-I/power tools into a single Signal Analysis operation selector.
- Updated widget keys to avoid Streamlit duplicate element IDs after the UI consolidation.

## v0.2.0-resonance

Suggested commit name:

```text
Add resonance ringdown and before-after waveform analysis
```

### Added

- Dedicated resonance/ringdown tab.
- Manual ringdown analysis window in microseconds.
- Positive/negative peak detection.
- Ringdown period estimated from same-polarity peaks, alternating extrema and zero crossings.
- Damped frequency and estimated natural frequency.
- Logarithmic decrement, damping ratio, Q factor and envelope decay time constant.
- Envelope fit R².
- Ringdown energy and decay per cycle.
- Before/after comparison tab for electroporation experiments.
- Percent deltas for period, frequency, tau, Q and ringdown energy.
- Waveform similarity metrics: Pearson correlation, NRMSE, MAE, max difference and cross-correlation delay.
- Exploratory resonance_shift_score.
- Extended V-I analysis with charge, effective resistance and FFT impedance estimate.

### Fixed/Kept

- Unique Streamlit keys for Plotly charts.
- NumPy trapezoidal integration compatibility.
