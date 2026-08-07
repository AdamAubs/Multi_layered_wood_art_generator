import argparse
from dataclasses import asdict, dataclass, replace
import json
import os
import shutil
import subprocess

import cv2
import numpy as np

from preview_tools.layer_composite import (
    discover_layer_pngs,
    ensure_writable_output,
    load_rgba_layers,
)

@dataclass(frozen=True)
class VideoPreset:
    name: str
    width: int
    height: int
    fps: int
    assembled_hold_sec: float
    explode_sec: float
    exploded_hold_sec: float
    reassemble_sec: float
    final_hold_sec: float
    background_rgb: tuple[int, int, int]
    margin_px: int
    layer_gap_x_px: int
    layer_gap_y_px: int
    thickness_px: int
    shadow_offset_x_px: int
    shadow_offset_y_px: int
    shadow_blur_px: int
    shadow_opacity: float

    @property
    def duration_sec(self):
        return (
            self.assembled_hold_sec
            + self.explode_sec
            + self.exploded_hold_sec
            + self.reassemble_sec
            + self.final_hold_sec
        )

    @property
    def frame_count(self):
        return int(round(self.duration_sec * self.fps))

PRESETS = {
    "etsy": VideoPreset(
        name="etsy",
        width=2160,
        height=1080,
        fps=30,
        assembled_hold_sec=0.8,
        explode_sec=2.0,
        exploded_hold_sec=1.4,
        reassemble_sec=2.0,
        final_hold_sec=0.8,
        background_rgb=(245, 242, 236),
        margin_px=72,
        layer_gap_x_px=96,
        layer_gap_y_px=-48,
        thickness_px=6,
        shadow_offset_x_px=18,
        shadow_offset_y_px=18,
        shadow_blur_px=19,
        shadow_opacity=0.22,
    ),
}

VIDEO_VIEWS = ("front", "rear")


def resolve_view(view, allow_both=False):
    choices = VIDEO_VIEWS + (("both",) if allow_both else ())
    if view in choices:
        return view

    choices_text = ", ".join(choices)
    raise ValueError(
        f"Unknown exploded-video view '{view}'. Choose from: {choices_text}"
    )


def resolve_final_dir(package_dir):
    requested = os.path.abspath(os.path.expanduser(os.fspath(package_dir)))
    candidates = [
        requested,
        os.path.join(requested, "outputs", "final"),
    ]

    checked = []
    for candidate in candidates:
        if candidate in checked:
            continue

        checked.append(candidate)

        try:
            discover_layer_pngs(candidate)
        except (FileNotFoundError, ValueError):
            continue

        return candidate

    checked_text = "\n".join(f"  - {path}" for path in checked)
    raise FileNotFoundError(
        "Could not resolve a final layer package. Pass either a directory that "
        "contains Layer_*.png files or a run directory containing outputs/final.\n"
        f"Checked:\n{checked_text}"
    )

def resolve_preset(preset):
    if isinstance(preset, VideoPreset):
        return preset

    try:
        return PRESETS[preset]
    except KeyError as exc:
        choices = ", ".join(sorted(PRESETS))
        raise ValueError(
            f"Unknown exploded-video preset '{preset}'. Choose from: {choices}"
        ) from exc

def _smoothstep(value):
    value = min(1.0, max(0.0, float(value)))
    return value * value * (3.0 - 2.0 * value)

def explosion_progress(time_sec, preset):
    preset = resolve_preset(preset)
    cursor = 0.0

    cursor += preset.assembled_hold_sec
    if time_sec <= cursor:
        return 0.0

    explode_end = cursor + preset.explode_sec
    if time_sec < explode_end:
        return _smoothstep((time_sec - cursor) / preset.explode_sec)
    cursor = explode_end

    cursor += preset.exploded_hold_sec
    if time_sec <= cursor:
        return 1.0

    reassemble_end = cursor + preset.reassemble_sec
    if time_sec < reassemble_end:
        return 1.0 - _smoothstep(
            (time_sec - cursor) / preset.reassemble_sec
        )

    return 0.0

def _make_solid_bgra(alpha, color_bgr, opacity=1.0):
    image = np.zeros((alpha.shape[0], alpha.shape[1], 4), dtype=np.uint8)
    image[..., :3] = np.asarray(color_bgr, dtype=np.uint8)
    image[..., 3] = np.clip(
        np.rint(alpha.astype(np.float32) * opacity),
        0,
        255,
    ).astype(np.uint8)
    return image


def _make_shadow_bgra(alpha, preset):
    radius = max(1, int(preset.shadow_blur_px))
    pad = radius * 2
    padded = np.zeros(
        (alpha.shape[0] + 2 * pad, alpha.shape[1] + 2 * pad),
        dtype=np.uint8,
    )
    padded[pad : pad + alpha.shape[0], pad : pad + alpha.shape[1]] = alpha
    blurred = cv2.GaussianBlur(
        padded,
        (0, 0),
        sigmaX=max(1.0, radius / 3.0),
        sigmaY=max(1.0, radius / 3.0),
    )
    return _make_solid_bgra(
        blurred,
        color_bgr=(47, 42, 37),
        opacity=preset.shadow_opacity,
    ), pad

def _composite_bgra_over_bgr(dst_bgr, src_bgra, x, y, alpha_scale=1.0):
    src_h, src_w = src_bgra.shape[:2]
    dst_h, dst_w = dst_bgr.shape[:2]

    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(dst_w, x + src_w)
    y1 = min(dst_h, y + src_h)
    if x0 >= x1 or y0 >= y1:
        return

    sx0 = x0 - x
    sy0 = y0 - y
    sx1 = sx0 + (x1 - x0)
    sy1 = sy0 + (y1 - y0)

    src = src_bgra[sy0:sy1, sx0:sx1]
    dst = dst_bgr[y0:y1, x0:x1]
    alpha = (
        src[..., 3:4].astype(np.float32)
        * (float(alpha_scale) / 255.0)
    )
    src_bgr = src[..., :3].astype(np.float32)
    dst_float = dst.astype(np.float32)
    dst_bgr[y0:y1, x0:x1] = np.clip(
        np.rint(src_bgr * alpha + dst_float * (1.0 - alpha)),
        0,
        255,
    ).astype(np.uint8)

def _resize_bgra_premultiplied(image_bgra, target_size, interpolation):
    image = image_bgra.astype(np.float32) / 255.0
    alpha = image[..., 3]
    premultiplied_bgr = image[..., :3] * alpha[..., None]

    resized_alpha = cv2.resize(
        alpha,
        target_size,
        interpolation=interpolation,
    )
    resized_premultiplied = cv2.resize(
        premultiplied_bgr,
        target_size,
        interpolation=interpolation,
    )
    if resized_premultiplied.ndim == 2:
        resized_premultiplied = resized_premultiplied[..., None]

    resized_bgr = np.zeros_like(resized_premultiplied)
    np.divide(
        resized_premultiplied,
        resized_alpha[..., None],
        out=resized_bgr,
        where=resized_alpha[..., None] > 1e-6,
    )

    output = np.zeros(
        (target_size[1], target_size[0], 4),
        dtype=np.uint8,
    )
    output[..., :3] = np.clip(
        np.rint(resized_bgr * 255.0),
        0,
        255,
    ).astype(np.uint8)
    output[..., 3] = np.clip(
        np.rint(resized_alpha * 255.0),
        0,
        255,
    ).astype(np.uint8)
    return output

def prepare_video_layers(layers, preset, view="front"):
    preset = resolve_preset(preset)
    view = resolve_view(view)
    if not layers:
        raise ValueError("No layers were provided for exploded-video rendering")

    source_h, source_w = layers[0]["image"].shape[:2]
    layer_count = len(layers)
    if view == "rear":
        layer_gap_x_px = -abs(preset.layer_gap_x_px)
        layer_gap_y_px = -abs(preset.layer_gap_y_px)
    else:
        layer_gap_x_px = preset.layer_gap_x_px
        layer_gap_y_px = preset.layer_gap_y_px

    max_dx = abs(layer_gap_x_px) * max(0, layer_count - 1)
    max_dy = abs(layer_gap_y_px) * max(0, layer_count - 1)

    available_w = preset.width - 2 * preset.margin_px - max_dx
    available_h = preset.height - 2 * preset.margin_px - max_dy
    if available_w <= 0 or available_h <= 0:
        raise ValueError(
            f"Preset '{preset.name}' does not leave enough canvas space for "
            f"{layer_count} layers"
        )

    scale = min(available_w / source_w, available_h / source_h)
    target_w = max(1, int(round(source_w * scale)))
    target_h = max(1, int(round(source_h * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LANCZOS4

    min_dx = min(0, layer_gap_x_px * max(0, layer_count - 1))
    max_dx_signed = max(0, layer_gap_x_px * max(0, layer_count - 1))
    min_dy = min(0, layer_gap_y_px * max(0, layer_count - 1))
    max_dy_signed = max(0, layer_gap_y_px * max(0, layer_count - 1))
    envelope_w = target_w + max_dx_signed - min_dx
    envelope_h = target_h + max_dy_signed - min_dy
    base_x = (preset.width - envelope_w) // 2 - min_dx
    base_y = (preset.height - envelope_h) // 2 - min_dy

    prepared = []
    for position, layer in enumerate(layers):
        source_image = layer["image"]
        if view == "rear":
            source_image = cv2.flip(source_image, 1)

        resized = _resize_bgra_premultiplied(
            source_image,
            (target_w, target_h),
            interpolation,
        )
        if view == "rear":
            step = position
        else:
            step = layer_count - 1 - position

        side = _make_solid_bgra(
            resized[..., 3],
            color_bgr=(72, 61, 50),
            opacity=0.88,
        )
        shadow, shadow_pad = _make_shadow_bgra(resized[..., 3], preset)
        prepared.append(
            {
                "index": layer["index"],
                "name": layer["name"],
                "image": resized,
                "side": side,
                "shadow": shadow,
                "shadow_pad": shadow_pad,
                "step": step,
                "base_x": base_x,
                "base_y": base_y,
                "layer_gap_x_px": layer_gap_x_px,
                "layer_gap_y_px": layer_gap_y_px,
                "view": view,
            }
        )
    return prepared


def _layers_in_draw_order(prepared_layers):
    if not prepared_layers:
        return []

    view = prepared_layers[0].get("view", "front")
    if view == "rear":
        return list(prepared_layers)

    return list(reversed(prepared_layers))


def render_exploded_frame(prepared_layers, preset, progress):
    preset = resolve_preset(preset)
    red, green, blue = preset.background_rgb
    frame = np.empty((preset.height, preset.width, 3), dtype=np.uint8)
    frame[:] = (blue, green, red)

    thickness_steps = sorted(
        {
            max(1, preset.thickness_px // 3),
            max(1, (2 * preset.thickness_px) // 3),
            max(1, preset.thickness_px),
        },
        reverse=True,
    )

    for layer in _layers_in_draw_order(prepared_layers):
        x = int(round(
            layer["base_x"]
            + layer["step"]
            * layer.get("layer_gap_x_px", preset.layer_gap_x_px)
            * progress
        ))
        y = int(round(
            layer["base_y"]
            + layer["step"]
            * layer.get("layer_gap_y_px", preset.layer_gap_y_px)
            * progress
        ))

        shadow_scale = 0.35 + 0.65 * progress
        _composite_bgra_over_bgr(
            frame,
            layer["shadow"],
            x + preset.shadow_offset_x_px - layer["shadow_pad"],
            y + preset.shadow_offset_y_px - layer["shadow_pad"],
            alpha_scale=shadow_scale,
        )

        for thickness_offset in thickness_steps:
            _composite_bgra_over_bgr(
                frame,
                layer["side"],
                x + thickness_offset,
                y + thickness_offset,
            )

        _composite_bgra_over_bgr(frame, layer["image"], x, y)

    return frame


def _ffmpeg_version(ffmpeg_path):
    result = subprocess.run(
        [ffmpeg_path, "-version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"

    first_line = result.stdout.splitlines()
    return first_line[0] if first_line else "unknown"


def _encode_video(video_path, prepared_layers, preset, ffmpeg_path):
    partial_path = f"{video_path}.partial.mp4"
    if os.path.exists(partial_path):
        os.remove(partial_path)

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{preset.width}x{preset.height}",
        "-r",
        str(preset.fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        partial_path,
    ]

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    stdin_pipe = process.stdin
    stderr_pipe = process.stderr

    if stdin_pipe is None or stderr_pipe is None:
        process.kill()
        process.wait()

        if os.path.exists(partial_path):
            os.remove(partial_path)

        raise RuntimeError("FFmpeg stdin/stderr pipes were not created")

    try:
        for frame_index in range(preset.frame_count):
            time_sec = frame_index / float(preset.fps)
            progress = explosion_progress(time_sec, preset)
            frame = render_exploded_frame(
                prepared_layers,
                preset,
                progress,
            )
            stdin_pipe.write(frame.tobytes())

        stdin_pipe.close()
        stderr = stderr_pipe.read().decode(
            "utf-8",
            errors="replace",
        )
        return_code = process.wait()
    except Exception:
        process.kill()
        process.wait()

        if os.path.exists(partial_path):
            os.remove(partial_path)

        raise

    if return_code != 0:
        if os.path.exists(partial_path):
            os.remove(partial_path)

        raise RuntimeError(
            f"FFmpeg failed with exit code {return_code}: "
            f"{stderr.strip()}"
        )

    os.replace(partial_path, video_path)


def _output_paths(animation_dir, preset, view):
    suffix = "" if view == "front" else "_rear"
    stem = f"exploded_view_{preset.name}{suffix}"
    return {
        "video_path": os.path.join(animation_dir, f"{stem}.mp4"),
        "poster_path": os.path.join(animation_dir, f"{stem}_poster.png"),
        "metadata_path": os.path.join(
            animation_dir,
            f"{stem}_metadata.json",
        ),
    }


def _render_single_view(
    package_dir,
    final_dir,
    layers,
    preset,
    animation_dir,
    view,
    output_paths,
    ffmpeg_path,
    ffmpeg_version,
):
    prepared_layers = prepare_video_layers(layers, preset, view=view)

    _encode_video(
        video_path=output_paths["video_path"],
        prepared_layers=prepared_layers,
        preset=preset,
        ffmpeg_path=ffmpeg_path,
    )

    poster = render_exploded_frame(
        prepared_layers,
        preset,
        progress=1.0,
    )
    if not cv2.imwrite(output_paths["poster_path"], poster):
        raise IOError(
            "Could not write exploded-view poster: "
            f'{output_paths["poster_path"]}'
        )

    draw_order = _layers_in_draw_order(prepared_layers)
    layer_order_bottom_to_top = [
        layer["name"] for layer in draw_order
    ]
    stationary_layer = min(
        prepared_layers,
        key=lambda layer: layer["step"],
    )["name"]
    farthest_moving_layer = max(
        prepared_layers,
        key=lambda layer: layer["step"],
    )["name"]

    metadata = {
        "schema_version": 1,
        "renderer": "preview_tools.exploded_video",
        "view": view,
        "preset": asdict(preset),
        "source": {
            "requested_path": os.fspath(package_dir),
            "resolved_final_dir": final_dir,
            "mirrored_horizontally": view == "rear",
            "layer_order_bottom_to_top": (
                layer_order_bottom_to_top
            ),
        },
        "animation": {
            "stationary_layer": stationary_layer,
            "farthest_moving_layer": farthest_moving_layer,
            "explosion_direction": (
                "up-left" if view == "rear" else "up-right"
            ),
        },
        "encoding": {
            "codec": "H.264",
            "pixel_format": "yuv420p",
            "audio": False,
            "ffmpeg": ffmpeg_version,
        },
        "outputs": {
            "video": os.path.basename(output_paths["video_path"]),
            "poster": os.path.basename(output_paths["poster_path"]),
        },
    }

    with open(
        output_paths["metadata_path"],
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return {
        "view": view,
        "final_dir": final_dir,
        "output_dir": animation_dir,
        **output_paths,
        "mirrored_horizontally": view == "rear",
        "stationary_layer": stationary_layer,
        "farthest_moving_layer": farthest_moving_layer,
        "layer_order_bottom_to_top": (
            layer_order_bottom_to_top
        ),
        "frame_count": preset.frame_count,
        "duration_sec": preset.duration_sec,
        "resolution": (preset.width, preset.height),
        "fps": preset.fps,
    }


def render_exploded_video(
    package_dir,
    preset="etsy",
    output_dir=None,
    background_color=None,
    force=False,
    ffmpeg_path=None,
    view="front",
):
    preset = resolve_preset(preset)
    view = resolve_view(view, allow_both=True)

    if background_color is not None:
        preset = replace(
            preset,
            background_rgb=tuple(background_color),
        )

    final_dir = resolve_final_dir(package_dir)
    layers = load_rgba_layers(final_dir)
    animation_dir = os.path.abspath(
        output_dir
        or os.path.join(final_dir, "previews", "animation")
    )
    os.makedirs(animation_dir, exist_ok=True)

    selected_views = VIDEO_VIEWS if view == "both" else (view,)
    paths_by_view = {
        selected_view: _output_paths(
            animation_dir,
            preset,
            selected_view,
        )
        for selected_view in selected_views
    }

    for selected_view in selected_views:
        for path in paths_by_view[selected_view].values():
            ensure_writable_output(path, force)

    resolved_ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not resolved_ffmpeg:
        raise FileNotFoundError(
            "FFmpeg was not found on PATH. On macOS, install it "
            "with 'brew install ffmpeg', then rerun this command."
        )

    ffmpeg_version = _ffmpeg_version(resolved_ffmpeg)
    results = {}
    for selected_view in selected_views:
        results[selected_view] = _render_single_view(
            package_dir=package_dir,
            final_dir=final_dir,
            layers=layers,
            preset=preset,
            animation_dir=animation_dir,
            view=selected_view,
            output_paths=paths_by_view[selected_view],
            ffmpeg_path=resolved_ffmpeg,
            ffmpeg_version=ffmpeg_version,
        )

    if view != "both":
        return results[view]

    return {
        "view": "both",
        "final_dir": final_dir,
        "output_dir": animation_dir,
        "views": results,
        "frame_count": preset.frame_count,
        "duration_sec": preset.duration_sec,
        "resolution": (preset.width, preset.height),
        "fps": preset.fps,
    }


def _parse_background_color(value):
    text = value.strip()
    message = (
        "background color must be either #RRGGBB or R,G,B, "
        "with every channel between 0 and 255"
    )

    if text.startswith("#"):
        if len(text) != 7:
            raise argparse.ArgumentTypeError(message)

        try:
            return tuple(
                int(text[position : position + 2], 16)
                for position in (1, 3, 5)
            )
        except ValueError as exc:
            raise argparse.ArgumentTypeError(message) from exc

    pieces = text.split(",")
    if len(pieces) != 3:
        raise argparse.ArgumentTypeError(message)

    try:
        rgb = tuple(int(piece.strip()) for piece in pieces)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(message) from exc

    if any(channel < 0 or channel > 255 for channel in rgb):
        raise argparse.ArgumentTypeError(message)

    return rgb


def _build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="python -m preview_tools.exploded_video",
        description=(
            "Generate a 2.5D exploded-view MP4 from a finalized "
            "multi-layer wood-art package."
        ),
    )
    parser.add_argument(
        "package_dir",
        help=(
            "Run directory containing outputs/final, or the final "
            "directory containing Layer_*.png files."
        ),
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default="etsy",
        help="Video preset to use. Default: etsy.",
    )
    parser.add_argument(
        "--view",
        choices=(*VIDEO_VIEWS, "both"),
        default="front",
        help=(
            "View to render: front, rear, or both. Default: front."
        ),
    )
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory for the MP4, poster, and metadata. By default, "
            "they are written under outputs/final/previews/animation."
        ),
    )
    parser.add_argument(
        "--background-color",
        type=_parse_background_color,
        metavar="COLOR",
        help=(
            "Override the preset background using #RRGGBB or R,G,B."
        ),
    )
    parser.add_argument(
        "--ffmpeg",
        dest="ffmpeg_path",
        help=(
            "Explicit FFmpeg executable path. By default, FFmpeg is "
            "resolved from PATH."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing video, poster, and metadata outputs.",
    )
    return parser


def _print_result(result, indent, heading=None):
    if heading is not None:
        print(f"{heading}:")

    width, height = result["resolution"]
    print(f'{indent}Video: {result["video_path"]}')
    print(f'{indent}Poster: {result["poster_path"]}')
    print(f'{indent}Metadata: {result["metadata_path"]}')
    print(f'{indent}Layers: {len(result["layer_order_bottom_to_top"])}')
    print(f"{indent}Resolution: {width}x{height}")
    print(f'{indent}FPS: {result["fps"]}')
    print(f'{indent}Frames: {result["frame_count"]}')
    print(f'{indent}Duration: {result["duration_sec"]:.2f} seconds')
    print(
        f"{indent}Bottom-to-top order: "
        + ", ".join(result["layer_order_bottom_to_top"])
    )


def main(argv=None):
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    try:
        result = render_exploded_video(
            package_dir=args.package_dir,
            preset=args.preset,
            output_dir=args.output_dir,
            background_color=args.background_color,
            force=args.force,
            ffmpeg_path=args.ffmpeg_path,
            view=args.view,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(
            status=1,
            message=f"error: {exc}\n",
        )

    if result["view"] == "both":
        print("Exploded-view videos created")
        for selected_view in VIDEO_VIEWS:
            _print_result(
                result["views"][selected_view],
                indent="    ",
                heading=f"  {selected_view.title()} view",
            )
    else:
        print("Exploded-view video created")
        _print_result(result, indent="  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
