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
n_colors = int(np.load('n_colors.npy')[0])
print(f"Loaded n_colors = {n_colors} from preprocessor")

# -- STEP 2: ISOLATE THE MASKS ---
# One binary mask per color: 255 = this pixel belongs to this color, 0 = it does not
color_masks = []
for k in range(n_colors):
    mask = (labels == k).astype(np.uint8) * 255
    color_masks.append(mask)

# -- STEP 3: CREATE THE INITIALIZATION FRAME (M_-1) ---
# The frame acts as the starting "safe zone" — all patches must eventually connect to it.
# Two spatially disconnected regions that both touch the frame boundary are treated
# as a single connected component, which is the paper's "photo frame" trick.
m_minus_1 = np.zeros((h, w), dtype=np.uint8)
frame_thickness = 15
cv2.rectangle(m_minus_1, (0, 0), (w - 1, h - 1), 255, frame_thickness)
print("Isolated masks and created the M_-1 frame (initial safe zone).")

# Remove frame pixels from every color mask so those pixels are never re-claimed
for k in range(n_colors):
    color_masks[k] = cv2.bitwise_and(color_masks[k], cv2.bitwise_not(m_minus_1))

# -- STEP 4: PREPARE THRESHOLDS ---
# All three thresholds come directly from the paper's recommended percentages.
diagonal = math.sqrt(w ** 2 + h ** 2)
omega_budget     = 0.03  * diagonal          # max total bridge length per layer (3% of diagonal)
delta_widening_px = max(1, int(0.002 * diagonal))  # skeleton dilation radius (0.2% of diagonal)
gamma_hole_area  = 0.0001 * (w * h)          # holes smaller than this get filled (0.01% of area)

print(f"Distance Budget  (omega):  {omega_budget:.2f} px")
print(f"Widening Radius  (delta):  {delta_widening_px} px")
print(f"Tiny Hole Limit  (gamma):  {gamma_hole_area:.2f} px²")

# -- STEP 5: GREEDY LAYER GENERATION LOOP ---
# Each iteration of the outer while-loop produces one layer.
# Each iteration of the inner for-loop tests one color as a candidate for that layer.
# The color that connects the most patches (nearest-first traversal) wins.
print("\n--- Running Greedy Layer Generation ---")

global_safe_zone        = m_minus_1.copy()
layer_counter           = 0
layer_order             = []   # which color index was chosen for each layer
generated_layers        = []   # XOR diff showing only what was newly added per layer
winning_safe_zone_history = [] # cumulative safe zone after each layer (used for saving)
min_patch_area = int(0.00005 * w * h)  # 0.005% of total image area

while True:
    print(f"\n--- Calculating Layer {layer_counter} ---")

    best_color        = -1
    max_area_connected = -1
    winning_safe_zone = None

    # --- Test every color to find which one connects the most patches ---
    for k in range(n_colors):
        current_mask = color_masks[k]

        # Decompose this color's mask into individual connected patches
        num_patches, patch_labels, stats, _ = cv2.connectedComponentsWithStats(current_mask)

        # Filter out micro-patches (noise artifacts) — keep only patches above a
        # size threshold scaled to the image rather than a hardcoded value.
        valid_patches = [
            patch_id
            for patch_id in range(1, num_patches)
            if stats[patch_id, cv2.CC_STAT_AREA] > min_patch_area
        ]

        if not valid_patches:
            continue

        # Simulate building this layer using nearest-first greedy traversal.
        # We start from the current global safe zone and greedily absorb the
        # nearest remaining patch each iteration, updating the safe zone as we go.
        # This matches the paper: "let p^k_{i0} be the patch closest to p'_0,
        # connect them to form p'_1, then find the nearest patch to p'_1..." etc.
        hypothetical_safe_zone = global_safe_zone.copy()
        remaining_patches      = list(valid_patches)
        connected_area        = 0
        spent_budget           = 0.0

        while remaining_patches:
            # Recompute distances from the CURRENT safe zone on every iteration.
            # This is the critical fix: as patches join the safe zone, previously
            # distant patches may now be reachable for free, preserving symmetry.
            inverted_safe_zone = cv2.bitwise_not(hypothetical_safe_zone)
            dist_map = cv2.distanceTransform(inverted_safe_zone, cv2.DIST_L2, 5)

            # Find the single nearest patch to the current safe zone
            nearest_patch_id = None
            nearest_distance = float('inf')

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
                # Patch already touches the safe zone — free connection
                connected_area += int(np.sum(patch_pixels)) 
                hypothetical_safe_zone[patch_pixels] = 255
                remaining_patches.remove(nearest_patch_id)

            elif (spent_budget + nearest_distance) <= omega_budget:
                # Patch is floating but a bridge is affordable — draw and connect
                spent_budget += nearest_distance
                connected_area += int(np.sum(patch_pixels))

                # Find the point on this patch closest to the safe zone
                patch_dist_map = np.where(patch_pixels, dist_map, np.inf)
                min_y, min_x = np.unravel_index(np.argmin(patch_dist_map), patch_dist_map.shape)

                # Find the nearest point on the safe zone edge
                safe_edge = cv2.morphologyEx(
                    hypothetical_safe_zone, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)
                )
                edge_y, edge_x = np.where(safe_edge > 0)
                distances_sq = (edge_x - min_x) ** 2 + (edge_y - min_y) ** 2
                best_edge_idx = np.argmin(distances_sq)
                target_x = int(edge_x[best_edge_idx])
                target_y = int(edge_y[best_edge_idx])

                # Draw the 1-pixel bridge
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
                # The nearest remaining patch is already over budget.
                # Because we always pick the nearest patch first, all remaining
                # patches are at least this far away — none can be connected.
                break

        print(f"  Color {k}: connected {connected_area}/{len(valid_patches)} patches | "
              f"bridge cost {spent_budget:.1f}/{omega_budget:.1f} px")

        # Record if this color is the best candidate so far
        if connected_area > max_area_connected:
            max_area_connected = connected_area
            best_color            = k
            winning_safe_zone     = hypothetical_safe_zone.copy()

    # -- END OF CANDIDATE TESTING --

    if max_area_connected == 0 or best_color == -1:
        print("\n[!] STUCK: No patches can be reached with the current budget. Stopping.")
        break

    print(f"WINNER: Layer {layer_counter} → Color {best_color} "
          f"({max_area_connected} patches connected)")
    layer_order.append(best_color)

    # -- PHASE C: POST-PROCESSING (widening + fill tiny holes) --
    print("   -> Widening skeleton and filling tiny holes...")

    # 1. Widen skeleton — thickens fragile 1-pixel bridges to be laser-cuttable
    skeleton = cv2.ximgproc.thinning(winning_safe_zone)
    kernel_size = delta_widening_px * 2 + 1
    dilation_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    dilated_skeleton = cv2.dilate(skeleton, dilation_kernel)
    winning_safe_zone = cv2.bitwise_or(winning_safe_zone, dilated_skeleton)

    # 2. Fill tiny holes — removes gaps too small to fabricate
    inverted_layer = cv2.bitwise_not(winning_safe_zone)
    num_holes, hole_labels, hole_stats, _ = cv2.connectedComponentsWithStats(inverted_layer)
    for hole_id in range(1, num_holes):
        if hole_stats[hole_id, cv2.CC_STAT_AREA] < gamma_hole_area:
            winning_safe_zone[hole_labels == hole_id] = 255
    
    # FREE PICKUP PASS: widening may have grown the safe zone enough to
    # now touch patches that were just out of reach during scoring.
    # Add any same-color patches now at distance 0 for free.
    print("   -> Free pickup pass after widening...")
    pickup_happened = True
    while pickup_happened:
        pickup_happened = False
        
        inverted = cv2.bitwise_not(winning_safe_zone)
        dist_map_post = cv2.distanceTransform(inverted, cv2.DIST_L2, 5)
        
        # Work from the color mask with already-claimed pixels removed
        # so we never re-examine patches that were already added
        remaining_color_mask = cv2.bitwise_and(
            color_masks[best_color],
            cv2.bitwise_not(winning_safe_zone)  # exclude anything already in safe zone
        )
        
        num_p, p_labels, p_stats, _ = cv2.connectedComponentsWithStats(remaining_color_mask)
        
        for pid in range(1, num_p):
            if p_stats[pid, cv2.CC_STAT_AREA] <= min_patch_area:
                continue
            patch_pixels = (p_labels == pid)
            if np.min(dist_map_post[patch_pixels]) == 0:
                winning_safe_zone[patch_pixels] = 255
                pickup_happened = True
                # Break so we recompute dist_map before checking more patches,
                # since adding this patch may make others newly reachable
                break

    # Compute what was newly added this layer (XOR gives the diff)
    newly_added = cv2.bitwise_xor(winning_safe_zone, global_safe_zone)
    generated_layers.append(newly_added.copy())

    # Erase claimed pixels from all color masks to prevent them being reused
    for c_idx in range(n_colors):
        color_masks[c_idx] = cv2.bitwise_and(
            color_masks[c_idx],
            cv2.bitwise_not(winning_safe_zone)
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

# -- STEP 6: SAVE OUTPUTS --
output_dir = './output_pyrMeanShiftFiltering_nk_new_generator_fair_selection_pickup'
os.makedirs(output_dir, exist_ok=True)
print(f"Saving {len(generated_layers)} layers to '{output_dir}'...")

cv2.imwrite(os.path.join(output_dir, "Final_Global_Safe_Zone.png"), global_safe_zone)

for i, color_id in enumerate(layer_order):
    filename = f"Layer_{i:02d}_Color_{color_id}.png"
    cv2.imwrite(os.path.join(output_dir, filename), winning_safe_zone_history[i])

print("\n--------------------------")
print(" ALL FILES SAVED SUCCESSFULLY!")
print("--------------------------\n")