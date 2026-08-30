## Overview

Adds an optional first-layer-shaped fabrication frame while preserving the existing rectangular frame as the default. Shaped runs now share one fitted outline and four validated alignment-hole positions across PNGs, DXFs, previews, layouts, and French-cleat layers.

## Added

- `first_layer` frame mode in the Python CLI, Tauri command, React interface, and saved run parameters.
- Shapely-backed outline offsets, quadrant hole placement, `frame_geometry.json`, and focused Python/Rust test coverage.

## Changed

- Finalization converts only the current package and clips shaped PNGs/previews to the shared silhouette.
- Shaped `WxH` sizes preserve aspect ratio, and fabrication settings retain resolved geometry through later pipeline stages.

## Deleted

- Removed the global wildcard DXF conversion behavior that could reconvert unrelated `output_final_*` packages.

## Acceptance Criteria

- [ ] Rectangular runs retain their existing sizing, margins, and four corner holes.
- [ ] First-layer runs create one non-rectangular outline and four identical, artwork-safe hole coordinates in every layer DXF.
- [ ] Invalid or boundary-touching first traces stop with actionable guidance.
- [ ] Shaped previews, stock layouts, French-cleat layers, and saved desktop runs use the resolved shared geometry.

## How to Test

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
(cd desktop && npm ci && npm run build)
(cd desktop/src-tauri && cargo test)
```

Expected result: All Python and Rust tests pass, the React production build succeeds, and rectangular compatibility tests remain green. A run using `--frame-shape first_layer` produces `frame_geometry.json` plus per-layer PNG/DXF files with a shared shaped outline and four shared holes.
