from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import random
import re
import threading
from typing import Any

try:
    import cv2
    import numpy as np
except ImportError:  # OpenCV is optional so the worker still has a deterministic demo mode.
    cv2 = None
    np = None

from fastapi import FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from usb_camera import (
    CameraUnavailable,
    RegistrationUnavailable,
    align_point_cloud,
    camera_status,
    capture_depth_points,
    pose_from_transform,
)

app = FastAPI(title="Position Simulation Worker", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNTIME_DATA = Path(os.environ.get("POSITION_RUNTIME_DATA_DIR", Path(__file__).parent / "runtime-data"))
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
USB_SCAN_LOCK = threading.Lock()


class Simulation(BaseModel):
    seed: int = 42
    noise: float = Field(.02, ge=0, le=1)
    reflectorCount: int = Field(4, ge=1, le=32)
    receiverCount: int = Field(1, ge=1, le=8)
    calibration: str = "standard-v1"


class UsbCameraCapture(BaseModel):
    roomX: float = Field(ge=-100, le=100, allow_inf_nan=False)
    roomY: float = Field(ge=-100, le=100, allow_inf_nan=False)
    roomZ: float = Field(ge=-100, le=100, allow_inf_nan=False)
    yawDegrees: float = Field(default=0, ge=-360, le=360, allow_inf_nan=False)
    pitchDegrees: float = Field(default=0, ge=-90, le=90, allow_inf_nan=False)
    rollDegrees: float = Field(default=0, ge=-90, le=90, allow_inf_nan=False)
    autoAlign: bool = True


def validate_room_scan_token(token: str | None) -> None:
    expected = os.environ.get("ROOM_SCAN_ACCESS_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Room scan access is not configured.")
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="A valid room scan access token is required.")


def usb_scan_paths(room_id: str) -> tuple[Path, Path]:
    directory = RUNTIME_DATA / "usb-camera" / safe_id(room_id, "roomId")
    return directory, directory / "latest.json"


def parse_calibration(preset: str, matrix_json: str | None, distortion_json: str | None) -> tuple[Any, Any, str]:
    if matrix_json or distortion_json:
        try:
            matrix = json.loads(matrix_json or "")
            distortion = json.loads(distortion_json or "[]")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Calibration JSON is invalid: {exc.msg}.")
        if not isinstance(matrix, list) or len(matrix) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in matrix):
            raise HTTPException(status_code=400, detail="cameraMatrix must be a 3x3 JSON array.")
        if not isinstance(distortion, list) or len(distortion) not in (4, 5, 8):
            raise HTTPException(status_code=400, detail="distortionCoefficients must contain 4, 5, or 8 values.")
        try:
            matrix_values = [[float(v) for v in row] for row in matrix]
            distortion_values = [float(v) for v in distortion]
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Calibration values must be finite numbers.")
        if any(not (float("-inf") < value < float("inf")) for row in matrix_values for value in row) or any(not (float("-inf") < value < float("inf")) for value in distortion_values):
            raise HTTPException(status_code=400, detail="Calibration values must be finite numbers.")
        if cv2 is None or np is None:
            return None, None, "valid-but-unavailable"
        return np.array(matrix_values, dtype=np.float64), np.array(distortion_values, dtype=np.float64), "custom"
    if preset in ("", "none", "standard-v1"):
        return None, None, "none"
    if preset == "demo-640x480":
        if cv2 is None or np is None:
            return None, None, "valid-but-unavailable"
        return np.array([[560., 0., 320.], [0., 560., 240.], [0., 0., 1.]]), np.zeros(5), preset
    raise HTTPException(status_code=400, detail="Unknown calibration preset.")


def analyse_image(content: bytes, preset: str, matrix_json: str | None, distortion_json: str | None) -> dict[str, Any]:
    matrix, distortion, calibration_status = parse_calibration(preset, matrix_json, distortion_json)
    result_data: dict[str, Any] = {
        "detectionStatus": "opencv-unavailable" if cv2 is None else "no-marker",
        "positionStatus": "simulated",
        "detections": {"qr": [], "aruco": []},
        "calibration": {"status": calibration_status, "applied": False},
    }
    if cv2 is None or np is None:
        return result_data
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="Uploaded image is not a decodable image.")
    if matrix is not None:
        image = cv2.undistort(image, matrix, distortion)
        result_data["calibration"]["applied"] = True
    detector = cv2.QRCodeDetector()
    multi_result = detector.detectAndDecodeMulti(image)
    if len(multi_result) == 4:
        found, values, points, _ = multi_result
    else:
        values, points, _ = multi_result
        found = points is not None
    if found and points is not None:
        for value, marker_points in zip(values, points):
            corners = marker_points.reshape(-1, 2).tolist()
            center = [
                round(float(sum(point[0] for point in corners) / len(corners)), 2),
                round(float(sum(point[1] for point in corners) / len(corners)), 2),
            ]
            result_data["detections"]["qr"].append({"data": value, "corners": corners, "centerPx": center})
    if hasattr(cv2, "aruco"):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        parameters = cv2.aruco.DetectorParameters() if hasattr(cv2.aruco, "DetectorParameters") else cv2.aruco.DetectorParameters_create()
        corners, ids, _ = cv2.aruco.detectMarkers(image, dictionary, parameters=parameters)
        if ids is not None:
            for marker_corners, marker_id in zip(corners, ids.flatten()):
                points_list = marker_corners.reshape(-1, 2).tolist()
                result_data["detections"]["aruco"].append({"id": int(marker_id), "corners": points_list})
    if result_data["detections"]["qr"] or result_data["detections"]["aruco"]:
        result_data["detectionStatus"] = "marker-detected"
        result_data["positionStatus"] = "measured-image-coordinates"
        result_data["events"] = [
            {
                "sequence": index,
                "x": detection["centerPx"][0],
                "y": detection["centerPx"][1],
                "z": 0,
                "confidence": 1.0,
                "status": "measured-image-coordinate",
            }
            for index, detection in enumerate(result_data["detections"]["qr"])
        ]
        if not result_data["events"]:
            result_data["events"] = [
                {
                    "sequence": index,
                    "x": sum(point[0] for point in detection["corners"]) / len(detection["corners"]),
                    "y": sum(point[1] for point in detection["corners"]) / len(detection["corners"]),
                    "z": 0,
                    "confidence": 1.0,
                    "status": "measured-image-coordinate",
                }
                for index, detection in enumerate(result_data["detections"]["aruco"])
            ]
    return result_data


def safe_id(value: str, field: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}.")
    return value


def result(r: Simulation):
    rng = random.Random(r.seed)
    return {
        "algorithmVersion": "demo-reflector-v1",
        "seed": r.seed,
        "dataStatus": "demo data — simulated, not measured",
        "events": [
            {
                "sequence": i,
                "x": 1 + rng.uniform(-r.noise, r.noise),
                "y": .4,
                "z": .5,
                "confidence": round(1 - r.noise, 3),
                "status": "high",
            }
            for i in range(3)
        ],
    }


def capture_paths(warehouse_id: str):
    directory = RUNTIME_DATA / safe_id(warehouse_id, "warehouseId")
    return directory, directory / "latest.json", directory / "latest-image"


@app.get("/health/live")
def live():
    return {"status": "live"}


@app.get("/position/usb-camera/status")
def usb_camera_health(x_room_scan_token: str | None = Header(default=None)):
    validate_room_scan_token(x_room_scan_token)
    return camera_status()


@app.post("/position/usb-camera/rooms/{room_id}/capture")
def capture_usb_camera_room(
    room_id: str,
    request: UsbCameraCapture,
    x_room_scan_token: str | None = Header(default=None),
):
    validate_room_scan_token(x_room_scan_token)
    safe_id(room_id, "roomId")

    try:
        points = capture_depth_points(
            room_x=request.roomX,
            room_y=request.roomY,
            room_z=request.roomZ,
            yaw_degrees=request.yawDegrees,
            pitch_degrees=request.pitchDegrees,
            roll_degrees=request.rollDegrees,
        )
    except CameraUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    directory, latest_path = usb_scan_paths(room_id)
    with USB_SCAN_LOCK:
        if latest_path.is_file():
            scan = json.loads(latest_path.read_text(encoding="utf-8"))
        else:
            scan = {
                "roomId": room_id,
                "coordinateSystem": "room-local-y-up-meters",
                "units": "meters",
                "points": [],
                "captureCount": 0,
            }

        pose = request.model_dump(exclude={"autoAlign"})
        registration: dict[str, Any] = {"method": "initial-pose" if not scan["points"] else "manual-pose"}
        if request.autoAlign and scan["points"]:
            try:
                points, correction_rotation, correction_translation, metrics = align_point_cloud(points, scan["points"])
            except RegistrationUnavailable as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            pose = pose_from_transform(pose, correction_rotation, correction_translation)
            registration = {"method": "icp", **metrics}

        scan["points"].extend(points)
        if len(scan["points"]) > 40000:
            reduction_stride = (len(scan["points"]) + 39999) // 40000
            scan["points"] = scan["points"][::reduction_stride]
        scan["captureCount"] += 1
        scan["capturedAt"] = datetime.now(timezone.utc).isoformat()
        scan["camera"] = "Orbbec RGB-D"
        scan["lastPose"] = pose
        scan["lastRegistration"] = registration
        directory.mkdir(parents=True, exist_ok=True)
        temporary_path = directory / "latest.tmp"
        temporary_path.write_text(json.dumps(scan, separators=(",", ":")), encoding="utf-8")
        temporary_path.replace(latest_path)

    return {
        "roomId": room_id,
        "capturedAt": scan["capturedAt"],
        "captureCount": scan["captureCount"],
        "pointsAdded": len(points),
        "pointCount": len(scan["points"]),
        "coordinateSystem": scan["coordinateSystem"],
        "camera": scan["camera"],
        "pose": pose,
        "registration": registration,
    }


@app.get("/position/usb-camera/rooms/{room_id}/latest")
def latest_usb_camera_room(room_id: str, x_room_scan_token: str | None = Header(default=None)):
    validate_room_scan_token(x_room_scan_token)
    _, latest_path = usb_scan_paths(room_id)
    if not latest_path.is_file():
        raise HTTPException(status_code=404, detail="No USB camera scan found for this room.")
    return json.loads(latest_path.read_text(encoding="utf-8"))


@app.post("/simulate")
def simulate(r: Simulation):
    return result(r)


@app.post("/position/locate")
async def locate(
    photo: UploadFile = File(...),
    warehouseId: str = Form(...),
    itemId: str = Form(...),
    seed: int = Form(42),
    noise: float = Form(.02),
    reflectorCount: int = Form(4),
    receiverCount: int = Form(1),
    calibration: str = Form("standard-v1"),
    calibrationPreset: str = Form(""),
    cameraMatrix: str | None = Form(None),
    distortionCoefficients: str | None = Form(None),
):
    warehouse_id = safe_id(warehouseId, "warehouseId")
    item_id = safe_id(itemId, "itemId")
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported.")
    content = await photo.read()
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be between 1 byte and 10 MB.")

    simulation = Simulation(
        seed=seed, noise=noise, reflectorCount=reflectorCount,
        receiverCount=receiverCount, calibration=calibration,
    )
    analysis = analyse_image(content, calibrationPreset or calibration, cameraMatrix, distortionCoefficients)
    directory, metadata_path, image_path = capture_paths(warehouse_id)
    directory.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(content)
    metadata = {
        **result(simulation),
        **analysis,
        "warehouseId": warehouse_id,
        "itemId": item_id,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "image": {
            "filename": photo.filename or "capture",
            "contentType": photo.content_type,
            "bytes": len(content),
            "url": f"/position/warehouses/{warehouse_id}/latest/image",
        },
    }
    if analysis["positionStatus"] != "simulated":
        # These are pixel/image coordinates, deliberately not warehouse/world coordinates.
        detections = analysis["detections"]["qr"] + analysis["detections"]["aruco"]
        metadata["events"] = []
        for sequence, detection in enumerate(detections):
            center = detection["centerPx"] if "centerPx" in detection else [
                sum(point[0] for point in detection["corners"]) / len(detection["corners"]),
                sum(point[1] for point in detection["corners"]) / len(detection["corners"]),
            ]
            metadata["events"].append({
                "sequence": sequence,
                "x": round(center[0], 2),
                "y": round(center[1], 2),
                "z": 0,
                "confidence": 1.0,
                "status": "measured-image-coordinate",
            })
        metadata["dataStatus"] = "marker detected — measured image coordinates only; world position not calibrated"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


@app.get("/position/warehouses/{warehouse_id}/latest")
def latest(warehouse_id: str):
    _, metadata_path, _ = capture_paths(warehouse_id)
    if not metadata_path.is_file():
        raise HTTPException(status_code=404, detail="No capture found for this warehouse.")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


@app.get("/position/warehouses/{warehouse_id}/latest/image")
def latest_image(warehouse_id: str):
    _, metadata_path, image_path = capture_paths(warehouse_id)
    if not metadata_path.is_file() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="No capture found for this warehouse.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return Response(content=image_path.read_bytes(), media_type=metadata["image"]["contentType"])
