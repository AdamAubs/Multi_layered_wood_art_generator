import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from fabrication_tools.settings import (
    load_dxf_settings,
    merge_fabrication_settings,
    write_fabrication_settings,
)
from fabrication_tools.png_to_dxf import write_dxf
from pipeline import compute_dpi_for_outer_size, validate_dxf_geometry


class PipelineFabricationTests(unittest.TestCase):
    def test_computes_dpi_for_compatible_rectangular_outer_frame(self):
        dpi_x, dpi_y, outer_width_mm, outer_height_mm = compute_dpi_for_outer_size(
            1200,
            600,
            254.0 / 25.4,
            132.0 / 25.4,
            5.0,
        )

        self.assertGreater(dpi_x, 0.0)
        self.assertGreater(dpi_y, 0.0)
        self.assertAlmostEqual(outer_width_mm, 254.0)
        self.assertAlmostEqual(outer_height_mm, 132.0)
        self.assertAlmostEqual(dpi_x, dpi_y)

    def test_fills_mismatched_outer_frame_with_the_selected_margin(self):
        dpi_x, dpi_y, outer_width_mm, outer_height_mm = compute_dpi_for_outer_size(
            1576,
            704,
            9.0,
            3.5,
            2.0,
        )

        self.assertNotEqual(dpi_x, dpi_y)
        self.assertAlmostEqual(outer_width_mm, 228.6)
        self.assertAlmostEqual(outer_height_mm, 88.9)
        self.assertAlmostEqual(1576 * 25.4 / dpi_x + 4.0, outer_width_mm)
        self.assertAlmostEqual(704 * 25.4 / dpi_y + 4.0, outer_height_mm)

    def test_independent_dpis_keep_the_requested_outer_dxf_size(self):
        dpi_x, dpi_y, _, _ = compute_dpi_for_outer_size(
            1576,
            704,
            9.0,
            3.5,
            2.0,
        )
        with TemporaryDirectory() as temporary:
            dxf_path = Path(temporary) / "layer.dxf"
            write_dxf(
                [np.array([[[0, 0]], [[1576, 0]], [[1576, 704]], [[0, 704]]])],
                dxf_path,
                img_h=704,
                img_w=1576,
                dpi=300.0,
                dpi_x=dpi_x,
                dpi_y=dpi_y,
                frame_margin_mm=2.0,
            )

            import ezdxf

            document = ezdxf.readfile(dxf_path)
            frame = next(
                entity
                for entity in document.modelspace().query("LWPOLYLINE")
                if entity.dxf.color == 2
            )
            points = list(frame.get_points())

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        self.assertAlmostEqual(max(x_values) - min(x_values), 228.6)
        self.assertAlmostEqual(max(y_values) - min(y_values), 88.9)

    def test_validates_setting_holes_stay_inside_frame(self):
        validate_dxf_geometry(5.0, 2.5, 7.0, 254.0, 132.0)

        with self.assertRaisesRegex(ValueError, "keep each setting hole inside"):
            validate_dxf_geometry(5.0, 10.0, 4.0, 254.0, 132.0)

    def test_final_package_records_resolved_dxf_settings(self):
        with TemporaryDirectory() as temporary:
            write_fabrication_settings(
                temporary,
                {
                    "schema_version": 1,
                    "dxf": {
                        "dpi": 450.0,
                        "dpi_x": 400.0,
                        "dpi_y": 450.0,
                        "frame_margin_mm": 6.0,
                        "frame_margin_x_mm": 8.0,
                        "frame_margin_y_mm": 6.0,
                        "setting_hole_diameter_mm": 3.0,
                        "setting_hole_inset_mm": 8.5,
                    },
                },
            )

            settings = load_dxf_settings(temporary)

        self.assertEqual(settings.dpi, 450.0)
        self.assertEqual(settings.dpi_x, 400.0)
        self.assertEqual(settings.dpi_y, 450.0)
        self.assertEqual(settings.frame_margin_mm, 6.0)
        self.assertEqual(settings.frame_margin_x_mm, 8.0)
        self.assertEqual(settings.frame_margin_y_mm, 6.0)
        self.assertEqual(settings.setting_hole_diameter_mm, 3.0)
        self.assertEqual(settings.setting_hole_inset_mm, 8.5)

    def test_later_pipeline_updates_preserve_resolved_shaped_geometry(self):
        with TemporaryDirectory() as temporary:
            write_fabrication_settings(
                temporary,
                {
                    "schema_version": 1,
                    "dxf": {
                        "dpi": 188.0,
                        "frame_shape": "first_layer",
                        "frame_geometry_file": "frame_geometry.json",
                    },
                    "outer_frame": {"width_mm": 127.0, "height_mm": 171.08},
                },
            )
            merge_fabrication_settings(
                temporary,
                {"french_cleats": {"requested": True, "generated": True}},
            )
            settings = load_dxf_settings(temporary)
            import json

            raw = json.loads(
                (Path(temporary) / "fabrication_settings.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(settings.dpi, 188.0)
        self.assertEqual(settings.frame_shape, "first_layer")
        self.assertEqual(raw["outer_frame"]["width_mm"], 127.0)
        self.assertTrue(raw["french_cleats"]["generated"])


if __name__ == "__main__":
    unittest.main()
