"""Filename-based signal classification helpers for Tektronix ISF files.

The laboratory acquisition convention is:
    TXXXXCH1 -> voltage
    TXXXXCH2 -> current

Keeping the rule in one module avoids duplicating channel logic across the
Streamlit screens and exported tables.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from pathlib import Path
from typing import Iterable


_CHANNEL_PATTERN = re.compile(r"T(?P<pulse>\d+)CH(?P<channel>[12])", re.IGNORECASE)

_ROLE_BY_CHANNEL = {
    1: "voltage",
    2: "current",
}

_ROLE_LABEL_PT = {
    "voltage": "Tensão",
    "current": "Corrente",
    "unknown": "Não classificado",
}

_ROLE_UNIT = {
    "voltage": "V",
    "current": "A ou unidade do canal",
    "unknown": "unidade do arquivo",
}

_ROLE_ICON = {
    "voltage": "⚡",
    "current": "↗",
    "unknown": "?",
}


@dataclass(frozen=True)
class SignalInfo:
    """Channel metadata extracted from an uploaded waveform filename."""

    role: str
    role_label: str
    role_icon: str
    role_unit: str
    channel: int | None
    pulse_index: int | None
    pulse_label: str

    def as_dict(self) -> dict:
        """Return a plain dictionary suitable for merging into waveform items."""
        return asdict(self)


def classify_signal_name(filename: str) -> SignalInfo:
    """Classify a Tektronix filename into voltage/current/unknown."""
    stem = Path(filename).stem
    match = _CHANNEL_PATTERN.search(stem)
    if match is None:
        return SignalInfo(
            role="unknown",
            role_label=_ROLE_LABEL_PT["unknown"],
            role_icon=_ROLE_ICON["unknown"],
            role_unit=_ROLE_UNIT["unknown"],
            channel=None,
            pulse_index=None,
            pulse_label="Pulso não identificado",
        )

    channel = int(match.group("channel"))
    pulse_index = int(match.group("pulse"))
    role = _ROLE_BY_CHANNEL.get(channel, "unknown")
    return SignalInfo(
        role=role,
        role_label=_ROLE_LABEL_PT[role],
        role_icon=_ROLE_ICON[role],
        role_unit=_ROLE_UNIT[role],
        channel=channel,
        pulse_index=pulse_index,
        pulse_label=f"Pulso {pulse_index:04d}",
    )


def item_label(item: dict) -> str:
    """Human-readable label for Streamlit selectors."""
    role_icon = item.get("role_icon", "?")
    role_label = item.get("role_label", "Não classificado")
    pulse_label = item.get("pulse_label", "Pulso não identificado")
    return f"{role_icon} {item['name']} — {role_label} | {pulse_label}"


def filter_items_by_role(items: Iterable[dict], role: str | None) -> list[dict]:
    """Return items matching a signal role, or all items when role is None."""
    if role is None or role == "all":
        return list(items)
    return [item for item in items if item.get("role") == role]


def sort_items_by_pulse(items: Iterable[dict]) -> list[dict]:
    """Sort waveforms by pulse index, channel, then filename."""
    def _key(item: dict) -> tuple[int, int, str]:
        pulse = item.get("pulse_index")
        channel = item.get("channel")
        return (
            int(pulse) if pulse is not None else 10**12,
            int(channel) if channel is not None else 99,
            str(item.get("name", "")),
        )

    return sorted(items, key=_key)


def role_counts(items: Iterable[dict]) -> dict[str, int]:
    """Count voltage/current/unknown items."""
    counts = {"voltage": 0, "current": 0, "unknown": 0}
    for item in items:
        role = item.get("role", "unknown")
        counts[role if role in counts else "unknown"] += 1
    return counts


def names_for_role(items: Iterable[dict], role: str | None) -> list[str]:
    """Return item names for a given role, sorted by pulse."""
    return [item["name"] for item in sort_items_by_pulse(filter_items_by_role(items, role))]


def matching_current_for_voltage(voltage_item: dict, items: Iterable[dict]) -> dict | None:
    """Find the current waveform with the same pulse index as a voltage item."""
    pulse_index = voltage_item.get("pulse_index")
    if pulse_index is None:
        return None
    for item in sort_items_by_pulse(items):
        if item.get("role") == "current" and item.get("pulse_index") == pulse_index:
            return item
    return None
