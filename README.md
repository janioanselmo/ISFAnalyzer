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

## v0.3.13 file refresh and color refinement

This package keeps the validated Envelope workflow and fixes the final upload-refresh issue:

- Internal app version updated to `0.3.13-file-refresh-colors`.
- When a new `.ISF` file is uploaded, file-dependent widgets are synchronized automatically.
- New files are immediately added to **Sinais** and **Envelope** selections.
- Single-choice controls in **Comparação**, **Potência** and **Exportação** are kept valid after adding/removing files.
- Envelope image-click plot is forced to refresh when the uploaded file list changes.
- Global color order remains standardized across **Sinais**, **Envelope**, **Comparação** and **Potência**.
- Default color order: 1st curve orange, 2nd curve blue, then green, magenta, teal and other high-contrast colors.
- The purple third curve was removed from the default palette.
- Verified Streamlit calls use `width="stretch"` rather than deprecated `use_container_width=True`.
- Verified the app name remains **ISF Analyzer**.
- Verified Envelope defaults: start = -100 µs, end = 500 µs, 4 peaks per curve, criterion = **Últimos N picos**.

## Envelope workflow

The **Envelope** operation follows the dominant-positive-peak workflow:

1. Choose 1 to 4 `.ISF` files.
2. Adjust the ringdown window, peak threshold and minimum peak distance.
3. The Envelope plot shows the complete waveform trace for context.
4. The app keeps only the dominant positive local maxima as visible clickable candidates.
5. Enable **Auto-selecionar** and choose **Picos por curva** to start with N peaks already selected in red.
6. Click a selected peak to remove it, or a candidate peak to add it.
7. Envelope fits and normalized comparisons update automatically.
