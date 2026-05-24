import argparse
import os
import subprocess
import sys
from datetime import datetime


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
    final_output = build_output_dir("output_final", run_name, timestamp)

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
        "--finalize",
        "--run-name",
        run_name,
        "--final-dir",
        final_output,
    ]

    if run_step(postprocessor_cmd, "Postprocessor") != 0:
        return 1

    print(f"\nPipeline complete. Postprocessed output saved to '{post_output}'.")
    print(f"Final fabrication package saved to '{final_output}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
