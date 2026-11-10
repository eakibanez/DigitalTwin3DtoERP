/// <reference types="vite/client" />

const API_BASE = import.meta.env.VITE_API_BASE ?? "";
const WORKER_BASE = import.meta.env.VITE_WORKER_BASE ?? "";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export type Warehouse = { id: string; name: string };
export type Item = { id: string; name: string; warehouseId: string };
export type Inventory = { itemId: string; quantity: number; status: string };
export type SimulationRequest = { seed: number; noise: number; reflectorCount: number; receiverCount: number; calibration: string; calibrationPreset?: string; cameraMatrix?: string; distortionCoefficients?: string };
export type SimulationResult = { algorithmVersion: string; seed: number; events: Array<{ sequence: number; x: number; y: number; z: number; confidence: number; status: string }>; dataStatus: string };
export type PhotoLocationResult = SimulationResult & {
  warehouseId: string; itemId: string;   capturedAt: string;
  captureCount: number;
  image: { filename: string; contentType: string; bytes: number; url: string };
  detectionStatus: "opencv-unavailable" | "no-marker" | "marker-detected";
  positionStatus: "simulated" | "measured-image-coordinates";
  detections: { qr: Array<{ data: string; corners: number[][]; centerPx: number[] }>; aruco: Array<{ id: number; corners: number[][] }> };
  calibration: { status: string; applied: boolean };
};
export type LatestCapture = PhotoLocationResult;
export type WorkOrder = { id: string; status: string };
export type Scene = {
  warehouseId: string;
  coordinateSystem: string;
  revision: string;
  entities: Array<{ id: string; type: string; x: number; y: number; z: number; confidence: number }>;
};
export type Building = { id: string; name: string };
export type Floor = { id: string; buildingId: string; name: string };
export type Room = { id: string; floorId: string; name: string };
export type RoomSurface = { id: string; kind: "wall" | "door" | "window" | "opening"; transform: number[]; dimensions: number[] };
export type RoomScan = {
  scanId: string;
  buildingId: string;
  floorId: string;
  roomId: string;
  roomName: string;
  capturedAt: string;
  coordinateSystem: "roomplan-local-y-up-meters";
  units: "meters";
  surfaces: RoomSurface[];
};
export type UsbCameraStatus = {
  sdk: string;
  sdkAvailable: boolean;
  sdkVersion?: string;
  deviceConnected: boolean;
  devices: string[];
  detail: string;
};
export type UsbPointCloud = {
  roomId: string;
  coordinateSystem: "room-local-y-up-meters";
  units: "meters";
  capturedAt: string;
  captureCount: number;
  camera: string;
  points: number[][];
  lastPose?: UsbCameraPose;
  lastRegistration?: UsbRegistration;
};
export type UsbCameraPose = { roomX: number; roomY: number; roomZ: number; yawDegrees: number; pitchDegrees: number; rollDegrees: number };
export type UsbRegistration = { method: "initial-pose" | "manual-pose" | "icp"; fitness?: number; rmseMeters?: number; correspondences?: number };

export const api = {
  warehouses: () => get<Warehouse[]>("/api/v1/warehouses"),
  items: (warehouseId: string) => get<Item[]>(`/api/v1/items?warehouseId=${encodeURIComponent(warehouseId)}`),
  inventory: (warehouseId: string, itemId: string) =>
    get<Inventory[]>(`/api/v1/inventory?warehouseId=${encodeURIComponent(warehouseId)}&itemId=${encodeURIComponent(itemId)}`),
  receiving: () => get<unknown[]>("/api/v1/receiving"),
  picking: () => get<unknown[]>("/api/v1/picking"),
  workOrders: () => get<WorkOrder[]>("/api/v1/work-orders"),
  scene: (warehouseId: string) => get<Scene>(`/api/v1/twin/scenes/${encodeURIComponent(warehouseId)}`),
  buildings: () => get<Building[]>("/api/v1/buildings"),
  floors: (buildingId: string) => get<Floor[]>(`/api/v1/buildings/${encodeURIComponent(buildingId)}/floors`),
  rooms: (floorId: string) => get<Room[]>(`/api/v1/floors/${encodeURIComponent(floorId)}/rooms`),
  latestRoomScan: async (roomId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/rooms/${encodeURIComponent(roomId)}/scans/latest`, {
      headers: { "X-Room-Scan-Token": sessionStorage.getItem("roomScanAccessToken") ?? "" },
    });
    if (!response.ok) throw new Error(`/api/v1/rooms/${roomId}/scans/latest returned ${response.status}`);
    return response.json() as Promise<RoomScan>;
  },
  usbCameraStatus: async (token: string) => {
    const response = await fetch(`${WORKER_BASE}/position/usb-camera/status`, {
      headers: { "X-Room-Scan-Token": token },
    });
    if (!response.ok) throw new Error(`USB camera status returned ${response.status}`);
    return response.json() as Promise<UsbCameraStatus>;
  },
  captureUsbRoom: async (
    roomId: string,
    token: string,
    pose: UsbCameraPose,
    autoAlign: boolean,
  ) => {
    const response = await fetch(`${WORKER_BASE}/position/usb-camera/rooms/${encodeURIComponent(roomId)}/capture`, {
      method: "POST",
      headers: { "content-type": "application/json", "X-Room-Scan-Token": token },
      body: JSON.stringify({ ...pose, autoAlign }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`USB camera capture returned ${response.status}: ${detail}`);
    }
    return response.json() as Promise<{ pointCount: number; pointsAdded: number; captureCount: number; capturedAt: string; pose: UsbCameraPose; registration: UsbRegistration }>;
  },
  latestUsbRoom: async (roomId: string, token: string) => {
    const response = await fetch(`${WORKER_BASE}/position/usb-camera/rooms/${encodeURIComponent(roomId)}/latest`, {
      headers: { "X-Room-Scan-Token": token },
    });
    if (!response.ok) throw new Error(`Latest USB camera scan returned ${response.status}`);
    return response.json() as Promise<UsbPointCloud>;
  },
  simulate: async (request: SimulationRequest) => {
    const response = await fetch(`${WORKER_BASE}/simulate`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
    if (!response.ok) throw new Error(`Position worker returned ${response.status}`);
    return response.json() as Promise<SimulationResult>;
  },
  locatePhoto: async (photo: File, warehouseId: string, itemId: string, request: SimulationRequest) => {
    const form = new FormData();
    form.append("photo", photo);
    form.append("warehouseId", warehouseId);
    form.append("itemId", itemId);
    form.append("seed", String(request.seed));
    form.append("noise", String(request.noise));
    form.append("reflectorCount", String(request.reflectorCount));
    form.append("receiverCount", String(request.receiverCount));
    form.append("calibration", request.calibration);
    if (request.calibrationPreset) form.append("calibrationPreset", request.calibrationPreset);
    if (request.cameraMatrix) form.append("cameraMatrix", request.cameraMatrix);
    if (request.distortionCoefficients) form.append("distortionCoefficients", request.distortionCoefficients);
    const response = await fetch(`${WORKER_BASE}/position/locate`, { method: "POST", body: form });
    if (!response.ok) throw new Error(`Position server returned ${response.status}`);
    return response.json() as Promise<PhotoLocationResult>;
  },
  latestCapture: (warehouseId: string) =>
    get<LatestCapture>(`/position/warehouses/${encodeURIComponent(warehouseId)}/latest`),
};
