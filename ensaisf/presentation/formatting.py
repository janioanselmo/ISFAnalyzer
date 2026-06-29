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

__all__ = [
    "_format_metric",
    "_find_item_by_name",
    "_format_signal_label",
    "_select_signal_name",
]


def _format_metric(value: float, unit: str = "", precision: int = 4) -> str:
    if value is None:
        return "—"
    try:
        if not np.isfinite(float(value)):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{float(value):.{precision}g} {unit}".strip()


def _find_item_by_name(waveforms: list[dict], name: str) -> dict:
    """Return one waveform item by filename."""
    return next(item for item in waveforms if item["name"] == name)


def _format_signal_label(name: str, waveforms: list[dict]) -> str:
    """Format a selector option using channel metadata."""
    try:
        return item_label(_find_item_by_name(waveforms, name))
    except StopIteration:
        return name


def _select_signal_name(
    container,
    label: str,
    options: list[str],
    key: str,
    waveforms: list[dict],
    preferred_index: int = 0,
) -> str | None:
    """Render a channel-aware selectbox and keep its state valid."""
    if not options:
        container.warning(f"Nenhum arquivo disponível para: {label}.")
        return None
    preferred_index = min(max(int(preferred_index), 0), len(options) - 1)
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[preferred_index]
    return container.selectbox(
        label,
        options,
        key=key,
        format_func=lambda name: _format_signal_label(name, waveforms),
    )
