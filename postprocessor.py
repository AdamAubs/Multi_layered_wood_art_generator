import argparse
import json
import os

import cv2
import numpy as np


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
        "--meta-dir",
        default="preprocessor_output",
        help="Directory containing run_metadata.json for default naming.",
    )
    return parser.parse_args()


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
        input_dir = f"output_generator_{run_name}"

    output_dir = args.out_dir
    if not output_dir and run_name:
        output_dir = f"output_postprocessed_{run_name}"

    return input_dir, output_dir


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


def merge_small_layers(individual_masks, layer_order, frame, epsilon):
    working_masks = [mask.copy() for mask in individual_masks]
    working_colors = list(layer_order)
    merge_occurred = True
    merge_round = 0

    while merge_occurred:
        merge_occurred = False
        merge_round += 1
        current_areas = recompute_visible_areas(working_masks, frame)
        n_current = len(working_masks)

        print(f"\n--- Merge round {merge_round} ({n_current} layers) ---")

        for i in range(n_current):
            if current_areas[i] < epsilon:
                color_id = working_colors[i]
                target_idx = find_merge_target(i, color_id, working_colors, n_current)

                if target_idx is None:
                    print(
                        f"  Layer {i:02d} (Color {color_id}): "
                        "no same-color target found, keeping."
                    )
                    continue

                direction = "above" if target_idx < i else "below"
                print(
                    f"  Merging Layer {i:02d} (Color {color_id}, "
                    f"{current_areas[i]} px visible) -> "
                    f"Layer {target_idx:02d} ({direction})"
                )

                working_masks[target_idx] = cv2.bitwise_or(
                    working_masks[target_idx],
                    working_masks[i],
                )

                working_masks.pop(i)
                working_colors.pop(i)

                merge_occurred = True
                break

    return working_masks, working_colors


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


def main():
    print("--------------------------\n")
    print("\n Starting Post-Processor \n")
    print("--------------------------\n")

    args = parse_args()
    run_name = resolve_run_name(args)
    input_dir, output_dir = resolve_dirs(args, run_name)

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

    visible_masks, visible_areas = compute_visible_regions(individual_masks, frame)
    total_pixels = w * h
    epsilon = 0.01 * total_pixels

    print(
        f"\nVisible region areas (epsilon threshold = {epsilon:.0f} px = 1% of image):"
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

    save_outputs(output_dir, working_masks, working_colors, frame)
    print_final_summary(working_masks, working_colors, frame)

    print("\n--------------------------")
    print(" POST-PROCESSING COMPLETE")
    print("--------------------------\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())