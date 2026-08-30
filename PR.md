## Overview

Adds an optional first-layer-shaped fabrication frame while keeping rectangular frames as the default. Shaped runs now reuse one fitted outline and four validated alignment holes across PNGs, DXFs, previews, layouts, French-cleat layers, and saved desktop runs.

## Added

- `first_layer` frame mode across the Python CLI, Tauri command, React interface, TypeScript/Rust contracts, and persisted run settings.
- Shapely-backed offsets, quadrant hole placement, portable `frame_geometry.json`, backward-compatibility handling, and focused Python/Rust tests.

## Changed

- Trace extraction selects a clearly dominant enclosed silhouette, ignores small internal pockets, repairs raster corner contacts for valid vector geometry, and still rejects competing or boundary-touching shapes with padding guidance.
- Finalization converts only the current package, clips shaped PNGs/previews to the shared outline, and preserves shaped geometry through stock layouts and French-cleat generation.
- Shaped `WxH` sizing uses uniform scaling while rectangular sizing and corner-hole behavior remain unchanged.

## Deleted

- Removed the global wildcard DXF conversion behavior that could reconvert unrelated `output_final_*` packages.

## Acceptance Criteria

- [ ] Rectangular runs retain their existing sizing, margins, and four corner holes.
- [ ] First-layer runs create one non-rectangular outline and four identical, artwork-safe hole coordinates in every layer DXF.
- [ ] Small internal trace pockets do not block an otherwise dominant silhouette; competing or boundary-touching traces fail with actionable guidance.
- [ ] Shaped PNGs, previews, stock layouts, French-cleat layers, metadata, and saved desktop runs use the same resolved geometry.
- [ ] Older settings and run records without `frameShape` continue loading as rectangular runs.

## How to Test

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
(cd desktop && npm ci && npm run build)
(cd desktop/src-tauri && cargo test)
```

Expected result: All 23 Python tests and all Rust tests pass, the React production build succeeds, and rectangular compatibility remains green. A run using `--frame-shape first_layer` produces `frame_geometry.json`, matching shaped PNG/DXF outlines and holes on every layer, previews, and a stock layout without processing another run's output.
