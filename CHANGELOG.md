# Changelog

## v0.3.6 - Envelope defaults

- Changed the sidebar ringdown window defaults to -100 µs and 500 µs.
- Changed Envelope automatic peak count default from 6 to 4 peaks per curve.
- Changed Envelope auto-selection criterion default to Últimos N picos.
- Updated Streamlit widget keys for the Envelope defaults to avoid stale session-state values.

## v0.3.5 - Auto dominant positive peaks

- Added automatic selection of the N dominant positive peaks in Envelope mode.
- The full waveform remains visible, but only dominant positive maxima are marked as candidates.
- Selected peaks start in red automatically when auto-selection is enabled.
- Added a simple control for the number of peaks per curve and the auto-selection criterion.
- Manual mouse clicks can still deselect or reselect peaks after the automatic initialization.
- Reduced visual clutter and click latency by limiting markers to dominant peak candidates.

## v0.3.4 - Positive peaks on full waveform

- Restored the full waveform trace in Envelope mode.
- Limited clickable markers to positive local maxima only.
- Removed minima/valley markers from the Envelope workflow.
- Simplified quick selection to last N positive peaks or N largest positive peaks.
- Kept multi-file overlay in the same axis for direct envelope comparison.

## v0.3.3 - Extrema-only envelope selector

- Changed Envelope mode to draw only local maxima and minima instead of the full waveform trace.
- Added quick selection buttons for last N maxima, last N minima, last N maxima + minima, and N largest extrema by absolute amplitude.
- Kept manual mouse-click selection on extrema.
- Improved responsiveness by avoiding full waveform rendering during envelope clicks.
- Improved wording from generic peaks to maxima/minima extrema for clearer electroporation ringdown analysis.

## v0.3.2 - Multi-envelope fast selector

- Added a shared-axis Envelope selector for 1 to 4 waveforms.
- The user now clicks peaks from multiple files in the same graph.
- Each file keeps independent peak selections and independent exponential fitting.
- Envelope comparison is generated automatically from all valid selected files.
- Reduced click latency by drawing the selector with fewer points and by generating export metrics on demand.


## v0.3.1 - Image click selection

- Replaced the unstable Plotly click callback in the Envelope workflow with image-coordinate based selection.
- The visible waveform is now the clickable selector.
- Clicking near a peak marker toggles selection and reruns the envelope fit.
- Updated Streamlit chart/dataframe calls from `use_container_width=True` to `width="stretch"`.
- Added `streamlit-image-coordinates` and `Pillow` dependencies.

## v0.3.0 - Clickable envelope

- Made waveform plot directly clickable for envelope fitting.
