import os
import re 

import cv2
import numpy as np

LAYER_PNG_RE = re.compile(r"^Layer_(\d+)(?:_.*)?\.png$", re.IGNORECASE)

def parse_background_color(value):
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"Background color must be R,G,B with three 0-255 integers, got '{value}'"
        )

    rgb = []
    for part in parts:
        component = int(part)
        if component < 0 or component > 255:
            raise ValueError(
                f"Background color components must be between 0 and 255, got '{value}'"
            )
        rgb.append(component)
    return tuple(rgb)

def discover_layer_pngs(final_dir):
    if not os.path.isdir(final_dir):
        raise FileNotFoundError(f"Final package directory does not exist: {final_dir}")

    layer_entries = []
    for name in os.listdir(final_dir):
        match = LAYER_PNG_RE.match(name)
        if not match:
            continue

        path = os.path.join(final_dir, name)
        if not os.path.isfile(path):
            continue

        layer_entries.append(
            {
                "index": int(match.group(1)),
                "name": name,
                "path": path,
            }
        )

    if not layer_entries:
        raise FileNotFoundError(f"No Layer_*.png files found in {final_dir}")

    if not any(entry["index"] == 0 for entry in layer_entries):
        raise ValueError(
            f"Missing Layer_00 in {final_dir}. The assembled preview requires an explicit top layer."
        )

    layer_entries.sort(key=lambda entry: entry["index"])
    return layer_entries

def load_rgba_layers(final_dir):
    layer_entries = discover_layer_pngs(final_dir)

    expected_shape = None
    loaded_layers = []

    for entry in layer_entries:
        image = cv2.imread(entry["path"], cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileNotFoundError(f"Could not read layer image: {entry['path']}")

        if image.ndim != 3 or image.shape[2] != 4:
            raise ValueError(
                f"Layer image must be RGBA/BGRA with 4 channels: {entry['path']} has shape {image.shape}"
            )

        if expected_shape is None:
            expected_shape = image.shape[:2]
        elif image.shape[:2] != expected_shape:
            raise ValueError(
                f"Layer dimensions do not match: {entry['name']} has {image.shape[1]}x{image.shape[0]} "
                f"but expected {expected_shape[1]}x{expected_shape[0]}"
            )

        loaded_layers.append(
            {
                "index": entry["index"],
                "name": entry["name"],
                "path": entry["path"],
                "image": image,
            }
        )

    return loaded_layers

def alpha_composite_bgra(dst_bgra, src_bgra):
    if dst_bgra.shape != src_bgra.shape:
        raise ValueError(
            f"Alpha composite requires matching image shapes, got {dst_bgra.shape} and {src_bgra.shape}"
        )

    dst = dst_bgra.astype(np.float32) / 255.0
    src = src_bgra.astype(np.float32) / 255.0

    dst_rgb = dst[..., :3]
    dst_alpha = dst[..., 3:4]

    src_rgb = src[..., :3]
    src_alpha = src[..., 3:4]

    out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
    out_rgb_premult = (
        src_rgb * src_alpha
        + dst_rgb * dst_alpha * (1.0 - src_alpha)
    )
    out_rgb = np.where(
        out_alpha > 0,
        out_rgb_premult / np.clip(out_alpha, 1e-6, 1.0),
        0.0,
    )

    out = np.zeros_like(dst_bgra)
    out[..., :3] = np.clip(np.rint(out_rgb * 255.0), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.rint(out_alpha[..., 0] * 255.0), 0, 255).astype(np.uint8)
    return out

def compose_layers_bgra(layers):
    if not layers:
        raise ValueError("No layers were provided for composition")

    height, width = layers[0]["image"].shape[:2]
    composite = np.zeros((height, width, 4), dtype=np.uint8)

    draw_order = sorted(layers, key=lambda layer: layer["index"], reverse=True)
    for layer in draw_order:
        composite = alpha_composite_bgra(composite, layer["image"])

    return composite, draw_order

def render_on_background(composite_bgra, background_rgb):
    if composite_bgra.ndim != 3 or composite_bgra.shape[2] != 4:
        raise ValueError(
            f"Expected a 4-channel composite image, got shape {composite_bgra.shape}"
        )

    red, green, blue = background_rgb
    background = np.zeros((composite_bgra.shape[0], composite_bgra.shape[1], 3), dtype=np.uint8)
    background[..., 0] = blue
    background[..., 1] = green
    background[..., 2] = red

    fg = composite_bgra[..., :3].astype(np.float32) / 255.0
    alpha = composite_bgra[..., 3:4].astype(np.float32) / 255.0
    bg = background.astype(np.float32) / 255.0

    out = fg * alpha + bg * (1.0 - alpha)
    return np.clip(np.rint(out * 255.0), 0, 255).astype(np.uint8)


def ensure_writable_output(path, force):
    if os.path.exists(path) and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing preview file without --force: {path}"
        )

def render_composite_previews(
    final_dir,
    output_dir=None,
    transparent_name="composite_transparent.png",
    background_name="composite_on_neutral_background.png",
    background_color=(245, 245, 245),
    force=False,
):
    layers = load_rgba_layers(final_dir)
    composite_bgra, draw_order = compose_layers_bgra(layers)

    preview_dir = output_dir or os.path.join(final_dir, "previews")
    os.makedirs(preview_dir, exist_ok=True)

    transparent_path = os.path.join(preview_dir, transparent_name)
    background_path = os.path.join(preview_dir, background_name)

    ensure_writable_output(transparent_path, force)
    ensure_writable_output(background_path, force)

    background_bgr = render_on_background(composite_bgra, background_color)

    if not cv2.imwrite(transparent_path, composite_bgra):
        raise IOError(f"Could not write transparent composite preview: {transparent_path}")

    if not cv2.imwrite(background_path, background_bgr):
        raise IOError(f"Could not write neutral-background composite preview: {background_path}")

    height, width = composite_bgra.shape[:2]
    return {
        "output_dir": preview_dir,
        "transparent_path": transparent_path,
        "background_path": background_path,
        "image_size": (width, height),
        "layer_order_desc": [layer["name"] for layer in draw_order],
        "layer_indices_desc": [layer["index"] for layer in draw_order],
    }