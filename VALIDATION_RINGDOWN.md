# ISF Analyzer v0.3.24 — Ringdown detector validation

## Dataset used

Validation was performed with the real uploaded Tektronix ISF files:

- T0000CH1.ISF
- T0001CH1.ISF
- T0002CH1.ISF
- T0003CH1.ISF
- T0004CH1.ISF
- T0005CH1.ISF
- T0006CH1.ISF

## Standard test configuration

- Ringing window: -100 µs to 500 µs
- Peak threshold: 5%
- Minimum distance: 5 µs
- Selection mode: N peaks after largest peak
- Automatic N used for validation: 4

## Main correction

The detector no longer tries to select the last visible local maxima directly from the overlaid plot. It now processes each waveform independently before overlaying:

1. Baseline correction per signal.
2. Smoothing and decimation only for robust crest localization.
3. Broad upper-crest detection.
4. Forced-resonance anchor = largest upper crest of that individual signal.
5. Crest-to-crest period estimation from strong crests before/at the anchor.
6. Natural ringdown tracking at anchor + kT.
7. Boundary rejection near the right edge of the analysis window.
8. Overlay plotting only after per-signal detection is complete.

The algorithm deliberately returns fewer than N peaks when the waveform does not contain enough complete natural crests after the largest peak within the selected window. This avoids falsely selecting valleys, tail baseline drift, or the window boundary.

## Validation output

See `PEAK_DETECTION_VALIDATION.csv` for the detailed per-file anchor, estimated period, selected peak times, and selected peak amplitudes.
