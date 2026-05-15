import cv2
import numpy as np

print("--------------------------\n")
print("\n Starting Generator \n")
print("--------------------------\n")

# -- STEP 1: LOAD THE DATA ---
try:
    labels = np.load('labels.npy')
    print("Successfully loaded labels grid!")
except FileNotFoundError:
    print("Error: Could not find labels.npy. Run preprocessor.py first!")
    exit()

h, w = labels.shape
n_colors = 5

# -- STEP 2: ISOLATE THE MASKS ---
# We will store our 5 masks in a Python list
color_masks = []

for k in range(n_colors):
    # This creates the 1s and 0s
    # We multiply by 255 just so it shows up as bright white on our screen instead of pure black
    mask = (labels == k).astype(np.uint8) * 255
    color_masks.append(mask)

# -- STEP 3: CREATE THE INITIALIZATION FRAME (M_-1) ---
# Create a blank black canvas (all 0s)
m_minus_1 = np.zeros((h, w), dtype=np.uint8)

# Draw a white rectangle (1s) around the very edge to act as our "Photo Frame" 
# Thickness is 15 pixels
frame_thickness = 15
cv2.rectangle(m_minus_1, (0,0), (w-1, h-1), 255, frame_thickness)

print("Isolated masks and created the M_-1 Safe Zone frame.")

# -- STEP 4: VISUALIZE TO VERIFY ---
# Let's look at Mask 0 and our new Frame
cv2.imshow("Color Mask 0", color_masks[0])
cv2.imshow("M_-1 (Initial Safe Zone)", m_minus_1)

print("Press any key on your keyboard while selecting the image window to close.")
cv2.waitKey(0)
cv2.destroyAllWindows()