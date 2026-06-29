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
from ensaisf.domain.channel_metrics import add_channel_columns

__all__ = [
    "build_waveform_metrics_table",
    "build_ring_metrics_table",
]


def build_waveform_metrics_table(
    waveforms: list[dict],
    gap_mm: float,
    resistance_ohm: float,
    threshold_fraction: float,
    baseline_mode: str,
) -> tuple[list[dict], pd.DataFrame]:
    rows = [
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
    return rows, add_channel_columns(metrics_dataframe(rows), waveforms)


def build_ring_metrics_table(
    waveforms: list[dict],
    ring_start_us: float,
    ring_end_us: float,
    baseline_mode: str,
    resistance_ohm: float,
    peak_threshold_fraction: float,
    min_peak_distance_us: float,
) -> tuple[list[dict], pd.DataFrame]:
    rows = [
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
    return rows, add_channel_columns(metrics_dataframe(rows), waveforms)
