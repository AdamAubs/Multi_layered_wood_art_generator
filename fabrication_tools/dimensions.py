"""Persist physical bounds measured from the exported cutting geometry."""
import json
import math
from pathlib import Path

import ezdxf
from ezdxf import bbox


def write_dimensions_report(final_dir, requested_size_in=None, frame_shape="rectangle"):
    directory = Path(final_dir)
    layers = []
    for path in sorted(directory.glob("Layer_*.dxf")):
        doc = ezdxf.readfile(path)
        if doc.units != 4:
            raise ValueError(f"Cannot measure {path.name}: expected millimeter DXF units.")
        bounds = bbox.extents(doc.modelspace())
        if not bounds.has_data:
            raise ValueError(f"Cannot measure empty cutting file: {path.name}")
        width, height = bounds.size.x, bounds.size.y
        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
            raise ValueError(f"Invalid cutting bounds: {path.name}")
        layers.append({"file": path.name, "width_mm": width, "height_mm": height})
    if not layers:
        raise ValueError("No exported Layer_*.dxf files found to measure.")
    settings_path = directory / "fabrication_settings.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    report = {
        "version": 1,
        "warnings": settings.get("warnings", []),
        "measurement": "Exported DXF geometry bounds, in millimeters",
        "requested_size_in": requested_size_in,
        "frame_shape": frame_shape,
        "width_mm": max(layer["width_mm"] for layer in layers),
        "height_mm": max(layer["height_mm"] for layer in layers),
        "layers": layers,
    }
    (directory / "dimensions.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
