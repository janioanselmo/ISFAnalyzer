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

## v0.3.14 isolated state and palette refinement

This package keeps the validated Envelope workflow and fixes the remaining per-tab state issue:

- Internal app version updated to `0.3.14-isolated-state`.
- File uploads remain global, but each analysis operation now has independent file-selection state.
- **Sinais** can show one or multiple uploaded files.
- **Envelope** can show 1 to 4 files in the same axis and keeps its own selection when switching tabs.
- **Comparação** is intentionally limited to exactly two selections: reference versus compared.
- **Potência** is intentionally limited to exactly two selections: voltage channel and current channel.
- Adding a new `.ISF` file automatically synchronizes Sinais and Envelope without being overwritten by Comparação or Potência.
- The Envelope image-click plot is rebuilt only after real upload changes, preserving valid peak selections.
- Global color order remains standardized across **Sinais**, **Envelope**, **Comparação** and **Potência**.
- Default color order: 1st curve orange, 2nd curve blue, then green, charcoal, magenta, teal, golden brown and brown.
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
