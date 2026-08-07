"""Strict discovery and normalized facts for a completed layer run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import cv2
import ezdxf
from ezdxf import bbox


CANONICAL_LAYER_RE = re.compile(r"^Layer_(\d{2,})_(.+)\.(png|dxf)$", re.IGNORECASE)
CLEAT_LABELS = (
    "french_cleat_backing",
    "french_cleat_cavity",
    "french_cleat_keyhole",
)
MM_INSUNITS = 4
INCHES_PER_MM = 1 / 25.4


class ReleaseValidationError(ValueError):
    """Raised when a final package cannot safely become a release."""


@dataclass(frozen=True)
class LayerFile:
    index: int
    label: str
    stem: str
    png_path: Path
    dxf_path: Path

    @property
    def is_cleat(self) -> bool:
        return self.label in CLEAT_LABELS


@dataclass(frozen=True)
class ReleaseFacts:
    source_final: Path
    run_dir: Path | None
    project_id: str | None
    run_id: str | None
    original_filename: str | None
    layers: tuple[LayerFile, ...]
    source_pixels: tuple[int, int]
    dimensions_mm: tuple[float, float]
    stock_size_in: str | None
    dpi: float | None
    warnings: tuple[str, ...]

    @property
    def art_layers(self) -> tuple[LayerFile, ...]:
        return tuple(layer for layer in self.layers if not layer.is_cleat)

    @property
    def cleat_layers(self) -> tuple[LayerFile, ...]:
        return tuple(layer for layer in self.layers if layer.is_cleat)

    @property
    def has_valid_cleats(self) -> bool:
        cleats = self.cleat_layers
        return (
            len(cleats) == 3
            and tuple(layer.label for layer in cleats) == CLEAT_LABELS
            and tuple(layer.index for layer in cleats)
            == tuple(range(len(self.layers) - 3, len(self.layers)))
        )

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_final"] = "outputs/final"
        value["run_dir"] = None
        value["layers"] = [
            {
                "index": layer.index,
                "label": layer.label,
                "stem": layer.stem,
                "source": {
                    "originalFilename": layer.png_path.name,
                    "dxfFilename": layer.dxf_path.name,
                },
                "is_cleat": layer.is_cleat,
            }
            for layer in self.layers
        ]
        return value


def resolve_final_dir(requested: str | Path) -> tuple[Path, Path | None]:
    """Resolve either a final package or exactly its own run's final package."""
    requested_path = Path(requested).expanduser().resolve()
    candidates = (requested_path, requested_path / "outputs" / "final")
    for candidate in candidates:
        if candidate.is_dir() and any(CANONICAL_LAYER_RE.match(path.name) for path in candidate.iterdir()):
            run_dir = requested_path if candidate != requested_path else _find_run_dir(candidate)
            return candidate, run_dir
    raise ReleaseValidationError(
        "Could not resolve a final package. Pass a final directory containing "
        "canonical Layer_XX_<label>.png/.dxf files, or its run directory."
    )


def _find_run_dir(final_dir: Path) -> Path | None:
    parent = final_dir.parent
    if parent.name == "outputs" and (parent.parent / "run.json").is_file():
        return parent.parent
    return None


def discover_release_facts(requested: str | Path) -> ReleaseFacts:
    final_dir, run_dir = resolve_final_dir(requested)
    layers = discover_canonical_layers(final_dir)
    source_pixels = validate_pngs(layers)
    dimensions_mm = dxf_dimensions_mm(layers[0].dxf_path)
    for layer in layers[1:]:
        candidate = dxf_dimensions_mm(layer.dxf_path)
        if not _dimensions_equal(dimensions_mm, candidate):
            raise ReleaseValidationError(
                f"DXF canvas mismatch: {layer.dxf_path.name} is {candidate}, "
                f"expected {dimensions_mm}."
            )

    run_data = _read_json(run_dir / "run.json") if run_dir else {}
    handoff_data = _read_json(final_dir / "run_metadata.json")
    warnings: list[str] = []
    _record_layer_count_conflicts(warnings, layers, run_data, handoff_data)
    dpi = _read_dpi(handoff_data)
    return ReleaseFacts(
        source_final=final_dir,
        run_dir=run_dir,
        project_id=run_data.get("projectId") or (run_dir.parent.parent.name if run_dir else None),
        run_id=run_data.get("runId") or (run_dir.name if run_dir else None),
        original_filename=(run_data.get("source") or {}).get("originalFilename"),
        layers=tuple(layers),
        source_pixels=source_pixels,
        dimensions_mm=dimensions_mm,
        stock_size_in=(run_data.get("parameters") or {}).get("stockSizeIn"),
        dpi=dpi,
        warnings=tuple(warnings),
    )


def discover_canonical_layers(final_dir: Path) -> list[LayerFile]:
    grouped: dict[str, dict[str, Path]] = {}
    identities: dict[int, str] = {}
    for path in final_dir.iterdir():
        if not path.is_file():
            continue
        match = CANONICAL_LAYER_RE.match(path.name)
        if not match:
            continue
        index, label, extension = int(match.group(1)), match.group(2), match.group(3).lower()
        stem = path.stem
        existing_stem = identities.setdefault(index, stem)
        if existing_stem != stem:
            raise ReleaseValidationError(f"Multiple canonical layer stems use index {index:02d}.")
        entries = grouped.setdefault(stem, {})
        if extension in entries:
            raise ReleaseValidationError(f"Duplicate canonical {extension.upper()} for {stem}.")
        entries[extension] = path

    if not grouped:
        raise ReleaseValidationError(f"No canonical layer pairs found in {final_dir}.")
    layers: list[LayerFile] = []
    for stem, files in grouped.items():
        if set(files) != {"png", "dxf"}:
            raise ReleaseValidationError(f"Canonical layer {stem} requires exactly one PNG and one DXF.")
        match = CANONICAL_LAYER_RE.match(files["png"].name)
        assert match is not None
        layers.append(LayerFile(int(match.group(1)), match.group(2), stem, files["png"], files["dxf"]))
    layers.sort(key=lambda layer: layer.index)
    indices = [layer.index for layer in layers]
    if indices != list(range(len(layers))):
        raise ReleaseValidationError(
            "Canonical layer indices must be unique, contiguous, and begin at 00; "
            f"found {', '.join(f'{index:02d}' for index in indices)}."
        )
    return layers


def validate_pngs(layers: list[LayerFile] | tuple[LayerFile, ...]) -> tuple[int, int]:
    expected: tuple[int, int] | None = None
    for layer in layers:
        if layer.png_path.stat().st_size == 0 or layer.dxf_path.stat().st_size == 0:
            raise ReleaseValidationError(f"Empty canonical source file for {layer.stem}.")
        image = cv2.imread(str(layer.png_path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 3 or image.shape[2] != 4:
            raise ReleaseValidationError(f"{layer.png_path.name} must be a readable RGBA PNG.")
        pixels = (int(image.shape[1]), int(image.shape[0]))
        if expected is None:
            expected = pixels
        elif pixels != expected:
            raise ReleaseValidationError(f"PNG dimensions differ: {layer.png_path.name} is {pixels}, expected {expected}.")
    assert expected is not None
    return expected


def dxf_dimensions_mm(path: Path) -> tuple[float, float]:
    try:
        doc = ezdxf.readfile(path)
    except Exception as exc:
        raise ReleaseValidationError(f"Cannot read DXF {path.name}: {exc}") from exc
    if doc.header.get("$INSUNITS", 0) != MM_INSUNITS:
        raise ReleaseValidationError(f"{path.name} must explicitly use millimeters ($INSUNITS=4).")
    try:
        extents = bbox.extents(doc.modelspace(), fast=False)
    except Exception as exc:
        raise ReleaseValidationError(f"Cannot measure DXF {path.name}: {exc}") from exc
    if not extents.has_data:
        raise ReleaseValidationError(f"DXF {path.name} has no measurable modelspace geometry.")
    width = float(extents.extmax.x - extents.extmin.x)
    height = float(extents.extmax.y - extents.extmin.y)
    if width <= 0 or height <= 0:
        raise ReleaseValidationError(f"DXF {path.name} has non-positive measured dimensions.")
    return (round(width, 6), round(height, 6))


def hash_tree(directory: Path, exclude_top_level: set[str] | None = None) -> dict[str, str]:
    excluded = exclude_top_level or set()
    hashes: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.relative_to(directory).parts[0] in excluded:
            continue
        hashes[path.relative_to(directory).as_posix()] = sha256_file(path)
    return hashes


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _record_layer_count_conflicts(warnings: list[str], layers: list[LayerFile], *metadata: dict[str, Any]) -> None:
    for document in metadata:
        for key in ("layerCount", "layer_count", "totalLayers"):
            if key in document and document[key] != len(layers):
                warnings.append(f"Metadata {key}={document[key]!r} conflicts with {len(layers)} canonical layers.")


def _read_dpi(metadata: dict[str, Any]) -> float | None:
    for key in ("dpi", "DPI"):
        value = metadata.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _dimensions_equal(left: tuple[float, float], right: tuple[float, float], tolerance: float = 0.05) -> bool:
    return abs(left[0] - right[0]) <= tolerance and abs(left[1] - right[1]) <= tolerance