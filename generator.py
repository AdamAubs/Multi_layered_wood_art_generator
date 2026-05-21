import argparse
import json
import math
import os
from datetime import datetime

import cv2
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate layered safe zones from preprocessor outputs."
    )
    parser.add_argument(
        "--in-dir",
        default="preprocessor_output",
        help="Directory containing labels.npy, n_colors.npy, and run_metadata.json.",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Override path to labels.npy.",
    )
    parser.add_argument(
        "--n-colors",
        default=None,
        help="Override path to n_colors.npy.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Explicit output directory (skips run-name naming).",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Override run name for output directory.",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help="Append a YYYYMMDD_HHMMSS timestamp to the output directory.",
    )
    return parser.parse_args()


def load_run_metadata(in_dir):
    metadata_path = os.path.join(in_dir, "run_metadata.json")
    if not os.path.exists(metadata_path):
        return None
    with open(metadata_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_run_name(args):
    if args.run_name:
        return args.run_name
    metadata = load_run_metadata(args.in_dir)
    if metadata and metadata.get("run_name"):
        return metadata["run_name"]
    return None


def resolve_input_paths(args):
    labels_path = args.labels or os.path.join(args.in_dir, "labels.npy")
    n_colors_path = args.n_colors or os.path.join(args.in_dir, "n_colors.npy")
    return labels_path, n_colors_path


def resolve_output_dir(args, run_name):
    if args.out_dir:
        return args.out_dir
    base = f"output_generator_{run_name}"
    if args.timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base}_{timestamp}"
    return base


def load_inputs(labels_path, n_colors_path):
    try:
        labels = np.load(labels_path)
        print("Successfully loaded labels grid!")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Error: Could not find labels.npy at '{labels_path}'."
        )
    try:
        n_colors = int(np.load(n_colors_path)[0])
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Error: Could not find n_colors.npy at '{n_colors_path}'."
        )
    print(f"Loaded n_colors = {n_colors} from preprocessor")
    return labels, n_colors


def build_color_masks(labels, n_colors):
    color_masks = []
    for k in range(n_colors):
        mask = (labels == k).astype(np.uint8) * 255
        color_masks.append(mask)
    return color_masks


def create_frame(h, w):
    m_minus_1 = np.zeros((h, w), dtype=np.uint8)
    frame_thickness = 15
    cv2.rectangle(m_minus_1, (0, 0), (w - 1, h - 1), 255, frame_thickness)
    return m_minus_1


def prepare_thresholds(w, h):
    diagonal = math.sqrt(w ** 2 + h ** 2)
    omega_budget = 0.03 * diagonal
    delta_widening_px = max(1, int(0.002 * diagonal))
    gamma_hole_area = 0.0001 * (w * h)
    return omega_budget, delta_widening_px, gamma_hole_area


def generate_layers(labels, n_colors):
    h, w = labels.shape
    color_masks = build_color_masks(labels, n_colors)
    m_minus_1 = create_frame(h, w)

    print("Isolated masks and created the M_-1 frame (initial safe zone).")
    for k in range(n_colors):
        color_masks[k] = cv2.bitwise_and(color_masks[k], cv2.bitwise_not(m_minus_1))

    omega_budget, delta_widening_px, gamma_hole_area = prepare_thresholds(w, h)
    print(f"Distance Budget  (omega):  {omega_budget:.2f} px")
    print(f"Widening Radius  (delta):  {delta_widening_px} px")
    print(f"Tiny Hole Limit  (gamma):  {gamma_hole_area:.2f} px²")

    print("\n--- Running Greedy Layer Generation ---")

    global_safe_zone = m_minus_1.copy()
    layer_counter = 0
    layer_order = []
    generated_layers = []
    winning_safe_zone_history = []
    min_patch_area = int(0.00005 * w * h)

    while True:
        print(f"\n--- Calculating Layer {layer_counter} ---")

        best_color = -1
        max_area_connected = -1
        winning_safe_zone = None

        for k in range(n_colors):
            current_mask = color_masks[k]
            num_patches, patch_labels, stats, _ = cv2.connectedComponentsWithStats(current_mask)
            valid_patches = [
                patch_id
                for patch_id in range(1, num_patches)
                if stats[patch_id, cv2.CC_STAT_AREA] > min_patch_area
            ]

            if not valid_patches:
                continue

            hypothetical_safe_zone = global_safe_zone.copy()
            remaining_patches = list(valid_patches)
            connected_area = 0
            spent_budget = 0.0

            while remaining_patches:
                inverted_safe_zone = cv2.bitwise_not(hypothetical_safe_zone)
                dist_map = cv2.distanceTransform(inverted_safe_zone, cv2.DIST_L2, 5)

                nearest_patch_id = None
                nearest_distance = float("inf")

                for patch_id in remaining_patches:
                    patch_pixels = (patch_labels == patch_id)
                    d = np.min(dist_map[patch_pixels])
                    if d < nearest_distance:
                        nearest_distance = d
                        nearest_patch_id = patch_id

                if nearest_patch_id is None:
                    break

                patch_pixels = (patch_labels == nearest_patch_id)

                if nearest_distance == 0:
                    connected_area += int(np.sum(patch_pixels))
                    hypothetical_safe_zone[patch_pixels] = 255
                    remaining_patches.remove(nearest_patch_id)
                elif (spent_budget + nearest_distance) <= omega_budget:
                    spent_budget += nearest_distance
                    connected_area += int(np.sum(patch_pixels))

                    patch_dist_map = np.where(patch_pixels, dist_map, np.inf)
                    min_y, min_x = np.unravel_index(
                        np.argmin(patch_dist_map), patch_dist_map.shape
                    )

                    safe_edge = cv2.morphologyEx(
                        hypothetical_safe_zone,
                        cv2.MORPH_GRADIENT,
                        np.ones((3, 3), np.uint8),
                    )
                    edge_y, edge_x = np.where(safe_edge > 0)
                    distances_sq = (edge_x - min_x) ** 2 + (edge_y - min_y) ** 2
                    best_edge_idx = np.argmin(distances_sq)
                    target_x = int(edge_x[best_edge_idx])
                    target_y = int(edge_y[best_edge_idx])

                    cv2.line(
                        hypothetical_safe_zone,
                        (int(min_x), int(min_y)),
                        (target_x, target_y),
                        255,
                        1,
                    )

                    hypothetical_safe_zone[patch_pixels] = 255
                    remaining_patches.remove(nearest_patch_id)
                else:
                    break

            print(
                f"  Color {k}: connected {connected_area}/{len(valid_patches)} patches | "
                f"bridge cost {spent_budget:.1f}/{omega_budget:.1f} px"
            )

            if connected_area > max_area_connected:
                max_area_connected = connected_area
                best_color = k
                winning_safe_zone = hypothetical_safe_zone.copy()

        if max_area_connected == 0 or best_color == -1:
            print("\n[!] STUCK: No patches can be reached with the current budget. Stopping.")
            break

        print(
            f"WINNER: Layer {layer_counter} → Color {best_color} "
            f"({max_area_connected} patches connected)"
        )
        layer_order.append(best_color)

        print("   -> Widening skeleton and filling tiny holes...")
        skeleton = cv2.ximgproc.thinning(winning_safe_zone)
        kernel_size = delta_widening_px * 2 + 1
        dilation_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (kernel_size, kernel_size),
        )
        dilated_skeleton = cv2.dilate(skeleton, dilation_kernel)
        winning_safe_zone = cv2.bitwise_or(winning_safe_zone, dilated_skeleton)

        inverted_layer = cv2.bitwise_not(winning_safe_zone)
        num_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(
            inverted_layer
        )
        for hole_id in range(1, num_holes):
            if hole_stats[hole_id, cv2.CC_STAT_AREA] < gamma_hole_area:
                winning_safe_zone[hole_labels == hole_id] = 255

        print("   -> Free pickup pass after widening...")
        pickup_happened = True
        while pickup_happened:
            pickup_happened = False

            inverted = cv2.bitwise_not(winning_safe_zone)
            dist_map_post = cv2.distanceTransform(inverted, cv2.DIST_L2, 5)

            remaining_color_mask = cv2.bitwise_and(
                color_masks[best_color],
                cv2.bitwise_not(winning_safe_zone),
            )

            num_p, p_labels, p_stats, _ = cv2.connectedComponentsWithStats(
                remaining_color_mask
            )

            for pid in range(1, num_p):
                if p_stats[pid, cv2.CC_STAT_AREA] <= min_patch_area:
                    continue
                patch_pixels = (p_labels == pid)
                if np.min(dist_map_post[patch_pixels]) == 0:
                    winning_safe_zone[patch_pixels] = 255
                    pickup_happened = True
                    break

        newly_added = cv2.bitwise_xor(winning_safe_zone, global_safe_zone)
        generated_layers.append(newly_added.copy())

        for c_idx in range(n_colors):
            color_masks[c_idx] = cv2.bitwise_and(
                color_masks[c_idx],
                cv2.bitwise_not(winning_safe_zone),
            )

        winning_safe_zone_history.append(winning_safe_zone.copy())
        global_safe_zone = winning_safe_zone.copy()
        layer_counter += 1

        if layer_counter > 50:
            print("\n[!] SAFETY LIMIT: 50 layers reached. Stopping.")
            break

    print("\n--------------------------")
    print(" GENERATION COMPLETE")
    print(f" Layer order (top → bottom): {layer_order}")
    print("--------------------------\n")

    return global_safe_zone, layer_order, winning_safe_zone_history, m_minus_1, generated_layers


def save_outputs(output_dir, global_safe_zone, layer_order, winning_safe_zone_history, frame):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving {len(winning_safe_zone_history)} layers to '{output_dir}'...")

    cv2.imwrite(os.path.join(output_dir, "Final_Global_Safe_Zone.png"), global_safe_zone)

    for i, color_id in enumerate(layer_order):
        filename = f"Layer_{i:02d}_Color_{color_id}.png"
        cv2.imwrite(os.path.join(output_dir, filename), winning_safe_zone_history[i])

    np.save(os.path.join(output_dir, "layer_order.npy"), np.array(layer_order))
    np.save(os.path.join(output_dir, "frame.npy"), frame)
    print(f"Saved layer_order.npy ({len(layer_order)} layers) and frame.npy")


def main():
    print("--------------------------\n")
    print("\n Starting Generator \n")
    print("--------------------------\n")

    args = parse_args()
    run_name = resolve_run_name(args)
    if not run_name and not args.out_dir:
        print(
            "Error: Could not determine run name. "
            "Run preprocessor first, pass --run-name, or set --out-dir."
        )
        return 1

    labels_path, n_colors_path = resolve_input_paths(args)
    try:
        labels, n_colors = load_inputs(labels_path, n_colors_path)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    output_dir = resolve_output_dir(args, run_name)
    (
        global_safe_zone,
        layer_order,
        winning_safe_zone_history,
        frame,
        _,
    ) = generate_layers(labels, n_colors)
    save_outputs(output_dir, global_safe_zone, layer_order, winning_safe_zone_history, frame)

    print("\n--------------------------")
    print(" ALL FILES SAVED SUCCESSFULLY!")
    print("--------------------------\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())