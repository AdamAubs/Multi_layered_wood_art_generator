import argparse
import json
import os

import cv2
import numpy as np
from itertools import combinations
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


def parse_args():
    parser = argparse.ArgumentParser(
        description="Preprocess an image into labels.npy and n_colors.npy."
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to the input image.",
    )
    parser.add_argument(
        "--filter",
        choices=["meanshift", "bilateral"],
        default="meanshift",
        help="Simplification filter to apply before clustering.",
    )
    parser.add_argument(
        "--meanshift-sp",
        type=int,
        default=20,
        help="Mean shift spatial window radius.",
    )
    parser.add_argument(
        "--meanshift-sr",
        type=int,
        default=60,
        help="Mean shift color window radius.",
    )
    parser.add_argument(
        "--meanshift-max-level",
        type=int,
        default=2,
        help="Mean shift pyramid max level.",
    )
    parser.add_argument(
        "--bilateral-d",
        type=int,
        default=15,
        help="Bilateral filter diameter of pixel neighborhood.",
    )
    parser.add_argument(
        "--sigma-color",
        type=float,
        default=80.0,
        help="Bilateral filter sigmaColor.",
    )
    parser.add_argument(
        "--sigma-space",
        type=float,
        default=80.0,
        help="Bilateral filter sigmaSpace.",
    )
    parser.add_argument(
        "--bilateral-passes",
        type=int,
        default=3,
        help="How many times to apply the bilateral filter.",
    )
    parser.add_argument(
        "--out-dir",
        default="preprocessor_output",
        help="Output directory for labels.npy and n_colors.npy.",
    )
    return parser.parse_args()


def load_image(image_path):
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise FileNotFoundError(
            f"Error: Could not load image at {image_path}. Check the file name."
        )
    return img_bgr


def simplify_image(img_bgr, args):
    print("Simplifying image to remove gradients and noise...")
    if args.filter == "bilateral":
        for _ in range(args.bilateral_passes):
            img_bgr = cv2.bilateralFilter(
                img_bgr,
                args.bilateral_d,
                args.sigma_color,
                args.sigma_space,
            )
        return img_bgr

    return cv2.pyrMeanShiftFiltering(
        img_bgr,
        sp=args.meanshift_sp,
        sr=args.meanshift_sr,
        maxLevel=args.meanshift_max_level,
    )


def derive_run_name(image_path):
    filename = os.path.basename(image_path)
    run_name, _ = os.path.splitext(filename)
    return run_name


def find_optimal_k(pixels, k_range=range(3, 10)):
    # Sample pixels for speed (silhouette is slow on large arrays)
    sample_idx = np.random.choice(len(pixels), min(5000, len(pixels)), replace=False)
    sample = pixels[sample_idx]

    wcss = []
    sil_scores = []

    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=5)
        km.fit(sample)
        wcss.append(km.inertia_)
        sil_scores.append(silhouette_score(sample, km.labels_) if k > 2 else 0)
    
    # Elbow: where the rate of WCSS improvement slows down most
    wcss = np.array(wcss)
    deltas = np.diff(wcss)
    elbow_idx = np.argmax(np.diff(deltas)) + 1
    elbow_k = list(k_range)[elbow_idx]

    # Silhouette: first k where score exceeds threshold
    threshold = 0.35
    valid_ks = [k for k, s in zip(k_range, sil_scores) if s >= threshold]

    best_k = max(elbow_k, min(valid_ks) if valid_ks else elbow_k)

    print(f"  WCSS values:      {[round(w) for w in wcss]}")
    print(f"  Silhouette scores:{[round(s, 3) for s in sil_scores]}")
    print(f"  Elbow at k={elbow_k}, silhouette valid from k={min(valid_ks) if valid_ks else '?'}")
    print(f"  >>> Auto-selected n_colors = {best_k}")
    return best_k


def run_kmeans(pixels, n_colors):
    print("Running K-Means (this might take a few seconds)...")
    kmeans = KMeans(n_clusters=n_colors, random_state=42)
    kmeans.fit(pixels)
    centers = kmeans.cluster_centers_.astype(np.uint8)
    labels = kmeans.labels_
    return centers, labels


def merge_similar_clusters(labels, centers_lab, delta_e_threshold=0.0):
    """
    After K-means, merge any two clusters whose LAB centers are within
    delta_e_threshold of each other (Euclidean distance in LAB ≈ ΔE).
    Returns updated labels and a mapping from old cluster id to new cluster id.
    """
    n = len(centers_lab)
    # Build a union-find structure to track merges
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    # Check all pairs of cluster centers
    for i, j in combinations(range(n), 2):
        dist = np.linalg.norm(centers_lab[i].astype(float) - centers_lab[j].astype(float))
        if dist < delta_e_threshold:
            print(f"  Merging cluster {i} and {j}: LAB distance = {dist:.1f} < {delta_e_threshold}")
            union(i, j)

    # Build remapping: old cluster id -> new sequential id
    root_to_new = {}
    new_id = 0
    remap = {}
    for k in range(n):
        root = find(k)
        if root not in root_to_new:
            root_to_new[root] = new_id
            new_id += 1
        remap[k] = root_to_new[root]

    # Apply remapping to every pixel's label
    new_labels = np.vectorize(remap.get)(labels)
    n_new = len(set(new_labels.flatten()))

    print(f"  Clusters after perceptual merge: {n} → {n_new}")
    return new_labels, n_new


def save_outputs(labels_2d, n_colors, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "labels.npy"), labels_2d)
    np.save(os.path.join(out_dir, "n_colors.npy"), np.array([n_colors]))


def save_run_metadata(out_dir, run_name, image_path, palette=None):
    """Save run metadata. If `palette` is provided, include it.

    palette: list of dicts with keys: id, rgb, lab, name
    """
    metadata = {
        "run_name": run_name,
        "image_path": image_path,
    }
    if palette is not None:
        metadata["palette"] = palette
    metadata_path = os.path.join(out_dir, "run_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)


def main():
    print("--------------------------\n")
    print("\n Starting preprocessor \n")
    print("--------------------------\n")

    args = parse_args()

    # Load and simplify
    try:
        img_bgr = load_image(args.image)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    img_bgr = simplify_image(img_bgr, args)

    # Convert to LAB and flatten for clustering
    img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    h, w, _ = img_lab.shape
    pixels = img_lab.reshape((-1, 3))

    print("Determining optimal color count...")
    n_colors = find_optimal_k(pixels)
    centers, labels = run_kmeans(pixels, n_colors)

    # Merge perceptually similar clusters before saving
    labels_2d = labels.reshape((h, w))
    labels_2d, n_colors = merge_similar_clusters(labels_2d.flatten(), centers)
    labels_2d = labels_2d.reshape((h, w))

    save_outputs(labels_2d, n_colors, args.out_dir)
    run_name = derive_run_name(args.image)

    # Build palette: mean color (RGB) and LAB per cluster id
    palette = []
    h, w, _ = img_bgr.shape
    for k in range(n_colors):
        mask = (labels_2d == k)
        if np.any(mask):
            pixels = img_bgr[mask]
            mean_bgr = pixels.mean(axis=0)
            # mean_bgr is B, G, R
            r = int(round(mean_bgr[2]))
            g = int(round(mean_bgr[1]))
            b = int(round(mean_bgr[0]))
            # compute LAB via OpenCV (expects BGR)
            lab = cv2.cvtColor(
                np.uint8([[[int(round(mean_bgr[0])), int(round(mean_bgr[1])), int(round(mean_bgr[2]))]]]),
                cv2.COLOR_BGR2LAB,
            )[0, 0].tolist()
        else:
            # fallback: try to use kmeans centers if present
            try:
                c_lab = centers[k]
                lab = [int(round(c_lab[0])), int(round(c_lab[1])), int(round(c_lab[2]))]
                bgr = cv2.cvtColor(np.uint8([[[lab[0], lab[1], lab[2]]]]), cv2.COLOR_LAB2BGR)[0, 0]
                b, g, r = [int(x) for x in bgr]
            except Exception:
                r, g, b = 0, 0, 0
                lab = [0, 0, 0]

        palette.append({"id": int(k), "rgb": [r, g, b], "lab": lab, "name": None})

    save_run_metadata(args.out_dir, run_name, args.image, palette=palette)
    print(f"Saved outputs to '{args.out_dir}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
