from __future__ import annotations

from pathlib import Path
import hashlib
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:  # optional component; app still runs, but image-click selection is disabled
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
from ensaisf.isf_parser import read_isf_bytes


st.set_page_config(
    page_title="ISF Analyzer",
    page_icon="⚡",
    layout="wide",
)


APP_VERSION = "0.3.20-natural-ringdown-peaks"


# Global color order used by all analysis screens.
# 1st curve: orange, 2nd: blue. Additional curves use high-contrast,
# visually distinct colors while preserving the same file/color mapping across tabs.
SERIES_COLORS_RGB = [
    (230, 126, 34),  # orange - first curve
    (0, 109, 204),   # blue - second curve
    (0, 150, 90),    # green - third curve
    (45, 45, 45),    # charcoal - fourth curve
    (0, 155, 170),   # teal - fifth curve
    (190, 135, 0),   # golden brown - sixth curve
    (210, 0, 125),   # magenta - seventh curve
    (120, 80, 30),   # brown - eighth curve
    (90, 55, 160),   # violet - fallback only for larger overlays
    (80, 80, 80),    # neutral gray - fallback only
]
SERIES_COLORS_HEX = [f"rgb({r},{g},{b})" for r, g, b in SERIES_COLORS_RGB]
SELECTED_PEAK_COLOR_RGB = (235, 68, 68)
ENVELOPE_IMAGE_MAX_POINTS = 8_000
POWER_METRIC_MAX_POINTS = 12_000
POWER_PLOT_MAX_POINTS = 12_000


def _trapz(y: np.ndarray, x: np.ndarray) -> float:
    if len(y) < 2 or len(x) < 2:
        return float("nan")
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


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
        "data_hash": hashlib.md5(data).hexdigest(),
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


def peak_id_from_click_event(click_event: dict, peak_df: pd.DataFrame) -> int | None:
    """Return a peak id from Plotly click data, using customdata first."""
    custom = click_event.get("customdata") if isinstance(click_event, dict) else None
    if isinstance(custom, (list, tuple, np.ndarray)) and len(custom):
        custom = custom[0]
    try:
        return int(custom)
    except (TypeError, ValueError):
        return nearest_peak_id_from_click_event(click_event, peak_df)


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

    peak_id = peak_id_from_click_event(click_event, peak_df)
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
    """Filter peak table according to selected polarity/extrema naming."""
    if peak_df.empty:
        return peak_df.copy()

    positive_labels = {"Somente positivos", "Somente máximos"}
    negative_labels = {"Somente negativos", "Somente mínimos"}

    if polarity in positive_labels:
        return peak_df[peak_df["tipo"] == "positivo"].copy()
    if polarity in negative_labels:
        return peak_df[peak_df["tipo"] == "negativo"].copy()
    return peak_df.copy()


def _sort_peak_ids_by_time(peak_df: pd.DataFrame, peak_ids: list[int]) -> list[int]:
    """Sort selected peak IDs by their time position."""
    if peak_df.empty:
        return []
    order = {int(row["peak_id"]): float(row["tempo_us"]) for _, row in peak_df.iterrows()}
    return sorted(set(int(x) for x in peak_ids), key=lambda peak_id: order.get(peak_id, float("inf")))


def _last_n_extrema_ids(peak_df: pd.DataFrame, kind: str, n_items: int) -> list[int]:
    """Return last N extrema IDs by time for positive or negative extrema."""
    if peak_df.empty:
        return []
    filtered = peak_df[peak_df["tipo"] == kind].copy()
    if filtered.empty:
        return []
    return [int(x) for x in filtered.sort_values("tempo_us").tail(int(n_items))["peak_id"].to_list()]


def _dominance_series(peaks: pd.DataFrame) -> pd.Series:
    """Return a robust score for choosing relevant maxima.

    The raw amplitude alone fails when a local maximum lies below the zero
    axis. The prominence column, when available, captures how much the peak
    rises above its neighboring valleys, so it remains valid even for peaks
    with negative absolute voltage.
    """
    if peaks.empty:
        return pd.Series(dtype=float)
    if "prominence" in peaks.columns:
        prominence = peaks["prominence"].astype(float).abs()
    else:
        prominence = pd.Series(np.zeros(len(peaks)), index=peaks.index, dtype=float)
    amplitude = peaks["amplitude"].astype(float).abs()
    return np.maximum(amplitude, prominence)


def _largest_n_extrema_ids(peak_df: pd.DataFrame, n_items: int) -> list[int]:
    """Return N maxima with largest robust dominance score, sorted by time."""
    if peak_df.empty:
        return []
    peaks = peak_df.copy()
    peaks["dominance_score"] = _dominance_series(peaks)
    peaks = peaks[np.isfinite(peaks["dominance_score"]) & (peaks["dominance_score"] > 0)]
    if peaks.empty:
        return []
    selected = peaks.sort_values("dominance_score", ascending=False).head(int(n_items))
    return _sort_peak_ids_by_time(peak_df, [int(x) for x in selected["peak_id"].to_list()])


def dominant_positive_peak_candidates(
    peak_df: pd.DataFrame,
    max_candidates: int,
    min_separation_us: float,
    candidate_floor_fraction: float = 0.15,
) -> pd.DataFrame:
    """Keep dominant local maxima for the Envelope selector.

    A maximum does not need to be above the zero axis. This is important for
    late ringing, where a shifted centerline can make a real upper-envelope
    peak appear below 0 V. The dominant score therefore combines absolute
    amplitude and local prominence.
    """
    if peak_df.empty:
        return peak_df.copy()

    peaks = peak_df[peak_df["tipo"] == "positivo"].copy()
    peaks["dominance_score"] = _dominance_series(peaks)
    peaks = peaks[np.isfinite(peaks["dominance_score"]) & (peaks["dominance_score"] > 0)]
    if peaks.empty:
        return peaks

    max_candidates = max(1, int(max_candidates))
    min_separation_us = max(float(min_separation_us), 0.0)
    candidate_floor_fraction = float(candidate_floor_fraction)
    if not np.isfinite(candidate_floor_fraction):
        candidate_floor_fraction = 0.15
    candidate_floor_fraction = float(np.clip(candidate_floor_fraction, 0.03, 0.60))

    max_score = float(peaks["dominance_score"].max())
    if not np.isfinite(max_score) or max_score <= 0:
        return peaks.head(0).copy()

    floor = max_score * candidate_floor_fraction
    filtered = peaks[peaks["dominance_score"] >= floor].copy()
    if len(filtered) < min(2, len(peaks)):
        relaxed_floor = max_score * max(0.03, candidate_floor_fraction * 0.5)
        filtered = peaks[peaks["dominance_score"] >= relaxed_floor].copy()

    if filtered.empty:
        return peaks.head(0).copy()

    selected_rows = []
    for _, row in filtered.sort_values("dominance_score", ascending=False).iterrows():
        time_us = float(row["tempo_us"])
        if all(abs(time_us - float(chosen["tempo_us"])) >= min_separation_us for chosen in selected_rows):
            selected_rows.append(row)
        if len(selected_rows) >= max_candidates:
            break

    if not selected_rows:
        return peaks.head(0).copy()

    candidates = pd.DataFrame(selected_rows).sort_values("tempo_us").reset_index(drop=True)
    candidates["peak_id"] = np.arange(len(candidates), dtype=int)
    return candidates

def _natural_ringdown_peak_ids_after_forced_peak(
    peak_df: pd.DataFrame,
    n_items: int,
) -> list[int]:
    """Select the first N upper crests after the dominant forced crest.

    This is the default envelope workflow for resonant electroporation tests:
    the largest upper crest is treated as the end/reference of the forced
    resonance, and the exponential envelope is fitted on the following natural
    ringdown crests. Only local maxima already present in ``peak_df`` are used;
    valleys are never valid candidates here.
    """
    if peak_df.empty:
        return []

    n_items = max(1, int(n_items))
    peaks = peak_df.copy().sort_values("tempo_us").reset_index(drop=True)
    if peaks.empty:
        return []

    # Prefer prominence/dominance to raw amplitude so a large baseline shift does
    # not move the anchor to a visually misleading sample. Fall back safely.
    score_col = "dominance_score" if "dominance_score" in peaks.columns else "amplitude"
    scores = pd.to_numeric(peaks[score_col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    if scores.notna().any():
        forced_pos = int(scores.idxmax())
    else:
        forced_pos = int(pd.to_numeric(peaks["amplitude"], errors="coerce").idxmax())

    after = peaks.iloc[forced_pos + 1 :].copy()
    if len(after) >= n_items:
        return [int(x) for x in after.head(n_items)["peak_id"].to_list()]

    # If the selected window ends too close to the forced peak, still return the
    # available post-forced crests. If none exist, fall back to the dominant crest
    # itself so the UI shows a meaningful reference rather than random tail noise.
    if not after.empty:
        return [int(x) for x in after["peak_id"].to_list()]

    return [int(peaks.iloc[forced_pos]["peak_id"])]


def auto_select_positive_peak_ids(peak_df: pd.DataFrame, mode: str, n_items: int) -> list[int]:
    """Build automatic selection using upper-crest candidates only."""
    if peak_df.empty:
        return []

    n_items = max(1, int(n_items))
    if mode == "N picos após maior pico":
        ids = _natural_ringdown_peak_ids_after_forced_peak(peak_df, n_items)
    elif mode == "Últimos N picos":
        ids = [
            int(x)
            for x in peak_df.sort_values("tempo_us").tail(n_items)["peak_id"].to_list()
        ]
    else:
        ids = _largest_n_extrema_ids(peak_df, n_items)

    return _sort_peak_ids_by_time(peak_df, ids)


def auto_select_extrema_ids(peak_df: pd.DataFrame, mode: str, n_items: int) -> list[int]:
    """Backward-compatible alias for automatic upper-crest selection."""
    if mode in {"N picos após maior pico", "Após maior pico"}:
        return auto_select_positive_peak_ids(peak_df, "N picos após maior pico", n_items)
    if mode in {"Últimos N máximos", "Últimos N picos"}:
        return auto_select_positive_peak_ids(peak_df, "Últimos N picos", n_items)
    return auto_select_positive_peak_ids(peak_df, "N maiores picos", n_items)


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



def _state_suffix(name: str) -> str:
    """Return a stable Streamlit-session suffix for a file name."""
    return hashlib.md5(name.encode("utf-8")).hexdigest()[:10]


def _peak_selection_key(file_name: str) -> str:
    return f"envelope_selected_peak_ids_{_state_suffix(file_name)}_v035"


def _last_click_key(file_name: str) -> str:
    return f"envelope_last_click_signature_{_state_suffix(file_name)}_v035"


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


def _axis_ranges_for_envelope_view(
    t_win: np.ndarray,
    y_win: np.ndarray,
    peak_df: pd.DataFrame,
    start_us: float,
    end_us: float,
    focus_y_on_peaks: bool = True,
) -> tuple[list[float] | None, list[float] | None]:
    """Build robust axis ranges for waveform and peak views."""
    x_range = [float(start_us), float(end_us)] if end_us > start_us else None

    if focus_y_on_peaks and not peak_df.empty:
        y_values = peak_df["amplitude"].astype(float).to_numpy()
    else:
        y_values = y_win.astype(float) if len(y_win) else np.array([], dtype=float)

    y_values = y_values[np.isfinite(y_values)]
    y_range = None
    if y_values.size:
        y_min = float(np.nanmin(y_values))
        y_max = float(np.nanmax(y_values))
        if np.isclose(y_min, y_max):
            pad = max(abs(y_max) * 0.35, 5.0)
        else:
            pad = max((y_max - y_min) * 0.20, 5.0)
        y_range = [y_min - pad, y_max + pad]
    return x_range, y_range


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



def _to_pixel_x(x_value: float, x_range: tuple[float, float], plot_box: tuple[int, int, int, int]) -> float:
    left, _top, right, _bottom = plot_box
    x_min, x_max = x_range
    if np.isclose(x_max, x_min):
        return float(left)
    return left + (float(x_value) - x_min) * (right - left) / (x_max - x_min)


def _to_pixel_y(y_value: float, y_range: tuple[float, float], plot_box: tuple[int, int, int, int]) -> float:
    _left, top, _right, bottom = plot_box
    y_min, y_max = y_range
    if np.isclose(y_max, y_min):
        return float(bottom)
    return bottom - (float(y_value) - y_min) * (bottom - top) / (y_max - y_min)


def _draw_text(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, fill=(70, 76, 86)) -> None:
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text(position, text, fill=fill, font=font)


def _text_size(draw: ImageDraw.ImageDraw, text: str) -> tuple[int, int]:
    try:
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        return int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
    except Exception:
        return max(6 * len(text), 1), 12


def build_clickable_waveform_image(
    item: dict,
    peak_df: pd.DataFrame,
    selected_peak_ids: list[int],
    start_us: float,
    end_us: float,
    baseline_mode: str,
    max_points: int,
    focus_y_on_peaks: bool = True,
    image_width: int = 1400,
    image_height: int = 500,
) -> tuple[Image.Image, dict[int, tuple[float, float]]]:
    """Render a waveform as a PNG-like image and return peak pixel locations.

    Streamlit/Plotly click callbacks were unstable on some local installations.
    This image-based selector is intentionally simple: the user clicks the
    plotted marker, the app maps the pixel click to the nearest peak, and the
    selected peak IDs drive the envelope fit.
    """
    t = item["time_s"]
    y, _baseline = subtract_baseline(t, item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(t, y, start_us, end_us)
    x_range_list, y_range_list = _axis_ranges_for_envelope_view(
        t_win,
        y_win,
        peak_df,
        start_us,
        end_us,
        focus_y_on_peaks=focus_y_on_peaks,
    )
    x_range = (float(x_range_list[0]), float(x_range_list[1]))
    y_range = (float(y_range_list[0]), float(y_range_list[1]))

    img = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = 88, 32, image_width - 36, image_height - 66
    plot_box = (left, top, right, bottom)

    grid_color = (225, 230, 236)
    axis_color = (80, 88, 98)
    signal_color = (0, 109, 204)
    peak_color = (35, 145, 255)
    selected_color = (235, 68, 68)

    # Plot area and grid.
    draw.rectangle([left, top, right, bottom], outline=(238, 241, 245), width=1)
    for idx in range(6):
        gx = left + idx * (right - left) / 5
        draw.line([(gx, top), (gx, bottom)], fill=grid_color, width=1)
        x_val = x_range[0] + idx * (x_range[1] - x_range[0]) / 5
        _draw_text(draw, (int(gx) - 18, bottom + 10), f"{x_val:.0f}")
    for idx in range(5):
        gy = top + idx * (bottom - top) / 4
        draw.line([(left, gy), (right, gy)], fill=grid_color, width=1)
        y_val = y_range[1] - idx * (y_range[1] - y_range[0]) / 4
        _draw_text(draw, (10, int(gy) - 7), f"{y_val:.0f}")

    # Zero axes, when inside range.
    if x_range[0] <= 0 <= x_range[1]:
        x0 = _to_pixel_x(0, x_range, plot_box)
        draw.line([(x0, top), (x0, bottom)], fill=(110, 110, 110), width=1)
    if y_range[0] <= 0 <= y_range[1]:
        y0 = _to_pixel_y(0, y_range, plot_box)
        draw.line([(left, y0), (right, y0)], fill=(110, 110, 110), width=1)

    # Waveform line, decimated.
    if len(t_win):
        t_plot, y_plot = decimate_for_plot(t_win, y_win, max_points=max_points)
        points = []
        for tx, yy in zip(t_plot * 1e6, y_plot):
            if not np.isfinite(tx) or not np.isfinite(yy):
                continue
            px = _to_pixel_x(float(tx), x_range, plot_box)
            py = _to_pixel_y(float(yy), y_range, plot_box)
            points.append((px, py))
        if len(points) >= 2:
            draw.line(points, fill=signal_color, width=2)

    selected_set = set(int(x) for x in selected_peak_ids)
    peak_pixels: dict[int, tuple[float, float]] = {}
    if not peak_df.empty:
        for _, row in peak_df.iterrows():
            peak_id = int(row["peak_id"])
            px = _to_pixel_x(float(row["tempo_us"]), x_range, plot_box)
            py = _to_pixel_y(float(row["amplitude"]), y_range, plot_box)
            peak_pixels[peak_id] = (px, py)
            if peak_id in selected_set:
                r = 9
                draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 240, 240), outline=selected_color, width=4)
                draw.line([(px - 8, py), (px + 8, py)], fill=selected_color, width=2)
                draw.line([(px, py - 8), (px, py + 8)], fill=selected_color, width=2)
            else:
                r = 6
                draw.ellipse([px - r, py - r, px + r, py + r], fill="white", outline=peak_color, width=3)

    _draw_text(draw, (left, image_height - 28), "Tempo (µs)")
    _draw_text(draw, (left, 8), "Clique nos círculos dos picos para selecionar/desmarcar")
    _draw_text(draw, (image_width - 250, 8), "azul = detectado | vermelho = selecionado")
    # Y label simplified horizontally for readability in the image component.
    _draw_text(draw, (10, 8), "Amplitude corrigida")
    return img, peak_pixels


def nearest_peak_id_from_image_click(
    click_data: dict | None,
    peak_pixels: dict[int, tuple[float, float]],
    max_distance_px: float = 28.0,
) -> int | None:
    """Return nearest peak id from a streamlit-image-coordinates click."""
    if not click_data or not peak_pixels:
        return None
    try:
        click_x = float(click_data.get("x"))
        click_y = float(click_data.get("y"))
    except (TypeError, ValueError):
        return None
    best_id = None
    best_dist = float("inf")
    for peak_id, (px, py) in peak_pixels.items():
        dist = float(np.hypot(click_x - px, click_y - py))
        if dist < best_dist:
            best_dist = dist
            best_id = int(peak_id)
    if best_dist <= max_distance_px:
        return best_id
    return None


def toggle_peak_selection_from_image_click(
    click_data: dict | None,
    peak_pixels: dict[int, tuple[float, float]],
    peak_df: pd.DataFrame,
    selected_state_key: str,
    last_click_state_key: str,
) -> bool:
    """Toggle selected peak using an image coordinate click."""
    if not click_data:
        return False
    signature = f"{click_data.get('x')}:{click_data.get('y')}"
    if st.session_state.get(last_click_state_key) == signature:
        return False
    peak_id = nearest_peak_id_from_image_click(click_data, peak_pixels)
    if peak_id is None:
        st.session_state[last_click_state_key] = signature
        return False
    selected_ids = list(st.session_state.get(selected_state_key, []))
    if peak_id in selected_ids:
        selected_ids = [item for item in selected_ids if int(item) != peak_id]
    else:
        selected_ids.append(int(peak_id))
    peak_order = {
        int(row["peak_id"]): float(row["tempo_us"])
        for _, row in peak_df.iterrows()
    }
    selected_ids = sorted(set(selected_ids), key=lambda item: peak_order.get(int(item), float("inf")))
    st.session_state[selected_state_key] = selected_ids
    st.session_state[last_click_state_key] = signature
    return True


def _image_click_version_key(file_name: str) -> str:
    return f"envelope_image_click_version_{_state_suffix(file_name)}_v035"



def _multi_image_click_version_key() -> str:
    return "envelope_multi_image_click_version_v0311"


def _multi_last_click_key() -> str:
    return "envelope_multi_last_click_signature_v035"


def _auto_selection_signature_key(file_name: str) -> str:
    return f"envelope_auto_selection_signature_{_state_suffix(file_name)}_v035"


def _auto_selection_signature(
    file_name: str,
    peak_df: pd.DataFrame,
    n_peaks: int,
    mode: str,
    start_us: float,
    end_us: float,
    threshold: float,
    min_distance_us: float,
) -> str:
    """Return a compact signature for automatic envelope peak selection."""
    if peak_df.empty:
        time_digest = "empty"
    else:
        times = peak_df["tempo_us"].astype(float).round(6).astype(str).str.cat(sep=",")
        amplitudes = peak_df["amplitude"].astype(float).round(3).astype(str).str.cat(sep=",")
        time_digest = hashlib.md5(f"{times}|{amplitudes}".encode("utf-8")).hexdigest()[:10]
    return (
        f"{file_name}|{n_peaks}|{mode}|{start_us:.6g}|{end_us:.6g}|"
        f"{threshold:.6g}|{min_distance_us:.6g}|{len(peak_df)}|{time_digest}"
    )


def _draw_polyline_decimated(
    draw: ImageDraw.ImageDraw,
    t_win: np.ndarray,
    y_win: np.ndarray,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    plot_box: tuple[int, int, int, int],
    color: tuple[int, int, int],
    max_points: int,
) -> None:
    """Draw a fast decimated line in the image selector."""
    if len(t_win) < 2:
        return
    t_plot, y_plot = decimate_for_plot(t_win, y_win, max_points=max_points)
    points = []
    for tx, yy in zip(t_plot * 1e6, y_plot):
        if not np.isfinite(tx) or not np.isfinite(yy):
            continue
        points.append(
            (
                _to_pixel_x(float(tx), x_range, plot_box),
                _to_pixel_y(float(yy), y_range, plot_box),
            )
        )
    if len(points) >= 2:
        draw.line(points, fill=color, width=2)


def build_multi_clickable_waveform_image(
    items: list[dict],
    peaks_by_file: dict[str, pd.DataFrame],
    selected_by_file: dict[str, list[int]],
    start_us: float,
    end_us: float,
    baseline_mode: str,
    max_points: int,
    focus_y_on_peaks: bool = False,
    image_width: int = 1450,
    image_height: int = 560,
) -> tuple[Image.Image, dict[tuple[str, int], tuple[float, float]]]:
    """Render full waveforms with positive peak markers only.

    Envelope analysis keeps the complete ringdown waveform visible for context,
    but only local positive maxima are drawn as clickable markers. The selected
    peak IDs are then used to fit the exponential decay envelope.
    """
    x_range = (float(start_us), float(end_us)) if end_us > start_us else (0.0, 1.0)

    waveform_cache: list[tuple[dict, np.ndarray, np.ndarray]] = []
    y_pool: list[float] = []
    peak_y_pool: list[float] = []
    for item in items:
        t = item["time_s"]
        y, _baseline = subtract_baseline(t, item["value"], mode=baseline_mode)
        t_win, y_win, _indices = slice_window_us(t, y, start_us, end_us)
        waveform_cache.append((item, t_win, y_win))
        if len(y_win):
            values = y_win.astype(float)
            values = values[np.isfinite(values)]
            y_pool.extend(values.tolist())
        peak_df = peaks_by_file.get(item["name"], pd.DataFrame())
        if not peak_df.empty:
            values = peak_df["amplitude"].astype(float).to_numpy()
            values = values[np.isfinite(values)]
            peak_y_pool.extend(values.tolist())

    y_values = np.asarray(peak_y_pool if focus_y_on_peaks and peak_y_pool else y_pool, dtype=float)
    if not y_values.size:
        y_values = np.array([-1.0, 1.0])
    y_min = float(np.nanmin(y_values))
    y_max = float(np.nanmax(y_values))
    if np.isclose(y_min, y_max):
        pad = max(abs(y_max) * 0.35, 5.0)
    else:
        pad = max((y_max - y_min) * 0.16, 5.0)
    y_range = (y_min - pad, y_max + pad)

    img = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(img)
    # The plot area starts near the top. Curve legends are drawn inside the
    # graph, matching the Plotly envelope-comparison chart and avoiding label
    # overlap above the figure.
    left, top, right, bottom = 96, 32, image_width - 38, image_height - 72
    plot_box = (left, top, right, bottom)

    grid_color = (225, 230, 236)
    axis_color = (90, 96, 106)
    palette = SERIES_COLORS_RGB
    selected_color = SELECTED_PEAK_COLOR_RGB

    draw.rectangle([left, top, right, bottom], outline=(238, 241, 245), width=1)
    for idx in range(6):
        gx = left + idx * (right - left) / 5
        draw.line([(gx, top), (gx, bottom)], fill=grid_color, width=1)
        x_val = x_range[0] + idx * (x_range[1] - x_range[0]) / 5
        _draw_text(draw, (int(gx) - 18, bottom + 10), f"{x_val:.0f}")
    for idx in range(5):
        gy = top + idx * (bottom - top) / 4
        draw.line([(left, gy), (right, gy)], fill=grid_color, width=1)
        y_val = y_range[1] - idx * (y_range[1] - y_range[0]) / 4
        _draw_text(draw, (10, int(gy) - 7), f"{y_val:.0f}")

    if x_range[0] <= 0 <= x_range[1]:
        x0 = _to_pixel_x(0, x_range, plot_box)
        draw.line([(x0, top), (x0, bottom)], fill=axis_color, width=1)
    if y_range[0] <= 0 <= y_range[1]:
        y0 = _to_pixel_y(0, y_range, plot_box)
        draw.line([(left, y0), (right, y0)], fill=axis_color, width=1)

    peak_pixels: dict[tuple[str, int], tuple[float, float]] = {}

    for idx, (item, t_win, y_win) in enumerate(waveform_cache):
        name = item["name"]
        color = item.get("series_color_rgb", palette[idx % len(palette)])
        _draw_polyline_decimated(
            draw,
            t_win,
            y_win,
            x_range=x_range,
            y_range=y_range,
            plot_box=plot_box,
            color=color,
            max_points=max_points,
        )

    # Legend inside the plot area, like the Plotly chart in "Envoltórias calculadas".
    legend_items = [
        (item["name"][:36], item.get("series_color_rgb", palette[idx % len(palette)]))
        for idx, (item, _t_win, _y_win) in enumerate(waveform_cache)
    ]
    if legend_items:
        text_width = max(_text_size(draw, name)[0] for name, _color in legend_items)
        legend_width = min(max(text_width + 82, 210), 380)
        legend_row_height = 24
        legend_height = 18 + legend_row_height * len(legend_items)
        legend_left = right - legend_width - 14
        legend_top = top + 12
        legend_right = right - 14
        legend_bottom = legend_top + legend_height
        draw.rounded_rectangle(
            [legend_left, legend_top, legend_right, legend_bottom],
            radius=8,
            fill=(255, 255, 255),
            outline=(218, 224, 232),
            width=1,
        )
        for idx, (name, color) in enumerate(legend_items):
            ly = legend_top + 10 + idx * legend_row_height
            lx = legend_left + 12
            draw.line([(lx, ly + 8), (lx + 30, ly + 8)], fill=color, width=3)
            draw.ellipse([lx + 11, ly + 3, lx + 21, ly + 13], fill="white", outline=color, width=3)
            _draw_text(draw, (lx + 40, ly), name, fill=(50, 56, 66))

    # Draw peak markers after all waveforms so the clickable targets stay visible.
    for idx, item in enumerate(items):
        name = item["name"]
        color = item.get("series_color_rgb", palette[idx % len(palette)])
        peak_df = peaks_by_file.get(name, pd.DataFrame())
        selected_set = set(int(x) for x in selected_by_file.get(name, []))
        if peak_df.empty:
            continue
        for _, row in peak_df.iterrows():
            peak_id = int(row["peak_id"])
            px = _to_pixel_x(float(row["tempo_us"]), x_range, plot_box)
            py = _to_pixel_y(float(row["amplitude"]), y_range, plot_box)
            peak_pixels[(name, peak_id)] = (px, py)
            if peak_id in selected_set:
                r = 10
                draw.ellipse(
                    [px - r, py - r, px + r, py + r],
                    fill=(255, 240, 240),
                    outline=selected_color,
                    width=4,
                )
                draw.line([(px - 9, py), (px + 9, py)], fill=selected_color, width=2)
                draw.line([(px, py - 9), (px, py + 9)], fill=selected_color, width=2)
            else:
                r = 7
                draw.ellipse([px - r, py - r, px + r, py + r], fill="white", outline=color, width=3)

    _draw_text(draw, (left, image_height - 32), "Tempo (us)")
    _draw_text(draw, (10, top - 28), "Amplitude")
    return img, peak_pixels


def nearest_multi_peak_from_image_click(
    click_data: dict | None,
    peak_pixels: dict[tuple[str, int], tuple[float, float]],
    max_distance_px: float = 30.0,
) -> tuple[str, int] | None:
    """Return nearest (file_name, peak_id) from an image-coordinate click."""
    if not click_data or not peak_pixels:
        return None
    try:
        click_x = float(click_data.get("x"))
        click_y = float(click_data.get("y"))
    except (TypeError, ValueError):
        return None
    best_key = None
    best_dist = float("inf")
    for peak_key, (px, py) in peak_pixels.items():
        dist = float(np.hypot(click_x - px, click_y - py))
        if dist < best_dist:
            best_dist = dist
            best_key = peak_key
    if best_dist <= max_distance_px:
        return best_key
    return None


def toggle_multi_peak_selection_from_image_click(
    click_data: dict | None,
    peak_pixels: dict[tuple[str, int], tuple[float, float]],
    peaks_by_file: dict[str, pd.DataFrame],
) -> bool:
    """Toggle selected peak for the file nearest to a shared overlay-image click."""
    if not click_data:
        return False
    signature = f"{click_data.get('x')}:{click_data.get('y')}"
    last_key = _multi_last_click_key()
    if st.session_state.get(last_key) == signature:
        return False

    peak_target = nearest_multi_peak_from_image_click(click_data, peak_pixels)
    st.session_state[last_key] = signature
    if peak_target is None:
        return False

    file_name, peak_id = peak_target
    selected_key = _peak_selection_key(file_name)
    selected_ids = list(st.session_state.get(selected_key, []))
    if int(peak_id) in selected_ids:
        selected_ids = [item for item in selected_ids if int(item) != int(peak_id)]
    else:
        selected_ids.append(int(peak_id))

    peak_df = peaks_by_file.get(file_name, pd.DataFrame())
    peak_order = {
        int(row["peak_id"]): float(row["tempo_us"])
        for _, row in peak_df.iterrows()
    }
    selected_ids = sorted(set(selected_ids), key=lambda item: peak_order.get(int(item), float("inf")))
    st.session_state[selected_key] = selected_ids
    return True

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


def _envelope_peak_cache_key(
    item: dict,
    start_us: float,
    end_us: float,
    baseline_mode: str,
    threshold: float,
    min_distance_us: float,
    candidate_count: int,
    candidate_floor_fraction: float,
) -> tuple:
    return (
        "envelope_peaks_v0320",
        item.get("data_hash"),
        round(float(start_us), 6),
        round(float(end_us), 6),
        baseline_mode,
        round(float(threshold), 8),
        round(float(min_distance_us), 6),
        int(candidate_count),
        round(float(candidate_floor_fraction), 6),
    )




def _moving_average_np(y: np.ndarray, window_samples: int) -> np.ndarray:
    """Fast centered moving average for envelope peak localization."""
    window_samples = int(window_samples)
    if window_samples <= 1 or y.size < 5:
        return y.astype(float, copy=True)
    window_samples = min(window_samples, max(3, y.size // 5))
    if window_samples % 2 == 0:
        window_samples += 1
    pad = window_samples // 2
    padded = np.pad(y.astype(float), (pad, pad), mode="edge")
    csum = np.cumsum(np.insert(padded, 0, 0.0))
    return (csum[window_samples:] - csum[:-window_samples]) / float(window_samples)


def _refine_indices_to_raw_extrema(
    y: np.ndarray,
    indices: np.ndarray,
    search_radius: int,
    kind: str,
) -> np.ndarray:
    """Refine extrema detected on a smoothed signal to the raw waveform."""
    indices = np.asarray(indices, dtype=int)
    if indices.size == 0:
        return indices
    search_radius = max(1, int(search_radius))
    refined: list[int] = []
    n = int(len(y))
    for idx in indices:
        left = max(0, int(idx) - search_radius)
        right = min(n, int(idx) + search_radius + 1)
        if right <= left:
            continue
        segment = y[left:right]
        if not np.any(np.isfinite(segment)):
            continue
        if kind == "max":
            refined.append(left + int(np.nanargmax(segment)))
        else:
            refined.append(left + int(np.nanargmin(segment)))
    return np.array(sorted(set(refined)), dtype=int)


def _prominence_for_upper_peaks(
    y: np.ndarray,
    max_indices: np.ndarray,
    min_indices: np.ndarray,
) -> np.ndarray:
    """Prominence of true upper peaks relative to nearest valleys.

    This helper deliberately computes prominence only for local maxima. It
    prevents negative minima/valleys from being treated as envelope peaks when
    the user requests "Últimos N picos".
    """
    max_indices = np.asarray(max_indices, dtype=int)
    min_indices = np.asarray(min_indices, dtype=int)
    if max_indices.size == 0:
        return np.array([], dtype=float)
    if min_indices.size == 0:
        return np.abs(y[max_indices].astype(float))

    min_indices = np.sort(min_indices)
    positions = np.searchsorted(min_indices, max_indices)
    prominence = np.zeros(max_indices.shape, dtype=float)

    for i, (idx, pos) in enumerate(zip(max_indices, positions)):
        valley_values: list[float] = []
        if pos > 0:
            valley_values.append(float(y[min_indices[pos - 1]]))
        if pos < min_indices.size:
            valley_values.append(float(y[min_indices[pos]]))
        if not valley_values:
            prominence[i] = max(0.0, abs(float(y[idx])))
            continue
        # For an upper peak, the limiting baseline is the higher neighboring
        # valley. A true crest must be above that local reference.
        local_reference = max(valley_values)
        prominence[i] = max(0.0, float(y[idx]) - local_reference)
    return prominence


def robust_upper_peak_candidates_from_waveform(
    item: dict,
    start_us: float,
    end_us: float,
    baseline_mode: str,
    threshold_fraction: float,
    min_distance_us: float,
    max_candidates: int,
    candidate_floor_fraction: float,
) -> tuple[pd.DataFrame, int]:
    """Return only upper-lobe maxima for envelope fitting.

    The previous decay-aware detector could allow lower extrema to enter the
    candidate pool in late low-amplitude portions of the waveform. This routine
    re-detects candidates from the waveform itself and explicitly accepts only
    local maxima/crests. A crest may be below the zero axis, but it must still
    be above its neighboring valleys.
    """
    y, _baseline = subtract_baseline(item["time_s"], item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(item["time_s"], y, start_us, end_us)
    if len(y_win) < 5:
        return pd.DataFrame(columns=["tipo", "tempo_us", "amplitude", "prominence", "abs_amplitude", "dominance_score", "peak_id"]), 0

    finite_mask = np.isfinite(y_win)
    if not np.any(finite_mask):
        return pd.DataFrame(columns=["tipo", "tempo_us", "amplitude", "prominence", "abs_amplitude", "dominance_score", "peak_id"]), 0

    dt = float(np.median(np.diff(t_win))) if len(t_win) > 1 else 0.0
    min_distance_samples = 1
    if dt > 0:
        min_distance_samples = max(1, int(round(float(min_distance_us) * 1e-6 / dt)))

    # Smooth only for locating broad lobes. The plotted and fitted amplitudes
    # still come from the original baseline-corrected waveform.
    smooth_window = max(5, min(2501, min_distance_samples // 6))
    if smooth_window % 2 == 0:
        smooth_window += 1
    y_detect = _moving_average_np(y_win.astype(float), smooth_window)

    max_detect = np.flatnonzero((y_detect[1:-1] > y_detect[:-2]) & (y_detect[1:-1] >= y_detect[2:])) + 1
    min_detect = np.flatnonzero((y_detect[1:-1] < y_detect[:-2]) & (y_detect[1:-1] <= y_detect[2:])) + 1

    refine_radius = max(2, min_distance_samples // 3)
    max_idx = _refine_indices_to_raw_extrema(y_win, max_detect, refine_radius, kind="max")
    min_idx = _refine_indices_to_raw_extrema(y_win, min_detect, refine_radius, kind="min")

    # Keep only extrema that are local maxima in a small neighborhood. This is
    # the guard that prevents valleys from being displayed as candidate peaks.
    guard_radius = max(2, min(refine_radius, max(3, min_distance_samples // 4)))
    valid_maxima: list[int] = []
    for idx in max_idx:
        left = max(0, int(idx) - guard_radius)
        right = min(len(y_win), int(idx) + guard_radius + 1)
        segment = y_win[left:right]
        if segment.size == 0 or not np.any(np.isfinite(segment)):
            continue
        if float(y_win[idx]) >= float(np.nanmax(segment)) - 1e-12:
            valid_maxima.append(int(idx))
    max_idx = np.array(sorted(set(valid_maxima)), dtype=int)

    if max_idx.size == 0:
        return pd.DataFrame(columns=["tipo", "tempo_us", "amplitude", "prominence", "abs_amplitude", "dominance_score", "peak_id"]), 0

    prominence = _prominence_for_upper_peaks(y_win, max_idx, min_idx)
    y_range = float(np.nanmax(y_win) - np.nanmin(y_win))
    peak_abs = float(np.nanmax(np.abs(y_win)))
    scale = max(peak_abs, 0.5 * y_range, 1e-12)
    max_prominence = float(np.nanmax(prominence)) if prominence.size else 0.0

    # Use a gentle absolute threshold plus a relative prominence floor. This
    # keeps late low-amplitude crests available for "Últimos N picos" while
    # rejecting sample noise.
    threshold_floor = max(float(threshold_fraction) * scale, float(candidate_floor_fraction) * max_prominence)
    if not np.isfinite(threshold_floor) or threshold_floor <= 0:
        threshold_floor = 0.0

    keep_mask = prominence >= threshold_floor
    # If the user configured an aggressive threshold, fall back to a softer
    # floor rather than returning no late crests.
    if np.sum(keep_mask) < min(2, len(max_idx)) and max_prominence > 0:
        keep_mask = prominence >= max(0.01 * max_prominence, 0.002 * scale)

    max_idx = max_idx[keep_mask]
    prominence = prominence[keep_mask]
    if max_idx.size == 0:
        return pd.DataFrame(columns=["tipo", "tempo_us", "amplitude", "prominence", "abs_amplitude", "dominance_score", "peak_id"]), 0

    # Enforce the requested minimum distance, always keeping the stronger crest
    # inside each exclusion window. This operates on maxima only.
    order = np.argsort(prominence)[::-1]
    kept: list[int] = []
    kept_prom: list[float] = []
    for pos in order:
        idx = int(max_idx[pos])
        if all(abs(idx - existing) >= min_distance_samples for existing in kept):
            kept.append(idx)
            kept_prom.append(float(prominence[pos]))
    kept_arr = np.array(kept, dtype=int)
    kept_prom_arr = np.array(kept_prom, dtype=float)

    # Limit visible candidates without destroying "Últimos N". If too many are
    # present, keep the most prominent set, then sort them by time for display.
    max_candidates = max(1, int(max_candidates))
    if kept_arr.size > max_candidates:
        keep_order = np.argsort(kept_prom_arr)[::-1][:max_candidates]
        kept_arr = kept_arr[keep_order]
        kept_prom_arr = kept_prom_arr[keep_order]

    order_time = np.argsort(t_win[kept_arr])
    kept_arr = kept_arr[order_time]
    kept_prom_arr = kept_prom_arr[order_time]

    rows = []
    for idx, prom in zip(kept_arr, kept_prom_arr):
        amp = float(y_win[int(idx)])
        rows.append(
            {
                "tipo": "positivo",
                "tempo_us": float(t_win[int(idx)] * 1e6),
                "amplitude": amp,
                "prominence": float(prom),
                "abs_amplitude": abs(amp),
                "dominance_score": max(abs(amp), float(prom)),
            }
        )
    df = pd.DataFrame(rows).sort_values("tempo_us").reset_index(drop=True)
    df["peak_id"] = np.arange(len(df), dtype=int)
    return df, int(len(max_detect))

def cached_dominant_positive_peaks(
    item: dict,
    start_us: float,
    end_us: float,
    baseline_mode: str,
    threshold: float,
    min_distance_us: float,
    candidate_count: int,
    candidate_floor_fraction: float,
) -> tuple[pd.DataFrame, int]:
    """Cache dominant peak detection across click reruns."""
    cache = st.session_state.setdefault("_envelope_peak_cache_v0320", {})
    key = _envelope_peak_cache_key(
        item,
        start_us,
        end_us,
        baseline_mode,
        threshold,
        min_distance_us,
        candidate_count,
        candidate_floor_fraction,
    )
    if key not in cache:
        peak_df, raw_count = robust_upper_peak_candidates_from_waveform(
            item,
            start_us=start_us,
            end_us=end_us,
            baseline_mode=baseline_mode,
            threshold_fraction=threshold,
            min_distance_us=min_distance_us,
            max_candidates=int(candidate_count),
            candidate_floor_fraction=candidate_floor_fraction,
        )
        cache[key] = (peak_df.copy(), int(raw_count))
    peak_df, raw_count = cache[key]
    return peak_df.copy(), int(raw_count)


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
    return rows, metrics_dataframe(rows)


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
    return rows, metrics_dataframe(rows)


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
        value=-100.0,
        step=1.0,
        format="%.3f",
        key="sidebar_ring_start_us_v036",
        help="Ajuste para pegar os picos finais da oscilação natural, após o disparo principal.",
    )
    ring_end_us = st.number_input(
        "Fim da janela de ringing (µs)",
        value=500.0,
        step=1.0,
        format="%.3f",
        key="sidebar_ring_end_us_v036",
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

for idx, file in enumerate(uploaded_files):
    try:
        item = parse_uploaded_file(file.name, file.getvalue())
        item["series_color_rgb"] = SERIES_COLORS_RGB[idx % len(SERIES_COLORS_RGB)]
        item["series_color_hex"] = SERIES_COLORS_HEX[idx % len(SERIES_COLORS_HEX)]
        waveforms.append(item)
    except Exception as exc:
        errors.append(f"{file.name}: {exc}")

if errors:
    st.error("Alguns arquivos não puderam ser lidos:\n\n" + "\n".join(errors))

if not waveforms:
    st.stop()



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


synchronize_file_dependent_state([item["name"] for item in waveforms])

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
        key="signal_analysis_mode_v035",
        help=(
            "Sinais: visualizar curvas e métricas gerais. Envelope: selecionar picos por clique e ajustar decaimento. "
            "Comparação: antes/depois. Potência: análise V × I."
        ),
    )

    # Keep the active operation in session state, but do not rebuild the
    # image-click component just because the user navigated away and returned.
    # Recreating the component key on mode changes can make the image selector
    # disappear on some Streamlit/component versions until another button rerun.
    st.session_state["_previous_signal_analysis_mode_v038"] = analysis_mode

    if analysis_mode == "Sinais":
        st.subheader("Sinais")
        metrics, metrics_df = build_waveform_metrics_table(
            waveforms,
            gap_mm=gap_mm,
            resistance_ohm=resistance_ohm,
            threshold_fraction=threshold_fraction,
            baseline_mode=baseline_mode,
        )
        control_cols = st.columns(4)
        selected_names = control_cols[0].multiselect(
            "Arquivos",
            [item["name"] for item in waveforms],
            default=list(st.session_state.get("signals_selected_v0314", [item["name"] for item in waveforms])),
            key="signals_selected_v0314",
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
            st.plotly_chart(fig, width="stretch", key="signals_waveform_chart_v026")

        selected_metric_name = st.selectbox(
            "Resumo do arquivo",
            [item["name"] for item in waveforms],
            key="signals_metric_file_v0314",
        )
        selected_metrics = next(row for row in metrics if row["arquivo"] == selected_metric_name)
        cols = st.columns(5)
        cols[0].metric("Vmax", _format_metric(selected_metrics["v_max"], "V"))
        cols[1].metric("Vmin", _format_metric(selected_metrics["v_min"], "V"))
        cols[2].metric("Vpp", _format_metric(selected_metrics["v_pp"], "V"))
        cols[3].metric("Campo", _format_metric(selected_metrics["campo_kv_cm"], "kV/cm"))
        cols[4].metric("Freq. FFT", _format_metric(selected_metrics["freq_fft_khz"], "kHz"))

        with st.expander("Tabela completa", expanded=False):
            st.dataframe(metrics_df, width="stretch")

    elif analysis_mode == "Envelope":
        st.subheader("Envelope")
        st.caption(
            "No modo Envelope, o gráfico mantém a onda completa no mesmo eixo, "
            "mas marca somente os máximos dominantes. Clique nos círculos para selecionar os picos usados na envoltória."
        )

        st.markdown("**1) Arquivos e janela de análise**")
        file_names = [item["name"] for item in waveforms]
        default_files = list(st.session_state.get("envelope_files_v0315", file_names))
        default_files = [name for name in default_files if name in file_names]
        env_selected_names = st.multiselect(
            "Arquivos no mesmo eixo",
            file_names,
            default=default_files,
            key="envelope_files_v0315",
            help="Selecione um ou mais arquivos. A opção 'Select all' agora mantém todos os arquivos carregados no Envelope.",
        )
        if len(env_selected_names) > 6:
            st.info(
                "Muitos arquivos no mesmo eixo podem reduzir a velocidade do clique no Envelope. "
                "A seleção é permitida, mas para análise fina recomenda-se revisar as curvas em grupos quando necessário."
            )

        control_cols = st.columns([1, 1, 1, 1])
        env_start_us = control_cols[0].number_input(
            "Início (µs)",
            value=ring_start_us,
            step=1.0,
            format="%.3f",
            key="envelope_start_us_v036",
        )
        env_end_us = control_cols[1].number_input(
            "Fim (µs)",
            value=ring_end_us,
            step=1.0,
            format="%.3f",
            key="envelope_end_us_v036",
        )
        env_threshold = control_cols[2].slider(
            "Limiar dos picos (%)",
            min_value=1,
            max_value=50,
            value=int(round(peak_threshold_fraction * 100)),
            step=1,
            key="envelope_threshold_v036",
        ) / 100.0
        env_min_distance = control_cols[3].number_input(
            "Distância mínima (µs)",
            min_value=0.001,
            value=min_peak_distance_us,
            step=0.5,
            format="%.3f",
            key="envelope_min_distance_v036",
        )
        polarity = "Somente máximos"

        auto_cols = st.columns([1, 1, 1, 1, 2])
        auto_select_enabled = auto_cols[0].checkbox(
            "Auto-selecionar",
            value=True,
            key="envelope_auto_enabled_v036",
            help="Quando ativo, o app já seleciona os picos da ressonância natural para calcular a envoltória.",
        )
        auto_n = auto_cols[1].number_input(
            "Picos por curva",
            min_value=1,
            max_value=12,
            value=4,
            step=1,
            key="envelope_auto_n_v036",
            help="Quantidade de cristas da ressonância natural usadas no ajuste. Com 1 pico não há ajuste exponencial; use 2 ou mais.",
        )
        auto_mode = auto_cols[2].selectbox(
            "Critério",
            ["N picos após maior pico", "N maiores picos", "Últimos N picos"],
            index=0,
            key="envelope_auto_mode_v0320",
            help=(
                "N picos após maior pico seleciona a resposta natural após a crista forçada dominante. "
                "N maiores picos prioriza amplitude; Últimos N picos é mantido como modo legado."
            ),
        )
        focus_y = auto_cols[3].checkbox(
            "Focar Y",
            value=False,
            key="envelope_focus_y_v036",
            help="Quando ativo, aproxima a escala vertical dos picos marcados. Desative para ver toda a onda na janela.",
        )
        auto_cols[4].info(
            "O gráfico mostra a onda completa. O app marca máximos dominantes com filtro adaptativo de proeminência, "
            "seleciona N automaticamente em vermelho e permite ajuste manual por clique."
        )

        option_cols = st.columns([1, 1, 4])
        log_y_fit = option_cols[0].checkbox(
            "Envelope em log",
            value=False,
            key="envelope_log_y_v036",
        )
        normalize_env = option_cols[1].checkbox(
            "Comparar normalizado",
            value=True,
            key="envelope_compare_norm_v036",
        )
        option_cols[2].caption(
            "Use o clique no pico para desmarcar/remarcar. Se alterar N, janela, limiar ou critério, "
            "a seleção automática é recalculada."
        )

        if not env_selected_names:
            st.warning("Selecione pelo menos um arquivo para analisar o envelope.")
        else:
            selected_items = [item for item in waveforms if item["name"] in env_selected_names]
            st.markdown("**2) Seleção dos picos no mesmo eixo**")

            peaks_by_file: dict[str, pd.DataFrame] = {}
            raw_peak_count_by_file: dict[str, int] = {}
            selected_by_file: dict[str, list[int]] = {}
            peak_summary_rows = []

            # Keep a compact pool of dominant maxima. This keeps the
            # image selector fast and prevents dozens of tiny late oscillations
            # from cluttering the Envelope workflow. The auto-selected N peaks
            # are chosen from this same candidate pool.
            # Keep enough candidates to make "Últimos N picos" robust, even
            # when many waveforms are overlaid. The adaptive floor below removes
            # tiny late ripples, so a larger candidate pool does not clutter as much.
            if auto_mode == "N picos após maior pico":
                # Default physical workflow: keep enough post-forced crests to
                # fit the natural ringdown, but avoid very late ripple/noise.
                candidate_count = max(int(auto_n) + 8, 14)
                candidate_count = min(candidate_count, 80)
                candidate_floor_fraction = max(0.035, min(0.12, float(env_threshold) * 1.10))
                detection_threshold = max(0.01, min(float(env_threshold), float(env_threshold) * 0.85))
            elif auto_mode == "Últimos N picos":
                # Legacy mode: allow a larger pool, but candidates remain upper
                # crests only. This mode can be more sensitive to tail ripple.
                candidate_count = max(int(auto_n) * 10, int(auto_n) + 20, 32)
                candidate_count = min(candidate_count, 200)
                candidate_floor_fraction = max(0.015, min(0.06, float(env_threshold) * 0.60))
                detection_threshold = max(0.006, min(float(env_threshold), float(env_threshold) * 0.45))
            else:
                # For amplitude-priority analysis, keep a stricter pool so that
                # the selected points truly represent the dominant lobes.
                candidate_count = max(int(auto_n) * 4, int(auto_n) + 8, 16)
                candidate_count = min(candidate_count, 40)
                candidate_floor_fraction = max(0.10, min(0.30, float(env_threshold) * 3.0))
                detection_threshold = float(env_threshold)

            for ring_item in selected_items:
                peak_df, raw_count = cached_dominant_positive_peaks(
                    ring_item,
                    start_us=env_start_us,
                    end_us=env_end_us,
                    baseline_mode=baseline_mode,
                    threshold=detection_threshold,
                    min_distance_us=env_min_distance,
                    candidate_count=candidate_count,
                    candidate_floor_fraction=candidate_floor_fraction,
                )
                raw_peak_count_by_file[ring_item["name"]] = raw_count
                peaks_by_file[ring_item["name"]] = peak_df

                selected_ids = selected_peak_ids_for_file(ring_item["name"])
                valid_ids = set(peak_df["peak_id"].to_list()) if not peak_df.empty else set()
                selected_ids = [peak_id for peak_id in selected_ids if peak_id in valid_ids]

                if auto_select_enabled:
                    signature = _auto_selection_signature(
                        ring_item["name"],
                        peak_df,
                        int(auto_n),
                        auto_mode,
                        float(env_start_us),
                        float(env_end_us),
                        float(env_threshold),
                        float(env_min_distance),
                    )
                    signature_key = _auto_selection_signature_key(ring_item["name"])
                    if st.session_state.get(signature_key) != signature:
                        selected_ids = auto_select_positive_peak_ids(peak_df, auto_mode, int(auto_n))
                        st.session_state[signature_key] = signature

                set_selected_peak_ids_for_file(ring_item["name"], selected_ids)
                selected_by_file[ring_item["name"]] = selected_ids
                peak_summary_rows.append(
                    {
                        "arquivo": ring_item["name"],
                        "picos_brutos": raw_peak_count_by_file[ring_item["name"]],
                        "candidatos_crista": int(len(peak_df)),
                        "picos_selecionados": int(len(selected_ids)),
                    }
                )

            action_cols = st.columns([1, 1, 1, 3])
            if action_cols[0].button("Limpar seleção", key="clear_all_peak_selection_v036"):
                for name in env_selected_names:
                    set_selected_peak_ids_for_file(name, [])
                    # Preserve the current auto-signature so clearing does not
                    # immediately reselect the same peaks on the rerun.
                    peak_df = peaks_by_file.get(name, pd.DataFrame())
                    st.session_state[_auto_selection_signature_key(name)] = _auto_selection_signature(
                        name,
                        peak_df,
                        int(auto_n),
                        auto_mode,
                        float(env_start_us),
                        float(env_end_us),
                        float(env_threshold),
                        float(env_min_distance),
                    )
                st.session_state[_multi_last_click_key()] = None
                st.session_state[_multi_image_click_version_key()] = int(
                    st.session_state.get(_multi_image_click_version_key(), 0)
                ) + 1
                st.rerun()

            if action_cols[1].button("Detectar Automático", key="detect_auto_peak_selection_v037"):
                for name in env_selected_names:
                    peak_df = peaks_by_file.get(name, pd.DataFrame())
                    selected_ids = auto_select_positive_peak_ids(peak_df, auto_mode, int(auto_n))
                    set_selected_peak_ids_for_file(name, selected_ids)
                    st.session_state[_auto_selection_signature_key(name)] = _auto_selection_signature(
                        name,
                        peak_df,
                        int(auto_n),
                        auto_mode,
                        float(env_start_us),
                        float(env_end_us),
                        float(env_threshold),
                        float(env_min_distance),
                    )
                st.session_state[_multi_last_click_key()] = None
                st.session_state[_multi_image_click_version_key()] = int(
                    st.session_state.get(_multi_image_click_version_key(), 0)
                ) + 1
                st.rerun()

            action_cols[2].caption(
                f"Total selecionado: {sum(len(v) for v in selected_by_file.values())}"
            )
            action_cols[3].dataframe(pd.DataFrame(peak_summary_rows), width="stretch", height=130)

            st.caption(
                "No gráfico do Envelope a onda completa permanece desenhada. "
                "As marcações aparecem somente nas cristas/máximos locais relevantes; vermelho indica os picos usados no ajuste."
            )

            if any(df.empty for df in peaks_by_file.values()):
                empty_names = [name for name, df in peaks_by_file.items() if df.empty]
                st.warning(
                    "Sem cristas/máximos relevantes detectados em: " + ", ".join(empty_names) +
                    ". Ajuste a janela, reduza o limiar ou diminua a distância mínima."
                )

            if streamlit_image_coordinates is None:
                st.error(
                    "O componente de clique por imagem não está instalado. Rode: "
                    "pip install streamlit-image-coordinates"
                )
            else:
                if _multi_image_click_version_key() not in st.session_state:
                    st.session_state[_multi_image_click_version_key()] = 0

                st.caption(
                    "A legenda das curvas fica dentro do gráfico; vermelho indica os picos selecionados para o ajuste."
                )
                click_img, peak_pixels = build_multi_clickable_waveform_image(
                    selected_items,
                    peaks_by_file=peaks_by_file,
                    selected_by_file=selected_by_file,
                    start_us=env_start_us,
                    end_us=env_end_us,
                    baseline_mode=baseline_mode,
                    max_points=min(max_plot_points, ENVELOPE_IMAGE_MAX_POINTS),
                    focus_y_on_peaks=focus_y,
                    image_width=1450,
                    image_height=560,
                )
                image_state_signature = hashlib.md5(
                    repr(
                        [
                            tuple(env_selected_names),
                            float(env_start_us),
                            float(env_end_us),
                            float(env_threshold),
                            float(env_min_distance),
                            bool(focus_y),
                            int(auto_n),
                            auto_mode,
                            {name: tuple(selected_by_file.get(name, [])) for name in env_selected_names},
                        ]
                    ).encode("utf-8")
                ).hexdigest()[:10]
                click_data = streamlit_image_coordinates(
                    click_img,
                    width=1450,
                    key=(
                        "envelope_multi_image_click_"
                        f"{st.session_state[_multi_image_click_version_key()]}_"
                        f"{image_state_signature}_v0311"
                    ),
                )
                changed = toggle_multi_peak_selection_from_image_click(
                    click_data,
                    peak_pixels,
                    peaks_by_file=peaks_by_file,
                )
                if changed:
                    st.session_state[_multi_image_click_version_key()] = int(
                        st.session_state.get(_multi_image_click_version_key(), 0)
                    ) + 1
                    st.rerun()

            st.markdown("**3) Envoltórias calculadas**")
            envelope_rows = []
            envelope_fit_tables: dict[str, pd.DataFrame] = {}
            for ring_item in selected_items:
                name = ring_item["name"]
                selected_ids = selected_peak_ids_for_file(name)
                peak_df = peaks_by_file.get(name, pd.DataFrame())
                envelope_metrics, fit_df = fit_selected_envelope_only(
                    peak_df,
                    selected_ids,
                    polarity=polarity,
                    file_name=name,
                )
                envelope_fit_tables[name] = fit_df
                if np.isfinite(envelope_metrics.get("tau_us", np.nan)):
                    envelope_metrics["series_color"] = ring_item.get("series_color_hex", SERIES_COLORS_HEX[len(envelope_rows) % len(SERIES_COLORS_HEX)])
                    envelope_rows.append(envelope_metrics)

            if len(envelope_rows) == 0:
                st.info("Selecione pelo menos 2 picos máximos em um arquivo para calcular a primeira envoltória.")
            else:
                envelope_df = pd.DataFrame(envelope_rows)
                fig_cmp = plot_envelope_comparison(envelope_df, normalize=normalize_env)
                st.plotly_chart(fig_cmp, width="stretch", key="envelope_compare_chart_v035")
                st.dataframe(compact_metrics_table(envelope_rows), width="stretch")
                st.download_button(
                    "Baixar comparação de envelopes em CSV",
                    data=envelope_df.to_csv(index=False).encode("utf-8"),
                    file_name="comparacao_envelopes_exponenciais.csv",
                    mime="text/csv",
                    key="download_envelope_compare_v035",
                )

            with st.expander("Detalhar picos selecionados e detectados", expanded=False):
                for ring_item in selected_items:
                    name = ring_item["name"]
                    st.markdown(f"**{name}**")
                    fit_df = envelope_fit_tables.get(name, pd.DataFrame())
                    peak_df = peaks_by_file.get(name, pd.DataFrame())
                    if fit_df.empty:
                        st.caption("Ainda sem picos suficientes selecionados para ajuste.")
                    else:
                        st.dataframe(
                            fit_df[["tempo_us", "tipo", "amplitude", "abs_amplitude"]],
                            width="stretch",
                            height=160,
                        )
                    st.dataframe(peak_df, width="stretch", height=180)

    elif analysis_mode == "Comparação":
        st.subheader("Comparação")
        st.caption(
            "Comparação direta entre exatamente 2 arquivos: Referência × Comparado. "
            "Esta seleção é independente da aba Envelope."
        )
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
                key="comparison_before_v0314",
            )
            after_name = col_ba_2.selectbox(
                "Depois",
                [item["name"] for item in waveforms],
                index=min(1, len(waveforms) - 1),
                key="comparison_after_v0314",
            )
            if before_name == after_name:
                st.warning("Selecione dois arquivos diferentes para uma comparação física útil.")
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
            st.plotly_chart(fig_ba, width="stretch", key="comparison_overlay_chart_v026")
            st.dataframe(compare_df, width="stretch")
            st.download_button(
                "Baixar comparação em CSV",
                data=compare_df.to_csv(index=False).encode("utf-8"),
                file_name="comparacao_antes_depois_ringdown.csv",
                mime="text/csv",
                key="download_comparison_v026",
            )

    elif analysis_mode == "Potência":
        st.subheader("Potência")
        st.caption(
            "Use exatamente 2 arquivos: um canal de tensão e um canal de corrente. "
            "Esta seleção é independente das demais abas."
        )

        if len(waveforms) < 2:
            st.warning("Carregue pelo menos dois arquivos: um canal de tensão e um canal de corrente.")
        else:
            col1, col2, col3 = st.columns(3)
            voltage_name = col1.selectbox(
                "Tensão",
                [item["name"] for item in waveforms],
                index=0,
                key="power_voltage_v0314",
            )
            current_name = col2.selectbox(
                "Corrente",
                [item["name"] for item in waveforms],
                index=min(1, len(waveforms) - 1),
                key="power_current_v0314",
            )
            if voltage_name == current_name:
                st.warning("Selecione canais diferentes para tensão e corrente antes de interpretar P(t)=V(t)I(t).")
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

            with st.spinner("Calculando potência e impedância..."):
                t, v, i, p, vi = get_power_analysis_cached(
                    voltage_item,
                    current_item,
                    current_scale,
                )

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

            t_plot, p_plot = decimate_for_plot(t, p, max_points=min(max_plot_points, POWER_PLOT_MAX_POINTS))
            fig_p = go.Figure()
            fig_p.add_trace(
                go.Scattergl(
                    x=t_plot * 1e6,
                    y=p_plot,
                    mode="lines",
                    name="P(t)=V(t)I(t)",
                    line=dict(color=SERIES_COLORS_HEX[0]),
                )
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
            st.plotly_chart(fig_p, width="stretch", key="power_chart_v026")
            st.dataframe(pd.DataFrame([vi]).T.rename(columns={0: "valor"}), width="stretch")
            csv_key = (
                "power_vip_csv_v037",
                voltage_item.get("data_hash"),
                current_item.get("data_hash"),
                round(float(current_scale), 12),
            )
            if st.button("Preparar CSV V-I-P", key="prepare_power_csv_v037"):
                st.session_state[csv_key] = vip_csv_bytes(t, v, i, p)
            if csv_key in st.session_state:
                st.download_button(
                    "Baixar V-I-P em CSV",
                    data=st.session_state[csv_key],
                    file_name="analise_v_i_p.csv",
                    mime="text/csv",
                    key="download_power_csv_v037",
                )
            else:
                st.caption("O CSV completo de V-I-P é gerado sob demanda para manter a aba Potência mais rápida.")

with tab_export:
    st.subheader("Exportação")
    st.caption(
        "Área dedicada para baixar métricas, ringing e formas de onda em CSV. "
        "As métricas completas são geradas sob demanda para não deixar os cliques do Envelope lentos."
    )

    if st.button("Gerar métricas para exportação", key="prepare_export_metrics_v035"):
        metrics_rows, metrics_df = build_waveform_metrics_table(
            waveforms,
            gap_mm=gap_mm,
            resistance_ohm=resistance_ohm,
            threshold_fraction=threshold_fraction,
            baseline_mode=baseline_mode,
        )
        ring_rows, ring_metrics_df = build_ring_metrics_table(
            waveforms,
            ring_start_us=ring_start_us,
            ring_end_us=ring_end_us,
            baseline_mode=baseline_mode,
            resistance_ohm=resistance_ohm,
            peak_threshold_fraction=peak_threshold_fraction,
            min_peak_distance_us=min_peak_distance_us,
        )
        st.session_state["export_metrics_csv_v035"] = metrics_df.to_csv(index=False).encode("utf-8")
        st.session_state["export_ring_metrics_csv_v035"] = ring_metrics_df.to_csv(index=False).encode("utf-8")

    if "export_metrics_csv_v035" in st.session_state:
        st.download_button(
            "Baixar métricas gerais em CSV",
            data=st.session_state["export_metrics_csv_v035"],
            file_name="metricas_isf.csv",
            mime="text/csv",
            key="download_general_metrics_v035",
        )
        st.download_button(
            "Baixar métricas de ringing em CSV",
            data=st.session_state["export_ring_metrics_csv_v035"],
            file_name="metricas_ringdown_resonancia.csv",
            mime="text/csv",
            key="download_ring_metrics_v035",
        )
    else:
        st.info("Clique em 'Gerar métricas para exportação' quando precisar dos CSVs de métricas.")

    st.divider()
    export_name = st.selectbox(
        "Exportar forma de onda",
        [item["name"] for item in waveforms],
        key="export_waveform_select_v0314",
    )
    export_item = next(item for item in waveforms if item["name"] == export_name)

    if st.button("Gerar CSV da forma de onda", key="prepare_waveform_csv_v035"):
        st.session_state["export_waveform_csv_v035"] = waveform_csv_bytes(export_item)
        st.session_state["export_waveform_csv_name_v035"] = Path(export_name).with_suffix(".csv").name

    if (
        "export_waveform_csv_v035" in st.session_state
        and st.session_state.get("export_waveform_csv_name_v035") == Path(export_name).with_suffix(".csv").name
    ):
        st.download_button(
            "Baixar forma de onda em CSV",
            data=st.session_state["export_waveform_csv_v035"],
            file_name=st.session_state["export_waveform_csv_name_v035"],
            mime="text/csv",
            key="download_waveform_csv_v035",
        )
    else:
        st.info("Clique em 'Gerar CSV da forma de onda' para preparar este arquivo.")

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
