import unittest

import numpy as np

from usb_camera import camera_status, depth_image_to_points, transform_points


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


if __name__ == "__main__":
    unittest.main()
