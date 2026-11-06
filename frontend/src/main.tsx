import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Canvas } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { Button, FluentProvider, webDarkTheme, Text, Badge } from "@fluentui/react-components";
import { api, Item, Inventory, LatestCapture, PhotoLocationResult, Scene, SimulationResult, Warehouse } from "./api";
import "./style.css";

function Marker({ position, label }: { position: [number, number, number]; label: string }) {
  return <mesh position={position}><sphereGeometry args={[.18, 24, 24]} /><meshStandardMaterial color="#42d9ff" emissive="#116b88" /><Html><span className="marker">{label}</span></Html></mesh>;
}

function App() {
  const video = useRef<HTMLVideoElement>(null);
  const [step, setStep] = useState(1); const [camera, setCamera] = useState(false);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]); const [items, setItems] = useState<Item[]>([]);
  const [warehouse, setWarehouse] = useState<Warehouse>(); const [item, setItem] = useState<Item>();
  const [inventory, setInventory] = useState<Inventory>(); const [scene, setScene] = useState<Scene>();
  const [simulation, setSimulation] = useState<SimulationResult | PhotoLocationResult>(); const [noise, setNoise] = useState(.02);
  const [latestCapture, setLatestCapture] = useState<LatestCapture>();
  const [reflectors, setReflectors] = useState(4); const [receivers, setReceivers] = useState(1); const [calibration, setCalibration] = useState("standard-v1");
  const [calibrationPreset, setCalibrationPreset] = useState("none"); const [cameraMatrix, setCameraMatrix] = useState(""); const [distortion, setDistortion] = useState("");
  const [captureMode, setCaptureMode] = useState("QR or ArUco"); const [webXr, setWebXr] = useState<boolean | undefined>();
  const [photo, setPhoto] = useState<File>(); const [photoName, setPhotoName] = useState("");
  useEffect(() => { setWebXr("xr" in navigator && typeof (navigator as Navigator & { xr?: unknown }).xr !== "undefined"); }, []);

  useEffect(() => { api.warehouses().then(setWarehouses).catch(e => setError(String(e))); }, []);
  useEffect(() => {
    if (!warehouse) return;
    setItem(undefined); setInventory(undefined); setScene(undefined);
    setLatestCapture(undefined);
    api.items(warehouse.id).then(setItems).catch(e => setError(String(e)));
    api.latestCapture(warehouse.id).then(setLatestCapture).catch(e => {
      if (!String(e).includes("404")) setError(String(e));
    });
  }, [warehouse]);
  async function loadInventory() {
    if (!warehouse || !item) return; setLoading(true); setError("");
    try { const rows = await api.inventory(warehouse.id, item.id); setInventory(rows[0]); setScene(await api.scene(warehouse.id)); setStep(3); }
    catch (e) { setError(e instanceof Error ? e.message : "Inventory API unavailable."); } finally { setLoading(false); }
  }
  async function runSimulation() {
    setLoading(true); setError("");
    try { setSimulation(await api.simulate({ seed: 42, noise, reflectorCount: reflectors, receiverCount: receivers, calibration })); setStep(4); }
    catch (e) { setError("Position worker unavailable. Start uvicorn on port 8001."); } finally { setLoading(false); }
  }
  async function locatePhoto() {
    if (!photo) return;
    setLoading(true); setError("");
    try {
      if (!warehouse || !item) return;
      setSimulation(await api.locatePhoto(photo, warehouse.id, item.id, { seed: 42, noise, reflectorCount: reflectors, receiverCount: receivers, calibration, calibrationPreset, cameraMatrix, distortionCoefficients: distortion }));
      setLatestCapture(await api.latestCapture(warehouse.id));
      setStep(4);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Photo position server unavailable.");
    } finally { setLoading(false); }
  }
  async function enableCamera() {
    try { const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }); if (video.current) { video.current.srcObject = stream; await video.current.play(); } setCamera(true); }
    catch { setError("Camera requires HTTPS/localhost and permission."); }
  }
  function reset() { setStep(1); setInventory(undefined); setSimulation(undefined); setScene(undefined); setError(""); }
  const event = (latestCapture ?? simulation)?.events[(latestCapture ?? simulation)!.events.length - 1]; const entity = scene?.entities.find(x => x.id === (latestCapture?.itemId ?? item?.id)) ?? scene?.entities[0];
  return <FluentProvider theme={webDarkTheme}><main><header><div><Text size={700} weight="bold">Guided Inventory Location Demo</Text><Text block>Digital Twin 3D → EIS-ERP · iPhone position overlay</Text></div><Badge appearance="filled" color={error ? "danger" : "success"}>{error ? "Needs attention" : "Demo data / API boundary"}</Badge></header>
    <div className="steps">{["1 Select", "2 Load inventory", "3 Simulate position", "4 Overlay & summary"].map((label, i) => <span className={step === i + 1 ? "active" : step > i + 1 ? "done" : ""} key={label}>{label}</span>)}</div>
    <section className="workspace"><aside><Text size={500} weight="semibold">Guided steps</Text>
      <label>Warehouse<select value={warehouse?.id ?? ""} onChange={e => setWarehouse(warehouses.find(w => w.id === e.target.value))}><option value="">Select warehouse</option>{warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <label>Item<select value={item?.id ?? ""} onChange={e => setItem(items.find(x => x.id === e.target.value))}><option value="">Select item</option>{items.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <Button disabled={!warehouse || !item || loading} appearance="primary" onClick={loadInventory}>2. Load inventory</Button>
      <hr /><Text weight="semibold">3. AI simulated position</Text>
      <label>Reflectors <input type="number" min="1" max="32" value={reflectors} onChange={e => setReflectors(+e.target.value)} /></label>
      <label>Receivers <input type="number" min="1" max="8" value={receivers} onChange={e => setReceivers(+e.target.value)} /></label>
      <label>Noise ({noise.toFixed(2)}) <input type="range" min="0" max=".5" step=".01" value={noise} onChange={e => setNoise(+e.target.value)} /></label>
      <label>Calibration preset<select value={calibrationPreset} onChange={e => setCalibrationPreset(e.target.value)}><option value="none">None (do not undistort)</option><option value="demo-640x480">Demo 640×480</option><option value="custom">Custom JSON below</option></select></label>
      {calibrationPreset === "custom" && <><label>Camera matrix JSON (3×3)<input placeholder="[[560,0,320],[0,560,240],[0,0,1]]" value={cameraMatrix} onChange={e => setCameraMatrix(e.target.value)} /></label><label>Distortion JSON (4/5/8 values)<input placeholder="[0,0,0,0,0]" value={distortion} onChange={e => setDistortion(e.target.value)} /></label></>}
      <Button disabled={!inventory || loading} onClick={runSimulation}>{loading ? "Working…" : "Request simulated position"}</Button>
      <label>Capture mode<select value={captureMode} onChange={e => setCaptureMode(e.target.value)}><option>QR or ArUco</option><option>QR only</option><option>ArUco only</option></select></label>
      <p className="hint">Guidance: fill the frame with a high-contrast QR code or a flat 4×4 ArUco marker. Without a marker, the server explicitly falls back to deterministic simulation.</p>
      <label>Capture warehouse photo
        <input type="file" accept="image/*" capture="environment" disabled={loading} onChange={e => { const selected = e.target.files?.[0]; setPhoto(selected); setPhotoName(selected?.name ?? ""); }} />
      </label>
      {photoName && <p className="hint">Selected: {photoName}</p>}
      <Button disabled={!inventory || !photo || loading} appearance="primary" onClick={locatePhoto}>Send photo to server and locate</Button>
      {error && <p className="error">{error}</p>}</aside>
      <div className="stage">{camera && <video className="camera" ref={video} playsInline muted />}<Canvas camera={{ position: [5, 4, 7] }}><ambientLight intensity={1.4} /><directionalLight position={[4, 6, 3]} /><gridHelper args={[12, 12, "#315064", "#182b37"]} /><mesh position={[0, -.2, 0]}><boxGeometry args={[7, .3, 5]} /><meshStandardMaterial color="#18303c" /></mesh>{simulation && "detections" in simulation && simulation.events.length > 0 ? simulation.events.map((markerEvent, index) => <Marker key={markerEvent.sequence} position={[markerEvent.x, markerEvent.y, markerEvent.z]} label={`${simulation.detections.qr[index]?.data || `marker-${index + 1}`} · ${Math.round(markerEvent.confidence * 100)}%`} />) : (event || entity) && <Marker position={event ? [event.x, event.y, event.z] : [entity!.x, entity!.y, entity!.z]} label={`${latestCapture?.itemId ?? item?.id ?? "entity"} · ${Math.round((event?.confidence ?? entity!.confidence) * 100)}%`} />}</Canvas><div className="stage-label">{camera ? "CAMERA PREVIEW + 3D OVERLAY" : "3D overlay preview"} · latest entity/item position (not camera position) · {scene?.coordinateSystem ?? "waiting for scene"}</div></div>
      <aside><Text size={500} weight="semibold">4. Result</Text>{latestCapture && <><img className="capture-preview" src={latestCapture.image.url} alt="Latest warehouse capture" /><p><b>Latest capture:</b> {new Date(latestCapture.capturedAt).toLocaleString()}</p></>}<p><b>Position status:</b> {simulation && "positionStatus" in simulation ? simulation.positionStatus === "simulated" ? "SIMULATED (no marker)" : "MEASURED IMAGE COORDINATES (not world coordinates)" : "—"}</p>{simulation && "detectionStatus" in simulation && <><p><b>Detection:</b> {simulation.detectionStatus}</p><p><b>QR:</b> {simulation.detections.qr.map(x => x.data || "(empty payload)").join(", ") || "none"} · <b>ArUco:</b> {simulation.detections.aruco.map(x => x.id).join(", ") || "none"}</p><p><b>Undistortion:</b> {simulation.calibration.applied ? "applied" : "not applied"}</p></>}<p><b>Warehouse:</b> {warehouse?.name ?? "—"}</p><p><b>Item:</b> {item?.name ?? "—"}</p><p><b>Inventory:</b> {inventory ? `${inventory.quantity} ${inventory.status}` : "Not loaded"}</p><p><b>Position:</b> {event ? `${event.x.toFixed(2)}, ${event.y.toFixed(2)}, ${event.z.toFixed(2)}` : "Not simulated"}</p><p><b>Confidence:</b> {event ? `${Math.round(event.confidence * 100)}%` : "—"}</p>{simulation && "image" in simulation && <p><b>Server image:</b> {simulation.image.filename} ({simulation.image.bytes} bytes)</p>}<p className={webXr ? "event" : "muted"}><b>WebXR:</b> {webXr === undefined ? "checking…" : webXr ? "available (optional)" : "not available; iOS Safari camera mode still works"}</p><Button onClick={enableCamera}>{camera ? "Camera enabled" : "Enable rear camera"}</Button><div className="actions"><Button onClick={reset}>Reset</Button><Button disabled={!simulation} appearance="primary" onClick={() => setStep(4)}>Next</Button></div></aside></section></main></FluentProvider>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
