# Changelog

## v0.5.2-final-three-peak-envelope — 2026-06-29

- Fixed Envelope fitting so the red curve is fitted from the selected upper-crest coordinates, not from local peak-to-valley prominence amplitudes.
- Changed the default Envelope workflow to use 3 final peaks of the signal.
- Changed the default automatic criterion to `Últimos N picos`, with `N = 3`.
- Anchored the exponential fit at the first selected final crest so the overlay starts at the selected peak and stays in the same y-axis coordinate system as the waveform.
- Kept `envelope_amplitude` as a diagnostic column, but no longer uses it as the default visible fit amplitude for the final-peak envelope.



## v0.5.1-ddd-refactor-hotfix — 2026-06-29

- Fixed runtime `NameError` caused by missing `SERIES_COLORS_HEX` imports after the DDD refactor.
- Fixed latent comparison page issue by passing `max_plot_points` explicitly.
- Added DDD hotfix audit note in `governance/AUDIT_2026-06-29_DDD_HOTFIX.md`.

## v0.5.0 - DDD-inspired modular refactor

- Reduced `app.py` to a minimal Streamlit entry point.
- Moved Streamlit UI orchestration into `ensaisf/presentation/streamlit_app.py`.
- Added `ensaisf/domain/` for channel-aware sequence metrics and envelope analysis helpers.
- Added `ensaisf/application/` for power analysis and exported metric-table use cases.
- Added `ensaisf/infrastructure/` for generic upload/ZIP loading and CSV export adapters.
- Added `ensaisf/presentation/theme.py`, `formatting.py`, `plots.py`, and `state.py` to isolate UI constants, formatting, plotting, and Streamlit state.
- Kept the validated numerical behavior from v0.4.3 while improving maintainability and future testability.

## v0.4.3 - Generic ZIP dataset loading

- Generalized ZIP loading so the app works with any uploaded ZIP, not only the validation dataset used during development.
- Prefixes ZIP members with the uploaded ZIP stem, preserving dataset identity when multiple ZIPs contain the same internal folder and Tektronix filenames.
- Updated sidebar guidance to make clear that per-folder standardization is dynamic: the app computes the smallest common `TXXXX` count for the currently loaded groups.
- Removed wording that could imply a fixed 14-acquisition rule; the previous 14-count case remains only a validation example.

## v0.4.2 - ZIP folders, sequence standardization and envelope overlay

- Added `.ZIP` upload support while preserving internal folder paths, allowing files with the same Tektronix basename to coexist safely.
- Added optional per-folder standardization that keeps the first common `TXXXX` acquisitions in each folder. This supports datasets such as 14 acquisitions in the first-pulse folder and 20 in the final-pulse folder, using 14 from each.
- Kept direct duplicate `.ISF` filenames usable by adding an internal duplicate suffix when needed.
- Updated the Envelope workflow so the fitted envelope is drawn over the item-2 waveform/peak-selection graph while item 3 remains a separated summary/comparison section.
- Updated governance notes for non-renaming, ZIP-based grouping, and non-redundant Envelope presentation.

## v0.4.1 - Channel statistics package cleanup

- Confirmed that the v0.4.0 package contains code-level changes for automatic CH1/CH2 classification and channel-aware statistics.
- Removed `PEAK_DETECTION_VALIDATION.csv` from the distributed ZIP package.
- Updated README and validation notes so temporary validation CSV data is no longer referenced as a shipped project file.
- Updated the application version string to make this corrected package visibly distinguishable in the Streamlit header.

## v0.4.0 — Channel-aware statistics

- Added automatic filename-based signal classification: `TXXXXCH1` as voltage and `TXXXXCH2` as current.
- Added channel-aware selectors to Sinais, Envelope, Comparação and Potência.
- Added comparison modes for Tensão×Corrente, Corrente×Corrente, Tensão×Tensão and Personalizada.
- Prevented redundant/physically ambiguous metrics by keeping V×I energy/impedance/fase in Potência and same-channel ringdown deltas in Comparação.
- Added pulse-sequence trend statistics for voltage amplitude decay and current amplitude increase.
- Moved governance/audit documentation into `governance/`.

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
