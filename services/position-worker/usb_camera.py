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


class RegistrationUnavailable(RuntimeError):
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


def align_point_cloud(
    source_points: list[list[float]],
    target_points: list[list[float]],
    *,
    max_correspondence_distance: float = 0.3,
    max_iterations: int = 30,
) -> tuple[list[list[float]], np.ndarray, np.ndarray, dict[str, float | int]]:
    source = np.asarray(source_points, dtype=np.float64)
    target = np.asarray(target_points, dtype=np.float64)
    if source.ndim != 2 or target.ndim != 2 or source.shape[1:] != (3,) or target.shape[1:] != (3,):
        raise RegistrationUnavailable("Point clouds must contain 3D XYZ points.")
    if len(source) < 30 or len(target) < 30 or not np.isfinite(source).all() or not np.isfinite(target).all():
        raise RegistrationUnavailable("At least 30 finite points are required in each cloud for alignment.")

    source_indices = np.linspace(0, len(source) - 1, min(len(source), 1200), dtype=int)
    target_indices = np.linspace(0, len(target) - 1, min(len(target), 1800), dtype=int)
    source_sample = source[source_indices]
    target_sample = target[target_indices]
    rotation = np.eye(3, dtype=np.float64)
    translation = np.zeros(3, dtype=np.float64)

    for _ in range(max_iterations):
        transformed = source_sample @ rotation.T + translation
        nearest, distances = _nearest_points(transformed, target_sample)
        inliers = distances <= max_correspondence_distance
        if np.count_nonzero(inliers) < 30:
            raise RegistrationUnavailable("Not enough overlapping geometry; keep the camera close to the previous view.")

        source_inliers = transformed[inliers]
        target_inliers = nearest[inliers]
        residuals = np.linalg.norm(source_inliers - target_inliers, axis=1)
        median = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - median)))
        robust_limit = min(max_correspondence_distance, median + max(0.02, 2.5 * mad))
        robust_inliers = residuals <= robust_limit
        if np.count_nonzero(robust_inliers) < 30:
            raise RegistrationUnavailable("Not enough reliable correspondences to align this view.")

        moving = source_inliers[robust_inliers]
        fixed = target_inliers[robust_inliers]
        moving_center = moving.mean(axis=0)
        fixed_center = fixed.mean(axis=0)
        covariance = (moving - moving_center).T @ (fixed - fixed_center)
        u, singular_values, vt = np.linalg.svd(covariance)
        correction = vt.T @ u.T
        if np.linalg.det(correction) < 0:
            vt[-1, :] *= -1
            correction = vt.T @ u.T
        if singular_values[1] < 1e-8:
            raise RegistrationUnavailable("The overlapping scene is too geometrically ambiguous to align.")

        offset = fixed_center - correction @ moving_center
        rotation = correction @ rotation
        translation = correction @ translation + offset
        if np.linalg.norm(offset) < 1e-4 and np.linalg.norm(correction - np.eye(3)) < 1e-4:
            break

    aligned_sample = source_sample @ rotation.T + translation
    nearest, distances = _nearest_points(aligned_sample, target_sample)
    inliers = distances <= max_correspondence_distance
    correspondence_count = int(np.count_nonzero(inliers))
    fitness = correspondence_count / len(source_sample)
    rmse = float(np.sqrt(np.mean(np.square(distances[inliers])))) if correspondence_count else float("inf")
    if correspondence_count < 30 or fitness < 0.2 or rmse > 0.08:
        raise RegistrationUnavailable(
            "Automatic alignment confidence is too low. Move less, keep more of the previous view visible, or use manual poses."
        )

    aligned = source @ rotation.T + translation
    metrics: dict[str, float | int] = {
        "fitness": round(fitness, 4),
        "rmseMeters": round(rmse, 4),
        "correspondences": correspondence_count,
    }
    return np.round(aligned, decimals=4).tolist(), rotation, translation, metrics


def _nearest_points(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nearest_points = np.empty_like(source)
    nearest_distances = np.empty(len(source), dtype=np.float64)
    for start in range(0, len(source), 128):
        batch = source[start : start + 128]
        differences = batch[:, None, :] - target[None, :, :]
        squared_distances = np.einsum("ijk,ijk->ij", differences, differences)
        indices = np.argmin(squared_distances, axis=1)
        nearest_points[start : start + len(batch)] = target[indices]
        nearest_distances[start : start + len(batch)] = np.sqrt(squared_distances[np.arange(len(batch)), indices])
    return nearest_points, nearest_distances


def pose_from_transform(
    original_pose: dict[str, float],
    correction_rotation: np.ndarray,
    correction_translation: np.ndarray,
) -> dict[str, float]:
    yaw, pitch, roll = map(
        math.radians,
        (original_pose["yawDegrees"], original_pose["pitchDegrees"], original_pose["rollDegrees"]),
    )
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    rotation = np.array(
        [
            [cy * cr + sy * sp * sr, -cy * sr + sy * sp * cr, sy * cp],
            [cp * sr, cp * cr, -sp],
            [-sy * cr + cy * sp * sr, sy * sr + cy * sp * cr, cy * cp],
        ],
        dtype=np.float64,
    )
    translation = np.array([original_pose["roomX"], original_pose["roomY"], original_pose["roomZ"]])
    corrected_rotation = correction_rotation @ rotation
    corrected_translation = correction_rotation @ translation + correction_translation
    corrected_pitch = math.asin(max(-1.0, min(1.0, -corrected_rotation[1, 2])))
    cosine_pitch = math.cos(corrected_pitch)
    if abs(cosine_pitch) > 1e-6:
        corrected_yaw = math.atan2(corrected_rotation[0, 2], corrected_rotation[2, 2])
        corrected_roll = math.atan2(corrected_rotation[1, 0], corrected_rotation[1, 1])
    else:
        corrected_yaw = math.atan2(-corrected_rotation[2, 0], corrected_rotation[0, 0])
        corrected_roll = 0.0
    return {
        "roomX": round(float(corrected_translation[0]), 4),
        "roomY": round(float(corrected_translation[1]), 4),
        "roomZ": round(float(corrected_translation[2]), 4),
        "yawDegrees": round(math.degrees(corrected_yaw), 3),
        "pitchDegrees": round(math.degrees(corrected_pitch), 3),
        "rollDegrees": round(math.degrees(corrected_roll), 3),
    }
