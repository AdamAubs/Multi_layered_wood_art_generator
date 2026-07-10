import argparse
import os
import sys

if __package__ is None or __package__ == "":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from preview_tools.layer_composite import parse_background_color, render_composite_previews

def parse_args():
    parser = argparse.ArgumentParser(
        description="Render assembled preview images from transparent Layer_*.png files."
    )
    parser.add_argument(
        "final_dir",
        help="Path to the output_final_* directory.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for preview images (defaults to <final_dir>/previews).",
    )
    parser.add_argument(
        "--transparent-name",
        default="composite_transparent.png",
        help="Filename for the transparent assembled preview.",
    )
    parser.add_argument(
        "--background-name",
        default="composite_on_neutral_background.png",
        help="Filename for the neutral-background assembled preview.",
    )
    parser.add_argument(
        "--background-color",
        default="245,245,245",
        help="Neutral background color as R,G,B. Default: 245,245,245",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing preview files.",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    background_color = parse_background_color(args.background_color)

    result = render_composite_previews(
        final_dir=args.final_dir,
        output_dir=args.output_dir,
        transparent_name=args.transparent_name,
        background_name=args.background_name,
        background_color=background_color,
        force=args.force,
    )

    print("Detected layer draw order (bottom -> top):")
    for name in result["layer_order_desc"]:
        print(f"  {name}")

    width, height = result["image_size"]
    print(f"Final image dimensions: {width}x{height} px")
    print(f"Transparent composite: {result['transparent_path']}")
    print(f"Neutral-background composite: {result['background_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())