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
from ensaisf.utils.math_utils import _linear_trend_r2, _safe_percent_change

__all__ = [
    "add_channel_columns",
    "sequence_trend_table",
]


def add_channel_columns(metrics_df: pd.DataFrame, waveforms: list[dict]) -> pd.DataFrame:
    """Add filename-derived channel metadata to a metrics table."""
    if metrics_df.empty or "arquivo" not in metrics_df.columns:
        return metrics_df
    metadata_by_name = {
        item["name"]: {
            "tipo_sinal": item.get("role_label", "Não classificado"),
            "canal": item.get("channel"),
            "pulso": item.get("pulse_index"),
        }
        for item in waveforms
    }
    out = metrics_df.copy()
    for column in ["tipo_sinal", "canal", "pulso"]:
        if column in out.columns:
            out = out.drop(columns=[column])
    out.insert(1, "tipo_sinal", out["arquivo"].map(lambda name: metadata_by_name.get(name, {}).get("tipo_sinal")))
    out.insert(2, "canal", out["arquivo"].map(lambda name: metadata_by_name.get(name, {}).get("canal")))
    out.insert(3, "pulso", out["arquivo"].map(lambda name: metadata_by_name.get(name, {}).get("pulso")))
    return out


def sequence_trend_table(metrics_df: pd.DataFrame, waveforms: list[dict]) -> pd.DataFrame:
    """Summarize non-redundant pulse-sequence trends by signal role."""
    metrics_with_channels = add_channel_columns(metrics_df, waveforms)
    if metrics_with_channels.empty:
        return pd.DataFrame()

    rows = []
    for role_label, expected_behavior in [
        ("Tensão", "esperado: decaimento de amplitude"),
        ("Corrente", "esperado: acréscimo de amplitude"),
    ]:
        group = metrics_with_channels[metrics_with_channels["tipo_sinal"] == role_label].copy()
        group = group[np.isfinite(pd.to_numeric(group["pulso"], errors="coerce"))]
        group = group.sort_values("pulso")
        if len(group) < 2:
            continue

        pulses = group["pulso"].to_numpy(dtype=float)
        peak_abs = group["pico_abs_corrigido"].to_numpy(dtype=float)
        vpp = group["v_pp"].to_numpy(dtype=float)
        rms = group["rms_corrigido"].to_numpy(dtype=float)

        step_changes = [
            _safe_percent_change(peak_abs[idx - 1], peak_abs[idx])
            for idx in range(1, len(peak_abs))
        ]
        step_changes = np.array(step_changes, dtype=float)
        finite_steps = step_changes[np.isfinite(step_changes)]
        mean_step = float(np.mean(finite_steps)) if len(finite_steps) else float("nan")
        std_step = float(np.std(finite_steps, ddof=1)) if len(finite_steps) > 1 else float("nan")
        first_last_peak = _safe_percent_change(peak_abs[0], peak_abs[-1])
        first_last_vpp = _safe_percent_change(vpp[0], vpp[-1])
        first_last_rms = _safe_percent_change(rms[0], rms[-1])
        slope, trend_r2 = _linear_trend_r2(pulses, peak_abs)

        if role_label == "Tensão":
            observed = "decaimento" if np.isfinite(mean_step) and mean_step < 0 else "sem decaimento claro"
        else:
            observed = "acréscimo" if np.isfinite(mean_step) and mean_step > 0 else "sem acréscimo claro"

        rows.append(
            {
                "tipo_sinal": role_label,
                "n_pulsos": int(len(group)),
                "pulso_inicial": int(pulses[0]),
                "pulso_final": int(pulses[-1]),
                "pico_abs_inicial": float(peak_abs[0]),
                "pico_abs_final": float(peak_abs[-1]),
                "delta_pico_abs_primeiro_ultimo_%": first_last_peak,
                "media_delta_pico_abs_por_pulso_%": mean_step,
                "desvio_delta_pico_abs_por_pulso_%": std_step,
                "delta_vpp_primeiro_ultimo_%": first_last_vpp,
                "delta_rms_primeiro_ultimo_%": first_last_rms,
                "slope_pico_abs_por_pulso": slope,
                "r2_tendencia_pico_abs": trend_r2,
                "leitura": f"{observed}; {expected_behavior}",
            }
        )

    return pd.DataFrame(rows)
