import os
import math

import cv2
import numpy as np

from preview_tools.layer_composite import (
    compose_layers_bgra,
    discover_layer_pngs,
    ensure_writable_output,
    load_rgba_layers,
    render_on_background
)

def _alpha_bbox(alpha):
    ys, xs = np.where(alpha > 0)
    if ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

def _crop_to_alpha(image_bgra):
    bbox = _alpha_bbox(image_bgra[..., 3])
    if bbox is None:
        return image_bgra.copy(), (0, 0)
    x0, y0, x1, y1 = bbox
    return image_bgra[y0:y1, x0:x1].copy(), (x0, y0)

def _fit_within(image_bgra, max_w, max_h):
    h, w = image_bgra.shape[:2]
    if h <= 0 or w <= 0:
        return image_bgra.copy()

    scale = min(max_w / float(w), max_h / float(h), 1.0)
    if scale == 1.0:
        return image_bgra.copy()

    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(image_bgra, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _paste_alpha(dst_bgra, src_bgra, x, y):
    h, w = src_bgra.shape[:2]
    dst_h, dst_w = dst_bgra.shape[:2]

    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(dst_w, x + w)
    y1 = min(dst_h, y + h)
    if x0 >= x1 or y0 >= y1:
        return

    sx0 = x0 - x
    sy0 = y0 - y
    sx1 = sx0 + (x1 - x0)
    sy1 = sy0 + (y1 - y0)

    src = src_bgra[sy0:sy1, sx0:sx1]
    dst = dst_bgra[y0:y1, x0:x1]

    # alpha composite src over dst
    src_f = src.astype(np.float32) / 255.0
    dst_f = dst.astype(np.float32) / 255.0

    src_rgb = src_f[..., :3]
    src_a = src_f[..., 3:4]
    dst_rgb = dst_f[..., :3]
    dst_a = dst_f[..., 3:4]

    out_a = src_a + dst_a * (1.0 - src_a)
    out_rgb_premult = src_rgb * src_a + dst_rgb * dst_a * (1.0 - src_a)
    out_rgb = np.where(out_a > 0, out_rgb_premult / np.clip(out_a, 1e-6, 1.0), 0.0)

    out = np.zeros_like(dst)
    out[..., :3] = np.clip(np.rint(out_rgb * 255.0), 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(np.rint(out_a[..., 0] * 255.0), 0, 255).astype(np.uint8)

    dst_bgra[y0:y1, x0:x1] = out


def _build_fan_showcase(layers_desc, canvas_w, canvas_h, x_step, y_step, margin):
    canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

    # Crop each layer to non-transparent bbox so offsets are visually meaningful.
    cropped_layers = []
    for layer in layers_desc:
        cropped, _ = _crop_to_alpha(layer["image"])
        cropped_layers.append(
            {
                "index": layer["index"],
                "name": layer["name"],
                "image": cropped,
            }
        )

    if not cropped_layers:
        return canvas

    max_h = max(layer["image"].shape[0] for layer in cropped_layers)
    max_w = max(layer["image"].shape[1] for layer in cropped_layers)

    # Anchor near lower-middle, then stagger each layer to the right and slightly upward.
    base_x = margin
    base_y = min(canvas_h - max_h - margin, int(canvas_h * 0.60))
    base_y = max(margin, base_y)

    # Draw bottom-most first, top-most last.
    for i, layer in enumerate(cropped_layers):
        x = base_x + i * x_step
        y = base_y - i * y_step
        _paste_alpha(canvas, layer["image"], x, y)

    return canvas

def _stack_vertical(top_bgra, bottom_bgra, gap, margin):
    top_h, top_w = top_bgra.shape[:2]
    bot_h, bot_w = bottom_bgra.shape[:2]

    out_w = max(top_w, bot_w) + 2 * margin
    out_h = top_h + bot_h + gap + 2 * margin
    out = np.zeros((out_h, out_w, 4), dtype=np.uint8)

    top_x = margin + (max(top_w, bot_w) - top_w) // 2
    bot_x = margin + (max(top_w, bot_w) - bot_w) // 2

    _paste_alpha(out, top_bgra, top_x, margin)
    _paste_alpha(out, bottom_bgra, bot_x, margin + top_h + gap)
    return out

def _build_lineup_strip(layers_desc, strip_w, strip_h, margin, item_gap):
    strip = np.zeros((strip_h, strip_w, 4), dtype=np.uint8)
    n = len(layers_desc)
    if n == 0:
        return strip

    usable_w = strip_w - 2 * margin
    usable_h = strip_h - 2 * margin
    if usable_w <= 0 or usable_h <= 0:
        return strip

    slot_w = max(1, int((usable_w - item_gap * (n - 1)) / n))
    slot_h = usable_h

    x = margin
    for layer in layers_desc:
        cropped, _ = _crop_to_alpha(layer["image"])
        fitted = _fit_within(cropped, slot_w, slot_h)
        fh, fw = fitted.shape[:2]

        px = x + max(0, (slot_w - fw) // 2)
        py = margin + max(0, (slot_h - fh) // 2)
        _paste_alpha(strip, fitted, px, py)

        x += slot_w + item_gap

    return strip

def _side_by_side(left_bgra, right_bgra, gap, margin):
    lh, lw = left_bgra.shape[:2]
    rh, rw = right_bgra.shape[:2]

    out_w = lw + rw + gap + 2 * margin
    out_h = max(lh, rh) + 2 * margin
    out = np.zeros((out_h, out_w, 4), dtype=np.uint8)

    ly = margin + (max(lh, rh) - lh) // 2
    ry = margin + (max(lh, rh) - rh) // 2

    _paste_alpha(out, left_bgra, margin, ly)
    _paste_alpha(out, right_bgra, margin + lw + gap, ry)
    return out

def render_showcase_previews(
    final_dir,
    output_dir=None,
    force=False,
    background_color=(245, 245, 245),
    fan_name="showcase_fan_transparent.png",
    fan_bg_name="showcase_fan_on_neutral_background.png",
    compare_name="showcase_side_by_side_transparent.png",
    compare_bg_name="showcase_side_by_side_on_neutral_background.png",
):
    # Load in canonical order (ascending index), then get compositing order.
    layers = load_rgba_layers(final_dir)
    composite_bgra, layers_desc = compose_layers_bgra(layers)  # desc order: bottom -> top

    h, w = composite_bgra.shape[:2]
    n = len(layers_desc)

    # Fan layout params scale with image size/layer count.
    margin = max(24, int(round(min(w, h) * 0.04)))
    x_step = max(14, int(round(w * 0.035)))
    y_step = max(8, int(round(h * 0.018)))

    # Canvas for fan area (wider and taller than source so offsets fit).
    fan_w = w + x_step * max(0, n - 1) + 2 * margin
    fan_h = h + y_step * max(0, n - 1) + 2 * margin

    fan = _build_fan_showcase(
        layers_desc=layers_desc,
        canvas_w=fan_w,
        canvas_h=fan_h,
        x_step=x_step,
        y_step=y_step,
        margin=margin,
    )

    # Bottom lineup strip.
    strip_h = max(120, int(round(h * 0.20)))
    strip = _build_lineup_strip(
        layers_desc=layers_desc,
        strip_w=fan_w,
        strip_h=strip_h,
        margin=max(12, margin // 2),
        item_gap=max(6, int(round(w * 0.01))),
    )

    fan_with_strip = _stack_vertical(
        top_bgra=fan,
        bottom_bgra=strip,
        gap=max(10, margin // 2),
        margin=max(8, margin // 3),
    )

    # Side-by-side: assembled composite next to fan+lineup showcase.
    compare = _side_by_side(
        left_bgra=composite_bgra,
        right_bgra=fan_with_strip,
        gap=max(20, margin),
        margin=margin,
    )

    showcase_dir = output_dir or os.path.join(final_dir, "previews", "showcase")
    os.makedirs(showcase_dir, exist_ok=True)

    fan_path = os.path.join(showcase_dir, fan_name)
    fan_bg_path = os.path.join(showcase_dir, fan_bg_name)
    compare_path = os.path.join(showcase_dir, compare_name)
    compare_bg_path = os.path.join(showcase_dir, compare_bg_name)

    ensure_writable_output(fan_path, force)
    ensure_writable_output(fan_bg_path, force)
    ensure_writable_output(compare_path, force)
    ensure_writable_output(compare_bg_path, force)

    fan_bg = render_on_background(fan_with_strip, background_color)
    compare_bg = render_on_background(compare, background_color)

    if not cv2.imwrite(fan_path, fan_with_strip):
        raise IOError(f"Could not write showcase fan preview: {fan_path}")
    if not cv2.imwrite(fan_bg_path, fan_bg):
        raise IOError(f"Could not write showcase fan neutral preview: {fan_bg_path}")
    if not cv2.imwrite(compare_path, compare):
        raise IOError(f"Could not write showcase side-by-side preview: {compare_path}")
    if not cv2.imwrite(compare_bg_path, compare_bg):
        raise IOError(f"Could not write showcase side-by-side neutral preview: {compare_bg_path}")

    return {
        "output_dir": showcase_dir,
        "fan_path": fan_path,
        "fan_bg_path": fan_bg_path,
        "compare_path": compare_path,
        "compare_bg_path": compare_bg_path,
        "layer_order_desc": [layer["name"] for layer in layers_desc],
        "assembled_size": (w, h),
        "fan_size": (fan_with_strip.shape[1], fan_with_strip.shape[0]),
        "compare_size": (compare.shape[1], compare.shape[0]),
    }