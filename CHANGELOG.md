# Changelog

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
