from __future__ import annotations

from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit_plotly_events import plotly_events
except ImportError:  # optional component; app still runs with native Streamlit selection
    plotly_events = None

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
from ensaisf.isf_parser import read_isf_bytes


st.set_page_config(
    page_title="ISF Analyzer",
    page_icon="⚡",
    layout="wide",
)


APP_VERSION = "0.2.6-usability"


def _format_metric(value: float, unit: str = "", precision: int = 4) -> str:
    if value is None:
        return "—"
    try:
        if not np.isfinite(float(value)):
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{float(value):.{precision}g} {unit}".strip()


@st.cache_data(show_spinner=False)
def parse_uploaded_file(name: str, data: bytes):
    waveform = read_isf_bytes(data)
    return {
        "name": name,
        "time_s": waveform.time_s,
        "value": waveform.value,
        "metadata": waveform.metadata,
        "header": waveform.header,
    }


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

    for item in waveforms:
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
        # The streamlit-plotly-events component is more reliable with SVG traces
        # for click selection; Scattergl can make the chart render as an empty
        # default axis in some Plotly/Streamlit combinations.
        fig.add_trace(
            go.Scatter(
                x=t_plot * 1e6,
                y=y_plot,
                mode="lines",
                name="sinal corrigido",
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
                marker=dict(size=8, symbol="circle"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=neg["tempo_us"],
                y=neg["amplitude"],
                mode="markers",
                name="picos negativos",
                marker=dict(size=8, symbol="x"),
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




def _get_selection_points(selection_state) -> list[dict]:
    """Return Plotly selected points from Streamlit selection state."""
    if selection_state is None:
        return []

    selection = getattr(selection_state, "selection", None)
    if selection is None and isinstance(selection_state, dict):
        selection = selection_state.get("selection")
    if selection is None:
        return []

    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points", [])
    return list(points or [])


def extract_selected_peak_ids(selection_state) -> list[int]:
    """Extract peak identifiers from marker customdata after mouse selection."""
    selected_ids: list[int] = []
    for point in _get_selection_points(selection_state):
        custom = None
        if isinstance(point, dict):
            custom = point.get("customdata")
        else:
            custom = getattr(point, "customdata", None)

        if isinstance(custom, (list, tuple, np.ndarray)) and len(custom):
            custom = custom[0]

        try:
            selected_ids.append(int(custom))
        except (TypeError, ValueError):
            continue

    return sorted(set(selected_ids))


def _click_signature(click_event: dict) -> str:
    """Create a stable signature so one browser event is not toggled twice."""
    x = click_event.get("x", "")
    y = click_event.get("y", "")
    curve = click_event.get("curveNumber", "")
    point = click_event.get("pointNumber", click_event.get("pointIndex", ""))
    try:
        x = f"{float(x):.9g}"
        y = f"{float(y):.9g}"
    except (TypeError, ValueError):
        pass
    return f"{curve}:{point}:{x}:{y}"


def nearest_peak_id_from_click_event(
    click_event: dict,
    peak_df: pd.DataFrame,
    x_tolerance_us: float | None = None,
    y_tolerance_fraction: float = 0.08,
) -> int | None:
    """Return the nearest peak id to a mouse click, or None when it is too far."""
    if peak_df.empty:
        return None

    try:
        click_x = float(click_event.get("x"))
        click_y = float(click_event.get("y"))
    except (TypeError, ValueError):
        return None

    peaks = peak_df.copy()
    peaks = peaks[np.isfinite(peaks["tempo_us"]) & np.isfinite(peaks["amplitude"])]
    if peaks.empty:
        return None

    times = peaks["tempo_us"].to_numpy(dtype=float)
    amplitudes = peaks["amplitude"].to_numpy(dtype=float)

    if x_tolerance_us is None:
        if len(times) > 1:
            diffs = np.diff(np.sort(times))
            diffs = diffs[diffs > 0]
            x_tolerance_us = float(np.median(diffs) * 0.45) if len(diffs) else 3.0
        else:
            x_tolerance_us = 3.0
        x_tolerance_us = max(float(x_tolerance_us), 0.25)

    y_span = float(np.nanmax(amplitudes) - np.nanmin(amplitudes)) if len(amplitudes) else 0.0
    y_tolerance = max(y_span * y_tolerance_fraction, np.nanmax(np.abs(amplitudes)) * 0.03, 1e-12)

    dx = np.abs(times - click_x)
    dy = np.abs(amplitudes - click_y)
    normalized_distance = (dx / x_tolerance_us) ** 2 + (dy / y_tolerance) ** 2
    best_position = int(np.argmin(normalized_distance))

    if dx[best_position] <= x_tolerance_us and dy[best_position] <= y_tolerance:
        return int(peaks.iloc[best_position]["peak_id"])
    return None


def toggle_peak_selection_from_clicks(
    clicked_points: list[dict],
    peak_df: pd.DataFrame,
    selected_state_key: str,
    last_click_state_key: str,
) -> bool:
    """Toggle the clicked peak in Streamlit session state."""
    if not clicked_points:
        return False

    click_event = clicked_points[-1]
    signature = _click_signature(click_event)
    if st.session_state.get(last_click_state_key) == signature:
        return False

    peak_id = nearest_peak_id_from_click_event(click_event, peak_df)
    if peak_id is None:
        st.session_state[last_click_state_key] = signature
        return False

    selected_ids = list(st.session_state.get(selected_state_key, []))
    if peak_id in selected_ids:
        selected_ids = [item for item in selected_ids if item != peak_id]
    else:
        selected_ids.append(peak_id)

    peak_order = {
        int(row["peak_id"]): float(row["tempo_us"])
        for _, row in peak_df.iterrows()
    }
    selected_ids = sorted(set(selected_ids), key=lambda item: peak_order.get(int(item), float("inf")))

    st.session_state[selected_state_key] = selected_ids
    st.session_state[last_click_state_key] = signature
    return True


def filter_peak_table_by_polarity(peak_df: pd.DataFrame, polarity: str) -> pd.DataFrame:
    """Filter peak table according to selected polarity."""
    if peak_df.empty:
        return peak_df.copy()
    if polarity == "Somente positivos":
        return peak_df[peak_df["tipo"] == "positivo"].copy()
    if polarity == "Somente negativos":
        return peak_df[peak_df["tipo"] == "negativo"].copy()
    return peak_df.copy()


def fit_exponential_envelope(
    peak_df: pd.DataFrame,
    n_peaks: int = 3,
    polarity: str = "Extremos positivos e negativos",
    selected_peak_ids: list[int] | None = None,
    file_name: str = "",
) -> tuple[dict, pd.DataFrame]:
    """Fit |V_peak| = A0 * exp(-(t - t0) / tau) from selected or last peaks."""
    empty_metrics = {
        "arquivo": file_name,
        "metodo": "sem picos suficientes",
        "n_picos_fit": 0,
        "t0_us": float("nan"),
        "ultimo_pico_us": float("nan"),
        "a0": float("nan"),
        "tau_us": float("nan"),
        "slope_1_s": float("nan"),
        "r2_envelope": float("nan"),
        "periodo_mediano_us": float("nan"),
        "freq_envelope_khz": float("nan"),
        "decaimento_por_periodo_percent": float("nan"),
        "meia_vida_us": float("nan"),
        "amplitude_final_predita": float("nan"),
        "razao_final_inicial_predita": float("nan"),
    }

    if peak_df.empty:
        return empty_metrics, peak_df.copy()

    peaks = filter_peak_table_by_polarity(peak_df, polarity)
    if peaks.empty:
        return empty_metrics, peaks

    if selected_peak_ids:
        fit_df = peak_df[peak_df["peak_id"].isin(selected_peak_ids)].copy()
        fit_df = filter_peak_table_by_polarity(fit_df, polarity)
        method = "seleção manual no gráfico"
    else:
        fit_df = peaks.sort_values("tempo_us").tail(n_peaks).copy()
        method = f"últimos {n_peaks} picos detectados"

    fit_df = fit_df.sort_values("tempo_us").reset_index(drop=True)
    fit_df["abs_amplitude"] = np.abs(fit_df["amplitude"].astype(float))
    fit_df = fit_df[np.isfinite(fit_df["tempo_us"]) & (fit_df["abs_amplitude"] > 0)]

    if len(fit_df) < 2:
        metrics = empty_metrics.copy()
        metrics["arquivo"] = file_name
        metrics["metodo"] = method
        metrics["n_picos_fit"] = int(len(fit_df))
        return metrics, fit_df

    t_us = fit_df["tempo_us"].to_numpy(dtype=float)
    amp = fit_df["abs_amplitude"].to_numpy(dtype=float)
    t0_us = float(t_us[0])
    x_s = (t_us - t0_us) * 1e-6
    log_amp = np.log(amp)

    slope, intercept = np.polyfit(x_s, log_amp, deg=1)
    pred_log = slope * x_s + intercept
    ss_res = float(np.sum((log_amp - pred_log) ** 2))
    ss_tot = float(np.sum((log_amp - np.mean(log_amp)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    tau_s = float(-1.0 / slope) if slope < 0 else float("nan")
    tau_us = float(tau_s * 1e6) if np.isfinite(tau_s) else float("nan")
    a0 = float(np.exp(intercept))

    periods_us = np.diff(t_us)
    periods_us = periods_us[periods_us > 0]
    median_period_us = float(np.median(periods_us)) if len(periods_us) else float("nan")
    freq_khz = float(1e3 / median_period_us) if np.isfinite(median_period_us) and median_period_us > 0 else float("nan")

    if np.isfinite(tau_us) and np.isfinite(median_period_us):
        decay_per_period = float(100.0 * (1.0 - np.exp(-median_period_us / tau_us)))
    else:
        decay_per_period = float("nan")

    half_life_us = float(tau_us * np.log(2.0)) if np.isfinite(tau_us) else float("nan")
    last_x_s = float(x_s[-1])
    final_amp = float(a0 * np.exp(slope * last_x_s))
    ratio_final_initial = float(final_amp / a0) if a0 > 0 else float("nan")

    fit_df["amp_envelope_fit"] = np.exp(pred_log)
    fit_df["residuo_log"] = log_amp - pred_log

    return {
        "arquivo": file_name,
        "metodo": method,
        "n_picos_fit": int(len(fit_df)),
        "t0_us": t0_us,
        "ultimo_pico_us": float(t_us[-1]),
        "a0": a0,
        "tau_us": tau_us,
        "slope_1_s": float(slope),
        "r2_envelope": r2,
        "periodo_mediano_us": median_period_us,
        "freq_envelope_khz": freq_khz,
        "decaimento_por_periodo_percent": decay_per_period,
        "meia_vida_us": half_life_us,
        "amplitude_final_predita": final_amp,
        "razao_final_inicial_predita": ratio_final_initial,
    }, fit_df


def add_peak_ids(peak_df: pd.DataFrame) -> pd.DataFrame:
    """Add stable peak identifiers for Plotly selection."""
    peak_df = peak_df.copy()
    if not peak_df.empty:
        peak_df = peak_df.sort_values("tempo_us").reset_index(drop=True)
        peak_df["peak_id"] = np.arange(len(peak_df), dtype=int)
    else:
        peak_df["peak_id"] = []
    return peak_df


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
        # The streamlit-plotly-events component is more reliable with SVG traces
        # for click selection; Scattergl can make the chart render as an empty
        # default axis in some Plotly/Streamlit combinations.
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

    # Force a meaningful view. Without explicit ranges, some combinations of
    # streamlit-plotly-events + Plotly can render an empty default axis even
    # when the peak table is populated.
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
        dragmode="zoom",
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

    for _, row in envelope_df.iterrows():
        if not np.isfinite(row.get("tau_us", np.nan)) or not np.isfinite(row.get("a0", np.nan)):
            continue
        duration = row.get("ultimo_pico_us", np.nan) - row.get("t0_us", np.nan)
        if not np.isfinite(duration) or duration <= 0:
            duration = row["tau_us"] * 3.0
        x_us = np.linspace(0.0, duration, 500)
        y = np.exp(-x_us / row["tau_us"]) if normalize else row["a0"] * np.exp(-x_us / row["tau_us"])
        fig.add_trace(
            go.Scatter(
                x=x_us,
                y=y,
                mode="lines",
                name=str(row["arquivo"]),
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



def _state_suffix(name: str) -> str:
    """Return a stable Streamlit-session suffix for a file name."""
    return hashlib.md5(name.encode("utf-8")).hexdigest()[:10]


def _peak_selection_key(file_name: str) -> str:
    return f"envelope_selected_peak_ids_{_state_suffix(file_name)}_v026"


def _last_click_key(file_name: str) -> str:
    return f"envelope_last_click_signature_{_state_suffix(file_name)}_v026"


def selected_peak_ids_for_file(file_name: str) -> list[int]:
    return list(st.session_state.get(_peak_selection_key(file_name), []))


def set_selected_peak_ids_for_file(file_name: str, peak_ids: list[int]) -> None:
    st.session_state[_peak_selection_key(file_name)] = list(dict.fromkeys(int(x) for x in peak_ids))


def fallback_peak_ids(peak_df: pd.DataFrame, n_peaks: int, polarity: str) -> list[int]:
    """Return the last N peak ids after polarity filtering."""
    peaks = filter_peak_table_by_polarity(peak_df, polarity)
    if peaks.empty:
        return []
    return [int(x) for x in peaks.sort_values("tempo_us").tail(int(n_peaks))["peak_id"].to_list()]


def fit_selected_envelope_only(
    peak_df: pd.DataFrame,
    selected_peak_ids: list[int],
    polarity: str,
    file_name: str,
) -> tuple[dict, pd.DataFrame]:
    """Fit the envelope only when the user selected at least two peaks."""
    if len(selected_peak_ids) < 2:
        empty_metrics = {
            "arquivo": file_name,
            "metodo": "aguardando seleção manual",
            "n_picos_fit": int(len(selected_peak_ids)),
            "t0_us": float("nan"),
            "ultimo_pico_us": float("nan"),
            "a0": float("nan"),
            "tau_us": float("nan"),
            "slope_1_s": float("nan"),
            "r2_envelope": float("nan"),
            "periodo_mediano_us": float("nan"),
            "freq_envelope_khz": float("nan"),
            "decaimento_por_periodo_percent": float("nan"),
            "meia_vida_us": float("nan"),
            "amplitude_final_predita": float("nan"),
            "razao_final_inicial_predita": float("nan"),
        }
        selected_df = peak_df[peak_df.get("peak_id", pd.Series(dtype=int)).isin(selected_peak_ids)].copy()
        if not selected_df.empty:
            selected_df["abs_amplitude"] = np.abs(selected_df["amplitude"].astype(float))
        return empty_metrics, selected_df

    return fit_exponential_envelope(
        peak_df,
        n_peaks=len(selected_peak_ids),
        polarity=polarity,
        selected_peak_ids=selected_peak_ids,
        file_name=file_name,
    )


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
    """Plot the ringdown waveform and large clickable peak markers."""
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
            )
        )

    if not peak_df.empty:
        selected_set = set(int(x) for x in selected_peak_ids)
        selected_point_indices = [
            int(i)
            for i, peak_id in enumerate(peak_df["peak_id"].to_list())
            if int(peak_id) in selected_set
        ]
        fig.add_trace(
            go.Scatter(
                x=peak_df["tempo_us"],
                y=peak_df["amplitude"],
                mode="markers",
                name="clique nos picos",
                customdata=peak_df[["peak_id"]].to_numpy(),
                selectedpoints=selected_point_indices if selected_point_indices else None,
                marker=dict(size=14, symbol="circle-open"),
                selected=dict(marker=dict(size=20, opacity=1.0)),
                unselected=dict(marker=dict(opacity=0.80)),
            )
        )

    x_range = [float(start_us), float(end_us)] if end_us > start_us else None
    y_range = None
    if focus_y_on_peaks and not peak_df.empty:
        y_values = peak_df["amplitude"].astype(float).to_numpy()
    else:
        y_values = y_win.astype(float) if len(y_win) else np.array([], dtype=float)
    y_values = y_values[np.isfinite(y_values)]
    if y_values.size:
        y_min = float(np.nanmin(y_values))
        y_max = float(np.nanmax(y_values))
        if np.isclose(y_min, y_max):
            pad = max(abs(y_max) * 0.35, 5.0)
        else:
            pad = max((y_max - y_min) * 0.20, 5.0)
        y_range = [y_min - pad, y_max + pad]

    fig.update_layout(
        height=520,
        xaxis_title="Tempo (µs)",
        yaxis_title="Amplitude corrigida",
        hovermode="closest",
        clickmode="event+select",
        dragmode="zoom",
        margin=dict(l=40, r=20, t=35, b=40),
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
            yaxis_title="|Amplitude do pico|",
            margin=dict(l=40, r=20, t=35, b=40),
        )
        return fig

    t0_us = float(fit_df["tempo_us"].iloc[0])
    x_rel = fit_df["tempo_us"].astype(float) - t0_us
    y_abs = np.abs(fit_df["amplitude"].astype(float))
    fig.add_trace(
        go.Scatter(
            x=x_rel,
            y=y_abs,
            mode="markers",
            name="picos selecionados",
            marker=dict(size=13, symbol="diamond-open"),
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
            )
        )

    fig.update_layout(
        height=420,
        xaxis_title="Tempo relativo ao primeiro pico selecionado (µs)",
        yaxis_title="|Amplitude do pico|",
        yaxis_type="log" if log_y else "linear",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=35, b=40),
        legend_title="",
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=True)
    return fig


def compact_metrics_table(rows: list[dict]) -> pd.DataFrame:
    """Return only the most useful envelope columns for on-screen comparison."""
    if not rows:
        return pd.DataFrame()
    cols = [
        "arquivo",
        "metodo",
        "n_picos_fit",
        "tau_us",
        "r2_envelope",
        "periodo_mediano_us",
        "freq_envelope_khz",
        "decaimento_por_periodo_percent",
        "meia_vida_us",
    ]
    df = pd.DataFrame(rows)
    return df[[c for c in cols if c in df.columns]]


st.title("⚡ ISF Analyzer")
st.caption(
    f"Analisador local para Tektronix .ISF | versão {APP_VERSION} | foco: pulso, ringing, ressonância e eletroporação"
)

with st.sidebar:
    st.header("Configuração da análise")

    uploaded_files = st.file_uploader(
        "Carregue arquivos Tektronix .ISF",
        type=["isf", "ISF"],
        accept_multiple_files=True,
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
        value=-90.0,
        step=1.0,
        format="%.3f",
        help="Ajuste para pegar os picos finais da oscilação natural, após o disparo principal.",
    )
    ring_end_us = st.number_input(
        "Fim da janela de ringing (µs)",
        value=240.0,
        step=1.0,
        format="%.3f",
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
        "Carregue um ou mais arquivos `.ISF` na barra lateral. "
        "O `.PNG` do osciloscópio é útil para conferência visual, mas o `.ISF` contém a forma de onda real."
    )
    st.stop()

waveforms: list[dict] = []
errors: list[str] = []

for file in uploaded_files:
    try:
        waveforms.append(parse_uploaded_file(file.name, file.getvalue()))
    except Exception as exc:
        errors.append(f"{file.name}: {exc}")

if errors:
    st.error("Alguns arquivos não puderam ser lidos:\n\n" + "\n".join(errors))

if not waveforms:
    st.stop()

metrics = [
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
metrics_df = metrics_dataframe(metrics)

ring_metrics = [
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
ring_metrics_df = metrics_dataframe(ring_metrics)



tab_signal, tab_export, tab_header = st.tabs(
    [
        "Análise de sinais",
        "Exportação",
        "Cabeçalho",
    ]
)

with tab_signal:
    st.subheader("Análise de sinais")
    st.caption(
        "Escolha uma operação por vez. A tela mostra apenas os controles úteis para aquela análise."
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Arquivos", len(waveforms))
    summary_cols[1].metric("Gap", _format_metric(gap_mm, "mm"))
    summary_cols[2].metric("Carga", _format_metric(resistance_ohm, "Ω"))
    summary_cols[3].metric("Amostras", f"{sum(len(item['value']) for item in waveforms):,}".replace(",", "."))

    analysis_mode = st.radio(
        "Operação",
        ["Sinais", "Envelope", "Comparação", "Potência"],
        horizontal=True,
        key="signal_analysis_mode_v026",
        help=(
            "Sinais: visualizar curvas e métricas gerais. Envelope: selecionar picos por clique e ajustar decaimento. "
            "Comparação: antes/depois. Potência: análise V × I."
        ),
    )

    if analysis_mode == "Sinais":
        st.subheader("Sinais")
        control_cols = st.columns(4)
        selected_names = control_cols[0].multiselect(
            "Arquivos",
            [item["name"] for item in waveforms],
            default=[item["name"] for item in waveforms[: min(4, len(waveforms))]],
            key="signals_selected_v026",
        )
        normalize = control_cols[1].checkbox(
            "Normalizar",
            value=False,
            key="signals_normalize_v026",
            help="Divide cada sinal pelo próprio pico absoluto.",
        )
        corrected_overview = control_cols[2].checkbox(
            "Remover baseline",
            value=True,
            key="signals_corrected_v026",
        )
        use_custom_window = control_cols[3].checkbox(
            "Recortar janela",
            value=False,
            key="signals_window_enable_v026",
        )

        if use_custom_window:
            win_cols = st.columns(2)
            overview_start_us = win_cols[0].number_input(
                "Início (µs)",
                value=ring_start_us,
                step=1.0,
                key="signals_start_us_v026",
            )
            overview_end_us = win_cols[1].number_input(
                "Fim (µs)",
                value=ring_end_us,
                step=1.0,
                key="signals_end_us_v026",
            )
        else:
            overview_start_us = None
            overview_end_us = None

        selected_waveforms = [item for item in waveforms if item["name"] in selected_names]
        if not selected_waveforms:
            st.warning("Selecione pelo menos um arquivo.")
        else:
            fig = plot_waveforms(
                selected_waveforms,
                normalize=normalize,
                corrected=corrected_overview,
                baseline_mode=baseline_mode,
                max_points=max_plot_points,
                start_us=overview_start_us,
                end_us=overview_end_us,
            )
            st.plotly_chart(fig, use_container_width=True, key="signals_waveform_chart_v026")

        selected_metric_name = st.selectbox(
            "Resumo do arquivo",
            [item["name"] for item in waveforms],
            key="signals_metric_file_v026",
        )
        selected_metrics = next(row for row in metrics if row["arquivo"] == selected_metric_name)
        cols = st.columns(5)
        cols[0].metric("Vmax", _format_metric(selected_metrics["v_max"], "V"))
        cols[1].metric("Vmin", _format_metric(selected_metrics["v_min"], "V"))
        cols[2].metric("Vpp", _format_metric(selected_metrics["v_pp"], "V"))
        cols[3].metric("Campo", _format_metric(selected_metrics["campo_kv_cm"], "kV/cm"))
        cols[4].metric("Freq. FFT", _format_metric(selected_metrics["freq_fft_khz"], "kHz"))

        with st.expander("Tabela completa", expanded=False):
            st.dataframe(metrics_df, use_container_width=True)

    elif analysis_mode == "Envelope":
        st.subheader("Envelope")
        st.caption(
            "Fluxo: ajuste a janela → clique nos picos do gráfico superior → confira a exponencial no gráfico inferior. "
            "Nada é ajustado automaticamente até você selecionar pelo menos 2 picos ou usar o botão de autopreenchimento."
        )

        st.markdown("**1) Janela e detecção de picos**")
        control_cols = st.columns([1.5, 1, 1, 1, 1])
        ring_name = control_cols[0].selectbox(
            "Arquivo",
            [item["name"] for item in waveforms],
            key="envelope_file_v026",
        )
        env_start_us = control_cols[1].number_input(
            "Início (µs)",
            value=ring_start_us,
            step=1.0,
            format="%.3f",
            key="envelope_start_us_v026",
        )
        env_end_us = control_cols[2].number_input(
            "Fim (µs)",
            value=ring_end_us,
            step=1.0,
            format="%.3f",
            key="envelope_end_us_v026",
        )
        env_threshold = control_cols[3].slider(
            "Limiar (%)",
            min_value=1,
            max_value=50,
            value=int(round(peak_threshold_fraction * 100)),
            step=1,
            key="envelope_threshold_v026",
        ) / 100.0
        env_min_distance = control_cols[4].number_input(
            "Dist. mín. (µs)",
            min_value=0.001,
            value=min_peak_distance_us,
            step=0.5,
            format="%.3f",
            key="envelope_min_distance_v026",
        )

        control_cols_2 = st.columns([1, 1, 1, 1])
        polarity = control_cols_2[0].selectbox(
            "Tipo de pico",
            ["Extremos positivos e negativos", "Somente positivos", "Somente negativos"],
            key="envelope_polarity_v026",
        )
        n_fit_peaks = control_cols_2[1].number_input(
            "N para autopreencher",
            min_value=2,
            max_value=12,
            value=3,
            step=1,
            key="envelope_n_peaks_v026",
        )
        focus_y = control_cols_2[2].checkbox(
            "Ampliar eixo Y nos picos",
            value=True,
            key="envelope_focus_y_v026",
            help="Útil quando o pulso principal é muito maior que os picos finais do ringing.",
        )
        log_y_fit = control_cols_2[3].checkbox(
            "Gráfico inferior em log",
            value=False,
            key="envelope_log_y_v026",
        )

        ring_item = next(item for item in waveforms if item["name"] == ring_name)
        peak_df = add_peak_ids(
            ringdown_peak_table(
                ring_item["time_s"],
                ring_item["value"],
                start_us=env_start_us,
                end_us=env_end_us,
                baseline_mode=baseline_mode,
                peak_threshold_fraction=env_threshold,
                min_peak_distance_us=env_min_distance,
            )
        )
        peak_df = filter_peak_table_by_polarity(peak_df, polarity).reset_index(drop=True)
        if not peak_df.empty:
            peak_df["peak_id"] = np.arange(len(peak_df), dtype=int)

        selected_ids = selected_peak_ids_for_file(ring_name)
        valid_peak_ids = set(int(x) for x in peak_df["peak_id"].to_list()) if not peak_df.empty else set()
        selected_ids = [int(x) for x in selected_ids if int(x) in valid_peak_ids]
        set_selected_peak_ids_for_file(ring_name, selected_ids)

        action_cols = st.columns([1, 1, 2])
        if action_cols[0].button("Usar últimos N", key="envelope_use_last_n_v026"):
            set_selected_peak_ids_for_file(
                ring_name,
                fallback_peak_ids(peak_df, int(n_fit_peaks), polarity),
            )
            st.rerun()
        if action_cols[1].button("Limpar picos", key="envelope_clear_v026"):
            set_selected_peak_ids_for_file(ring_name, [])
            st.session_state[_last_click_key(ring_name)] = ""
            st.rerun()
        action_cols[2].info(
            f"{len(peak_df)} picos detectados na janela. {len(selected_ids)} pico(s) selecionado(s)."
        )

        st.markdown("**2) Clique nos picos desejados**")
        fig_click = plot_peak_selection_graph(
            ring_item,
            peak_df,
            selected_ids,
            start_us=env_start_us,
            end_us=env_end_us,
            baseline_mode=baseline_mode,
            max_points=max_plot_points,
            focus_y_on_peaks=focus_y,
        )
        if plotly_events is not None:
            clicked_points = plotly_events(
                fig_click,
                click_event=True,
                hover_event=False,
                select_event=False,
                override_height=520,
                override_width="100%",
                key=f"envelope_click_chart_{_state_suffix(ring_name)}_v026",
            )
            changed = toggle_peak_selection_from_clicks(
                clicked_points,
                peak_df,
                selected_state_key=_peak_selection_key(ring_name),
                last_click_state_key=_last_click_key(ring_name),
            )
            if changed:
                st.rerun()
        else:
            st.warning(
                "Seleção por clique indisponível. Instale: pip install streamlit-plotly-events"
            )
            st.plotly_chart(fig_click, use_container_width=True, key="envelope_static_chart_v026")

        selected_ids = selected_peak_ids_for_file(ring_name)
        envelope_metrics, fit_df = fit_selected_envelope_only(
            peak_df,
            selected_ids,
            polarity=polarity,
            file_name=ring_name,
        )

        st.markdown("**3) Envoltória exponencial calculada a partir dos picos selecionados**")
        result_cols = st.columns([2, 1])
        with result_cols[0]:
            fig_fit = plot_selected_envelope_fit(fit_df, envelope_metrics, log_y=log_y_fit)
            st.plotly_chart(fig_fit, use_container_width=True, key="envelope_fit_chart_v026")
        with result_cols[1]:
            if len(selected_ids) < 2:
                st.warning("Selecione pelo menos 2 picos no gráfico superior para calcular τ.")
            else:
                st.success(f"Ajuste usando {len(fit_df)} pico(s).")
            if not fit_df.empty:
                st.dataframe(
                    fit_df[["tempo_us", "tipo", "amplitude", "abs_amplitude"]],
                    use_container_width=True,
                    height=260,
                )
            else:
                st.dataframe(pd.DataFrame(), use_container_width=True, height=260)

        cols = st.columns(6)
        cols[0].metric("τ", _format_metric(envelope_metrics["tau_us"], "µs"))
        cols[1].metric("R²", _format_metric(envelope_metrics["r2_envelope"], ""))
        cols[2].metric("Período", _format_metric(envelope_metrics["periodo_mediano_us"], "µs"))
        cols[3].metric("Freq.", _format_metric(envelope_metrics["freq_envelope_khz"], "kHz"))
        cols[4].metric("Decaimento/ciclo", _format_metric(envelope_metrics["decaimento_por_periodo_percent"], "%"))
        cols[5].metric("Meia-vida", _format_metric(envelope_metrics["meia_vida_us"], "µs"))

        st.markdown("---")
        st.subheader("Comparação de envelopes salvos")
        st.caption(
            "A comparação usa as seleções manuais salvas por arquivo. Para incluir outro arquivo, selecione-o acima e clique em seus picos."
        )
        cmp_cols = st.columns([1, 1, 2])
        normalize_env = cmp_cols[0].checkbox(
            "Normalizar envelopes",
            value=True,
            key="envelope_compare_norm_v026",
        )
        if cmp_cols[1].button("Autopreencher todos", key="envelope_autofill_all_v026"):
            for item in waveforms:
                peaks_i = add_peak_ids(
                    ringdown_peak_table(
                        item["time_s"],
                        item["value"],
                        start_us=env_start_us,
                        end_us=env_end_us,
                        baseline_mode=baseline_mode,
                        peak_threshold_fraction=env_threshold,
                        min_peak_distance_us=env_min_distance,
                    )
                )
                peaks_i = filter_peak_table_by_polarity(peaks_i, polarity).reset_index(drop=True)
                if not peaks_i.empty:
                    peaks_i["peak_id"] = np.arange(len(peaks_i), dtype=int)
                set_selected_peak_ids_for_file(
                    item["name"],
                    fallback_peak_ids(peaks_i, int(n_fit_peaks), polarity),
                )
            st.rerun()
        cmp_cols[2].info("Use o autopreenchimento só para triagem rápida; para publicação, prefira seleção manual consistente.")

        envelope_rows = []
        for item in waveforms:
            peaks_i = add_peak_ids(
                ringdown_peak_table(
                    item["time_s"],
                    item["value"],
                    start_us=env_start_us,
                    end_us=env_end_us,
                    baseline_mode=baseline_mode,
                    peak_threshold_fraction=env_threshold,
                    min_peak_distance_us=env_min_distance,
                )
            )
            peaks_i = filter_peak_table_by_polarity(peaks_i, polarity).reset_index(drop=True)
            if not peaks_i.empty:
                peaks_i["peak_id"] = np.arange(len(peaks_i), dtype=int)
            ids_i = selected_peak_ids_for_file(item["name"])
            ids_i = [int(x) for x in ids_i if int(x) in set(peaks_i["peak_id"].to_list())]
            if len(ids_i) < 2:
                continue
            row, _fit_i = fit_selected_envelope_only(
                peaks_i,
                ids_i,
                polarity=polarity,
                file_name=item["name"],
            )
            if np.isfinite(row.get("tau_us", np.nan)):
                envelope_rows.append(row)

        envelope_df = pd.DataFrame(envelope_rows)
        if envelope_df.empty:
            st.info("Nenhum arquivo com pelo menos 2 picos selecionados para comparar.")
        else:
            fig_cmp = plot_envelope_comparison(envelope_df, normalize=normalize_env)
            st.plotly_chart(fig_cmp, use_container_width=True, key="envelope_compare_chart_v026")
            st.dataframe(compact_metrics_table(envelope_rows), use_container_width=True)
            st.download_button(
                "Baixar comparação de envelopes em CSV",
                data=envelope_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacao_envelopes_exponenciais.csv",
                mime="text/csv",
                key="download_envelope_compare_v026",
            )

        with st.expander("Picos detectados na janela atual", expanded=False):
            st.dataframe(peak_df, use_container_width=True)

    elif analysis_mode == "Comparação":
        st.subheader("Comparação")
        st.caption("Comparação antes × depois dentro da janela de ringing selecionada.")
        ring_cols = st.columns(2)
        cmp_start_us = ring_cols[0].number_input(
            "Início da janela (µs)",
            value=ring_start_us,
            step=1.0,
            format="%.3f",
            key="comparison_start_us_v026",
        )
        cmp_end_us = ring_cols[1].number_input(
            "Fim da janela (µs)",
            value=ring_end_us,
            step=1.0,
            format="%.3f",
            key="comparison_end_us_v026",
        )
        if len(waveforms) < 2:
            st.warning("Carregue pelo menos dois arquivos para comparar antes e depois.")
        else:
            col_ba_1, col_ba_2 = st.columns(2)
            before_name = col_ba_1.selectbox(
                "Antes",
                [item["name"] for item in waveforms],
                index=0,
                key="comparison_before_v026",
            )
            after_name = col_ba_2.selectbox(
                "Depois",
                [item["name"] for item in waveforms],
                index=min(1, len(waveforms) - 1),
                key="comparison_after_v026",
            )
            before_item = next(item for item in waveforms if item["name"] == before_name)
            after_item = next(item for item in waveforms if item["name"] == after_name)
            before_ring = ringdown_metrics(
                before_name,
                before_item["time_s"],
                before_item["value"],
                start_us=cmp_start_us,
                end_us=cmp_end_us,
                baseline_mode=baseline_mode,
                resistance_ohm=resistance_ohm,
                peak_threshold_fraction=peak_threshold_fraction,
                min_peak_distance_us=min_peak_distance_us,
            )
            after_ring = ringdown_metrics(
                after_name,
                after_item["time_s"],
                after_item["value"],
                start_us=cmp_start_us,
                end_us=cmp_end_us,
                baseline_mode=baseline_mode,
                resistance_ohm=resistance_ohm,
                peak_threshold_fraction=peak_threshold_fraction,
                min_peak_distance_us=min_peak_distance_us,
            )

            compare_df = compare_ringdown_metrics(before_ring, after_ring)
            shift_score = resonance_shift_score(compare_df)
            similarity = waveform_similarity_metrics(
                before_name,
                before_item["time_s"],
                before_item["value"],
                after_name,
                after_item["time_s"],
                after_item["value"],
                start_us=cmp_start_us,
                end_us=cmp_end_us,
                baseline_mode=baseline_mode,
            )

            cols = st.columns(5)
            metric_map = {row["metrica"]: row["delta_percent"] for _, row in compare_df.iterrows()}
            cols[0].metric("Δ período", _format_metric(metric_map.get("period_peaks_us"), "%"))
            cols[1].metric("Δ frequência", _format_metric(metric_map.get("freq_damped_khz"), "%"))
            cols[2].metric("Δ τ", _format_metric(metric_map.get("tau_envelope_us"), "%"))
            cols[3].metric("Δ Q", _format_metric(metric_map.get("quality_factor_q"), "%"))
            cols[4].metric("Δ energia", _format_metric(metric_map.get("ring_energy_resistive_j"), "%"))

            cols = st.columns(4)
            cols[0].metric("Shift score", _format_metric(shift_score, "%"))
            cols[1].metric("Correlação", _format_metric(similarity["pearson_r"], ""))
            cols[2].metric("NRMSE", _format_metric(similarity["nrmse"], ""))
            cols[3].metric("Atraso", _format_metric(similarity["delay_xcorr_us"], "µs"))

            normalize_ba = st.checkbox(
                "Normalizar curvas",
                value=False,
                key="comparison_normalize_v026",
            )
            fig_ba = plot_waveforms(
                [before_item, after_item],
                normalize=normalize_ba,
                corrected=True,
                baseline_mode=baseline_mode,
                max_points=max_plot_points,
                start_us=cmp_start_us,
                end_us=cmp_end_us,
            )
            st.plotly_chart(fig_ba, use_container_width=True, key="comparison_overlay_chart_v026")
            st.dataframe(compare_df, use_container_width=True)
            st.download_button(
                "Baixar comparação em CSV",
                data=compare_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacao_antes_depois_ringdown.csv",
                mime="text/csv",
                key="download_comparison_v026",
            )

    elif analysis_mode == "Potência":
        st.subheader("Potência")
        st.caption("Use quando houver um canal de tensão e um canal de corrente, ou corrente escalada por probe/shunt.")

        if len(waveforms) < 2:
            st.warning("Carregue pelo menos dois arquivos: um canal de tensão e um canal de corrente.")
        else:
            col1, col2, col3 = st.columns(3)
            voltage_name = col1.selectbox(
                "Tensão",
                [item["name"] for item in waveforms],
                index=0,
                key="power_voltage_v026",
            )
            current_name = col2.selectbox(
                "Corrente",
                [item["name"] for item in waveforms],
                index=min(1, len(waveforms) - 1),
                key="power_current_v026",
            )
            current_scale = col3.number_input(
                "Escala de corrente (A/unidade)",
                min_value=1e-12,
                value=1.0,
                step=0.1,
                format="%.6g",
                help="Use 1 se o canal já estiver em ampères. Se estiver em V de probe/shunt, informe A/V.",
                key="power_current_scale_v026",
            )

            voltage_item = next(item for item in waveforms if item["name"] == voltage_name)
            current_item = next(item for item in waveforms if item["name"] == current_name)

            t, v, i = align_current_to_voltage(
                voltage_item["time_s"],
                voltage_item["value"],
                current_item["time_s"],
                current_item["value"],
                current_scale_a_per_unit=current_scale,
            )
            p = v * i
            vi = vi_metrics(t, v, i)

            cols = st.columns(6)
            cols[0].metric("Imax", _format_metric(vi.get("i_max"), "A"))
            cols[1].metric("Imin", _format_metric(vi.get("i_min"), "A"))
            cols[2].metric("Pmax", _format_metric(vi.get("p_max_w"), "W"))
            cols[3].metric("Energia", _format_metric(vi.get("energia_j"), "J"))
            cols[4].metric("Carga", _format_metric(vi.get("carga_c"), "C"))
            cols[5].metric("R efetiva", _format_metric(vi.get("resistencia_efetiva_ohm"), "Ω"))

            cols = st.columns(4)
            cols[0].metric("|Z| FFT", _format_metric(vi.get("impedancia_fft_mag_ohm"), "Ω"))
            cols[1].metric("Fase Z", _format_metric(vi.get("impedancia_fft_phase_deg"), "°"))
            cols[2].metric("Delay V-I", _format_metric(vi.get("delay_v_i_xcorr_us"), "µs"))
            cols[3].metric("xcorr", _format_metric(vi.get("xcorr_v_i_peak"), ""))

            t_plot, p_plot = decimate_for_plot(t, p, max_points=max_plot_points)
            fig_p = go.Figure()
            fig_p.add_trace(
                go.Scattergl(x=t_plot * 1e6, y=p_plot, mode="lines", name="P(t)=V(t)I(t)")
            )
            fig_p.update_layout(
                height=500,
                xaxis_title="Tempo (µs)",
                yaxis_title="Potência (W)",
                hovermode="x unified",
                margin=dict(l=40, r=20, t=40, b=40),
            )
            fig_p.update_xaxes(showgrid=True)
            fig_p.update_yaxes(showgrid=True)
            st.plotly_chart(fig_p, use_container_width=True, key="power_chart_v026")
            st.dataframe(pd.DataFrame([vi]).T.rename(columns={0: "valor"}), use_container_width=True)
            st.download_button(
                "Baixar V-I-P em CSV",
                data=vip_csv_bytes(t, v, i, p),
                file_name="analise_v_i_p.csv",
                mime="text/csv",
                key="download_power_csv_v026",
            )

with tab_export:
    st.subheader("Exportação")
    st.caption("Área dedicada para baixar métricas, ringing e formas de onda em CSV.")

    st.download_button(
        "Baixar métricas gerais em CSV",
        data=metrics_df.to_csv(index=False).encode("utf-8"),
        file_name="metricas_isf.csv",
        mime="text/csv",
        key="download_general_metrics_v025",
    )

    st.download_button(
        "Baixar métricas de ringing em CSV",
        data=ring_metrics_df.to_csv(index=False).encode("utf-8"),
        file_name="metricas_ringdown_resonancia.csv",
        mime="text/csv",
        key="download_ring_metrics_v025",
    )

    export_name = st.selectbox(
        "Exportar forma de onda",
        [item["name"] for item in waveforms],
        key="export_waveform_select_v025",
    )
    export_item = next(item for item in waveforms if item["name"] == export_name)

    st.download_button(
        "Baixar forma de onda em CSV",
        data=waveform_csv_bytes(export_item),
        file_name=Path(export_name).with_suffix(".csv").name,
        mime="text/csv",
        key="download_waveform_csv_v025",
    )

with tab_header:
    st.subheader("Cabeçalho")
    st.caption("Metadados extraídos do arquivo ISF e cabeçalho bruto do Tektronix.")

    selected_header_name = st.selectbox(
        "Selecione o arquivo",
        [item["name"] for item in waveforms],
        key="header_select_v025",
    )
    header_item = next(item for item in waveforms if item["name"] == selected_header_name)

    st.subheader("Metadados extraídos")
    st.json(header_item["metadata"])

    st.subheader("Cabeçalho bruto")
    st.text_area(
        "Cabeçalho",
        header_item["header"],
        height=350,
        key="raw_header_text_v025",
    )
