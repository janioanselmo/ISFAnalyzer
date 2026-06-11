# ISF Analyzer v0.3.12 - Color Standardization Audit

## Scope

This release applies a small visual consistency update only. The validated Envelope workflow was not redesigned.

## Changes verified

- Global palette order is now orange, blue, purple, green, muted red, teal, brown/orange and gray.
- The same palette is used by waveform visualization, Envelope image selector, Envelope comparison and Power plotting.
- Uploaded files receive `series_color_rgb` and `series_color_hex` fields immediately after parsing.
- Envelope comparison uses the stored file color when available.
- Python syntax compilation passed for `app.py`, `ensaisf/analysis.py` and `ensaisf/isf_parser.py`.

## Notes

The first two curves are now orange and blue, the third is purple, and additional curves use distinct colors. This should make visual comparison easier when switching between Sinais, Envelope, Comparação and Potência.
