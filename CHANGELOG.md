# Changelog

## v0.3.23 — Per-signal diagnostics

- Enforced per-file envelope detection workflow: each waveform is detected independently before overlay plotting.
- Simplified `N picos após maior pico`: selects the first N upper-crest candidates after the forced-resonance anchor for each individual signal.
- Added an expanded diagnostic table showing, per file, the forced anchor time/amplitude and selected peak times/amplitudes.
- Bumped internal state/cache keys to avoid stale automatic selections from previous versions.
- Preserved multi-file overlay, image-click selection, color standardization, and independent tab state.
