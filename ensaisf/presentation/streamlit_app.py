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
    classify_signal_name,
    matching_current_for_voltage,
    names_for_role,
    role_counts,
    sort_items_by_pulse,
)
from ensaisf.domain.channel_metrics import *
from ensaisf.domain.envelope_analysis import *
from ensaisf.infrastructure.csv_exporter import *
from ensaisf.infrastructure.upload_loader import *
from ensaisf.presentation.formatting import *
from ensaisf.presentation.plots import *
from ensaisf.presentation.state import *
from ensaisf.presentation.pages.analysis_page import render_analysis_page
from ensaisf.presentation.pages.export_page import render_export_page
from ensaisf.presentation.pages.header_page import render_header_page
from ensaisf.presentation.theme import (
    APP_VERSION,
    ENVELOPE_IMAGE_MAX_POINTS,
    POWER_PLOT_MAX_POINTS,
    SERIES_COLORS_HEX,
    SERIES_COLORS_RGB,
)
from ensaisf.analysis import (
    compare_ringdown_metrics,
    decimate_for_plot,
    resonance_shift_score,
    ringdown_metrics,
    waveform_similarity_metrics,
)


def run_app() -> None:
    """Run the Streamlit user interface."""
    st.set_page_config(
        page_title="ISF Analyzer",
        page_icon="⚡",
        layout="wide",
    )

    st.title("⚡ ISF Analyzer")
    st.caption(
        f"Analisador local para Tektronix .ISF | versão {APP_VERSION} | foco: pulso, ringing, ressonância e eletroporação"
    )

    with st.sidebar:
        st.header("Configuração da análise")

        uploaded_files = st.file_uploader(
            "Carregue arquivos Tektronix .ISF ou um .ZIP com pastas",
            type=["isf", "ISF", "zip", "ZIP"],
            accept_multiple_files=True,
            help=(
                "Você pode carregar qualquer ZIP com arquivos .ISF em qualquer estrutura de pastas. "
                "O app preserva o nome do ZIP e o caminho interno, evitando colisões de nomes iguais."
            ),
        )

        standardize_groups = st.checkbox(
            "Padronizar quantidade por pasta/grupo",
            value=True,
            help=(
                "Funciona para qualquer ZIP ou conjunto de arquivos. Quando grupos têm quantidades "
                "diferentes de aquisições TXXXX, o app calcula automaticamente o menor N comum e "
                "mantém os primeiros N TXXXX de cada grupo. Não há valor fixo no código."
            ),
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
            value=-100.0,
            step=1.0,
            format="%.3f",
            key="sidebar_ring_start_us_v039",
            help="Ajuste para pegar os picos finais da oscilação natural, após o disparo principal.",
        )
        ring_end_us = st.number_input(
            "Fim da janela de ringing (µs)",
            value=500.0,
            step=1.0,
            format="%.3f",
            key="sidebar_ring_end_us_v039",
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
            "Carregue um ou mais arquivos `.ISF` ou qualquer `.ZIP` contendo arquivos `.ISF` na barra lateral. "
            "O `.PNG` do osciloscópio é útil para conferência visual, mas o `.ISF` contém a forma de onda real."
        )
        st.stop()

    waveforms: list[dict] = []
    errors: list[str] = []
    upload_entries, upload_expand_errors = expand_uploaded_files(uploaded_files)
    errors.extend(upload_expand_errors)

    for idx, (entry_name, entry_data) in enumerate(upload_entries):
        try:
            item = parse_uploaded_file(entry_name, entry_data)
            item.update(classify_signal_name(entry_name).as_dict())
            item["series_color_rgb"] = SERIES_COLORS_RGB[idx % len(SERIES_COLORS_RGB)]
            item["series_color_hex"] = SERIES_COLORS_HEX[idx % len(SERIES_COLORS_HEX)]
            waveforms.append(item)
        except Exception as exc:
            errors.append(f"{entry_name}: {exc}")

    waveforms_raw_count = len(waveforms)
    waveforms, group_summary_df, common_group_count = standardize_waveforms_by_group(
        waveforms,
        enabled=standardize_groups,
    )

    # Re-assign colors after optional standardization so legends stay compact.
    for idx, item in enumerate(waveforms):
        item["series_color_rgb"] = SERIES_COLORS_RGB[idx % len(SERIES_COLORS_RGB)]
        item["series_color_hex"] = SERIES_COLORS_HEX[idx % len(SERIES_COLORS_HEX)]

    if errors:
        st.error("Alguns arquivos não puderam ser lidos:\n\n" + "\n".join(errors))

    if not waveforms:
        st.stop()

    if not group_summary_df.empty:
        with st.sidebar.expander("Resumo das pastas carregadas", expanded=False):
            st.dataframe(group_summary_df, width="stretch", height=180)
            if standardize_groups and common_group_count is not None:
                st.caption(
                    f"Padronização ativa: usando os primeiros {common_group_count} TXXXX de cada pasta/grupo detectado. "
                    f"Arquivos ISF usados: {len(waveforms)} de {waveforms_raw_count}."
                )
            elif common_group_count is not None:
                st.caption(
                    f"Padronização desativada. Menor série detectada: {common_group_count} TXXXX."
                )
































    synchronize_file_dependent_state([item["name"] for item in waveforms])

    tab_signal, tab_export, tab_header = st.tabs(
        [
            "Análise de sinais",
            "Exportação",
            "Cabeçalho",
        ]
    )

    with tab_signal:
        render_analysis_page(
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

    with tab_export:
        render_export_page(
            waveforms=waveforms,
            gap_mm=gap_mm,
            resistance_ohm=resistance_ohm,
            threshold_fraction=threshold_fraction,
            baseline_mode=baseline_mode,
            ring_start_us=ring_start_us,
            ring_end_us=ring_end_us,
            peak_threshold_fraction=peak_threshold_fraction,
            min_peak_distance_us=min_peak_distance_us,
        )

    with tab_header:
        render_header_page(waveforms=waveforms)
