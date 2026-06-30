# Audit — Peak-through visual envelope

Date: 2026-06-30
Version: 0.5.4-peak-through-envelope

## User requirement

The Envelope tab must detect the maximum crest of each damped sinusoidal lobe and, by default, use the final three selected peaks (`N = 3`, configurable) to plot the envelope.

The visual red envelope must pass through the selected crest maxima. In previous versions, the red line represented a least-squares exponential fit. With real measured data, three experimental peaks are not always perfectly exponential, so the least-squares curve can miss the second or third selected crest even when peak detection is correct.

## Decision

Separate two concepts:

1. **Visual envelope overlay**
   - Drawn through the exact selected crest coordinates.
   - Uses log-linear interpolation between selected positive crest maxima.
   - Falls back to linear interpolation if non-positive crest values are selected.

2. **Statistical exponential fit**
   - Still used for `tau_us`, `r2_envelope`, decay per period, half-life and related metrics.
   - Kept in the numeric summary table and exportable data.

## Files changed

- `ensaisf/domain/envelope_analysis.py`
- `ensaisf/presentation/pages/envelope_page.py`
- `ensaisf/presentation/theme.py`
- `README.md`
- `governance/CHANGELOG.md`

## Validation

- Syntax validation passed with:

```bash
python -m py_compile app.py $(find ensaisf -name '*.py' -type f)
```

- Validation with the uploaded `Resultados.zip` and `1 Pulso (Primeiro)/T0000CH1.ISF` confirmed the selected final three peaks:

```text
239.058 us -> 860.0
310.601 us -> 300.0
382.229 us -> 40.0
```

The generated visual-envelope points include these exact coordinates, so the red line passes through the selected markers.

## Commit message

Fix envelope overlay to pass through selected damped-sinusoid crest maxima
