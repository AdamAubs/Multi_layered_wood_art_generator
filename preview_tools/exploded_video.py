from dataclasses import dataclass
import os

from preview_tools.layer_composite import discover_layer_pngs

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