# ISF Analyzer v0.3.18 — Decay-aware peak detection audit

## Summary
This release refines the Envelope automatic selection algorithm for tail-oriented analysis.

## Fix
When `Critério = Últimos N picos`, late maxima can be physically relevant even when they are below the zero axis or much smaller than the first lobes. The previous candidate filter was still too strict for these late decaying peaks.

## Changes
- Uses a looser detection threshold only for `Últimos N picos`.
- Uses a larger candidate pool only for tail-oriented peak selection.
- Keeps the stricter candidate pool for `N maiores picos`.
- Preserves the existing UI, click selection and multi-file overlay behavior.

## Validation
- Python compile check passed for `app.py`, `ensaisf/analysis.py` and `ensaisf/isf_parser.py`.
- No structural change to ISF parsing, export, comparison or power analysis.
