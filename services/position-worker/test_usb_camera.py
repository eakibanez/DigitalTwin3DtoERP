import unittest

import numpy as np

from usb_camera import align_point_cloud, camera_status, depth_image_to_points, pose_from_transform, transform_points


class UsbCameraTests(unittest.TestCase):
    def test_depth_pixels_project_to_camera_coordinates_in_meters(self):
        depth = np.array([[1000, 0], [2000, 3000]], dtype=np.uint16)

        points = depth_image_to_points(
            depth,
            depth_scale_mm=1,
            fx=2,
            fy=2,
            cx=0.5,
            cy=0.5,
            room_x=0,
            room_y=0,
            room_z=0,
            yaw_degrees=0,
            pitch_degrees=0,
            roll_degrees=0,
            max_points=8000,
        )

        self.assertEqual(points, [[-0.25, 0.25, 1.0], [-0.5, -0.5, 2.0], [0.75, -0.75, 3.0]])

    def test_identity_pose_preserves_camera_points(self):
        points = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)

        transformed = transform_points(
            points,
            room_x=0,
            room_y=0,
            room_z=0,
            yaw_degrees=0,
            pitch_degrees=0,
            roll_degrees=0,
        )

        self.assertEqual(transformed, [[1.0, 2.0, 3.0]])

    def test_yaw_and_translation_transform_into_room_coordinates(self):
        points = np.array([[0.0, 0.0, 1.0]], dtype=np.float32)

        transformed = transform_points(
            points,
            room_x=2,
            room_y=1,
            room_z=3,
            yaw_degrees=90,
            pitch_degrees=0,
            roll_degrees=0,
        )

        self.assertEqual(transformed, [[3.0, 1.0, 3.0]])

    def test_status_reports_sdk_and_device_separately(self):
        status = camera_status()

        self.assertIsInstance(status["sdkAvailable"], bool)
        self.assertIsInstance(status["deviceConnected"], bool)
        self.assertEqual(status["deviceConnected"], bool(status["devices"]))
        self.assertTrue(status["detail"])

    def test_icp_refines_a_close_initial_pose(self):
        rng = np.random.default_rng(42)
        target = rng.uniform(-1, 1, size=(3000, 3))
        initial_offset = np.array([0.025, -0.015, 0.02])
        source = target + initial_offset

        aligned, rotation, translation, metrics = align_point_cloud(source.tolist(), target.tolist())

        self.assertLess(float(np.mean(np.linalg.norm(np.asarray(aligned) - target, axis=1))), 0.02)
        self.assertGreater(metrics["fitness"], 0.2)
        self.assertLess(metrics["rmseMeters"], 0.08)
        self.assertTrue(np.allclose(rotation @ initial_offset + translation, np.zeros(3), atol=0.02))

    def test_icp_rejects_non_overlapping_views(self):
        rng = np.random.default_rng(7)
        source = rng.uniform(0, 1, size=(500, 3))
        target = rng.uniform(3, 4, size=(500, 3))

        with self.assertRaisesRegex(RuntimeError, "overlapping geometry"):
            align_point_cloud(source.tolist(), target.tolist())

    def test_refined_pose_matches_corrected_point_transform(self):
        original_pose = {
            "roomX": 1.0,
            "roomY": 1.2,
            "roomZ": -0.5,
            "yawDegrees": 25,
            "pitchDegrees": -8,
            "rollDegrees": 4,
        }
        angle = np.radians(7)
        correction = np.array(
            [[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]],
        )
        offset = np.array([0.1, -0.04, 0.03])
        refined_pose = pose_from_transform(original_pose, correction, offset)
        point = np.array([[0.3, 0.8, 1.1]])
        original_point = np.asarray(
            transform_points(
                point,
                room_x=original_pose["roomX"],
                room_y=original_pose["roomY"],
                room_z=original_pose["roomZ"],
                yaw_degrees=original_pose["yawDegrees"],
                pitch_degrees=original_pose["pitchDegrees"],
                roll_degrees=original_pose["rollDegrees"],
            )
        )
        expected = original_point @ correction.T + offset
        actual = np.asarray(
            transform_points(
                point,
                room_x=refined_pose["roomX"],
                room_y=refined_pose["roomY"],
                room_z=refined_pose["roomZ"],
                yaw_degrees=refined_pose["yawDegrees"],
                pitch_degrees=refined_pose["pitchDegrees"],
                roll_degrees=refined_pose["rollDegrees"],
            )
        )

        self.assertTrue(np.allclose(actual, expected, atol=1e-4))


if __name__ == "__main__":
    unittest.main()
