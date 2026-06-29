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
from ensaisf.domain.envelope_analysis import _axis_ranges_for_envelope_view

__all__ = [
    "plot_sequence_trend",
    "plot_waveforms",
    "plot_ringdown",
    "plot_ringdown_with_envelope",
    "plot_envelope_comparison",
    "plot_envelope_context_graph",
    "plot_peak_selection_graph",
    "plot_selected_envelope_fit",
]


def plot_sequence_trend(metrics_df: pd.DataFrame, waveforms: list[dict], role_label: str) -> go.Figure:
    """Plot peak amplitude across pulse index for one signal type."""
    data = add_channel_columns(metrics_df, waveforms)
    data = data[data["tipo_sinal"] == role_label].copy()
    data = data.sort_values("pulso")
    fig = go.Figure()
    if not data.empty:
        fig.add_trace(
            go.Scatter(
                x=data["pulso"],
                y=data["pico_abs_corrigido"],
                mode="lines+markers",
                name=f"Pico absoluto — {role_label}",
            )
        )
    fig.update_layout(
        height=360,
        xaxis_title="Pulso",
        yaxis_title="Pico absoluto corrigido",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=30, b=40),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def plot_waveforms(
    waveforms: list[dict],
    normalize: bool = False,
    corrected: bool = False,
    baseline_mode: str = "t<0",
    max_points: int = 30_000,
    start_us: float | None = None,
    end_us: float | None = None,
):
    fig = go.Figure()

    for idx, item in enumerate(waveforms):
        color = item.get("series_color_hex", SERIES_COLORS_HEX[idx % len(SERIES_COLORS_HEX)])
        t = item["time_s"]
        y = item["value"].astype(float)

        if corrected:
            y, _baseline = subtract_baseline(t, y, mode=baseline_mode)

        if start_us is not None or end_us is not None:
            t, y, _indices = slice_window_us(t, y, start_us, end_us)

        if len(t) == 0:
            continue

        if normalize:
            denom = np.max(np.abs(y))
            if denom > 0:
                y = y / denom

        t_plot, y_plot = decimate_for_plot(t, y, max_points=max_points)
        fig.add_trace(
            go.Scattergl(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name=item["name"],
                line=dict(color=color),
            )
        )

    fig.update_layout(
        height=560,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude normalizada" if normalize else "Amplitude",
        hovermode="x unified",
        legend_title="Arquivo",
        margin=dict(l=40, r=20, t=40, b=40),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def plot_ringdown(
    item: dict,
    start_us: float,
    end_us: float,
    baseline_mode: str,
    peak_threshold_fraction: float,
    min_peak_distance_us: float,
    max_points: int,
):
    t = item["time_s"]
    y, _baseline = subtract_baseline(t, item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(t, y, start_us, end_us)
    peak_df = ringdown_peak_table(
        t,
        item["value"],
        start_us=start_us,
        end_us=end_us,
        baseline_mode=baseline_mode,
        peak_threshold_fraction=peak_threshold_fraction,
        min_peak_distance_us=min_peak_distance_us,
    )

    fig = go.Figure()
    if len(t_win):
        t_plot, y_plot = decimate_for_plot(t_win, y_win, max_points=max_points)
        # Use regular Scatter here instead of Scattergl.
        fig.add_trace(
            go.Scatter(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name="sinal corrigido",
                line=dict(color=SERIES_COLORS_HEX[0]),
            )
        )

    if not peak_df.empty:
        pos = peak_df[peak_df["tipo"] == "positivo"]
        neg = peak_df[peak_df["tipo"] == "negativo"]
        fig.add_trace(
            go.Scatter(
                x=pos["tempo_us"],
                y=pos["amplitude"],
                mode="markers",
                name="picos positivos",
                marker=dict(size=8, symbol="circle", color=SERIES_COLORS_HEX[0]),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=neg["tempo_us"],
                y=neg["amplitude"],
                mode="markers",
                name="picos negativos",
                marker=dict(size=8, symbol="x", color=SERIES_COLORS_HEX[1]),
            )
        )

    fig.update_layout(
        height=560,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude corrigida",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=40, b=40),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig, peak_df


def plot_ringdown_with_envelope(
    item: dict,
    peak_df: pd.DataFrame,
    fit_df: pd.DataFrame,
    envelope: dict,
    start_us: float,
    end_us: float,
    baseline_mode: str,
    max_points: int,
    selected_peak_ids: list[int] | None = None,
):
    """Plot ringdown, selectable peaks and fitted exponential envelope."""
    t = item["time_s"]
    y, _baseline = subtract_baseline(t, item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(t, y, start_us, end_us)

    fig = go.Figure()
    if len(t_win):
        t_plot, y_plot = decimate_for_plot(t_win, y_win, max_points=max_points)
        # Use regular Scatter here instead of Scattergl.
        fig.add_trace(
            go.Scatter(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name="sinal corrigido",
            )
        )

    if not peak_df.empty:
        selected_peak_ids = selected_peak_ids or []
        selected_point_indices = [
            int(i)
            for i, peak_id in enumerate(peak_df["peak_id"].to_list())
            if int(peak_id) in set(selected_peak_ids)
        ]
        fig.add_trace(
            go.Scatter(
                x=peak_df["tempo_us"],
                y=peak_df["amplitude"],
                mode="markers",
                name="picos clicáveis",
                customdata=peak_df[["peak_id"]].to_numpy(),
                selectedpoints=selected_point_indices if selected_point_indices else None,
                marker=dict(size=10),
                selected=dict(marker=dict(size=15)),
                unselected=dict(marker=dict(opacity=0.72)),
            )
        )

    if not fit_df.empty:
        fig.add_trace(
            go.Scatter(
                x=fit_df["tempo_us"],
                y=fit_df["amplitude"],
                mode="markers",
                name="picos usados no ajuste",
                marker=dict(size=14, symbol="diamond-open"),
            )
        )

    if np.isfinite(envelope.get("tau_us", np.nan)) and np.isfinite(envelope.get("a0", np.nan)):
        t0_us = envelope["t0_us"]
        tau_us = envelope["tau_us"]
        a0 = envelope["a0"]
        x_env_us = np.linspace(t0_us, end_us, 500)
        amp_env = a0 * np.exp(-(x_env_us - t0_us) / tau_us)
        fig.add_trace(
            go.Scatter(
                x=x_env_us,
                y=amp_env,
                mode="lines",
                name="envoltória +A·e⁻ᵗ/τ",
                line=dict(dash="dash"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=x_env_us,
                y=-amp_env,
                mode="lines",
                name="envoltória -A·e⁻ᵗ/τ",
                line=dict(dash="dash"),
            )
        )

    # Force a meaningful view. Without explicit ranges, some Plotly/Streamlit
    # combinations can render an empty default axis even when data exists.
    x_values = []
    y_values = []
    if len(t_win):
        x_values.extend((t_win * 1e6).astype(float).tolist())
        y_values.extend(y_win.astype(float).tolist())
    if not peak_df.empty:
        x_values.extend(peak_df["tempo_us"].astype(float).tolist())
        y_values.extend(peak_df["amplitude"].astype(float).tolist())
    if not fit_df.empty:
        x_values.extend(fit_df["tempo_us"].astype(float).tolist())
        y_values.extend(fit_df["amplitude"].astype(float).tolist())

    x_range = None
    if np.isfinite(start_us) and np.isfinite(end_us) and end_us > start_us:
        x_range = [float(start_us), float(end_us)]
    elif x_values:
        x_min = float(np.nanmin(x_values))
        x_max = float(np.nanmax(x_values))
        pad = max((x_max - x_min) * 0.05, 1.0)
        x_range = [x_min - pad, x_max + pad]

    y_range = None
    y_arr = np.asarray(y_values, dtype=float) if y_values else np.array([], dtype=float)
    y_arr = y_arr[np.isfinite(y_arr)]
    if y_arr.size:
        y_min = float(np.nanmin(y_arr))
        y_max = float(np.nanmax(y_arr))
        if np.isclose(y_min, y_max):
            pad = max(abs(y_max) * 0.25, 1.0)
        else:
            pad = max((y_max - y_min) * 0.10, 1.0)
        y_range = [y_min - pad, y_max + pad]

    fig.update_layout(
        height=580,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude corrigida",
        hovermode="closest",
        clickmode="event+select",
        dragmode="select",
        margin=dict(l=40, r=20, t=40, b=40),
    )
    fig.update_xaxes(showgrid=True, range=x_range)
    fig.update_yaxes(showgrid=True, range=y_range)
    return fig


def plot_envelope_comparison(envelope_df: pd.DataFrame, normalize: bool = True):
    """Compare fitted exponential envelopes from multiple loaded files."""
    fig = go.Figure()
    if envelope_df.empty:
        return fig

    for idx, (_, row) in enumerate(envelope_df.iterrows()):
        if not np.isfinite(row.get("tau_us", np.nan)) or not np.isfinite(row.get("a0", np.nan)):
            continue
        duration = row.get("ultimo_pico_us", np.nan) - row.get("t0_us", np.nan)
        if not np.isfinite(duration) or duration <= 0:
            duration = row["tau_us"] * 3.0
        x_us = np.linspace(0.0, duration, 500)
        y = np.exp(-x_us / row["tau_us"]) if normalize else row["a0"] * np.exp(-x_us / row["tau_us"])
        color = row.get("series_color", SERIES_COLORS_HEX[idx % len(SERIES_COLORS_HEX)])
        fig.add_trace(
            go.Scatter(
                x=x_us,
                y=y,
                mode="lines",
                name=str(row["arquivo"]),
                line=dict(color=color, width=2.5),
            )
        )

    fig.update_layout(
        height=520,
        xaxis_title="Tempo relativo ao primeiro pico usado no ajuste (µs)",
        yaxis_title="Amplitude normalizada" if normalize else "Amplitude da envoltória",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=40, b=40),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def plot_envelope_context_graph(
    item: dict,
    peak_df: pd.DataFrame,
    selected_peak_ids: list[int],
    start_us: float,
    end_us: float,
    baseline_mode: str,
    max_points: int,
    focus_y_on_peaks: bool = True,
):
    """Clickable waveform plot used for manual peak selection.

    This figure is intentionally rendered with regular SVG Scatter traces, not
    Scattergl, because the Streamlit click component is substantially more
    reliable with SVG traces. The waveform line is visual context only; the
    peak markers carry customdata with peak_id and are the intended click
    targets.
    """
    t = item["time_s"]
    y, _baseline = subtract_baseline(t, item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(t, y, start_us, end_us)

    fig = go.Figure()
    if len(t_win):
        t_plot, y_plot = decimate_for_plot(t_win, y_win, max_points=max_points)
        fig.add_trace(
            go.Scatter(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name="sinal na janela",
                line=dict(width=1.5, color=SERIES_COLORS_HEX[0]),
                hoverinfo="skip",
            )
        )

    if not peak_df.empty:
        selected_set = set(int(x) for x in selected_peak_ids)
        unselected = peak_df[~peak_df["peak_id"].isin(selected_set)]
        selected = peak_df[peak_df["peak_id"].isin(selected_set)]
        if not unselected.empty:
            fig.add_trace(
                go.Scatter(
                    x=unselected["tempo_us"],
                    y=unselected["amplitude"],
                    mode="markers",
                    name="clique para selecionar",
                    customdata=unselected["peak_id"].astype(int).tolist(),
                    marker=dict(size=17, symbol="circle-open", color=SERIES_COLORS_HEX[0], line=dict(width=2, color=SERIES_COLORS_HEX[0])),
                    hovertemplate=(
                        "Pico %{customdata}<br>"
                        "Tempo: %{x:.3f} µs<br>"
                        "Amplitude: %{y:.3f}<extra></extra>"
                    ),
                )
            )
        if not selected.empty:
            fig.add_trace(
                go.Scatter(
                    x=selected["tempo_us"],
                    y=selected["amplitude"],
                    mode="markers",
                    name="selecionados",
                    customdata=selected["peak_id"].astype(int).tolist(),
                    marker=dict(size=23, symbol="diamond-open", color="rgb(235,68,68)", line=dict(width=3, color="rgb(235,68,68)")),
                    hovertemplate=(
                        "Selecionado %{customdata}<br>"
                        "Tempo: %{x:.3f} µs<br>"
                        "Amplitude: %{y:.3f}<extra></extra>"
                    ),
                )
            )

    x_range, y_range = _axis_ranges_for_envelope_view(
        t_win, y_win, peak_df, start_us, end_us, focus_y_on_peaks=focus_y_on_peaks
    )
    fig.update_layout(
        height=470,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude corrigida",
        hovermode="closest",
        clickmode="event+select",
        margin=dict(l=40, r=20, t=35, b=40),
        legend_title="",
    )
    fig.update_xaxes(showgrid=True, range=x_range)
    fig.update_yaxes(showgrid=True, range=y_range)
    return fig


def plot_peak_selection_graph(
    item: dict,
    peak_df: pd.DataFrame,
    selected_peak_ids: list[int],
    start_us: float,
    end_us: float,
    baseline_mode: str,
    max_points: int,
    focus_y_on_peaks: bool = True,
):
    """Marker-only Plotly figure for robust click/toggle peak selection."""
    del item, baseline_mode, max_points, focus_y_on_peaks  # kept for call compatibility
    fig = go.Figure()

    if not peak_df.empty:
        selected_set = set(int(x) for x in selected_peak_ids)
        unselected = peak_df[~peak_df["peak_id"].isin(selected_set)]
        selected = peak_df[peak_df["peak_id"].isin(selected_set)]

        if not unselected.empty:
            fig.add_trace(
                go.Scatter(
                    x=unselected["tempo_us"],
                    y=unselected["amplitude"],
                    mode="markers",
                    name="clique para selecionar",
                    customdata=unselected["peak_id"].astype(int).tolist(),
                    marker=dict(size=18, symbol="circle-open", color=SERIES_COLORS_HEX[0], line=dict(width=2, color=SERIES_COLORS_HEX[0])),
                )
            )
        if not selected.empty:
            fig.add_trace(
                go.Scatter(
                    x=selected["tempo_us"],
                    y=selected["amplitude"],
                    mode="markers",
                    name="selecionados",
                    customdata=selected["peak_id"].astype(int).tolist(),
                    marker=dict(size=24, symbol="diamond-open", color="rgb(235,68,68)", line=dict(width=3, color="rgb(235,68,68)")),
                )
            )

    x_range = [float(start_us), float(end_us)] if end_us > start_us else None
    y_range = None
    if not peak_df.empty:
        y_values = peak_df["amplitude"].astype(float).to_numpy()
        y_values = y_values[np.isfinite(y_values)]
        if y_values.size:
            y_min = float(np.nanmin(y_values))
            y_max = float(np.nanmax(y_values))
            if np.isclose(y_min, y_max):
                pad = max(abs(y_max) * 0.35, 5.0)
            else:
                pad = max((y_max - y_min) * 0.25, 5.0)
            y_range = [y_min - pad, y_max + pad]

    fig.update_layout(
        height=300,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude do pico",
        hovermode="closest",
        clickmode="event+select",
        margin=dict(l=40, r=20, t=25, b=40),
        legend_title="",
    )
    fig.update_xaxes(showgrid=True, range=x_range)
    fig.update_yaxes(showgrid=True, range=y_range)
    return fig


def plot_selected_envelope_fit(fit_df: pd.DataFrame, envelope: dict, log_y: bool = False):
    """Plot selected peak amplitudes and the fitted exponential envelope."""
    fig = go.Figure()
    if fit_df.empty:
        fig.update_layout(
            height=420,
            xaxis_title="Tempo relativo (µs)",
            yaxis_title="Amplitude de envelope do pico",
            margin=dict(l=40, r=20, t=35, b=40),
        )
        return fig

    t0_us = float(fit_df["tempo_us"].iloc[0])
    x_rel = fit_df["tempo_us"].astype(float) - t0_us
    y_abs = fit_df["fit_amplitude"].astype(float) if "fit_amplitude" in fit_df.columns else np.abs(fit_df["amplitude"].astype(float))
    fig.add_trace(
        go.Scatter(
            x=x_rel,
            y=y_abs,
            mode="markers",
            name="picos selecionados",
            marker=dict(size=13, symbol="diamond-open", color="rgb(235,68,68)", line=dict(color="rgb(235,68,68)")),
        )
    )

    if np.isfinite(envelope.get("tau_us", np.nan)) and np.isfinite(envelope.get("a0", np.nan)):
        duration = float(np.nanmax(x_rel)) if len(x_rel) else 0.0
        duration = max(duration, float(envelope["tau_us"]) * 0.1 if np.isfinite(envelope["tau_us"]) else 1.0)
        x_fit = np.linspace(0.0, duration, 400)
        y_fit = float(envelope["a0"]) * np.exp(-x_fit / float(envelope["tau_us"]))
        fig.add_trace(
            go.Scatter(
                x=x_fit,
                y=y_fit,
                mode="lines",
                name="ajuste exponencial",
                line=dict(color=SERIES_COLORS_HEX[0], width=2.5),
            )
        )

    fig.update_layout(
        height=420,
        xaxis_title="Tempo relativo ao primeiro pico selecionado (µs)",
        yaxis_title="Amplitude de envelope do pico",
        yaxis_type="log" if log_y else "linear",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=35, b=40),
        legend_title="",
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig
