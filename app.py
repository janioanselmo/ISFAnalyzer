from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ensaisf.analysis import (
    align_current_to_voltage,
    compare_ringdown_metrics,
    decimate_for_plot,
    metrics_dataframe,
    resonance_shift_score,
    ringdown_metrics,
    ringdown_peak_table,
    slice_window_us,
    subtract_baseline,
    vi_metrics,
    waveform_metrics,
    waveform_similarity_metrics,
)
from ensaisf.isf_parser import read_isf_bytes


st.set_page_config(
    page_title="ENSA ISF Analyzer",
    page_icon="⚡",
    layout="wide",
)


APP_VERSION = "0.2.1-signal-tabs"


def _format_metric(value: float, unit: str = "", precision: int = 4) -> str:
    if value is None:
        return "—"
    try:
        if not np.isfinite(float(value)):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{float(value):.{precision}g} {unit}".strip()


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
    baseline_mode: str = "t<0",
    max_points: int = 30_000,
    start_us: float | None = None,
    end_us: float | None = None,
):
    fig = go.Figure()

    for item in waveforms:
        t = item["time_s"]
        y = item["value"].astype(float)

        if corrected:
            y, _baseline = subtract_baseline(t, y, mode=baseline_mode)

        if start_us is not None or end_us is not None:
            t, y, _indices = slice_window_us(t, y, start_us, end_us)

        if len(t) == 0:
            continue

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


def plot_ringdown(
    item: dict,
    start_us: float,
    end_us: float,
    baseline_mode: str,
    peak_threshold_fraction: float,
    min_peak_distance_us: float,
    max_points: int,
):
    t = item["time_s"]
    y, _baseline = subtract_baseline(t, item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(t, y, start_us, end_us)
    peak_df = ringdown_peak_table(
        t,
        item["value"],
        start_us=start_us,
        end_us=end_us,
        baseline_mode=baseline_mode,
        peak_threshold_fraction=peak_threshold_fraction,
        min_peak_distance_us=min_peak_distance_us,
    )

    fig = go.Figure()
    if len(t_win):
        t_plot, y_plot = decimate_for_plot(t_win, y_win, max_points=max_points)
        fig.add_trace(
            go.Scattergl(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name="sinal corrigido",
            )
        )

    if not peak_df.empty:
        pos = peak_df[peak_df["tipo"] == "positivo"]
        neg = peak_df[peak_df["tipo"] == "negativo"]
        fig.add_trace(
            go.Scatter(
                x=pos["tempo_us"],
                y=pos["amplitude"],
                mode="markers",
                name="picos positivos",
                marker=dict(size=8, symbol="circle"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=neg["tempo_us"],
                y=neg["amplitude"],
                mode="markers",
                name="picos negativos",
                marker=dict(size=8, symbol="x"),
            )
        )

    fig.update_layout(
        height=560,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude corrigida",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=40, b=40),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig, peak_df


def waveform_csv_bytes(item: dict) -> bytes:
    df = pd.DataFrame(
        {
            "tempo_s": item["time_s"],
            "tempo_us": item["time_s"] * 1e6,
            "amplitude": item["value"],
        }
    )
    return df.to_csv(index=False).encode("utf-8")


def vip_csv_bytes(t: np.ndarray, v: np.ndarray, i: np.ndarray, p: np.ndarray) -> bytes:
    df = pd.DataFrame(
        {
            "tempo_s": t,
            "tempo_us": t * 1e6,
            "tensao_v": v,
            "corrente_a": i,
            "potencia_w": p,
        }
    )
    return df.to_csv(index=False).encode("utf-8")


st.title("⚡ ENSA ISF Analyzer")
st.caption(
    f"Mini-IDE para Tektronix .ISF | versão {APP_VERSION} | foco: pulso, ringing, ressonância e eletroporação"
)

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

    baseline_mode_label = st.selectbox(
        "Linha de base",
        ["t<0", "primeiros 10%"],
        index=0,
    )
    baseline_mode = "t<0" if baseline_mode_label == "t<0" else "first"

    max_plot_points = st.slider(
        "Máximo de pontos por curva no gráfico",
        min_value=5_000,
        max_value=120_000,
        value=30_000,
        step=5_000,
    )

    st.divider()
    st.subheader("Janela de ringing")
    ring_start_us = st.number_input(
        "Início da janela de ringing (µs)",
        value=-90.0,
        step=1.0,
        format="%.3f",
        help="Ajuste para pegar os picos finais da oscilação natural, após o disparo principal.",
    )
    ring_end_us = st.number_input(
        "Fim da janela de ringing (µs)",
        value=240.0,
        step=1.0,
        format="%.3f",
    )
    peak_threshold_fraction = st.slider(
        "Limiar dos picos de ringing (% do maior pico na janela)",
        min_value=1,
        max_value=50,
        value=5,
        step=1,
    ) / 100.0
    min_peak_distance_us = st.number_input(
        "Distância mínima entre picos (µs)",
        min_value=0.001,
        value=5.0,
        step=0.5,
        format="%.3f",
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
        baseline_mode=baseline_mode,
    )
    for item in waveforms
]
metrics_df = metrics_dataframe(metrics)

ring_metrics = [
    ringdown_metrics(
        name=item["name"],
        time_s=item["time_s"],
        value=item["value"],
        start_us=ring_start_us,
        end_us=ring_end_us,
        baseline_mode=baseline_mode,
        resistance_ohm=resistance_ohm,
        peak_threshold_fraction=peak_threshold_fraction,
        min_peak_distance_us=min_peak_distance_us,
    )
    for item in waveforms
]
ring_metrics_df = metrics_dataframe(ring_metrics)



tab_signal, tab_export, tab_header = st.tabs(
    [
        "Análise de sinais",
        "Exportação",
        "Cabeçalho",
    ]
)

with tab_signal:
    st.subheader("Análise de sinais")
    st.caption(
        "Área única para sinal individual, múltiplos sinais, ressonância/ringing, "
        "comparação antes × depois e análise V × I / potência."
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Arquivos carregados", len(waveforms))
    summary_cols[1].metric("Gap", _format_metric(gap_mm, "mm"))
    summary_cols[2].metric("Carga equivalente", _format_metric(resistance_ohm, "Ω"))
    summary_cols[3].metric(
        "Janela de ringing",
        f"{ring_start_us:g} a {ring_end_us:g} µs",
    )

    analysis_mode = st.radio(
        "Escolha a operação",
        [
            "Sinal único",
            "Múltiplos sinais",
            "Ressonância / ringing",
            "Antes × depois",
            "V × I / potência",
        ],
        horizontal=True,
        key="signal_analysis_mode_v021",
    )

    if analysis_mode == "Sinal único":
        selected_name = st.selectbox(
            "Selecione o sinal",
            [item["name"] for item in waveforms],
            key="single_select_signal_v021",
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
        cols[3].metric("Energia aprox.", _format_metric(selected_metrics["energia_resistiva_j"], "J"))
        cols[4].metric("RMS", _format_metric(selected_metrics["rms_corrigido"], "V"))

        corrected = st.checkbox(
            "Subtrair linha de base no gráfico",
            value=False,
            key="single_corrected_v021",
        )
        fig = plot_waveforms(
            [selected],
            corrected=corrected,
            baseline_mode=baseline_mode,
            max_points=max_plot_points,
        )
        st.plotly_chart(fig, use_container_width=True, key="single_waveform_chart_v021")

        st.subheader("Métricas completas")
        st.dataframe(
            pd.DataFrame([selected_metrics]).T.rename(columns={0: "valor"}),
            use_container_width=True,
        )

    elif analysis_mode == "Múltiplos sinais":
        st.subheader("Comparação de formas de onda")
        col_a, col_b, col_c = st.columns(3)
        normalize = col_a.checkbox(
            "Normalizar pelo pico absoluto",
            value=False,
            key="multi_normalize_v021",
        )
        corrected_multi = col_b.checkbox(
            "Subtrair linha de base",
            value=False,
            key="multi_corrected_v021",
        )
        only_ring_window = col_c.checkbox(
            "Mostrar só janela de ringing",
            value=False,
            key="multi_only_ring_v021",
        )

        fig = plot_waveforms(
            waveforms,
            normalize=normalize,
            corrected=corrected_multi,
            baseline_mode=baseline_mode,
            max_points=max_plot_points,
            start_us=ring_start_us if only_ring_window else None,
            end_us=ring_end_us if only_ring_window else None,
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            key="multi_waveform_comparison_chart_v021",
        )

        st.subheader("Tabela comparativa geral")
        st.dataframe(metrics_df, use_container_width=True)

        st.subheader("Tabela comparativa de ringing")
        st.dataframe(ring_metrics_df, use_container_width=True)

    elif analysis_mode == "Ressonância / ringing":
        st.subheader("Análise da oscilação natural / ringdown")
        ring_name = st.selectbox(
            "Selecione o sinal para ringing",
            [item["name"] for item in waveforms],
            key="ring_select_signal_v021",
        )
        ring_item = next(item for item in waveforms if item["name"] == ring_name)
        ring_row = next(row for row in ring_metrics if row["arquivo"] == ring_name)

        cols = st.columns(6)
        cols[0].metric("Período", _format_metric(ring_row["period_peaks_us"], "µs"))
        cols[1].metric("Freq. amortecida", _format_metric(ring_row["freq_damped_khz"], "kHz"))
        cols[2].metric("τ envelope", _format_metric(ring_row["tau_envelope_us"], "µs"))
        cols[3].metric("ζ", _format_metric(ring_row["damping_ratio_zeta"], ""))
        cols[4].metric("Q", _format_metric(ring_row["quality_factor_q"], ""))
        cols[5].metric("Energia ringing", _format_metric(ring_row["ring_energy_resistive_j"], "J"))

        cols = st.columns(5)
        cols[0].metric("Decremento log.", _format_metric(ring_row["log_decrement"], ""))
        cols[1].metric("Decaimento/ciclo", _format_metric(ring_row["decay_per_cycle_percent"], "%"))
        cols[2].metric("R² envelope", _format_metric(ring_row["envelope_r2"], ""))
        cols[3].metric("Picos detectados", _format_metric(ring_row["n_extrema"], "", precision=0))
        cols[4].metric("Assimetria +/−", _format_metric(ring_row["asymmetry_pos_neg"], ""))

        fig_ring, peak_df = plot_ringdown(
            ring_item,
            start_us=ring_start_us,
            end_us=ring_end_us,
            baseline_mode=baseline_mode,
            peak_threshold_fraction=peak_threshold_fraction,
            min_peak_distance_us=min_peak_distance_us,
            max_points=max_plot_points,
        )
        st.plotly_chart(fig_ring, use_container_width=True, key="ringdown_chart_v021")

        col_table_a, col_table_b = st.columns(2)
        with col_table_a:
            st.subheader("Métricas de ringing")
            st.dataframe(
                pd.DataFrame([ring_row]).T.rename(columns={0: "valor"}),
                use_container_width=True,
            )
        with col_table_b:
            st.subheader("Picos detectados")
            st.dataframe(peak_df, use_container_width=True)

    elif analysis_mode == "Antes × depois":
        st.subheader("Comparação antes × depois da eletroporação")
        if len(waveforms) < 2:
            st.warning("Carregue pelo menos dois arquivos para comparar antes e depois.")
        else:
            col_ba_1, col_ba_2 = st.columns(2)
            before_name = col_ba_1.selectbox(
                "Sinal ANTES",
                [item["name"] for item in waveforms],
                index=0,
                key="before_after_before_select_v021",
            )
            after_name = col_ba_2.selectbox(
                "Sinal DEPOIS",
                [item["name"] for item in waveforms],
                index=min(1, len(waveforms) - 1),
                key="before_after_after_select_v021",
            )
            before_item = next(item for item in waveforms if item["name"] == before_name)
            after_item = next(item for item in waveforms if item["name"] == after_name)
            before_ring = next(row for row in ring_metrics if row["arquivo"] == before_name)
            after_ring = next(row for row in ring_metrics if row["arquivo"] == after_name)

            compare_df = compare_ringdown_metrics(before_ring, after_ring)
            shift_score = resonance_shift_score(compare_df)
            similarity = waveform_similarity_metrics(
                before_name,
                before_item["time_s"],
                before_item["value"],
                after_name,
                after_item["time_s"],
                after_item["value"],
                start_us=ring_start_us,
                end_us=ring_end_us,
                baseline_mode=baseline_mode,
            )

            cols = st.columns(5)
            period_delta = compare_df.loc[
                compare_df["metrica"] == "period_peaks_us", "delta_percent"
            ].iloc[0]
            freq_delta = compare_df.loc[
                compare_df["metrica"] == "freq_damped_khz", "delta_percent"
            ].iloc[0]
            tau_delta = compare_df.loc[
                compare_df["metrica"] == "tau_envelope_us", "delta_percent"
            ].iloc[0]
            q_delta = compare_df.loc[
                compare_df["metrica"] == "quality_factor_q", "delta_percent"
            ].iloc[0]
            energy_delta = compare_df.loc[
                compare_df["metrica"] == "ring_energy_resistive_j", "delta_percent"
            ].iloc[0]
            cols[0].metric("Δ período", _format_metric(period_delta, "%"))
            cols[1].metric("Δ frequência", _format_metric(freq_delta, "%"))
            cols[2].metric("Δ τ", _format_metric(tau_delta, "%"))
            cols[3].metric("Δ Q", _format_metric(q_delta, "%"))
            cols[4].metric("Δ energia", _format_metric(energy_delta, "%"))

            cols = st.columns(4)
            cols[0].metric("Resonance shift score", _format_metric(shift_score, "%"))
            cols[1].metric("Correlação", _format_metric(similarity["pearson_r"], ""))
            cols[2].metric("NRMSE", _format_metric(similarity["nrmse"], ""))
            cols[3].metric("Atraso xcorr", _format_metric(similarity["delay_xcorr_us"], "µs"))

            normalize_ba = st.checkbox(
                "Normalizar curvas antes/depois pelo pico absoluto",
                value=False,
                key="before_after_normalize_v021",
            )
            fig_ba = plot_waveforms(
                [before_item, after_item],
                normalize=normalize_ba,
                corrected=True,
                baseline_mode=baseline_mode,
                max_points=max_plot_points,
                start_us=ring_start_us,
                end_us=ring_end_us,
            )
            st.plotly_chart(
                fig_ba,
                use_container_width=True,
                key="before_after_overlay_chart_v021",
            )

            st.subheader("Tabela de variações do ringing")
            st.dataframe(compare_df, use_container_width=True)

            st.subheader("Métricas de similaridade de forma de onda")
            st.dataframe(
                pd.DataFrame([similarity]).T.rename(columns={0: "valor"}),
                use_container_width=True,
            )

            st.download_button(
                "Baixar comparação antes-depois em CSV",
                data=compare_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacao_antes_depois_ringdown.csv",
                mime="text/csv",
                key="download_before_after_csv_v021",
            )

    elif analysis_mode == "V × I / potência":
        st.subheader("Análise tensão × corrente")

        if len(waveforms) < 2:
            st.warning("Carregue pelo menos dois arquivos: um canal de tensão e um canal de corrente.")
        else:
            col1, col2, col3 = st.columns(3)
            voltage_name = col1.selectbox(
                "Canal de tensão",
                [item["name"] for item in waveforms],
                index=0,
                key="vi_voltage_select_v021",
            )
            current_name = col2.selectbox(
                "Canal de corrente",
                [item["name"] for item in waveforms],
                index=min(1, len(waveforms) - 1),
                key="vi_current_select_v021",
            )
            current_scale = col3.number_input(
                "Fator do canal de corrente (A por unidade lida)",
                min_value=1e-12,
                value=1.0,
                step=0.1,
                format="%.6g",
                help="Use 1 se o arquivo já estiver em ampères. Se estiver em volts de shunt/probe, informe A/V.",
                key="vi_current_scale_v021",
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

            cols = st.columns(6)
            cols[0].metric("Imax", _format_metric(vi.get("i_max"), "A"))
            cols[1].metric("Imin", _format_metric(vi.get("i_min"), "A"))
            cols[2].metric("Pmax", _format_metric(vi.get("p_max_w"), "W"))
            cols[3].metric("Energia ∫Pdt", _format_metric(vi.get("energia_j"), "J"))
            cols[4].metric("Carga ∫Idt", _format_metric(vi.get("carga_c"), "C"))
            cols[5].metric("R efetiva", _format_metric(vi.get("resistencia_efetiva_ohm"), "Ω"))

            cols = st.columns(4)
            cols[0].metric("|Z| FFT", _format_metric(vi.get("impedancia_fft_mag_ohm"), "Ω"))
            cols[1].metric("Fase Z FFT", _format_metric(vi.get("impedancia_fft_phase_deg"), "°"))
            cols[2].metric("Delay V-I", _format_metric(vi.get("delay_v_i_xcorr_us"), "µs"))
            cols[3].metric("xcorr V-I", _format_metric(vi.get("xcorr_v_i_peak"), ""))

            t_plot, p_plot = decimate_for_plot(t, p, max_points=max_plot_points)
            fig_p = go.Figure()
            fig_p.add_trace(
                go.Scattergl(
                    x=t_plot * 1e6,
                    y=p_plot,
                    mode="lines",
                    name="P(t)=V(t)I(t)",
                )
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
            st.plotly_chart(fig_p, use_container_width=True, key="vi_power_chart_v021")

            st.subheader("Métricas V-I-P")
            st.dataframe(
                pd.DataFrame([vi]).T.rename(columns={0: "valor"}),
                use_container_width=True,
            )

            st.download_button(
                "Baixar V-I-P em CSV",
                data=vip_csv_bytes(t, v, i, p),
                file_name="analise_v_i_p.csv",
                mime="text/csv",
                key="download_vip_csv_v021",
            )

with tab_export:
    st.subheader("Exportação")
    st.caption("Área dedicada para baixar métricas, ringing e formas de onda em CSV.")

    st.download_button(
        "Baixar métricas gerais em CSV",
        data=metrics_df.to_csv(index=False).encode("utf-8"),
        file_name="metricas_isf.csv",
        mime="text/csv",
        key="download_general_metrics_v021",
    )

    st.download_button(
        "Baixar métricas de ringing em CSV",
        data=ring_metrics_df.to_csv(index=False).encode("utf-8"),
        file_name="metricas_ringdown_resonancia.csv",
        mime="text/csv",
        key="download_ring_metrics_v021",
    )

    export_name = st.selectbox(
        "Exportar forma de onda",
        [item["name"] for item in waveforms],
        key="export_waveform_select_v021",
    )
    export_item = next(item for item in waveforms if item["name"] == export_name)

    st.download_button(
        "Baixar forma de onda em CSV",
        data=waveform_csv_bytes(export_item),
        file_name=Path(export_name).with_suffix(".csv").name,
        mime="text/csv",
        key="download_waveform_csv_v021",
    )

with tab_header:
    st.subheader("Cabeçalho")
    st.caption("Metadados extraídos do arquivo ISF e cabeçalho bruto do Tektronix.")

    selected_header_name = st.selectbox(
        "Selecione o arquivo",
        [item["name"] for item in waveforms],
        key="header_select_v021",
    )
    header_item = next(item for item in waveforms if item["name"] == selected_header_name)

    st.subheader("Metadados extraídos")
    st.json(header_item["metadata"])

    st.subheader("Cabeçalho bruto")
    st.text_area(
        "Cabeçalho",
        header_item["header"],
        height=350,
        key="raw_header_text_v021",
    )
