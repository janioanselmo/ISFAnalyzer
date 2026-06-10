# ENSA ISF Analyzer

Mini-IDE em Python/Streamlit para carregar arquivos Tektronix `.ISF`, visualizar formas de onda e extrair métricas para análise de pulsos, ringing, campo elétrico e energia.

## Recursos

- Carregamento de múltiplos arquivos `.ISF`
- Visualização temporal com zoom interativo
- Métricas automáticas:
  - máximo, mínimo, pico-a-pico, RMS
  - largura de pulso por limiar
  - frequência dominante por FFT
  - estimativa de ringing
  - constante de decaimento aproximada
  - energia aproximada em carga resistiva
  - campo elétrico em V/m e kV/cm usando distância entre eletrodos
- Comparação de múltiplos sinais
- Análise V × I, com cálculo de potência e energia quando houver canal de corrente
- Exportação de tabela de métricas em CSV
- Exportação de forma de onda processada em CSV

## Instalação

Crie um ambiente virtual, instale as dependências e rode:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Uso sugerido

1. Abra a aplicação.
2. Carregue um ou mais arquivos `.ISF`.
3. Informe o gap entre eletrodos em mm.
4. Ajuste o limiar de detecção do pulso.
5. Use a aba de sinal único para estudar uma aquisição.
6. Use a aba múltiplos sinais para comparar vários disparos/canais.
7. Use a aba V × I se tiver canal de tensão e canal de corrente.

## Observações importantes

- O arquivo `.PNG` do osciloscópio serve para conferência visual.
- O arquivo `.ISF` é o dado real usado na análise.
- Energia por carga resistiva usa `E = ∫ v²/R dt`.
- Para análise V × I, use `P(t)=V(t)I(t)` e `E=∫P(t)dt`.
- Se o canal de corrente estiver em volts por causa de shunt ou probe, configure o fator A/V.


## Correção v0.1.1

Esta versão remove o uso direto de `np.trapz` e usa uma função de compatibilidade
com `np.trapezoid`, evitando o erro:

```text
AttributeError: module 'numpy' has no attribute 'trapz'
```
