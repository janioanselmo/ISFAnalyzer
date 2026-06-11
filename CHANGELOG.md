# Changelog

## v0.3.24 — Validated Ringdown Tracker

- Added a per-signal period-tracked ringdown detector validated with real uploaded ISF files.
- The detector now finds the largest forced-resonance crest per waveform and tracks the next natural crests using the estimated crest-to-crest period.
- Detection is performed before overlay plotting, avoiding cross-curve confusion in multi-file Envelope mode.
- Added boundary rejection to avoid false peaks at the right edge of the ringing window.
- Added `envelope_amplitude` and `fit_amplitude` handling so late crests below the zero axis can still be used more physically in the exponential fit.
- Expanded the diagnostics table with estimated period information.
- Added `PEAK_DETECTION_VALIDATION.csv` and `VALIDATION_RINGDOWN.md`.

## v0.3.23 — Per-signal Diagnostics

- Added explicit per-signal envelope detection diagnostics.
- Reinforced independent per-file detection before overlay plotting.
