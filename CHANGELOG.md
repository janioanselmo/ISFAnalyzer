# Changelog

## v0.3.1 - Image click selection

- Replaced the unstable Plotly click callback in the Envelope workflow with image-coordinate based selection.
- The visible waveform is now the clickable selector.
- Clicking near a peak marker toggles selection and reruns the envelope fit.
- Updated Streamlit chart/dataframe calls from `use_container_width=True` to `width="stretch"`.
- Added `streamlit-image-coordinates` and `Pillow` dependencies.

## v0.3.0 - Clickable envelope

- Made waveform plot directly clickable for envelope fitting.
