"""layout_cut_generator.py

Create a combined DXF that lays out per-layer DXF parts into a stock-sized sheet.

This initial implementation uses axis-aligned bounding-box placement (no rotation)
and a simple shelf packing heuristic. It supports basic entity types produced by
our tracing pipeline (LWPOLYLINE, POLYLINE, LINE, CIRCLE, TEXT).

Usage: python layout_cut_generator.py --dir output_final_<run_name> --stock-size-in 12x20
"""

import argparse
import json
import os
import sys

try:
    import ezdxf
except ImportError:
    print("Error: ezdxf is required. Install with: pip install ezdxf")
    raise


def parse_stock_size_in(value):
    import re

    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)\s*", value)
    if not match:
        raise ValueError("--stock-size-in must use WxH format such as 12x20.")
    w = float(match.group(1))
    h = float(match.group(2))
    if w <= 0 or h <= 0:
        raise ValueError("stock size values must be > 0")
    return w, h


def bbox_from_entity(entity):
    # Return minx, miny, maxx, maxy for supported entity types (in DXF units)
    t = entity.dxftype()
    if t == "LWPOLYLINE":
        pts = list(entity.get_points())
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    if t == "POLYLINE":
        pts = [v.dxf.location for v in entity.vertices]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    if t == "LINE":
        x1, y1, _ = entity.dxf.start
        x2, y2, _ = entity.dxf.end
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if t == "CIRCLE":
        cx, cy = entity.dxf.center[0], entity.dxf.center[1]
        r = entity.dxf.radius
        return cx - r, cy - r, cx + r, cy + r
    if t in ("TEXT", "MTEXT"):
        # approximate as point
        ins = entity.dxf.insert if t == "TEXT" else entity.dxf.insert
        return ins[0], ins[1], ins[0], ins[1]
    # Unknown entity type: return None so caller can handle
    return None


def collect_dxf_bbox(path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    bboxes = []
    for e in msp:
        try:
            bb = bbox_from_entity(e)
        except Exception:
            bb = None
        if bb is not None:
            bboxes.append(bb)
    if not bboxes:
        return None
    minx = min(b[0] for b in bboxes)
    miny = min(b[1] for b in bboxes)
    maxx = max(b[2] for b in bboxes)
    maxy = max(b[3] for b in bboxes)
    return (minx, miny, maxx, maxy)


def translate_point(pt, dx, dy):
    return (pt[0] + dx, pt[1] + dy)


def copy_entities_with_offset(src_doc, dst_msp, offset_x, offset_y):
    dst_doc = dst_msp.doc
    added = 0
    for e in src_doc.modelspace():
        t = e.dxftype()
        try:
            layer_name = getattr(e.dxf, 'layer', '0')
            # ensure layer exists in destination
            try:
                dst_doc.layers.new(layer_name)
            except Exception:
                # layer may already exist; ignore
                pass

            if t == "LWPOLYLINE":
                pts = []
                for p in e.get_points("xyseb"):
                    pts.append((p[0] + offset_x, p[1] + offset_y, p[2], p[3], p[4]))
                dst_msp.add_lwpolyline(pts, format="xyseb", close=e.closed, dxfattribs={'layer': layer_name})
                added += 1
            elif t == "POLYLINE":
                pts = []
                for v in e.vertices:
                    loc = v.dxf.location
                    pts.append((loc[0] + offset_x, loc[1] + offset_y, getattr(v.dxf, 'start_width', 0.0), getattr(v.dxf, 'end_width', 0.0), getattr(v.dxf, 'bulge', 0.0)))
                dst_msp.add_lwpolyline(pts, format="xyseb", close=e.is_closed if hasattr(e, 'is_closed') else False, dxfattribs={'layer': layer_name})
                added += 1
            elif t == "LINE":
                x1, y1, _ = e.dxf.start
                x2, y2, _ = e.dxf.end
                dst_msp.add_line((x1 + offset_x, y1 + offset_y), (x2 + offset_x, y2 + offset_y), dxfattribs={'layer': layer_name})
                added += 1
            elif t == "CIRCLE":
                cx, cy, _ = e.dxf.center
                r = e.dxf.radius
                dst_msp.add_circle((cx + offset_x, cy + offset_y), r, dxfattribs={'layer': layer_name})
                added += 1
            elif t in ("TEXT", "MTEXT"):
                ins = e.dxf.insert
                txt = dst_msp.add_text(str(e.text) if t == 'TEXT' else e.text, dxfattribs={'layer': layer_name, 'height': getattr(e.dxf, 'height', None)})
                try:
                    txt.set_pos((ins[0] + offset_x, ins[1] + offset_y), align="LEFT")
                except Exception:
                    txt.dxf.insert = (ins[0] + offset_x, ins[1] + offset_y)
                added += 1
            else:
                # skip unsupported entities
                continue
        except Exception:
            # best-effort: skip problematic entities but continue
            continue
    return added


def shelf_place_until_full(parts, stock_w, stock_h, gap, margin):
    """Place parts sequentially into one stock sheet until it fills.

    Returns a list of (part, x, y) for placed parts and the index of next unplaced part.
    """
    placements = []
    x = margin
    y = margin
    row_h = 0
    idx = 0
    n = len(parts)
    while idx < n:
        p = parts[idx]
        pw = p['w']
        ph = p['h']
        # if single part bigger than sheet, fail early
        if pw > stock_w - 2 * margin + 1e-6 or ph > stock_h - 2 * margin + 1e-6:
            raise ValueError(f"Part '{os.path.basename(p['path'])}' is larger than the stock sheet ({pw:.1f}×{ph:.1f} mm).")

        if x + pw > stock_w - margin + 1e-6:
            # new row
            x = margin
            y += row_h + gap
            row_h = 0

        if y + ph > stock_h - margin + 1e-6:
            # no space left on this sheet
            break

        placements.append((p, x, y))
        x += pw + gap
        if ph > row_h:
            row_h = ph
        idx += 1

    return placements, idx


def pack_into_sheets(parts, stock_w, stock_h, gap, margin):
    """Greedily pack parts into multiple sheets. Returns list of sheets where each sheet is a list of (part,x,y)."""
    sheets = []
    remaining = parts[:]
    while remaining:
        placed, next_idx = shelf_place_until_full(remaining, stock_w, stock_h, gap, margin)
        if not placed:
            # If nothing could be placed (single part too large), raise
            raise ValueError("A part could not be placed on an empty sheet. Check part size vs stock.")
        sheets.append(placed)
        remaining = remaining[next_idx:]
    return sheets


def main():
    parser = argparse.ArgumentParser(description="Generate a combined layout DXF for final package layers.")
    parser.add_argument("--dir", required=True, help="Path to output_final_* directory")
    parser.add_argument("--stock-size-in", required=True, help="Stock size as WxH in inches, e.g. 12x20")
    parser.add_argument("--gap-mm", type=float, default=5.0, help="Gap between parts in mm")
    parser.add_argument("--output-name", default="layout-cut-generator.dxf", help="Output DXF filename placed in the final dir")
    args = parser.parse_args()

    final_dir = os.path.abspath(args.dir)
    if not os.path.isdir(final_dir):
        print(f"Error: directory not found: {final_dir}")
        return 1

    try:
        stock_w_in, stock_h_in = parse_stock_size_in(args.stock_size_in)
    except Exception as exc:
        print(f"Error parsing stock size: {exc}")
        return 1

    stock_w_mm = stock_w_in * 25.4
    stock_h_mm = stock_h_in * 25.4
    gap_mm = float(args.gap_mm)
    margin = gap_mm

    # Collect layer DXFs
    dxf_files = [os.path.join(final_dir, n) for n in os.listdir(final_dir) if n.lower().endswith('.dxf') and n.startswith('Layer_')]
    if not dxf_files:
        print(f"No per-layer .dxf files found in {final_dir}")
        return 1

    parts = []
    for path in sorted(dxf_files):
        bb = collect_dxf_bbox(path)
        if bb is None:
            print(f"Warning: could not determine bbox for {path}; skipping")
            continue
        minx, miny, maxx, maxy = bb
        w = maxx - minx
        h = maxy - miny
        parts.append({'path': path, 'minx': minx, 'miny': miny, 'w': w, 'h': h})

    if not parts:
        print("No valid parts to place.")
        return 1

    # Remove prior layout outputs so a refresh does not leave stale sheets behind.
    output_stem = os.path.splitext(args.output_name)[0]
    for name in os.listdir(final_dir):
        if name == f"{output_stem}_metadata.json" or (name.startswith(output_stem) and name.lower().endswith(".dxf")):
            try:
                os.remove(os.path.join(final_dir, name))
            except OSError:
                pass

    try:
        sheets = pack_into_sheets(parts, stock_w_mm, stock_h_mm, gap_mm, margin)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    metadata = {'stock_mm': [stock_w_mm, stock_h_mm], 'gap_mm': gap_mm, 'sheets': []}

    for si, sheet in enumerate(sheets):
        doc = ezdxf.new(dxfversion="R2010")
        doc.header['$INSUNITS'] = 4
        msp = doc.modelspace()
        sheet_meta = {'index': si, 'placements': []}
        for part, px, py in sheet:
            src = ezdxf.readfile(part['path'])
            offset_x = px - part['minx']
            offset_y = py - part['miny']
            added = copy_entities_with_offset(src, msp, offset_x, offset_y)
            # we don't fail on zero added here, but record for diagnostics
            if added is None:
                added = 0
            sheet_meta['placements'].append({'file': os.path.basename(part['path']), 'x_mm': px, 'y_mm': py, 'w_mm': part['w'], 'h_mm': part['h'], 'entities_added': added})
            sheet_meta['placements'].append({'file': os.path.basename(part['path']), 'x_mm': px, 'y_mm': py, 'w_mm': part['w'], 'h_mm': part['h']})

        if len(sheets) == 1:
            out_name = args.output_name
        else:
            base, ext = os.path.splitext(args.output_name)
            out_name = f"{base}_{si:02d}{ext}"

        out_path = os.path.join(final_dir, out_name)
        doc.saveas(out_path)
        # validate saved file contains entities
        try:
            saved_doc = ezdxf.readfile(out_path)
            saved_count = len(list(saved_doc.modelspace()))
        except Exception:
            saved_count = 0

        metadata['sheets'].append({'file': out_name, 'placements': sheet_meta['placements']})
        print(f"Saved sheet {si} -> {out_path} (modelspace entities: {saved_count})")
        if saved_count == 0:
            print(f"Warning: saved DXF '{out_name}' contains 0 modelspace entities — check logs and input DXFs.")

    meta_path = os.path.join(final_dir, args.output_name.replace('.dxf', '_metadata.json'))
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    print(f"Layout metadata saved to: {meta_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
