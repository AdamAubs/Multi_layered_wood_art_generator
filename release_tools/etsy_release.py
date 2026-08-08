"""Build an immutable Etsy buyer delivery and seller listing-media release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from preview_tools.exploded_video import render_exploded_video
from preview_tools.layer_composite import render_composite_previews
from preview_tools.layer_showcase import render_showcase_previews
from release_tools.archive import ETSY_MAX_BYTES, ETSY_MAX_FILES, ETSY_POLICY_URL, ETSY_POLICY_VERIFIED_ON, create_buyer_archives, write_upload_instructions
from release_tools.buyer_docs import write_buyer_documents, write_manifest
from release_tools.dxf_to_svg import dxf_to_svg, validate_matching_canvases
from release_tools.etsy_handoff import write_etsy_handoff
from release_tools.run_facts import ReleaseFacts, ReleaseValidationError, discover_release_facts, hash_tree


COMBINED_LAYOUT_STEM = "All_Layers_Layout"


def build_release(
    requested: str | Path,
    *,
    product_name: str | None = None,
    release_version: str = "v1.0",
    french_cleats: str = "ask",
    background_color: tuple[int, int, int] | None = None,
    ffmpeg_path: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    keep_staging: bool = False,
) -> dict[str, Any]:
    facts = discover_release_facts(requested)
    cleat_mode = _resolve_cleat_mode(french_cleats, facts)
    product_name = product_name or _default_product_name(facts)
    safe_name = _safe_name(product_name)
    release_version = _safe_name(release_version)
    destination = facts.source_final / "EtsyRelease"
    plan = {
        "source_final": "outputs/final",
        "product_name": product_name,
        "layers": [layer.stem for layer in facts.layers if cleat_mode == "include" or not layer.is_cleat],
        "french_cleats": cleat_mode,
        "combined_layout": f"{COMBINED_LAYOUT_STEM}.dxf and {COMBINED_LAYOUT_STEM}.svg (10 mm-spaced grid)",
        "destination": "outputs/final/EtsyRelease",
        "media": ["composite", "showcase", "front exploded video", "rear exploded video"],
    }
    if dry_run:
        return {"dry_run": True, "plan": plan}
    if destination.exists() and not force:
        raise ReleaseValidationError(f"{destination.name} already exists; pass --force to replace it after a successful build.")

    source_hashes = hash_tree(facts.source_final, {"EtsyRelease"})
    staging_root = Path(tempfile.mkdtemp(prefix=".EtsyRelease-build-", dir=facts.source_final))
    release_root = staging_root / "EtsyRelease"
    log_lines: list[str] = [f"Release build started: {datetime.now(timezone.utc).isoformat()}", json.dumps(plan, indent=2)]
    try:
        staged_final = staging_root / "staged_final"
        _copy_staged_sources(facts, staged_final, include_existing_cleats=cleat_mode == "include" and facts.has_valid_cleats)
        if cleat_mode == "include" and not facts.has_valid_cleats:
            _add_cleats(staged_final, log_lines)
        staged_facts = discover_release_facts(staged_final)
        if cleat_mode == "exclude" and staged_facts.cleat_layers:
            raise ReleaseValidationError("French-cleat exclusion left mounting layers in staging.")
        if cleat_mode == "include" and not staged_facts.has_valid_cleats:
            raise ReleaseValidationError("French-cleat inclusion did not produce the required three final layers.")
        release_root.mkdir()
        buyer_root = release_root / "Buyer_Download"
        package_dir = buyer_root / f"{safe_name}_{release_version}"
        package_dir.mkdir(parents=True)
        _copy_buyer_layers(staged_facts, package_dir)
        _write_layer_svgs(staged_facts, package_dir)
        _write_combined_layout(staged_facts, package_dir)
        seller_media = release_root / "Seller_Listing_Media"
        media = _render_media(staged_final, seller_media, background_color, ffmpeg_path)
        _copy_assembly_references(media, package_dir)
        write_buyer_documents(package_dir, staged_facts, release_version)
        write_manifest(package_dir, staged_facts, release_version)
        archive_details = create_buyer_archives(buyer_root, package_dir, f"{safe_name}_{release_version}")
        write_upload_instructions(buyer_root / "ETSY_UPLOAD_FILES.txt", archive_details)
        handoff_path = release_root / "ETSY_HANDOFF.md"
        write_etsy_handoff(handoff_path, staged_facts, product_name, release_version, [detail.__dict__ for detail in archive_details])
        metadata = _metadata(staged_facts, product_name, release_version, archive_details, media)
        _write_json(release_root / "etsy_release_metadata.json", metadata)
        _write_json(release_root / "validation_report.json", {"source_hashes_unchanged": True, "svg_layers": len(staged_facts.layers), "combined_layout": True, "buyer_archives": len(archive_details)})
        (release_root / "release.log").write_text("\n\n".join(log_lines) + "\n", encoding="utf-8")
        if hash_tree(facts.source_final, {"EtsyRelease", staging_root.name}) != source_hashes:
            raise ReleaseValidationError("Source final files changed during the release build; refusing to publish release.")
        _publish(staging_root, destination, force)
        published = destination
        return {
            "release_dir": str(published),
            "archives": [{"path": str(published / "Buyer_Download" / detail.name), **detail.__dict__} for detail in archive_details],
            "handoff": str(published / "ETSY_HANDOFF.md"),
            "warnings": list(staged_facts.warnings),
        }
    except Exception:
        if keep_staging:
            print(f"Build failed; retained staging directory: {staging_root}", file=sys.stderr)
        else:
            shutil.rmtree(staging_root, ignore_errors=True)
        raise


def _copy_staged_sources(facts: ReleaseFacts, staged_final: Path, *, include_existing_cleats: bool) -> None:
    staged_final.mkdir(parents=True)
    for layer in facts.layers:
        if layer.is_cleat and not include_existing_cleats:
            continue
        shutil.copy2(layer.png_path, staged_final / layer.png_path.name)
        shutil.copy2(layer.dxf_path, staged_final / layer.dxf_path.name)
    for name in ("handoff.md", "run_metadata.json"):
        source = facts.source_final / name
        if source.is_file():
            shutil.copy2(source, staged_final / name)


def _add_cleats(staged_final: Path, log_lines: list[str]) -> None:
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(root / "add_french_cleats.py"), "--dir", str(staged_final)]
    dry_run = subprocess.run([*command, "--dry-run"], cwd=root, text=True, capture_output=True)
    log_lines.append("French-cleat dry run:\n" + dry_run.stdout + dry_run.stderr)
    if dry_run.returncode:
        raise ReleaseValidationError("French-cleat dry run failed; see release log.")
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    log_lines.append("French-cleat build:\n" + result.stdout + result.stderr)
    if result.returncode:
        raise ReleaseValidationError("French-cleat generation failed; see release log.")


def _copy_buyer_layers(facts: ReleaseFacts, package_dir: Path) -> None:
    dxf_dir, png_dir = package_dir / "DXF_Layers", package_dir / "PNG_References" / "Layers"
    dxf_dir.mkdir(parents=True)
    png_dir.mkdir(parents=True)
    for layer in facts.layers:
        shutil.copy2(layer.dxf_path, dxf_dir / layer.dxf_path.name)
        shutil.copy2(layer.png_path, png_dir / layer.png_path.name)


def _write_layer_svgs(facts: ReleaseFacts, package_dir: Path) -> None:
    svg_dir = package_dir / "SVG_Layers"
    svg_dir.mkdir()
    outputs = []
    for layer in facts.layers:
        output = svg_dir / f"{layer.stem}.svg"
        dxf_to_svg(layer.dxf_path, output)
        outputs.append(output)
    validate_matching_canvases(outputs)


def _write_combined_layout(facts: ReleaseFacts, package_dir: Path) -> None:
    import ezdxf
    from ezdxf.addons import Importer
    from ezdxf import bbox

    layout_dir = package_dir / "Combined_Layout"
    layout_dir.mkdir()
    combined_dxf = layout_dir / f"{COMBINED_LAYOUT_STEM}.dxf"
    combined_doc = ezdxf.new("R2010")
    combined_doc.header["$INSUNITS"] = 4
    gap_mm = 10.0
    columns = 2
    extents = []
    for layer in facts.layers:
        source_doc = ezdxf.readfile(layer.dxf_path)
        source_extents = bbox.extents(source_doc.modelspace(), fast=False)
        if not source_extents.has_data:
            raise ReleaseValidationError(f"Cannot place empty layer in combined layout: {layer.dxf_path.name}")
        extents.append(source_extents)
    cell_width = max(float(extent.extmax.x - extent.extmin.x) for extent in extents)
    cell_height = max(float(extent.extmax.y - extent.extmin.y) for extent in extents)
    for position, (layer, source_extents) in enumerate(zip(facts.layers, extents)):
        source_doc = ezdxf.readfile(layer.dxf_path)
        importer = Importer(source_doc, combined_doc)
        importer.import_modelspace()
        importer.finalize()
        column, row = position % columns, position // columns
        offset_x = column * (cell_width + gap_mm) - float(source_extents.extmin.x)
        offset_y = row * (cell_height + gap_mm) - float(source_extents.extmin.y)
        imported_entities = list(combined_doc.modelspace())[-len(source_doc.modelspace()):]
        for entity in imported_entities:
            try:
                entity.translate(offset_x, offset_y, 0)
            except (AttributeError, TypeError) as exc:
                raise ReleaseValidationError(f"Cannot position {entity.dxftype()} in the combined layout.") from exc
    combined_doc.saveas(combined_dxf)
    _validate_combined_layout(combined_dxf, len(facts.layers))
    dxf_to_svg(combined_dxf, layout_dir / f"{COMBINED_LAYOUT_STEM}.svg")


def _validate_combined_layout(path: Path, layer_count: int) -> None:
    import ezdxf

    document = ezdxf.readfile(path)
    if document.header.get("$INSUNITS", 0) != 4 or len(document.modelspace()) < layer_count:
        raise ReleaseValidationError("Combined layout is missing modelspace geometry or millimeter units.")


def _render_media(staged_final: Path, seller_media: Path, background_color: tuple[int, int, int] | None, ffmpeg_path: str | None) -> dict[str, Any]:
    seller_media.mkdir(parents=True)
    color = background_color or (245, 242, 236)
    composite = render_composite_previews(str(staged_final), output_dir=str(seller_media), background_color=color, force=True)
    showcase = render_showcase_previews(str(staged_final), output_dir=str(seller_media / "showcase"), background_color=color, force=True)
    animation = render_exploded_video(str(staged_final), preset="etsy", view="both", output_dir=str(seller_media / "animation"), background_color=color, ffmpeg_path=ffmpeg_path, force=True)
    return {"composite": composite, "showcase": showcase, "animation": animation}


def _copy_assembly_references(media: dict[str, Any], package_dir: Path) -> None:
    assembly = package_dir / "Assembly_References"
    assembly.mkdir()
    shutil.copy2(media["composite"]["transparent_path"], assembly / "assembled_composite.png")
    views = media["animation"]["views"]
    shutil.copy2(views["front"]["poster_path"], assembly / "exploded_front.png")
    shutil.copy2(views["rear"]["poster_path"], assembly / "exploded_rear.png")


def _metadata(facts: ReleaseFacts, product_name: str, release_version: str, archives: list[Any], media: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tool": "release_tools.etsy_release",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": facts.public_dict(),
        "selection": {"visible_art_layers": len(facts.art_layers), "mounting_layers": len(facts.cleat_layers), "total_layers": len(facts.layers), "combined_layout": f"{COMBINED_LAYOUT_STEM}.dxf and {COMBINED_LAYOUT_STEM}.svg (10 mm-spaced grid)"},
        "dimensions": {"mm": facts.dimensions_mm, "source_png_pixels": facts.source_pixels, "dpi": facts.dpi},
        "buyer_files": [detail.__dict__ for detail in archives],
        "seller_media": {"animation_duration_sec": media["animation"]["duration_sec"], "animation_resolution": media["animation"]["resolution"]},
        "license": {"physical_product_limit": 100},
        "etsy_policy": {"max_files": ETSY_MAX_FILES, "max_bytes_per_file": ETSY_MAX_BYTES, "source_url": ETSY_POLICY_URL, "verified_on": ETSY_POLICY_VERIFIED_ON},
        "warnings": list(facts.warnings),
        "validation": {"combined_layout": True, "release_name": product_name, "release_version": release_version},
    }


def _publish(staging_root: Path, destination: Path, force: bool) -> None:
    built_release = staging_root / "EtsyRelease"
    if not destination.exists():
        built_release.replace(destination)
        shutil.rmtree(staging_root, ignore_errors=True)
        return
    if not force:
        raise ReleaseValidationError(f"{destination} already exists.")
    backup = destination.with_name(f".EtsyRelease-previous-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    destination.replace(backup)
    try:
        built_release.replace(destination)
    except Exception:
        backup.replace(destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    shutil.rmtree(staging_root, ignore_errors=True)


def _resolve_cleat_mode(value: str, facts: ReleaseFacts) -> str:
    if value in {"include", "exclude"}:
        return value
    if not sys.stdin.isatty():
        raise ReleaseValidationError("--french-cleats ask requires an interactive terminal; pass --french-cleats include or exclude.")
    default_yes = facts.has_valid_cleats
    prompt = "French-cleat layers were found. Include them in this release? [Y/n] " if default_yes else "Add the optional French-cleat mounting layers? [y/N] "
    answer = input(prompt).strip().lower()
    return "include" if (answer in {"y", "yes"} or (not answer and default_yes)) else "exclude"


def _default_product_name(facts: ReleaseFacts) -> str:
    return (facts.project_id or facts.source_final.parent.parent.name).replace("-", " ").replace("_", " ").title()


def _safe_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip().replace(" ", "_"))
    clean = clean.strip("._-")[:55]
    if not clean:
        raise ReleaseValidationError("Product name must contain letters or numbers.")
    return clean


def _parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        raise argparse.ArgumentTypeError("background color must be #RRGGBB")
    return tuple(int(value[offset : offset + 2], 16) for offset in (0, 2, 4))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package a completed layer run as an Etsy-ready release.")
    parser.add_argument("run_or_final", help="Completed run directory or final layer directory")
    parser.add_argument("--product-name")
    parser.add_argument("--release-version", default="v1.0")
    parser.add_argument("--french-cleats", choices=("ask", "include", "exclude"), default="ask")
    parser.add_argument("--background-color", type=_parse_color)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-staging", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build_release(args.run_or_final, product_name=args.product_name, release_version=args.release_version, french_cleats=args.french_cleats, background_color=args.background_color, ffmpeg_path=args.ffmpeg, dry_run=args.dry_run, force=args.force, keep_staging=args.keep_staging)
    except (OSError, RuntimeError, ReleaseValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if result.get("dry_run"):
        print(json.dumps(result["plan"], indent=2))
        return 0
    for archive in result["archives"]:
        print(f"Buyer ZIP: {archive['path']} ({archive['size']} bytes)")
    print(f"Seller handoff: {result['handoff']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())