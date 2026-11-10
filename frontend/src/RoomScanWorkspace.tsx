import { useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { BufferGeometry, Float32BufferAttribute, Matrix4 } from "three";
import { Button, Text } from "@fluentui/react-components";
import { api, Building, Floor, Room, RoomScan, UsbCameraStatus, UsbPointCloud } from "./api";
import "./room-scan.css";

const colors = { wall: "#9bb7c8", door: "#f0a04b", window: "#42d9ff", opening: "#c690ff" };

function ScannedRoom({ scan }: { scan: RoomScan }) {
  return <group>
    {scan.surfaces.map(surface => {
      const [width, height, depth] = surface.dimensions;
      return <mesh key={surface.id} matrix={new Matrix4().fromArray(surface.transform)} matrixAutoUpdate={false}>
        <boxGeometry args={[width, height, Math.max(depth, 0.035)]} />
        <meshStandardMaterial color={colors[surface.kind]} roughness={0.75} transparent opacity={surface.kind === "window" ? 0.45 : 0.9} />
      </mesh>;
    })}
  </group>;
}

function DemoRoom() {
  return <group>
    <mesh position={[0, 0, 0]}><boxGeometry args={[4, 0.08, 3]} /><meshStandardMaterial color="#405562" /></mesh>
    <mesh position={[0, 1.4, -1.5]}><boxGeometry args={[4, 2.8, 0.08]} /><meshStandardMaterial color="#9bb7c8" transparent opacity={0.75} /></mesh>
    <mesh position={[-2, 1.4, 0]}><boxGeometry args={[0.08, 2.8, 3]} /><meshStandardMaterial color="#9bb7c8" transparent opacity={0.75} /></mesh>
    <mesh position={[2, 1.4, 0]}><boxGeometry args={[0.08, 2.8, 3]} /><meshStandardMaterial color="#9bb7c8" transparent opacity={0.75} /></mesh>
  </group>;
}

function RoomPoints({ cloud }: { cloud: UsbPointCloud }) {
  const geometry = useMemo(() => {
    const positions = new Float32Array(cloud.points.length * 3);
    const colors = new Float32Array(cloud.points.length * 3);
    cloud.points.forEach((point, index) => {
      positions.set(point, index * 3);
      const depth = Math.max(0, Math.min(1, Math.hypot(point[0], point[1], point[2]) / 8));
      colors.set([0.1 + depth * 0.9, 0.85 - depth * 0.55, 1 - depth * 0.9], index * 3);
    });
    const result = new BufferGeometry();
    result.setAttribute("position", new Float32BufferAttribute(positions, 3));
    result.setAttribute("color", new Float32BufferAttribute(colors, 3));
    result.computeBoundingSphere();
    return result;
  }, [cloud]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  return <points geometry={geometry}><pointsMaterial size={0.025} vertexColors sizeAttenuation /></points>;
}

export function RoomScanWorkspace() {
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [buildingId, setBuildingId] = useState("");
  const [floorId, setFloorId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [scan, setScan] = useState<RoomScan>();
  const [pointCloud, setPointCloud] = useState<UsbPointCloud>();
  const [scanToken, setScanToken] = useState(() => sessionStorage.getItem("roomScanAccessToken") ?? "");
  const [cameraStatus, setCameraStatus] = useState<UsbCameraStatus>();
  const [autoAlign, setAutoAlign] = useState(true);
  const [cameraPose, setCameraPose] = useState({ roomX: 0, roomY: 1.2, roomZ: 0, yawDegrees: 0, pitchDegrees: 0, rollDegrees: 0 });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.buildings().then(result => {
      setBuildings(result);
      setBuildingId(result[0]?.id ?? "");
    }).catch(cause => setError(String(cause)));
  }, []);

  useEffect(() => {
    if (!buildingId) return;
    setFloors([]);
    setRooms([]);
    setFloorId("");
    setRoomId("");
    api.floors(buildingId).then(result => {
      setFloors(result);
      setFloorId(result[0]?.id ?? "");
    }).catch(cause => setError(String(cause)));
  }, [buildingId]);

  useEffect(() => {
    if (!floorId) return;
    setRooms([]);
    setRoomId("");
    api.rooms(floorId).then(result => {
      setRooms(result);
      setRoomId(result[0]?.id ?? "");
    }).catch(cause => setError(String(cause)));
  }, [floorId]);

  useEffect(() => {
    if (!roomId) return;
    setScan(undefined);
    setPointCloud(undefined);
    setError("");
    if (!scanToken) return;
    api.latestRoomScan(roomId).then(setScan).catch(cause => {
      if (!String(cause).includes("404")) setError(String(cause));
    });
    api.latestUsbRoom(roomId, scanToken).then(cloud => {
      setPointCloud(cloud);
      if (cloud.lastPose) setCameraPose(cloud.lastPose);
    }).catch(cause => {
      if (!String(cause).includes("404")) setError(String(cause));
    });
  }, [roomId, scanToken]);

  async function refreshScan() {
    if (!roomId) return;
    if (!scanToken) {
      setError("Enter the room scan access token printed by start-demo.ps1.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setScan(await api.latestRoomScan(roomId));
    } catch (cause) {
      if (String(cause).includes("404")) setScan(undefined);
      else setError(String(cause));
    } finally {
      setLoading(false);
    }
  }

  async function checkUsbCamera() {
    if (!scanToken) {
      setError("Enter the room scan access token printed by start-demo.ps1.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setCameraStatus(await api.usbCameraStatus(scanToken));
    } catch (cause) {
      setError(String(cause));
    } finally {
      setLoading(false);
    }
  }

  async function captureUsbCamera() {
    if (!roomId || !scanToken) {
      setError("Select a room and enter the room scan access token.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const capture = await api.captureUsbRoom(roomId, scanToken, cameraPose, autoAlign);
      setCameraPose(capture.pose);
      setPointCloud(await api.latestUsbRoom(roomId, scanToken));
    } catch (cause) {
      setError(String(cause));
    } finally {
      setLoading(false);
    }
  }

  const selectedRoom = rooms.find(room => room.id === roomId);
  return <section className="room-workspace">
    <aside className="room-controls">
      <Text size={500} weight="semibold">Room reconstruction</Text>
      <label>Building<select value={buildingId} onChange={event => setBuildingId(event.target.value)}><option value="">Select building</option>{buildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}</select></label>
      <label>Floor<select value={floorId} onChange={event => setFloorId(event.target.value)}><option value="">Select floor</option>{floors.map(floor => <option key={floor.id} value={floor.id}>{floor.name}</option>)}</select></label>
      <label>Room<select value={roomId} onChange={event => setRoomId(event.target.value)}><option value="">Select room</option>{rooms.map(room => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>
      <label>Room scan access token<input type="password" autoComplete="off" value={scanToken} onChange={event => { setScanToken(event.target.value); sessionStorage.setItem("roomScanAccessToken", event.target.value); }} /></label>
      <Button disabled={!roomId || loading} onClick={refreshScan}>{loading ? "Refreshing…" : "Refresh latest scan"}</Button>
      <hr />
      <Text weight="semibold">Orbbec USB RGB-D camera</Text>
      <Button disabled={loading} onClick={checkUsbCamera}>Check USB camera</Button>
      {cameraStatus && <p className={cameraStatus.deviceConnected ? "event" : "warn"}>{cameraStatus.sdk}: {cameraStatus.deviceConnected ? cameraStatus.devices.join(", ") : cameraStatus.detail}</p>}
      <label><input type="checkbox" checked={autoAlign} onChange={event => setAutoAlign(event.target.checked)} /> Auto-align overlapping views (ICP)</label>
      <p className="room-hint">Set an approximate pose for the first capture. Later captures refine the last pose automatically when views overlap; move the camera in small steps and keep the previous scene visible.</p>
      <label>Camera room X (m)<input type="number" step="0.1" value={cameraPose.roomX} onChange={event => setCameraPose({ ...cameraPose, roomX: Number(event.target.value) })} /></label>
      <label>Camera height Y (m)<input type="number" step="0.1" value={cameraPose.roomY} onChange={event => setCameraPose({ ...cameraPose, roomY: Number(event.target.value) })} /></label>
      <label>Camera room Z (m)<input type="number" step="0.1" value={cameraPose.roomZ} onChange={event => setCameraPose({ ...cameraPose, roomZ: Number(event.target.value) })} /></label>
      <label>Yaw (degrees)<input type="number" step="5" value={cameraPose.yawDegrees} onChange={event => setCameraPose({ ...cameraPose, yawDegrees: Number(event.target.value) })} /></label>
      <label>Pitch (degrees)<input type="number" step="5" value={cameraPose.pitchDegrees} onChange={event => setCameraPose({ ...cameraPose, pitchDegrees: Number(event.target.value) })} /></label>
      <label>Roll (degrees)<input type="number" step="5" value={cameraPose.rollDegrees} onChange={event => setCameraPose({ ...cameraPose, rollDegrees: Number(event.target.value) })} /></label>
      <Button disabled={!roomId || loading || cameraStatus?.deviceConnected !== true} appearance="primary" onClick={captureUsbCamera}>Capture depth and align view</Button>
      <p className="room-hint">ICP is local point-cloud registration, not full SLAM: large moves, weak overlap, or repetitive/flat surfaces can fail or drift. Failed alignments are rejected without saving points; turn off auto-align to place a view manually.</p>
      <p className="room-hint">LiDAR iPhone RoomPlan scans remain supported; USB depth points and RoomPlan surfaces can be shown together.</p>
      {error && <p className="error">{error}</p>}
    </aside>
    <div className="room-stage">
      <Canvas camera={{ position: [4.5, 3.5, 5], fov: 50 }}>
        <ambientLight intensity={1.4} />
        <directionalLight position={[4, 6, 3]} intensity={1.5} />
        <gridHelper args={[12, 12, "#315064", "#182b37"]} />
        {scan && <ScannedRoom scan={scan} />}
        {pointCloud && <RoomPoints cloud={pointCloud} />}
        {!scan && !pointCloud && <DemoRoom />}
        <OrbitControls makeDefault target={[0, 1, 0]} />
      </Canvas>
      <div className="room-stage-label">{pointCloud ? `${selectedRoom?.name ?? roomId} · USB depth point cloud · ${pointCloud.points.length} points · ${pointCloud.captureCount} captures` : scan ? `${selectedRoom?.name ?? scan.roomName} · RoomPlan scan · meters` : "Demo preview — not measured"}</div>
    </div>
    <aside className="room-details">
      <Text size={500} weight="semibold">Scan details</Text>
      <p><b>Building:</b> {buildings.find(item => item.id === buildingId)?.name ?? "—"}</p>
      <p><b>Floor:</b> {floors.find(item => item.id === floorId)?.name ?? "—"}</p>
      <p><b>Room:</b> {selectedRoom?.name ?? "—"}</p>
      <p><b>Scan status:</b> {scan || pointCloud ? "Measured geometry" : "No scan uploaded"}</p>
      {scan && <>
        <p><b>Captured:</b> {new Date(scan.capturedAt).toLocaleString()}</p>
        <p><b>Surfaces:</b> {scan.surfaces.length}</p>
        <p><b>Scan ID:</b> {scan.scanId}</p>
        <p><b>Coordinate system:</b> {scan.coordinateSystem}</p>
      </>}
      {pointCloud && <>
        <p><b>USB captures:</b> {pointCloud.captureCount}</p>
        <p><b>Point count:</b> {pointCloud.points.length}</p>
        <p><b>Camera:</b> {pointCloud.camera}</p>
        <p><b>Last alignment:</b> {pointCloud.lastRegistration?.method ?? "legacy scan"}{pointCloud.lastRegistration?.rmseMeters !== undefined ? ` · RMSE ${pointCloud.lastRegistration.rmseMeters} m` : ""}</p>
        {pointCloud.lastRegistration?.fitness !== undefined && <p><b>Overlap fitness:</b> {Math.round(pointCloud.lastRegistration.fitness * 100)}%</p>}
        <p><b>Captured:</b> {new Date(pointCloud.capturedAt).toLocaleString()}</p>
        <p><b>Coordinate system:</b> {pointCloud.coordinateSystem}</p>
      </>}
    </aside>
  </section>;
}
