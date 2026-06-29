# Audit — DDD Refactor Hotfix v0.5.1

Date: 2026-06-29
Version: 0.5.1-ddd-refactor-hotfix

## Reason

A runtime `NameError` was reported after the v0.5.0 DDD refactor:

```text
NameError: name 'SERIES_COLORS_HEX' is not defined
```

The error occurred in `ensaisf/presentation/pages/envelope_page.py` during envelope rendering.

## Root cause

During the split of the original `app.py` into presentation pages, some constants from
`ensaisf.presentation.theme` were not imported explicitly in pages that still referenced them.
The syntax compiler did not catch this because the variable is resolved only at runtime.

A second latent issue was identified in `comparison_page.py`: `max_plot_points` was used but not
included in the page function signature or call path.

## Fixes applied

- Added explicit `SERIES_COLORS_HEX` import in:
  - `ensaisf/presentation/pages/envelope_page.py`
  - `ensaisf/presentation/pages/power_page.py`
- Added `max_plot_points` to:
  - `render_comparison_page(...)`
  - the call from `analysis_page.py`
- Updated `APP_VERSION` to `0.5.1-ddd-refactor-hotfix`.

## Validation

Executed:

```bash
python -m py_compile app.py $(find ensaisf -name '*.py')
```

Also executed a lightweight static page-name check for the Streamlit page modules and verified that
no unresolved direct page names remain for the reported class of error.

Finally, the sample `Resultados.zip` was expanded using the generic ZIP loader:

- Raw entries: 68 `.ISF`
- Raw classification: 34 voltage CH1 + 34 current CH2
- Dynamic standardization: 14 common acquisitions per group
- Standardized output: 28 voltage CH1 + 28 current CH2

## Governance note

For future refactors, constants used by presentation pages must be imported explicitly from
`ensaisf.presentation.theme`. Avoid relying on wildcard imports to propagate shared constants.
