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
    parser.add_argument(
        "--frame-margin-mm",
        type=float,
        default=20.0,
        help="Extra margin in mm between the contour and the outer frame.",
    )
    parser.add_argument(
        "--setting-hole-diameter-mm",
        type=float,
        default=2.5,
        help="Diameter in mm for the two corner setting holes.",
    )
    parser.add_argument(
        "--setting-hole-inset-mm",
        type=float,
        default=10.0,
        help="Inset in mm from each outer frame corner to the hole center.",
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

    image_area = float(mask_gray.shape[0] * mask_gray.shape[1])

    simplified = []
    for cnt in contours:
        if simplify_epsilon > 0:
            cnt = cv2.approxPolyDP(cnt, simplify_epsilon, closed=True)
        x, y, w, h = cv2.boundingRect(cnt)
        touches_full_border = x <= 0 and y <= 0 and (x + w) >= mask_gray.shape[1] and (y + h) >= mask_gray.shape[0]
        if touches_full_border and cv2.contourArea(cnt) >= 0.98 * image_area:
            continue
        if len(cnt) >= 3:
            simplified.append(cnt)

    return simplified


def add_setting_holes(msp, frame_points, hole_inset_mm, hole_diameter_mm):
    radius_mm = hole_diameter_mm / 2.0
    xs = [point[0] for point in frame_points]
    ys = [point[1] for point in frame_points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    hole_centers = [
        (min_x + hole_inset_mm, max_y - hole_inset_mm),
        (max_x - hole_inset_mm, max_y - hole_inset_mm),
        (min_x + hole_inset_mm, min_y + hole_inset_mm),
        (max_x - hole_inset_mm, min_y + hole_inset_mm),
    ]
    for center_x_mm, center_y_mm in hole_centers:
        msp.add_circle((center_x_mm, center_y_mm), radius_mm, dxfattribs={"color": 1})


def write_dxf(
    contours,
    out_path,
    img_h,
    img_w,
    dpi,
    dxf_version="R2000",
    add_frame=True,
    frame_color=2,
    frame_margin_mm=20.0,
    setting_hole_diameter_mm=2.5,
    setting_hole_inset_mm=10.0,
):
    """Write contours as LWPOLYLINE entities plus an optional frame rectangle."""
    try:
        import ezdxf
    except ImportError:
        raise ImportError("ezdxf is required: pip install ezdxf")

    doc = ezdxf.new(dxf_version)  # type: ignore[attr-defined]
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

    w_mm = px_to_mm(img_w, dpi)
    h_mm = px_to_mm(img_h, dpi)
    frame_points = None

    # --- Outer frame rectangle ---
    # Draws a closed rectangle that sits outside the artwork by the requested margin.
    if add_frame:
        frame_points = [
            (-frame_margin_mm, -frame_margin_mm),
            (w_mm + frame_margin_mm, -frame_margin_mm),
            (w_mm + frame_margin_mm, h_mm + frame_margin_mm),
            (-frame_margin_mm, h_mm + frame_margin_mm),
        ]
        msp.add_lwpolyline(
            frame_points,
            close=True,
            dxfattribs={"color": frame_color},
        )

    if frame_points is None:
        frame_points = [
            (-frame_margin_mm, -frame_margin_mm),
            (w_mm + frame_margin_mm, -frame_margin_mm),
            (w_mm + frame_margin_mm, h_mm + frame_margin_mm),
            (-frame_margin_mm, h_mm + frame_margin_mm),
        ]

    add_setting_holes(
        msp,
        frame_points=frame_points,
        hole_inset_mm=setting_hole_inset_mm,
        hole_diameter_mm=setting_hole_diameter_mm,
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
        frame_margin_mm=args.frame_margin_mm,
        setting_hole_diameter_mm=args.setting_hole_diameter_mm,
        setting_hole_inset_mm=args.setting_hole_inset_mm,
    )
    print(f"  Saved: {out_path}")
    if not args.no_frame:
        w_mm = px_to_mm(w, args.dpi)
        h_mm = px_to_mm(h, args.dpi)
        outer_w_mm = w_mm + 2.0 * args.frame_margin_mm
        outer_h_mm = h_mm + 2.0 * args.frame_margin_mm
        print(
            f"  Frame: {outer_w_mm:.2f} mm × {outer_h_mm:.2f} mm "
            f"(margin {args.frame_margin_mm:.2f} mm, color index {args.frame_color})"
        )
    print(
        f"  Setting holes: 2 × {args.setting_hole_diameter_mm:.2f} mm "
        f"(inset {args.setting_hole_inset_mm:.2f} mm from the frame corners)"
    )


if __name__ == "__main__":
    main()