# ISF Analyzer Governance

## Laboratory channel convention

The application uses the Tektronix filename convention below as a project rule:

| Filename pattern | Signal type | Intended use |
|---|---|---|
| `TXXXXCH1` | Voltage | Voltage plots, voltage-to-voltage comparison, V×I power |
| `TXXXXCH2` | Current | Current plots, current-to-current comparison, V×I power |

Files that do not match this pattern remain available as `Não classificado`, but they are not used as automatic voltage/current defaults.

## Non-redundant analysis screens

The Streamlit operation selector must keep each screen focused:

| Operation | Responsibility | Avoid duplicating |
|---|---|---|
| Sinais | Visual inspection, baseline removal, normalization, individual waveform metrics | Sequence trends and V×I power |
| Envelope | Ringing/ringdown envelope fitting and peak selection | General waveform statistics already shown in Sinais |
| Comparação | Pairwise comparison and pulse-sequence trend statistics | Energy/impedance/fase V×I from Potência |
| Potência | Voltage-current alignment, instantaneous power, energy, charge, effective resistance, impedance and phase | Same-channel ringdown deltas from Comparação |

## Experimental interpretation notes

For resonant pulses applied to potato tissue, current leading voltage is compatible with a capacitive reactance contribution. In this project, the software should support this interpretation with quantitative evidence such as:

- V-I cross-correlation delay;
- FFT-based impedance phase;
- pulse-sequence amplitude trend;
- voltage amplitude decay across pulses;
- current amplitude increase across pulses;
- energy and charge per selected voltage-current pair.

This software does not claim biological electroporation by itself. It provides waveform-derived evidence to support later correlation with biological/visual/impedance observations.

## Audit requirements

- Keep channel-classification logic centralized in `ensaisf/channels.py`.
- Keep governance and audit files inside `governance/`.
- Keep each new UI metric assigned to only one operation unless there is a strong usability reason to repeat it.
- Run at least:

```bash
python -m py_compile app.py ensaisf/*.py
```

before producing a release ZIP.

## Modular architecture rule

From `v0.5.0` onward, `app.py` must remain a minimal entry point. New code should follow this placement rule:

| Layer | Folder | Use for |
|---|---|---|
| Domain | `ensaisf/domain/` | Scientific rules, metrics, fitting, signal interpretation helpers |
| Application | `ensaisf/application/` | Use cases that combine domain routines into app-level workflows |
| Infrastructure | `ensaisf/infrastructure/` | Uploads, ZIP expansion, file adapters, CSV/export adapters |
| Presentation | `ensaisf/presentation/` | Streamlit UI, state, formatting, plots and visual components |
| Utilities | `ensaisf/utils/` | Generic numerical or formatting helpers with no scientific ownership |

Avoid adding analysis logic directly to `app.py` or mixing Streamlit widgets with domain calculations.

Updated validation command:

```bash
python -m py_compile app.py ensaisf/*.py ensaisf/**/*.py
```
