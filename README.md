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

## v0.3.4 usability notes

The **Envelope** operation now follows the positive-peak workflow:

1. Choose 1 to 4 `.ISF` files.
2. Adjust the ringdown window, peak threshold and minimum peak distance.
3. The Envelope plot shows the complete waveform trace for context.
4. Only positive local maxima are marked as clickable points.
5. Click peak markers manually, or use quick selection for:
   - last N positive peaks;
   - N largest positive peaks.
6. The exponential envelope is fitted automatically when at least two peaks are selected for a file.
7. With multiple files, waveforms and positive peak markers share the same axis and fitted envelopes are overlaid for comparison.

## v0.3.4

- Restored full waveform rendering in Envelope mode.
- Kept clickable markers only on positive local maxima.
- Removed minima/valley markers from the main Envelope workflow.
- Simplified automatic peak selection to last N positive peaks or N largest positive peaks.
- Preserved multi-waveform overlay and envelope comparison.

## v0.3.3

- Envelope mode plotted only local extrema for faster peak/valley selection.
- Added quick selection for last N maxima, last N minima, last N maxima + minima, and largest-N extrema.
- Preserved manual mouse-click selection on extrema.
- Improved multi-waveform overlay usability for comparing envelope decay across experiments.

## v0.3.2

- Multi-file envelope selection on a single shared axis.
- One click image selector for 1 to 4 waveforms.
- Per-file peak selection state and exponential fit.
- Faster click response by reducing the image selector draw load.
- Export metrics are now generated on demand to avoid slowing down Envelope clicks.

## v0.3.1

- Click-toggle peak selection for envelope fitting.
- One graph per selected ISF file in Envelope mode.
- Automatic envelope comparison after at least two files have valid selected peaks.
