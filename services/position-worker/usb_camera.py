from __future__ import annotations

import importlib.metadata
import math
import threading
from typing import Any

import numpy as np

try:
    import pyorbbecsdk as ob
except ImportError as exc:
    ob = None
    SDK_IMPORT_ERROR = str(exc)
else:
    SDK_IMPORT_ERROR = None


class CameraUnavailable(RuntimeError):
    pass


CAMERA_LOCK = threading.Lock()


def camera_status() -> dict[str, Any]:
    if ob is None:
        return {
            "sdk": "Orbbec SDK v2",
            "sdkAvailable": False,
            "deviceConnected": False,
            "devices": [],
            "detail": f"Install requirements-usb-camera.txt. {SDK_IMPORT_ERROR}",
        }

    try:
        devices = ob.Context().query_devices()
        names = [devices.get_device_name_by_index(index) for index in range(devices.get_count())]
    except Exception as exc:
        return {
            "sdk": "Orbbec SDK v2",
            "sdkAvailable": True,
            "sdkVersion": importlib.metadata.version("pyorbbecsdk2"),
            "deviceConnected": False,
            "devices": [],
            "detail": f"Could not enumerate USB cameras: {exc}",
        }

    return {
        "sdk": "Orbbec SDK v2",
        "sdkAvailable": True,
        "sdkVersion": importlib.metadata.version("pyorbbecsdk2"),
        "deviceConnected": bool(names),
        "devices": names,
        "detail": "Ready to capture depth frames." if names else "Connect an Orbbec RGB-D camera over USB 3.0.",
    }


def capture_depth_points(
    *,
    room_x: float,
    room_y: float,
    room_z: float,
    yaw_degrees: float,
    pitch_degrees: float,
    roll_degrees: float,
    max_points: int = 8000,
) -> list[list[float]]:
    if ob is None:
        raise CameraUnavailable(f"Orbbec SDK is not installed. {SDK_IMPORT_ERROR}")

    with CAMERA_LOCK:
        devices = ob.Context().query_devices()
        if devices.get_count() == 0:
            raise CameraUnavailable("No Orbbec RGB-D camera is connected.")

        pipeline = ob.Pipeline()
        started = False
        try:
            pipeline.start()
            started = True
            frames = pipeline.wait_for_frames(3000)
            if frames is None or frames.get_depth_frame() is None:
                raise CameraUnavailable("The camera did not provide a depth frame within 3 seconds.")

            frame = frames.get_depth_frame()
            width = frame.get_width()
            height = frame.get_height()
            depth_scale_mm = float(frame.get_depth_scale())

            depth = np.frombuffer(frame.get_data(), dtype=np.uint16)
            if depth.size != width * height:
                raise CameraUnavailable("The depth frame buffer size does not match its dimensions.")
            depth = depth.reshape((height, width))

            intrinsics = pipeline.get_camera_param().depth_intrinsic
            fx = float(intrinsics.fx)
            fy = float(intrinsics.fy)
            cx = float(intrinsics.cx)
            cy = float(intrinsics.cy)
            return depth_image_to_points(
                depth,
                depth_scale_mm=depth_scale_mm,
                fx=fx,
                fy=fy,
                cx=cx,
                cy=cy,
                room_x=room_x,
                room_y=room_y,
                room_z=room_z,
                yaw_degrees=yaw_degrees,
                pitch_degrees=pitch_degrees,
                roll_degrees=roll_degrees,
                max_points=max_points,
            )
        except CameraUnavailable:
            raise
        except Exception as exc:
            raise CameraUnavailable(f"Orbbec capture failed: {exc}") from exc
        finally:
            if started:
                pipeline.stop()


def depth_image_to_points(
    depth: np.ndarray,
    *,
    depth_scale_mm: float,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    room_x: float,
    room_y: float,
    room_z: float,
    yaw_degrees: float,
    pitch_degrees: float,
    roll_degrees: float,
    max_points: int,
) -> list[list[float]]:
    height, width = depth.shape
    if height < 2 or width < 2 or not math.isfinite(depth_scale_mm) or depth_scale_mm <= 0:
        raise CameraUnavailable("The camera returned invalid depth dimensions or scale.")
    if not all(math.isfinite(value) for value in (fx, fy, cx, cy)) or fx <= 0 or fy <= 0:
        raise CameraUnavailable("The camera returned invalid depth intrinsics.")

    stride = max(1, math.ceil(math.sqrt((width * height) / max_points)))
    rows, columns = np.mgrid[0:height:stride, 0:width:stride]
    depth_m = depth[::stride, ::stride].astype(np.float32) * (depth_scale_mm / 1000.0)
    valid = np.isfinite(depth_m) & (depth_m >= 0.15) & (depth_m <= 10.0)
    if not np.any(valid):
        raise CameraUnavailable("No valid depth samples were found in the camera frame.")

    x = (columns[valid].astype(np.float32) - cx) * depth_m[valid] / fx
    y = -(rows[valid].astype(np.float32) - cy) * depth_m[valid] / fy
    z = depth_m[valid]
    return transform_points(
        np.column_stack((x, y, z)),
        room_x=room_x,
        room_y=room_y,
        room_z=room_z,
        yaw_degrees=yaw_degrees,
        pitch_degrees=pitch_degrees,
        roll_degrees=roll_degrees,
    )


def transform_points(
    points: np.ndarray,
    *,
    room_x: float,
    room_y: float,
    room_z: float,
    yaw_degrees: float,
    pitch_degrees: float,
    roll_degrees: float,
) -> list[list[float]]:
    yaw, pitch, roll = map(math.radians, (yaw_degrees, pitch_degrees, roll_degrees))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)

    rotate_yaw = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    rotate_pitch = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], dtype=np.float32)
    rotate_roll = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]], dtype=np.float32)
    rotation = rotate_yaw @ rotate_pitch @ rotate_roll
    translation = np.array([room_x, room_y, room_z], dtype=np.float32)
    room_points = points @ rotation.T + translation
    return np.round(room_points, decimals=4).tolist()
