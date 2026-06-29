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
    "parse_uploaded_file",
    "_source_group_from_name",
    "_safe_zip_member",
    "_safe_dataset_root",
    "_zip_member_display_name",
    "_unique_upload_name",
    "expand_uploaded_files",
    "standardize_waveforms_by_group",
]


@st.cache_data(show_spinner=False)
def parse_uploaded_file(name: str, data: bytes):
    waveform = read_isf_bytes(data)
    normalized_name = str(name).replace("\\", "/")
    return {
        "name": normalized_name,
        "source_path": normalized_name,
        "raw_filename": Path(normalized_name).name,
        "source_group": _source_group_from_name(normalized_name),
        "data_hash": hashlib.md5(data).hexdigest(),
        "time_s": waveform.time_s,
        "value": waveform.value,
        "metadata": waveform.metadata,
        "header": waveform.header,
    }


def _source_group_from_name(name: str) -> str:
    """Return the folder/acquisition group for a file-like display name."""
    normalized = str(name).replace("\\", "/")
    parent = str(Path(normalized).parent).replace("\\", "/")
    if parent in {".", ""}:
        return "Arquivos avulsos"
    return parent


def _safe_zip_member(member_name: str) -> bool:
    """Accept regular ISF files from ZIPs and reject unsafe paths."""
    normalized = str(member_name).replace("\\", "/")
    path = Path(normalized)
    if normalized.endswith("/") or path.is_absolute():
        return False
    if any(part in {"", ".", ".."} for part in path.parts):
        return False
    return path.suffix.lower() == ".isf"


def _safe_dataset_root(upload_name: str) -> str:
    """Return a stable dataset root from the uploaded ZIP filename."""
    stem = Path(str(upload_name).replace("\\", "/")).stem.strip()
    if not stem:
        stem = "dataset_zip"
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ÿ_.() -]+", "_", stem).strip(" ._")
    return cleaned or "dataset_zip"


def _zip_member_display_name(upload_name: str, member_name: str) -> str:
    """Build a unique, dataset-aware display path for a ZIP member.

    The app must work with any uploaded ZIP, not only a specific validation
    package. Prefixing each member with the ZIP stem preserves dataset identity
    when several ZIPs contain identical internal folder/file names. If the ZIP
    already contains a top-level folder with the same name as the archive, the
    function avoids duplicating that root.
    """
    dataset_root = _safe_dataset_root(upload_name)
    normalized_member = str(member_name).replace("\\", "/").lstrip("/")
    member_parts = Path(normalized_member).parts
    if member_parts and member_parts[0].lower() == dataset_root.lower():
        return normalized_member
    return f"{dataset_root}/{normalized_member}"


def _unique_upload_name(name: str, used_names: set[str]) -> str:
    """Return a stable unique name while keeping the Tektronix basename readable."""
    normalized = str(name).replace("\\", "/")
    if normalized not in used_names:
        used_names.add(normalized)
        return normalized

    path = Path(normalized)
    stem = path.stem
    suffix = path.suffix
    parent = str(path.parent).replace("\\", "/")
    parent = "" if parent in {".", ""} else parent
    counter = 2
    while True:
        candidate_name = f"{stem}__duplicado_{counter:02d}{suffix}"
        candidate = f"{parent}/{candidate_name}" if parent else candidate_name
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter += 1


def expand_uploaded_files(uploaded_files) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Expand direct .ISF uploads and .ZIP uploads into unique file entries."""
    entries: list[tuple[str, bytes]] = []
    errors: list[str] = []
    used_names: set[str] = set()

    for uploaded in uploaded_files:
        upload_name = str(uploaded.name)
        data = uploaded.getvalue()
        if upload_name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(data)) as archive:
                    for info in sorted(archive.infolist(), key=lambda item: item.filename.lower()):
                        if not _safe_zip_member(info.filename):
                            continue
                        try:
                            member_data = archive.read(info)
                        except Exception as exc:
                            errors.append(f"{upload_name}/{info.filename}: {exc}")
                            continue
                        display_name = _zip_member_display_name(upload_name, info.filename)
                        member_name = _unique_upload_name(display_name, used_names)
                        entries.append((member_name, member_data))
            except zipfile.BadZipFile as exc:
                errors.append(f"{upload_name}: ZIP inválido ({exc})")
        elif upload_name.lower().endswith(".isf"):
            entries.append((_unique_upload_name(upload_name, used_names), data))
        else:
            errors.append(f"{upload_name}: formato ignorado; carregue .ISF ou .ZIP")

    return entries, errors


def standardize_waveforms_by_group(
    waveforms: list[dict],
    enabled: bool = True,
    target_count: int | None = None,
) -> tuple[list[dict], pd.DataFrame, int | None]:
    """Keep the first N acquisition indices in each folder/group.

    The count is dynamic and based on distinct Tektronix TXXXX acquisition
    indices, not on individual channels. Therefore N acquisitions means up to
    2N files when both CH1 and CH2 are present. No dataset name or acquisition
    count is hard-coded here.
    """
    if not waveforms:
        return waveforms, pd.DataFrame(), None

    rows = []
    pulse_indices_by_group: dict[str, list[int]] = {}
    for group in sorted({item.get("source_group", "Arquivos avulsos") for item in waveforms}):
        group_items = [item for item in waveforms if item.get("source_group") == group]
        pulse_indices = sorted(
            {int(item["pulse_index"]) for item in group_items if item.get("pulse_index") is not None}
        )
        pulse_indices_by_group[group] = pulse_indices
        rows.append(
            {
                "grupo/pasta": group,
                "arquivos_isf": int(len(group_items)),
                "aquisições_TXXXX": int(len(pulse_indices)),
                "tensão_CH1": int(sum(1 for item in group_items if item.get("role") == "voltage")),
                "corrente_CH2": int(sum(1 for item in group_items if item.get("role") == "current")),
            }
        )

    summary = pd.DataFrame(rows)
    counts = [len(values) for values in pulse_indices_by_group.values() if values]
    common_count = int(min(counts)) if counts else None
    if target_count is not None and common_count is not None:
        common_count = min(int(target_count), common_count)

    if not enabled or common_count is None:
        return waveforms, summary, common_count

    allowed_by_group = {
        group: set(indices[:common_count])
        for group, indices in pulse_indices_by_group.items()
    }
    filtered = [
        item
        for item in waveforms
        if item.get("pulse_index") is None
        or int(item["pulse_index"]) in allowed_by_group.get(item.get("source_group"), set())
    ]
    return filtered, summary, common_count
