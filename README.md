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

## Validation
`npm --prefix frontend run build`, `dotnet build services/integration-api`, and `python -m compileall services/position-worker`.