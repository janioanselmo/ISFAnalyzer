# Changelog

## v0.3.14 - Isolated per-tab state and palette refinement

- Isolated file-selection state between Sinais, Envelope, Comparação, Potência and Exportação.
- Fixed the issue where opening Potência or Comparação could leave Envelope with only two files after returning.
- Kept Sinais and Envelope as multi-file workflows.
- Kept Comparação intentionally as a two-file workflow: reference versus compared.
- Kept Potência intentionally as a two-file workflow: voltage channel versus current channel.
- Added clearer captions explaining the two-file limitation in Comparação and Potência.
- Updated widget keys to avoid stale Streamlit state from older versions.
- Refined the global palette: orange, blue, green, charcoal, magenta, teal, golden brown and brown.
- Preserved the validated Envelope workflow: full waveform, dominant positive peaks, automatic selection and manual click correction.

## v0.3.13 - File refresh and color refinement

- Added automatic synchronization of file-dependent widgets when new ISF files are uploaded.
- New uploaded files now appear immediately in Sinais and Envelope selections.
- Comparison, power and export selectboxes are kept valid after file-list changes.
- Forced the Envelope image-click component to refresh when the uploaded file set changes.
- Replaced the third default purple curve with a more distinct green.
- Updated the global palette to orange, blue, green, magenta, teal, dark gray and other high-contrast colors.

## v0.3.12 - Color standardization

- Standardized the global color palette across Sinais, Envelope, Comparação and Potência.
- Set the default visual order to orange and blue for the first two curves.
