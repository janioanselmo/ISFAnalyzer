# Audit - DDD-inspired refactor

Date: 2026-06-29  
Version: v0.5.0-ddd-refactor

## Objective

Refactor the Streamlit ISF Analyzer so the project no longer depends on a single monolithic `app.py` file. The goal is maintainability, scientific traceability, and easier future testing while preserving the validated behavior from v0.4.3.

## Main architectural decisions

- `app.py` is now only a minimal entry point.
- Streamlit orchestration lives in `ensaisf/presentation/streamlit_app.py`, while each visible page/operation is split under `ensaisf/presentation/pages/`.
- Scientific/domain logic was moved toward `ensaisf/domain/`.
- Use-case level routines were moved toward `ensaisf/application/`.
- File and export adapters were moved toward `ensaisf/infrastructure/`.
- UI helpers, plotting, visual state, and constants were moved toward `ensaisf/presentation/`.
- General numerical helpers were moved toward `ensaisf/utils/`.

## Current module map

```text
app.py
ensaisf/
  analysis.py
  channels.py
  isf_parser.py
  domain/
    channel_metrics.py
    envelope_analysis.py
  application/
    metrics_tables.py
    power_analysis.py
  infrastructure/
    upload_loader.py
    csv_exporter.py
  presentation/
    streamlit_app.py
    formatting.py
    plots.py
    state.py
    theme.py
    pages/
      analysis_page.py
      signals_page.py
      envelope_page.py
      comparison_page.py
      power_page.py
      export_page.py
      header_page.py
  utils/
    math_utils.py
```

## Scientific behavior preserved

The refactor was structural. It was not intended to change:

- CH1/CH2 classification rules;
- generic ZIP loading;
- dynamic per-folder standardization;
- Envelope peak-selection workflow;
- Envelope overlay on the item-2 graph;
- comparison modes;
- power/energy/impedance calculations;
- export workflows.

## Page split completed

The visible Streamlit areas were separated into page modules:

- `presentation/pages/analysis_page.py`: operation selector and page orchestration;
- `presentation/pages/signals_page.py`: Sinais;
- `presentation/pages/envelope_page.py`: Envelope;
- `presentation/pages/comparison_page.py`: Comparação;
- `presentation/pages/power_page.py`: Potência;
- `presentation/pages/export_page.py`: Exportação;
- `presentation/pages/header_page.py`: Cabeçalho.

A future low-risk cleanup can further reduce duplicate imports in these page modules, but the functional behavior is now separated from the entry point and from the infrastructure/domain layers.

## Validation performed

```bash
python -m py_compile app.py ensaisf/*.py ensaisf/**/*.py
```

No syntax errors were detected.

## Governance note

Future changes should avoid reintroducing scientific logic into `app.py`. New calculations should be added to `domain/` or `application/`; new file-format or export behavior should be added to `infrastructure/`; Streamlit-specific rendering should remain in `presentation/`.
