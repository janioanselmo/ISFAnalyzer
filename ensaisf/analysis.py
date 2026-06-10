"""Rotinas de análise para formas de onda Tektronix ISF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class PulseWindow:
    start_s: float
    end_s: float
    start_index: int
    end_index: int


def decimate_for_plot(
    time_s: np.ndarray,
    value: np.ndarray,
    max_points: int = 30_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduz pontos para plotagem mantendo desempenho."""
    if len(time_s) <= max_points:
        return time_s, value

    step = int(np.ceil(len(time_s) / max_points))
    return time_s[::step], value[::step]


def estimate_baseline(
    time_s: np.ndarray,
    value: np.ndarray,
    mode: str = "t<0",
    first_fraction: float = 0.10,
) -> float:
    """Estima linha de base."""
    if mode == "t<0":
        mask = time_s < 0
        if np.any(mask):
            return float(np.median(value[mask]))

    n = max(10, int(len(value) * first_fraction))
    return float(np.median(value[:n]))


def auto_pulse_window(
    time_s: np.ndarray,
    value: np.ndarray,
    baseline: float,
    threshold_fraction: float = 0.10,
) -> Optional[PulseWindow]:
    """Detecta janela do pulso por limiar relativo ao pico absoluto."""
    y = value - baseline
    peak = float(np.max(np.abs(y)))
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


def fft_dominant_frequency(
    time_s: np.ndarray,
    value: np.ndarray,
    f_min_hz: float = 1.0,
) -> tuple[float, float]:
    """Frequência dominante por FFT em uma janela de sinal."""
    if len(value) < 8:
        return float("nan"), float("nan")

    dt = float(np.median(np.diff(time_s)))
    if dt <= 0:
        return float("nan"), float("nan")

    y = value - np.mean(value)
    window = np.hanning(len(y))
    spectrum = np.fft.rfft(y * window)
    freqs = np.fft.rfftfreq(len(y), d=dt)
    mag = np.abs(spectrum)

    mask = freqs >= f_min_hz
    if not np.any(mask):
        return float("nan"), float("nan")

    idx_rel = int(np.argmax(mag[mask]))
    idx = int(np.flatnonzero(mask)[idx_rel])
    return float(freqs[idx]), float(mag[idx])


def zero_crossing_frequency(time_s: np.ndarray, value: np.ndarray) -> float:
    """Estimativa simples de frequência por cruzamentos de zero."""
    if len(value) < 4:
        return float("nan")

    y = value - np.mean(value)
    signs = np.signbit(y)
    crossing_indices = np.flatnonzero(np.diff(signs))

    if len(crossing_indices) < 3:
        return float("nan")

    crossing_times = time_s[crossing_indices]
    half_periods = np.diff(crossing_times)
    half_periods = half_periods[half_periods > 0]

    if len(half_periods) == 0:
        return float("nan")

    period = 2.0 * float(np.median(half_periods))
    if period <= 0:
        return float("nan")

    return float(1.0 / period)


def estimate_decay_tau(time_s: np.ndarray, value: np.ndarray) -> float:
    """Estima constante de decaimento de oscilação amortecida.

    Usa picos locais de |y| e regressão linear em log(envelope).
    É uma aproximação; para publicação, ajustar modelo físico depois.
    """
    if len(value) < 20:
        return float("nan")

    y = np.abs(value - np.mean(value))
    if np.max(y) <= 0:
        return float("nan")

    # Picos locais simples sem scipy
    peaks = np.flatnonzero((y[1:-1] > y[:-2]) & (y[1:-1] >= y[2:])) + 1
    if len(peaks) < 5:
        return float("nan")

    # Mantém picos acima de 15% do maior para evitar ruído final.
    peaks = peaks[y[peaks] > 0.15 * np.max(y)]
    if len(peaks) < 5:
        return float("nan")

    t = time_s[peaks]
    envelope = y[peaks]

    valid = envelope > 0
    t = t[valid]
    envelope = envelope[valid]

    if len(t) < 5 or np.ptp(t) <= 0:
        return float("nan")

    slope, _intercept = np.polyfit(t, np.log(envelope), deg=1)
    if slope >= 0:
        return float("nan")

    return float(-1.0 / slope)


def integrate_energy_resistive(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    resistance_ohm: float,
) -> float:
    """Energia aproximada em carga resistiva: integral(v²/R dt)."""
    if resistance_ohm <= 0 or len(voltage_v) < 2:
        return float("nan")
    power_w = (voltage_v ** 2) / resistance_ohm
    return float(np.trapz(power_w, time_s))


def electric_field_metrics(
    peak_abs_v: float,
    gap_mm: float,
) -> tuple[float, float]:
    """Campo elétrico em V/m e kV/cm para um pico de tensão."""
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
    """Calcula métricas principais de uma forma de onda."""
    baseline = estimate_baseline(time_s, value, mode=baseline_mode)
    y = value - baseline

    pulse = auto_pulse_window(time_s, value, baseline, threshold_fraction)

    if pulse is not None:
        t_win = time_s[pulse.start_index:pulse.end_index + 1]
        y_win = y[pulse.start_index:pulse.end_index + 1]
        pulse_width_s = pulse.end_s - pulse.start_s
    else:
        t_win = time_s
        y_win = y
        pulse_width_s = float("nan")

    f_fft, fft_mag = fft_dominant_frequency(t_win, y_win)
    f_zc = zero_crossing_frequency(t_win, y_win)
    tau_s = estimate_decay_tau(t_win, y_win)

    v_max = float(np.max(value))
    v_min = float(np.min(value))
    v_pp = float(v_max - v_min)
    peak_abs = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(y ** 2)))

    energy_j = integrate_energy_resistive(t_win, y_win, resistance_ohm)
    e_v_m, e_kv_cm = electric_field_metrics(peak_abs, gap_mm)

    return {
        "arquivo": name,
        "pontos": int(len(value)),
        "t_inicial_us": float(time_s[0] * 1e6),
        "t_final_us": float(time_s[-1] * 1e6),
        "dt_ns": float(np.median(np.diff(time_s)) * 1e9),
        "baseline": baseline,
        "v_max": v_max,
        "v_min": v_min,
        "v_pp": v_pp,
        "pico_abs_corrigido": peak_abs,
        "rms_corrigido": rms,
        "pulso_inicio_us": float(pulse.start_s * 1e6) if pulse else float("nan"),
        "pulso_fim_us": float(pulse.end_s * 1e6) if pulse else float("nan"),
        "largura_pulso_us": float(pulse_width_s * 1e6),
        "freq_fft_hz": f_fft,
        "freq_fft_khz": f_fft / 1e3 if np.isfinite(f_fft) else float("nan"),
        "freq_zero_cross_hz": f_zc,
        "freq_zero_cross_khz": f_zc / 1e3 if np.isfinite(f_zc) else float("nan"),
        "tau_decaimento_us": tau_s * 1e6 if np.isfinite(tau_s) else float("nan"),
        "energia_resistiva_j": energy_j,
        "campo_v_m": e_v_m,
        "campo_kv_cm": e_kv_cm,
    }


def metrics_dataframe(metrics: list[dict]) -> pd.DataFrame:
    """Gera tabela pandas."""
    return pd.DataFrame(metrics)


def align_current_to_voltage(
    t_v: np.ndarray,
    v: np.ndarray,
    t_i: np.ndarray,
    i: np.ndarray,
    current_scale_a_per_unit: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpola corrente na base temporal da tensão."""
    i_interp = np.interp(t_v, t_i, i) * current_scale_a_per_unit
    return t_v, v, i_interp


def vi_metrics(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    current_a: np.ndarray,
) -> dict:
    """Métricas de potência/energia para par tensão-corrente."""
    power_w = voltage_v * current_a
    energy_j = float(np.trapz(power_w, time_s))
    apparent_energy_abs_j = float(np.trapz(np.abs(power_w), time_s))

    return {
        "v_max": float(np.max(voltage_v)),
        "v_min": float(np.min(voltage_v)),
        "i_max": float(np.max(current_a)),
        "i_min": float(np.min(current_a)),
        "p_max_w": float(np.max(power_w)),
        "p_min_w": float(np.min(power_w)),
        "energia_j": energy_j,
        "energia_abs_j": apparent_energy_abs_j,
    }
