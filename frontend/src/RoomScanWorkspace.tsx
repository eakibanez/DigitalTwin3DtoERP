import { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Matrix4 } from "three";
import { Button, Text } from "@fluentui/react-components";
import { api, Building, Floor, Room, RoomScan } from "./api";
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

export function RoomScanWorkspace() {
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [buildingId, setBuildingId] = useState("");
  const [floorId, setFloorId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [scan, setScan] = useState<RoomScan>();
  const [scanToken, setScanToken] = useState(() => sessionStorage.getItem("roomScanAccessToken") ?? "");
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
    setError("");
    if (!scanToken) return;
    api.latestRoomScan(roomId).then(setScan).catch(cause => {
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

  const selectedRoom = rooms.find(room => room.id === roomId);
  return <section className="room-workspace">
    <aside className="room-controls">
      <Text size={500} weight="semibold">Room reconstruction</Text>
      <label>Building<select value={buildingId} onChange={event => setBuildingId(event.target.value)}><option value="">Select building</option>{buildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}</select></label>
      <label>Floor<select value={floorId} onChange={event => setFloorId(event.target.value)}><option value="">Select floor</option>{floors.map(floor => <option key={floor.id} value={floor.id}>{floor.name}</option>)}</select></label>
      <label>Room<select value={roomId} onChange={event => setRoomId(event.target.value)}><option value="">Select room</option>{rooms.map(room => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>
      <label>Room scan access token<input type="password" autoComplete="off" value={scanToken} onChange={event => { setScanToken(event.target.value); sessionStorage.setItem("roomScanAccessToken", event.target.value); }} /></label>
      <Button disabled={!roomId || loading} onClick={refreshScan}>{loading ? "Refreshing…" : "Refresh latest scan"}</Button>
      <p className="room-hint">Scan with the iOS RoomPlan app on a LiDAR iPhone. The native app uploads measured room surfaces in meters; this viewer does not infer dimensions from a single photo.</p>
      {error && <p className="error">{error}</p>}
    </aside>
    <div className="room-stage">
      <Canvas camera={{ position: [4.5, 3.5, 5], fov: 50 }}>
        <ambientLight intensity={1.4} />
        <directionalLight position={[4, 6, 3]} intensity={1.5} />
        <gridHelper args={[12, 12, "#315064", "#182b37"]} />
        {scan ? <ScannedRoom scan={scan} /> : <DemoRoom />}
        <OrbitControls makeDefault target={[0, 1, 0]} />
      </Canvas>
      <div className="room-stage-label">{scan ? `${selectedRoom?.name ?? scan.roomName} · RoomPlan scan · meters` : "Demo preview — not measured"}</div>
    </div>
    <aside className="room-details">
      <Text size={500} weight="semibold">Scan details</Text>
      <p><b>Building:</b> {buildings.find(item => item.id === buildingId)?.name ?? "—"}</p>
      <p><b>Floor:</b> {floors.find(item => item.id === floorId)?.name ?? "—"}</p>
      <p><b>Room:</b> {selectedRoom?.name ?? "—"}</p>
      <p><b>Scan status:</b> {scan ? "Measured geometry" : "No scan uploaded"}</p>
      {scan && <>
        <p><b>Captured:</b> {new Date(scan.capturedAt).toLocaleString()}</p>
        <p><b>Surfaces:</b> {scan.surfaces.length}</p>
        <p><b>Scan ID:</b> {scan.scanId}</p>
        <p><b>Coordinate system:</b> {scan.coordinateSystem}</p>
      </>}
    </aside>
  </section>;
}
