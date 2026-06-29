# Audit — Generic ZIP loading and dynamic group standardization

Date: 2026-06-29  
Version: v0.4.3-generic-zip-dataset-loading

## User clarification

The app must not be designed only for the supplied `Resultados.zip`. The user needs to load other ZIP files and other ISF datasets in future experiments.

## Implementation decision

1. ZIP handling is generic. Any uploaded `.zip` is expanded by scanning its internal members and accepting safe `.ISF` files.
2. The display/source path is now prefixed with the ZIP stem, for example:
   - `Resultados/1 Pulso (Primeiro)/T0000CH1.ISF`
   - `NewExperiment/Before/T0000CH1.ISF`
   - `NewExperiment/After/T0000CH1.ISF`
3. This avoids collisions when several ZIPs contain repeated names such as `T0000CH1.ISF` and `T0000CH2.ISF`.
4. The classification rule remains filename-based and generic:
   - `TXXXXCH1` = voltage
   - `TXXXXCH2` = current
5. Group standardization is not hard-coded to 14. It calculates the minimum number of distinct `TXXXX` indices available across the currently loaded groups and keeps the first common N when enabled.
6. If the user loads a ZIP with 8 acquisitions in one folder and 8 in another, N = 8. If another ZIP has 30 and 25, N = 25. The prior 14 case was only an example from the validation dataset.

## Expected user workflow

- Preferred: load complete ZIP datasets, because the internal paths are preserved.
- Also supported: load multiple standalone `.ISF` files. If standalone files share the same basename, the app adds an internal duplicate suffix because browsers generally do not expose the original local folder path for loose files.

## Validation

Static validation was run with:

```bash
python -m py_compile app.py ensaisf/*.py
```

The package should be validated interactively in Streamlit using at least:

1. The supplied `Resultados.zip`.
2. A second arbitrary ZIP with different folder names and counts.
3. A mixed upload containing a ZIP plus loose `.ISF` files.
