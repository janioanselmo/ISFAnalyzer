# ISF Analyzer — Final Audit Report

## Release candidate

- Version: `0.3.9-final-audit`
- Base audited version: v0.3.8 Envelope State and Label Fix
- Status: candidate for final user validation on Windows/Streamlit

## Checks performed

### Static code checks

- Python syntax compilation passed for:
  - `app.py`
  - `ensaisf/analysis.py`
  - `ensaisf/isf_parser.py`
- No `use_container_width=True` calls remain in source code.
- No generated `__pycache__` files are included in the final zip.
- Required package files are present:
  - `app.py`
  - `ensaisf/__init__.py`
  - `ensaisf/analysis.py`
  - `ensaisf/isf_parser.py`
  - `requirements.txt`
  - `README.md`
  - `CHANGELOG.md`
  - `run_windows.bat`
  - `run_linux_mac.sh`

### Functional smoke checks with sample Tektronix ISF

Using the available sample `T0039CH1.ISF`, the parser produced:

- Points: 1,000,000
- Time range: -300.000 µs to 699.999 µs
- Sampling step: approximately 1 ns
- Maximum voltage: 656 V
- Minimum voltage: -576 V

Ringdown peak detection in the default -100 to 500 µs window produced valid positive and negative extrema. The final Envelope UI uses only dominant positive maxima for clickable/automatic selection.

## Final audit fixes applied

1. Internal `APP_VERSION` was outdated and is now `0.3.9-final-audit`.
2. A duplicated `st.rerun()` after Envelope click selection was removed.
3. Stale Streamlit/Plotly compatibility comments were simplified.
4. README and CHANGELOG were updated to match the current workflow.
5. Release package is clean and excludes `__pycache__`.

## Items intentionally not changed

- The validated Envelope workflow was preserved.
- The image-based click selection was preserved because it was the first stable solution for peak selection.
- The automatic dominant positive peak selection was preserved.
- The default ringing window and peak criterion requested by the user were preserved.

## Recommendation before tagging final

Run on the target Windows environment with at least:

1. One `.ISF` file in **Envelope**.
2. Two `.ISF` files in **Envelope** with automatic selection and manual click adjustments.
3. One voltage-current pair in **Potência**.
4. Export CSV from the Envelope and Power operations.

If all four pass, tag as the final release.
