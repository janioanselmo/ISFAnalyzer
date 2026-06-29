# Package Confirmation Audit - 2026-06-29

## Purpose

Confirm whether the delivered package contains real code changes compared with the original `ISFAnalyzer.zip`, and document the corrective cleanup requested after review.

## Confirmed code-level changes

The corrected package includes the following implementation changes relative to the original project:

1. `app.py` now uses `APP_VERSION = "0.4.1-channel-aware-statistics-no-validation-csv"`.
2. `app.py` imports channel helpers from `ensaisf.channels`.
3. `ensaisf/channels.py` was added to centralize filename-based classification.
4. The application classifies files using the rule:
   - `TXXXXCH1` = voltage / tensão;
   - `TXXXXCH2` = current / corrente.
5. The single analysis operation selector preserves the non-redundant workflow:
   - Signals / Sinais: inspection and individual metrics;
   - Envelope: ringdown/envelope decay;
   - Comparison / Comparação: signal-to-signal comparison and sequence trends;
   - Power / Potência: voltage-current power, energy, impedance and phase metrics.
6. Comparison mode supports:
   - Voltage x Current;
   - Current x Current;
   - Voltage x Voltage;
   - Custom pairing.
7. Sequence statistics were added for:
   - mean peak-amplitude variation per pulse;
   - first-to-last pulse variation;
   - voltage decay trend;
   - current increase trend;
   - linear slope and R² of the peak-amplitude sequence.

## Corrective cleanup in v0.4.1

- Removed `PEAK_DETECTION_VALIDATION.csv` from the distributed ZIP package.
- Removed README references to the removed CSV file.
- Updated the historical validation note to explain that the CSV was temporary validation data and should be regenerated if needed.

## Validation performed

The package was checked with:

```bash
python -m py_compile app.py ensaisf/*.py
```

No Python syntax errors were detected during this check.
