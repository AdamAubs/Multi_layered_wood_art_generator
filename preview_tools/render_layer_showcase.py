import argparse
import os
import sys

if __package__ is None or __package__ == "":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from preview_tools.layer_composite import parse_background_color
from preview_tools.layer_showcase import render_showcase_previews

def parse_args():
    parser = argparse.ArgumentParser(
        description="Render showcase-style digital asset previews from Layer_*.png files."
    )
    parser.add_argument(
        "final_dir",
        help="Path to output_final_* directory.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <final_dir>/previews/showcase).",
    )
    parser.add_argument(
        "--background-color",
        default="245,245,245",
        help="Neutral background color as R,G,B.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing showcase preview files.",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    background_color = parse_background_color(args.background_color)

    result = render_showcase_previews(
        final_dir=args.final_dir,
        output_dir=args.output_dir,
        force=args.force,
        background_color=background_color,
    )

    print("Showcase layer order (bottom -> top):")
    for name in result["layer_order_desc"]:
        print(f"  {name}")

    print(f"Assembled size: {result['assembled_size'][0]}x{result['assembled_size'][1]} px")
    print(f"Fan showcase size: {result['fan_size'][0]}x{result['fan_size'][1]} px")
    print(f"Side-by-side size: {result['compare_size'][0]}x{result['compare_size'][1]} px")
    print(f"Fan transparent: {result['fan_path']}")
    print(f"Fan neutral background: {result['fan_bg_path']}")
    print(f"Compare transparent: {result['compare_path']}")
    print(f"Compare neutral background: {result['compare_bg_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())