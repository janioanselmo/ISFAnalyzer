"""Waveform analysis routines for Tektronix ISF files.

The module is intentionally dependency-light: NumPy + pandas only.
It includes basic pulse metrics, ringdown/resonance metrics, before/after
comparison metrics, and voltage/current power metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class PulseWindow:
    """Detected pulse window."""

    start_s: float
    end_s: float
    start_index: int
    end_index: int


@dataclass
class PeakSet:
    """Local extrema found in a ringdown window."""

    positive_indices: np.ndarray
    negative_indices: np.ndarray
    all_extrema_indices: np.ndarray


def finite_or_nan(value: float) -> float:
    """Return value as float, or NaN when it cannot be represented."""
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return float("nan")
    if not np.isfinite(out):
        return float("nan")
    return out


def safe_percent_change(before: float, after: float) -> float:
    """Percent change from before to after."""
    before = finite_or_nan(before)
    after = finite_or_nan(after)
    if not np.isfinite(before) or not np.isfinite(after) or abs(before) < 1e-30:
        return float("nan")
    return float(100.0 * (after - before) / before)


def decimate_for_plot(
    time_s: np.ndarray,
    value: np.ndarray,
    max_points: int = 30_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Downsample data for fast plotting."""
    if len(time_s) <= max_points:
        return time_s, value

    step = int(np.ceil(len(time_s) / max_points))
    return time_s[::step], value[::step]


def trapezoid_integral(y: np.ndarray, x: np.ndarray) -> float:
    """Integrate using the trapezoidal rule, NumPy-version safe."""
    if len(y) < 2 or len(x) < 2:
        return float("nan")
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def estimate_baseline(
    time_s: np.ndarray,
    value: np.ndarray,
    mode: str = "t<0",
    first_fraction: float = 0.10,
) -> float:
    """Estimate baseline/DC offset."""
    if mode == "t<0":
        mask = time_s < 0
        if np.any(mask):
            return float(np.median(value[mask]))

    n = max(10, int(len(value) * first_fraction))
    return float(np.median(value[:n]))


def subtract_baseline(
    time_s: np.ndarray,
    value: np.ndarray,
    mode: str = "t<0",
) -> tuple[np.ndarray, float]:
    """Return baseline-corrected waveform and the estimated baseline."""
    baseline = estimate_baseline(time_s, value, mode=mode)
    return value.astype(float) - baseline, baseline


def auto_pulse_window(
    time_s: np.ndarray,
    value: np.ndarray,
    baseline: float,
    threshold_fraction: float = 0.10,
) -> Optional[PulseWindow]:
    """Detect the active pulse/ringing window by a relative threshold."""
    y = value - baseline
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak <= 0:
        return None

    threshold = threshold_fraction * peak
    above = np.flatnonzero(np.abs(y) >= threshold)
    if above.size == 0:
        return None

    start_i = int(above[0])
    end_i = int(above[-1])
    return PulseWindow(
        start_s=float(time_s[start_i]),
        end_s=float(time_s[end_i]),
        start_index=start_i,
        end_index=end_i,
    )


def slice_window_us(
    time_s: np.ndarray,
    value: np.ndarray,
    start_us: float | None,
    end_us: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Slice a waveform using microsecond limits."""
    mask = np.ones_like(time_s, dtype=bool)
    if start_us is not None:
        mask &= time_s >= start_us * 1e-6
    if end_us is not None:
        mask &= time_s <= end_us * 1e-6
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return time_s[:0], value[:0], indices
    return time_s[indices], value[indices], indices


def fft_dominant_frequency(
    time_s: np.ndarray,
    value: np.ndarray,
    f_min_hz: float = 1.0,
    f_max_hz: float | None = None,
) -> tuple[float, float]:
    """Dominant frequency from FFT."""
    if len(value) < 8:
        return float("nan"), float("nan")

    dt = float(np.median(np.diff(time_s)))
    if dt <= 0:
        return float("nan"), float("nan")

    y = value.astype(float) - np.mean(value)
    if np.max(np.abs(y)) <= 0:
        return float("nan"), float("nan")

    window = np.hanning(len(y))
    spectrum = np.fft.rfft(y * window)
    freqs = np.fft.rfftfreq(len(y), d=dt)
    mag = np.abs(spectrum)

    mask = freqs >= f_min_hz
    if f_max_hz is not None and np.isfinite(f_max_hz):
        mask &= freqs <= f_max_hz
    if not np.any(mask):
        return float("nan"), float("nan")

    idx_candidates = np.flatnonzero(mask)
    idx = int(idx_candidates[int(np.argmax(mag[mask]))])
    return float(freqs[idx]), float(mag[idx])


def spectral_metrics(
    time_s: np.ndarray,
    value: np.ndarray,
    f_min_hz: float = 1.0,
    f_max_hz: float | None = None,
) -> dict:
    """Return dominant frequency, centroid, and bandwidth."""
    if len(value) < 8:
        return {
            "freq_fft_hz": float("nan"),
            "freq_fft_khz": float("nan"),
            "spectral_centroid_hz": float("nan"),
            "spectral_bandwidth_hz": float("nan"),
        }

    dt = float(np.median(np.diff(time_s)))
    if dt <= 0:
        return {
            "freq_fft_hz": float("nan"),
            "freq_fft_khz": float("nan"),
            "spectral_centroid_hz": float("nan"),
            "spectral_bandwidth_hz": float("nan"),
        }

    y = value.astype(float) - np.mean(value)
    window = np.hanning(len(y))
    spec = np.fft.rfft(y * window)
    freqs = np.fft.rfftfreq(len(y), d=dt)
    mag = np.abs(spec)
    mask = freqs >= f_min_hz
    if f_max_hz is not None and np.isfinite(f_max_hz):
        mask &= freqs <= f_max_hz

    if not np.any(mask) or np.sum(mag[mask]) <= 0:
        return {
            "freq_fft_hz": float("nan"),
            "freq_fft_khz": float("nan"),
            "spectral_centroid_hz": float("nan"),
            "spectral_bandwidth_hz": float("nan"),
        }

    freqs_m = freqs[mask]
    mag_m = mag[mask]
    dom_idx = int(np.argmax(mag_m))
    centroid = float(np.sum(freqs_m * mag_m) / np.sum(mag_m))
    bandwidth = float(np.sqrt(np.sum(((freqs_m - centroid) ** 2) * mag_m) / np.sum(mag_m)))
    return {
        "freq_fft_hz": float(freqs_m[dom_idx]),
        "freq_fft_khz": float(freqs_m[dom_idx] / 1e3),
        "spectral_centroid_hz": centroid,
        "spectral_bandwidth_hz": bandwidth,
    }


def zero_crossings(time_s: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Linear-interpolated zero-crossing times."""
    if len(value) < 2:
        return np.array([], dtype=float)

    y = value.astype(float) - np.mean(value)
    sign_change = np.flatnonzero(np.diff(np.signbit(y)))
    if sign_change.size == 0:
        return np.array([], dtype=float)

    crossing_times = []
    for idx in sign_change:
        y0 = y[idx]
        y1 = y[idx + 1]
        t0 = time_s[idx]
        t1 = time_s[idx + 1]
        if y1 == y0:
            crossing_times.append(t0)
        else:
            frac = -y0 / (y1 - y0)
            crossing_times.append(t0 + frac * (t1 - t0))
    return np.array(crossing_times, dtype=float)


def zero_crossing_frequency(time_s: np.ndarray, value: np.ndarray) -> float:
    """Frequency estimate using zero crossings."""
    zc = zero_crossings(time_s, value)
    if len(zc) < 3:
        return float("nan")

    half_periods = np.diff(zc)
    half_periods = half_periods[half_periods > 0]
    if len(half_periods) == 0:
        return float("nan")

    period = 2.0 * float(np.median(half_periods))
    if period <= 0:
        return float("nan")
    return float(1.0 / period)


def _thin_peaks_by_distance(
    candidate_indices: np.ndarray,
    score: np.ndarray,
    min_distance_samples: int,
) -> np.ndarray:
    """Keep stronger extrema while enforcing a minimum distance."""
    if candidate_indices.size == 0:
        return candidate_indices
    if min_distance_samples <= 1:
        return np.sort(candidate_indices)

    order = candidate_indices[np.argsort(score[candidate_indices])[::-1]]
    kept: list[int] = []
    for idx in order:
        if all(abs(int(idx) - int(existing)) >= min_distance_samples for existing in kept):
            kept.append(int(idx))
    return np.array(sorted(kept), dtype=int)


def find_ringdown_peaks(
    time_s: np.ndarray,
    value: np.ndarray,
    threshold_fraction: float = 0.05,
    min_peak_distance_us: float = 0.5,
) -> PeakSet:
    """Find positive and negative peaks in a ringdown waveform."""
    if len(value) < 3:
        empty = np.array([], dtype=int)
        return PeakSet(empty, empty, empty)

    y = value.astype(float)
    dt = float(np.median(np.diff(time_s))) if len(time_s) > 1 else 0.0
    min_distance_samples = 1
    if dt > 0:
        min_distance_samples = max(1, int(round(min_peak_distance_us * 1e-6 / dt)))

    abs_peak = float(np.max(np.abs(y)))
    if abs_peak <= 0:
        empty = np.array([], dtype=int)
        return PeakSet(empty, empty, empty)

    threshold = threshold_fraction * abs_peak
    pos = np.flatnonzero((y[1:-1] > y[:-2]) & (y[1:-1] >= y[2:])) + 1
    neg = np.flatnonzero((y[1:-1] < y[:-2]) & (y[1:-1] <= y[2:])) + 1
    pos = pos[y[pos] >= threshold]
    neg = neg[y[neg] <= -threshold]

    pos = _thin_peaks_by_distance(pos, np.abs(y), min_distance_samples)
    neg = _thin_peaks_by_distance(neg, np.abs(y), min_distance_samples)
    all_extrema = np.array(sorted(np.concatenate([pos, neg])), dtype=int)
    return PeakSet(pos, neg, all_extrema)


def _period_from_same_polarity_peaks(time_s: np.ndarray, peaks: np.ndarray) -> float:
    if len(peaks) < 2:
        return float("nan")
    periods = np.diff(time_s[peaks])
    periods = periods[periods > 0]
    if len(periods) == 0:
        return float("nan")
    return float(np.median(periods))


def _period_from_extrema(time_s: np.ndarray, extrema: np.ndarray) -> float:
    if len(extrema) < 3:
        return float("nan")
    half_periods = np.diff(time_s[extrema])
    half_periods = half_periods[half_periods > 0]
    if len(half_periods) == 0:
        return float("nan")
    return float(2.0 * np.median(half_periods))


def _log_decrement_from_peaks(value: np.ndarray, peaks: np.ndarray) -> float:
    if len(peaks) < 2:
        return float("nan")
    amplitudes = np.abs(value[peaks].astype(float))
    amplitudes = amplitudes[amplitudes > 0]
    if len(amplitudes) < 2:
        return float("nan")
    ratios = amplitudes[:-1] / amplitudes[1:]
    ratios = ratios[np.isfinite(ratios) & (ratios > 1.0)]
    if len(ratios) == 0:
        return float("nan")
    return float(np.median(np.log(ratios)))


def _envelope_fit_tau(time_s: np.ndarray, value: np.ndarray, extrema: np.ndarray) -> tuple[float, float, float]:
    """Fit ln(|peak|) = a + b*t; tau = -1/b."""
    if len(extrema) < 3:
        return float("nan"), float("nan"), float("nan")

    t = time_s[extrema].astype(float)
    amp = np.abs(value[extrema].astype(float))
    valid = np.isfinite(t) & np.isfinite(amp) & (amp > 0)
    t = t[valid]
    amp = amp[valid]
    if len(t) < 3 or np.ptp(t) <= 0:
        return float("nan"), float("nan"), float("nan")

    log_amp = np.log(amp)
    slope, intercept = np.polyfit(t, log_amp, deg=1)
    if slope >= 0:
        return float("nan"), float(intercept), float("nan")

    pred = slope * t + intercept
    ss_res = float(np.sum((log_amp - pred) ** 2))
    ss_tot = float(np.sum((log_amp - np.mean(log_amp)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    tau = float(-1.0 / slope)
    return tau, float(intercept), r2


def damping_from_log_decrement(delta: float, damped_frequency_hz: float) -> dict:
    """Convert logarithmic decrement to damping ratio, Q and natural frequency."""
    delta = finite_or_nan(delta)
    damped_frequency_hz = finite_or_nan(damped_frequency_hz)
    if not np.isfinite(delta) or delta <= 0:
        return {
            "log_decrement": float("nan"),
            "damping_ratio_zeta": float("nan"),
            "quality_factor_q": float("nan"),
            "omega_d_rad_s": float("nan"),
            "omega_n_rad_s": float("nan"),
            "freq_natural_hz": float("nan"),
        }

    zeta = float(delta / np.sqrt((2.0 * np.pi) ** 2 + delta ** 2))
    q = float(1.0 / (2.0 * zeta)) if zeta > 0 else float("nan")
    omega_d = float(2.0 * np.pi * damped_frequency_hz) if np.isfinite(damped_frequency_hz) else float("nan")
    if np.isfinite(omega_d) and zeta < 1.0:
        omega_n = float(omega_d / np.sqrt(1.0 - zeta ** 2))
        f_n = float(omega_n / (2.0 * np.pi))
    else:
        omega_n = float("nan")
        f_n = float("nan")

    return {
        "log_decrement": delta,
        "damping_ratio_zeta": zeta,
        "quality_factor_q": q,
        "omega_d_rad_s": omega_d,
        "omega_n_rad_s": omega_n,
        "freq_natural_hz": f_n,
    }


def integrate_energy_resistive(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    resistance_ohm: float,
) -> float:
    """Approximate energy in a resistive load: integral(v²/R dt)."""
    if resistance_ohm <= 0 or len(voltage_v) < 2:
        return float("nan")
    power_w = (voltage_v.astype(float) ** 2) / resistance_ohm
    return trapezoid_integral(power_w, time_s)


def electric_field_metrics(
    peak_abs_v: float,
    gap_mm: float,
) -> tuple[float, float]:
    """Electric field in V/m and kV/cm for a peak voltage."""
    if gap_mm <= 0:
        return float("nan"), float("nan")

    distance_m = gap_mm * 1e-3
    e_v_m = peak_abs_v / distance_m
    e_kv_cm = e_v_m / 100_000.0
    return float(e_v_m), float(e_kv_cm)


def waveform_metrics(
    name: str,
    time_s: np.ndarray,
    value: np.ndarray,
    gap_mm: float = 15.0,
    resistance_ohm: float = 50.0,
    threshold_fraction: float = 0.10,
    baseline_mode: str = "t<0",
) -> dict:
    """Calculate basic pulse metrics."""
    baseline = estimate_baseline(time_s, value, mode=baseline_mode)
    y = value.astype(float) - baseline

    pulse = auto_pulse_window(time_s, value, baseline, threshold_fraction)

    if pulse is not None:
        t_win = time_s[pulse.start_index:pulse.end_index + 1]
        y_win = y[pulse.start_index:pulse.end_index + 1]
        pulse_width_s = pulse.end_s - pulse.start_s
    else:
        t_win = time_s
        y_win = y
        pulse_width_s = float("nan")

    spec = spectral_metrics(t_win, y_win)
    f_zc = zero_crossing_frequency(t_win, y_win)

    v_max = float(np.max(value)) if len(value) else float("nan")
    v_min = float(np.min(value)) if len(value) else float("nan")
    v_pp = float(v_max - v_min) if np.isfinite(v_max) and np.isfinite(v_min) else float("nan")
    peak_abs = float(np.max(np.abs(y))) if len(y) else float("nan")
    rms = float(np.sqrt(np.mean(y ** 2))) if len(y) else float("nan")
    abs_area_vs = trapezoid_integral(np.abs(y_win), t_win) if len(y_win) > 1 else float("nan")
    signed_area_vs = trapezoid_integral(y_win, t_win) if len(y_win) > 1 else float("nan")
    energy_j = integrate_energy_resistive(t_win, y_win, resistance_ohm)
    e_v_m, e_kv_cm = electric_field_metrics(peak_abs, gap_mm)

    return {
        "arquivo": name,
        "pontos": int(len(value)),
        "t_inicial_us": float(time_s[0] * 1e6) if len(time_s) else float("nan"),
        "t_final_us": float(time_s[-1] * 1e6) if len(time_s) else float("nan"),
        "dt_ns": float(np.median(np.diff(time_s)) * 1e9) if len(time_s) > 1 else float("nan"),
        "baseline": baseline,
        "v_max": v_max,
        "v_min": v_min,
        "v_pp": v_pp,
        "pico_abs_corrigido": peak_abs,
        "rms_corrigido": rms,
        "pulso_inicio_us": float(pulse.start_s * 1e6) if pulse else float("nan"),
        "pulso_fim_us": float(pulse.end_s * 1e6) if pulse else float("nan"),
        "largura_pulso_us": float(pulse_width_s * 1e6),
        "freq_fft_hz": spec["freq_fft_hz"],
        "freq_fft_khz": spec["freq_fft_khz"],
        "freq_zero_cross_hz": f_zc,
        "freq_zero_cross_khz": f_zc / 1e3 if np.isfinite(f_zc) else float("nan"),
        "spectral_centroid_hz": spec["spectral_centroid_hz"],
        "spectral_bandwidth_hz": spec["spectral_bandwidth_hz"],
        "area_abs_v_s": abs_area_vs,
        "area_assinada_v_s": signed_area_vs,
        "energia_resistiva_j": energy_j,
        "campo_v_m": e_v_m,
        "campo_kv_cm": e_kv_cm,
    }


def ringdown_metrics(
    name: str,
    time_s: np.ndarray,
    value: np.ndarray,
    start_us: float,
    end_us: float,
    baseline_mode: str = "t<0",
    resistance_ohm: float = 50.0,
    peak_threshold_fraction: float = 0.05,
    min_peak_distance_us: float = 0.5,
) -> dict:
    """Calculate resonance/ringdown metrics in a selected time window."""
    y, baseline = subtract_baseline(time_s, value, mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(time_s, y, start_us, end_us)

    if len(y_win) < 8:
        return {
            "arquivo": name,
            "ring_start_us": start_us,
            "ring_end_us": end_us,
            "ring_duration_us": float("nan"),
            "baseline": baseline,
            "n_positive_peaks": 0,
            "n_negative_peaks": 0,
            "n_extrema": 0,
            "ring_v_max": float("nan"),
            "ring_v_min": float("nan"),
            "ring_v_pp": float("nan"),
            "ring_peak_abs": float("nan"),
            "ring_rms": float("nan"),
            "ring_energy_resistive_j": float("nan"),
            "period_peaks_us": float("nan"),
            "period_extrema_us": float("nan"),
            "period_zero_cross_us": float("nan"),
            "freq_damped_hz": float("nan"),
            "freq_damped_khz": float("nan"),
            "freq_fft_ring_hz": float("nan"),
            "freq_fft_ring_khz": float("nan"),
            "spectral_centroid_hz": float("nan"),
            "spectral_bandwidth_hz": float("nan"),
            "tau_envelope_us": float("nan"),
            "envelope_r2": float("nan"),
            "log_decrement": float("nan"),
            "damping_ratio_zeta": float("nan"),
            "quality_factor_q": float("nan"),
            "omega_d_rad_s": float("nan"),
            "omega_n_rad_s": float("nan"),
            "freq_natural_hz": float("nan"),
            "freq_natural_khz": float("nan"),
            "decay_per_cycle_percent": float("nan"),
            "t_to_10_percent_us": float("nan"),
            "settling_5_percent_us": float("nan"),
            "dc_offset_window": float("nan"),
            "asymmetry_pos_neg": float("nan"),
        }

    peaks = find_ringdown_peaks(
        t_win,
        y_win,
        threshold_fraction=peak_threshold_fraction,
        min_peak_distance_us=min_peak_distance_us,
    )

    period_pos = _period_from_same_polarity_peaks(t_win, peaks.positive_indices)
    period_neg = _period_from_same_polarity_peaks(t_win, peaks.negative_indices)
    period_candidates = [x for x in [period_pos, period_neg] if np.isfinite(x) and x > 0]
    period_peaks_s = float(np.median(period_candidates)) if period_candidates else float("nan")

    period_extrema_s = _period_from_extrema(t_win, peaks.all_extrema_indices)
    f_zc = zero_crossing_frequency(t_win, y_win)
    period_zc_s = 1.0 / f_zc if np.isfinite(f_zc) and f_zc > 0 else float("nan")

    period_preference = [p for p in [period_peaks_s, period_extrema_s, period_zc_s] if np.isfinite(p) and p > 0]
    period_s = float(np.median(period_preference)) if period_preference else float("nan")
    f_damped_hz = 1.0 / period_s if np.isfinite(period_s) and period_s > 0 else float("nan")

    delta_pos = _log_decrement_from_peaks(y_win, peaks.positive_indices)
    delta_neg = _log_decrement_from_peaks(y_win, peaks.negative_indices)
    delta_candidates = [d for d in [delta_pos, delta_neg] if np.isfinite(d) and d > 0]
    log_delta = float(np.median(delta_candidates)) if delta_candidates else float("nan")
    damping = damping_from_log_decrement(log_delta, f_damped_hz)

    tau_s, _intercept, envelope_r2 = _envelope_fit_tau(t_win, y_win, peaks.all_extrema_indices)
    if not np.isfinite(tau_s) and np.isfinite(damping.get("omega_n_rad_s", np.nan)) and np.isfinite(damping.get("damping_ratio_zeta", np.nan)):
        denom = damping["omega_n_rad_s"] * damping["damping_ratio_zeta"]
        tau_s = float(1.0 / denom) if denom > 0 else float("nan")

    spec = spectral_metrics(t_win, y_win)
    ring_energy = integrate_energy_resistive(t_win, y_win, resistance_ohm)
    v_max = float(np.max(y_win))
    v_min = float(np.min(y_win))
    peak_abs = float(np.max(np.abs(y_win)))
    rms = float(np.sqrt(np.mean(y_win ** 2)))
    pos_peak_amp = float(np.max(y_win[peaks.positive_indices])) if len(peaks.positive_indices) else float("nan")
    neg_peak_amp = float(abs(np.min(y_win[peaks.negative_indices]))) if len(peaks.negative_indices) else float("nan")
    if np.isfinite(pos_peak_amp) and np.isfinite(neg_peak_amp) and neg_peak_amp > 0:
        asymmetry = float(pos_peak_amp / neg_peak_amp)
    else:
        asymmetry = float("nan")

    if np.isfinite(log_delta):
        decay_per_cycle = float(100.0 * (1.0 - np.exp(-log_delta)))
    else:
        decay_per_cycle = float("nan")

    t_to_10 = float(tau_s * np.log(10.0) * 1e6) if np.isfinite(tau_s) else float("nan")
    settling_5 = float(tau_s * np.log(20.0) * 1e6) if np.isfinite(tau_s) else float("nan")

    return {
        "arquivo": name,
        "ring_start_us": start_us,
        "ring_end_us": end_us,
        "ring_duration_us": float((t_win[-1] - t_win[0]) * 1e6),
        "baseline": baseline,
        "n_positive_peaks": int(len(peaks.positive_indices)),
        "n_negative_peaks": int(len(peaks.negative_indices)),
        "n_extrema": int(len(peaks.all_extrema_indices)),
        "ring_v_max": v_max,
        "ring_v_min": v_min,
        "ring_v_pp": float(v_max - v_min),
        "ring_peak_abs": peak_abs,
        "ring_rms": rms,
        "ring_energy_resistive_j": ring_energy,
        "period_peaks_us": float(period_peaks_s * 1e6) if np.isfinite(period_peaks_s) else float("nan"),
        "period_extrema_us": float(period_extrema_s * 1e6) if np.isfinite(period_extrema_s) else float("nan"),
        "period_zero_cross_us": float(period_zc_s * 1e6) if np.isfinite(period_zc_s) else float("nan"),
        "freq_damped_hz": f_damped_hz,
        "freq_damped_khz": float(f_damped_hz / 1e3) if np.isfinite(f_damped_hz) else float("nan"),
        "freq_fft_ring_hz": spec["freq_fft_hz"],
        "freq_fft_ring_khz": spec["freq_fft_khz"],
        "spectral_centroid_hz": spec["spectral_centroid_hz"],
        "spectral_bandwidth_hz": spec["spectral_bandwidth_hz"],
        "tau_envelope_us": float(tau_s * 1e6) if np.isfinite(tau_s) else float("nan"),
        "envelope_r2": envelope_r2,
        "log_decrement": damping["log_decrement"],
        "damping_ratio_zeta": damping["damping_ratio_zeta"],
        "quality_factor_q": damping["quality_factor_q"],
        "omega_d_rad_s": damping["omega_d_rad_s"],
        "omega_n_rad_s": damping["omega_n_rad_s"],
        "freq_natural_hz": damping["freq_natural_hz"],
        "freq_natural_khz": float(damping["freq_natural_hz"] / 1e3) if np.isfinite(damping["freq_natural_hz"]) else float("nan"),
        "decay_per_cycle_percent": decay_per_cycle,
        "t_to_10_percent_us": t_to_10,
        "settling_5_percent_us": settling_5,
        "dc_offset_window": float(np.mean(y_win)),
        "asymmetry_pos_neg": asymmetry,
    }


def ringdown_peak_table(
    time_s: np.ndarray,
    value: np.ndarray,
    start_us: float,
    end_us: float,
    baseline_mode: str = "t<0",
    peak_threshold_fraction: float = 0.05,
    min_peak_distance_us: float = 0.5,
) -> pd.DataFrame:
    """Return a table with ringdown extrema."""
    y, _baseline = subtract_baseline(time_s, value, mode=baseline_mode)
    t_win, y_win, _indices = slice_window_us(time_s, y, start_us, end_us)
    peaks = find_ringdown_peaks(
        t_win,
        y_win,
        threshold_fraction=peak_threshold_fraction,
        min_peak_distance_us=min_peak_distance_us,
    )
    rows = []
    for idx in peaks.positive_indices:
        rows.append({"tipo": "positivo", "tempo_us": t_win[idx] * 1e6, "amplitude": y_win[idx]})
    for idx in peaks.negative_indices:
        rows.append({"tipo": "negativo", "tempo_us": t_win[idx] * 1e6, "amplitude": y_win[idx]})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("tempo_us").reset_index(drop=True)
        df["abs_amplitude"] = np.abs(df["amplitude"])
    return df


def common_grid_for_comparison(
    t_a: np.ndarray,
    y_a: np.ndarray,
    t_b: np.ndarray,
    y_b: np.ndarray,
    start_us: float | None = None,
    end_us: float | None = None,
    max_points: int = 50_000,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate two waveforms onto a common time grid."""
    start_s = max(float(t_a[0]), float(t_b[0]))
    end_s = min(float(t_a[-1]), float(t_b[-1]))
    if start_us is not None:
        start_s = max(start_s, start_us * 1e-6)
    if end_us is not None:
        end_s = min(end_s, end_us * 1e-6)

    if end_s <= start_s:
        empty = np.array([], dtype=float)
        return empty, empty, empty

    dt_a = float(np.median(np.diff(t_a))) if len(t_a) > 1 else np.inf
    dt_b = float(np.median(np.diff(t_b))) if len(t_b) > 1 else np.inf
    dt = max(dt_a, dt_b)
    n_points = int(np.floor((end_s - start_s) / dt)) + 1 if dt > 0 and np.isfinite(dt) else 0
    n_points = max(2, min(max_points, n_points))
    t_grid = np.linspace(start_s, end_s, n_points)
    ya = np.interp(t_grid, t_a, y_a)
    yb = np.interp(t_grid, t_b, y_b)
    return t_grid, ya, yb


def normalized_rmse(a: np.ndarray, b: np.ndarray) -> float:
    """RMSE normalized by signal range."""
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    rmse = float(np.sqrt(np.mean((a - b) ** 2)))
    denom = float(np.ptp(a))
    if denom <= 0:
        denom = float(np.max(np.abs(a)))
    if denom <= 0:
        return float("nan")
    return float(rmse / denom)


def cross_correlation_delay(
    time_s: np.ndarray,
    before: np.ndarray,
    after: np.ndarray,
) -> tuple[float, float]:
    """Return delay that maximizes normalized cross-correlation."""
    if len(before) < 4 or len(after) < 4 or len(before) != len(after):
        return float("nan"), float("nan")
    a = before.astype(float) - np.mean(before)
    b = after.astype(float) - np.mean(after)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm <= 0:
        return float("nan"), float("nan")
    corr = np.correlate(b, a, mode="full") / norm
    lags = np.arange(-len(a) + 1, len(a))
    idx = int(np.argmax(corr))
    dt = float(np.median(np.diff(time_s))) if len(time_s) > 1 else float("nan")
    return float(lags[idx] * dt), float(corr[idx])


def waveform_similarity_metrics(
    name_before: str,
    time_before_s: np.ndarray,
    value_before: np.ndarray,
    name_after: str,
    time_after_s: np.ndarray,
    value_after: np.ndarray,
    start_us: float | None = None,
    end_us: float | None = None,
    baseline_mode: str = "t<0",
    max_points: int = 50_000,
) -> dict:
    """Compare two waveforms in a selected interval."""
    y_before, _ = subtract_baseline(time_before_s, value_before, mode=baseline_mode)
    y_after, _ = subtract_baseline(time_after_s, value_after, mode=baseline_mode)
    t, a, b = common_grid_for_comparison(
        time_before_s,
        y_before,
        time_after_s,
        y_after,
        start_us=start_us,
        end_us=end_us,
        max_points=max_points,
    )
    if len(t) < 4:
        return {
            "before": name_before,
            "after": name_after,
            "comparison_start_us": start_us,
            "comparison_end_us": end_us,
            "pearson_r": float("nan"),
            "nrmse": float("nan"),
            "mae_v": float("nan"),
            "max_abs_diff_v": float("nan"),
            "delay_xcorr_us": float("nan"),
            "xcorr_peak": float("nan"),
            "area_abs_diff_v_s": float("nan"),
            "area_abs_diff_percent_of_before": float("nan"),
        }

    if np.std(a) > 0 and np.std(b) > 0:
        pearson = float(np.corrcoef(a, b)[0, 1])
    else:
        pearson = float("nan")
    nrmse = normalized_rmse(a, b)
    mae = float(np.mean(np.abs(a - b)))
    max_abs_diff = float(np.max(np.abs(a - b)))
    delay_s, corr_peak = cross_correlation_delay(t, a, b)
    area_diff = trapezoid_integral(np.abs(a - b), t)
    area_before = trapezoid_integral(np.abs(a), t)
    area_diff_pct = float(100.0 * area_diff / area_before) if area_before > 0 else float("nan")

    return {
        "before": name_before,
        "after": name_after,
        "comparison_start_us": start_us,
        "comparison_end_us": end_us,
        "pearson_r": pearson,
        "nrmse": nrmse,
        "mae_v": mae,
        "max_abs_diff_v": max_abs_diff,
        "delay_xcorr_us": float(delay_s * 1e6) if np.isfinite(delay_s) else float("nan"),
        "xcorr_peak": corr_peak,
        "area_abs_diff_v_s": area_diff,
        "area_abs_diff_percent_of_before": area_diff_pct,
    }


def compare_ringdown_metrics(before: dict, after: dict) -> pd.DataFrame:
    """Build before/after table with absolute and percent deltas."""
    keys = [
        "period_peaks_us",
        "period_extrema_us",
        "period_zero_cross_us",
        "freq_damped_khz",
        "freq_fft_ring_khz",
        "tau_envelope_us",
        "log_decrement",
        "damping_ratio_zeta",
        "quality_factor_q",
        "ring_energy_resistive_j",
        "ring_v_pp",
        "ring_peak_abs",
        "ring_rms",
        "spectral_centroid_hz",
        "spectral_bandwidth_hz",
        "decay_per_cycle_percent",
        "t_to_10_percent_us",
        "settling_5_percent_us",
        "asymmetry_pos_neg",
    ]
    rows = []
    for key in keys:
        b = finite_or_nan(before.get(key, np.nan))
        a = finite_or_nan(after.get(key, np.nan))
        rows.append(
            {
                "metrica": key,
                "before": b,
                "after": a,
                "delta": a - b if np.isfinite(a) and np.isfinite(b) else float("nan"),
                "delta_percent": safe_percent_change(b, a),
            }
        )
    return pd.DataFrame(rows)


def resonance_shift_score(comparison_df: pd.DataFrame) -> float:
    """Exploratory scalar score from selected percent changes.

    This is not a validated biological endpoint. It is only a screening index
    to rank experiments that changed the ringdown signature the most.
    """
    selected = comparison_df[
        comparison_df["metrica"].isin(
            [
                "period_peaks_us",
                "freq_damped_khz",
                "tau_envelope_us",
                "quality_factor_q",
                "ring_energy_resistive_j",
            ]
        )
    ]["delta_percent"].to_numpy(dtype=float)
    selected = selected[np.isfinite(selected)]
    if len(selected) == 0:
        return float("nan")
    return float(np.sqrt(np.mean(selected ** 2)))


def metrics_dataframe(metrics: list[dict]) -> pd.DataFrame:
    """Build pandas table."""
    return pd.DataFrame(metrics)


def align_current_to_voltage(
    t_v: np.ndarray,
    v: np.ndarray,
    t_i: np.ndarray,
    i: np.ndarray,
    current_scale_a_per_unit: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate current onto the voltage time base."""
    i_interp = np.interp(t_v, t_i, i) * current_scale_a_per_unit
    return t_v, v, i_interp


def vi_metrics(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    current_a: np.ndarray,
) -> dict:
    """Power/energy and dynamic impedance metrics for V/I pair."""
    if len(time_s) < 2:
        return {}
    power_w = voltage_v * current_a
    energy_j = trapezoid_integral(power_w, time_s)
    apparent_energy_abs_j = trapezoid_integral(np.abs(power_w), time_s)
    charge_c = trapezoid_integral(current_a, time_s)
    abs_charge_c = trapezoid_integral(np.abs(current_a), time_s)
    i2_dt = trapezoid_integral(current_a ** 2, time_s)
    effective_resistance = energy_j / i2_dt if i2_dt > 0 else float("nan")

    i_threshold = 0.05 * float(np.max(np.abs(current_a))) if len(current_a) else float("nan")
    mask = np.abs(current_a) > i_threshold if np.isfinite(i_threshold) and i_threshold > 0 else np.zeros_like(current_a, dtype=bool)
    if np.any(mask):
        z_inst = voltage_v[mask] / current_a[mask]
        z_median = float(np.median(z_inst))
        z_mean = float(np.mean(z_inst))
    else:
        z_median = float("nan")
        z_mean = float("nan")

    delay_s, corr_peak = cross_correlation_delay(time_s, voltage_v, current_a)

    f_v, _ = fft_dominant_frequency(time_s, voltage_v)
    z_fft_mag = float("nan")
    z_fft_phase_deg = float("nan")
    if np.isfinite(f_v) and f_v > 0:
        dt = float(np.median(np.diff(time_s)))
        v0 = voltage_v - np.mean(voltage_v)
        i0 = current_a - np.mean(current_a)
        freqs = np.fft.rfftfreq(len(v0), d=dt)
        v_spec = np.fft.rfft(v0 * np.hanning(len(v0)))
        i_spec = np.fft.rfft(i0 * np.hanning(len(i0)))
        idx = int(np.argmin(np.abs(freqs - f_v)))
        if idx < len(i_spec) and abs(i_spec[idx]) > 0:
            z = v_spec[idx] / i_spec[idx]
            z_fft_mag = float(abs(z))
            z_fft_phase_deg = float(np.angle(z, deg=True))

    return {
        "v_max": float(np.max(voltage_v)),
        "v_min": float(np.min(voltage_v)),
        "i_max": float(np.max(current_a)),
        "i_min": float(np.min(current_a)),
        "p_max_w": float(np.max(power_w)),
        "p_min_w": float(np.min(power_w)),
        "energia_j": energy_j,
        "energia_abs_j": apparent_energy_abs_j,
        "carga_c": charge_c,
        "carga_abs_c": abs_charge_c,
        "resistencia_efetiva_ohm": effective_resistance,
        "impedancia_instantanea_mediana_ohm": z_median,
        "impedancia_instantanea_media_ohm": z_mean,
        "freq_impedancia_fft_hz": f_v,
        "impedancia_fft_mag_ohm": z_fft_mag,
        "impedancia_fft_phase_deg": z_fft_phase_deg,
        "delay_v_i_xcorr_us": float(delay_s * 1e6) if np.isfinite(delay_s) else float("nan"),
        "xcorr_v_i_peak": corr_peak,
    }
