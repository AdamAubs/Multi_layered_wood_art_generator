"""Vector-preserving DXF to SVG conversion for buyer release files."""

from __future__ import annotations

from pathlib import Path
import math
import re
import xml.etree.ElementTree as ET

import ezdxf
from ezdxf import bbox, path as ezpath

from release_tools.run_facts import MM_INSUNITS, ReleaseValidationError, dxf_dimensions_mm


SUPPORTED_ENTITIES = frozenset({"LWPOLYLINE", "POLYLINE", "LINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE"})
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NAMESPACE)


def dxf_to_svg(source: str | Path, destination: str | Path, *, flattening_mm: float = 0.01) -> dict[str, float]:
    """Convert supported DXF modelspace entities into a transparent, mm-scaled SVG."""
    source_path, destination_path = Path(source), Path(destination)
    try:
        document = ezdxf.readfile(source_path)
    except Exception as exc:
        raise ReleaseValidationError(f"Cannot read DXF {source_path.name}: {exc}") from exc
    if document.header.get("$INSUNITS", 0) != MM_INSUNITS:
        raise ReleaseValidationError(f"{source_path.name} must explicitly use millimeters ($INSUNITS=4).")
    modelspace = document.modelspace()
    entities = list(modelspace)
    if not entities:
        raise ReleaseValidationError(f"DXF {source_path.name} has no modelspace geometry.")
    unsupported = sorted({entity.dxftype() for entity in entities if entity.dxftype() not in SUPPORTED_ENTITIES})
    if unsupported:
        raise ReleaseValidationError(f"{source_path.name} contains unsupported modelspace entities: {', '.join(unsupported)}.")
    try:
        extents = bbox.extents(modelspace, fast=False)
    except Exception as exc:
        raise ReleaseValidationError(f"Cannot measure DXF {source_path.name}: {exc}") from exc
    if not extents.has_data:
        raise ReleaseValidationError(f"DXF {source_path.name} has no measurable modelspace geometry.")
    min_x, min_y = float(extents.extmin.x), float(extents.extmin.y)
    max_x, max_y = float(extents.extmax.x), float(extents.extmax.y)
    width, height = max_x - min_x, max_y - min_y
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ReleaseValidationError(f"DXF {source_path.name} has invalid geometry extents.")

    root = ET.Element(_svg_tag("svg"), {
        "width": f"{_number(width)}mm",
        "height": f"{_number(height)}mm",
        "viewBox": f"0 0 {_number(width)} {_number(height)}",
        "version": "1.1",
    })
    for entity in entities:
        try:
            vector_path = ezpath.make_path(entity)
            points = list(vector_path.flattening(flattening_mm))
        except Exception as exc:
            raise ReleaseValidationError(f"Cannot convert {entity.dxftype()} in {source_path.name}: {exc}") from exc
        if len(points) < 2:
            raise ReleaseValidationError(f"Cannot convert degenerate {entity.dxftype()} in {source_path.name}.")
        commands = [f"M {_number(points[0].x - min_x)} {_number(max_y - points[0].y)}"]
        commands.extend(f"L {_number(point.x - min_x)} {_number(max_y - point.y)}" for point in points[1:])
        if vector_path.is_closed:
            commands.append("Z")
        ET.SubElement(root, _svg_tag("path"), {
            "d": " ".join(commands),
            "fill": "none",
            "stroke": "#000000",
            "stroke-width": "0.1",
        })
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination_path, encoding="utf-8", xml_declaration=True)
    validate_svg(destination_path, source_path)
    return {"width_mm": width, "height_mm": height}


def validate_svg(svg_path: str | Path, source_dxf: str | Path | None = None, *, tolerance_mm: float = 0.05) -> dict[str, float]:
    """Validate SVG safety, vector content, and optional source-DXF physical size."""
    path = Path(svg_path)
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ReleaseValidationError(f"Invalid SVG {path.name}: {exc}") from exc
    width = _parse_mm(root.get("width"), path.name)
    height = _parse_mm(root.get("height"), path.name)
    view_box = (root.get("viewBox") or "").split()
    if len(view_box) != 4:
        raise ReleaseValidationError(f"SVG {path.name} must have a finite four-value viewBox.")
    try:
        view_width, view_height = float(view_box[2]), float(view_box[3])
    except ValueError as exc:
        raise ReleaseValidationError(f"SVG {path.name} has an invalid viewBox.") from exc
    if not all(math.isfinite(value) and value > 0 for value in (width, height, view_width, view_height)):
        raise ReleaseValidationError(f"SVG {path.name} has non-positive or non-finite dimensions.")
    tags = [element.tag.rsplit("}", 1)[-1] for element in root.iter()]
    if not any(tag in {"path", "circle", "ellipse", "line", "polyline", "polygon"} for tag in tags):
        raise ReleaseValidationError(f"SVG {path.name} contains no vector geometry.")
    forbidden = {"image", "script", "foreignObject"}
    if forbidden.intersection(tags) or any("href" in attribute for element in root.iter() for attribute in element.attrib):
        raise ReleaseValidationError(f"SVG {path.name} contains prohibited raster, script, or external-link content.")
    if source_dxf is not None:
        expected_width, expected_height = dxf_dimensions_mm(Path(source_dxf))
        if abs(width - expected_width) > tolerance_mm or abs(height - expected_height) > tolerance_mm:
            raise ReleaseValidationError(f"SVG {path.name} dimensions do not match {Path(source_dxf).name}.")
    return {"width_mm": width, "height_mm": height, "view_width": view_width, "view_height": view_height}


def validate_matching_canvases(svg_paths: list[Path], *, tolerance_mm: float = 0.05) -> None:
    if not svg_paths:
        return
    baseline = validate_svg(svg_paths[0])
    for path in svg_paths[1:]:
        candidate = validate_svg(path)
        if any(abs(candidate[key] - baseline[key]) > tolerance_mm for key in ("width_mm", "height_mm", "view_width", "view_height")):
            raise ReleaseValidationError(f"SVG canvas mismatch: {path.name} differs from {svg_paths[0].name}.")


def _svg_tag(name: str) -> str:
    return f"{{{SVG_NAMESPACE}}}{name}"


def _number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _parse_mm(value: str | None, filename: str) -> float:
    match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))mm\s*", value or "")
    if not match:
        raise ReleaseValidationError(f"SVG {filename} width and height must use millimeters.")
    return float(match.group(1))