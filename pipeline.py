import argparse
import os
import subprocess
import sys
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run preprocessor -> generator -> postprocessor in one command."
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
        "--export-dxf",
        action="store_true",
        help="Export merged masks as a DXF with one layer per mask.",
    )
    parser.add_argument(
        "--dxf-path",
        default=None,
        help="Output DXF file path (defaults to <out-dir>/<run>_layers.dxf).",
    )
    parser.add_argument(
        "--dxf-version",
        choices=["R12", "R2000", "R2010", "R2013"],
        default="R12",
        help="DXF version to write.",
    )
    parser.add_argument(
        "--dxf-units",
        choices=["mm", "in", "px"],
        default="mm",
        help="DXF units; mm and in use the DPI scale, px is unitless.",
    )
    parser.add_argument(
        "--dxf-dpi",
        type=float,
        default=300.0,
        help="DPI to convert pixels to mm or inches.",
    )
    parser.add_argument(
        "--dxf-simplify-epsilon",
        type=float,
        default=0.0,
        help="Optional contour simplification epsilon in pixels.",
    )
    parser.add_argument(
        "--dxf-layout",
        choices=["stacked", "row", "grid"],
        default="grid",
        help="Layout for DXF layers (stacked overlays, or spread into row/grid).",
    )
    parser.add_argument(
        "--dxf-spacing",
        type=float,
        default=5.0,
        help="Spacing between layouts in DXF units.",
    )
    parser.add_argument(
        "--dxf-columns",
        type=int,
        default=0,
        help="Column count for grid layout (0 = auto).",
    )
    parser.add_argument(
        "--dxf-no-frame",
        action="store_true",
        help="Do not include the frame outline with each layer.",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Append a YYYYMMDD_HHMMSS timestamp to generator/postprocessor outputs.",
    )
    return parser.parse_args()


def derive_run_name(image_path):
    filename = os.path.basename(image_path)
    run_name, _ = os.path.splitext(filename)
    return run_name


def build_output_dir(prefix, run_name, timestamp):
    base = f"{prefix}_{run_name}"
    return f"{base}_{timestamp}" if timestamp else base


def run_step(command, label):
    print(f"\n--- {label} ---")
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"[!] {label} failed with exit code {result.returncode}")
    return result.returncode


def main():
    args = parse_args()
    run_name = derive_run_name(args.image)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") if args.timestamp else None

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

    if run_step(preprocessor_cmd, "Preprocessor") != 0:
        return 1

    generator_cmd = [
        python,
        "generator.py",
        "--in-dir",
        args.pre_out_dir,
        "--out-dir",
        generator_output,
    ]

    if run_step(generator_cmd, "Generator") != 0:
        return 1

    postprocessor_cmd = [
        python,
        "postprocessor.py",
        "--in-dir",
        generator_output,
        "--out-dir",
        post_output,
    ]

    if args.export_dxf:
        postprocessor_cmd.append("--export-dxf")
        if args.dxf_path:
            postprocessor_cmd.extend(["--dxf-path", args.dxf_path])
        postprocessor_cmd.extend(["--dxf-version", args.dxf_version])
        postprocessor_cmd.extend(["--dxf-units", args.dxf_units])
        postprocessor_cmd.extend(["--dxf-dpi", str(args.dxf_dpi)])
        postprocessor_cmd.extend(
            ["--dxf-simplify-epsilon", str(args.dxf_simplify_epsilon)]
        )
        postprocessor_cmd.extend(["--dxf-layout", args.dxf_layout])
        postprocessor_cmd.extend(["--dxf-spacing", str(args.dxf_spacing)])
        postprocessor_cmd.extend(["--dxf-columns", str(args.dxf_columns)])
        if args.dxf_no_frame:
            postprocessor_cmd.append("--dxf-no-frame")

    if run_step(postprocessor_cmd, "Postprocessor") != 0:
        return 1

    print(f"\nPipeline complete. Output saved to '{post_output}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
