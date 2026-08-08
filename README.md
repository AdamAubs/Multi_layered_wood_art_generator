## Multi Layered Wood Art Generator

This project turns an input image into a set of layered, laser-cuttable masks using a three-stage pipeline:
preprocessor -> generator -> postprocessor.

### Quick Start

Create and activate your own virtual environment, then install the project dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the entire pipeline in one command (optionally produce a combined stock layout):

```bash
python pipeline.py --image images/GPT4.0/Stylized_crane_with_pine_branches.png --stock-size-in 12x20
```

Best results usually come from images with a small number of clear, flat color regions, strong contrast between shapes, and minimal gradients or texture. Those kinds of images are easier for the clustering and layer-building steps to separate cleanly.

If you are generating a new image, see [image_gen_prompts/generic-reccomendations.md](image_gen_prompts/generic-reccomendations.md) for prompt ideas and composition tips that fit this pipeline well.

If you want the final DXF files to end up at a specific size, add `--fab-size-in`. The value uses `WxH` inches, such as `5x5`, and the pipeline computes the needed DXF DPI automatically:

```bash
python pipeline.py --image images/GPT4.0/Stylized_crane_with_pine_branches.png --fab-size-in 5x5
```

This flag sets the final outside size of the DXF, including the frame margin. For now it is intentionally strict: the source image must be square, and non-square images will fail fast instead of being stretched or fit into the box.

Cleanup generated folders:

```bash
python cleanup.py
```

Preview what will be removed:

```bash
python cleanup.py --dry-run
```

Optional timestamped outputs for testing:

```bash
python pipeline.py --image images/Stylized_crane_with_pine_branches.png --timestamp
```

Outputs:

- Generator: output*generator*<run_name> (or with \_YYYYMMDD_HHMMSS when using --timestamp)
- Postprocessor: output*postprocessed*<run_name> (or with \_YYYYMMDD_HHMMSS when using --timestamp)
- Final package: output*final*<run_name> (or with \_YYYYMMDD_HHMMSS when using --timestamp)

The run name is derived from the image filename stem.

### Run Each Stage Individually

#### 1) Preprocessor

Simplifies the image and creates clustering outputs.

```bash
python preprocessor.py --image images/GPT4.0/Stylized_crane_with_pine_branches.png
```

Optional filter settings:

```bash
python preprocessor.py --image images/GPT4.0/Stylized_crane_with_pine_branches.png \
	--filter bilateral --bilateral-d 15 --sigma-color 80 --sigma-space 80 --bilateral-passes 3
```

Outputs:

- preprocessor_output/labels.npy
- preprocessor_output/n_colors.npy
- preprocessor_output/run_metadata.json

#### 2) Generator

Greedy layer generation based on the preprocessor outputs.

```bash
python generator.py
```

Optional timestamped output:

```bash
python generator.py --timestamp
```

Outputs:

- output*generator*<run_name>/Layer_XX_Color_Y.png
- output*generator*<run_name>/layer_order.npy
- output*generator*<run_name>/frame.npy

#### 3) Postprocessor

Merges small visible regions and rebuilds the cumulative layers.

```bash
python postprocessor.py --finalize
```

~~Stress analysis~~ and widening weak members:

Currently the `--stress-analysis` command will NOT generate a stress analysis. Only the
optional named flags are currently implemented and tested. The stress analysis needs further review
due extremely long runtimes with in accurate results.

For the common workflow, use `--finalize` first and only reach for the advanced flags when you are tuning a specific layer or fabrication outcome.

Widening weak members:

```bash
# Detect anything under 4px, widen it out to 8px
python postprocessor.py --stress-analysis --thin-min-width 4 --thin-widen-to 8

# Detect anything under 6px, widen to 12px (very aggressive)
python postprocessor.py --stress-analysis --thin-min-width 6 --thin-widen-to 12
```

~~Optional stress settings:~~

<!-- ```bash
python postprocessor.py --stress-analysis \
	--stress-beta 20 \
	--stress-fea-size 100 \
	--stress-thickness-mm 3 \
	--stress-sheet-mm 400 \
	--stress-max-iters 10 \
	--stress-save-maps
```

What it does:

- Runs a simple 2-D FEA pass on each layer.
- Finds regions above the stress threshold and widens them until they are below `--stress-beta` or `--stress-max-iters` is reached.
- Keeps the widened result inside the frame boundary.

What it outputs:

- Updated `output_postprocessed_<run_name>/Layer_XX_Color_Y.png` masks.
- `layer_order.npy` and `frame.npy` for the merged result.
- `Final_Global_Safe_Zone.png` showing the final cumulative safe zone.
- Optional `*_stress_iterXX.png` heatmaps when `--stress-save-maps` is used. -->

Override input/output directories:

```bash
python postprocessor.py --in-dir output_generator_<run_name> --out-dir output_postprocessed_<run_name>
```

DXF export (one DXF with a layer per mask):

```bash
python postprocessor.py --export-dxf
```

Final fabrication package (per-layer PNG + DXF + handoff markdown):

```bash
# Create the final fabrication package (output_final_<run_name>)
python postprocessor.py --finalize

# Specify a custom final directory and omit friendly names
python postprocessor.py --finalize --final-dir output_final_myrun --no-color-names
```

If you run `--stress-analysis` in a separate step first, `--finalize` now prefers the matching `output_postprocessed_<run_name>` directory when it exists. That keeps the widened masks from the earlier postprocessing pass instead of rebuilding from the original generator output.

If the final package already has stock-layout metadata, or you pass `--stock-size-in`, `--finalize` also refreshes `layout-cut-generator.dxf` and its metadata so the combined stock layout stays in sync with the updated layer DXFs.

When you run `add_french_cleats.py --dir output_final_<run_name>`, the script now also refreshes `layout-cut-generator.dxf` (using an inferred stock size from existing metadata, or pass `--stock-size-in` to force a specific sheet size). This keeps the combined layout in sync after adding cleat/backing layers.

To test that behavior end to end:

```bash
# 1) Rebuild the postprocessed masks with widening enabled
python postprocessor.py --stress-analysis --thin-min-width 4 --thin-widen-to 8

# 2) Create the final package from the widened postprocessed output
python postprocessor.py --finalize
```

After step 2, compare the layer PNGs or the layer areas in `output_final_<run_name>/handoff.md` against `output_postprocessed_<run_name>/`.
The final package should match the widened geometry, not the original generator size.

**Trim Final Package Layers**

You can remove unwanted layers from a `output_final_<run_name>` package and automatically renumber the remaining layers (PNG + DXF) using the small utility `trim_final_layers.py`.

Examples:

```bash
# Show the planned deletions and renames without changing files
python trim_final_layers.py --dir output_final_<run_name> --delete 5 --dry-run

# Delete a single layer (index 5) and renumber the rest
python trim_final_layers.py --dir output_final_<run_name> --delete 5

# Delete a range of layers (3,4,5)
python trim_final_layers.py --dir output_final_<run_name> --delete 3-5

# Delete multiple non-contiguous layers
python trim_final_layers.py --dir output_final_<run_name> --delete 2 --delete 8
```

What it does:

- Removes any files named `Layer_XX_*.png` and `Layer_XX_*.dxf` for the indices you specify.
- Renumbers surviving `Layer_XX_*` files so indices are contiguous starting at `00`.
- Updates `handoff.md` to reflect the new layer indices and layer count.

Safety tip: always run the `--dry-run` first to confirm the planned changes before applying them.

**French Cleat Backing**

You can add a French cleat / keyhole backing to the final stack after the package has already been decided. The cleat tool inspects the back of the final package, keeps the existing art layers when possible, and appends up to two blank back layers only when the keyhole or clearance cavity would collide with contours.

Example:

```bash
python add_french_cleats.py --dir output_final_<run_name> --dry-run
python add_french_cleats.py --dir output_final_<run_name>
```

What it does:

- Places a keyhole-style wall mount near the top-center of the back stack.
- Uses the existing back layers when the cleat geometry has enough clearance.
- Appends up to two blank layers only when the current back stack would collide with the keyhole or cavity.
- Regenerates the touched DXFs so the vector output matches the updated PNGs.

Safety tip: start with `--dry-run` so you can see whether the tool will use existing layers or append new back layers before it writes anything.

## Etsy Release Handoff

Package a completed LazyLayerzzzLibrary run into a buyer-ready Etsy download, seller-only listing media, and a run-specific AI handoff. The release tool stages its work privately and leaves the existing `outputs/final` source files unchanged.

```bash
python -m release_tools.etsy_release \
	"LazyLayerzzzLibrary/projects/<project-name>/runs/<run-id>" \
	--french-cleats include
```

Use `--french-cleats exclude` for an art-only release. The default `ask` mode prompts for the choice in an interactive terminal. Add `--force` only when replacing an existing `outputs/final/EtsyRelease` build.

The completed release is written to:

```text
LazyLayerzzzLibrary/projects/<project-name>/runs/<run-id>/outputs/final/EtsyRelease/
```

The buyer ZIP is in `Buyer_Download/`. Seller-only composite, showcase, and exploded-video media are in `Seller_Listing_Media/`. The buyer package contains individual DXF/SVG layers plus `Combined_Layout/All_Layers_Layout.dxf` and `.svg`, where every delivered layer is arranged in a neat grid with 10 mm gaps.

### Create The Listing Guide

Open `EtsyRelease/ETSY_HANDOFF.md` and provide its complete contents to the AI helping with your listing. Before asking it to write `ETSY_LISTING_GUIDE.md`, provide the required seller answers, including:

- Photos you took of the completed physical artwork, and confirmation that it was cut from this release's delivered files.
- The machine, material, thickness, finished size, and any production changes used for the physical piece.
- Original design or presentation reference images, which images may be used publicly, and the intended showcase mood, environment, and lighting.
- Confirmed compatibility, pricing, AI disclosure, and intellectual-property information.

The handoff directs the AI to use your physical photos as fabrication evidence, create reference-driven showcase-image briefs with bright, intentional lighting, and avoid unsupported production or compatibility claims.

## Exploded video tool

Rear exploded view

```bash
python -m preview_tools.exploded_video \
  "LazyLayerzzzLibrary/projects/<project-name>/runs/<your-run>" \
  --preset etsy \
  --view rear
```

Front exploded view

```bash
python -m py_compile preview_tools/exploded_video.py
git diff --check
```

```bash
python -m preview_tools.exploded_video \
  "LazyLayerzzzLibrary/projects/jubilee-prod-draft/runs/run-20260726-008" \
  --preset etsy \
  --view front
```

**DXF converter differences**

- `--export-dxf` (postprocessor internal): uses the postprocessor's in-memory masks and the `export_dxf()` routine. It converts binary masks to vector contours via `mask_to_contours()` and writes polylines directly into a DXF. This path builds the DXF geometry from the masks in memory and allows layouting multiple layers into a single DXF file.

- `png-to-dxf.py` (standalone tracer): operates on PNG files. It thresholds the image and runs OpenCV's `findContours()` to extract contours, optionally simplifies them with `approxPolyDP`, and writes one DXF per input PNG. When you use `--finalize`, the pipeline saves the final PNGs (including any widenings) and then runs the exact shell loop below which calls `png-to-dxf.py` on those PNGs to produce per-layer DXFs:

```bash
for f in output_final_*/Layer_*.png; do python png-to-dxf.py --png "$f" --dpi 300; done
```

Notes about differences in the resulting DXFs:

- Both converters trace geometry from raster masks, so the widened shapes (from `--stress-analysis`) are present in both outputs
- Widening is applied before the DXF conversion step.
- Contour extraction and simplification settings differ: the internal `export_dxf()` may use different contour retrieval and polygon writing methods (polyline vs lwpolyline, grouping per-layer), while `png-to-dxf.py` uses `findContours()` + `approxPolyDP` which can produce slightly different vertex placements and numbers of contours. These differences affect small details (vertex counts, ordering, tiny artifacts) but not the overall widened silhouette.
- If you need bit-for-bit identical DXFs from the two paths, use one path consistently and tune the `--dxf-simplify-epsilon` (postprocessor) or `--simplify` (png-to-dxf) parameters to match results.

### Tuning simplification (examples)

Try a few simplification tolerances on a representative layer to find the sweet spot for your design. The values are interpreted in pixels on the source raster (i.e. before DPI scaling), so compare both paths at the same `--dpi`/scale.

Example commands:

```bash
# Postprocessor (internal DXF path)
python postprocessor.py --export-dxf --dxf-simplify-epsilon 1.0

# Standalone tracer (png-to-dxf)
python png-to-dxf.py --png output_final_<run_name>/Layer_02_*.png --simplify 1.0 --dpi 300
```

Typical ranges and effects:

- `0.0` — no simplification (preserve all vertices).
- `0.5–2.0` — subtle cleanup; removes tiny jitter and very small artifacts while keeping corners.
- `3–10` — aggressive smoothing; reduces vertex count and removes small features (use with caution for fit-sensitive parts).

Recommended workflow:

1. Pick a representative layer with both small details and important corners.
2. Run the two commands above with the same numeric value (start at `1.0`).
3. Inspect the resulting DXFs visually and check vertex counts (or load into your CAM to verify fit).
4. Increase the value to remove noise, or decrease it to preserve detail. Repeat until satisfied.

Note: very large values can round away small tabs or join features needed for assembly — increase gradually and test.

Optional DXF settings:

```bash
python postprocessor.py --export-dxf \
	--dxf-dpi 300 \
	--dxf-units mm \
	--dxf-version R12 \
	--dxf-simplify-epsilon 0.0 \
	--dxf-layout grid \
	--dxf-spacing 5 \
	--dxf-columns 0
```

#### 4) Png-to-DXF

DXF export (multiple DXFs for each layer mask):

**Combined stock layout**

You can generate a single combined DXF that arranges all final layer DXFs into a stock-sized sheet using the pipeline flag `--stock-size-in` or the standalone generator.

Example (from workspace root):

```bash
# Run full pipeline and produce a combined layout for a 10×20 in stock sheet
python pipeline.py --image images/GPT4.0/The_Whisk_and_Wildflower_Wreath.png --stock-size-in 10x20

# Or run the layout generator against an existing final package
python layout_cut_generator.py --dir output_final_The_Whisk_and_Wildflower_Wreath --stock-size-in 12x20
```

The generator creates `layout-cut-generator.dxf` and `layout-cut-generator_metadata.json` inside the final package directory. When you run `postprocessor.py --finalize` with `--stock-size-in`, or when an existing final package already has layout metadata, the same combined layout files are refreshed automatically.

```bash
for f in output_postprocessed_*/Layer_*.png; do python png-to-dxf.py --png "$f" --dpi 300; done
```

**How to Set `--dpi`**

```math
\text{Physical Size (inches)} = \frac{\text{Pixel Dimension}}{\text{DPI}}
```

**Example 1:** If your PNG is 3000 pixels wide, and you set --dpi 300:

- 3000 ÷ 300 = 10 inches.
- Your DXF will import into LightBurn exactly 10 inches wide.

Notes:

- Default scaling is 300 DPI with mm units ($\text{mm} = \text{px} \times 25.4 / 300$). Use `--dxf-dpi` or `--dxf-units px` to change.
- Default DXF layout is a grid with 5 mm spacing and the frame outline included in each layer. Use `--dxf-layout stacked` or `--dxf-no-frame` to change.
- The outer frame now sits 20 mm beyond the artwork contour by default, and each layer includes four 2.5 mm setting holes centered 10 mm in each frame corner.
- Use `--dxf-frame-margin-mm`, `--dxf-setting-hole-diameter-mm`, and `--dxf-setting-hole-inset-mm` to tune that geometry in the internal DXF export path. The standalone `png-to-dxf.py` script uses the same defaults.
- You can pass the same `--dxf-*` options to `pipeline.py`; it forwards them into the final DXF generation step.

### Building notes

```bash
python -m py_compile <name-of-file>
```

### Citation

If you use this project or build on the method, please cite:

Liu, H., Li, Z., Wu, K., Cai, Y., Zhai, X., Zhang, K., Liu, L., Xie, Y. M., & Fu, X.-M. (2025). _Computational multi-layered wood carving art_. _Computers & Graphics, 131_, 104337. [https://doi.org/10.1016/j.cag.2025.104337](https://doi.org/10.1016/j.cag.2025.104337)

<details>
<summary>BibTeX</summary>

```bibtex
@article{LIU2025104337,
  title = {Computational multi-layered wood carving art},
  journal = {Computers & Graphics},
  volume = {131},
  pages = {104337},
  year = {2025},
  doi = {https://doi.org/10.1016/j.cag.2025.104337},
  author = {Haochen Liu and Zhi Li and Kang Wu and Youcheng Cai and Xiaoya Zhai and Ketian Zhang and Ligang Liu and Yi Min Xie and Xiao-Ming Fu}
}
```

</details>
