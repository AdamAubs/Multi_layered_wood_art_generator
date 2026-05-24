import argparse
import os
import re
from collections import defaultdict


LAYER_FILE_RE = re.compile(r"^Layer_(\d{2})_(.+)\.(png|dxf)$")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete layers from an output_final_* package and renumber the rest."
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Path to the output_final_* directory to edit.",
    )
    parser.add_argument(
        "--delete",
        action="append",
        required=True,
        help="Layer index or range to remove, e.g. 5, 2-4, or repeat --delete.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the changes without modifying any files.",
    )
    return parser.parse_args()


def parse_delete_specs(specs):
    indices = set()
    for spec in specs:
        for chunk in str(spec).split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                start_text, end_text = chunk.split("-", 1)
                start = int(start_text)
                end = int(end_text)
                if end < start:
                    start, end = end, start
                indices.update(range(start, end + 1))
            else:
                indices.add(int(chunk))
    return indices


def load_layers(directory):
    layers = defaultdict(dict)
    for name in os.listdir(directory):
        match = LAYER_FILE_RE.match(name)
        if not match:
            continue
        index = int(match.group(1))
        suffix = match.group(2)
        extension = match.group(3)
        layers[index][extension] = suffix
    return layers


def rename_in_handoff(text, index_map):
    def remap_layer_tag(match):
        old_index = int(match.group(1))
        new_index = index_map.get(old_index, old_index)
        return f"Layer_{new_index:02d}"

    def remap_layer_label(match):
        old_index = int(match.group(1))
        new_index = index_map.get(old_index, old_index)
        return f"Layer {new_index:02d}"

    text = re.sub(r"Layer_(\d{2})", remap_layer_tag, text)
    text = re.sub(r"Layer (\d{2})", remap_layer_label, text)
    return text


def main():
    args = parse_args()
    directory = os.path.abspath(args.dir)
    delete_indices = parse_delete_specs(args.delete)

    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    layers = load_layers(directory)
    if not layers:
        raise FileNotFoundError(f"No Layer_XX_*.png or .dxf files found in {directory}")

    existing_indices = sorted(layers)
    missing = sorted(delete_indices - set(existing_indices))
    if missing:
        missing_text = ", ".join(f"{idx:02d}" for idx in missing)
        raise ValueError(f"Cannot delete missing layer(s): {missing_text}")

    remaining_indices = [index for index in existing_indices if index not in delete_indices]
    index_map = {old_index: new_index for new_index, old_index in enumerate(remaining_indices)}

    rename_plan = []
    for old_index in remaining_indices:
        new_index = index_map[old_index]
        suffix = layers[old_index].get("png") or layers[old_index].get("dxf") or "layer"
        for extension in sorted(layers[old_index]):
            old_name = f"Layer_{old_index:02d}_{suffix}.{extension}"
            new_name = f"Layer_{new_index:02d}_{suffix}.{extension}"
            rename_plan.append((old_name, new_name))

    handoff_path = os.path.join(directory, "handoff.md")
    handoff_text = None
    if os.path.exists(handoff_path):
        with open(handoff_path, "r", encoding="utf-8") as handle:
            handoff_text = handle.read()

    print(f"Directory: {directory}")
    print(f"Deleting layer(s): {', '.join(f'{idx:02d}' for idx in sorted(delete_indices))}")
    print(f"Remaining layer count: {len(remaining_indices)}")
    for old_name, new_name in rename_plan:
        print(f"  {old_name} -> {new_name}")

    if args.dry_run:
        return 0

    for deleted_index in sorted(delete_indices):
        for name in list(os.listdir(directory)):
            if name.startswith(f"Layer_{deleted_index:02d}_"):
                os.remove(os.path.join(directory, name))

    temp_prefix = ".__trim_tmp__"
    temp_plan = []
    for old_name, new_name in rename_plan:
        temp_name = f"{temp_prefix}{new_name}"
        temp_plan.append((old_name, temp_name, new_name))

    for old_name, temp_name, _ in temp_plan:
        os.replace(os.path.join(directory, old_name), os.path.join(directory, temp_name))

    for _, temp_name, new_name in temp_plan:
        os.replace(os.path.join(directory, temp_name), os.path.join(directory, new_name))

    if handoff_text is not None:
        updated = rename_in_handoff(handoff_text, index_map)
        updated = re.sub(
            r"(- Layers \(final\): )\d+",
            lambda match: f"{match.group(1)}{len(remaining_indices)}",
            updated,
        )
        with open(handoff_path, "w", encoding="utf-8") as handle:
            handle.write(updated)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())