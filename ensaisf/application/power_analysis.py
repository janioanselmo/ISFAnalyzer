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
from ensaisf.utils.math_utils import _trapz

__all__ = [
    "_decimate_aligned_arrays",
    "fast_vi_metrics",
    "get_power_analysis_cached",
]


def _decimate_aligned_arrays(
    time_s: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    max_points: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(time_s) <= max_points:
        return time_s, first, second
    step = int(np.ceil(len(time_s) / max_points))
    return time_s[::step], first[::step], second[::step]


def fast_vi_metrics(time_s: np.ndarray, voltage_v: np.ndarray, current_a: np.ndarray) -> dict:
    """Compute V/I metrics while keeping expensive FFT/xcorr on a bounded point count."""
    if len(time_s) < 2:
        return {}

    power_w = voltage_v * current_a
    metrics = {}
    t_metric, v_metric, i_metric = _decimate_aligned_arrays(
        time_s,
        voltage_v,
        current_a,
        max_points=POWER_METRIC_MAX_POINTS,
    )
    # The original vi_metrics is accurate but its cross-correlation becomes very
    # expensive with million-sample records. Running it on a representative,
    # aligned subset keeps the UI responsive while preserving full-resolution
    # integrals and extrema below.
    metrics.update(vi_metrics(t_metric, v_metric, i_metric))

    i2_dt = _trapz(current_a ** 2, time_s)
    energy_j = _trapz(power_w, time_s)
    i_threshold = 0.05 * float(np.max(np.abs(current_a))) if len(current_a) else float("nan")
    if np.isfinite(i_threshold) and i_threshold > 0:
        mask = np.abs(current_a) > i_threshold
    else:
        mask = np.zeros_like(current_a, dtype=bool)
    if np.any(mask):
        z_inst = voltage_v[mask] / current_a[mask]
        z_median = float(np.median(z_inst))
        z_mean = float(np.mean(z_inst))
    else:
        z_median = float("nan")
        z_mean = float("nan")

    metrics.update(
        {
            "v_max": float(np.max(voltage_v)),
            "v_min": float(np.min(voltage_v)),
            "i_max": float(np.max(current_a)),
            "i_min": float(np.min(current_a)),
            "p_max_w": float(np.max(power_w)),
            "p_min_w": float(np.min(power_w)),
            "energia_j": energy_j,
            "energia_abs_j": _trapz(np.abs(power_w), time_s),
            "carga_c": _trapz(current_a, time_s),
            "carga_abs_c": _trapz(np.abs(current_a), time_s),
            "resistencia_efetiva_ohm": energy_j / i2_dt if i2_dt > 0 else float("nan"),
            "impedancia_instantanea_mediana_ohm": z_median,
            "impedancia_instantanea_media_ohm": z_mean,
        }
    )
    return metrics


def get_power_analysis_cached(
    voltage_item: dict,
    current_item: dict,
    current_scale: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Cache aligned V/I arrays and metrics during Streamlit reruns."""
    cache = st.session_state.setdefault("_power_analysis_cache_v037", {})
    key = (
        voltage_item.get("data_hash"),
        current_item.get("data_hash"),
        round(float(current_scale), 12),
    )
    if key not in cache:
        t, v, i = align_current_to_voltage(
            voltage_item["time_s"],
            voltage_item["value"],
            current_item["time_s"],
            current_item["value"],
            current_scale_a_per_unit=current_scale,
        )
        p = v * i
        vi = fast_vi_metrics(t, v, i)
        cache[key] = (t, v, i, p, vi)
    return cache[key]
