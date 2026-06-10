# ENSA ISF Analyzer v0.2.0-resonance

Mini-IDE local em Python/Streamlit para carregar, visualizar e analisar arquivos Tektronix `.ISF`, com foco em pulsos, ringing, ressonância e eletroporação.

## Como rodar no Windows

```bat
run_windows.bat
```

Ou manualmente:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Como rodar no Linux/macOS

```bash
bash run_linux_mac.sh
```

## Principais recursos

### Sinal único

- leitura `.ISF` Tektronix;
- Vmax, Vmin, Vpp e RMS;
- largura de pulso por limiar relativo;
- frequência dominante por FFT;
- frequência por cruzamento de zero;
- área assinada e área absoluta;
- energia aproximada em carga resistiva;
- campo elétrico em V/m e kV/cm a partir do gap.

### Ressonância / ringing

A versão v0.2 adiciona análise dedicada da oscilação natural nos picos finais da onda:

- janela manual de ringing em µs;
- detecção de picos positivos e negativos;
- período por picos de mesma polaridade;
- período por extremos alternados;
- período por cruzamento de zero;
- frequência amortecida;
- frequência natural estimada;
- constante de decaimento do envelope, `tau`;
- decremento logarítmico;
- razão de amortecimento `zeta`;
- fator de qualidade `Q`;
- energia do ringing;
- decaimento percentual por ciclo;
- tempo estimado até 10% e acomodação a 5%;
- assimetria entre semiciclos positivo/negativo;
- R² do ajuste de envelope.

### Antes × depois da eletroporação

Comparação direta entre uma aquisição antes e outra depois:

- variação percentual de período;
- variação percentual de frequência;
- variação percentual de `tau`;
- variação percentual de `Q`;
- variação percentual da energia do ringing;
- correlação de forma de onda;
- NRMSE;
- atraso por correlação cruzada;
- índice exploratório `resonance_shift_score`.

> O `resonance_shift_score` é um indicador exploratório para triagem experimental. Ele ainda não deve ser tratado como marcador biológico validado.

### V × I / potência

Quando há um canal de tensão e outro de corrente:

- P(t) = V(t)I(t);
- energia integral ∫Pdt;
- carga ∫Idt;
- energia absoluta;
- resistência efetiva;
- impedância instantânea média/mediana;
- módulo e fase aproximados da impedância por FFT;
- atraso V-I por correlação cruzada.

## Sugestão de commit

```text
Add resonance ringdown and before-after waveform analysis
```

## Observações importantes

- Ajuste a janela de ringing para capturar apenas a oscilação natural, evitando incluir o pulso principal quando possível.
- Para comparar antes/depois, use a mesma janela de ringing, mesmo gap, mesma configuração de probe e mesma escala do osciloscópio.
- A energia resistiva depende do valor de carga equivalente informado. Para análise real com amostra biológica, prefira medir tensão e corrente simultaneamente.


## v0.2.1 — Interface simplificada

A interface agora possui apenas três abas principais:

1. **Análise de sinais** — concentra sinal único, múltiplos sinais, ressonância/ringing, antes × depois e V × I / potência.
2. **Exportação** — concentra os downloads CSV.
3. **Cabeçalho** — concentra metadados e cabeçalho bruto ISF.
