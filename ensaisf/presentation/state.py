from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:  # optional component; app still runs without image-click selection
    streamlit_image_coordinates = None

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
from ensaisf.channels import (
    classify_signal_name,
    item_label,
    matching_current_for_voltage,
    names_for_role,
    role_counts,
    sort_items_by_pulse,
)
from ensaisf.isf_parser import read_isf_bytes
from ensaisf.presentation.theme import (
    APP_VERSION,
    ENVELOPE_IMAGE_MAX_POINTS,
    POWER_METRIC_MAX_POINTS,
    POWER_PLOT_MAX_POINTS,
    SELECTED_PEAK_COLOR_RGB,
    SERIES_COLORS_HEX,
    SERIES_COLORS_RGB,
)
from ensaisf.domain.envelope_analysis import _multi_image_click_version_key

__all__ = [
    "synchronize_file_dependent_state",
]


def synchronize_file_dependent_state(file_names: list[str]) -> None:
    """Synchronize file-dependent widgets without sharing state between tabs.

    The uploaded file list is global, but each analysis screen must keep its
    own independent selection. In particular, Potência and Comparação are
    two-file workflows and must never reduce the Envelope selection.
    """
    if not file_names:
        return

    previous_names = list(st.session_state.get("_loaded_file_names_v0315", []))
    upload_changed = previous_names != file_names
    added_names = [name for name in file_names if name not in previous_names]

    def _sync_multiselect(
        key: str,
        *,
        max_items: int | None = None,
        include_new_files: bool = False,
        default_to_all: bool = True,
    ) -> None:
        raw_value = st.session_state.get(key)
        current = raw_value if isinstance(raw_value, list) else []
        current = [name for name in current if name in file_names]

        if include_new_files and upload_changed:
            for name in added_names:
                if name not in current:
                    current.append(name)

        if not current and (key not in st.session_state or upload_changed) and default_to_all:
            current = list(file_names)

        if max_items is not None:
            current = current[:max_items]

        st.session_state[key] = current

    def _sync_selectbox(key: str, preferred_index: int = 0) -> None:
        current = st.session_state.get(key)
        if current not in file_names:
            st.session_state[key] = file_names[min(preferred_index, len(file_names) - 1)]

    # Independent per-screen selections.
    _sync_multiselect(
        "signals_selected_v0314",
        max_items=None,
        include_new_files=True,
        default_to_all=True,
    )
    _sync_multiselect(
        "envelope_files_v0315",
        max_items=None,
        include_new_files=True,
        default_to_all=True,
    )

    # Single-choice widgets remain valid, but they do not modify multiselects.
    _sync_selectbox("signals_metric_file_v0314", preferred_index=0)
    _sync_selectbox("export_waveform_select_v0314", preferred_index=0)
    _sync_selectbox("comparison_before_v0314", preferred_index=0)
    _sync_selectbox("comparison_after_v0314", preferred_index=1)
    _sync_selectbox("power_voltage_v0314", preferred_index=0)
    _sync_selectbox("power_current_v0314", preferred_index=1)

    if upload_changed:
        # Rebuild only the Envelope image component after real upload changes.
        image_version_key = _multi_image_click_version_key()
        st.session_state[image_version_key] = int(
            st.session_state.get(image_version_key, 0)
        ) + 1
        st.session_state["_loaded_file_names_v0315"] = list(file_names)
