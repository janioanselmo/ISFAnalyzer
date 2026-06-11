# ISF Analyzer v0.3.16 - Robust Peak Detection Audit

## Scope
This version focuses only on the Envelope peak-selection algorithm.

## Changes checked
- Python compilation passed for `app.py` and `ensaisf/*.py`.
- The full waveform remains visible in Envelope.
- Only dominant positive maxima are marked as clickable candidates.
- Automatic selection with `Últimos N picos` now uses an adaptive dominance filter before selecting the last peaks.
- The candidate pool is larger, but filtered, reducing sensitivity to tiny late ripples and noise when several files are overlaid.

## Notes
The Streamlit visual workflow must still be validated in the user's local environment.
