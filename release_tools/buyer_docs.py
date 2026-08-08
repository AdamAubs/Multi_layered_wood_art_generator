"""Buyer-facing release documents and file manifests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from release_tools.run_facts import INCHES_PER_MM, ReleaseFacts, sha256_file


# This business-policy template is not legal advice.
LICENSE_TEXT = """SMALL COMMERCIAL LICENSE

The original purchaser may use these digital files for personal projects. The original purchaser, or one business owned by that purchaser, may make and sell up to 100 finished physical products total per purchase.

The digital files, and modified, traced, converted, or derivative digital versions, may not be sold, shared, gifted, sublicensed, uploaded, or redistributed. Print-on-demand, digital-template resale, and mass production are excluded. This license is non-transferable; copyright remains with the seller.

For an extended license, contact the Etsy seller.
"""


def write_buyer_documents(package_dir: Path, facts: ReleaseFacts, release_version: str) -> None:
    package_dir.joinpath("READ_ME_FIRST.txt").write_text(_readme(facts, release_version), encoding="utf-8")
    package_dir.joinpath("LICENSE.txt").write_text(LICENSE_TEXT, encoding="utf-8")


def write_manifest(package_dir: Path, facts: ReleaseFacts, release_version: str) -> None:
    entries = []
    for path in sorted(package_dir.rglob("*")):
        if path.is_file() and path.name != "FILE_MANIFEST.txt":
            relative = path.relative_to(package_dir).as_posix()
            entries.append(f"{relative} | {path.stat().st_size} | {sha256_file(path)} | {_purpose(relative)}")
    width_mm, height_mm = facts.dimensions_mm
    header = [
        "FILE MANIFEST",
        f"Release version: {release_version}",
        f"Build timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"Visible artwork layers: {len(facts.art_layers)}",
        f"Optional mounting layers: {len(facts.cleat_layers)}",
        f"Total delivered layers: {len(facts.layers)}",
        f"Outside dimensions: {width_mm:.3f} x {height_mm:.3f} mm ({width_mm * INCHES_PER_MM:.3f} x {height_mm * INCHES_PER_MM:.3f} in)",
        "Units: millimeters",
        f"French-cleat layers included: {'yes' if facts.cleat_layers else 'no'}",
        "Combined layout: one DXF and one matching SVG with every delivered layer in a neat 10 mm-spaced grid",
        "",
        "relative path | bytes | SHA-256 | purpose",
        *entries,
        "",
    ]
    package_dir.joinpath("FILE_MANIFEST.txt").write_text("\n".join(header), encoding="utf-8")


def _readme(facts: ReleaseFacts, release_version: str) -> str:
    width_mm, height_mm = facts.dimensions_mm
    width_in, height_in = width_mm * INCHES_PER_MM, height_mm * INCHES_PER_MM
    material = "Material and thickness are not specified for this release."
    return f"""READ ME FIRST - {release_version}

This is a DIGITAL DOWNLOAD. No physical item is shipped.

WHAT IS INCLUDED
DXF_Layers contains one full-size, aligned cutting file per numbered layer.
SVG_Layers contains the same per-layer geometry and scale for software that prefers SVG.
Combined_Layout contains one full-size DXF and matching SVG with all delivered layers arranged in a neat grid with 10 mm gaps. Use the individual layer files for cutting; the combined layout is a convenient complete-design reference, not a prearranged stock-sheet file.
PNG_References/Layers contains visual references only; PNGs are not the preferred cutting source.
Assembly_References contains assembled and exploded images to understand order and orientation. They are not dimensioned cutting files.

LAYERS AND SIZE
Visible artwork layers: {len(facts.art_layers)}
Optional mounting layers: {len(facts.cleat_layers)}
Total delivered layers: {len(facts.layers)}
Finished outside dimensions from DXF geometry: {width_mm:.3f} x {height_mm:.3f} mm ({width_in:.3f} x {height_in:.3f} in).
Layer numbers run from 00 upward. Keep files at the same scale and assemble in the numbered order indicated by the assembly references.

IMPORT AND CUTTING
Import DXF or SVG layers at 100% scale and verify dimensions before cutting. Test cut first. Kerf, focus, ventilation, machine-specific settings, material, glue, finish, mounting hardware, wall fasteners, and physical products are not included. The buyer is responsible for machine settings and safe operation.

MOUNTING
French-cleat mounting layers are {'included' if facts.cleat_layers else 'not included'} in this release. Mounting hardware and wall fasteners are never included.

COMPATIBILITY
No machine or software compatibility is claimed unless the seller has explicitly confirmed it. {material}
"""


def _purpose(relative: str) -> str:
    if relative.startswith("DXF_Layers/"):
        return "full-size layer cutting DXF"
    if relative.startswith("SVG_Layers/"):
        return "full-size layer cutting SVG"
    if relative.startswith("Combined_Layout/"):
        return "all-layer combined layout"
    if relative.startswith("PNG_References/"):
        return "visual layer reference"
    if relative.startswith("Assembly_References/"):
        return "assembly reference"
    if relative == "READ_ME_FIRST.txt":
        return "buyer instructions"
    if relative == "LICENSE.txt":
        return "license"
    return "buyer file"