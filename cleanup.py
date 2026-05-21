import argparse
import os
import shutil


def parse_args():
    parser = argparse.ArgumentParser(
        description="Remove generated output folders from the project root."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print folders to be removed without deleting them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Delete without confirmation prompt.",
    )
    return parser.parse_args()


def find_targets(root_dir):
    targets = []
    for name in os.listdir(root_dir):
        path = os.path.join(root_dir, name)
        if not os.path.isdir(path):
            continue
        if name == "preprocessor_output":
            targets.append(path)
            continue
        if name.startswith("output_generator"):
            targets.append(path)
            continue
        if name.startswith("output_postprocessed"):
            targets.append(path)
            continue
    return sorted(targets)


def prompt_confirmation(targets):
    print("The following folders will be removed:")
    for path in targets:
        print(f"  - {os.path.basename(path)}")
    response = input("Proceed? [y/N] ").strip().lower()
    return response == "y"


def main():
    args = parse_args()
    root_dir = os.path.dirname(os.path.abspath(__file__))
    targets = find_targets(root_dir)

    if not targets:
        print("No generated folders found to remove.")
        return 0

    if args.dry_run:
        print("Dry run - no changes made.")
        for path in targets:
            print(f"  - {os.path.basename(path)}")
        return 0

    if not args.yes and not prompt_confirmation(targets):
        print("Cancelled.")
        return 0

    for path in targets:
        shutil.rmtree(path)

    print("Cleanup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
