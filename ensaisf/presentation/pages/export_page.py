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


def render_export_page(
    *,
    waveforms: list[dict],
    gap_mm: float,
    resistance_ohm: float,
    threshold_fraction: float,
    baseline_mode: str,
    ring_start_us: float,
    ring_end_us: float,
    peak_threshold_fraction: float,
    min_peak_distance_us: float,
) -> None:
    st.subheader("Exportação")
    st.caption(
        "Área dedicada para baixar métricas, ringing e formas de onda em CSV. "
        "As métricas completas são geradas sob demanda para não deixar os cliques do Envelope lentos."
    )

    if st.button("Gerar métricas para exportação", key="prepare_export_metrics_v035"):
        metrics_rows, metrics_df = build_waveform_metrics_table(
            waveforms,
            gap_mm=gap_mm,
            resistance_ohm=resistance_ohm,
            threshold_fraction=threshold_fraction,
            baseline_mode=baseline_mode,
        )
        ring_rows, ring_metrics_df = build_ring_metrics_table(
            waveforms,
            ring_start_us=ring_start_us,
            ring_end_us=ring_end_us,
            baseline_mode=baseline_mode,
            resistance_ohm=resistance_ohm,
            peak_threshold_fraction=peak_threshold_fraction,
            min_peak_distance_us=min_peak_distance_us,
        )
        st.session_state["export_metrics_csv_v035"] = metrics_df.to_csv(index=False).encode("utf-8")
        st.session_state["export_ring_metrics_csv_v035"] = ring_metrics_df.to_csv(index=False).encode("utf-8")

    if "export_metrics_csv_v035" in st.session_state:
        st.download_button(
            "Baixar métricas gerais em CSV",
            data=st.session_state["export_metrics_csv_v035"],
            file_name="metricas_isf.csv",
            mime="text/csv",
            key="download_general_metrics_v035",
        )
        st.download_button(
            "Baixar métricas de ringing em CSV",
            data=st.session_state["export_ring_metrics_csv_v035"],
            file_name="metricas_ringdown_resonancia.csv",
            mime="text/csv",
            key="download_ring_metrics_v035",
        )
    else:
        st.info("Clique em 'Gerar métricas para exportação' quando precisar dos CSVs de métricas.")

    st.divider()
    export_name = _select_signal_name(
        st,
        "Exportar forma de onda",
        [item["name"] for item in sort_items_by_pulse(waveforms)],
        "export_waveform_select_v0314",
        waveforms,
        preferred_index=0,
    )
    export_item = _find_item_by_name(waveforms, export_name)

    if st.button("Gerar CSV da forma de onda", key="prepare_waveform_csv_v035"):
        st.session_state["export_waveform_csv_v035"] = waveform_csv_bytes(export_item)
        st.session_state["export_waveform_csv_name_v035"] = Path(export_name).with_suffix(".csv").name

    if (
        "export_waveform_csv_v035" in st.session_state
        and st.session_state.get("export_waveform_csv_name_v035") == Path(export_name).with_suffix(".csv").name
    ):
        st.download_button(
            "Baixar forma de onda em CSV",
            data=st.session_state["export_waveform_csv_v035"],
            file_name=st.session_state["export_waveform_csv_name_v035"],
            mime="text/csv",
            key="download_waveform_csv_v035",
        )
    else:
        st.info("Clique em 'Gerar CSV da forma de onda' para preparar este arquivo.")
