# ISF Analyzer v0.2.4

Analisador local para formas de onda Tektronix `.ISF`, com foco em pulso, ringing, ressonância e eletroporação.

## Novidades da v0.2.4

- Nome da aplicação alterado para **ISF Analyzer**.
- Seleção de picos por **clique direto no mouse**.
- Cada clique alterna o estado do pico: seleciona ou desmarca.
- Permite escolher 2, 3, 4 ou mais picos, em qualquer região da oscilação/ringdown.
- A envoltória exponencial é recalculada automaticamente a partir dos picos selecionados.
- Mantém fallback automático para os últimos N picos quando não há seleção manual.

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

## Como usar a seleção por clique

1. Carregue um ou mais arquivos `.ISF`.
2. Ajuste a janela de ringing na barra lateral.
3. Entre em **Análise de sinais → Ressonância e envoltória**.
4. Clique diretamente nos marcadores dos picos que deseja usar no ajuste.
5. Clique novamente em um pico selecionado para desmarcá-lo.
6. O software recalcula automaticamente a envoltória exponencial.
7. Use **Limpar seleção** para voltar ao modo automático.

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

## Observação

A seleção por clique usa o componente `streamlit-plotly-events`. Se a seleção por clique não aparecer, reinstale as dependências:

```bash
pip install -r requirements.txt
```
