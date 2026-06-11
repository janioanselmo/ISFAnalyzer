# ISF Analyzer v0.3.14 - Isolated State Audit

## Scope

This release fixes the remaining file-selection state issue and refines the palette. The validated Envelope workflow was not redesigned.

## Changes verified

- The uploaded file list is global, but each analysis operation now uses independent widget state.
- Sinais and Envelope remain multi-file operations.
- Comparação and Potência are explicitly two-file operations.
- Potência selectboxes no longer affect Envelope file selection.
- Comparação selectboxes no longer affect Envelope file selection.
- Adding a new uploaded file updates Sinais and Envelope automatically.
- Envelope selection is capped at 4 files for usability and performance.
- Global palette order is orange, blue, green, charcoal, magenta, teal, golden brown and brown.
- Python syntax compilation passed for `app.py`, `ensaisf/analysis.py` and `ensaisf/isf_parser.py`.
- No deprecated `use_container_width=True` calls were found.

## Notes

Comparação and Potência are intentionally restricted to two selected files because their calculations are pairwise. Multi-curve visual inspection and multi-envelope comparison should be performed in Sinais and Envelope.
