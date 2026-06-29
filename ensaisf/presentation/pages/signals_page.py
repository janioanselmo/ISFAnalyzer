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

def render_signals_page(
    *,
    waveforms: list[dict],
    gap_mm: float,
    resistance_ohm: float,
    threshold_fraction: float,
    baseline_mode: str,
    max_plot_points: int,
    ring_start_us: float,
    ring_end_us: float,
) -> None:
    st.subheader("Sinais")
    metrics, metrics_df = build_waveform_metrics_table(
        waveforms,
        gap_mm=gap_mm,
        resistance_ohm=resistance_ohm,
        threshold_fraction=threshold_fraction,
        baseline_mode=baseline_mode,
    )
    control_cols = st.columns(5)
    signal_filter = control_cols[0].selectbox(
        "Tipo",
        ["Todos", "Tensão", "Corrente", "Não classificado"],
        key="signals_role_filter_v040",
        help="Filtro visual. A classificação vem automaticamente do nome TXXXXCH1/CH2.",
    )
    role_filter_map = {
        "Todos": None,
        "Tensão": "voltage",
        "Corrente": "current",
        "Não classificado": "unknown",
    }
    signal_options = names_for_role(waveforms, role_filter_map[signal_filter])
    current_selection = list(st.session_state.get("signals_selected_v0314", signal_options))
    current_selection = [name for name in current_selection if name in signal_options]
    if not current_selection:
        current_selection = signal_options
    st.session_state["signals_selected_v0314"] = current_selection
    selected_names = control_cols[1].multiselect(
        "Arquivos",
        signal_options,
        default=current_selection,
        key="signals_selected_v0314",
        format_func=lambda name: _format_signal_label(name, waveforms),
    )
    normalize = control_cols[2].checkbox(
        "Normalizar",
        value=False,
        key="signals_normalize_v026",
        help="Divide cada sinal pelo próprio pico absoluto.",
    )
    corrected_overview = control_cols[3].checkbox(
        "Remover baseline",
        value=True,
        key="signals_corrected_v026",
    )
    use_custom_window = control_cols[4].checkbox(
        "Recortar janela",
        value=False,
        key="signals_window_enable_v026",
    )

    if use_custom_window:
        win_cols = st.columns(2)
        overview_start_us = win_cols[0].number_input(
            "Início (µs)",
            value=ring_start_us,
            step=1.0,
            key="signals_start_us_v026",
        )
        overview_end_us = win_cols[1].number_input(
            "Fim (µs)",
            value=ring_end_us,
            step=1.0,
            key="signals_end_us_v026",
        )
    else:
        overview_start_us = None
        overview_end_us = None

    selected_waveforms = [item for item in waveforms if item["name"] in selected_names]
    if not selected_waveforms:
        st.warning("Selecione pelo menos um arquivo.")
    else:
        fig = plot_waveforms(
            selected_waveforms,
            normalize=normalize,
            corrected=corrected_overview,
            baseline_mode=baseline_mode,
            max_points=max_plot_points,
            start_us=overview_start_us,
            end_us=overview_end_us,
        )
        st.plotly_chart(fig, width="stretch", key="signals_waveform_chart_v026")

    selected_metric_name = _select_signal_name(
        st,
        "Resumo do arquivo",
        [item["name"] for item in sort_items_by_pulse(waveforms)],
        "signals_metric_file_v0314",
        waveforms,
        preferred_index=0,
    )
    selected_metrics = next(row for row in metrics if row["arquivo"] == selected_metric_name)
    cols = st.columns(5)
    cols[0].metric("Vmax", _format_metric(selected_metrics["v_max"], "V"))
    cols[1].metric("Vmin", _format_metric(selected_metrics["v_min"], "V"))
    cols[2].metric("Vpp", _format_metric(selected_metrics["v_pp"], "V"))
    cols[3].metric("Campo", _format_metric(selected_metrics["campo_kv_cm"], "kV/cm"))
    cols[4].metric("Freq. FFT", _format_metric(selected_metrics["freq_fft_khz"], "kHz"))

    with st.expander("Tabela completa", expanded=False):
        st.dataframe(metrics_df, width="stretch")
