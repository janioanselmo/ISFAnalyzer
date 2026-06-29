# ISF Analyzer

Aplicativo local em Python/Streamlit para análise de formas de onda Tektronix `.ISF`, com foco em pulsos, ringing, ringdown, ressonância e experimentos de eletroporação.

> Histórico de versões: [`governance/CHANGELOG.md`](./governance/CHANGELOG.md)
> Governança/auditoria: [`governance/GOVERNANCE.md`](./governance/GOVERNANCE.md) e [`governance/AUDIT_2026-06-29_CHANNEL_STATISTICS.md`](./governance/AUDIT_2026-06-29_CHANNEL_STATISTICS.md)
> Relatórios de validação: [`governance/VALIDATION_RINGDOWN.md`](./governance/VALIDATION_RINGDOWN.md)

---

## 🇧🇷 PT-BR

### Visão Geral

O **ISF Analyzer** lê arquivos binários `.ISF` exportados por osciloscópios Tektronix, converte os dados para unidades físicas e oferece uma interface Streamlit para inspeção, comparação e extração de métricas de sinais pulsados. O fluxo principal foi pensado para análise de ringing/ringdown em janelas configuráveis, com seleção visual de picos e diagnóstico por arquivo.

O projeto separa a interface (`app.py`) das rotinas de análise (`ensaisf/analysis.py`) e do parser Tektronix (`ensaisf/isf_parser.py`), facilitando validação e manutenção.

### Funcionalidades

- Upload local de um ou vários arquivos `.ISF`.
- Parser Tektronix robusto para bloco binário `:CURV #`.
- Conversão para tempo e amplitude usando metadados do cabeçalho (`XINCR`, `XZERO`, `YMULT`, `YOFF`, `YZERO`).
- Correção de baseline e métricas de forma de onda.
- Operações de análise para **Sinais**, **Envelope**, **Comparação** e **Potência**, com seleção automática CH1/CH2.
- Detecção de picos de ringdown por arquivo antes da sobreposição visual.
- Seleção automática ou manual de picos no Envelope.
- Comparação normalizada entre curvas, incluindo Tensão×Corrente, Corrente×Corrente e Tensão×Tensão.
- Métricas de deslocamento de ressonância, similaridade e decaimento.
- Análise de potência para pares tensão/corrente com seletor restrito a CH1=tensão e CH2=corrente.
- Estatísticas de sequência para decaimento médio de tensão e acréscimo médio de corrente.
- Exportação e inspeção de metadados/cabeçalho bruto dos arquivos.
- Paleta fixa por ordem de curva para manter consistência visual entre abas.

### Estrutura

| Arquivo | Descrição |
|---|---|
| `app.py` | Aplicação Streamlit e fluxo de interface |
| `ensaisf/isf_parser.py` | Parser de arquivos Tektronix `.ISF` |
| `ensaisf/analysis.py` | Métricas, janelas, picos, ringdown, comparação e potência |
| `ensaisf/channels.py` | Classificação automática CH1=tensão e CH2=corrente |
| `requirements.txt` | Dependências Python |
| `run_windows.bat` | Atalho de execução no Windows |
| `run_linux_mac.sh` | Atalho de execução no Linux/macOS |
| `governance/CHANGELOG.md` | Histórico de versões |
| `governance/GOVERNANCE.md` | Regras de governança, auditoria e não redundância |
| `governance/VALIDATION_RINGDOWN.md` | Registro da validação do detector de ringdown |
| `governance/AUDIT_REPORT.md` | Auditoria técnica do fluxo validado anterior |
| `governance/AUDIT_2026-06-29_CHANNEL_STATISTICS.md` | Auditoria da atualização CH1/CH2 e estatísticas |

### Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

No Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Execução

```powershell
streamlit run app.py
```

No Windows, também é possível usar:

```bat
run_windows.bat
```

No Linux/macOS:

```bash
./run_linux_mac.sh
```

### Fluxo de Envelope

1. Carregue de 1 a 4 arquivos `.ISF`.
2. Ajuste a janela de ringing, o limiar de pico e a distância mínima entre picos.
3. Use a seleção automática para iniciar com N picos por curva.
4. Clique em um pico selecionado para removê-lo ou em um candidato para adicioná-lo.
5. O ajuste de envelope e as comparações normalizadas são atualizados automaticamente.

### Validação

```powershell
python -m py_compile app.py ensaisf\analysis.py ensaisf\isf_parser.py
```

O detector validado em `v0.3.24` processa cada forma de onda individualmente, identifica a maior crista de ressonância forçada e acompanha as cristas naturais seguintes usando o período estimado. Consulte [`governance/VALIDATION_RINGDOWN.md`](./governance/VALIDATION_RINGDOWN.md) para detalhes.

### Observações Técnicas

- A aplicação é local; os arquivos enviados pelo usuário são processados no ambiente Streamlit em execução.
- A seleção por clique no Envelope depende de `streamlit-image-coordinates`. Sem esse pacote, o app continua abrindo, mas a seleção por clique fica indisponível.
- Arquivos `.ISF` com cabeçalhos incompletos ou formatos binários não previstos podem gerar erro de parsing.
- Para manter reprodutibilidade, registre a versão do app, os parâmetros da janela de análise e os arquivos usados na validação.

### Licença

Distribuído sob **MIT**. Veja [`LICENSE`](./LICENSE).

---

## 🇺🇸 English

### Overview

**ISF Analyzer** reads Tektronix `.ISF` binary waveform files, converts them to physical units, and provides a Streamlit interface for signal inspection, comparison, and metric extraction. The main workflow targets pulse, ringing and ringdown analysis with configurable windows, visual peak selection, and per-file diagnostics.

The project keeps the UI (`app.py`) separate from analysis routines (`ensaisf/analysis.py`) and the Tektronix parser (`ensaisf/isf_parser.py`) to simplify validation and maintenance.

### Features

- Local upload of one or multiple `.ISF` files.
- Robust Tektronix parser for binary `:CURV #` blocks.
- Time and amplitude conversion from header metadata (`XINCR`, `XZERO`, `YMULT`, `YOFF`, `YZERO`).
- Baseline correction and waveform metrics.
- Analysis operations for **Signals**, **Envelope**, **Comparison**, and **Power**, with automatic CH1/CH2 selection.
- Per-file ringdown peak detection before visual overlay.
- Automatic or manual peak selection in the Envelope workflow.
- Normalized curve comparison, including Voltage×Current, Current×Current, and Voltage×Voltage.
- Resonance shift, similarity, and decay metrics.
- Power analysis for voltage/current pairs with selectors restricted to CH1=voltage and CH2=current.
- Pulse-sequence statistics for mean voltage-amplitude decay and mean current-amplitude increase.
- Export plus metadata/raw-header inspection.
- Fixed curve color order across tabs for visual consistency.

### Structure

| File | Description |
|---|---|
| `app.py` | Streamlit application and UI flow |
| `ensaisf/isf_parser.py` | Tektronix `.ISF` parser |
| `ensaisf/analysis.py` | Metrics, windows, peaks, ringdown, comparison and power routines |
| `ensaisf/channels.py` | Automatic CH1=voltage and CH2=current classification |
| `requirements.txt` | Python dependencies |
| `run_windows.bat` | Windows launcher |
| `run_linux_mac.sh` | Linux/macOS launcher |
| `governance/CHANGELOG.md` | Release history |
| `governance/GOVERNANCE.md` | Governance, audit, and non-redundancy rules |
| `governance/VALIDATION_RINGDOWN.md` | Ringdown detector validation notes |
| `governance/AUDIT_REPORT.md` | Previous technical audit of the validated workflow |
| `governance/AUDIT_2026-06-29_CHANNEL_STATISTICS.md` | Audit of the CH1/CH2 and statistics update |

### Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```powershell
streamlit run app.py
```

On Windows, you can also use:

```bat
run_windows.bat
```

On Linux/macOS:

```bash
./run_linux_mac.sh
```

### Envelope Workflow

1. Upload 1 to 4 `.ISF` files.
2. Adjust the ringing window, peak threshold, and minimum peak distance.
3. Use automatic selection to start with N peaks per curve.
4. Click a selected peak to remove it, or a candidate peak to add it.
5. Envelope fitting and normalized comparisons update automatically.

### Validation

```powershell
python -m py_compile app.py ensaisf\analysis.py ensaisf\isf_parser.py
```

The detector validated in `v0.3.24` processes each waveform independently, identifies the largest forced-resonance crest, and tracks the following natural crests using the estimated period. See [`governance/VALIDATION_RINGDOWN.md`](./governance/VALIDATION_RINGDOWN.md) for details.

### Technical Notes

- The application is local; uploaded files are processed by the running Streamlit environment.
- Click-based Envelope selection depends on `streamlit-image-coordinates`. Without it, the app still runs, but click selection is unavailable.
- `.ISF` files with incomplete headers or unsupported binary formats may raise parsing errors.
- For reproducibility, record the app version, analysis-window parameters, and files used for validation.

### License

Distributed under **MIT**. See [`LICENSE`](./LICENSE).
