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
    "waveform_csv_bytes",
    "vip_csv_bytes",
]


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
