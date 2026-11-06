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
  warehouseId: string; itemId: string; capturedAt: string;
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

export const api = {
  warehouses: () => get<Warehouse[]>("/api/v1/warehouses"),
  items: (warehouseId: string) => get<Item[]>(`/api/v1/items?warehouseId=${encodeURIComponent(warehouseId)}`),
  inventory: (warehouseId: string, itemId: string) =>
    get<Inventory[]>(`/api/v1/inventory?warehouseId=${encodeURIComponent(warehouseId)}&itemId=${encodeURIComponent(itemId)}`),
  receiving: () => get<unknown[]>("/api/v1/receiving"),
  picking: () => get<unknown[]>("/api/v1/picking"),
  workOrders: () => get<WorkOrder[]>("/api/v1/work-orders"),
  scene: (warehouseId: string) => get<Scene>(`/api/v1/twin/scenes/${encodeURIComponent(warehouseId)}`),
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
