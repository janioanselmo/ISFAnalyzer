from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ensaisf.analysis import (
    align_current_to_voltage,
    decimate_for_plot,
    metrics_dataframe,
    vi_metrics,
    waveform_metrics,
)
from ensaisf.isf_parser import read_isf_bytes


st.set_page_config(
    page_title="ENSA ISF Analyzer",
    page_icon="⚡",
    layout="wide",
)


def _format_metric(value: float, unit: str = "", precision: int = 3) -> str:
    if value is None or not np.isfinite(value):
        return "—"
    return f"{value:.{precision}g} {unit}".strip()


@st.cache_data(show_spinner=False)
def parse_uploaded_file(name: str, data: bytes):
    waveform = read_isf_bytes(data)
    return {
        "name": name,
        "time_s": waveform.time_s,
        "value": waveform.value,
        "metadata": waveform.metadata,
        "header": waveform.header,
    }


def plot_waveforms(
    waveforms: list[dict],
    normalize: bool = False,
    corrected: bool = False,
    max_points: int = 30_000,
):
    fig = go.Figure()

    for item in waveforms:
        t = item["time_s"]
        y = item["value"].astype(float)

        if corrected:
            baseline = np.median(y[t < 0]) if np.any(t < 0) else np.median(y[: max(10, len(y) // 10)])
            y = y - baseline

        if normalize:
            denom = np.max(np.abs(y))
            if denom > 0:
                y = y / denom

        t_plot, y_plot = decimate_for_plot(t, y, max_points=max_points)
        fig.add_trace(
            go.Scattergl(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name=item["name"],
            )
        )

    fig.update_layout(
        height=560,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude normalizada" if normalize else "Amplitude",
        hovermode="x unified",
        legend_title="Arquivo",
        margin=dict(l=40, r=20, t=40, b=40),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def waveform_csv_bytes(item: dict) -> bytes:
    df = pd.DataFrame(
        {
            "tempo_s": item["time_s"],
            "tempo_us": item["time_s"] * 1e6,
            "amplitude": item["value"],
        }
    )
    return df.to_csv(index=False).encode("utf-8")


st.title("⚡ ENSA ISF Analyzer")
st.caption("Mini-IDE para carregar, visualizar e analisar arquivos Tektronix .ISF")

with st.sidebar:
    st.header("Configuração da análise")

    uploaded_files = st.file_uploader(
        "Carregue arquivos Tektronix .ISF",
        type=["isf", "ISF"],
        accept_multiple_files=True,
    )

    gap_mm = st.number_input(
        "Distância entre eletrodos / gap (mm)",
        min_value=0.001,
        value=15.0,
        step=0.5,
        format="%.3f",
    )

    resistance_ohm = st.number_input(
        "Carga equivalente para energia resistiva (Ω)",
        min_value=0.001,
        value=50.0,
        step=1.0,
        format="%.3f",
    )

    threshold_fraction = st.slider(
        "Limiar para largura de pulso (% do pico)",
        min_value=1,
        max_value=80,
        value=10,
        step=1,
    ) / 100.0

    baseline_mode = st.selectbox(
        "Linha de base",
        ["t<0", "primeiros 10%"],
        index=0,
    )

    max_plot_points = st.slider(
        "Máximo de pontos por curva no gráfico",
        min_value=5_000,
        max_value=100_000,
        value=30_000,
        step=5_000,
    )

if not uploaded_files:
    st.info(
        "Carregue um ou mais arquivos `.ISF` na barra lateral. "
        "O `.PNG` do osciloscópio é útil para conferência visual, mas o `.ISF` contém a forma de onda real."
    )
    st.stop()

waveforms: list[dict] = []
errors: list[str] = []

for file in uploaded_files:
    try:
        waveforms.append(parse_uploaded_file(file.name, file.getvalue()))
    except Exception as exc:
        errors.append(f"{file.name}: {exc}")

if errors:
    st.error("Alguns arquivos não puderam ser lidos:\n\n" + "\n".join(errors))

if not waveforms:
    st.stop()

metrics = [
    waveform_metrics(
        name=item["name"],
        time_s=item["time_s"],
        value=item["value"],
        gap_mm=gap_mm,
        resistance_ohm=resistance_ohm,
        threshold_fraction=threshold_fraction,
        baseline_mode="t<0" if baseline_mode == "t<0" else "first",
    )
    for item in waveforms
]
metrics_df = metrics_dataframe(metrics)

tab_single, tab_multi, tab_vi, tab_export, tab_header = st.tabs(
    [
        "Sinal único",
        "Múltiplos sinais",
        "V × I / potência",
        "Exportação",
        "Cabeçalho ISF",
    ]
)

with tab_single:
    selected_name = st.selectbox(
        "Selecione o sinal",
        [item["name"] for item in waveforms],
    )
    selected = next(item for item in waveforms if item["name"] == selected_name)
    selected_metrics = next(row for row in metrics if row["arquivo"] == selected_name)

    cols = st.columns(5)
    cols[0].metric("Vmax", _format_metric(selected_metrics["v_max"], "V"))
    cols[1].metric("Vmin", _format_metric(selected_metrics["v_min"], "V"))
    cols[2].metric("Vpp", _format_metric(selected_metrics["v_pp"], "V"))
    cols[3].metric("Campo", _format_metric(selected_metrics["campo_kv_cm"], "kV/cm"))
    cols[4].metric("Freq. FFT", _format_metric(selected_metrics["freq_fft_khz"], "kHz"))

    cols = st.columns(5)
    cols[0].metric("Pulso início", _format_metric(selected_metrics["pulso_inicio_us"], "µs"))
    cols[1].metric("Pulso fim", _format_metric(selected_metrics["pulso_fim_us"], "µs"))
    cols[2].metric("Largura", _format_metric(selected_metrics["largura_pulso_us"], "µs"))
    cols[3].metric("τ decaimento", _format_metric(selected_metrics["tau_decaimento_us"], "µs"))
    cols[4].metric("Energia aprox.", _format_metric(selected_metrics["energia_resistiva_j"], "J"))

    corrected = st.checkbox("Subtrair linha de base no gráfico", value=False)
    fig = plot_waveforms([selected], corrected=corrected, max_points=max_plot_points)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Métricas completas")
    st.dataframe(
        pd.DataFrame([selected_metrics]).T.rename(columns={0: "valor"}),
        use_container_width=True,
    )

with tab_multi:
    st.subheader("Comparação de formas de onda")
    col_a, col_b = st.columns(2)
    normalize = col_a.checkbox("Normalizar pelo pico absoluto", value=False)
    corrected_multi = col_b.checkbox("Subtrair linha de base", value=False, key="corrected_multi")

    fig = plot_waveforms(
        waveforms,
        normalize=normalize,
        corrected=corrected_multi,
        max_points=max_plot_points,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tabela comparativa")
    st.dataframe(metrics_df, use_container_width=True)

with tab_vi:
    st.subheader("Análise tensão × corrente")

    if len(waveforms) < 2:
        st.warning("Carregue pelo menos dois arquivos: um canal de tensão e um canal de corrente.")
    else:
        col1, col2, col3 = st.columns(3)
        voltage_name = col1.selectbox("Canal de tensão", [item["name"] for item in waveforms], index=0)
        current_name = col2.selectbox("Canal de corrente", [item["name"] for item in waveforms], index=min(1, len(waveforms) - 1))
        current_scale = col3.number_input(
            "Fator do canal de corrente (A por unidade lida)",
            min_value=1e-12,
            value=1.0,
            step=0.1,
            format="%.6g",
            help="Use 1 se o arquivo já estiver em ampères. Se estiver em volts de shunt/probe, informe A/V.",
        )

        voltage_item = next(item for item in waveforms if item["name"] == voltage_name)
        current_item = next(item for item in waveforms if item["name"] == current_name)

        t, v, i = align_current_to_voltage(
            voltage_item["time_s"],
            voltage_item["value"],
            current_item["time_s"],
            current_item["value"],
            current_scale_a_per_unit=current_scale,
        )
        p = v * i
        vi = vi_metrics(t, v, i)

        cols = st.columns(4)
        cols[0].metric("Imax", _format_metric(vi["i_max"], "A"))
        cols[1].metric("Imin", _format_metric(vi["i_min"], "A"))
        cols[2].metric("Pmax", _format_metric(vi["p_max_w"], "W"))
        cols[3].metric("Energia ∫Pdt", _format_metric(vi["energia_j"], "J"))

        t_plot, p_plot = decimate_for_plot(t, p, max_points=max_plot_points)
        fig_p = go.Figure()
        fig_p.add_trace(
            go.Scattergl(x=t_plot * 1e6, y=p_plot, mode="lines", name="P(t)=V(t)I(t)")
        )
        fig_p.update_layout(
            height=500,
            xaxis_title="Tempo (µs)",
            yaxis_title="Potência (W)",
            hovermode="x unified",
            margin=dict(l=40, r=20, t=40, b=40),
        )
        fig_p.update_xaxes(showgrid=True)
        fig_p.update_yaxes(showgrid=True)
        st.plotly_chart(fig_p, use_container_width=True)

        vi_df = pd.DataFrame({"tempo_s": t, "tempo_us": t * 1e6, "tensao_v": v, "corrente_a": i, "potencia_w": p})
        st.download_button(
            "Baixar V-I-P em CSV",
            data=vi_df.to_csv(index=False).encode("utf-8"),
            file_name="analise_v_i_p.csv",
            mime="text/csv",
        )

with tab_export:
    st.subheader("Exportação")
    st.download_button(
        "Baixar métricas em CSV",
        data=metrics_df.to_csv(index=False).encode("utf-8"),
        file_name="metricas_isf.csv",
        mime="text/csv",
    )

    export_name = st.selectbox(
        "Exportar forma de onda",
        [item["name"] for item in waveforms],
        key="export_waveform",
    )
    export_item = next(item for item in waveforms if item["name"] == export_name)

    st.download_button(
        "Baixar forma de onda em CSV",
        data=waveform_csv_bytes(export_item),
        file_name=Path(export_name).with_suffix(".csv").name,
        mime="text/csv",
    )

with tab_header:
    selected_header_name = st.selectbox(
        "Selecione o arquivo",
        [item["name"] for item in waveforms],
        key="header_select",
    )
    header_item = next(item for item in waveforms if item["name"] == selected_header_name)

    st.subheader("Metadados extraídos")
    st.json(header_item["metadata"])

    st.subheader("Cabeçalho bruto")
    st.text_area(
        "Cabeçalho",
        header_item["header"],
        height=350,
    )
