import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi import HTTPException

import app as worker_app
from usb_camera import transform_points


class UsbCameraApiTests(unittest.TestCase):
    def setUp(self):
        self.data_directory = tempfile.TemporaryDirectory()
        self.previous_runtime_data = worker_app.RUNTIME_DATA
        self.previous_token = os.environ.get("ROOM_SCAN_ACCESS_TOKEN")
        worker_app.RUNTIME_DATA = Path(self.data_directory.name)
        os.environ["ROOM_SCAN_ACCESS_TOKEN"] = "test-room-scan-token"
        self.scene_points = np.random.default_rng(42).uniform(-1, 1, size=(600, 3)).tolist()

    def tearDown(self):
        worker_app.RUNTIME_DATA = self.previous_runtime_data
        if self.previous_token is None:
            os.environ.pop("ROOM_SCAN_ACCESS_TOKEN", None)
        else:
            os.environ["ROOM_SCAN_ACCESS_TOKEN"] = self.previous_token
        self.data_directory.cleanup()

    def test_capture_uses_first_pose_then_persists_icp_refinement(self):
        def fake_capture(**pose):
            return transform_points(
                np.asarray(self.scene_points),
                room_x=pose["room_x"],
                room_y=pose["room_y"],
                room_z=pose["room_z"],
                yaw_degrees=pose["yaw_degrees"],
                pitch_degrees=pose["pitch_degrees"],
                roll_degrees=pose["roll_degrees"],
            )

        with patch.object(worker_app, "capture_depth_points", side_effect=fake_capture):
            first = worker_app.capture_usb_camera_room(
                "room-api-test",
                worker_app.UsbCameraCapture(roomX=0, roomY=1, roomZ=0),
                "test-room-scan-token",
            )
            second = worker_app.capture_usb_camera_room(
                "room-api-test",
                worker_app.UsbCameraCapture(roomX=0.02, roomY=1, roomZ=0),
                "test-room-scan-token",
            )

        self.assertEqual(first["registration"]["method"], "initial-pose")
        self.assertEqual(second["registration"]["method"], "icp")
        self.assertEqual(second["captureCount"], 2)
        self.assertAlmostEqual(second["pose"]["roomX"], 0, delta=0.02)
        latest = worker_app.latest_usb_camera_room("room-api-test", "test-room-scan-token")
        self.assertEqual(latest["captureCount"], 2)
        self.assertEqual(latest["lastRegistration"]["method"], "icp")

    def test_failed_icp_does_not_modify_saved_scan(self):
        def fake_capture(**pose):
            points = np.asarray(self.scene_points)
            if pose["room_x"] > 1:
                points = points + np.array([3, 0, 0])
            return transform_points(
                points,
                room_x=pose["room_x"],
                room_y=pose["room_y"],
                room_z=pose["room_z"],
                yaw_degrees=pose["yaw_degrees"],
                pitch_degrees=pose["pitch_degrees"],
                roll_degrees=pose["roll_degrees"],
            )

        with patch.object(worker_app, "capture_depth_points", side_effect=fake_capture):
            worker_app.capture_usb_camera_room(
                "room-api-test",
                worker_app.UsbCameraCapture(roomX=0, roomY=1, roomZ=0),
                "test-room-scan-token",
            )
            before = worker_app.latest_usb_camera_room("room-api-test", "test-room-scan-token")
            with self.assertRaises(HTTPException) as raised:
                worker_app.capture_usb_camera_room(
                    "room-api-test",
                    worker_app.UsbCameraCapture(roomX=2, roomY=1, roomZ=0),
                    "test-room-scan-token",
                )
            after = worker_app.latest_usb_camera_room("room-api-test", "test-room-scan-token")

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(after["captureCount"], before["captureCount"])
        self.assertEqual(after["points"], before["points"])


if __name__ == "__main__":
    unittest.main()
