# Digital Twin 3D to EIS-ERP — Dev Demo

Local demo boundary: React/React Three Fiber, ASP.NET Core Web API, and Python/FastAPI position worker. Synthetic ERP data only; no secrets.

## Run
### One-command Windows start

From the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-demo.ps1 -Tunnel
```

This opens separate PowerShell windows for the frontend, Integration API, position worker, and Cloudflare HTTPS tunnel. Keep those windows open. The tunnel window prints the HTTPS URL to open in iPhone Safari. To run without a tunnel, omit `-Tunnel` and use the LAN URL printed by the script.

The HTTPS URL is temporary and changes whenever the tunnel is restarted. Always use the newest URL printed by the tunnel window; an old URL will stop working.

After the services are running, verify the current multi-QR version with:

```powershell
.\scripts\test-demo.ps1
```

```bash
cd frontend
npm install
npm run dev
```
Open the printed URL. Guided workflow: (1) select warehouse/item, (2) load inventory from the integration API, (3) request AI simulated position and tune reflector/receiver/noise/calibration, (4) capture a warehouse photo with the rear camera, (5) send the photo to the position server, then review the 3D overlay and inventory/location summary. Simulation output is explicitly labelled **demo data — simulated, not measured**.

```bash
cd services/integration-api
dotnet run
```
API: `http://localhost:5080`; Swagger: `/swagger`.

```bash
cd services/position-worker
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8001
```

For a different device/proxy, set `VITE_API_BASE` and `VITE_WORKER_BASE` to HTTPS reverse-proxy URLs before `npm run dev`. Keep both origins HTTPS on iPhone; the worker allows the local Vite origins for development.

SQL Server/Azure SQL migration and Blob/Azurite adapter configuration are included as boundaries. Apply migrations locally only; never commit credentials.

## iPhone photo-to-position demo

The frontend sends the captured image plus `warehouseId` and `itemId` as multipart form data to `POST /position/locate`. The worker optionally uses OpenCV QRCodeDetector and ArUco (contrib) detection. A marker result is measured in image pixels only; no world coordinates are claimed. No marker explicitly falls back to deterministic **demo data — simulated, not measured**. The worker persists one latest image and metadata JSON per warehouse under the ignored, server-local `services/position-worker/runtime-data` directory. `GET /position/warehouses/{warehouseId}/latest` returns metadata and a browser-loadable image URL; it returns 404 before the first capture. The Vite proxy forwards `/position` to port `8001`.

Sample QR image for testing: `samples/warehouse-item-qr.png`. It encodes `warehouseId=WH-BKK-01`, `itemId=ITEM-204`, and `entityId=ITEM-204`. Use it with the capture upload flow or select it from a desktop browser.

Multiple QR codes are supported in one photo. `samples/two-warehouse-items-qr.png` contains `ITEM-204` and `ITEM-205`; the worker returns one detection and one image-coordinate event per QR code, preserving each payload and center pixel.

Calibration accepts `calibrationPreset=demo-640x480` or JSON `cameraMatrix` (3x3) and `distortionCoefficients` (4/5/8 values). Undistortion is applied only after validation; `none`/`standard-v1` do not undistort. WebXR capability is displayed when available but is never required for iOS Safari.

## iPhone limitations
Use Safari over HTTPS (or localhost), grant camera permission, and keep the tab foregrounded. iOS may suspend camera/WebGL or throttle frame rate. This is a demo 3D overlay, not measured AR world tracking.

## iPhone RoomPlan room reconstruction

The **Building / floor / room 3D** view displays the latest RoomPlan geometry uploaded for a selected room. The iOS app source is in `ios/RoomPlanScanner`; it scans walls, doors, windows, and openings and sends their transforms and dimensions in meters to the ASP.NET API. The web viewer renders those measured surfaces with orbit/zoom controls. A placeholder room is explicitly labelled as a demo and is not measured.

RoomPlan requires a LiDAR-capable iPhone Pro and a Mac with Xcode to build/sign the native app. On the Mac, open `ios/RoomPlanScanner/RoomPlanScanner.xcodeproj`, set your Apple development team in Signing & Capabilities, connect the iPhone, and run the `RoomPlanScanner` target. In the app, select the building/floor/room, set **API base URL** to `https://<current-cloudflare-tunnel-host>/api/v1`, enter the room scan access token printed by `start-demo.ps1`, scan the room, finish the scan, and upload it. The URL must be the current HTTPS URL printed by `.\scripts\start-demo.ps1 -Tunnel`; it changes when the tunnel restarts. On the web page, open **Building / floor / room 3D**, enter that same token (held only in the current browser session), and refresh the latest scan.

## USB RGB-D camera room point cloud

The room viewer also supports an Orbbec USB RGB-D camera such as Gemini 2, using the official [Orbbec Python SDK v2 wrapper](https://github.com/orbbec/pyorbbecsdk). Connect the camera to the same Windows computer running the position worker using a USB 3.0 data cable/port. Install the optional SDK wheel without its example-viewer dependencies (the project already uses OpenCV contrib):

```powershell
& .\services\position-worker\.venv\Scripts\python.exe -m pip install --no-deps -r .\services\position-worker\requirements-usb-camera.txt
```

Restart `start-demo.ps1` after installation. In **Building / floor / room 3D**, enter the room scan token, press **Check USB camera**, set an approximate pose for the first capture, then press **Capture depth and align view**. With **Auto-align overlapping views (ICP)** enabled, later captures use the last estimated pose as an initial guess and refine it against the accumulated room cloud. Move in small steps and keep the previous scene visible. The viewer reports the latest alignment fitness and RMSE.

Each capture uses the depth stream and SDK-provided intrinsics to project valid samples into 3D. ICP refines overlapping views locally; low-confidence matches are rejected without changing the saved scan. This is **not full SLAM**: the first camera pose is approximate, motion must be small, and feature-poor, repetitive, or mostly flat scenes can fail or drift. Manual placement remains available. This prototype does not extract room planes or create a watertight mesh; one capture is only one viewpoint. Validate alignment on the target room and physical camera before relying on its measurements. The SDK package includes prebuilt Windows x64 wheels for supported Python versions, but the physical camera and USB 3 connection are required to test live capture.

The demo API provides `GET /api/v1/buildings`, `GET /api/v1/buildings/{buildingId}/floors`, `GET /api/v1/floors/{floorId}/rooms`, `POST /api/v1/rooms/{roomId}/scans`, and `GET /api/v1/rooms/{roomId}/scans/latest`. Scan upload/latest require the `X-Room-Scan-Token` header. The launcher generates a random 256-bit token if `ROOM_SCAN_ACCESS_TOKEN` is not set; the token is not stored in the repository. The API accepts at most 500 validated surfaces and 1 MB per request. Scan JSON is saved outside the repository in `%LOCALAPPDATA%\DigitalTwin3D\room-scans` (override with `ROOM_SCAN_DATA_DIR`); each room retains versioned JSON plus a latest pointer.

USB camera endpoints are `GET /position/usb-camera/status`, `POST /position/usb-camera/rooms/{roomId}/capture`, and `GET /position/usb-camera/rooms/{roomId}/latest`; all require the same `X-Room-Scan-Token`. USB point clouds are stored under the worker's ignored runtime-data directory.

This first milestone reconstructs room geometry; it does not use a single photo to infer depth and does not apply photographs as wall textures. The RoomPlan live camera view is used while scanning. For a non-LiDAR iPhone or photo-textured reconstruction, a separate photogrammetry/depth workflow is required. The demo endpoints currently use synthetic building/floor/room data and do not yet enforce production authentication.

## Validation
`npm --prefix frontend run build`, `dotnet build services/integration-api`, `python -m compileall services/position-worker`, and `services/position-worker/.venv/Scripts/python.exe -m unittest discover -s services/position-worker -p "test_usb_camera*.py"`.