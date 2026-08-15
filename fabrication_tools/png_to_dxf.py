import argparse
import os

import cv2
import numpy as np

from fabrication_tools.settings import (
    DEFAULT_DXF_DPI,
    DEFAULT_FRAME_MARGIN_MM,
    DEFAULT_SETTING_HOLE_DIAMETER_MM,
    DEFAULT_SETTING_HOLE_INSET_MM,
    load_dxf_settings,
)


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
        default=None,
        help="DPI for px→mm conversion (defaults to package settings or 300).",
    )
    parser.add_argument(
        "--dpi-x",
        type=float,
        default=None,
        help="Horizontal DPI for px→mm conversion (defaults to --dpi or package settings).",
    )
    parser.add_argument(
        "--dpi-y",
        type=float,
        default=None,
        help="Vertical DPI for px→mm conversion (defaults to --dpi or package settings).",
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
        default=None,
        help="Extra margin in mm between the contour and outer frame (defaults to package settings or 5).",
    )
    parser.add_argument(
        "--frame-margin-x-mm",
        type=float,
        default=None,
        help="Horizontal margin in mm between the contour and outer frame.",
    )
    parser.add_argument(
        "--frame-margin-y-mm",
        type=float,
        default=None,
        help="Vertical margin in mm between the contour and outer frame.",
    )
    parser.add_argument(
        "--setting-hole-diameter-mm",
        type=float,
        default=None,
        help="Diameter in mm for the setting holes (defaults to package settings or 2.5).",
    )
    parser.add_argument(
        "--setting-hole-inset-mm",
        type=float,
        default=None,
        help="Inset in mm from frame corners to hole centers (defaults to package settings or 7).",
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
    dpi_x=None,
    dpi_y=None,
    dxf_version="R2000",
    add_frame=True,
    frame_color=2,
    frame_margin_mm=15.0,
    frame_margin_x_mm=None,
    frame_margin_y_mm=None,
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
    dpi_x = dpi if dpi_x is None else dpi_x
    dpi_y = dpi if dpi_y is None else dpi_y

    # --- Cut contours ---
    for cnt in contours:
        points = []
        for pt in cnt:
            x_px, y_px = float(pt[0][0]), float(pt[0][1])
            # Convert to mm; flip Y so origin is bottom-left (DXF convention)
            x_mm = px_to_mm(x_px, dpi_x)
            y_mm = px_to_mm(img_h - y_px, dpi_y)
            points.append((x_mm, y_mm))

        if len(points) >= 2:
            msp.add_lwpolyline(points, close=True, dxfattribs={"color": 1})

    w_mm = px_to_mm(img_w, dpi_x)
    h_mm = px_to_mm(img_h, dpi_y)
    frame_margin_x_mm = (
        frame_margin_mm if frame_margin_x_mm is None else frame_margin_x_mm
    )
    frame_margin_y_mm = (
        frame_margin_mm if frame_margin_y_mm is None else frame_margin_y_mm
    )
    frame_points = None

    # --- Outer frame rectangle ---
    # Draws a closed rectangle that sits outside the artwork by the requested margin.
    if add_frame:
        frame_points = [
            (-frame_margin_x_mm, -frame_margin_y_mm),
            (w_mm + frame_margin_x_mm, -frame_margin_y_mm),
            (w_mm + frame_margin_x_mm, h_mm + frame_margin_y_mm),
            (-frame_margin_x_mm, h_mm + frame_margin_y_mm),
        ]
        msp.add_lwpolyline(
            frame_points,
            close=True,
            dxfattribs={"color": frame_color},
        )

    if frame_points is None:
        frame_points = [
            (-frame_margin_x_mm, -frame_margin_y_mm),
            (w_mm + frame_margin_x_mm, -frame_margin_y_mm),
            (w_mm + frame_margin_x_mm, h_mm + frame_margin_y_mm),
            (-frame_margin_x_mm, h_mm + frame_margin_y_mm),
        ]

    add_setting_holes(
        msp,
        frame_points=frame_points,
        hole_inset_mm=setting_hole_inset_mm,
        hole_diameter_mm=setting_hole_diameter_mm,
    )

    doc.saveas(out_path)

def load_mask_image(png_path):
    img = cv2.imread(png_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Could not read: {png_path}")

    if img.ndim == 2:
        return img

    if img.ndim != 3:
        raise ValueError(f"Unsupported image shape for '{png_path}': {img.shape}")

    channels = img.shape[2]
    if channels == 4:
        return img[:, :, 3]

    if channels == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if channels == 1:
        return img[:, :, 0]

    raise ValueError(
        f"Unsupported channel count for '{png_path}': expected 1, 3, or 4 channels, got shape {img.shape}"
    )

def main():
    args = parse_args()
    package_settings = load_dxf_settings(os.path.dirname(os.path.abspath(args.png)))
    uniform_dpi_was_supplied = args.dpi is not None
    uniform_margin_was_supplied = args.frame_margin_mm is not None
    args.dpi = args.dpi if args.dpi is not None else package_settings.dpi
    args.dpi_x = (
        args.dpi_x
        if args.dpi_x is not None
        else (args.dpi if uniform_dpi_was_supplied else package_settings.dpi_x)
    )
    args.dpi_y = (
        args.dpi_y
        if args.dpi_y is not None
        else (args.dpi if uniform_dpi_was_supplied else package_settings.dpi_y)
    )
    args.frame_margin_mm = (
        args.frame_margin_mm
        if args.frame_margin_mm is not None
        else package_settings.frame_margin_mm
    )
    args.frame_margin_x_mm = (
        args.frame_margin_x_mm
        if args.frame_margin_x_mm is not None
        else (
            args.frame_margin_mm
            if uniform_margin_was_supplied
            else package_settings.frame_margin_x_mm
        )
    )
    args.frame_margin_y_mm = (
        args.frame_margin_y_mm
        if args.frame_margin_y_mm is not None
        else (
            args.frame_margin_mm
            if uniform_margin_was_supplied
            else package_settings.frame_margin_y_mm
        )
    )
    args.setting_hole_diameter_mm = (
        args.setting_hole_diameter_mm
        if args.setting_hole_diameter_mm is not None
        else package_settings.setting_hole_diameter_mm
    )
    args.setting_hole_inset_mm = (
        args.setting_hole_inset_mm
        if args.setting_hole_inset_mm is not None
        else package_settings.setting_hole_inset_mm
    )

    # img = cv2.imread(args.png, cv2.IMREAD_GRAYSCALE)
    # if img is None:
    #     raise FileNotFoundError(f"Could not read: {args.png}")
    img = load_mask_image(args.png)

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
        dpi_x=args.dpi_x,
        dpi_y=args.dpi_y,
        add_frame=not args.no_frame,
        frame_color=args.frame_color,
        frame_margin_mm=args.frame_margin_mm,
        frame_margin_x_mm=args.frame_margin_x_mm,
        frame_margin_y_mm=args.frame_margin_y_mm,
        setting_hole_diameter_mm=args.setting_hole_diameter_mm,
        setting_hole_inset_mm=args.setting_hole_inset_mm,
    )
    print(f"  Saved: {out_path}")
    if not args.no_frame:
        w_mm = px_to_mm(w, args.dpi_x)
        h_mm = px_to_mm(h, args.dpi_y)
        outer_w_mm = w_mm + 2.0 * args.frame_margin_x_mm
        outer_h_mm = h_mm + 2.0 * args.frame_margin_y_mm
        print(
            f"  Frame: {outer_w_mm:.2f} mm × {outer_h_mm:.2f} mm "
            f"(margins {args.frame_margin_x_mm:.2f} mm horizontal, "
            f"{args.frame_margin_y_mm:.2f} mm vertical, color index {args.frame_color})"
        )
    print(
        f"  Setting holes: 2 × {args.setting_hole_diameter_mm:.2f} mm "
        f"(inset {args.setting_hole_inset_mm:.2f} mm from the frame corners)"
    )


if __name__ == "__main__":
    main()