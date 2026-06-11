# Audit report — ISF Analyzer v0.3.22-ringdown-tracker

## Scope

Focused patch for Envelope peak detection robustness.

## Checks performed

- Python compile check passed for:
  - `app.py`
  - `ensaisf/analysis.py`
  - `ensaisf/isf_parser.py`
- Removed `__pycache__` and `.pyc` files before packaging.

## Algorithm update

The Envelope automatic selection now uses a physics-guided ringdown tracker:

1. baseline is corrected using the existing baseline mode;
2. pre-trigger/noise candidates are suppressed with an adaptive noise floor;
3. only upper crests of resonant cycles are kept as candidates;
4. the dominant forced crest is used as the anchor;
5. the upper-crest period is estimated from dominant crests;
6. the next N natural upper crests are tracked cycle-by-cycle.

This avoids selecting tail ripple or lower valleys as envelope peaks.
