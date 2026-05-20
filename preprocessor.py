import cv2
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

print("--------------------------\n")
print("\n Starting preprocessor \n")
print("--------------------------\n")

# --- STEP 1: LOAD IMAGE ---
# image_path = 'images/Elgin_map.png'
image_path = 'images/Chinese_Pattern_Heather.png'
img_bgr = cv2.imread(image_path)

if img_bgr is None:
    print(f"Error: Could not load image at {image_path}. Check the file name.")
    exit()

# --- STEP 1.5: IMAGE SIMPLIFICATION (The LIVE Alternative) ---
print("Simplifying image to remove gradients and noise...")

# 1. Scale up the image to high resolution
# We double the size (200%) to give the laser cutter smoother curves
# scale_percent = 200
# width = int(img_bgr.shape[1] * scale_percent / 100)
# height = int(img_bgr.shape[0] * scale_percent / 100)
# img_bgr = cv2.resize(img_bgr, (width, height), interpolation=cv2.INTER_CUBIC)

# # # 2. Apply a Bilateral Filter (The "Cartoon" Filter)
# # Parameters: (image, diameter of pixel neighborhood, sigmaColor, sigmaSpace)
# # We run it 3 times in a row to aggressively melt the gradients into flat colors!
# for _ in range(3):
#     img_bgr = cv2.bilateralFilter(img_bgr, 15, 80, 80)

# # Instead of bilateral loop, try this:
img_bgr = cv2.pyrMeanShiftFiltering(img_bgr, sp=20, sr=60, maxLevel=2)
# sp = spatial window radius, sr = color window radius
# Tweak sr upward (60-80) for fewer, broader color regions

# --- STEP 2: COLOR CONVERSION (BGR to LAB) ---
img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

# --- STEP 3: FLATTEN IMAGE (The Reshape Step) ---
# Get the height, width, and number of channels (3 for L, A, B)
h, w, channels = img_lab.shape

# Flatten the 3D grid into a 2D list of pixels
pixels = img_lab.reshape((-1, 3))

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

# --- STEP 4; K-MEANS CLUSTERING ---
print("Determining optimal color count...")
n_colors = find_optimal_k(pixels)

print("Running K-Means (this might take a few seconds)...")
kmeans = KMeans(n_clusters=n_colors, random_state=42)
kmeans.fit(pixels)

# -- STEP 5: RECONSTRUCT IMAGE ---
# Grab the 5 "average" colors found by K-means
# Ensure centers is a proper numpy array of dtype uint8
centers = kmeans.cluster_centers_.astype(np.uint8)

# Grab the list that tells us which bucket every pixel belongs to
labels = kmeans.labels_

# Replace every original pixel with its new assigned bucket color
# Use np.take to avoid indexing issues with certain dtypes
quantized_pixels = np.take(centers, labels, axis=0)

# Reshape the flat list back into a 3D image grid
quantized_lab = quantized_pixels.reshape((h, w, channels))

# --- STEP 6: VISUALIZE ---
# Convert back to BGR so our screen can display it properly
quantized_bgr = cv2.cvtColor(quantized_lab, cv2.COLOR_LAB2BGR)

# Show the images in pop-up windows
cv2.imshow("Original", img_bgr)
cv2.imshow(f"Quantized ({n_colors} Colors)", quantized_lab)

# print("Press any key on your keyboard while selecting the image window to close.")
# cv2.waitKey(0)
# cv2.destroyAllWindows()

# Reshape the flat labels list back into a 2D (height, width) grid before saving
np.save('labels.npy', labels.reshape((h, w)))
np.save('n_colors.npy', np.array([n_colors]))
