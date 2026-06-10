# Changelog

## v0.2.5 - Click plot fix

- Fixed empty/default-axis rendering in click-based envelope selection.
- Replaced WebGL trace with regular Plotly Scatter in the ringdown clickable chart.
- Forced meaningful X/Y axis ranges based on the ringdown window and detected peaks.
- Converted peak customdata to NumPy arrays for more reliable Plotly event payloads.

# Changelog

## v0.2.4 - Plotly selected marker compatibility fix

- Removed unsupported `selected.marker.symbol` property from Plotly scatter traces.
- Keeps click-based peak selection and selected-point highlighting using supported marker size behavior.

## v0.2.4 - Click peak selection

Suggested commit:

```text
Add click-based peak selection for envelope fitting
```

### Added

- Click-based peak selection for ringdown envelope fitting.
- Peak toggle behavior: click to select, click again to remove.
- Automatic envelope refit after every peak selection change.
- Optional fallback to native Streamlit point selection if `streamlit-plotly-events` is unavailable.

### Changed

- Renamed application from ENSA ISF Analyzer to **ISF Analyzer**.
- Updated app title, page title, README and package naming for academic use.
- Replaced box/lasso-first workflow with direct click-based peak selection.

### Notes

- The selected peaks define the exponential envelope fit.
- If no peaks are manually selected, the app still uses the last N detected peaks as a fallback.
- Use the same selected peak count and comparable ringdown windows when comparing before/after electroporation.
