import cv2
import numpy as np
from sklearn.cluster import KMeans

print("--------------------------\n")
print("\n Starting preprocessor \n")
print("--------------------------\n")

# --- STEP 1: LOAD IMAGE ---
image_path = './images/Chinese_Pattern_Heather.png'
img_bgr = cv2.imread(image_path)

if img_bgr is None:
    print(f"Error: Could not load image at {image_path}. Check the file name.")
    exit()

# --- STEP 2: COLOR CONVERSION (BGR to LAB) ---
img_lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

# --- STEP 3: FLATTEN IMAGE (The Reshape Step) ---
# Get the height, width, and number of channels (3 for L, A, B)
h, w, channels = img_lab.shape

# Flatten the 3D grid into a 2D list of pixels
pixels = img_lab.reshape((-1, 3))

# --- STEP 4; K-MEANS CLUSTERING ---
print("Running K-Means (this might take a few seconds)...")
n_colors = 5
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

print("Press any key on your keyboard while selecting the image window to close.")
cv2.waitKey(0)
cv2.destroyAllWindows()