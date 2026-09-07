import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime
import cv2

from fabrication_tools.settings import (
    DEFAULT_DXF_DPI,
    DEFAULT_FRAME_MARGIN_MM,
    DEFAULT_SETTING_HOLE_DIAMETER_MM,
    DEFAULT_SETTING_HOLE_INSET_MM,
    merge_fabrication_settings as merge_package_fabrication_settings,
)
from fabrication_tools.frame_geometry import FRAME_SHAPES
from fabrication_tools.dimensions import write_dimensions_report


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run preprocessor -> generator -> postprocessor finalize in one command."
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to the input image.",
    )
    parser.add_argument(
        "--filter",
        choices=["meanshift", "bilateral"],
        default="meanshift",
        help="Simplification filter to apply before clustering.",
    )
    parser.add_argument(
        "--meanshift-sp",
        type=int,
        default=20,
        help="Mean shift spatial window radius.",
    )
    parser.add_argument(
        "--meanshift-sr",
        type=int,
        default=60,
        help="Mean shift color window radius.",
    )
    parser.add_argument(
        "--meanshift-max-level",
        type=int,
        default=2,
        help="Mean shift pyramid max level.",
    )
    parser.add_argument(
        "--bilateral-d",
        type=int,
        default=15,
        help="Bilateral filter diameter of pixel neighborhood.",
    )
    parser.add_argument(
        "--sigma-color",
        type=float,
        default=80.0,
        help="Bilateral filter sigmaColor.",
    )
    parser.add_argument(
        "--sigma-space",
        type=float,
        default=80.0,
        help="Bilateral filter sigmaSpace.",
    )
    parser.add_argument(
        "--bilateral-passes",
        type=int,
        default=3,
        help="How many times to apply the bilateral filter.",
    )
    parser.add_argument(
        "--pre-out-dir",
        default="preprocessor_output",
        help="Output directory for preprocessor artifacts.",
    )
    parser.add_argument(
        "--gen-out-dir",
        default=None,
        help="Override generator output directory.",
    )
    parser.add_argument(
        "--post-out-dir",
        default=None,
        help="Override postprocessor output directory.",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Append a YYYYMMDD_HHMMSS timestamp to generator, postprocessor, and final outputs.",
    )
    parser.add_argument(
        "--fab-size-in",
        default=None,
        help="Target final outer DXF frame size in inches as WxH, for example 5x5. Artwork scales to the requested frame margin.",
    )
    parser.add_argument(
        "--frame-shape",
        choices=FRAME_SHAPES,
        default="rectangle",
        help="Outer frame mode: rectangle (default) or the first selected layer outline.",
    )
    parser.add_argument(
        "--stock-size-in",
        default=None,
        help="Optional stock sheet size in inches as WxH (e.g. 12x20). When provided a combined layout DXF will be created and added to the final package.",
    )
    parser.add_argument(
        "--generate-composite-preview",
        action="store_true",
        default=False,
        help="Render assembled composite preview images after finalization succeeds.",
    )
    parser.add_argument(
        "--generate-showcase-preview",
        action="store_true",
        default=False,
        help="Render showcase-style digital asset previews after finalization succeeds."
    )
    parser.add_argument(
        "--bridge-count",
        type=int,
        default=5,
        help="Number of support bridges per patch. Default: 5. Higher values may distort fine details."
    )
    parser.add_argument(
        "--dxf-frame-margin-mm",
        type=float,
        default=DEFAULT_FRAME_MARGIN_MM,
        help="Extra margin in mm between the artwork contour and the outer frame.",
    )
    parser.add_argument(
        "--dxf-setting-hole-diameter-mm",
        type=float,
        default=DEFAULT_SETTING_HOLE_DIAMETER_MM,
        help="Diameter in mm for the four setting holes.",
    )
    parser.add_argument(
        "--dxf-setting-hole-inset-mm",
        type=float,
        default=DEFAULT_SETTING_HOLE_INSET_MM,
        help="Inset in mm from each outer frame corner to the hole center.",
    )
    parser.add_argument(
        "--add-french-cleats",
        action="store_true",
        default=False,
        help="Add French-cleat backing layers after finalization succeeds.",
    )
    parser.add_argument(
        "--create-etsy-release",
        action="store_true",
        default=False,
        help="Create a noninteractive Etsy release after finalization succeeds.",
    )
    parser.add_argument(
        "--merge-visible-fraction",
        type=float,
        default=None,
        help="Postprocessor merge threshold as fraction of image pixels (0 < value < 1).",
    )
    parser.add_argument(
        "--omega-budget-factor",
        type=float,
        default=None,
        help="Generator omega factor used in omega = factor * image_diagonal (0 < value < 1).",
    )
    return parser.parse_args()


def derive_run_name(image_path):
    filename = os.path.basename(image_path)
    run_name, _ = os.path.splitext(filename)
    return run_name


def build_output_dir(prefix, run_name, timestamp):
    base = f"{prefix}_{run_name}"
    return f"{base}_{timestamp}" if timestamp else base


def parse_fab_size_in(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*", value)
    if not match:
        raise ValueError("--fab-size-in must use WxH format such as 5x5.")

    width_in = float(match.group(1))
    height_in = float(match.group(2))
    if width_in <= 0 or height_in <= 0:
        raise ValueError("--fab-size-in values must be greater than zero.")
    return width_in, height_in


def parse_stock_size_in(value):
    """Parse a WxH stock size in inches; non-square allowed."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*", value)
    if not match:
        raise ValueError("--stock-size-in must use WxH format such as 12x20.")

    width_in = float(match.group(1))
    height_in = float(match.group(2))
    if width_in <= 0 or height_in <= 0:
        raise ValueError("--stock-size-in values must be greater than zero.")
    return width_in, height_in


def validate_dxf_geometry(
    frame_margin_mm,
    setting_hole_diameter_mm,
    setting_hole_inset_mm,
    outer_width_mm,
    outer_height_mm,
):
    values = {
        "--dxf-frame-margin-mm": frame_margin_mm,
        "--dxf-setting-hole-diameter-mm": setting_hole_diameter_mm,
        "--dxf-setting-hole-inset-mm": setting_hole_inset_mm,
    }
    for option, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{option} must be a finite value greater than zero.")

    if outer_width_mm <= 0 or outer_height_mm <= 0:
        raise ValueError("Final DXF frame dimensions must be greater than zero.")

    hole_radius_mm = setting_hole_diameter_mm / 2.0
    minimum_inset_mm = hole_radius_mm
    maximum_inset_mm = min(outer_width_mm, outer_height_mm) - hole_radius_mm
    if setting_hole_inset_mm < minimum_inset_mm or setting_hole_inset_mm > maximum_inset_mm:
        raise ValueError(
            "--dxf-setting-hole-inset-mm must keep each setting hole inside the "
            "outer frame."
        )


def compute_dpi_for_outer_size(
    image_width_px,
    image_height_px,
    target_width_in,
    target_height_in,
    frame_margin_mm,
):
    outer_width_mm = target_width_in * 25.4
    outer_height_mm = target_height_in * 25.4
    inner_width_mm = outer_width_mm - (2.0 * frame_margin_mm)
    inner_height_mm = outer_height_mm - (2.0 * frame_margin_mm)
    if inner_width_mm <= 0 or inner_height_mm <= 0:
        raise ValueError(
            "Requested fab size is too small for the configured frame margin. "
            "Increase --fab-size-in or reduce --dxf-frame-margin-mm."
        )

    dpi_x = image_width_px * 25.4 / inner_width_mm
    dpi_y = image_height_px * 25.4 / inner_height_mm

    return dpi_x, dpi_y, outer_width_mm, outer_height_mm


def run_step(command, label, log_path=None):
    print(f"\n--- {label} ---")
    if log_path:
        # Append header and redirect subprocess stdout/stderr to the log file.
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n=== {label} started at {datetime.now().isoformat()} ===\n")
            f.flush()
            result = subprocess.run(command, stdout=f, stderr=f)
            f.write(f"\n=== {label} exited with code {result.returncode} ===\n")
    else:
        result = subprocess.run(command)

    if result.returncode != 0:
        print(f"[!] {label} failed with exit code {result.returncode}")
    return result.returncode


def main():
    args = parse_args()
    run_name = derive_run_name(args.image)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") if args.timestamp else None

    source_image = cv2.imread(args.image, cv2.IMREAD_UNCHANGED)
    if source_image is None:
        print(f"Error: Could not load image at {args.image}.")
        return 1
    image_h, image_w = source_image.shape[:2]

    dxf_dpi_x = DEFAULT_DXF_DPI
    dxf_dpi_y = DEFAULT_DXF_DPI
    frame_margin_x_mm = args.dxf_frame_margin_mm
    frame_margin_y_mm = args.dxf_frame_margin_mm
    outer_width_mm = image_w * 25.4 / dxf_dpi_x + (2.0 * frame_margin_x_mm)
    outer_height_mm = image_h * 25.4 / dxf_dpi_y + (2.0 * frame_margin_y_mm)
    target_w_in = None
    target_h_in = None
    if args.fab_size_in is not None and args.frame_shape == "rectangle":
        try:
            target_w_in, target_h_in = parse_fab_size_in(args.fab_size_in)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        try:
            (
                dxf_dpi_x,
                dxf_dpi_y,
                outer_width_mm,
                outer_height_mm,
            ) = compute_dpi_for_outer_size(
                image_w,
                image_h,
                target_w_in,
                target_h_in,
                args.dxf_frame_margin_mm,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

    if args.fab_size_in is not None and args.frame_shape == "first_layer":
        try:
            target_w_in, target_h_in = parse_fab_size_in(args.fab_size_in)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1
        outer_width_mm = target_w_in * 25.4
        outer_height_mm = target_h_in * 25.4

    try:
        validate_dxf_geometry(
            args.dxf_frame_margin_mm,
            args.dxf_setting_hole_diameter_mm,
            args.dxf_setting_hole_inset_mm,
            outer_width_mm,
            outer_height_mm,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    if args.fab_size_in is not None and args.frame_shape == "rectangle":
        print(
            "Using computed DXF DPI "
            f"{dxf_dpi_x:.6f} (horizontal) and {dxf_dpi_y:.6f} (vertical) "
            f"for outer size {target_w_in:g}x{target_h_in:g} in with "
            f"{frame_margin_x_mm:.2f} mm margins."
        )

    generator_output = args.gen_out_dir or build_output_dir(
        "output_generator",
        run_name,
        timestamp,
    )
    post_output = args.post_out_dir or build_output_dir(
        "output_postprocessed",
        run_name,
        timestamp,
    )
    final_output = build_output_dir("output_final", run_name, timestamp)

    # Ensure final output directory exists and prepare run log path.
    os.makedirs(final_output, exist_ok=True)
    run_log = os.path.join(final_output, "run_log.txt")
    fabrication_settings = {
        "schema_version": 1,
        "dxf": {
            "dpi": dxf_dpi_y,
            "dpi_x": dxf_dpi_x,
            "dpi_y": dxf_dpi_y,
            "frame_margin_mm": args.dxf_frame_margin_mm,
            "frame_margin_x_mm": frame_margin_x_mm,
            "frame_margin_y_mm": frame_margin_y_mm,
            "setting_hole_diameter_mm": args.dxf_setting_hole_diameter_mm,
            "setting_hole_inset_mm": args.dxf_setting_hole_inset_mm,
            "frame_shape": args.frame_shape,
            "frame_geometry_file": "frame_geometry.json" if args.frame_shape == "first_layer" else None,
        },
        "outer_frame": {
            "width_mm": outer_width_mm,
            "height_mm": outer_height_mm,
            "requested_size_in": args.fab_size_in,
        },
        "french_cleats": {
            "requested": args.add_french_cleats,
            "generated": False,
        },
        "etsy_release": {
            "requested": args.create_etsy_release,
            "path": None,
        },
    }
    if args.frame_shape == "first_layer":
        fabrication_settings["outer_frame"].pop("width_mm", None)
        fabrication_settings["outer_frame"].pop("height_mm", None)
        fabrication_settings["dxf"].pop("dpi", None)
        fabrication_settings["dxf"].pop("dpi_x", None)
        fabrication_settings["dxf"].pop("dpi_y", None)

    python = sys.executable
    preprocessor_cmd = [
        python,
        "preprocessor.py",
        "--image",
        args.image,
        "--filter",
        args.filter,
        "--meanshift-sp",
        str(args.meanshift_sp),
        "--meanshift-sr",
        str(args.meanshift_sr),
        "--meanshift-max-level",
        str(args.meanshift_max_level),
        "--bilateral-d",
        str(args.bilateral_d),
        "--sigma-color",
        str(args.sigma_color),
        "--sigma-space",
        str(args.sigma_space),
        "--bilateral-passes",
        str(args.bilateral_passes),
        "--out-dir",
        args.pre_out_dir,
    ]

    if run_step(preprocessor_cmd, "Preprocessor", run_log) != 0:
        return 1

    generator_cmd = [
        python,
        "generator.py",
        "--in-dir",
        args.pre_out_dir,
        "--out-dir",
        generator_output,
    ]

    if args.bridge_count is not None:
        generator_cmd.extend(["--bridge-count", str(args.bridge_count)])
    
    if args.omega_budget_factor is not None:
        generator_cmd.extend(["--omega-budget-factor", str(args.omega_budget_factor)])


    if run_step(generator_cmd, "Generator", run_log) != 0:
        return 1

    postprocessor_cmd = [
        python,
        "postprocessor.py",
        "--in-dir",
        generator_output,
        "--out-dir",
        post_output,
        "--finalize",
        "--run-name",
        run_name,
        "--final-dir",
        final_output,
        "--run-log",
        run_log,
        "--dxf-frame-margin-mm",
        str(args.dxf_frame_margin_mm),
        "--dxf-frame-margin-x-mm",
        str(frame_margin_x_mm),
        "--dxf-frame-margin-y-mm",
        str(frame_margin_y_mm),
        "--dxf-setting-hole-diameter-mm",
        str(args.dxf_setting_hole_diameter_mm),
        "--dxf-setting-hole-inset-mm",
        str(args.dxf_setting_hole_inset_mm),
        "--frame-shape",
        args.frame_shape,
    ]

    if args.fab_size_in is not None:
        postprocessor_cmd.extend(["--fab-size-in", args.fab_size_in])

    if args.fab_size_in is not None:
        postprocessor_cmd.extend(
            [
                "--dxf-dpi",
                f"{dxf_dpi_y:.12f}",
                "--dxf-dpi-x",
                f"{dxf_dpi_x:.12f}",
                "--dxf-dpi-y",
                f"{dxf_dpi_y:.12f}",
            ]
        )

    if args.stock_size_in is not None:
        postprocessor_cmd.extend([
            "--stock-size-in",
            args.stock_size_in,
            "--layout-gap-mm",
            "5.0",
        ])
    
    if args.merge_visible_fraction is not None:
        postprocessor_cmd.extend([
            "--merge-visible-fraction", str(args.merge_visible_fraction)
        ])

    postprocessor_cmd.append("--generate-composite-preview")
    postprocessor_cmd.append("--generate-showcase-preview")

    if run_step(postprocessor_cmd, "Postprocessor", run_log) != 0:
        return 1

    # Postprocessing may resolve a shaped request to a rectangular frame.
    # Keep its actual geometry authoritative for mounting, reports and releases.
    with open(os.path.join(final_output, "fabrication_settings.json")) as settings_file:
        resolved = json.load(settings_file)
    fabrication_settings["dxf"].update(resolved["dxf"])
    fabrication_settings["outer_frame"].update(resolved["outer_frame"])
    args.frame_shape = resolved["dxf"]["frame_shape"]
    dxf_dpi_x = resolved["dxf"]["dpi_x"]
    dxf_dpi_y = resolved["dxf"]["dpi_y"]
    merge_package_fabrication_settings(final_output, fabrication_settings)

    if args.add_french_cleats:
        french_cleat_cmd = [
            python,
            "add_french_cleats.py",
            "--dir",
            final_output,
            "--dpi",
            f"{dxf_dpi_y:.12f}",
            "--dpi-x",
            f"{dxf_dpi_x:.12f}",
            "--dpi-y",
            f"{dxf_dpi_y:.12f}",
            "--frame-margin-mm",
            str(args.dxf_frame_margin_mm),
            "--frame-margin-x-mm",
            str(frame_margin_x_mm),
            "--frame-margin-y-mm",
            str(frame_margin_y_mm),
            "--setting-hole-diameter-mm",
            str(args.dxf_setting_hole_diameter_mm),
            "--setting-hole-inset-mm",
            str(args.dxf_setting_hole_inset_mm),
            "--frame-shape",
            args.frame_shape,
        ]
        if args.stock_size_in is not None:
            french_cleat_cmd.extend([
                "--stock-size-in",
                args.stock_size_in,
                "--layout-gap-mm",
                "5.0",
            ])

        if run_step(
            [*french_cleat_cmd, "--dry-run"],
            "French cleat validation",
            run_log,
        ) != 0:
            return 1
        if run_step(french_cleat_cmd, "French cleat generation", run_log) != 0:
            return 1

        fabrication_settings["french_cleats"]["generated"] = True
        merge_package_fabrication_settings(final_output, fabrication_settings)

    write_dimensions_report(final_output, args.fab_size_in, args.frame_shape)

    if args.create_etsy_release:
        cleat_mode = "include" if args.add_french_cleats else "exclude"
        etsy_release_cmd = [
            python,
            "-m",
            "release_tools.etsy_release",
            final_output,
            "--french-cleats",
            cleat_mode,
        ]
        if run_step(etsy_release_cmd, "Etsy release", run_log) != 0:
            return 1

        fabrication_settings["etsy_release"]["path"] = os.path.join(
            final_output,
            "EtsyRelease",
        )
        merge_package_fabrication_settings(final_output, fabrication_settings)

    print(f"\nPipeline complete. Postprocessed output saved to '{post_output}'.")
    print(f"Final fabrication package saved to '{final_output}'.")
    if args.create_etsy_release:
        print(f"Etsy release saved to '{fabrication_settings['etsy_release']['path']}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
