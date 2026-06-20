import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
import cv2


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
        help="Target final outer DXF size in inches as WxH, for example 5x5. Requires a square source image.",
    )
    parser.add_argument(
        "--stock-size-in",
        default=None,
        help="Optional stock sheet size in inches as WxH (e.g. 12x20). When provided a combined layout DXF will be created and added to the final package.",
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
        default=15.0,
        help="Extra margin in mm between the artwork contour and the outer frame.",
    )
    parser.add_argument(
        "--dxf-setting-hole-diameter-mm",
        type=float,
        default=2.5,
        help="Diameter in mm for the two corner setting holes.",
    )
    parser.add_argument(
        "--dxf-setting-hole-inset-mm",
        type=float,
        default=10.0,
        help="Inset in mm from each outer frame corner to the hole center.",
    )
    parser.add_argument(
        "--merge-visible-fraction",
        type=float,
        default=None,
        help="Postprocessor merge threshold as fraction of image pixels (0 < value < 1).",
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
    if abs(width_in - height_in) > 1e-9:
        raise ValueError("--fab-size-in currently requires a square target such as 5x5.")
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


def compute_dpi_for_outer_size(image_px, target_size_in, frame_margin_mm):
    outer_size_mm = target_size_in * 25.4
    inner_size_mm = outer_size_mm - (2.0 * frame_margin_mm)
    if inner_size_mm <= 0:
        raise ValueError(
            "Requested fab size is too small for the configured frame margin. "
            "Increase --fab-size-in or reduce --dxf-frame-margin-mm."
        )
    return image_px * 25.4 / inner_size_mm


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

    dxf_dpi = 300.0
    if args.fab_size_in is not None:
        try:
            target_w_in, target_h_in = parse_fab_size_in(args.fab_size_in)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        if image_w != image_h:
            print(
                "Error: --fab-size-in requires a square source image. "
                f"Got {image_w}x{image_h} px from '{args.image}'."
            )
            return 1

        try:
            dxf_dpi = compute_dpi_for_outer_size(
                image_w,
                target_w_in,
                args.dxf_frame_margin_mm,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        print(
            "Using computed DXF DPI "
            f"{dxf_dpi:.6f} for outer size {target_w_in:g}x{target_h_in:g} in "
            f"with {args.dxf_frame_margin_mm:.2f} mm frame margin."
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
        "--dxf-setting-hole-diameter-mm",
        str(args.dxf_setting_hole_diameter_mm),
        "--dxf-setting-hole-inset-mm",
        str(args.dxf_setting_hole_inset_mm),
    ]

    if args.fab_size_in is not None:
        postprocessor_cmd.extend(["--dxf-dpi", f"{dxf_dpi:.12f}"])

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

    if run_step(postprocessor_cmd, "Postprocessor", run_log) != 0:
        return 1

    print(f"\nPipeline complete. Postprocessed output saved to '{post_output}'.")
    print(f"Final fabrication package saved to '{final_output}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
