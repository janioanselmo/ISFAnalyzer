# Audit — Channel-aware statistics update

Date: 2026-06-29
Version: v0.4.0-channel-aware-statistics

## User requirements covered

- Automatically classify `TXXXXCH1` files as voltage and `TXXXXCH2` files as current.
- Allow combinations in the existing operations: Sinais, Envelope, Comparação and Potência.
- Avoid redundant analyses between operations.
- Add statistical support for pulse-sequence behavior, including voltage amplitude decrease and current amplitude increase.
- Keep governance/audit documentation in a dedicated folder.
- Provide a GitHub commit sentence in English.

## Implemented changes

### Channel classification

Added `ensaisf/channels.py` with centralized filename parsing:

- `TXXXXCH1` → `voltage` / `Tensão`;
- `TXXXXCH2` → `current` / `Corrente`;
- non-matching files → `unknown` / `Não classificado`.

Each loaded waveform now receives metadata fields for role, channel and pulse index.

### Sinais

Added channel-aware filtering while keeping this screen focused on visualization and individual metrics.

### Envelope

Added channel-aware filtering so voltage and current envelopes can be analyzed separately without mixing channels unintentionally.

### Comparação

Added comparison modes:

- Tensão × Corrente;
- Corrente × Corrente;
- Tensão × Tensão;
- Personalizada.

For same-role comparisons, ringdown deltas are shown. For voltage-current comparisons, only normalized similarity, delay and correlation are shown; power, energy, impedance and phase remain exclusive to Potência.

Added automatic sequence trend statistics:

- mean percent change of corrected absolute peak per pulse;
- first-to-last percent change;
- Vpp and RMS first-to-last changes;
- linear trend slope and R² over pulse index;
- separate interpretation for voltage decay and current increase.

### Potência

Voltage selector is now restricted to CH1 files and current selector is restricted to CH2 files. This reduces the risk of computing `P(t)=V(t)I(t)` from two voltage or two current files.

## Static validation

Passed:

```bash
python -m py_compile app.py ensaisf/*.py
```

## Remaining manual validation

Run the Streamlit UI locally with a real dataset containing both CH1 and CH2 files and verify:

1. selectors display voltage/current labels correctly;
2. comparison modes filter file lists correctly;
3. sequence trend signs match the expected physical behavior;
4. Potência uses the intended current scale.
