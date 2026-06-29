from __future__ import annotations

from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:  # optional component; app still runs without image-click selection
    streamlit_image_coordinates = None

from ensaisf.application.metrics_tables import *
from ensaisf.application.power_analysis import *
from ensaisf.channels import (
    matching_current_for_voltage,
    names_for_role,
    sort_items_by_pulse,
)
from ensaisf.domain.channel_metrics import *
from ensaisf.domain.envelope_analysis import *
from ensaisf.infrastructure.csv_exporter import *
from ensaisf.presentation.formatting import *
from ensaisf.presentation.plots import *
from ensaisf.presentation.theme import ENVELOPE_IMAGE_MAX_POINTS, POWER_PLOT_MAX_POINTS
from ensaisf.analysis import (
    compare_ringdown_metrics,
    decimate_for_plot,
    resonance_shift_score,
    ringdown_metrics,
    waveform_similarity_metrics,
)

def render_comparison_page(
    *,
    waveforms: list[dict],
    gap_mm: float,
    resistance_ohm: float,
    threshold_fraction: float,
    baseline_mode: str,
    max_plot_points: int,
    ring_start_us: float,
    ring_end_us: float,
    peak_threshold_fraction: float,
    min_peak_distance_us: float,
) -> None:
    st.subheader("Comparação")
    st.caption(
        "Escolha o tipo de par. A tela evita misturar métricas de unidades diferentes: "
        "V×I mostra atraso/correlação; Tensão×Tensão e Corrente×Corrente mostram também Δ de ringing."
    )
    ring_cols = st.columns(3)
    comparison_kind = ring_cols[0].selectbox(
        "Tipo de comparação",
        ["Tensão × Corrente", "Corrente × Corrente", "Tensão × Tensão", "Personalizada"],
        key="comparison_kind_v040",
    )
    cmp_start_us = ring_cols[1].number_input(
        "Início da janela (µs)",
        value=ring_start_us,
        step=1.0,
        format="%.3f",
        key="comparison_start_us_v026",
    )
    cmp_end_us = ring_cols[2].number_input(
        "Fim da janela (µs)",
        value=ring_end_us,
        step=1.0,
        format="%.3f",
        key="comparison_end_us_v026",
    )
    if len(waveforms) < 2:
        st.warning("Carregue pelo menos dois arquivos para comparar.")
    else:
        voltage_names = names_for_role(waveforms, "voltage")
        current_names = names_for_role(waveforms, "current")
        all_names = [item["name"] for item in sort_items_by_pulse(waveforms)]

        if comparison_kind == "Tensão × Corrente":
            left_options = voltage_names
            right_options = current_names
            left_label = "Tensão (CH1)"
            right_label = "Corrente (CH2)"
        elif comparison_kind == "Corrente × Corrente":
            left_options = current_names
            right_options = current_names
            left_label = "Corrente de referência"
            right_label = "Corrente comparada"
        elif comparison_kind == "Tensão × Tensão":
            left_options = voltage_names
            right_options = voltage_names
            left_label = "Tensão de referência"
            right_label = "Tensão comparada"
        else:
            left_options = all_names
            right_options = all_names
            left_label = "Sinal de referência"
            right_label = "Sinal comparado"

        if not left_options or not right_options:
            st.warning("Não há arquivos suficientes para este tipo de comparação com a regra CH1=tensão e CH2=corrente.")
        else:
            col_ba_1, col_ba_2 = st.columns(2)
            before_name = _select_signal_name(
                col_ba_1,
                left_label,
                left_options,
                "comparison_before_v040",
                waveforms,
                preferred_index=0,
            )
            preferred_right = 1 if len(right_options) > 1 else 0
            after_name = _select_signal_name(
                col_ba_2,
                right_label,
                right_options,
                "comparison_after_v040",
                waveforms,
                preferred_index=preferred_right,
            )
            if before_name is None or after_name is None:
                st.stop()
            if before_name == after_name:
                st.warning("Selecione dois arquivos diferentes para uma comparação física útil.")

            before_item = _find_item_by_name(waveforms, before_name)
            after_item = _find_item_by_name(waveforms, after_name)
            same_role = before_item.get("role") == after_item.get("role") and before_item.get("role") != "unknown"

            similarity = waveform_similarity_metrics(
                before_name,
                before_item["time_s"],
                before_item["value"],
                after_name,
                after_item["time_s"],
                after_item["value"],
                start_us=cmp_start_us,
                end_us=cmp_end_us,
                baseline_mode=baseline_mode,
            )

            if same_role:
                before_ring = ringdown_metrics(
                    before_name,
                    before_item["time_s"],
                    before_item["value"],
                    start_us=cmp_start_us,
                    end_us=cmp_end_us,
                    baseline_mode=baseline_mode,
                    resistance_ohm=resistance_ohm,
                    peak_threshold_fraction=peak_threshold_fraction,
                    min_peak_distance_us=min_peak_distance_us,
                )
                after_ring = ringdown_metrics(
                    after_name,
                    after_item["time_s"],
                    after_item["value"],
                    start_us=cmp_start_us,
                    end_us=cmp_end_us,
                    baseline_mode=baseline_mode,
                    resistance_ohm=resistance_ohm,
                    peak_threshold_fraction=peak_threshold_fraction,
                    min_peak_distance_us=min_peak_distance_us,
                )
                compare_df = compare_ringdown_metrics(before_ring, after_ring)
                shift_score = resonance_shift_score(compare_df)

                cols = st.columns(5)
                metric_map = {row["metrica"]: row["delta_percent"] for _, row in compare_df.iterrows()}
                cols[0].metric("Δ período", _format_metric(metric_map.get("period_peaks_us"), "%"))
                cols[1].metric("Δ frequência", _format_metric(metric_map.get("freq_damped_khz"), "%"))
                cols[2].metric("Δ τ", _format_metric(metric_map.get("tau_envelope_us"), "%"))
                cols[3].metric("Δ Q", _format_metric(metric_map.get("quality_factor_q"), "%"))
                cols[4].metric("Δ energia", _format_metric(metric_map.get("ring_energy_resistive_j"), "%"))

                cols = st.columns(4)
                cols[0].metric("Shift score", _format_metric(shift_score, "%"))
                cols[1].metric("Correlação", _format_metric(similarity["pearson_r"], ""))
                cols[2].metric("NRMSE", _format_metric(similarity["nrmse"], ""))
                cols[3].metric("Atraso", _format_metric(similarity["delay_xcorr_us"], "µs"))
            else:
                st.info(
                    "Par com unidades diferentes. Por isso, a comparação aqui fica em atraso/correlação "
                    "e forma normalizada. Energia, impedância e fase V×I ficam exclusivamente em Potência."
                )
                cols = st.columns(4)
                cols[0].metric("Correlação", _format_metric(similarity["pearson_r"], ""))
                cols[1].metric("NRMSE", _format_metric(similarity["nrmse"], ""))
                cols[2].metric("Atraso", _format_metric(similarity["delay_xcorr_us"], "µs"))
                cols[3].metric("xcorr", _format_metric(similarity["xcorr_peak"], ""))
                compare_df = pd.DataFrame([similarity])

            normalize_ba = st.checkbox(
                "Normalizar curvas",
                value=not same_role,
                key="comparison_normalize_v040",
                help="Recomendado para V×I, porque tensão e corrente possuem escalas físicas diferentes.",
            )
            fig_ba = plot_waveforms(
                [before_item, after_item],
                normalize=normalize_ba,
                corrected=True,
                baseline_mode=baseline_mode,
                max_points=max_plot_points,
                start_us=cmp_start_us,
                end_us=cmp_end_us,
            )
            st.plotly_chart(fig_ba, width="stretch", key="comparison_overlay_chart_v040")
            st.dataframe(compare_df, width="stretch")
            st.download_button(
                "Baixar comparação em CSV",
                data=compare_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacao_sinais.csv",
                mime="text/csv",
                key="download_comparison_v040",
            )

    st.divider()
    st.markdown("**Tendência automática da sequência carregada**")
    st.caption(
        "Esta análise resume a evolução por pulso sem repetir as métricas das outras telas: "
        "decaimento médio de amplitude para tensão e acréscimo médio para corrente, quando existirem CH1/CH2 suficientes."
    )
    _, trend_metrics_df = build_waveform_metrics_table(
        waveforms,
        gap_mm=gap_mm,
        resistance_ohm=resistance_ohm,
        threshold_fraction=threshold_fraction,
        baseline_mode=baseline_mode,
    )
    trend_df = sequence_trend_table(trend_metrics_df, waveforms)
    if trend_df.empty:
        st.info("Carregue pelo menos dois pulsos do mesmo tipo de sinal para estimar tendência por sequência.")
    else:
        trend_cols = st.columns(2)
        voltage_trend = trend_df[trend_df["tipo_sinal"] == "Tensão"]
        current_trend = trend_df[trend_df["tipo_sinal"] == "Corrente"]
        if not voltage_trend.empty:
            row = voltage_trend.iloc[0]
            trend_cols[0].metric(
                "Tensão: média Δ pico/pulso",
                _format_metric(row["media_delta_pico_abs_por_pulso_%"], "%"),
            )
        else:
            trend_cols[0].metric("Tensão: média Δ pico/pulso", "—")
        if not current_trend.empty:
            row = current_trend.iloc[0]
            trend_cols[1].metric(
                "Corrente: média Δ pico/pulso",
                _format_metric(row["media_delta_pico_abs_por_pulso_%"], "%"),
            )
        else:
            trend_cols[1].metric("Corrente: média Δ pico/pulso", "—")

        plot_cols = st.columns(2)
        plot_cols[0].plotly_chart(
            plot_sequence_trend(trend_metrics_df, waveforms, "Tensão"),
            width="stretch",
            key="trend_voltage_chart_v040",
        )
        plot_cols[1].plotly_chart(
            plot_sequence_trend(trend_metrics_df, waveforms, "Corrente"),
            width="stretch",
            key="trend_current_chart_v040",
        )
        st.dataframe(trend_df, width="stretch")
        st.download_button(
            "Baixar tendência da sequência em CSV",
            data=trend_df.to_csv(index=False).encode("utf-8"),
            file_name="tendencia_sequencia_pulsos.csv",
            mime="text/csv",
            key="download_sequence_trend_v040",
        )
