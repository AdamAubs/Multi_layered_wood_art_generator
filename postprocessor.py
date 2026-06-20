import argparse
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np
import re
import shutil


def parse_args():
    parser = argparse.ArgumentParser(
        description="Post-process generator outputs to merge tiny visible layers."
    )
    parser.add_argument(
        "--in-dir",
        default=None,
        help="Generator output directory to process.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to write postprocessed layers.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Override run name for input/output directories.",
    )
    parser.add_argument(
        "--run-log",
        default=None,
        help="Optional path to a pipeline run log to use as the formatted runtime log.",
    )
    parser.add_argument(
        "--meta-dir",
        default="preprocessor_output",
        help="Directory containing run_metadata.json for default naming.",
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
        "--dxf-include-frame",
        action="store_true",
        help="Include the frame outline with every layer.",
    )
    parser.add_argument(
        "--dxf-no-frame",
        dest="dxf_include_frame",
        action="store_false",
        help="Do not include the frame outline with each layer.",
    )
    parser.add_argument(
        "--dxf-frame-margin-mm",
        type=float,
        default=15.0,
        help="Extra margin in mm between each layer contour and its outer frame.",
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
        "--stock-size-in",
        default=None,
        help="Optional stock sheet size in inches as WxH (e.g. 12x20). When provided, finalize also refreshes layout-cut-generator DXFs.",
    )
    parser.add_argument(
        "--layout-gap-mm",
        type=float,
        default=5.0,
        help="Gap in mm to use when generating combined stock layout DXFs.",
    )
    parser.add_argument(
        "--stress-analysis", action="store_true", default=False,
        help="Run FEA stress analysis and widen weak members (paper Section 3.5).",
    )
    parser.add_argument(
        "--stress-beta", type=float, default=20.0,
        help="Stress threshold β in MPa. Members above this are widened. Default: 20.",
    )
    parser.add_argument(
        "--stress-fea-size", type=int, default=100,
        help="Downsample each mask to this max dimension before FEA. "
             "Higher = more accurate but slower. Default: 100.",
    )
    parser.add_argument(
        "--stress-thickness-mm", type=float, default=3.0,
        help="Physical layer thickness in mm (paper uses 3 mm). Default: 3.",
    )
    parser.add_argument(
        "--stress-sheet-mm", type=float, default=400.0,
        help="Physical sheet side length in mm (paper uses 400 mm). Default: 400.",
    )
    parser.add_argument(
        "--stress-max-iters", type=int, default=10,
        help="Maximum widening iterations per layer. Default: 10.",
    )
    parser.add_argument(
        "--stress-save-maps", action="store_true", default=False,
        help="Save per-layer stress maps as PNG images for inspection.",
    )
    parser.add_argument(
        "--bridge-support",
        action="store_true",
        default=False,
        help="Bridge small gaps from islands to their supporting layers.",
    )
    parser.add_argument(
        "--bridge-gap-px",
        type=int,
        default=30,
        help="Max pixel gap to bridge to support (conservative). Default: 6.",
    )
    parser.add_argument(
        "--bridge-max-bridges",
        type=int,
        default=8,
        help="Max bridges per layer (0 = unlimited). Default: 8.",
    )
    parser.add_argument(
        "--debug-stress",
        action="store_true",
        default=False,
        help="Print per-iteration stress debug counts to stdout.",
    )
    parser.add_argument(
        "--debug-bridge",
        action="store_true",
        default=False,
        help="Print bridge diagnostics to stdout.",
    )
    parser.add_argument(
        "--thin-min-width",
        type=int,
        default=4,
        help="Members narrower than this (px) are considered thin. Default: 4.",
    )
    parser.add_argument(
        "--thin-widen-to",
        type=int,
        default=None,
        help="Target width in px after widening thin members. "
            "Defaults to --thin-min-width if not set.",
    )
    parser.add_argument(
        "--merge-visible-fraction",
        type=float,
        default=0.01,
        help="Merge layers whocse visible area is below this fraction of total image pixels (0 < value < 1).",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Create a fabrication-ready package (PNG + per-layer DXF + handoff.md).",
    )
    parser.add_argument(
        "--final-dir",
        default=None,
        help="Explicit final output directory (defaults to output_final_{run_name}).",
    )
    parser.add_argument(
        "--no-color-names",
        dest="use_color_names",
        action="store_false",
        help="Do not attempt to generate friendly color names; use explicit RGB/LAB codes in filenames.",
    )
    parser.add_argument(
        "--include-intermediates",
        action="store_true",
        default=False,
        help="Include intermediate files (frame.npy, layer_order.npy, run_metadata.json) in final package.",
    )

    parser.set_defaults(dxf_include_frame=True)
    return parser.parse_args()

# ---------------------------------------------------------------------------
# Directory / metadata helpers 
# ---------------------------------------------------------------------------

def load_run_metadata(meta_dir):
    metadata_path = os.path.join(meta_dir, "run_metadata.json")
    if not os.path.exists(metadata_path):
        return None
    with open(metadata_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_run_name(args):
    if args.run_name:
        return args.run_name
    metadata = load_run_metadata(args.meta_dir)
    if metadata and metadata.get("run_name"):
        return metadata["run_name"]
    return None


def resolve_dirs(args, run_name):
    input_dir = args.in_dir
    if not input_dir and run_name:
        postprocessed_dir = f"output_postprocessed_{run_name}"
        generator_dir = f"output_generator_{run_name}"
        if args.finalize and os.path.exists(postprocessed_dir):
            input_dir = postprocessed_dir
        else:
            input_dir = generator_dir

    output_dir = args.out_dir
    if not output_dir and run_name:
        output_dir = f"output_postprocessed_{run_name}"

    return input_dir, output_dir


def parse_stock_size_in(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*", value)
    if not match:
        raise ValueError("--stock-size-in must use WxH format such as 12x20.")

    width_in = float(match.group(1))
    height_in = float(match.group(2))
    if width_in <= 0 or height_in <= 0:
        raise ValueError("--stock-size-in values must be greater than zero.")
    return width_in, height_in


def refresh_layout_cut_generator(final_dir, stock_size_in, gap_mm, run_log=None):
    layout_script = os.path.join(os.path.dirname(__file__), "layout_cut_generator.py")
    layout_cmd = [
        sys.executable,
        layout_script,
        "--dir",
        final_dir,
        "--stock-size-in",
        stock_size_in,
        "--gap-mm",
        str(gap_mm),
    ]
    print("\nRefreshing layout-cut-generator DXFs...")
    result = subprocess.run(layout_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if run_log:
        with open(run_log, "a", encoding="utf-8") as handle:
            handle.write("\n\n=== Layout-Cut-Generator refresh started ===\n")
            handle.write(" ".join(layout_cmd) + "\n")
            handle.write(result.stdout)
            handle.write(f"\n=== Layout-Cut-Generator refresh exited with code {result.returncode} ===\n")
    else:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(f"Warning: layout cut generator refresh failed with exit code {result.returncode}")
    return result.returncode


def infer_layout_refresh_config(final_dir):
    metadata_path = os.path.join(final_dir, "layout-cut-generator_metadata.json")
    if not os.path.exists(metadata_path):
        return None
    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        stock_mm = metadata.get("stock_mm")
        if not (isinstance(stock_mm, list) and len(stock_mm) == 2):
            return None
        stock_w_in = float(stock_mm[0]) / 25.4
        stock_h_in = float(stock_mm[1]) / 25.4
        gap_mm = float(metadata.get("gap_mm", 5.0))
        return f"{stock_w_in:g}x{stock_h_in:g}", gap_mm
    except Exception:
        return None


def resolve_dxf_path(args, run_name, output_dir):
    if args.dxf_path:
        return args.dxf_path
    filename = f"{run_name}_layers.dxf" if run_name else "layers.dxf"
    return os.path.join(output_dir, filename)

# ---------------------------------------------------------------------------
# Layer loading / reconstruction 
# ---------------------------------------------------------------------------

def load_generator_outputs(input_dir):
    try:
        layer_order = np.load(os.path.join(input_dir, "layer_order.npy")).tolist()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Error: Could not find layer_order.npy in '{input_dir}'."
        )
    try:
        frame = np.load(os.path.join(input_dir, "frame.npy"))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Error: Could not find frame.npy in '{input_dir}'."
        )
    return layer_order, frame


def load_cumulative_zones(input_dir, layer_order):
    cumulative_zones = []
    for i, color_id in enumerate(layer_order):
        path = os.path.join(input_dir, f"Layer_{i:02d}_Color_{color_id}.png")
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"Error: Could not load {path}.")
        cumulative_zones.append(img)
    return cumulative_zones


def reconstruct_individual_masks(cumulative_zones, frame):
    individual_masks = []
    prev = frame.copy()
    for cumulative in cumulative_zones:
        mask = cv2.bitwise_xor(cumulative, prev)
        individual_masks.append(mask)
        prev = cumulative
    return individual_masks


def compute_visible_regions(individual_masks, frame):
    h, w = frame.shape
    visible_masks = []
    visible_areas = []
    cumulative_upper = np.zeros((h, w), dtype=np.uint8)

    for mask in individual_masks:
        visible = cv2.bitwise_and(mask, cv2.bitwise_not(cumulative_upper))
        visible_masks.append(visible)
        visible_areas.append(int(np.sum(visible > 0)))
        cumulative_upper = cv2.bitwise_or(cumulative_upper, mask)

    return visible_masks, visible_areas


def find_merge_target(orphan_idx, color_id, colors, count):
    for j in range(orphan_idx - 1, -1, -1):
        if colors[j] == color_id:
            return j
    for j in range(orphan_idx + 1, count):
        if colors[j] == color_id:
            return j
    return None


def recompute_visible_areas(masks, frame_mask):
    visible_areas = []
    upper = np.zeros_like(frame_mask)
    for mask in masks:
        visible = cv2.bitwise_and(mask, cv2.bitwise_not(upper))
        visible_areas.append(int(np.sum(visible > 0)))
        upper = cv2.bitwise_or(upper, mask)
    return visible_areas

# ---------------------------------------------------------------------------
# Merging (unchanged)
# ---------------------------------------------------------------------------

def merge_small_layers(individual_masks, layer_order, frame, epsilon):
    working_masks  = [m.copy() for m in individual_masks]
    working_colors = list(layer_order)
    merge_occurred = True
    merge_round    = 0

    while merge_occurred:
        merge_occurred = False
        merge_round   += 1
        areas     = recompute_visible_areas(working_masks, frame)
        n_current = len(working_masks)

        print(f"\n--- Merge round {merge_round} ({n_current} layers) ---")
        for i in range(n_current):
            if areas[i] < epsilon:
                color_id   = working_colors[i]
                target_idx = find_merge_target(i, color_id, working_colors, n_current)
                if target_idx is None:
                    print(f"  Layer {i:02d} (Color {color_id}): no same-color target, keeping.")
                    continue
                direction = "above" if target_idx < i else "below"
                print(f"  Merging Layer {i:02d} (Color {color_id}, {areas[i]} px) "
                      f"-> Layer {target_idx:02d} ({direction})")
                working_masks[target_idx] = cv2.bitwise_or(
                    working_masks[target_idx], working_masks[i])
                working_masks.pop(i)
                working_colors.pop(i)
                merge_occurred = True
                break

    return working_masks, working_colors

# ---------------------------------------------------------------------------
# Widening thin connections 
# ---------------------------------------------------------------------------

def find_thin_connections(mask, min_width_px=3):
    """
    Find pixels where the solid region is narrower than min_width_px.
    Uses distance transform: each pixel's value = distance to nearest void.
    Pixels where this distance < min_width_px/2 are thin members.
    Returns a binary mask of thin regions.
    """
    binary = (mask > 0).astype(np.uint8)
    # Distance transform gives each solid pixel its distance to nearest void
    dist = cv2.distanceTransform(binary * 255, cv2.DIST_L2, 5)
    # Pixels with distance < half the minimum width are dangerously thin
    thin = (dist < min_width_px / 2.0) & (binary > 0)
    return thin.astype(np.uint8) * 255

def widen_thin_connections(mask, frame, min_width_px=3, widen_to_px=None):
    """
    Widen any solid member narrower than min_width_px.
    widen_to_px controls the target width after dilation.
    If None, defaults to min_width_px (old behaviour).
    """
    thin = find_thin_connections(mask, min_width_px)
    if not np.any(thin):
        return mask

    target_width = widen_to_px if widen_to_px is not None else min_width_px
    kernel_r = max(1, target_width // 2)
    kernel_size = kernel_r * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    widened_thin = cv2.dilate(thin, kernel)
    result = cv2.bitwise_or(mask, widened_thin)
    result = cv2.bitwise_and(result, cv2.bitwise_not(frame))
    return result


def _sanitize_label(s):
    # Replace non-alphanumeric characters with underscore and trim
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^0-9A-Za-z_\-]", "", s)
    return s or "unnamed"


def _rgb_to_lab(rgb):
    # rgb is [R,G,B] 0-255; convert to LAB using OpenCV (BGR input)
    bgr = np.uint8([[[int(rgb[2]), int(rgb[1]), int(rgb[0])]]])
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[0, 0].tolist()
    return [int(lab[0]), int(lab[1]), int(lab[2])]


def _css3_candidates():
    # Prefer the full CSS3/X11 color name set when `webcolors` is installed.
    # This greatly improves friendly-name accuracy for a wider palette.
    try:
        import webcolors

        candidates = {}
        for name, hexval in webcolors.CSS3_NAMES_TO_HEX.items():
            # hexval like '#RRGGBB' -> convert to (R,G,B)
            h = hexval.lstrip('#')
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            candidates[name] = (r, g, b)
        return candidates
    except Exception:
        # Minimal fallback set if webcolors not available.
        return {
            "white": (255, 255, 255),
            "black": (0, 0, 0),
            "red": (255, 0, 0),
            "green": (0, 128, 0),
            "blue": (0, 0, 255),
            "yellow": (255, 255, 0),
            "cyan": (0, 255, 255),
            "magenta": (255, 0, 255),
            "orange": (255, 165, 0),
            "brown": (165, 42, 42),
            "gray": (128, 128, 128),
            "pink": (255, 192, 203),
            "purple": (128, 0, 128),
        }


def _nearest_friendly_name(cluster_lab):
    # cluster_lab: [L,a,b]
    candidates = _css3_candidates()
    best_name = None
    best_dist = float("inf")
    # Find nearest candidate in LAB space
    for name, rgb in candidates.items():
        lab = _rgb_to_lab(rgb)
        d = (cluster_lab[0] - lab[0]) ** 2 + (cluster_lab[1] - lab[1]) ** 2 + (cluster_lab[2] - lab[2]) ** 2
        if d < best_dist:
            best_dist = d
            best_name = name

    # Preserve obvious black/white matches when lightness is extreme.
    try:
        L = float(cluster_lab[0])
        a = float(cluster_lab[1])
        b = float(cluster_lab[2])
    except Exception:
        L = 127.0
        a = b = 0.0

    # Very dark -> black; very light -> white (LAB L is 0-255 here via OpenCV)
    if L <= 8.0:
        return "black"
    if L >= 240.0:
        return "white"

    chroma = (a * a + b * b) ** 0.5

    # If the cluster is chromatic but the nearest name is black/white,
    # prefer a non-black/white candidate (avoid mapping desaturated chroma to black).
    if best_name in ("black", "white") and chroma > 12.0:
        alt_name = None
        alt_dist = float("inf")
        for name, rgb in candidates.items():
            if name in ("black", "white"):
                continue
            lab = _rgb_to_lab(rgb)
            d = (cluster_lab[0] - lab[0]) ** 2 + (cluster_lab[1] - lab[1]) ** 2 + (cluster_lab[2] - lab[2]) ** 2
            if d < alt_dist:
                alt_dist = d
                alt_name = name
        if alt_name:
            return alt_name

    return best_name


def _colorize_white_mask(mask_gray, rgb):
    """Return a BGR image where only white mask pixels are colorized.

    - mask_gray: uint8 single-channel mask (0/255 expected)
    - rgb: [R, G, B]
    """
    # Pick a high-contrast background so very dark/light fills remain visible.
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    bg_val = 255 if luminance < 128 else 0

    out = np.full((mask_gray.shape[0], mask_gray.shape[1], 3), bg_val, dtype=np.uint8)
    # OpenCV writes/reads color as BGR.
    bgr = (b, g, r)
    out[mask_gray == 255] = bgr
    return out

# ---------------------------------------------------------------------------
# Stress analysis: 2-D plane stress FEM
# ---------------------------------------------------------------------------
#
# Physical model (matches paper Section 3.5):
#   - Material:  E = 7.2 GPa, ν = 0.3, ρ = 500 kg/m³
#   - Loading:   gravity body force (−Y direction in physical coords)
#   - BCs:       zero displacement on all frame-boundary nodes (clamped)
#   - Criterion: von Mises stress > β → widen the element
#
# Implementation:
#   1. Downsample mask to FEA_SIZE for practical runtimes.
#   2. Build bilinear quad (Q4) plane-stress stiffness matrix via 2×2 Gauss.
#   3. Assemble global K and gravity load vector f (vectorised COO).
#   4. Apply zero-displacement BCs on boundary nodes.
#   5. Solve K·u = f with scipy sparse solver.
#   6. Compute von Mises stress per element (average over Gauss points).
#   7. Upsample stress map to original resolution.
#   8. Dilate high-stress region; OR into mask; repeat until converged.
#
# ---------------------------------------------------------------------------

def _ke_plane_stress(E, nu, h_el, t):
    """
    8×8 element stiffness matrix for a square bilinear quad in plane stress.
    h_el = side length [m],  t = thickness [m].
    Node order: TL, TR, BR, BL  (in image / row-major sense).
    """
    c  = E * t / (1.0 - nu * nu)
    gp = 1.0 / math.sqrt(3.0)
    gauss_pts = [(-gp, -gp), (gp, -gp), (gp, gp), (-gp, gp)]
    K = np.zeros((8, 8))

    for xi, eta in gauss_pts:
        dN_dxi  = 0.25 * np.array([-(1-eta),  (1-eta),  (1+eta), -(1+eta)])
        dN_deta = 0.25 * np.array([-(1-xi),  -(1+xi),   (1+xi),   (1-xi)])

        # For a square element mapped from [−1,1]² to [0,h_el]²:
        # Jacobian is diagonal with value h_el/2; det(J) = (h_el/2)²
        inv_j   = 2.0 / h_el
        det_j   = (h_el / 2.0) ** 2

        dN_dx = dN_dxi  * inv_j
        dN_dy = dN_deta * inv_j

        # Strain-displacement matrix B (3×8)
        B = np.zeros((3, 8))
        for i in range(4):
            B[0, 2*i]   = dN_dx[i]   # ε_xx = ∂u/∂x
            B[1, 2*i+1] = dN_dy[i]   # ε_yy = ∂v/∂y
            B[2, 2*i]   = dN_dy[i]   # γ_xy = ∂u/∂y + ∂v/∂x
            B[2, 2*i+1] = dN_dx[i]

        D = c * np.array([
            [1,  nu, 0            ],
            [nu, 1,  0            ],
            [0,  0,  (1-nu)/2.0   ],
        ])

        # weight = 1 for each of the 4 Gauss points
        K += B.T @ D @ B * det_j

    return K


def _assemble(solid_mask, ke, h_el, t_m, rho, g):
    """
    Assemble global stiffness K and gravity load vector f (vectorised COO).
    Gravity acts in +row direction (downward in image coords).

    solid_mask : bool array (nr × nc),  True = solid element
    Returns K (scipy csr_matrix), f (ndarray, shape 2*(nr+1)*(nc+1))
    """
    from scipy import sparse

    nr, nc = solid_mask.shape
    n_nodes = (nr + 1) * (nc + 1)
    n_dof   = 2 * n_nodes

    er_arr, ec_arr = np.where(solid_mask)     # indices of solid elements

    if er_arr.size == 0:
        K = sparse.csr_matrix((n_dof, n_dof))
        return K, np.zeros(n_dof)

    # Node indices for each solid element (all vectorised)
    # TL, TR, BR, BL
    n0 = er_arr       * (nc + 1) + ec_arr          # TL
    n1 = er_arr       * (nc + 1) + ec_arr + 1      # TR
    n2 = (er_arr + 1) * (nc + 1) + ec_arr + 1      # BR
    n3 = (er_arr + 1) * (nc + 1) + ec_arr          # BL

    # DOF array: shape (n_elem, 8)
    dofs = np.column_stack([
        2*n0, 2*n0+1,
        2*n1, 2*n1+1,
        2*n2, 2*n2+1,
        2*n3, 2*n3+1,
    ])   # (n_elem, 8)

    # Build COO triplets for stiffness (n_elem * 64 entries)
    i_idx, j_idx = np.meshgrid(np.arange(8), np.arange(8), indexing='ij')
    # shape (64,)
    i_flat = i_idx.ravel()
    j_flat = j_idx.ravel()
    ke_flat = ke.ravel()          # (64,)

    rows = dofs[:, i_flat].ravel()   # (n_elem * 64,)
    cols = dofs[:, j_flat].ravel()
    vals = np.tile(ke_flat, len(er_arr))

    K = sparse.coo_matrix((vals, (rows, cols)), shape=(n_dof, n_dof)).tocsr()

    # Gravity body force (+row = downward physically)
    # Distributed equally to 4 nodes per element
    f_node = rho * t_m * h_el * h_el * g / 4.0    # [N] per node
    f = np.zeros(n_dof)
    # Y-DOF of each of the 4 nodes (+row direction)
    for node_arr in [n0, n1, n2, n3]:
        np.add.at(f, 2 * node_arr + 1, f_node)

    return K, f


def _apply_bcs(K, f, fixed_dofs):
    """Zero-displacement BCs via row/col zeroing + unit diagonal."""
    from scipy import sparse

    K = K.tolil()
    for d in fixed_dofs:
        K[d, :] = 0.0
        K[:, d] = 0.0
        K[d, d] = 1.0
        f[d]    = 0.0
    return K.tocsr(), f


def _fixed_dofs_frame(nr, nc):
    """Return list of DOFs for all boundary nodes (top/bottom rows, left/right cols)."""
    dofs = set()
    for r in range(nr + 1):
        for c in range(nc + 1):
            if r == 0 or r == nr or c == 0 or c == nc:
                n = r * (nc + 1) + c
                dofs.add(2 * n)
                dofs.add(2 * n + 1)
    return list(dofs)


def _fixed_dofs_with_support(solid_mask, support_mask):
    """
    Return fixed DOFs for support regions plus anchors for interior islands and
    unused nodes to avoid singular stiffness matrices.
    """
    nr, nc = solid_mask.shape
    fixed = set()

    if support_mask is None:
        fixed.update(_fixed_dofs_frame(nr, nc))
    else:
        sr_arr, sc_arr = np.where(support_mask)
        if sr_arr.size > 0:
            n0 = sr_arr       * (nc + 1) + sc_arr
            n1 = sr_arr       * (nc + 1) + sc_arr + 1
            n2 = (sr_arr + 1) * (nc + 1) + sc_arr + 1
            n3 = (sr_arr + 1) * (nc + 1) + sc_arr
            support_nodes = np.unique(np.concatenate([n0, n1, n2, n3]))
            for node in support_nodes:
                fixed.add(2 * node)
                fixed.add(2 * node + 1)

    if not np.any(solid_mask):
        n_nodes = (nr + 1) * (nc + 1)
        for node in range(n_nodes):
            fixed.add(2 * node)
            fixed.add(2 * node + 1)
        return list(fixed)

    # Fix any nodes not connected to a solid element.
    er_arr, ec_arr = np.where(solid_mask)
    n0 = er_arr       * (nc + 1) + ec_arr
    n1 = er_arr       * (nc + 1) + ec_arr + 1
    n2 = (er_arr + 1) * (nc + 1) + ec_arr + 1
    n3 = (er_arr + 1) * (nc + 1) + ec_arr
    used_nodes = set(np.concatenate([n0, n1, n2, n3]).tolist())
    n_nodes = (nr + 1) * (nc + 1)
    for node in range(n_nodes):
        if node not in used_nodes:
            fixed.add(2 * node)
            fixed.add(2 * node + 1)

    # Connected components over elements (not nodes).
    labels_count, labels = cv2.connectedComponents(
        solid_mask.astype(np.uint8), connectivity=4
    )
    for comp in range(1, labels_count):
        coords = np.column_stack(np.where(labels == comp))
        if coords.size == 0:
            continue

        if support_mask is None:
            touches_support = np.any(
                (coords[:, 0] == 0)
                | (coords[:, 0] == nr - 1)
                | (coords[:, 1] == 0)
                | (coords[:, 1] == nc - 1)
            )
        else:
            touches_support = np.any(support_mask[coords[:, 0], coords[:, 1]] > 0)

        if touches_support:
            continue

        # Anchor two distinct nodes in the island to remove rotation modes.
        r0, c0 = coords[0]
        r1, c1 = coords[-1]
        node_a = r0 * (nc + 1) + c0
        node_b = (r1 + 1) * (nc + 1) + (c1 + 1)
        if node_a == node_b:
            node_b = r0 * (nc + 1) + (c0 + 1 if c0 + 1 <= nc else c0)

        for node in (node_a, node_b):
            fixed.add(2 * node)
            fixed.add(2 * node + 1)

    return list(fixed)


def _von_mises_stress(u, solid_mask, E, nu, h_el):
    """
    Compute per-element von Mises stress (average over 4 Gauss points).
    Returns stress array (nr × nc) in Pascals; zero for void elements.
    """
    nr, nc   = solid_mask.shape
    c        = E / (1.0 - nu * nu)
    gp       = 1.0 / math.sqrt(3.0)
    gauss_pts = [(-gp, -gp), (gp, -gp), (gp, gp), (-gp, gp)]
    inv_j    = 2.0 / h_el

    D = c * np.array([
        [1,  nu, 0           ],
        [nu, 1,  0           ],
        [0,  0,  (1-nu)/2.0  ],
    ])

    er_arr, ec_arr = np.where(solid_mask)
    if er_arr.size == 0:
        return np.zeros((nr, nc))

    # Gather displacement vectors for all elements at once
    n0 = er_arr       * (nc + 1) + ec_arr
    n1 = er_arr       * (nc + 1) + ec_arr + 1
    n2 = (er_arr + 1) * (nc + 1) + ec_arr + 1
    n3 = (er_arr + 1) * (nc + 1) + ec_arr

    # u_e: shape (n_elem, 8)
    u_e = np.column_stack([
        u[2*n0],   u[2*n0+1],
        u[2*n1],   u[2*n1+1],
        u[2*n2],   u[2*n2+1],
        u[2*n3],   u[2*n3+1],
    ])

    sig_sum = np.zeros((len(er_arr), 3))  # [σ_xx, σ_yy, σ_xy] accumulated

    for xi, eta in gauss_pts:
        dN_dxi  = 0.25 * np.array([-(1-eta),  (1-eta),  (1+eta), -(1+eta)])
        dN_deta = 0.25 * np.array([-(1-xi),  -(1+xi),   (1+xi),   (1-xi)])
        dN_dx   = dN_dxi  * inv_j
        dN_dy   = dN_deta * inv_j

        # B matrix (3×8) — same for all elements (uniform mesh)
        B = np.zeros((3, 8))
        for i in range(4):
            B[0, 2*i]   = dN_dx[i]
            B[1, 2*i+1] = dN_dy[i]
            B[2, 2*i]   = dN_dy[i]
            B[2, 2*i+1] = dN_dx[i]

        # ε = B · u_e  →  (n_elem, 3)
        eps = u_e @ B.T          # shape (n_elem, 3)
        sig = eps @ D.T          # shape (n_elem, 3)
        sig_sum += sig

    sig_avg = sig_sum / 4.0      # average over 4 Gauss points
    s11, s22, s12 = sig_avg[:, 0], sig_avg[:, 1], sig_avg[:, 2]
    vm = np.sqrt(s11**2 - s11*s22 + s22**2 + 3*s12**2)

    sigma_vm = np.zeros((nr, nc))
    sigma_vm[er_arr, ec_arr] = vm
    return sigma_vm


def run_fea(mask_bin, support_mask, E, nu, rho, g, t_m, h_el):
    """
    Run one FEA pass on a binary mask.
    Returns von Mises stress map (same shape as mask_bin), units = Pa.
    """
    from scipy.sparse.linalg import spsolve

    nr, nc   = mask_bin.shape
    solid    = mask_bin > 0
    ke       = _ke_plane_stress(E, nu, h_el, t_m)
    K, f     = _assemble(solid, ke, h_el, t_m, rho, g)
    fixed    = _fixed_dofs_with_support(solid, support_mask)
    K, f     = _apply_bcs(K, f, fixed)

    try:
        u = spsolve(K, f)
    except Exception as exc:
        print(f"    [!] FEA solver error: {exc}. Returning zero stress.")
        return np.zeros((nr, nc))

    if not np.all(np.isfinite(u)):
        print("    [!] FEA solver returned non-finite displacements. "
              "Returning zero stress.")
        return np.zeros((nr, nc))

    return _von_mises_stress(u, solid, E, nu, h_el)


# def widen_weak_members_stress(
#     mask,
#     frame,
#     support_mask,
#     beta_pa,
#     fea_size,
#     E, nu, rho, t_m, sheet_m,
#     max_iters,
#     save_maps=False,
#     save_dir=None,
#     layer_name="",
#     debug=False,
# ):
#     """
#     Iteratively widen regions of `mask` where von Mises stress exceeds beta_pa.

#     Parameters
#     ----------
#     mask      : uint8 numpy array (H × W), 255 = solid wood, 0 = void
#     frame     : uint8 numpy array (H × W), the border frame mask
#     beta_pa   : stress threshold in Pa (e.g. 20e6 for 20 MPa)
#     fea_size  : max image dimension for FEA downsampling
#     E, nu, rho, t_m, sheet_m : material / geometry parameters
#     max_iters : maximum widening iterations
#     save_maps : if True, write stress PNG maps to save_dir
#     layer_name: label for print messages

#     Returns
#     -------
#     widened mask (same dtype/shape as input)
#     """
#     try:
#         from scipy.sparse.linalg import spsolve  # noqa: F401 – validate import early
#     except ImportError:
#         print("    [!] scipy not found. Install with: pip install scipy")
#         print("    [!] Skipping stress analysis for this layer.")
#         return mask

#     h_orig, w_orig = mask.shape
#     g = 9.81  # m/s²

#     # Downsample scale so the larger dimension ≤ fea_size
#     scale_down = min(fea_size / h_orig, fea_size / w_orig, 1.0)
#     fea_h = max(2, int(round(h_orig * scale_down)))
#     fea_w = max(2, int(round(w_orig * scale_down)))

#     # Physical element size at the FEA resolution
#     h_el = sheet_m / max(fea_w, fea_h)

#     # Widening kernel: 1 element = 1 pixel at FEA resolution, widened by 1 px
#     widen_kernel_fea = np.ones((3, 3), np.uint8)

#     current_mask = mask.copy()

#     for iteration in range(max_iters):
#         # --- Downsample current mask for FEA ---
#         mask_small = cv2.resize(
#             current_mask, (fea_w, fea_h),
#             interpolation=cv2.INTER_NEAREST
#         )
#         _, mask_small = cv2.threshold(mask_small, 127, 255, cv2.THRESH_BINARY)

#         support_small = None
#         if support_mask is not None:
#             support_small = cv2.resize(
#                 support_mask, (fea_w, fea_h),
#                 interpolation=cv2.INTER_NEAREST
#             )
#             _, support_small = cv2.threshold(
#                 support_small, 127, 255, cv2.THRESH_BINARY
#             )

#         # --- Run FEA ---
#         sigma_vm = run_fea(mask_small, support_small, E, nu, rho, g, t_m, h_el)

#         max_stress_pa = float(np.max(sigma_vm))
#         print(f"    iter {iteration+1}: max von Mises = {max_stress_pa/1e6:.2f} MPa "
#               f"(β = {beta_pa/1e6:.1f} MPa)")

#         # --- Save stress map if requested ---
#         if save_maps and save_dir:
#             os.makedirs(save_dir, exist_ok=True)
#             # Normalise to 0-255 for visualisation
#             vis_max = max(max_stress_pa, beta_pa)
#             vis = np.clip(sigma_vm / vis_max * 255, 0, 255).astype(np.uint8)
#             vis_color = cv2.applyColorMap(vis, cv2.COLORMAP_JET)
#             fname = f"{layer_name}_stress_iter{iteration+1:02d}.png"
#             cv2.imwrite(os.path.join(save_dir, fname), vis_color)

#         # --- Check convergence ---
#         if max_stress_pa <= beta_pa:
#             print(f"    Converged after {iteration+1} iteration(s).")
#             break

#         # --- Identify high-stress elements at FEA resolution ---
#         high_stress_small = (sigma_vm > beta_pa).astype(np.uint8) * 255

#         # Dilate high-stress region by 1 element to widen the member
#         high_stress_dilated = cv2.dilate(high_stress_small, widen_kernel_fea)

#         # --- Upsample to original resolution ---
#         high_stress_orig = cv2.resize(
#             high_stress_dilated, (w_orig, h_orig),
#             interpolation=cv2.INTER_NEAREST
#         )
#         _, high_stress_orig = cv2.threshold(high_stress_orig, 127, 255, cv2.THRESH_BINARY)

#         # --- Widen: OR the high-stress region into the current mask ---
#         new_mask = cv2.bitwise_or(current_mask, high_stress_orig)

#         # Do not grow outside the frame boundary
#         new_mask = cv2.bitwise_and(new_mask, cv2.bitwise_not(frame))

#         if debug:
#             high_count = int(np.count_nonzero(high_stress_small))
#             added = int(np.count_nonzero(new_mask) - np.count_nonzero(current_mask))
#             support_count = (
#                 int(np.count_nonzero(support_small)) if support_small is not None else 0
#             )
#             print(
#                 f"    debug: high_px={high_count}, added_px={max(0, added)}, "
#                 f"support_px={support_count}"
#             )

#         if np.array_equal(new_mask, current_mask):
#             print(f"    No change after widening — stopping early.")
#             break

#         current_mask = new_mask
#     else:
#         print(f"    Reached max iterations ({max_iters}). "
#               f"Max stress was {max_stress_pa/1e6:.2f} MPa.")

#     return current_mask

# ---------------------------------------------------------------------------
# DXF export 
# ---------------------------------------------------------------------------

def dxf_scale_from_args(dxf_units, dxf_dpi):
    if dxf_units == "px":
        return 1.0
    if dxf_dpi <= 0:
        raise ValueError("dxf_dpi must be > 0 when using mm or in units.")
    if dxf_units == "mm":
        return 25.4 / dxf_dpi
    return 1.0 / dxf_dpi


def mask_to_contours(mask, simplify_epsilon):
    binary = (mask > 0).astype(np.uint8) * 255
    method = cv2.CHAIN_APPROX_NONE if simplify_epsilon <= 0 else cv2.CHAIN_APPROX_SIMPLE
    contours, _ = cv2.findContours(binary, cv2.RETR_CCOMP, method)
    if simplify_epsilon > 0:
        simplified = []
        for contour in contours:
            approx = cv2.approxPolyDP(contour, simplify_epsilon, True)
            if len(approx) >= 3:
                simplified.append(approx)
        return simplified
    return [contour for contour in contours if len(contour) >= 3]


def contour_to_points(contour, height, scale, offset):
    pts = contour.reshape(-1, 2)
    offset_x, offset_y = offset
    return [
        (
            float(x) * scale + offset_x,
            float(height - 1 - y) * scale + offset_y,
        )
        for x, y in pts
    ]


def mm_to_units(mm_value, dxf_units, dxf_dpi):
    if dxf_units == "mm":
        return float(mm_value)
    if dxf_units == "in":
        return float(mm_value) / 25.4
    if dxf_units == "px":
        return float(mm_value) * dxf_dpi / 25.4
    raise ValueError(f"Unsupported DXF units: {dxf_units}")


def frame_outline_points(width, height, scale, offset, margin_units):
    offset_x, offset_y = offset
    
    # Calculate the scaled dimensions
    w_scaled = (width - 1) * scale
    h_scaled = (height - 1) * scale
    
    # Apply the scale, the positional offset, and the requested margin.
    corners = [
        (offset_x - margin_units,            offset_y - margin_units),            # Bottom-Left
        (offset_x + w_scaled + margin_units, offset_y - margin_units),            # Bottom-Right
        (offset_x + w_scaled + margin_units, offset_y + h_scaled + margin_units), # Top-Right
        (offset_x - margin_units,            offset_y + h_scaled + margin_units), # Top-Left
    ]
    return corners


def setting_hole_points(width, height, scale, offset, margin_units, inset_units):
    offset_x, offset_y = offset
    w_scaled = (width - 1) * scale
    h_scaled = (height - 1) * scale
    return [
        (
            offset_x - margin_units + inset_units,
            offset_y + h_scaled + margin_units - inset_units,
        ),
        (
            offset_x + w_scaled + margin_units - inset_units,
            offset_y + h_scaled + margin_units - inset_units,
        ),
        (
            offset_x - margin_units + inset_units,
            offset_y - margin_units + inset_units,
        ),
        (
            offset_x + w_scaled + margin_units - inset_units,
            offset_y - margin_units + inset_units,
        ),
    ]

def px_to_point(x_px, y_px, height, scale, offset):
    """Convert image pixel coords to DXF model point using same convention
    as contour_to_points (flips Y) and applies offset.
    """
    offset_x, offset_y = offset
    return (
        float(x_px) * scale + offset_x,
        float(height - 1 - y_px) * scale + offset_y,
    )


def default_label_height(dxf_units):
    if dxf_units == "mm":
        return 5.0
    if dxf_units == "in":
        return 0.2
    return 20.0


def compute_layout_offsets(count, width_px, height_px, scale, layout, spacing, columns):
    width_units = float(width_px) * scale
    height_units = float(height_px) * scale
    spacing_units = max(0.0, float(spacing))

    if layout == "stacked":
        return [(0.0, 0.0) for _ in range(count)]
    if layout == "row":
        return [
            (i * (width_units + spacing_units), 0.0) for i in range(count)
        ]
    if layout == "grid":
        if columns <= 0:
            columns = max(1, int(math.ceil(math.sqrt(count))))
        offsets = []
        for idx in range(count):
            row = idx // columns
            col = idx % columns
            offsets.append(
                (
                    col * (width_units + spacing_units),
                    row * (height_units + spacing_units),
                )
            )
        return offsets

    raise ValueError(f"Unknown DXF layout: {layout}")

def export_dxf(
    output_path,
    working_masks,
    working_colors,
    frame,
    dxf_version,
    dxf_units,
    dxf_dpi,
    dxf_scale,
    simplify_epsilon,
    layout,
    spacing,
    columns,
    include_frame,
    frame_margin_mm,
    setting_hole_diameter_mm,
    setting_hole_inset_mm,
):
    try:
        import ezdxf
        from ezdxf import units as ezdxf_units
    except ImportError:
        print(
            "Error: ezdxf is required for DXF export. "
            "Install it with: pip install ezdxf"
        )
        return False

    unit_map = {
        "mm": ezdxf_units.MM,
        "in": ezdxf_units.IN,
        "px": 0,
    }

    doc = ezdxf.new(dxfversion=dxf_version)
    if dxf_version != "R12":
        doc.units = unit_map[dxf_units]
    msp = doc.modelspace()

    height = frame.shape[0]
    width = frame.shape[1]
    margin_units = mm_to_units(frame_margin_mm, dxf_units, dxf_dpi)
    hole_radius_units = mm_to_units(setting_hole_diameter_mm / 2.0, dxf_units, dxf_dpi)
    hole_inset_units = mm_to_units(setting_hole_inset_mm, dxf_units, dxf_dpi)
    offsets = compute_layout_offsets(
        len(working_masks),
        width,
        height,
        dxf_scale,
        layout,
        spacing,
        columns,
    )
    
    for i, (mask, color_id) in enumerate(zip(working_masks, working_colors)):
        layer_name = f"Layer_{i:02d}_Color_{color_id}"
        if not doc.layers.has_entry(layer_name):
            doc.layers.new(name=layer_name, dxfattribs={"color": 7})

        if include_frame:
            frame_points = frame_outline_points(
                width,
                height,
                dxf_scale,
                offsets[i],
                margin_units,
            )
            if dxf_version == "R12":
                msp.add_polyline2d(
                    frame_points,
                    dxfattribs={"layer": layer_name, "closed": True},
                )
            else:
                msp.add_lwpolyline(
                    frame_points,
                    dxfattribs={"layer": layer_name, "closed": True},
                )

        if include_frame:
            for hole_center in setting_hole_points(
                width,
                height,
                dxf_scale,
                offsets[i],
                margin_units,
                hole_inset_units,
            ):
                msp.add_circle(
                    hole_center,
                    hole_radius_units,
                    dxfattribs={"layer": layer_name},
                )

        # add a small text label near the top-left of this placed layer
        try:
            label_height = default_label_height(dxf_units)
            label_pos = px_to_point(10, 10, height, dxf_scale, offsets[i])
            # create text on the same layer so it is grouped visually
            text_kwargs = {"layer": layer_name, "height": label_height}
            txt = msp.add_text(f"{layer_name}", dxfattribs=text_kwargs)
            # place text; set_pos available on ezdxf text entity
            try:
                txt.set_pos(label_pos, align="LEFT")
            except Exception:
                # fallback: set insert point attribute
                txt.dxf.insert = label_pos
        except Exception:
            # don't fail DXF export if text can't be created
            pass

        contours = mask_to_contours(mask, simplify_epsilon)
        for contour in contours:
            points = contour_to_points(contour, height, dxf_scale, offsets[i])
            if len(points) < 3:
                continue
            if dxf_version == "R12":
                msp.add_polyline2d(
                    points,
                    dxfattribs={"layer": layer_name, "closed": True},
                )
            else:
                msp.add_lwpolyline(
                    points,
                    dxfattribs={"layer": layer_name, "closed": True},
                )

    doc.saveas(output_path)
    print(f"DXF saved to: {output_path}")
    return True


# ---------------------------------------------------------------------------
# Save / summary 
# ---------------------------------------------------------------------------

def save_outputs(output_dir, working_masks, working_colors, frame):
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nSaving {len(working_masks)} merged layers to '{output_dir}'...")

    merged_cumulative = frame.copy()
    for i, (mask, color_id) in enumerate(zip(working_masks, working_colors)):
        merged_cumulative = cv2.bitwise_or(merged_cumulative, mask)
        filename = f"Layer_{i:02d}_Color_{color_id}.png"
        cv2.imwrite(os.path.join(output_dir, filename), merged_cumulative)

    np.save(os.path.join(output_dir, "layer_order.npy"), np.array(working_colors))
    np.save(os.path.join(output_dir, "frame.npy"), frame)
    cv2.imwrite(
        os.path.join(output_dir, "Final_Global_Safe_Zone.png"),
        merged_cumulative,
    )


def print_final_summary(working_masks, working_colors, frame):
    total_pixels = frame.shape[0] * frame.shape[1]
    final_areas = recompute_visible_areas(working_masks, frame)

    print("\nFinal layer summary:")
    print(f"{'Layer':<8} {'Color':<8} {'Visible px':<14} {'% of image':<12}")
    print("-" * 44)
    for i in range(len(working_masks)):
        pct = 100 * final_areas[i] / total_pixels
        print(f"  {i:02d}     {working_colors[i]:<8} {final_areas[i]:<14,} {pct:.2f}%")
    print(f"\nFinal layer order (top -> bottom): {working_colors}")


def build_support_masks(working_masks, frame):
    """
    For each layer, build a support mask that includes the frame and all layers
    below it (assuming working_masks is ordered top -> bottom).
    """
    support_masks = [None] * len(working_masks)
    support = frame.copy()
    for idx in range(len(working_masks) - 1, -1, -1):
        support_masks[idx] = support.copy()
        support = cv2.bitwise_or(support, working_masks[idx])
    return support_masks


def bridge_islands_to_support(mask, support_mask, frame, gap_px, max_bridges, debug=False):
    """
    Add thin bridges from disconnected islands to the nearest support when the
    gap is within gap_px. Designed to be conservative.
    """
    if gap_px <= 0 or support_mask is None:
        return mask

    mask_bin = (mask > 0).astype(np.uint8) * 255
    support_bin = (support_mask > 0).astype(np.uint8) * 255

    h, w = mask_bin.shape
    max_bridges = int(max_bridges)
    if max_bridges < 0:
        max_bridges = 0

    # Distance to support for all pixels (0 inside support).
    dist_to_support = cv2.distanceTransform(
        (support_bin == 0).astype(np.uint8), cv2.DIST_L2, 3
    )

    labels_count, labels = cv2.connectedComponents(mask_bin, connectivity=4)
    bridges_added = 0
    out_mask = mask_bin.copy()
    considered = 0
    bridged = 0
    bridged_distances = []

    for comp in range(1, labels_count):
        coords = np.column_stack(np.where(labels == comp))
        if coords.size == 0:
            continue
        if np.any(support_bin[coords[:, 0], coords[:, 1]] > 0):
            continue

        considered += 1
        dists = dist_to_support[coords[:, 0], coords[:, 1]]
        min_idx = int(np.argmin(dists))
        min_dist = float(dists[min_idx])
        if min_dist > gap_px:
            continue

        island_r, island_c = coords[min_idx]
        r0 = max(0, island_r - gap_px)
        r1 = min(h - 1, island_r + gap_px)
        c0 = max(0, island_c - gap_px)
        c1 = min(w - 1, island_c + gap_px)
        window = support_bin[r0:r1 + 1, c0:c1 + 1]
        support_coords = np.column_stack(np.where(window > 0))
        if support_coords.size == 0:
            continue

        support_coords[:, 0] += r0
        support_coords[:, 1] += c0
        dr = support_coords[:, 0] - island_r
        dc = support_coords[:, 1] - island_c
        nearest_idx = int(np.argmin(dr * dr + dc * dc))
        sup_r, sup_c = support_coords[nearest_idx]

        cv2.line(out_mask, (int(island_c), int(island_r)), (int(sup_c), int(sup_r)), 255, 1)
        bridges_added += 1
        bridged += 1
        bridged_distances.append(min_dist)
        if max_bridges > 0 and bridges_added >= max_bridges:
            break

    out_mask = cv2.bitwise_and(out_mask, cv2.bitwise_not(frame))
    if debug:
        if bridged_distances:
            dist_min = min(bridged_distances)
            dist_max = max(bridged_distances)
            dist_med = float(np.median(bridged_distances))
        else:
            dist_min = dist_max = dist_med = 0.0
        print(
            "    debug: islands="
            f"{labels_count - 1}, considered={considered}, bridged={bridged}, "
            f"gap_px={gap_px}, dist_min={dist_min:.2f}, "
            f"dist_med={dist_med:.2f}, dist_max={dist_max:.2f}"
        )
    return out_mask

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("--------------------------\n")
    print("\n Starting Post-Processor \n")
    print("--------------------------\n")

    args = parse_args()
    run_name = resolve_run_name(args)
    input_dir, output_dir = resolve_dirs(args, run_name)
    dxf_path = resolve_dxf_path(args, run_name, output_dir) if args.export_dxf else None

    if not input_dir or not output_dir:
        print(
            "Error: Could not resolve input/output directories. "
            "Run preprocessor/generator first or pass --in-dir/--out-dir."
        )
        return 1

    try:
        layer_order, frame = load_generator_outputs(input_dir)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    n_layers = len(layer_order)
    h, w = frame.shape
    print(f"Loaded {n_layers} layers: color order = {layer_order}")
    print(f"Image dimensions: {w}x{h}")

    try:
        cumulative_zones = load_cumulative_zones(input_dir, layer_order)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    print("All layer images loaded.\n")

    individual_masks = reconstruct_individual_masks(cumulative_zones, frame)
    print("Reconstructed individual layer masks.")

    _, visible_areas = compute_visible_regions(individual_masks, frame)
    total_pixels = w * h

    if args.merge_visible_fraction:
        if not (0.0 < args.merge_visible_fraction < 1.0):
            print("Error: --merge-visible-fraction must be between 0 and 1 (exclusive).")
            return 1
        epsilon = args.merge_visible_fraction * total_pixels
    else:
        epsilon = 0.01 * total_pixels

    print(
        f"\nVisible region areas (epsilon threshold = {epsilon:.0f} px = "
        f"{args.merge_visible_fraction * 100:.2f}% of image):"
    )

    for i in range(n_layers):
        pct = 100 * visible_areas[i] / total_pixels
        flag = " <- merge candidate" if visible_areas[i] < epsilon else ""
        print(
            f"  Layer {i:02d}  Color {layer_order[i]}  "
            f"visible = {visible_areas[i]:>8,} px  ({pct:.2f}%){flag}"
        )

    working_masks, working_colors = merge_small_layers(
        individual_masks,
        layer_order,
        frame,
        epsilon,
    )

    print(
        f"\nMerging complete.  {n_layers} layers -> {len(working_masks)} layers."
    )

    if args.stress_analysis:
        print("\n--- Pre-pass: widening thin connections ---")
        for i, (mask, color_id) in enumerate(zip(working_masks, working_colors)):
            layer_name = f"Layer_{i:02d}_Color_{color_id}"
            widened = widen_thin_connections(mask, frame, min_width_px=args.thin_min_width, widen_to_px=args.thin_widen_to,)
            if not np.array_equal(widened, mask):
                added = int(np.count_nonzero(widened)) - int(np.count_nonzero(mask))
                print(f"  {layer_name}: widened {added} thin pixels")
                working_masks[i] = widened

    # TODO 
    #     print("\n--- Stress Analysis: widening weak members ---")
    #     print(f"  β = {args.stress_beta:.1f} MPa  |  "
    #             f"FEA size = {args.stress_fea_size}  |  "
    #             f"thickness = {args.stress_thickness_mm} mm  |  "
    #             f"sheet = {args.stress_sheet_mm} mm")

    #     # Material parameters (paper values)
    #     E_pa    = 7.2e9           # Young's modulus [Pa]
    #     nu      = 0.3             # Poisson's ratio
    #     rho     = 500.0           # density [kg/m³]
    #     t_m     = args.stress_thickness_mm / 1000.0   # [m]
    #     sheet_m = args.stress_sheet_mm     / 1000.0   # [m]
    #     beta_pa = args.stress_beta         * 1e6      # [Pa]

    #     stress_map_dir = os.path.join(output_dir, "stress_maps") if args.stress_save_maps else None

    #     support_masks = build_support_masks(working_masks, frame)

    #     for i, (mask, color_id) in enumerate(zip(working_masks, working_colors)):
    #         layer_name = f"Layer_{i:02d}_Color_{color_id}"
    #         print(f"\n  Processing {layer_name} ...")
    #         working_masks[i] = widen_weak_members_stress(
    #             mask         = mask,
    #             frame        = frame,
    #             support_mask = support_masks[i],
    #             beta_pa      = beta_pa,
    #             fea_size     = args.stress_fea_size,
    #             E            = E_pa,
    #             nu           = nu,
    #             rho          = rho,
    #             t_m          = t_m,
    #             sheet_m      = sheet_m,
    #             max_iters    = args.stress_max_iters,
    #             save_maps    = args.stress_save_maps,
    #             save_dir     = stress_map_dir,
    #             layer_name   = layer_name,
    #             debug        = args.debug_stress,
    #         )

    # print("\nStress analysis complete.")

    if args.bridge_support:
        print("\n--- Bridging disconnected islands to support ---")
        support_masks = build_support_masks(working_masks, frame)
        for i, (mask, color_id) in enumerate(zip(working_masks, working_colors)):
            layer_name = f"Layer_{i:02d}_Color_{color_id}"
            print(f"  Bridging {layer_name} ...")
            working_masks[i] = bridge_islands_to_support(
                mask=mask,
                support_mask=support_masks[i],
                frame=frame,
                gap_px=args.bridge_gap_px,
                max_bridges=args.bridge_max_bridges,
                debug=args.debug_bridge,
            )
        
    save_outputs(output_dir, working_masks, working_colors, frame)

    # Finalize: create fabrication-ready package (per-layer PNG + DXF + handoff.md)
    if args.finalize:
        final_dir = args.final_dir or (f"output_final_{run_name}" if run_name else None)
        if not final_dir:
            print("Error: Could not determine final directory name. Provide --final-dir or --run-name.")
            return 1
        os.makedirs(final_dir, exist_ok=True)

        # Remove previous final artifacts so the shell loop only sees the current run.
        for name in os.listdir(final_dir):
            if name.startswith("Layer_") and name.lower().endswith((".png", ".dxf")):
                try:
                    os.remove(os.path.join(final_dir, name))
                except OSError:
                    pass
            elif name in {"handoff.md", "run_metadata.json"}:
                try:
                    os.remove(os.path.join(final_dir, name))
                except OSError:
                    pass

        # Load preprocessor metadata (palette)
        metadata = load_run_metadata(args.meta_dir) or load_run_metadata(input_dir) or {}
        palette = metadata.get("palette", []) if metadata else []
        palette_map = {int(p.get("id")): p for p in palette} if palette else {}

        used_names = {}
        fallback_used = []
        final_layer_pngs = []
        merged_cumulative = frame.copy()

        for i, (mask, color_id) in enumerate(zip(working_masks, working_colors)):
            entry = palette_map.get(int(color_id)) if palette_map else None
            label = None
            cluster_lab = None
            rgb = None
            if entry is not None:
                rgb = entry.get("rgb")
                cluster_lab = entry.get("lab")
                if entry.get("name"):
                    label = entry.get("name")

            if args.use_color_names and label is None and cluster_lab is not None:
                try:
                    label = _nearest_friendly_name(cluster_lab)
                except Exception:
                    label = None

            if not label:
                # deterministic fallback notation
                if rgb:
                    label = f"RGB_{rgb[0]}_{rgb[1]}_{rgb[2]}"
                elif cluster_lab:
                    label = f"LAB_{cluster_lab[0]}_{cluster_lab[1]}_{cluster_lab[2]}"
                else:
                    label = f"Color_{color_id}"
                fallback_used.append((i, label))

            base_label = _sanitize_label(str(label))
            # ensure uniqueness
            if base_label in used_names:
                used_names[base_label] += 1
                base_label = f"{base_label}_id{used_names[base_label]}"
            else:
                used_names[base_label] = 0

            png_name = f"Layer_{i:02d}_{base_label}.png"
            png_path = os.path.join(final_dir, png_name)
            merged_cumulative = cv2.bitwise_or(merged_cumulative, mask)
            # Write the cumulative safe-zone PNG so it matches postprocessed output content.
            cv2.imwrite(png_path, merged_cumulative)
            final_layer_pngs.append(
                {
                    "index": i,
                    "path": png_path,
                    "rgb": rgb if rgb is not None else [255, 255, 255],
                }
            )

            # DXF conversion happens after all PNGs are written, via the exact shell loop.

        # Convert the final PNGs to DXFs using the exact shell loop requested.
        shell_loop = (
            'for f in output_final_*/Layer_*.png; do '
            'python png-to-dxf.py --png "$f" --dpi '
            f'{args.dxf_dpi} '
            f'--frame-margin-mm {args.dxf_frame_margin_mm} '
            f'--setting-hole-diameter-mm {args.dxf_setting_hole_diameter_mm} '
            f'--setting-hole-inset-mm {args.dxf_setting_hole_inset_mm}; '
            'done'
        )
        print(f"Running DXF conversion loop: {shell_loop}")
        env = os.environ.copy()
        env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
        try:
            subprocess.run(
                shell_loop,
                shell=True,
                check=True,
                cwd=os.path.dirname(__file__),
                env=env,
                executable="/bin/zsh",
            )
        except subprocess.CalledProcessError as exc:
            print(f"Warning: DXF conversion shell loop failed: {exc}")

        # Colorize final layer PNGs by painting only white mask pixels.
        # This is done after DXF conversion so vector export still traces binary masks.
        for layer in final_layer_pngs:
            mask_gray = cv2.imread(layer["path"], cv2.IMREAD_GRAYSCALE)
            if mask_gray is None:
                continue
            colorized = _colorize_white_mask(mask_gray, layer["rgb"])
            cv2.imwrite(layer["path"], colorized)

        layout_stock_size = args.stock_size_in
        layout_gap_mm = args.layout_gap_mm
        if not layout_stock_size:
            inferred = infer_layout_refresh_config(final_dir)
            if inferred is not None:
                layout_stock_size, layout_gap_mm = inferred

        if layout_stock_size:
            refresh_layout_cut_generator(final_dir, layout_stock_size, layout_gap_mm, run_log=args.run_log)

        # Copy run metadata into final dir if available
        src_meta = os.path.join(args.meta_dir, "run_metadata.json")
        if os.path.exists(src_meta):
            shutil.copy2(src_meta, os.path.join(final_dir, "run_metadata.json"))

        # Optionally include intermediates
        if args.include_intermediates:
            for name in ["frame.npy", "layer_order.npy", "run_metadata.json"]:
                src = os.path.join(output_dir, name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(final_dir, name))

        # Write handoff markdown with analytics
        final_areas = recompute_visible_areas(working_masks, frame)
        total_pixels = frame.shape[0] * frame.shape[1]
        lines = []
        img_desc = metadata.get("image_path", "") if metadata else ""
        lines.append(f"# Fabrication Handoff — {run_name}\n")
        lines.append(f"**Source image:** {img_desc}\n")
        lines.append("## Analytics\n")
        lines.append(f"- Layers (final): {len(working_masks)}\n")
        lines.append(f"- Image size: {frame.shape[1]}×{frame.shape[0]} px ({total_pixels} px)\n")
        lines.append(f"- DXF units: {args.dxf_units}, DPI: {args.dxf_dpi}\n")
        lines.append("\n")
        lines.append("### Layer areas\n")
        for i, area in enumerate(final_areas):
            pct = 100.0 * area / total_pixels
            lines.append(f"- Layer {i:02d}: {area} px ({pct:.2f}% of image)\n")

        lines.append("\n## Files\n")
        lines.append("Per-layer PNG and DXF files are provided for laser cutting. Filenames prefer friendly color names when available; fallback codes are explicit (RGB/LAB).\n")
        if fallback_used:
            lines.append("\n## Fallback naming used for these layers\n")
            for idx, lbl in fallback_used:
                lines.append(f"- Layer {idx:02d}: {lbl}\n")

        # weird fact: smallest visible layer
        min_area = min(final_areas) if final_areas else 0
        lines.append("\n## Weird fact\n")
        lines.append(f"The smallest final visible layer contains {min_area} pixels ({100.0*min_area/total_pixels:.6f}% of the image).\n")

        # Append a toggleable execution story for novices. Uses an HTML <details>
        # block so it is hidden by default but viewable if the user expands it.
        exec_lines = []
        exec_lines.append("--------------------------")
        exec_lines.append("Starting Post-Processor")
        exec_lines.append(f"Loaded {n_layers} layers: color order = {layer_order}")
        exec_lines.append(f"Image dimensions: {frame.shape[1]}x{frame.shape[0]}")
        exec_lines.append("All layer images loaded.")
        exec_lines.append("Reconstructed individual layer masks.")

        # Visible region areas (recompute cleanly here)
        try:
            _, visible_areas_exec = compute_visible_regions(individual_masks, frame)
        except Exception:
            visible_areas_exec = final_areas

        exec_lines.append("")
        exec_lines.append(f"Visible region areas (epsilon = {epsilon:.0f} px):")
        for i in range(min(len(visible_areas_exec), len(layer_order))):
            pct = 100.0 * visible_areas_exec[i] / total_pixels if total_pixels else 0.0
            exec_lines.append(f"  Layer {i:02d}  Color {layer_order[i]}  visible = {visible_areas_exec[i]:,} px  ({pct:.2f}%)")

        exec_lines.append("")
        exec_lines.append(f"Merging complete. {n_layers} layers -> {len(working_masks)} layers.")
        exec_lines.append(f"Stress-analysis widening: {'enabled' if args.stress_analysis else 'disabled'}")

        # Files produced during finalize
        try:
            saved_pngs = [os.path.basename(p['path']) for p in final_layer_pngs]
        except Exception:
            saved_pngs = []
        if saved_pngs:
            exec_lines.append("")
            exec_lines.append("Files written to final directory:")
            for p in saved_pngs:
                exec_lines.append(f"  {p}")

        # DXF conversion loop shown and any produced .dxf files
        exec_lines.append("")
        exec_lines.append(f"DXF conversion loop: {shell_loop}")
        try:
            dxf_files = [n for n in os.listdir(final_dir) if n.lower().endswith('.dxf')]
        except Exception:
            dxf_files = []
        if dxf_files:
            exec_lines.append("DXF files created:")
            for n in dxf_files:
                exec_lines.append(f"  {n}")

        exec_lines.append("")
        exec_lines.append("POST-PROCESSING COMPLETE")

        # Short plain-English explanation for novices (brief and direct)
        explanation = []
        explanation.append("This run performed the following steps in order:")
        explanation.append("1) Loaded the generator outputs (layer order and frame).")
        explanation.append("2) Reconstructed each layer's individual mask from cumulative images.")
        explanation.append("3) Measured visible area for each layer and marked tiny layers for merging.")
        explanation.append("4) Merged very small layers into nearby same-color layers to simplify cutting files.")
        explanation.append("5) Optionally widened thin parts if stress-analysis was enabled (safer for cutting).")
        explanation.append("6) Saved per-layer PNGs and run metadata into the final package.")
        explanation.append("7) Converted final PNGs to DXF using the external tracer loop (one DXF per PNG).")
        explanation.append("8) Wrote this handoff file with analytics and the list of files produced.")

        # Create a separate runtime log file `runtimelog.md` in the final directory.
        runtimelog_path = os.path.join(final_dir, "runtimelog.md")
        if args.run_log and os.path.exists(args.run_log):
            try:
                with open(args.run_log, "r", encoding="utf-8") as rf:
                    formatted_run_log = rf.read()
            except Exception:
                formatted_run_log = "\n".join(exec_lines)
        else:
            formatted_run_log = "\n".join(exec_lines)

        # Write runtimelog.md: header, formatted run log as a code block, then plain-English bullets.
        runt_lines = []
        runt_lines.append(f"# Runtime Log — {run_name}\n\n")
        runt_lines.append("```text\n")
        runt_lines.append(formatted_run_log.rstrip() + "\n")
        runt_lines.append("```\n\n")
        runt_lines.append("### Plain English explanation\n\n")
        for s in explanation:
            runt_lines.append(f"- {s}\n")

        try:
            with open(runtimelog_path, "w", encoding="utf-8") as rf:
                rf.write("".join(runt_lines))
        except Exception:
            # best-effort: if writing fails, continue but warn on stdout
            print(f"Warning: could not write runtime log to '{runtimelog_path}'")

        # Write the details block into the handoff markdown (toggleable).
        # Replace the big formatted run-log block with a short link to runtimelog.md,
        # and keep the plain-English explanation here for quick viewing.
        lines.append("\n<details>\n")
        lines.append("<summary>Execution Story (click to expand)</summary>\n\n")
        lines.append(f"See runtimelog.md for the formatted run log.\n\n")
        lines.append("### Plain English explanation\n\n")
        for s in explanation:
            lines.append(f"- {s}\n")
        lines.append("\n</details>\n")

        handoff_path = os.path.join(final_dir, "handoff.md")
        with open(handoff_path, "w", encoding="utf-8") as h:
            h.write("".join(lines))

        print(f"Final fabrication package written to: {final_dir}")

    if args.export_dxf:
        try:
            dxf_scale = dxf_scale_from_args(args.dxf_units, args.dxf_dpi)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 1

        print(
            "\nExporting DXF "
            "(units="
            f"{args.dxf_units}, dpi={args.dxf_dpi}, scale={dxf_scale:.6f}, "
            f"layout={args.dxf_layout})..."
        )
        if not export_dxf(
            dxf_path,
            working_masks,
            working_colors,
            frame,
            args.dxf_version,
            args.dxf_units,
            args.dxf_dpi,
            dxf_scale,
            args.dxf_simplify_epsilon,
            args.dxf_layout,
            args.dxf_spacing,
            args.dxf_columns,
            args.dxf_include_frame,
            args.dxf_frame_margin_mm,
            args.dxf_setting_hole_diameter_mm,
            args.dxf_setting_hole_inset_mm,
        ):
            return 1

    print_final_summary(working_masks, working_colors, frame)

    print("\n--------------------------")
    print(" POST-PROCESSING COMPLETE")
    print("--------------------------\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())