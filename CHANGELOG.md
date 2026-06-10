# Changelog

## v0.2.2 - Envelope analysis

Suggested commit:

```text
Add selectable exponential ringdown envelope analysis
```

### Added

- Mouse selection of ringdown peaks using Plotly box/lasso selection.
- Exponential envelope fitting from selected peaks.
- Automatic fallback to the last N detected peaks when no manual selection is made.
- Envelope comparison across multiple loaded ISF files.
- Normalized envelope overlay for before/after electroporation comparisons.
- CSV export for envelope metrics.

### Changed

- Reduced redundancy in the signal analysis screen.
- Merged single-signal and multi-signal visualization into **Visão geral / formas de onda**.
- Kept only four operations inside the main analysis tab:
  - Visão geral / formas de onda
  - Ressonância e envoltória
  - Antes × depois
  - V × I / potência

### Notes

- The envelope fit uses `|V_peak| = A0 * exp(-(t - t0) / tau)`.
- `tau_us` and decay-per-cycle are exploratory resonance markers and should be interpreted together with repeatability, sample geometry, conductivity and electrode contact.
