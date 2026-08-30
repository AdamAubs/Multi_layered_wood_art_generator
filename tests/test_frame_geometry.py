import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from fabrication_tools.frame_geometry import (
    build_first_layer_frame_geometry,
    extract_first_layer_silhouette,
    rasterize_outer_frame,
    save_frame_geometry,
    transform_and_clip_mask,
)
from fabrication_tools.png_to_dxf import extract_cut_contours, write_dxf
from fabrication_tools.settings import load_dxf_settings, write_fabrication_settings


def ellipse_first_layer(width=200, height=240):
    cumulative = np.full((height, width), 255, dtype=np.uint8)
    cv2.ellipse(
        cumulative,
        (width // 2, height // 2),
        (width // 4, height // 3),
        0,
        0,
        360,
        0,
        thickness=-1,
    )
    return cumulative


class FirstLayerFrameGeometryTests(unittest.TestCase):
    def test_extracts_one_filled_enclosed_outer_trace(self):
        cumulative = ellipse_first_layer()
        cv2.circle(cumulative, (100, 120), 10, 255, thickness=-1)

        silhouette = extract_first_layer_silhouette(cumulative)

        self.assertEqual(silhouette[120, 100], 255)
        self.assertEqual(silhouette[0, 0], 0)

    def test_rejects_multiple_meaningful_traces(self):
        cumulative = np.full((200, 200), 255, dtype=np.uint8)
        cv2.circle(cumulative, (60, 100), 30, 0, thickness=-1)
        cv2.circle(cumulative, (140, 100), 30, 0, thickness=-1)

        with self.assertRaisesRegex(ValueError, "Found 2 meaningful enclosed traces"):
            extract_first_layer_silhouette(cumulative)

    def test_rejects_trace_touching_image_boundary(self):
        cumulative = np.full((200, 200), 255, dtype=np.uint8)
        cv2.rectangle(cumulative, (0, 40), (100, 160), 0, thickness=-1)

        with self.assertRaisesRegex(ValueError, "touches the image boundary"):
            extract_first_layer_silhouette(cumulative)

    def test_rejects_trace_touching_generator_safety_frame(self):
        frame = np.zeros((200, 200), dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (199, 199), 255, thickness=5)
        left_frame_edge = int(np.max(np.where(frame[100, :100] > 0)[0]))
        cumulative = np.full((200, 200), 255, dtype=np.uint8)
        cv2.rectangle(
            cumulative,
            (left_frame_edge + 1, 50),
            (100, 150),
            0,
            thickness=-1,
        )

        with self.assertRaisesRegex(ValueError, "touches the image boundary"):
            extract_first_layer_silhouette(cumulative, frame_mask=frame)

    def test_builds_eight_mm_offset_and_four_quadrant_holes(self):
        silhouette = extract_first_layer_silhouette(ellipse_first_layer())

        geometry = build_first_layer_frame_geometry(
            silhouette,
            source_color_id=7,
            frame_margin_mm=5.0,
            setting_hole_inset_mm=5.0,
            setting_hole_diameter_mm=2.5,
            requested_size_in="5x7",
        )

        self.assertEqual(geometry["effective_offset_mm"], 8.0)
        self.assertLessEqual(geometry["actual_width_mm"], 5.0 * 25.4 + 1e-6)
        self.assertLessEqual(geometry["actual_height_mm"], 7.0 * 25.4 + 1e-6)
        self.assertEqual(len(geometry["hole_centers_mm"]), 4)
        center_x = geometry["actual_width_mm"] / 2.0
        center_y = geometry["actual_height_mm"] / 2.0
        quadrants = {
            (x > center_x, y > center_y) for x, y in geometry["hole_centers_mm"]
        }
        self.assertEqual(quadrants, {(False, False), (False, True), (True, False), (True, True)})

        from shapely.geometry import Point, Polygon

        inner = Polygon(geometry["inner_outline_mm"])
        outer = Polygon(geometry["outer_outline_mm"])
        for x, y in geometry["hole_centers_mm"]:
            circle = Point(x, y).buffer(1.25)
            self.assertGreaterEqual(circle.distance(inner), 4.95)
            self.assertTrue(outer.buffer(-0.5).covers(circle))

    def test_clips_final_mask_to_shaped_canvas(self):
        cumulative = ellipse_first_layer()
        geometry = build_first_layer_frame_geometry(
            extract_first_layer_silhouette(cumulative),
            source_color_id=0,
            frame_margin_mm=5.0,
            setting_hole_inset_mm=5.0,
            setting_hole_diameter_mm=2.5,
        )

        clipped = transform_and_clip_mask(cumulative, geometry)
        outer = rasterize_outer_frame(geometry)

        self.assertEqual(clipped.shape, outer.shape)
        self.assertEqual(int(clipped[0, 0]), 0)
        self.assertTrue(np.all(clipped[outer == 0] == 0))

    def test_writes_identical_shaped_frame_to_each_dxf(self):
        cumulative = ellipse_first_layer()
        geometry = build_first_layer_frame_geometry(
            extract_first_layer_silhouette(cumulative),
            source_color_id=0,
            frame_margin_mm=5.0,
            setting_hole_inset_mm=5.0,
            setting_hole_diameter_mm=2.5,
        )
        clipped = transform_and_clip_mask(cumulative, geometry)
        outer_mask = rasterize_outer_frame(geometry)
        contours = extract_cut_contours(clipped, clip_mask=outer_mask)

        import ezdxf

        frames = []
        with TemporaryDirectory() as temporary:
            for index in range(2):
                path = Path(temporary) / f"layer-{index}.dxf"
                write_dxf(
                    contours,
                    path,
                    img_h=clipped.shape[0],
                    img_w=clipped.shape[1],
                    dpi=geometry["dpi"],
                    frame_margin_mm=5.0,
                    setting_hole_diameter_mm=2.5,
                    setting_hole_inset_mm=5.0,
                    frame_geometry=geometry,
                )
                document = ezdxf.readfile(path)
                frame = next(
                    entity
                    for entity in document.modelspace().query("LWPOLYLINE")
                    if entity.dxf.color == 2
                )
                frames.append([(point[0], point[1]) for point in frame.get_points()])
                self.assertEqual(len(document.modelspace().query("CIRCLE")), 4)

        self.assertEqual(frames[0], frames[1])

    def test_package_settings_default_old_runs_to_rectangle(self):
        with TemporaryDirectory() as temporary:
            write_fabrication_settings(
                temporary,
                {"schema_version": 1, "dxf": {"frame_margin_mm": 5.0}},
            )
            settings = load_dxf_settings(temporary)
        self.assertEqual(settings.frame_shape, "rectangle")
        self.assertIsNone(settings.frame_geometry_file)

    def test_package_settings_load_shaped_frame_contract(self):
        with TemporaryDirectory() as temporary:
            write_fabrication_settings(
                temporary,
                {
                    "schema_version": 1,
                    "dxf": {
                        "frame_shape": "first_layer",
                        "frame_geometry_file": "frame_geometry.json",
                    },
                },
            )
            settings = load_dxf_settings(temporary)
        self.assertEqual(settings.frame_shape, "first_layer")
        self.assertEqual(settings.frame_geometry_file, "frame_geometry.json")

    def test_geometry_artifact_is_portable_json(self):
        geometry = build_first_layer_frame_geometry(
            extract_first_layer_silhouette(ellipse_first_layer()),
            source_color_id=2,
            frame_margin_mm=5.0,
            setting_hole_inset_mm=5.0,
            setting_hole_diameter_mm=2.5,
        )
        with TemporaryDirectory() as temporary:
            path = save_frame_geometry(temporary, geometry)
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["frame_shape"], "first_layer")
        self.assertEqual(loaded["source_color_id"], 2)


if __name__ == "__main__":
    unittest.main()
