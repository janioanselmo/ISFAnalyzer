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

## v0.2.9 usability notes

The **Envelope** operation now uses mouse-based peak selection only:

1. Choose one or more `.ISF` files.
2. Adjust the ringdown window.
3. Select the peaks directly in the waveform graph using the mouse.
4. The number of peaks is defined by the selected points; there is no manual `N` field.
5. The exponential envelope is fitted automatically when at least two peaks are selected.

If two files are selected, the app shows two peak-selection graphs side by side and then overlays the fitted envelopes for comparison.


## v0.2.9

- Click-toggle peak selection for envelope fitting.
- One graph per selected ISF file in Envelope mode.
- Automatic envelope comparison after at least two files have valid selected peaks.

