# ENSA ISF Analyzer v0.2.2

Mini-IDE local para análise de formas de onda Tektronix `.ISF`, com foco em eletroporação, PEF e assinatura ressonante/ringdown.

## Novidades da v0.2.2

- Interface otimizada dentro da aba **Análise de sinais**.
- Fusão das análises de sinal único e múltiplos sinais em **Visão geral / formas de onda**.
- Nova análise **Ressonância e envoltória**.
- Seleção de picos com mouse no gráfico Plotly usando box/lasso.
- Ajuste de envoltória exponencial nos picos selecionados ou nos últimos N picos detectados.
- Comparação das envoltórias exponenciais entre vários arquivos carregados.
- Exportação das métricas da envoltória em CSV.

## Abas principais

1. **Análise de sinais**
   - Visão geral / formas de onda
   - Ressonância e envoltória
   - Antes × depois
   - V × I / potência

2. **Exportação**
   - Métricas gerais
   - Métricas de ringing
   - Forma de onda individual em CSV

3. **Cabeçalho**
   - Metadados extraídos
   - Cabeçalho bruto Tektronix

## Como usar a envoltória exponencial

1. Carregue um ou mais arquivos `.ISF`.
2. Ajuste a janela de ringing na barra lateral.
3. Entre em **Análise de sinais → Ressonância e envoltória**.
4. Escolha o sinal.
5. Selecione os picos finais com o mouse usando box/lasso no gráfico.
6. Se nenhum pico for selecionado, o software usa automaticamente os últimos N picos detectados.
7. Compare o valor de `tau_us`, `decaimento_por_periodo_percent`, `r2_envelope` e as curvas normalizadas entre os arquivos.

O modelo ajustado é:

```text
|V_peak(t)| = A0 * exp(-(t - t0) / tau)
```

## Instalação

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Ou execute:

```bat
run_windows.bat
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Ou execute:

```bash
bash run_linux_mac.sh
```

## Observação de desempenho

Streamlit é ótimo para prototipagem científica, mas pode ficar lento com muitos arquivos `.ISF` grandes porque o navegador precisa renderizar muitos pontos e o script é reexecutado a cada interação. Para uso com muitos ensaios, a recomendação futura é migrar a visualização pesada para PySide6/PyQtGraph, mantendo o núcleo de análise NumPy/Pandas.
