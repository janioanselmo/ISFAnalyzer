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
    role_counts,
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


from ensaisf.presentation.pages.signals_page import render_signals_page
from ensaisf.presentation.pages.envelope_page import render_envelope_page
from ensaisf.presentation.pages.comparison_page import render_comparison_page
from ensaisf.presentation.pages.power_page import render_power_page

def render_analysis_page(
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
    st.subheader("Análise de sinais")
    st.caption(
        "Escolha uma operação por vez. A tela mostra apenas os controles úteis para aquela análise."
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Arquivos", len(waveforms))
    summary_cols[1].metric("Gap", _format_metric(gap_mm, "mm"))
    summary_cols[2].metric("Carga", _format_metric(resistance_ohm, "Ω"))
    summary_cols[3].metric("Amostras", f"{sum(len(item['value']) for item in waveforms):,}".replace(",", "."))

    counts = role_counts(waveforms)
    st.caption(
        "Classificação automática: "
        f"{counts['voltage']} tensão (CH1), "
        f"{counts['current']} corrente (CH2), "
        f"{counts['unknown']} não classificado."
    )

    analysis_mode = st.radio(
        "Operação",
        ["Sinais", "Envelope", "Comparação", "Potência"],
        horizontal=True,
        key="signal_analysis_mode_v035",
        help=(
            "Sinais: visualizar curvas e métricas gerais. Envelope: selecionar picos por clique e ajustar decaimento. "
            "Comparação: antes/depois. Potência: análise V × I."
        ),
    )

    # Keep the active operation in session state, but do not rebuild the
    # image-click component just because the user navigated away and returned.
    # Recreating the component key on mode changes can make the image selector
    # disappear on some Streamlit/component versions until another button rerun.
    st.session_state["_previous_signal_analysis_mode_v038"] = analysis_mode


    if analysis_mode == "Sinais":
        render_signals_page(
            waveforms=waveforms,
            gap_mm=gap_mm,
            resistance_ohm=resistance_ohm,
            threshold_fraction=threshold_fraction,
            baseline_mode=baseline_mode,
            max_plot_points=max_plot_points,
            ring_start_us=ring_start_us,
            ring_end_us=ring_end_us,
        )
    elif analysis_mode == "Envelope":
        render_envelope_page(
            waveforms=waveforms,
            baseline_mode=baseline_mode,
            max_plot_points=max_plot_points,
            ring_start_us=ring_start_us,
            ring_end_us=ring_end_us,
            peak_threshold_fraction=peak_threshold_fraction,
            min_peak_distance_us=min_peak_distance_us,
        )
    elif analysis_mode == "Comparação":
        render_comparison_page(
            waveforms=waveforms,
            gap_mm=gap_mm,
            resistance_ohm=resistance_ohm,
            threshold_fraction=threshold_fraction,
            baseline_mode=baseline_mode,
            max_plot_points=max_plot_points,
            ring_start_us=ring_start_us,
            ring_end_us=ring_end_us,
            peak_threshold_fraction=peak_threshold_fraction,
            min_peak_distance_us=min_peak_distance_us,
        )
    elif analysis_mode == "Potência":
        render_power_page(
            waveforms=waveforms,
            max_plot_points=max_plot_points,
        )
