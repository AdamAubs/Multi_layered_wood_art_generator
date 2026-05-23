import argparse
import os

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a single PNG mask to a DXF cut file."
    )
    parser.add_argument("--png", required=True, help="Path to the PNG mask.")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (defaults to PNG directory).",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=300.0,
        help="DPI for px→mm conversion.",
    )
    parser.add_argument(
        "--simplify",
        type=float,
        default=0.5,
        help="Contour simplification epsilon in px.",
    )
    parser.add_argument(
        "--cut-white",
        action="store_true",
        default=True,
        help="Extract contours of WHITE (void) regions — what the laser cuts.",
    )
    parser.add_argument(
        "--no-frame",
        action="store_true",
        default=False,
        help="Omit the outer frame rectangle.",
    )
    parser.add_argument(
        "--frame-color",
        type=int,
        default=2,
        help="ACI color index for the frame rectangle (default 2 = yellow, distinct from cut lines).",
    )
    
    return parser.parse_args()


def px_to_mm(px, dpi):
    return px * 25.4 / dpi


def extract_cut_contours(mask_gray, cut_white=True, simplify_epsilon=0.5):
    """
    Extract the contours that the laser should cut.
    cut_white=True:  laser cuts the white (void) regions → invert mask, find contours of voids.
    cut_white=False: laser cuts the black regions → find contours of solid.
    """
    _, binary = cv2.threshold(mask_gray, 127, 255, cv2.THRESH_BINARY)

    if cut_white:
        # Invert so white becomes the "objects" for findContours
        target = cv2.bitwise_not(binary)
    else:
        target = binary

    contours, _ = cv2.findContours(target, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    simplified = []
    for cnt in contours:
        if simplify_epsilon > 0:
            cnt = cv2.approxPolyDP(cnt, simplify_epsilon, closed=True)
        if len(cnt) >= 3:
            simplified.append(cnt)

    return simplified


def write_dxf(
    contours,
    out_path,
    img_h,
    img_w,
    dpi,
    dxf_version="R2000",
    add_frame=True,
    frame_color=2,
):
    """Write contours as LWPOLYLINE entities plus an optional frame rectangle."""
    try:
        import ezdxf
    except ImportError:
        raise ImportError("ezdxf is required: pip install ezdxf")

    doc = ezdxf.new(dxf_version)
    # Explicitly set units to Millimeters
    doc.header['$INSUNITS'] = 4
    msp = doc.modelspace()

    # --- Cut contours ---
    for cnt in contours:
        points = []
        for pt in cnt:
            x_px, y_px = float(pt[0][0]), float(pt[0][1])
            # Convert to mm; flip Y so origin is bottom-left (DXF convention)
            x_mm = px_to_mm(x_px, dpi)
            y_mm = px_to_mm(img_h - y_px, dpi)
            points.append((x_mm, y_mm))

        if len(points) >= 2:
            msp.add_lwpolyline(points, close=True, dxfattribs={"color": 1})

    # --- Outer frame rectangle ---
    # Draws a closed rectangle that exactly matches the image boundary,
    # so every layer sheet shares the same outer edge for alignment.
    if add_frame:
        w_mm = px_to_mm(img_w, dpi)
        h_mm = px_to_mm(img_h, dpi)

        frame_points = [
            (0.0,  0.0),
            (w_mm, 0.0),
            (w_mm, h_mm),
            (0.0,  h_mm),
        ]
        msp.add_lwpolyline(
            frame_points,
            close=True,
            dxfattribs={"color": frame_color},
        )

    doc.saveas(out_path)


def main():
    args = parse_args()

    img = cv2.imread(args.png, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Could not read: {args.png}")

    h, w = img.shape

    contours = extract_cut_contours(
        img,
        cut_white=args.cut_white,
        simplify_epsilon=args.simplify,
    )
    print(f"  Found {len(contours)} contours in {os.path.basename(args.png)}")

    out_dir = args.out_dir or os.path.dirname(args.png) or "."
    os.makedirs(out_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(args.png))[0]
    out_path = os.path.join(out_dir, f"{base}.dxf")

    write_dxf(
        contours,
        out_path,
        img_h=h,
        img_w=w,
        dpi=args.dpi,
        add_frame=not args.no_frame,
        frame_color=args.frame_color,
    )
    print(f"  Saved: {out_path}")
    if not args.no_frame:
        w_mm = px_to_mm(w, args.dpi)
        h_mm = px_to_mm(h, args.dpi)
        print(f"  Frame: {w_mm:.2f} mm × {h_mm:.2f} mm (color index {args.frame_color})")


if __name__ == "__main__":
    main()