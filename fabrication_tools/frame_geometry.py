"""Shared first-layer frame geometry for fabrication exports."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


FRAME_GEOMETRY_FILENAME = "frame_geometry.json"
FRAME_SHAPES = ("rectangle", "first_layer")
OUTER_WEB_MM = 0.5


def parse_size_in(value: str | None) -> tuple[float, float] | None:
    if value is None:
        return None
    import re

    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*", value
    )
    if not match:
        raise ValueError("Final outer frame size must use WxH format such as 10x16.")
    width = float(match.group(1)) * 25.4
    height = float(match.group(2)) * 25.4
    if width <= 0 or height <= 0:
        raise ValueError("Final outer frame size values must be greater than zero.")
    return width, height


def extract_first_layer_silhouette(
    first_cumulative: np.ndarray,
    min_area_fraction: float = 0.00005,
    frame_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Return one filled, enclosed void from the first cumulative safe zone."""
    if first_cumulative.ndim != 2:
        raise ValueError("The first cumulative layer must be a grayscale mask.")

    void = (first_cumulative == 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(void, connectivity=8)
    min_area = max(1, int(round(void.size * min_area_fraction)))
    candidates: list[int] = []
    border_components: list[int] = []
    height, width = void.shape

    for component in range(1, count):
        area = int(stats[component, cv2.CC_STAT_AREA])
        if area <= min_area:
            continue
        x = int(stats[component, cv2.CC_STAT_LEFT])
        y = int(stats[component, cv2.CC_STAT_TOP])
        w = int(stats[component, cv2.CC_STAT_WIDTH])
        h = int(stats[component, cv2.CC_STAT_HEIGHT])
        touches_generator_frame = False
        if frame_mask is not None:
            if frame_mask.shape != void.shape:
                raise ValueError("Generator frame and first cumulative layer dimensions differ.")
            component_mask = (labels == component).astype(np.uint8)
            expanded = cv2.dilate(component_mask, np.ones((3, 3), np.uint8))
            touches_generator_frame = bool(np.any((expanded > 0) & (frame_mask > 0)))
        if (
            x <= 0
            or y <= 0
            or x + w >= width
            or y + h >= height
            or touches_generator_frame
        ):
            border_components.append(component)
        else:
            candidates.append(component)

    guidance = (
        "First-layer frame requires one clean enclosed trace. Make the background "
        "the dominant color so it is selected first, or use the rectangular frame."
    )
    if border_components:
        raise ValueError(f"The first selected trace touches the image boundary. {guidance}")
    if len(candidates) != 1:
        raise ValueError(
            f"Found {len(candidates)} meaningful enclosed traces in the first layer. {guidance}"
        )

    component_mask = (labels == candidates[0]).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if len(contours) != 1 or len(contours[0]) < 3:
        raise ValueError(guidance)

    filled = np.zeros_like(component_mask)
    cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
    return filled


def _silhouette_contour(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if len(contours) != 1 or len(contours[0]) < 3:
        raise ValueError("First-layer silhouette did not produce one valid outer contour.")
    return contours[0].reshape(-1, 2).astype(float)


def _polygon_from_contour(points_px: np.ndarray, mm_per_px: float):
    try:
        from shapely.geometry import Polygon
    except ImportError as exc:
        raise ImportError(
            "Shapely is required for first-layer frames. Install project requirements."
        ) from exc

    points_mm = [(float(x) * mm_per_px, -float(y) * mm_per_px) for x, y in points_px]
    polygon = Polygon(points_mm)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.geom_type != "Polygon" or polygon.is_empty:
        raise ValueError("First-layer trace could not be converted into one valid polygon.")
    return polygon


def _choose_quadrant_holes(inner, outer, inset_mm: float, diameter_mm: float):
    from shapely.geometry import Point

    radius = diameter_mm / 2.0
    center_distance = inset_mm + radius
    center_path_polygon = inner.buffer(center_distance, join_style=1)
    center_path = center_path_polygon.exterior
    safe_outer = outer.buffer(-OUTER_WEB_MM)
    minx, miny, maxx, maxy = outer.bounds
    center_x = (inner.bounds[0] + inner.bounds[2]) / 2.0
    center_y = (inner.bounds[1] + inner.bounds[3]) / 2.0
    targets = [
        (minx, maxy),
        (maxx, maxy),
        (minx, miny),
        (maxx, miny),
    ]
    quadrants: list[list[tuple[float, float, float]]] = [[], [], [], []]
    sample_count = max(720, int(math.ceil(center_path.length * 8.0)))

    for index in range(sample_count):
        point = center_path.interpolate(index / sample_count, normalized=True)
        if point.x == center_x or point.y == center_y:
            continue
        quadrant = (0 if point.y > center_y else 2) + (1 if point.x > center_x else 0)
        circle = point.buffer(radius, quad_segs=24)
        if not safe_outer.covers(circle):
            continue
        if circle.distance(inner) + 0.05 < inset_mm:
            continue
        target_x, target_y = targets[quadrant]
        score = (point.x - target_x) ** 2 + (point.y - target_y) ** 2
        quadrants[quadrant].append((score, float(point.x), float(point.y)))

    for candidates in quadrants:
        candidates.sort(key=lambda item: item[0])
        del candidates[80:]
        if not candidates:
            raise ValueError(
                "Could not place one alignment hole in every frame quadrant. "
                "Increase the frame margin or use the rectangular frame."
            )

    chosen: list[tuple[float, float]] = []

    def choose(quadrant: int) -> bool:
        if quadrant == 4:
            return True
        for _, x, y in quadrants[quadrant]:
            if all(math.hypot(x - ox, y - oy) >= diameter_mm + OUTER_WEB_MM for ox, oy in chosen):
                chosen.append((x, y))
                if choose(quadrant + 1):
                    return True
                chosen.pop()
        return False

    if not choose(0):
        raise ValueError(
            "Could not find four non-overlapping alignment-hole positions on the shaped frame."
        )
    return chosen


def build_first_layer_frame_geometry(
    silhouette_mask: np.ndarray,
    source_color_id: int,
    frame_margin_mm: float,
    setting_hole_inset_mm: float,
    setting_hole_diameter_mm: float,
    base_dpi: float = 300.0,
    requested_size_in: str | None = None,
) -> dict[str, Any]:
    if base_dpi <= 0:
        raise ValueError("DXF DPI must be greater than zero.")
    values = (frame_margin_mm, setting_hole_inset_mm, setting_hole_diameter_mm)
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Frame margin and setting-hole values must be positive.")

    points_px = _silhouette_contour(silhouette_mask)
    min_px = points_px.min(axis=0)
    max_px = points_px.max(axis=0)
    width_px = max(1.0, float(max_px[0] - min_px[0]))
    height_px = max(1.0, float(max_px[1] - min_px[1]))
    effective_offset = max(
        frame_margin_mm,
        setting_hole_inset_mm + setting_hole_diameter_mm + OUTER_WEB_MM,
    )

    target_mm = parse_size_in(requested_size_in)
    if target_mm is None:
        mm_per_px = 25.4 / base_dpi
    else:
        available_width = target_mm[0] - 2.0 * effective_offset
        available_height = target_mm[1] - 2.0 * effective_offset
        if available_width <= 0 or available_height <= 0:
            raise ValueError(
                "Requested final size is too small for the shaped-frame offset and holes."
            )
        mm_per_px = min(available_width / width_px, available_height / height_px)
    resolved_dpi = 25.4 / mm_per_px

    inner = _polygon_from_contour(points_px, mm_per_px)
    outer = inner.buffer(effective_offset, join_style=1)
    if outer.geom_type != "Polygon" or outer.is_empty:
        raise ValueError("The offset frame did not produce one valid outer polygon.")
    holes = _choose_quadrant_holes(
        inner, outer, setting_hole_inset_mm, setting_hole_diameter_mm
    )

    outer_min_x, outer_min_y, outer_max_x, outer_max_y = outer.bounds
    translate_x = -outer_min_x
    translate_y = -outer_min_y

    def translated_points(ring) -> list[list[float]]:
        return [
            [float(x + translate_x), float(y + translate_y)]
            for x, y in list(ring.coords)[:-1]
        ]

    width_mm = outer_max_x - outer_min_x
    height_mm = outer_max_y - outer_min_y
    canvas_width = max(2, int(math.ceil(width_mm / mm_per_px)) + 1)
    canvas_height = max(2, int(math.ceil(height_mm / mm_per_px)) + 1)
    source_tx = translate_x / mm_per_px
    source_ty = height_mm / mm_per_px + outer_min_y / mm_per_px

    return {
        "schema_version": 1,
        "frame_shape": "first_layer",
        "source_layer_index": 0,
        "source_color_id": int(source_color_id),
        "requested_size_in": requested_size_in,
        "requested_frame_margin_mm": float(frame_margin_mm),
        "effective_offset_mm": float(effective_offset),
        "setting_hole_inset_mm": float(setting_hole_inset_mm),
        "setting_hole_diameter_mm": float(setting_hole_diameter_mm),
        "outer_web_mm": OUTER_WEB_MM,
        "dpi": float(resolved_dpi),
        "dpi_x": float(resolved_dpi),
        "dpi_y": float(resolved_dpi),
        "mm_per_px": float(mm_per_px),
        "actual_width_mm": float(width_mm),
        "actual_height_mm": float(height_mm),
        "inner_outline_mm": translated_points(inner.exterior),
        "outer_outline_mm": translated_points(outer.exterior),
        "hole_centers_mm": [
            [float(x + translate_x), float(y + translate_y)] for x, y in holes
        ],
        "raster": {
            "width_px": canvas_width,
            "height_px": canvas_height,
            "source_translate_x_px": float(source_tx),
            "source_translate_y_px": float(source_ty),
        },
    }


def outline_mm_to_raster_points(geometry: dict[str, Any]) -> np.ndarray:
    mm_per_px = float(geometry["mm_per_px"])
    height_px = int(geometry["raster"]["height_px"])
    points = []
    for x_mm, y_mm in geometry["outer_outline_mm"]:
        points.append(
            [int(round(x_mm / mm_per_px)), int(round((height_px - 1) - y_mm / mm_per_px))]
        )
    return np.asarray(points, dtype=np.int32)


def rasterize_outer_frame(geometry: dict[str, Any]) -> np.ndarray:
    raster = geometry["raster"]
    mask = np.zeros((int(raster["height_px"]), int(raster["width_px"])), dtype=np.uint8)
    points = outline_mm_to_raster_points(geometry)
    cv2.fillPoly(mask, [points], 255)
    return mask


def transform_and_clip_mask(mask: np.ndarray, geometry: dict[str, Any]) -> np.ndarray:
    raster = geometry["raster"]
    matrix = np.asarray(
        [
            [1.0, 0.0, float(raster["source_translate_x_px"])],
            [0.0, 1.0, float(raster["source_translate_y_px"])],
        ],
        dtype=np.float32,
    )
    transformed = cv2.warpAffine(
        mask,
        matrix,
        (int(raster["width_px"]), int(raster["height_px"])),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return cv2.bitwise_and(transformed, rasterize_outer_frame(geometry))


def save_frame_geometry(directory: str | Path, geometry: dict[str, Any]) -> Path:
    path = Path(directory) / FRAME_GEOMETRY_FILENAME
    path.write_text(json.dumps(geometry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_frame_geometry(directory_or_path: str | Path) -> dict[str, Any]:
    path = Path(directory_or_path)
    if path.is_dir():
        path = path / FRAME_GEOMETRY_FILENAME
    try:
        geometry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load shaped frame geometry from {path}: {exc}") from exc
    if geometry.get("frame_shape") != "first_layer":
        raise ValueError(f"Unsupported frame geometry in {path}.")
    return geometry
