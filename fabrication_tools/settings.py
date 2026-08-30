"""Shared DXF settings and finalized-package configuration helpers."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


DEFAULT_DXF_DPI = 300.0
DEFAULT_FRAME_MARGIN_MM = 5.0
DEFAULT_SETTING_HOLE_DIAMETER_MM = 2.5
DEFAULT_SETTING_HOLE_INSET_MM = 7.0
SETTINGS_FILENAME = "fabrication_settings.json"


@dataclass(frozen=True)
class DxfSettings:
    dpi: float = DEFAULT_DXF_DPI
    dpi_x: float = DEFAULT_DXF_DPI
    dpi_y: float = DEFAULT_DXF_DPI
    frame_margin_mm: float = DEFAULT_FRAME_MARGIN_MM
    frame_margin_x_mm: float = DEFAULT_FRAME_MARGIN_MM
    frame_margin_y_mm: float = DEFAULT_FRAME_MARGIN_MM
    setting_hole_diameter_mm: float = DEFAULT_SETTING_HOLE_DIAMETER_MM
    setting_hole_inset_mm: float = DEFAULT_SETTING_HOLE_INSET_MM
    frame_shape: str = "rectangle"
    frame_geometry_file: str | None = None


def _positive_number(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


def load_dxf_settings(directory: str | Path) -> DxfSettings:
    """Load recorded DXF settings from a final package, or use defaults."""
    settings_path = Path(directory) / SETTINGS_FILENAME
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DxfSettings()

    dxf = raw.get("dxf", {}) if isinstance(raw, dict) else {}
    if not isinstance(dxf, dict):
        return DxfSettings()
    frame_shape = dxf.get("frame_shape", "rectangle")
    if frame_shape not in {"rectangle", "first_layer"}:
        frame_shape = "rectangle"
    frame_geometry_file = dxf.get("frame_geometry_file")
    if not isinstance(frame_geometry_file, str) or not frame_geometry_file.strip():
        frame_geometry_file = None

    return DxfSettings(
        dpi=_positive_number(dxf.get("dpi"), DEFAULT_DXF_DPI),
        dpi_x=_positive_number(
            dxf.get("dpi_x"),
            _positive_number(dxf.get("dpi"), DEFAULT_DXF_DPI),
        ),
        dpi_y=_positive_number(
            dxf.get("dpi_y"),
            _positive_number(dxf.get("dpi"), DEFAULT_DXF_DPI),
        ),
        frame_margin_mm=_positive_number(
            dxf.get("frame_margin_mm"),
            DEFAULT_FRAME_MARGIN_MM,
        ),
        frame_margin_x_mm=_positive_number(
            dxf.get("frame_margin_x_mm"),
            _positive_number(dxf.get("frame_margin_mm"), DEFAULT_FRAME_MARGIN_MM),
        ),
        frame_margin_y_mm=_positive_number(
            dxf.get("frame_margin_y_mm"),
            _positive_number(dxf.get("frame_margin_mm"), DEFAULT_FRAME_MARGIN_MM),
        ),
        setting_hole_diameter_mm=_positive_number(
            dxf.get("setting_hole_diameter_mm"),
            DEFAULT_SETTING_HOLE_DIAMETER_MM,
        ),
        setting_hole_inset_mm=_positive_number(
            dxf.get("setting_hole_inset_mm"),
            DEFAULT_SETTING_HOLE_INSET_MM,
        ),
        frame_shape=frame_shape,
        frame_geometry_file=frame_geometry_file,
    )


def merge_fabrication_settings(directory: str | Path, updates: dict[str, Any]) -> Path:
    """Deep-merge package settings so later stages do not erase frame geometry."""
    settings_path = Path(directory) / SETTINGS_FILENAME
    try:
        current = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current = {}
    if not isinstance(current, dict):
        current = {}

    def merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value

    merge(current, updates)
    return write_fabrication_settings(directory, current)


def write_fabrication_settings(directory: str | Path, settings: dict[str, Any]) -> Path:
    """Persist resolved fabrication settings alongside a finalized package."""
    settings_path = Path(directory) / SETTINGS_FILENAME
    settings_path.write_text(
        json.dumps(settings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return settings_path
