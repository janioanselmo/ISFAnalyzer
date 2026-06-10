# Changelog

## 0.2.8 - Click toggle selection

- Added click-toggle selection for ringdown peaks.
- Removed reliance on Streamlit native box/lasso selection for the envelope workflow.
- Added explicit selection counter and clear button per file.
- Kept one selection graph and one fitted-envelope graph per selected ISF file.

# Changelog

## v0.2.7 - Mouse peak selection

- Reworked the Envelope workflow to remove the confusing `N`-based selection.
- Peak count is now defined by mouse selection only.
- One selected file shows one peak-selection graph; two selected files show two side-by-side peak-selection graphs.
- Added a dedicated exponential envelope fit plot for each selected signal.
- Replaced `streamlit-plotly-events` with native Streamlit Plotly selection for more reliable rendering.
- Improved usability labels and removed redundant controls from the Envelope screen.

Suggested commit:

```text
🖱️ Improve mouse-based peak selection workflow
```
