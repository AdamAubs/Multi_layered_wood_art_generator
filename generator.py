import cv2
import numpy as np
import math
import os

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

# --- Clean up the initial overlapping edges ---
# Erase the frame area from all color masks so we don't get stuck in an infinite loop
# trying to add pieces that are already covered by the frame!
for k in range(n_colors):
    color_masks[k] = cv2.bitwise_and(color_masks[k], cv2.bitwise_not(m_minus_1))

# --- STEP 4: PREPARE THE DISTANCE BUDGET ---
# The paper defines the budget (omega) as 3% of the image diagonal
diagonal = math.sqrt(w**2 + h**2)
omega_budget = 0.03 * diagonal
delta_widening_px = int(0.002 * diagonal) # 0.2% of diagonal for widening
gamma_hole_area = 0.0001 * (w * h)        # 0.01% of total image area for tiny holes

if delta_widening_px < 1: delta_widening_px = 1

print(f"Distance Budget (Omega): {omega_budget:.2f} pixels")
print(f"Widening Thickness (Delta): {delta_widening_px} pixels")
print(f"Tiny Hole Max Area (Gamma): {gamma_hole_area:.2f} pixels")

# --- STEP 5: THE GREEDY GENERATION LOOP ---
print("\n--- Running Greedy Simulations ---")
global_safe_zone = m_minus_1.copy()
layer_counter = 0
layer_order = [] # Keeps track of which color became which layer
generated_layers = [] # Stores the actual image masks for each layer
winning_safe_zone_history = [] # Stores the 

# Continue looping until the entire global safe zone is white (no 0s left)
while True:
    print(f"\n--- Calculating Layer {layer_counter} ---")

    best_color = -1
    max_patches_connected = -1
    winning_safe_zone = None

    # Test every color to see which one connects the most pieces
    for k in range(n_colors):
        current_mask = color_masks[k]

        # 1. Break the mask into pieces AND get their physical sizes (Stats)
        num_patches, patch_labels, stats, centroids = cv2.connectedComponentsWithStats(current_mask)
        
        # Create a list to hold ONLY the pieces that are big enough to matter
        valid_patches = []
        
        # We start at 1 to skip the black background (which is index 0)
        for patch_id in range(1, num_patches):
            # stats[patch_id, cv2.CC_STAT_AREA] gets the square pixel area of the piece
            piece_area = stats[patch_id, cv2.CC_STAT_AREA]
            
            # THE FILTER: Only keep pieces larger than 10 pixels!
            if piece_area > 10:
                valid_patches.append(patch_id)
                
        total_pieces = len(valid_patches) 

        # If there are no pieces left for this color, skip it
        if total_pieces <= 0:
            continue

        # Create a hypothetical safe zone for this color's simulation 
        # IMPORTANT: We now start from the creeping global_safe_zone, not the starting frame!
        hypothetical_safe_zone = global_safe_zone.copy()

        connected_count = 0
        spent_budget = 0.0

        # 2. Create the L2-Norm Radar (Distance Transform)
        # We invert the safe zone so the safe zone is 0 (black), and empty space is >0 (white)
        inverted_safe_zone = cv2.bitwise_not(hypothetical_safe_zone)
        dist_map = cv2.distanceTransform(inverted_safe_zone, cv2.DIST_L2, 5)

        # 3. Measure the distance to every single puzzle piece
        for patch_id in valid_patches:
            # Isolate this specific puzzle piece
            single_piece_mask = (patch_labels == patch_id)

            # Look at the distance map specifically underneath this piece
            # The shortest L2-norm distance is simply the smallest number on the map!
            shortest_distance = np.min(dist_map[single_piece_mask])

            # 4. Check Connectivity and Budget
            if shortest_distance == 0:
                # It is physically touching the Safe Zone! (A Neighbor)
                connected_count += 1
                # Add it to the safe zone (Cost is 0)
                hypothetical_safe_zone[single_piece_mask] = 255

            elif (spent_budget + shortest_distance) <= omega_budget:
                # It is floating, but we can afford to build a bridge!
                spent_budget += shortest_distance
                connected_count += 1

                # --- NEW DRAW THE PHYSICAL 1-PIXEL BRIDGE ---
                # 1. Find the exact coordinate on the patch closest to the Safe Zone
                patch_dist = np.where(single_piece_mask, dist_map, np.inf)
                min_y, min_x = np.unravel_index(np.argmin(patch_dist), patch_dist.shape)

                # 2. Find the exact coordinate on the edge of the Safe Zone closes to the patch
                safe_edge = cv2.morphologyEx(hypothetical_safe_zone, cv2.MORPH_GRADIENT, np.ones((3,3), np.uint8))
                edge_y, edge_x = np.where(safe_edge > 0)

                distances_sq = (edge_x - min_x)**2 + (edge_y - min_y)**2
                best_idx = np.argmin(distances_sq)
                target_x, target_y = edge_x[best_idx], edge_y[best_idx]

                # 3. Draw the line!
                # Ensure coordinates are native Python ints (not numpy types) for OpenCV
                cv2.line(
                    hypothetical_safe_zone,
                    (int(min_x), int(min_y)),
                    (int(target_x), int(target_y)),
                    255,
                    1,
                )

                # 4. Fill in the patch 
                hypothetical_safe_zone[single_piece_mask] = 255

        print(f"Color {k}: Connected {connected_count}/{total_pieces} pieces. Cost: {spent_budget:.2f}px")

        # --- STEP 6: RECORD THE WINNER (PHASE B) ---
        if connected_count > max_patches_connected:
            max_patches_connected = connected_count
            best_color = k
            winning_safe_zone = hypothetical_safe_zone.copy()

    # --- STEP 6: END OF ROUND PROCESSING ---

    # Failsafe: If no pieces could be connected, the budget is too small to cross the gap
    if max_patches_connected == 0 or best_color == -1:
        print("\n[!] ALGORITHM STUCK: Cannot reach any remaining pieces with the current budget.")
        break

    print(f"WINNER: Layer {layer_counter} is Color {best_color} (Connected {max_patches_connected} pieces)")
    layer_order.append(best_color)

    # --- NEW: PHASE C (WIDENING & FILLING HOLES) ---
    print("   -> Widening skeleton and filling tiny holes...")

    # 1. Widen the Skeleton (Thicken the fragile bridges)
    skeleton = cv2.ximgproc.thinning(winning_safe_zone)
    kernel_size = delta_widening_px * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    dilated_skeleton = cv2.dilate(skeleton, kernel)

    # Merge the thick skeleton back into the layer
    winning_safe_zone = cv2.bitwise_or(winning_safe_zone, dilated_skeleton)

    # 2. Fill Tiny Holes (Melt away un-manufacturable gaps)
    # We invert the mask so the "holes" (0s) become solid objects (255s) we can measure
    num_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(winning_safe_zone))

    for hole_id in range(1, num_holes): # Skip 0 (the giant background outside the frame)
            hole_area = hole_stats[hole_id, cv2.CC_STAT_AREA]
            if hole_area < gamma_hole_area:
                # It's too small! Fill it with wood
                winning_safe_zone[hole_labels == hole_id] = 255

    
    if winning_safe_zone is None:
        winning_safe_zone = global_safe_zone.copy()
    # Consume the winning pieces so they can't be reused
    # 1. Find exactly what was just added (XOR find the difference between the old and new safe zone)
    just_added_pieces = cv2.bitwise_xor(winning_safe_zone, global_safe_zone)

    # Save this raw layer so we can look at it
    generated_layers.append(just_added_pieces.copy())

   # 2. Erase the newly created solid wood from ALL color masks to prevent Ghost Loops!
    for c_idx in range(n_colors):
        color_masks[c_idx] = cv2.bitwise_and(
            color_masks[c_idx],
            cv2.bitwise_not(winning_safe_zone)
        ) 
    winning_safe_zone_history.append(winning_safe_zone.copy())
    # Update the Global Safe Zone (The creeping shadow moves inward!)
    global_safe_zone = winning_safe_zone.copy()


    layer_counter += 1

    # Infinite loop failsafe
    if layer_counter > 50:
        print("\n[!] SAFETY LIMIT REACHED: Over 50 layers generated. Exiting loop.")
        break
    
print("\n--------------------------")
print(" GENERATION COMPLETE")
print(f" Final Layer Order (Top to Bottom): {layer_order}")
print("--------------------------\n")

# --- STEP 7: SAVE THE FINAL RESULT ---
# Define the path to the parent directory's output folder
output_dir = './output_test_bilateral_filter'

# Create the folder if it doesn't already exist
os.makedirs(output_dir, exist_ok=True)

print(f"Saving {len(generated_layers)} layers to '{output_dir}'...")

# Save the final Safe Zone just to confirm it filled up
final_path = os.path.join(output_dir, "Final_Global_Safe_Zone.png")
cv2.imwrite(final_path, global_safe_zone)

# Loop through our saved layers and save them as PNG files
for i in range(len(generated_layers)):
    color_id = layer_order[i]
    
    # We use {i:02d} so the files sort correctly in your folder (00, 01, 02...)
    filename = f"Layer_{i:02d}_Color_{color_id}.png"
    filepath = os.path.join(output_dir, filename)
    
    cv2.imwrite(filepath, winning_safe_zone_history[i])

print("\n--------------------------")
print(" ALL FILES SAVED SUCCESSFULLY!")
print("--------------------------\n")