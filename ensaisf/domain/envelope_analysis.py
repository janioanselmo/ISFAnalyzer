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
    "_get_selection_points",
    "extract_selected_peak_ids",
    "_click_signature",
    "nearest_peak_id_from_click_event",
    "peak_id_from_click_event",
    "toggle_peak_selection_from_clicks",
    "filter_peak_table_by_polarity",
    "_sort_peak_ids_by_time",
    "_last_n_extrema_ids",
    "_dominance_series",
    "_largest_n_extrema_ids",
    "dominant_positive_peak_candidates",
    "_estimate_peak_period_us",
    "_forced_peak_id_from_candidates",
    "_natural_ringdown_peak_ids_after_forced_peak",
    "per_signal_detection_diagnostic",
    "auto_select_positive_peak_ids",
    "auto_select_extrema_ids",
    "fit_exponential_envelope",
    "add_peak_ids",
    "_state_suffix",
    "_peak_selection_key",
    "_last_click_key",
    "selected_peak_ids_for_file",
    "set_selected_peak_ids_for_file",
    "fallback_peak_ids",
    "fit_selected_envelope_only",
    "_axis_ranges_for_envelope_view",
    "_to_pixel_x",
    "_to_pixel_y",
    "_draw_text",
    "_text_size",
    "build_clickable_waveform_image",
    "nearest_peak_id_from_image_click",
    "toggle_peak_selection_from_image_click",
    "_image_click_version_key",
    "_multi_image_click_version_key",
    "_multi_last_click_key",
    "_auto_selection_signature_key",
    "_auto_selection_signature",
    "_draw_polyline_decimated",
    "_envelope_curve_points",
    "_draw_envelope_curve",
    "build_multi_clickable_waveform_image",
    "nearest_multi_peak_from_image_click",
    "toggle_multi_peak_selection_from_image_click",
    "compact_metrics_table",
    "_envelope_peak_cache_key",
    "_moving_average_np",
    "_refine_indices_to_raw_extrema",
    "_prominence_for_upper_peaks",
    "_cycle_crest_candidates",
    "robust_upper_peak_candidates_from_waveform",
    "cached_dominant_positive_peaks",
]


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


def _estimate_peak_period_us(peaks: pd.DataFrame, anchor_time_us: float) -> float:
    """Estimate the upper-crest period from relevant peak candidates."""
    if peaks.empty or "tempo_us" not in peaks.columns:
        return float("nan")

    times = pd.to_numeric(peaks["tempo_us"], errors="coerce").to_numpy(dtype=float)
    scores = _dominance_series(peaks).to_numpy(dtype=float) if len(peaks) else np.array([], dtype=float)
    valid = np.isfinite(times) & np.isfinite(scores) & (scores > 0)
    times = times[valid]
    scores = scores[valid]
    if times.size < 3:
        return float("nan")

    max_score = float(np.nanmax(scores)) if scores.size else float("nan")
    if not np.isfinite(max_score) or max_score <= 0:
        return float("nan")

    # Estimate period from the dominant crests, not from tiny tail ripple.
    strong = times[scores >= max_score * 0.25]
    if strong.size < 3:
        strong = times[scores >= max_score * 0.12]
    if strong.size < 3:
        # Last fallback: use all candidates, but still reject tiny time gaps.
        strong = times

    strong = np.sort(strong)
    diffs = np.diff(strong)
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if diffs.size == 0:
        return float("nan")

    # Remove gaps caused by missed cycles and very small gaps caused by shoulders.
    median = float(np.nanmedian(diffs))
    if not np.isfinite(median) or median <= 0:
        return float("nan")
    plausible = diffs[(diffs >= 0.45 * median) & (diffs <= 1.8 * median)]
    if plausible.size:
        return float(np.nanmedian(plausible))
    return median


def _forced_peak_id_from_candidates(peak_df: pd.DataFrame) -> int | None:
    """Return the forced-resonance anchor ID for one isolated waveform.

    This function receives candidates from a single file only. The anchor is
    the largest upper crest by corrected amplitude. It is not computed from the
    overlaid/multi-file plot.
    """
    if peak_df.empty:
        return None
    peaks = peak_df.copy()
    amplitudes = pd.to_numeric(peaks.get("amplitude"), errors="coerce")
    valid = peaks[amplitudes.notna()].copy()
    if valid.empty:
        return None
    # Use the highest upper crest as the end of forced resonance. Do not use
    # absolute value here, because a lower valley can have a larger magnitude
    # but is not an upper-envelope crest.
    pos = amplitudes.loc[valid.index].idxmax()
    try:
        return int(peaks.loc[pos, "peak_id"])
    except Exception:
        return None


def _natural_ringdown_peak_ids_after_forced_peak(
    peak_df: pd.DataFrame,
    n_items: int,
) -> list[int]:
    """Select the first N upper crests after the forced-resonance anchor.

    The detection is intentionally per-signal and intentionally simple at this
    stage: once the candidate table contains only upper crests for ONE file, the
    free/natural ringdown peaks are the next N crests after the largest crest.
    This avoids the previous failure mode where period tracking could jump to a
    wrong later ripple or appear to mix curves in an overlay.
    """
    if peak_df.empty:
        return []

    n_items = max(1, int(n_items))
    peaks = peak_df.copy().sort_values("tempo_us").reset_index(drop=True)
    forced_id = _forced_peak_id_from_candidates(peaks)
    if forced_id is None:
        return []

    forced_rows = peaks[peaks["peak_id"].astype(int) == int(forced_id)]
    if forced_rows.empty:
        return []
    forced_time = float(forced_rows.iloc[0]["tempo_us"])

    after = peaks[peaks["tempo_us"].astype(float) > forced_time].copy()
    if after.empty:
        return []

    # A very soft dominance guard removes baseline clicks/noise but does not
    # delete the late natural crests. Candidate generation already removed
    # lower valleys; here we only guard against accidental tiny baseline markers.
    forced_score = float(_dominance_series(forced_rows).iloc[0]) if len(forced_rows) else float("nan")
    if np.isfinite(forced_score) and forced_score > 0 and "dominance_score" in after.columns:
        score = pd.to_numeric(after["dominance_score"], errors="coerce")
        soft_floor = max(1e-12, 0.003 * forced_score)
        guarded = after[score.notna() & (score >= soft_floor)].copy()
        if len(guarded) >= min(n_items, len(after)):
            after = guarded

    selected = [int(x) for x in after.sort_values("tempo_us").head(n_items)["peak_id"].to_list()]
    return _sort_peak_ids_by_time(peak_df, selected)


def per_signal_detection_diagnostic(
    file_name: str,
    peak_df: pd.DataFrame,
    selected_ids: list[int],
    n_items: int,
    mode: str,
) -> dict:
    """Summarize detection for one waveform so overlay confusion is visible."""
    forced_id = _forced_peak_id_from_candidates(peak_df)
    forced_time = float("nan")
    forced_amp = float("nan")
    if forced_id is not None and not peak_df.empty:
        forced_row = peak_df[peak_df["peak_id"].astype(int) == int(forced_id)]
        if not forced_row.empty:
            forced_time = float(forced_row.iloc[0]["tempo_us"])
            forced_amp = float(forced_row.iloc[0]["amplitude"])

    selected_df = peak_df[peak_df.get("peak_id", pd.Series(dtype=int)).isin(selected_ids)].copy()
    selected_df = selected_df.sort_values("tempo_us") if not selected_df.empty else selected_df
    times = [] if selected_df.empty else [f"{float(x):.3f}" for x in selected_df["tempo_us"].to_list()]
    amps = [] if selected_df.empty else [f"{float(x):.3g}" for x in selected_df["amplitude"].to_list()]

    period_us = float("nan")
    if not peak_df.empty and "estimated_period_us" in peak_df.columns:
        period_values = pd.to_numeric(peak_df["estimated_period_us"], errors="coerce").dropna()
        if not period_values.empty:
            period_us = float(period_values.iloc[0])

    return {
        "arquivo": file_name,
        "modo": mode,
        "N": int(n_items),
        "ancora_forcada_us": forced_time,
        "ancora_forcada_amp": forced_amp,
        "periodo_estimado_us": period_us,
        "candidatos_do_sinal": int(len(peak_df)),
        "selecionados": int(len(selected_ids)),
        "tempos_sel_us": ", ".join(times),
        "amps_sel": ", ".join(amps),
    }


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

    # IMPORTANT: the visible envelope in the Streamlit graph must be fitted
    # from the selected upper crests themselves. A previous version used
    # ``envelope_amplitude`` derived from local peak-to-valley prominence.
    # That value is useful as a diagnostic, but it does not live in the same
    # y-coordinate system as the waveform; consequently the red envelope could
    # float above the last selected peaks. For the physical workflow requested
    # here, fit the final upper-envelope from the last selected peak coordinates.
    crest_amplitude = pd.to_numeric(fit_df["amplitude"], errors="coerce").to_numpy(dtype=float)
    fallback_amplitude = fit_df["abs_amplitude"].to_numpy(dtype=float)
    positive_reference = fallback_amplitude[np.isfinite(fallback_amplitude) & (fallback_amplitude > 0)]
    amplitude_floor = float(np.nanmax(positive_reference) * 1e-3) if positive_reference.size else 1e-12
    amplitude_floor = max(amplitude_floor, 1e-12)
    fit_amplitude = np.where(
        np.isfinite(crest_amplitude) & (crest_amplitude > 0),
        crest_amplitude,
        fallback_amplitude,
    )
    fit_amplitude = np.where(
        np.isfinite(fit_amplitude) & (fit_amplitude > 0),
        fit_amplitude,
        amplitude_floor,
    )
    fit_df["fit_amplitude"] = fit_amplitude
    fit_df["fit_amplitude_source"] = np.where(
        np.isfinite(crest_amplitude) & (crest_amplitude > 0),
        "selected upper-crest amplitude",
        "near-zero crest floor for exponential fit",
    )
    fit_df = fit_df[np.isfinite(fit_df["tempo_us"]) & (fit_df["fit_amplitude"] > 0)]

    if len(fit_df) < 2:
        metrics = empty_metrics.copy()
        metrics["arquivo"] = file_name
        metrics["metodo"] = method
        metrics["n_picos_fit"] = int(len(fit_df))
        return metrics, fit_df

    t_us = fit_df["tempo_us"].to_numpy(dtype=float)
    amp = fit_df["fit_amplitude"].to_numpy(dtype=float)
    t0_us = float(t_us[0])
    x_s = (t_us - t0_us) * 1e-6
    log_amp = np.log(amp)

    # Anchor the exponential at the first selected final crest. This makes the
    # red curve start at the first selected point and prevents the comparison
    # graph from visually implying that unselected earlier lobes were used.
    a0 = float(amp[0])
    if len(fit_df) == 2:
        slope = float((log_amp[-1] - log_amp[0]) / x_s[-1]) if x_s[-1] > 0 else float("nan")
        intercept = float(np.log(a0))
    else:
        denom = float(np.sum(x_s ** 2))
        slope = float(np.sum(x_s * (log_amp - np.log(a0))) / denom) if denom > 0 else float("nan")
        intercept = float(np.log(a0))

    pred_log = slope * x_s + intercept
    ss_res = float(np.sum((log_amp - pred_log) ** 2))
    ss_tot = float(np.sum((log_amp - np.mean(log_amp)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    tau_s = float(-1.0 / slope) if np.isfinite(slope) and slope < 0 else float("nan")
    tau_us = float(tau_s * 1e6) if np.isfinite(tau_s) else float("nan")

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


def _state_suffix(name: str) -> str:
    """Return a stable Streamlit-session suffix for a file name."""
    return hashlib.md5(name.encode("utf-8")).hexdigest()[:10]


def _peak_selection_key(file_name: str) -> str:
    return f"envelope_selected_peak_ids_{_state_suffix(file_name)}_v039"


def _last_click_key(file_name: str) -> str:
    return f"envelope_last_click_signature_{_state_suffix(file_name)}_v039"


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
            crest_amp = pd.to_numeric(selected_df["amplitude"], errors="coerce")
            fit_amp = crest_amp.where(crest_amp > 0, selected_df["abs_amplitude"])
            positive_ref = fit_amp[np.isfinite(fit_amp) & (fit_amp > 0)]
            amp_floor = float(positive_ref.max() * 1e-3) if len(positive_ref) else 1e-12
            amp_floor = max(amp_floor, 1e-12)
            selected_df["fit_amplitude"] = fit_amp.where(fit_amp > 0, amp_floor)
            selected_df["fit_amplitude_source"] = np.where(
                crest_amp > 0,
                "selected upper-crest amplitude",
                "near-zero crest floor for exponential fit",
            )
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
    return "envelope_multi_last_click_signature_v039"


def _auto_selection_signature_key(file_name: str) -> str:
    return f"envelope_auto_selection_signature_{_state_suffix(file_name)}_v039"


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


def _envelope_curve_points(
    envelope_metrics: dict,
    start_us: float,
    end_us: float,
    n_points: int = 300,
) -> tuple[np.ndarray, np.ndarray]:
    """Return absolute-time upper-envelope points for the context graph."""
    tau_us = float(envelope_metrics.get("tau_us", np.nan))
    a0 = float(envelope_metrics.get("a0", np.nan))
    t0_us = float(envelope_metrics.get("t0_us", np.nan))
    last_us = float(envelope_metrics.get("ultimo_pico_us", np.nan))
    if not all(np.isfinite(value) for value in [tau_us, a0, t0_us, last_us]):
        return np.array([], dtype=float), np.array([], dtype=float)
    if tau_us <= 0 or a0 <= 0 or last_us <= t0_us:
        return np.array([], dtype=float), np.array([], dtype=float)

    x0 = max(float(start_us), t0_us)
    x1 = min(float(end_us), last_us)
    if not np.isfinite(x0) or not np.isfinite(x1) or x1 <= x0:
        return np.array([], dtype=float), np.array([], dtype=float)

    x_us = np.linspace(x0, x1, max(16, int(n_points)))
    y_env = a0 * np.exp(-((x_us - t0_us) / tau_us))
    return x_us, y_env


def _draw_envelope_curve(
    draw: ImageDraw.ImageDraw,
    envelope_metrics: dict,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    plot_box: tuple[int, int, int, int],
    color: tuple[int, int, int] = SELECTED_PEAK_COLOR_RGB,
) -> None:
    """Draw the fitted upper envelope over the waveform context graph."""
    x_us, y_env = _envelope_curve_points(envelope_metrics, x_range[0], x_range[1])
    points = []
    for tx, yy in zip(x_us, y_env):
        if not np.isfinite(tx) or not np.isfinite(yy):
            continue
        points.append(
            (
                _to_pixel_x(float(tx), x_range, plot_box),
                _to_pixel_y(float(yy), y_range, plot_box),
            )
        )
    if len(points) >= 2:
        draw.line(points, fill=color, width=3)


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
    envelope_metrics_by_file: dict[str, dict] | None = None,
) -> tuple[Image.Image, dict[tuple[str, int], tuple[float, float]]]:
    """Render full waveforms with positive peak markers only.

    Envelope analysis keeps the complete ringdown waveform visible for context,
    but only local positive maxima are drawn as clickable markers. The selected
    peak IDs are then used to fit the exponential decay envelope. When at least
    two peaks are selected, the fitted upper envelope is also drawn over this
    same graph while the summary/comparison remains separated below.
    """
    envelope_metrics_by_file = envelope_metrics_by_file or {}
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
        env_x, env_y = _envelope_curve_points(
            envelope_metrics_by_file.get(item["name"], {}),
            start_us,
            end_us,
        )
        if len(env_x) and len(env_y):
            env_values = env_y.astype(float)
            env_values = env_values[np.isfinite(env_values)]
            y_pool.extend(env_values.tolist())
            peak_y_pool.extend(env_values.tolist())

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

    for item, _t_win, _y_win in waveform_cache:
        metrics = envelope_metrics_by_file.get(item["name"], {})
        if metrics:
            _draw_envelope_curve(
                draw,
                metrics,
                x_range=x_range,
                y_range=y_range,
                plot_box=plot_box,
                color=SELECTED_PEAK_COLOR_RGB,
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
    if envelope_metrics_by_file:
        _draw_text(draw, (left + 120, image_height - 32), "linha vermelha = envoltória ajustada")
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
        "envelope_peaks_v0324",
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


def _cycle_crest_candidates(
    y: np.ndarray,
    t: np.ndarray,
    min_indices: np.ndarray,
    min_distance_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return upper crests as maxima between consecutive valleys.

    For the envelope workflow, the physically relevant points are the upper
    crests of each free-oscillation cycle. A simple local-maximum detector can
    be fooled by tail ripple, baseline noise or by a smoothed minimum being
    refined incorrectly. Segmenting the signal from valley to valley makes the
    definition stricter: each candidate must be the maximum sample between two
    neighboring lower valleys. Therefore selected points cannot be valleys.
    """
    min_indices = np.asarray(sorted(set(int(i) for i in min_indices)), dtype=int)
    if min_indices.size < 2:
        return np.array([], dtype=int), np.array([], dtype=float)

    min_gap = max(1, int(min_distance_samples // 2))
    crest_indices: list[int] = []
    prominences: list[float] = []
    n = int(len(y))

    for left, right in zip(min_indices[:-1], min_indices[1:]):
        left = int(left)
        right = int(right)
        if right <= left + min_gap:
            continue
        if left < 0 or right >= n:
            continue

        segment = y[left : right + 1]
        if segment.size < 3 or not np.any(np.isfinite(segment)):
            continue

        rel_max = int(np.nanargmax(segment))
        idx = left + rel_max

        # Reject crests sitting at the valley boundaries. A physical upper lobe
        # must occur inside the valley-to-valley interval.
        edge_guard = max(1, min(min_gap // 2, max(1, (right - left) // 5)))
        if idx <= left + edge_guard or idx >= right - edge_guard:
            continue

        local_reference = max(float(y[left]), float(y[right]))
        prominence = float(y[idx]) - local_reference
        if not np.isfinite(prominence) or prominence <= 0:
            continue

        crest_indices.append(int(idx))
        prominences.append(float(prominence))

    if not crest_indices:
        return np.array([], dtype=int), np.array([], dtype=float)

    # Deduplicate rare duplicated indices from adjacent/flat minima.
    best: dict[int, float] = {}
    for idx, prom in zip(crest_indices, prominences):
        if idx not in best or prom > best[idx]:
            best[int(idx)] = float(prom)

    ordered = sorted(best)
    return np.array(ordered, dtype=int), np.array([best[i] for i in ordered], dtype=float)


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
    """Return upper-crest candidates using a period-tracked ringdown detector.

    The previous detector tried to rank isolated local maxima. That was fragile
    for these electroporation resonance records because the post-forced natural
    response is better described cycle-by-cycle. This detector works per file:

    1. baseline-corrects one waveform;
    2. smooths and decimates only for robust lobe localization;
    3. finds broad upper crests, never valleys;
    4. uses the largest upper crest as the forced-resonance anchor;
    5. estimates the crest-to-crest period from the strong crests;
    6. tracks the next natural crests at anchor + k*T.

    The returned table is still a set of clickable markers over the complete
    waveform. Detection is performed before any multi-file overlay is drawn.
    """
    columns = [
        "tipo",
        "tempo_us",
        "amplitude",
        "prominence",
        "abs_amplitude",
        "envelope_amplitude",
        "dominance_score",
        "raw_index",
        "peak_id",
        "detector_role",
        "estimated_period_us",
    ]

    y, _baseline = subtract_baseline(item["time_s"], item["value"], mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(item["time_s"], y, start_us, end_us)
    if len(y_win) < 8:
        return pd.DataFrame(columns=columns), 0

    t_us = t_win * 1e6
    y_win = y_win.astype(float)
    finite = np.isfinite(t_us) & np.isfinite(y_win)
    if not np.any(finite):
        return pd.DataFrame(columns=columns), 0

    dt_s = float(np.median(np.diff(t_win))) if len(t_win) > 1 else 0.0
    if not np.isfinite(dt_s) or dt_s <= 0:
        return pd.DataFrame(columns=columns), 0
    dt_us = dt_s * 1e6

    min_distance_samples = max(1, int(round(float(min_distance_us) / dt_us)))

    # Smooth over a visually small window and decimate before detecting peaks.
    # This removes the many nanosecond-scale extrema caused by ISF sampling and
    # keeps the detector focused on the visible resonance lobes.
    smooth_window_samples = max(11, int(round(2.0 / dt_us)))
    smooth_window_samples = min(smooth_window_samples, 5001)
    if smooth_window_samples % 2 == 0:
        smooth_window_samples += 1
    y_detect = _moving_average_np(y_win, smooth_window_samples)

    decimation_step = max(1, int(round(0.5 / dt_us)))
    y_dec = y_detect[::decimation_step]
    if y_dec.size < 3:
        return pd.DataFrame(columns=columns), 0

    max_dec = np.flatnonzero((y_dec[1:-1] > y_dec[:-2]) & (y_dec[1:-1] >= y_dec[2:])) + 1
    min_dec = np.flatnonzero((y_dec[1:-1] < y_dec[:-2]) & (y_dec[1:-1] <= y_dec[2:])) + 1
    if max_dec.size == 0:
        return pd.DataFrame(columns=columns), 0

    rough_max = np.clip(max_dec * decimation_step, 0, len(y_detect) - 1)
    rough_min = np.clip(min_dec * decimation_step, 0, len(y_detect) - 1)

    refine_radius = max(2, int(round(2.0 / dt_us)))
    max_idx = _refine_indices_to_raw_extrema(y_detect, rough_max, refine_radius, kind="max")
    min_idx = _refine_indices_to_raw_extrema(y_detect, rough_min, refine_radius, kind="min")
    if max_idx.size == 0:
        return pd.DataFrame(columns=columns), int(max_dec.size)

    def _smooth_prominence(indices: np.ndarray) -> np.ndarray:
        indices = np.asarray(indices, dtype=int)
        valleys = np.sort(np.asarray(min_idx, dtype=int))
        if indices.size == 0:
            return np.array([], dtype=float)
        if valleys.size == 0:
            return np.abs(y_detect[indices].astype(float))
        out: list[float] = []
        for idx in indices:
            pos = int(np.searchsorted(valleys, int(idx)))
            references: list[float] = []
            if pos > 0:
                references.append(float(y_detect[valleys[pos - 1]]))
            if pos < valleys.size:
                references.append(float(y_detect[valleys[pos]]))
            if references:
                out.append(max(0.0, float(y_detect[idx]) - max(references)))
            else:
                out.append(abs(float(y_detect[idx])))
        return np.array(out, dtype=float)

    prominence = _smooth_prominence(max_idx)

    # Noise floor from the quiet/pre-trigger portion. With these Tektronix ISF
    # records the true oscillation lobes are tens/hundreds of volts, while the
    # flat baseline has only a few volts of quantization noise.
    quiet = y_detect[t_us < 0]
    if quiet.size < 20:
        quiet = y_detect[: max(20, len(y_detect) // 10)]
    quiet = quiet[np.isfinite(quiet)]
    if quiet.size:
        mad = float(np.median(np.abs(quiet - np.median(quiet))))
        noise = 1.4826 * mad
    else:
        noise = 0.0
    if not np.isfinite(noise):
        noise = 0.0

    y_range = float(np.nanmax(y_detect) - np.nanmin(y_detect))
    scale = max(y_range, float(np.nanmax(np.abs(y_detect))), 1e-12)
    # Interpret the UI threshold gently for the ringdown tracker. The user may
    # set 5%, but late natural crests can be far below 5% of the largest forced
    # lobe and are still physically meaningful.
    floor = max(
        6.0 * noise,
        float(threshold_fraction) * scale * 0.08,
        8.0,
    )

    keep = (t_us[max_idx] >= 0.0) & np.isfinite(prominence) & (prominence >= floor)
    crest_idx = max_idx[keep]
    crest_prom = prominence[keep]
    if crest_idx.size == 0:
        # One controlled relaxation: enough to find weak late crests, not enough
        # to reintroduce baseline markers.
        relaxed_floor = max(5.0 * noise, float(threshold_fraction) * scale * 0.03, 5.0)
        keep = (t_us[max_idx] >= 0.0) & np.isfinite(prominence) & (prominence >= relaxed_floor)
        crest_idx = max_idx[keep]
        crest_prom = prominence[keep]
        floor = relaxed_floor

    if crest_idx.size == 0:
        return pd.DataFrame(columns=columns), int(max_dec.size)

    # Enforce separation between visible crests, keeping the crest with higher
    # smooth prominence. This still leaves one marker per lobe/cycle.
    score = crest_prom + 0.05 * np.maximum(y_detect[crest_idx], 0.0)
    order = np.argsort(score)[::-1]
    separated: list[int] = []
    for pos in order:
        idx = int(crest_idx[pos])
        if all(abs(idx - selected) >= min_distance_samples for selected in separated):
            separated.append(idx)
    crest_idx = np.array(sorted(separated), dtype=int)
    crest_prom = _smooth_prominence(crest_idx)

    if crest_idx.size == 0:
        return pd.DataFrame(columns=columns), int(max_dec.size)

    # Forced-resonance anchor: highest upper crest of this individual waveform.
    anchor_pos = int(np.argmax(y_detect[crest_idx]))
    anchor_idx = int(crest_idx[anchor_pos])
    anchor_time_us = float(t_us[anchor_idx])
    anchor_amp = float(y_detect[anchor_idx])

    # Estimate period from strong crests up to the anchor. This prevents the
    # tracker from jumping to valley positions or tail ripple after the anchor.
    pre_mask = t_us[crest_idx] <= anchor_time_us + 1e-9
    pre_idx = crest_idx[pre_mask]
    pre_prom = _smooth_prominence(pre_idx)
    if pre_idx.size:
        max_pre_prom = float(np.nanmax(pre_prom)) if pre_prom.size else 0.0
        strong_mask = (y_detect[pre_idx] >= 0.25 * anchor_amp) | (pre_prom >= 0.25 * max_pre_prom)
        strong_times = np.sort(t_us[pre_idx][strong_mask])
    else:
        strong_times = np.array([], dtype=float)

    diffs = np.diff(strong_times)
    diffs = diffs[np.isfinite(diffs) & (diffs > max(2.0 * float(min_distance_us), 15.0)) & (diffs < 160.0)]
    if diffs.size == 0:
        all_times = np.sort(t_us[crest_idx])
        diffs = np.diff(all_times)
        diffs = diffs[np.isfinite(diffs) & (diffs > max(2.0 * float(min_distance_us), 15.0)) & (diffs < 160.0)]
    estimated_period_us = float(np.nanmedian(diffs)) if diffs.size else float("nan")

    tracked_idx: list[int] = []
    if np.isfinite(estimated_period_us) and estimated_period_us > 0:
        # Track more than the current N so manual adjustment and "Últimos N" can
        # still use late candidates when they exist.
        max_to_track = max(8, int(max_candidates))
        search_half_width = 0.42 * estimated_period_us
        local_floor = max(5.0 * noise, float(threshold_fraction) * scale * 0.03, 5.0)
        for k in range(1, max_to_track + 1):
            expected_time = anchor_time_us + k * estimated_period_us
            if expected_time > float(end_us):
                break
            window = (t_us >= expected_time - search_half_width) & (t_us <= expected_time + search_half_width)
            if not np.any(window):
                continue
            window_indices = np.flatnonzero(window)
            # Prefer already-detected maxima inside the expected cycle window.
            local_maxima = [int(idx) for idx in max_idx if window_indices[0] <= int(idx) <= window_indices[-1]]
            if local_maxima:
                local_maxima_arr = np.asarray(local_maxima, dtype=int)
                local_scores = y_detect[local_maxima_arr]
                chosen_idx = int(local_maxima_arr[int(np.nanargmax(local_scores))])
            else:
                chosen_idx = int(window_indices[int(np.nanargmax(y_detect[window_indices]))])
                chosen_idx = int(_refine_indices_to_raw_extrema(
                    y_detect,
                    np.array([chosen_idx], dtype=int),
                    refine_radius,
                    kind="max",
                )[0])

            # Require it to be clearly after the anchor and to have local lobe
            # amplitude above the noise floor. The local amplitude is measured
            # from the lowest point in approximately one crest-to-crest period.
            if t_us[chosen_idx] <= anchor_time_us + 0.25 * estimated_period_us:
                continue
            local_window = (
                (t_us >= t_us[chosen_idx] - 0.50 * estimated_period_us)
                & (t_us <= t_us[chosen_idx] + 0.50 * estimated_period_us)
            )
            local_prom = float(y_detect[chosen_idx] - np.nanmin(y_detect[local_window])) if np.any(local_window) else 0.0
            if not np.isfinite(local_prom) or local_prom < local_floor:
                continue
            if any(abs(t_us[chosen_idx] - t_us[existing]) < 0.45 * estimated_period_us for existing in tracked_idx):
                continue
            tracked_idx.append(chosen_idx)

    # Merge broad detected crests and tracked crests. Reject extrema too close
    # to the right edge of the user window: those are often just the signal
    # returning to baseline at the boundary rather than a complete crest.
    merged = sorted(set(int(idx) for idx in crest_idx.tolist() + tracked_idx))
    if np.isfinite(estimated_period_us) and estimated_period_us > 0:
        boundary_guard_us = max(1.0, min(5.0, 0.05 * estimated_period_us))
    else:
        boundary_guard_us = 1.0
    merged = [idx for idx in merged if t_us[int(idx)] <= float(end_us) - boundary_guard_us]

    if len(merged) > int(max_candidates):
        mandatory = set(int(idx) for idx in tracked_idx + [anchor_idx])
        remaining = [idx for idx in merged if idx not in mandatory]
        remaining_scores = _smooth_prominence(np.asarray(remaining, dtype=int)) if remaining else np.array([], dtype=float)
        ranked_remaining = [idx for _, idx in sorted(zip(remaining_scores, remaining), reverse=True)]
        keep_list = list(mandatory) + ranked_remaining[: max(0, int(max_candidates) - len(mandatory))]
        merged = sorted(set(keep_list))

    rows = []
    for idx in merged:
        idx = int(idx)
        local_window = (
            (t_us >= t_us[idx] - 0.50 * estimated_period_us)
            & (t_us <= t_us[idx] + 0.50 * estimated_period_us)
            if np.isfinite(estimated_period_us) and estimated_period_us > 0
            else np.ones_like(t_us, dtype=bool)
        )
        local_prom = float(y_detect[idx] - np.nanmin(y_detect[local_window])) if np.any(local_window) else float(abs(y_detect[idx]))
        local_prom = max(local_prom, 0.0)
        role = "forçado/âncora" if idx == anchor_idx else ("natural rastreado" if idx in tracked_idx else "crista candidata")
        amp = float(y_win[idx])
        rows.append(
            {
                "tipo": "positivo",
                "tempo_us": float(t_us[idx]),
                "amplitude": amp,
                "prominence": float(local_prom),
                "abs_amplitude": abs(amp),
                # Half prominence approximates the sinusoidal envelope amplitude
                # (peak-to-trough is roughly 2A). It remains meaningful even
                # when the upper crest falls below the zero axis.
                "envelope_amplitude": max(float(local_prom) * 0.5, abs(amp), 1e-12),
                "dominance_score": max(abs(amp), float(local_prom)),
                "raw_index": idx,
                "detector_role": role,
                "estimated_period_us": estimated_period_us,
            }
        )

    df = pd.DataFrame(rows).sort_values("tempo_us").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=columns), int(max_dec.size)
    df["peak_id"] = np.arange(len(df), dtype=int)
    df = df[[col for col in columns if col in df.columns]]
    return df, int(max_dec.size)


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
    cache = st.session_state.setdefault("_envelope_peak_cache_v0324", {})
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
