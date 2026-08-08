import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import ezdxf
import numpy as np

from release_tools.run_facts import ReleaseValidationError, discover_release_facts
from release_tools.etsy_release import _write_combined_layout


ROOT = Path(__file__).resolve().parents[1]


def write_layer(directory: Path, index: int, label: str) -> None:
    stem = f"Layer_{index:02d}_{label}"
    image = np.zeros((20, 30, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    assert cv2.imwrite(str(directory / f"{stem}.png"), image)
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_lwpolyline([(0, 0), (30, 0), (30, 20), (0, 20)], close=True)
    document.saveas(directory / f"{stem}.dxf")


class ReleaseDiscoveryTests(unittest.TestCase):
    def test_manual_combined_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            final_dir = Path(temporary)
            write_layer(final_dir, 0, "top")
            write_layer(final_dir, 1, "bottom")
            (final_dir / "combined-design.dxf").write_text("not canonical", encoding="utf-8")
            (final_dir / "combined-design.svg").write_text("<svg/>", encoding="utf-8")
            facts = discover_release_facts(final_dir)
            self.assertEqual([layer.stem for layer in facts.layers], ["Layer_00_top", "Layer_01_bottom"])

    def test_missing_png_dxf_pair_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            final_dir = Path(temporary)
            write_layer(final_dir, 0, "top")
            (final_dir / "Layer_01_bottom.png").write_bytes(b"not a pair")
            with self.assertRaises(ReleaseValidationError):
                discover_release_facts(final_dir)


class LayoutMetadataTests(unittest.TestCase):
    def test_each_layer_has_one_layout_placement(self):
        with tempfile.TemporaryDirectory() as temporary:
            final_dir = Path(temporary)
            write_layer(final_dir, 0, "top")
            write_layer(final_dir, 1, "bottom")
            result = subprocess.run(
                [sys.executable, str(ROOT / "layout_cut_generator.py"), "--dir", str(final_dir), "--stock-size-in", "4x4"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            metadata = json.loads((final_dir / "layout-cut-generator_metadata.json").read_text(encoding="utf-8"))
            placements = [placement for sheet in metadata["sheets"] for placement in sheet["placements"]]
            self.assertEqual([placement["file"] for placement in placements], ["Layer_00_top.dxf", "Layer_01_bottom.dxf"])


class CombinedLayoutTests(unittest.TestCase):
    def test_combined_layout_contains_all_selected_layer_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            final_dir = Path(temporary) / "final"
            package_dir = Path(temporary) / "buyer"
            final_dir.mkdir()
            package_dir.mkdir()
            write_layer(final_dir, 0, "top")
            write_layer(final_dir, 1, "bottom")
            facts = discover_release_facts(final_dir)
            _write_combined_layout(facts, package_dir)
            layout_dir = package_dir / "Combined_Layout"
            combined = ezdxf.readfile(layout_dir / "All_Layers_Layout.dxf")
            self.assertEqual(combined.header["$INSUNITS"], 4)
            self.assertEqual(len(combined.modelspace()), 2)
            polylines = list(combined.modelspace().query("LWPOLYLINE"))
            first_bbox = [value for point in polylines[0].get_points() for value in point[:2]]
            second_bbox = [value for point in polylines[1].get_points() for value in point[:2]]
            self.assertGreaterEqual(min(second_bbox[::2]) - max(first_bbox[::2]), 10.0)
            self.assertTrue((layout_dir / "All_Layers_Layout.svg").is_file())


if __name__ == "__main__":
    unittest.main()