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

The run name is derived from the image filename stem.

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
python postprocessor.py
```

Override input/output directories:

```bash
python postprocessor.py --in-dir output_generator_<run_name> --out-dir output_postprocessed_<run_name>
```
