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
from ensaisf.presentation.theme import (
    ENVELOPE_IMAGE_MAX_POINTS,
    POWER_PLOT_MAX_POINTS,
    SERIES_COLORS_HEX,
)
from ensaisf.analysis import (
    compare_ringdown_metrics,
    decimate_for_plot,
    resonance_shift_score,
    ringdown_metrics,
    waveform_similarity_metrics,
)

def render_power_page(
    *,
    waveforms: list[dict],
    max_plot_points: int,
) -> None:
    st.subheader("Potência")
    st.caption(
        "Use exatamente 2 arquivos: um canal de tensão e um canal de corrente. "
        "Esta seleção é independente das demais abas."
    )

    voltage_options = names_for_role(waveforms, "voltage")
    current_options = names_for_role(waveforms, "current")
    if len(waveforms) < 2 or not voltage_options or not current_options:
        st.warning(
            "Carregue pelo menos um CH1 (tensão) e um CH2 (corrente). "
            "A classificação automática usa TXXXXCH1 e TXXXXCH2 no nome do arquivo."
        )
    else:
        col1, col2, col3 = st.columns(3)
        voltage_name = _select_signal_name(
            col1,
            "Tensão (CH1)",
            voltage_options,
            "power_voltage_v040",
            waveforms,
            preferred_index=0,
        )
        voltage_item_for_match = _find_item_by_name(waveforms, voltage_name) if voltage_name else None
        matched_current = matching_current_for_voltage(voltage_item_for_match, waveforms) if voltage_item_for_match else None
        preferred_current_index = 0
        if matched_current and matched_current["name"] in current_options:
            preferred_current_index = current_options.index(matched_current["name"])
        current_name = _select_signal_name(
            col2,
            "Corrente (CH2)",
            current_options,
            "power_current_v040",
            waveforms,
            preferred_index=preferred_current_index,
        )
        if voltage_name == current_name:
            st.warning("Selecione canais diferentes para tensão e corrente antes de interpretar P(t)=V(t)I(t).")
        current_scale = col3.number_input(
            "Escala de corrente (A/unidade)",
            min_value=1e-12,
            value=1.0,
            step=0.1,
            format="%.6g",
            help="Use 1 se o canal já estiver em ampères. Se estiver em V de probe/shunt, informe A/V.",
            key="power_current_scale_v026",
        )

        voltage_item = next(item for item in waveforms if item["name"] == voltage_name)
        current_item = next(item for item in waveforms if item["name"] == current_name)

        with st.spinner("Calculando potência e impedância..."):
            t, v, i, p, vi = get_power_analysis_cached(
                voltage_item,
                current_item,
                current_scale,
            )

        cols = st.columns(6)
        cols[0].metric("Imax", _format_metric(vi.get("i_max"), "A"))
        cols[1].metric("Imin", _format_metric(vi.get("i_min"), "A"))
        cols[2].metric("Pmax", _format_metric(vi.get("p_max_w"), "W"))
        cols[3].metric("Energia", _format_metric(vi.get("energia_j"), "J"))
        cols[4].metric("Carga", _format_metric(vi.get("carga_c"), "C"))
        cols[5].metric("R efetiva", _format_metric(vi.get("resistencia_efetiva_ohm"), "Ω"))

        cols = st.columns(4)
        cols[0].metric("|Z| FFT", _format_metric(vi.get("impedancia_fft_mag_ohm"), "Ω"))
        cols[1].metric("Fase Z", _format_metric(vi.get("impedancia_fft_phase_deg"), "°"))
        cols[2].metric("Delay V-I", _format_metric(vi.get("delay_v_i_xcorr_us"), "µs"))
        cols[3].metric("xcorr", _format_metric(vi.get("xcorr_v_i_peak"), ""))

        t_plot, p_plot = decimate_for_plot(t, p, max_points=min(max_plot_points, POWER_PLOT_MAX_POINTS))
        fig_p = go.Figure()
        fig_p.add_trace(
            go.Scattergl(
                x=t_plot * 1e6,
                y=p_plot,
                mode="lines",
                name="P(t)=V(t)I(t)",
                line=dict(color=SERIES_COLORS_HEX[0]),
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
        st.plotly_chart(fig_p, width="stretch", key="power_chart_v026")
        st.dataframe(pd.DataFrame([vi]).T.rename(columns={0: "valor"}), width="stretch")
        csv_key = (
            "power_vip_csv_v037",
            voltage_item.get("data_hash"),
            current_item.get("data_hash"),
            round(float(current_scale), 12),
        )
        if st.button("Preparar CSV V-I-P", key="prepare_power_csv_v037"):
            st.session_state[csv_key] = vip_csv_bytes(t, v, i, p)
        if csv_key in st.session_state:
            st.download_button(
                "Baixar V-I-P em CSV",
                data=st.session_state[csv_key],
                file_name="analise_v_i_p.csv",
                mime="text/csv",
                key="download_power_csv_v037",
            )
        else:
            st.caption("O CSV completo de V-I-P é gerado sob demanda para manter a aba Potência mais rápida.")
