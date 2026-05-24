## Multi Layered Wood Art Generator

This project turns an input image into a set of layered, laser-cuttable masks using a three-stage pipeline:
preprocessor -> generator -> postprocessor.

### Quick Start (Single Command)

Run the entire pipeline in one command:

```bash
python pipeline.py --image images/Stylized_crane_with_pine_branches.png
```

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

The run name is derived from the image filename stem. The pipeline now ends with `postprocessor.py --finalize`, so the default quick-start path produces both the postprocessed masks and the fabrication-ready final package.

### Run Each Stage Individually

#### 1) Preprocessor

Simplifies the image and creates clustering outputs.

```bash
python preprocessor.py --image images/Stylized_crane_with_pine_branches.png
```

Optional filter settings:

```bash
python preprocessor.py --image images/Stylized_crane_with_pine_branches.png \
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

Currently only the widening part of the `--stress-analysis` is implemented due to long of runtimes
that don't yield accurate results. This needs in depth review.

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

**DXF converter differences (important)**

- `--export-dxf` (postprocessor internal): uses the postprocessor's in-memory masks and the `export_dxf()` routine. It converts binary masks to vector contours via `mask_to_contours()` and writes polylines directly into a DXF. This path builds the DXF geometry from the masks in memory and allows layouting multiple layers into a single DXF file.
- `png-to-dxf.py` (standalone tracer): operates on PNG files. It thresholds the image and runs OpenCV's `findContours()` to extract contours, optionally simplifies them with `approxPolyDP`, and writes one DXF per input PNG. When you use `--finalize`, the pipeline saves the final PNGs (including any widenings) and then runs the exact shell loop below which calls `png-to-dxf.py` on those PNGs to produce per-layer DXFs:

```bash
for f in output_final_*/Layer_*.png; do python png-to-dxf.py --png "$f" --dpi 300; done
```

Notes about differences in the resulting DXFs:

- Both converters trace geometry from raster masks, so the widened shapes (from `--stress-analysis`) are present in both outputs — widening is applied before the DXF conversion step.
- However, contour extraction and simplification settings differ: the internal `export_dxf()` may use different contour retrieval and polygon writing methods (polyline vs lwpolyline, grouping per-layer), while `png-to-dxf.py` uses `findContours()` + `approxPolyDP` which can produce slightly different vertex placements and numbers of contours. These differences affect small details (vertex counts, ordering, tiny artifacts) but not the overall widened silhouette.
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

- DXF export requires ezdxf: `pip install ezdxf`
- Default scaling is 300 DPI with mm units ($\text{mm} = \text{px} \times 25.4 / 300$). Use `--dxf-dpi` or `--dxf-units px` to change.
- Default DXF layout is a grid with 5 mm spacing and the frame outline included in each layer. Use `--dxf-layout stacked` or `--dxf-no-frame` to change.
- Stress analysis is optional and off by default. It adds an iterative widening pass before the normal postprocessor outputs are written.

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
