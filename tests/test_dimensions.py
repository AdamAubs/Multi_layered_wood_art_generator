import json
import tempfile
import unittest
from pathlib import Path

import ezdxf
from fabrication_tools.dimensions import write_dimensions_report


class DimensionsReportTests(unittest.TestCase):
    def make_layer(self, root, name, points, units=4):
        doc = ezdxf.new()
        doc.units = units
        doc.modelspace().add_lwpolyline(points, close=True)
        doc.saveas(Path(root) / name)

    def test_measures_exported_bounds_instead_of_requested_size(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_layer(root, 'Layer_01.dxf', [(-5, -5), (249, -5), (249, 401.4), (-5, 401.4)])
            report = write_dimensions_report(root, '12x16', 'first_layer')
            self.assertAlmostEqual(report['width_mm'], 254)
            self.assertAlmostEqual(report['height_mm'], 406.4)
            self.assertEqual(report['requested_size_in'], '12x16')
            self.assertEqual(json.loads((Path(root) / 'dimensions.json').read_text()), report)

    def test_tracks_each_layer_and_excludes_stock_layout(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_layer(root, 'Layer_01.dxf', [(0, 0), (100, 0), (100, 200), (0, 200)])
            self.make_layer(root, 'Layer_02.dxf', [(0, 0), (110, 0), (110, 190), (0, 190)])
            self.make_layer(root, 'stock_layout.dxf', [(0, 0), (500, 0), (500, 900), (0, 900)])
            report = write_dimensions_report(root)
            self.assertEqual((report['width_mm'], report['height_mm']), (110, 200))
            self.assertEqual(len(report['layers']), 2)

    def test_rejects_unmeasurable_or_wrong_unit_exports(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                write_dimensions_report(root)
            self.make_layer(root, 'Layer_01.dxf', [(0, 0), (10, 0), (10, 20)], units=1)
            with self.assertRaises(ValueError):
                write_dimensions_report(root)
