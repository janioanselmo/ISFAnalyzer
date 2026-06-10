"""Parser simples e robusto para arquivos Tektronix ISF.

Compatível com muitos arquivos salvos por osciloscópios Tektronix.
A função principal é `read_isf_bytes`, que retorna tempo, amplitude e metadados.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

import numpy as np


@dataclass
class IsfWaveform:
    """Forma de onda convertida para unidades físicas."""

    time_s: np.ndarray
    value: np.ndarray
    metadata: dict
    header: str


_NUMBER_RE = r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?"


def _find_float(header: str, aliases: list[str], default: Optional[float] = None) -> Optional[float]:
    """Procura um valor numérico no cabeçalho usando possíveis nomes de campo."""
    for alias in aliases:
        pattern = rf"\b{re.escape(alias)}\b\s+({_NUMBER_RE})"
        found = re.search(pattern, header, flags=re.IGNORECASE)
        if found:
            return float(found.group(1))
    return default


def _find_int(header: str, aliases: list[str], default: Optional[int] = None) -> Optional[int]:
    value = _find_float(header, aliases, None)
    return int(value) if value is not None else default


def _find_text(header: str, aliases: list[str], default: str = "") -> str:
    """Procura valor textual simples no cabeçalho."""
    for alias in aliases:
        pattern = rf"\b{re.escape(alias)}\b\s+([^;:\s]+)"
        found = re.search(pattern, header, flags=re.IGNORECASE)
        if found:
            return found.group(1).strip().strip('"')
    return default


def _find_curve_block(data: bytes) -> tuple[int, int, str]:
    """Retorna posição inicial dos dados binários, tamanho do bloco e cabeçalho ASCII."""
    # Exemplo Tektronix: :CURV #71000000<dados>
    match = re.search(br":CURV(?:E)?\s*#(\d)(\d+)", data, flags=re.IGNORECASE)
    if not match:
        raise ValueError("Bloco binário ':CURV #' não encontrado no arquivo ISF.")

    n_digits = int(match.group(1))
    length_digits = match.group(2)[:n_digits]
    n_bytes = int(length_digits)
    data_start = match.end()

    header = data[:data_start].decode("ascii", errors="ignore")
    return data_start, n_bytes, header


def _raw_dtype(header: str, byte_count: int, bit_count: int) -> np.dtype:
    """Determina dtype do bloco binário."""
    byte_order = _find_text(header, ["BYT_OR", "BYT_ORder", "BYT_ORd"], "MSB").upper()
    bin_format = _find_text(header, ["BN_FMT", "BN_Fmt"], "RI").upper()

    signed = bin_format in {"RI", "SRI", "INT", "SIGNED"}

    if byte_count == 1 and bit_count == 8:
        return np.dtype("i1" if signed else "u1")

    if byte_count == 2 and bit_count == 16:
        endian = "<" if byte_order.startswith("LSB") else ">"
        return np.dtype(endian + ("i2" if signed else "u2"))

    if byte_count == 4 and bit_count == 32:
        endian = "<" if byte_order.startswith("LSB") else ">"
        return np.dtype(endian + ("i4" if signed else "u4"))

    raise ValueError(f"Formato binário não tratado: BYT_N={byte_count}, BIT_N={bit_count}")


def read_isf_bytes(data: bytes) -> IsfWaveform:
    """Lê bytes de um arquivo ISF e converte para tempo e amplitude.

    Fórmula Tektronix:
        y = (raw - YOFF) * YMULT + YZERO
        t = XZERO + (n - PT_OFF) * XINCR
    """
    data_start, n_bytes, header = _find_curve_block(data)

    byte_count = _find_int(header, ["BYT_N", "BYT_NR", "BYT_NR"], 1)
    bit_count = _find_int(header, ["BIT_N", "BIT_NR", "BIT_NR"], 8)

    if byte_count is None or bit_count is None:
        raise ValueError("Não foi possível identificar BYT_N/BIT_N no cabeçalho.")

    dtype = _raw_dtype(header, byte_count, bit_count)
    usable_bytes = n_bytes - (n_bytes % byte_count)
    raw = np.frombuffer(data[data_start:data_start + usable_bytes], dtype=dtype)

    x_increment = _find_float(header, ["XIN", "XINCR", "XINcr"], None)
    x_zero = _find_float(header, ["XZE", "XZERO", "XZEro"], 0.0)
    point_offset = _find_float(header, ["PT_O", "PT_OFF", "PT_Off"], 0.0)

    y_multiplier = _find_float(header, ["YMU", "YMULT", "YMUlt"], None)
    y_offset = _find_float(header, ["YOF", "YOFF", "YOFf"], 0.0)
    y_zero = _find_float(header, ["YZE", "YZERO", "YZEro"], 0.0)

    if x_increment is None:
        raise ValueError("Não foi possível identificar XINCR/XIN no cabeçalho.")
    if y_multiplier is None:
        raise ValueError("Não foi possível identificar YMULT/YMU no cabeçalho.")

    time_s = x_zero + (np.arange(raw.size, dtype=float) - point_offset) * x_increment
    value = (raw.astype(float) - y_offset) * y_multiplier + y_zero

    metadata = {
        "points": int(raw.size),
        "byte_count": int(byte_count),
        "bit_count": int(bit_count),
        "x_increment_s": float(x_increment),
        "x_zero_s": float(x_zero),
        "point_offset": float(point_offset),
        "y_multiplier": float(y_multiplier),
        "y_offset": float(y_offset),
        "y_zero": float(y_zero),
        "x_unit": _find_text(header, ["XUNIT", "XUN"], "s"),
        "y_unit": _find_text(header, ["YUNIT", "YUN"], "V"),
        "byte_order": _find_text(header, ["BYT_OR", "BYT_ORder"], ""),
        "bin_format": _find_text(header, ["BN_FMT", "BN_Fmt"], ""),
    }

    return IsfWaveform(time_s=time_s, value=value, metadata=metadata, header=header)


def read_isf_file(path: str) -> IsfWaveform:
    """Lê arquivo ISF no disco."""
    with open(path, "rb") as file:
        return read_isf_bytes(file.read())
