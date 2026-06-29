# Changelog

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
