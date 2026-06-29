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
    "_trapz",
    "_safe_percent_change",
    "_linear_trend_r2",
]


def _trapz(y: np.ndarray, x: np.ndarray) -> float:
    if len(y) < 2 or len(x) < 2:
        return float("nan")
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def _safe_percent_change(before: float, after: float) -> float:
    """Return percentage change, guarding against zero/invalid values."""
    try:
        before_f = float(before)
        after_f = float(after)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(before_f) or not np.isfinite(after_f) or abs(before_f) < 1e-30:
        return float("nan")
    return float(100.0 * (after_f - before_f) / before_f)


def _linear_trend_r2(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return slope and R² for a first-order sequence trend."""
    mask = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(mask) < 2:
        return float("nan"), float("nan")
    x_m = x[mask].astype(float)
    y_m = y[mask].astype(float)
    if np.allclose(x_m, x_m[0]) or np.allclose(y_m, y_m[0]):
        return float("nan"), float("nan")
    slope, intercept = np.polyfit(x_m, y_m, deg=1)
    y_hat = slope * x_m + intercept
    ss_res = float(np.sum((y_m - y_hat) ** 2))
    ss_tot = float(np.sum((y_m - np.mean(y_m)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return float(slope), float(r2)
