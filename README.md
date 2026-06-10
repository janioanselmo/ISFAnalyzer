# ISF Analyzer v0.2.6

Analisador local para formas de onda Tektronix `.ISF`, com foco em pulso, ringing, ressonância e eletroporação.

## Novidades da v0.2.6

- Interface da aba **Análise de sinais** simplificada para quatro operações curtas e exclusivas:
  - **Sinais**: visualização e métricas gerais.
  - **Envelope**: seleção manual de picos por clique e ajuste exponencial.
  - **Comparação**: análise antes × depois.
  - **Potência**: análise V × I / potência.
- A operação **Envelope** agora segue um fluxo em três passos:
  1. ajustar janela e detecção de picos;
  2. clicar nos picos desejados;
  3. visualizar a envoltória exponencial calculada.
- O ajuste da envoltória não é mais feito automaticamente por padrão quando nenhum pico é selecionado.
- Adicionado botão **Usar últimos N** para triagem rápida.
- Seleções manuais são mantidas por arquivo, permitindo comparar envelopes de diferentes curvas carregadas.
- Adicionado segundo gráfico dedicado somente ao ajuste exponencial dos picos selecionados.
- Adicionada opção de ampliar o eixo Y nos picos, útil quando o pulso principal é muito maior que o ringing.

## Como usar a seleção de envelope

1. Carregue um ou mais arquivos `.ISF` na barra lateral.
2. Entre em **Análise de sinais → Envelope**.
3. Escolha o arquivo.
4. Ajuste início/fim da janela onde estão os picos de interesse.
5. Clique nos marcadores dos picos no gráfico superior.
6. Use pelo menos 2 picos para gerar a envoltória exponencial no gráfico inferior.
7. Para comparar vários arquivos, selecione os picos de cada arquivo. A comparação usa as seleções salvas por arquivo.

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
bash run_linux_mac.sh
```

## Dependência para clique em picos

A seleção por clique usa `streamlit-plotly-events`:

```bash
pip install -r requirements.txt
```
