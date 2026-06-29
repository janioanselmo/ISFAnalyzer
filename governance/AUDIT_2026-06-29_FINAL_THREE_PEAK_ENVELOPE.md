# Audit — Final Three-Peak Envelope Hotfix

Date: 2026-06-29  
Version: `0.5.2-final-three-peak-envelope`

## User issue

The Envelope tab was selecting the visible final upper crests, but the red fitted envelope was not visually following those selected peaks. The curve could appear above the final selected peaks because the fit used `envelope_amplitude`, which was derived from local peak-to-valley prominence.

## Root cause

`envelope_amplitude` is a diagnostic amplitude estimate for the oscillation lobe. It can be useful for numerical interpretation of ringing, but it is not necessarily the same coordinate as the waveform y-axis. Drawing the exponential fit from that quantity over the waveform caused the red line to be inconsistent with the selected peak markers.

## Decision

For the visible Envelope workflow, the fitted exponential must use the selected upper-crest coordinates themselves:

```text
fit_amplitude = selected peak amplitude, when positive
fallback      = absolute selected peak amplitude, only if needed
zero crest    = small near-zero floor only to keep exponential log-fit valid
```

The default automatic workflow now uses the final three upper crests of the signal:

```text
Picos por curva = 3
Critério        = Últimos N picos
```

## Validation with uploaded dataset

Validation case: `Resultados.zip`, `1 Pulso (Primeiro)/T0000CH1.ISF`, window `-100 µs` to `500 µs`.

Detected upper crest candidates:

```text
18.699 µs   500 V
91.949 µs   720 V
165.429 µs  820 V
238.894 µs  820 V
312.807 µs  280 V
385.795 µs   40 V
```

Selected final three peaks:

```text
238.894 µs  820 V
312.807 µs  280 V
385.795 µs   40 V
```

The fit now uses:

```text
fit_amplitude = 820 V, 280 V, 40 V
```

not the local prominence-derived values.

## Files changed

- `ensaisf/domain/envelope_analysis.py`
- `ensaisf/presentation/pages/envelope_page.py`
- `ensaisf/presentation/theme.py`
- `governance/CHANGELOG.md`
- `governance/AUDIT_2026-06-29_FINAL_THREE_PEAK_ENVELOPE.md`


## Broader check

A scripted check was run against the first 14 `CH1` acquisitions in each folder of the uploaded `Resultados.zip` dataset, totaling 28 voltage waveforms after the project standardization rule. For each waveform, the automatic default selected 3 final candidate peaks and produced 3 positive fit amplitudes.

One waveform had a final crest quantized at exactly zero; this is now kept in the selected set and internally represented with a small near-zero floor only for the exponential logarithm, instead of being silently dropped from the fit.
