import argparse
from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np


LAYER_FILE_RE = re.compile(
    r"^Layer_(\d{2})_(.+)\.(png|dxf)$",
    re.IGNORECASE,
)


@dataclass
class LayerRecord:
    index: int
    label: str
    png_path: str
    dxf_path: str


def parse_args():
    parser = argparse.ArgumentParser(
        description="Add a French cleat / keyhole feature to the back layers of a final package."
    )
    parser.add_argument(
        "--dir",
        default=".",
        help=(
            "Path to a finalized layer directory, or to a run directory "
            "containing outputs/final."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the planned layer changes without writing files.",
    )
    parser.add_argument(
        "--max-added-layers",
        type=int,
        default=3,
        help="Total cleat layers to append (minimum 3: backing, cavity, keyhole).",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=300.0,
        help="DPI used to convert mm dimensions into PNG pixels.",
    )
    parser.add_argument(
        "--top-inset-mm",
        type=float,
        default=10.0,
        help="Inset from the top edge to the top of the throat.",
    )
    parser.add_argument(
        "--entry-diameter-mm",
        type=float,
        default=10.5,
        help="Diameter of the keyhole entry circle in mm.",
    )
    parser.add_argument(
        "--throat-width-mm",
        type=float,
        default=5.0,
        help="Width of the keyhole throat in mm.",
    )
    parser.add_argument(
        "--throat-height-mm",
        type=float,
        default=10.0,
        help="Height of the keyhole throat in mm.",
    )
    parser.add_argument(
        "--cavity-width-mm",
        type=float,
        default=12.0,
        help="Width of the clearance cavity in mm.",
    )
    parser.add_argument(
        "--cavity-extension-mm",
        type=float,
        default=3.0,
        help="Extra height added above and below the clearance cavity in mm.",
    )
    parser.add_argument(
        "--collision-padding-mm",
        type=float,
        default=0.0,
        help="Optional padding applied to the proposed cleat shape for collision checks.",
    )
    parser.add_argument(
        "--frame-margin-mm",
        type=float,
        default=5.0,
        help="Frame margin passed through to DXF regeneration.",
    )
    parser.add_argument(
        "--setting-hole-diameter-mm",
        type=float,
        default=2.5,
        help="Setting-hole diameter passed through to DXF regeneration.",
    )
    parser.add_argument(
        "--setting-hole-inset-mm",
        type=float,
        default=7.0,
        help="Setting-hole inset passed through to DXF regeneration.",
    )
    parser.add_argument(
        "--stock-size-in",
        default=None,
        help="Optional stock sheet size in inches as WxH (e.g. 12x20). When provided, the layout-cut-generator will be refreshed after changes.",
    )
    parser.add_argument(
        "--layout-gap-mm",
        type=float,
        default=5.0,
        help="Gap in mm to use when generating combined stock layout DXFs.",
    )
    return parser.parse_args()


def contains_layer_pngs(directory):
    if not os.path.isdir(directory):
        return False

    for name in os.listdir(directory):
        match = LAYER_FILE_RE.match(name)
        if match and match.group(3).lower() == "png":
            return True

    return False


def ensure_final_package(directory):
    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        raise FileNotFoundError(f"Directory not found: {abs_dir}")

    candidates = [abs_dir]
    if os.path.basename(abs_dir) == "outputs":
        candidates.append(os.path.join(abs_dir, "final"))
    candidates.append(os.path.join(abs_dir, "outputs", "final"))

    for candidate in candidates:
        if contains_layer_pngs(candidate):
            return os.path.abspath(candidate)

    raise ValueError(
        "Could not find a finalized layer package. Pass either a directory "
        "containing Layer_XX_*.png files or a run directory containing "
        f"outputs/final: {abs_dir}"
    )


def load_layers(directory):
    layers = []
    for name in os.listdir(directory):
        match = LAYER_FILE_RE.match(name)
        if not match or match.group(3).lower() != "png":
            continue
        if match.group(2).startswith("french_cleat_"):
            continue
        index = int(match.group(1))
        label = match.group(2)
        png_path = os.path.join(directory, name)
        dxf_path = os.path.join(directory, f"Layer_{index:02d}_{label}.dxf")
        layers.append(LayerRecord(index=index, label=label, png_path=png_path, dxf_path=dxf_path))

    layers.sort(key=lambda layer: layer.index)
    if not layers:
        raise FileNotFoundError(f"No Layer_XX_*.png files found in {directory}")
    return layers


def mm_to_px(value_mm, dpi):
    return int(round(value_mm * dpi / 25.4))


def load_image_mask(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    if img.ndim == 2:
        return (img > 0).astype(np.uint8)
    if img.ndim == 3:
        if img.shape[2] == 4:
            return (img[:, :, 3] > 0).astype(np.uint8)
        return (np.any(img > 0, axis=2)).astype(np.uint8)
    raise ValueError(f"Unsupported image shape for {image_path}: {img.shape}")


def ensure_bgra(image):
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)

    if image.ndim != 3:
        raise ValueError(f"Unsupported image shape: {image.shape}")

    channels = image.shape[2]
    if channels == 4:
        return image.copy()
    if channels == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    if channels == 1:
        return cv2.cvtColor(image[:, :, 0], cv2.COLOR_GRAY2BGRA)

    raise ValueError(
        "Unsupported image channel count: "
        f"expected 1, 3, or 4 channels, got {image.shape}"
    )


def load_color_image(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    return ensure_bgra(img)


def build_keyhole_mask(shape, args):
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)

    top = mm_to_px(args.top_inset_mm, args.dpi)
    entry_radius = mm_to_px(args.entry_diameter_mm / 2.0, args.dpi)
    throat_width = max(1, mm_to_px(args.throat_width_mm, args.dpi))
    throat_height = max(1, mm_to_px(args.throat_height_mm, args.dpi))

    center_x = width // 2
    circle_center_y = top + throat_height + entry_radius
    throat_left = max(0, center_x - throat_width // 2)
    throat_right = min(width - 1, throat_left + throat_width)
    throat_top = max(0, top)
    throat_bottom = min(height - 1, top + throat_height)

    if throat_top >= throat_bottom:
        raise ValueError("Keyhole throat does not fit within the image height.")
    if circle_center_y + entry_radius >= height:
        raise ValueError("Keyhole entry circle does not fit within the image height.")

    cv2.rectangle(mask, (throat_left, throat_top), (throat_right, throat_bottom), 255, thickness=-1)
    cv2.circle(mask, (center_x, circle_center_y), entry_radius, 255, thickness=-1)
    return mask


def build_cavity_mask(shape, args):
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)

    top = mm_to_px(args.top_inset_mm, args.dpi)
    entry_radius = mm_to_px(args.entry_diameter_mm / 2.0, args.dpi)
    throat_height = max(1, mm_to_px(args.throat_height_mm, args.dpi))
    cavity_width = max(1, mm_to_px(args.cavity_width_mm, args.dpi))
    cavity_extension = max(1, mm_to_px(args.cavity_extension_mm, args.dpi))

    center_x = width // 2
    circle_center_y = top + throat_height + entry_radius
    cavity_top = max(0, top - cavity_extension)
    cavity_bottom = min(height - 1, circle_center_y + entry_radius + cavity_extension)
    radius = max(1, cavity_width // 2)

    if cavity_top >= cavity_bottom:
        raise ValueError("Clearance cavity does not fit within the image height.")

    cv2.rectangle(
        mask,
        (max(0, center_x - radius), cavity_top),
        (min(width - 1, center_x + radius), cavity_bottom),
        255,
        thickness=-1,
    )
    cv2.circle(mask, (center_x, cavity_top), radius, 255, thickness=-1)
    cv2.circle(mask, (center_x, cavity_bottom), radius, 255, thickness=-1)
    return mask


def pad_mask(mask, padding_px):
    if padding_px <= 0:
        return mask
    kernel_size = padding_px * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    return cv2.dilate(mask, kernel, iterations=1)


def overlaps(layer_mask, proposal_mask, padding_px):
    if layer_mask.shape != proposal_mask.shape:
        raise ValueError("Layer mask and proposal mask shapes do not match.")
    proposal = pad_mask(proposal_mask, padding_px)
    return bool(np.any((layer_mask > 0) & (proposal > 0)))


def write_png(image, path):
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError(
            "French cleat layer images must be BGRA with 4 channels: "
            f"{path} has shape {image.shape}"
        )

    ok = cv2.imwrite(path, image)
    if not ok:
        raise OSError(f"Failed to write image: {path}")


def remove_existing_french_cleat_files(directory):
    removed = []
    for name in os.listdir(directory):
        match = LAYER_FILE_RE.match(name)
        if not match:
            continue
        if not match.group(2).startswith("french_cleat_"):
            continue
        path = os.path.join(directory, name)
        try:
            os.remove(path)
            removed.append(name)
        except OSError:
            pass
    return removed


def regenerate_dxf(png_path, args):
    return regenerate_dxf_with_frame(png_path, args)


def regenerate_dxf_with_frame(png_path, args):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "png-to-dxf.py")
    command = [
        sys.executable,
        script_path,
        "--png",
        png_path,
        "--dpi",
        f"{args.dpi}",
        "--frame-margin-mm",
        f"{args.frame_margin_mm}",
        "--setting-hole-diameter-mm",
        f"{args.setting_hole_diameter_mm}",
        "--setting-hole-inset-mm",
        f"{args.setting_hole_inset_mm}",
    ]
    subprocess.run(command, check=True)


def infer_layout_refresh_config(final_dir):
    metadata_path = os.path.join(final_dir, "layout-cut-generator_metadata.json")
    if not os.path.exists(metadata_path):
        return None
    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        stock_mm = metadata.get("stock_mm")
        if not (isinstance(stock_mm, list) and len(stock_mm) == 2):
            return None
        stock_w_in = float(stock_mm[0]) / 25.4
        stock_h_in = float(stock_mm[1]) / 25.4
        gap_mm = float(metadata.get("gap_mm", 5.0))
        return f"{stock_w_in:g}x{stock_h_in:g}", gap_mm
    except Exception:
        return None


def refresh_layout_cut_generator(final_dir, stock_size_in, gap_mm):
    layout_script = os.path.join(os.path.dirname(__file__), "layout_cut_generator.py")
    layout_cmd = [
        sys.executable,
        layout_script,
        "--dir",
        final_dir,
        "--stock-size-in",
        stock_size_in,
        "--gap-mm",
        str(gap_mm),
    ]
    print("Refreshing layout-cut-generator DXFs...")
    result = subprocess.run(layout_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(f"Warning: layout cut generator refresh failed with exit code {result.returncode}")
    return result.returncode


def update_handoff(directory, added_layers, keyhole_layer, cavity_layer, args):
    handoff_path = os.path.join(directory, "handoff.md")
    if not os.path.exists(handoff_path):
        return

    def layer_get(layer, key):
        if isinstance(layer, dict):
            return layer[key]
        return getattr(layer, key)

    with open(handoff_path, "r", encoding="utf-8") as handle:
        text = handle.read()

    total_layers_match = re.search(r"(- Layers \(final\): )(\d+)", text)
    if total_layers_match:
        current_total = int(total_layers_match.group(2))
        new_total = current_total + added_layers
        text = re.sub(
            r"(- Layers \(final\): )\d+",
            lambda match: f"{match.group(1)}{new_total}",
            text,
            count=1,
        )

    cleat_section = [
        "## French Cleat",
        f"- Keyhole layer: Layer_{layer_get(keyhole_layer, 'index'):02d}_{layer_get(keyhole_layer, 'label')}",
        f"- Clearance layer: Layer_{layer_get(cavity_layer, 'index'):02d}_{layer_get(cavity_layer, 'label')}",
        f"- Added blank layers: {added_layers}",
        f"- Entry diameter: {args.entry_diameter_mm:.2f} mm",
        f"- Throat width: {args.throat_width_mm:.2f} mm",
        f"- Cavity width: {args.cavity_width_mm:.2f} mm",
    ]
    cleat_text = "\n".join(cleat_section) + "\n"

    existing_section = re.compile(r"\n## French Cleat\n.*?(?=\n## |\Z)", re.S)
    if existing_section.search(text):
        text = existing_section.sub("\n" + cleat_text, text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + cleat_text

    with open(handoff_path, "w", encoding="utf-8") as handle:
        handle.write(text)


def make_blank_layer(shape):
    height, width = shape
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    return image


def overlay_white(image, mask):
    result = ensure_bgra(image)
    result[mask > 0] = (255, 255, 255, 0)
    return result


def main():
    args = parse_args()
    directory = ensure_final_package(args.dir)

    if not args.dry_run:
        removed = remove_existing_french_cleat_files(directory)
        if removed:
            print(f"Removed existing French cleat files: {', '.join(sorted(removed))}")

    layers = load_layers(directory)

    image_masks = [load_image_mask(layer.png_path) for layer in layers]
    base_shape = image_masks[0].shape
    if any(mask.shape != base_shape for mask in image_masks):
        raise ValueError("All layer PNGs must have the same dimensions.")

    keyhole_mask = build_keyhole_mask(base_shape, args)
    cavity_mask = build_cavity_mask(base_shape, args)
    if len(layers) < 1:
        raise ValueError("At least one layer is required to add a French cleat.")

    added_layers = 3

    print(f"Directory: {directory}")
    print(f"Existing layers: {len(layers)}")
    print(f"Selected added blank layers: {added_layers}")

    planned_backing_target = len(layers)
    planned_cavity_target = len(layers) + 1
    planned_keyhole_target = len(layers) + 2
    print(f"Backing target layer: {planned_backing_target:02d}")
    print(f"Clearance target layer: {planned_cavity_target:02d}")
    print(f"Keyhole target layer: {planned_keyhole_target:02d}")

    if args.dry_run:
        print("Dry run - no files were changed.")
        return 0

    output_layers = []
    for layer in layers:
        output_layers.append(
            {
                "index": layer.index,
                "label": layer.label,
                "png_path": layer.png_path,
                "dxf_path": layer.dxf_path,
                "image": load_color_image(layer.png_path),
            }
        )

    added_layer_labels = [
        "french_cleat_backing",
        "french_cleat_cavity",
        "french_cleat_keyhole",
    ]

    for label in added_layer_labels[:added_layers]:
        new_index = len(output_layers)
        output_layers.append(
            {
                "index": new_index,
                "label": label,
                "png_path": os.path.join(directory, f"Layer_{new_index:02d}_{label}.png"),
                "dxf_path": os.path.join(directory, f"Layer_{new_index:02d}_{label}.dxf"),
                "image": make_blank_layer(base_shape),
                "synthetic": True,
            }
        )

    backing_target = len(output_layers) - 3
    cavity_target = len(output_layers) - 2
    keyhole_target = len(output_layers) - 1

    print(f"Backing target layer: {backing_target:02d}")
    print(f"Clearance target layer: {cavity_target:02d}")
    print(f"Keyhole target layer: {keyhole_target:02d}")

    output_layers[cavity_target]["image"] = overlay_white(output_layers[cavity_target]["image"], cavity_mask)
    output_layers[keyhole_target]["image"] = overlay_white(output_layers[keyhole_target]["image"], keyhole_mask)

    touched_indices = [backing_target, cavity_target, keyhole_target]

    print("Planned writes:")
    for index in touched_indices:
        layer = output_layers[index]
        print(f"  Layer_{layer['index']:02d}_{layer['label']}.png")

    for index in touched_indices:
        layer = output_layers[index]
        write_png(layer["image"], layer["png_path"])
        regenerate_dxf_with_frame(layer["png_path"], args)

    if added_layers > 0:
        update_handoff(directory, added_layers, output_layers[keyhole_target], output_layers[cavity_target], args)

    # Optionally refresh combined layout DXFs so the final package stays in sync
    layout_stock_size = args.stock_size_in
    layout_gap_mm = args.layout_gap_mm
    if not layout_stock_size:
        inferred = infer_layout_refresh_config(directory)
        if inferred is not None:
            layout_stock_size, layout_gap_mm = inferred

    if layout_stock_size:
        try:
            refresh_layout_cut_generator(directory, layout_stock_size, layout_gap_mm)
        except Exception as exc:
            print(f"Warning: failed to refresh layout-cut-generator: {exc}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
