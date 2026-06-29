# ISF Analyzer v0.3.23 — Audit Report

## Scope
Final targeted audit after fixing envelope detection ambiguity in multi-waveform overlays.

## Changes verified
- Detection runs per waveform/file before the combined overlay is rendered.
- `N picos após maior pico` now uses the largest upper crest of each individual waveform as the forced-resonance anchor.
- The next N upper crests after that anchor are selected for envelope fitting.
- A diagnostic table was added to make per-file detection visible.
- Streamlit state/cache keys were bumped for envelope peak selections and cached candidate tables.

## Static checks
- `app.py`, `ensaisf/analysis.py`, and `ensaisf/isf_parser.py` compile with `python -m py_compile`.
- `__pycache__` and `.pyc` files were removed from the package.
- The Tektronix ISF parser was tested with the available `T0039CH1.ISF` sample.

## Runtime note
The visual Streamlit UI was not executed in this environment, so validate the Envelope tab locally with your multi-file dataset before tagging as stable.
