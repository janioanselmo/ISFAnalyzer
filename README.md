# ISF Analyzer

Local Streamlit app for Tektronix `.ISF` waveform analysis, focused on pulse analysis, ringdown, resonance and electroporation experiments.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

On Windows, you can also run:

```bat
run_windows.bat
```

## v0.3.12 color standardization

This package keeps the validated Envelope workflow and standardizes the color mapping across all analysis operations:

- Internal app version updated to `0.3.12-color-standardization`.
- Global curve palette standardized across **Sinais**, **Envelope**, **Comparação** and **Potência**.
- Default color order: 1st curve orange, 2nd curve blue, 3rd curve purple, then high-contrast distinct colors.
- Each uploaded file receives a stable color mapping so the same file keeps the same visual identity across operation changes.
- Removed generated `__pycache__` files from the distribution package.
- Removed a duplicated `st.rerun()` in the Envelope click-selection path.
- Verified Streamlit calls use `width="stretch"` rather than deprecated `use_container_width=True`.
- Verified the app name remains **ISF Analyzer**.
- Verified the current Envelope default workflow: start = -100 µs, end = 500 µs, 4 peaks per curve, criterion = **Últimos N picos**.

## Envelope workflow

The **Envelope** operation follows the dominant-positive-peak workflow:

1. Choose 1 to 4 `.ISF` files.
2. Adjust the ringdown window, peak threshold and minimum peak distance.
3. The Envelope plot shows the complete waveform trace for context.
4. The app keeps only the dominant positive local maxima as visible clickable candidates.
5. Enable **Auto-selecionar** and choose **Picos por curva** to start with N peaks already selected in red.
6. Click a red peak to remove it from the fit, or click a visible candidate to add it back.
7. The exponential envelope is fitted automatically when at least two peaks are selected for a file.
8. With multiple files, waveforms and dominant positive peaks share the same axis and fitted envelopes are overlaid for comparison.

## Main operations

- **Sinais**: waveform visualization and general pulse metrics.
- **Envelope**: full waveform + dominant positive peak selection + exponential envelope fit.
- **Comparação**: before/after waveform and ringdown comparison.
- **Potência**: voltage-current, power, energy, charge and impedance analysis.

## Notes

The `.PNG` exported by the oscilloscope is useful for visual checking, but the `.ISF` file is the scientific data source used by this app.
