# Digital Twin 3D to EIS-ERP — Dev Demo Project Plan

**Status**: Approved
**Created**: 2026-11-06
**Mode**: Dev demo first; phased path to production

## 1. Project Summary

Build a demonstrable Digital Twin 3D application integrated with EIS-ERP. The first release visualizes warehouses and inventory-related objects, retrieves ERP data, runs a reflector-based AI position simulation, and displays replayable positions with confidence. Simulation parameters derived from `ระบบ AI จำลองตำแหน่งด้วยตัวสะท้อน.pdf` are editable in the UI.

The existing PHP/IIS EIS-ERP remains the system of record. A new ASP.NET Core Web API is an explicit integration boundary, and a Python/FastAPI worker owns simulation calculations. No telemetry stream or Redis is included in this phase.

## 2. Goals, Scope & Non-Goals

### Goals
- Deliver a local dev demo with a navigable 3D warehouse/facility scene.
- Connect Digital Twin views to ERP entities: `items`, `warehouses`, `inventory`, `receiving`, `picking`, and `work_orders`.
- Support Microsoft Entra ID/OAuth2 authentication and authorization.
- Allow users to edit reflector, receiver, noise, calibration, and confidence parameters.
- Produce deterministic simulation runs, position events, confidence/status, and replay controls.
- Scan LiDAR-enabled iPhone rooms with RoomPlan, bind scans to building/floor/room, and render measured surfaces in the web Digital Twin.
- Define complete boundaries for later deployment without prematurely implementing production infrastructure.

### Non-Goals
- No live hardware/telemetry ingestion in the dev demo.
- No Redis, message broker, or real-time production event bus.
- No write-through changes to ERP inventory without an explicit approved command endpoint.
- No replacement of the existing PHP ERP.

## 3. Users & Primary Flows

1. **Warehouse operator** signs in, selects a warehouse, navigates the 3D scene, selects an item/location, and opens the corresponding ERP record.
2. **Supervisor** filters inventory, receiving, picking, and work orders, starts a simulation replay, and reviews position confidence and warnings.
3. **Integrator/developer** changes simulation parameters, runs a deterministic scenario, inspects raw measurements and calculated position, and exports a replay artifact.
4. **Auditor** views simulation run metadata, parameter versions, user, timestamp, and correlation ID.

## 4. Architecture & Service Boundaries

### Components
- **Frontend**: React + TypeScript, React Three Fiber/Three.js, Fluent UI v9. Hosts scene, ERP panels, parameter editor, replay controls, and API client.
- **iOS scanner**: SwiftUI + Apple RoomPlan on a LiDAR-capable iPhone. Uploads versioned room surfaces, transforms, and dimensions in meters to the Integration API.
- **USB depth capture**: Python position worker with the official Orbbec SDK v2 wrapper. Captures Gemini 2 depth frames, projects them using device intrinsics, and uses seeded ICP to refine the initial camera pose between overlapping views.
- **Integration API**: ASP.NET Core Web API. Validates Entra tokens, exposes versioned `/api/v1` endpoints, maps ERP contracts, owns demo orchestration and audit metadata.
- **AI worker**: Python + FastAPI. Implements PDF-derived reflector/receiver calculation, noise and calibration models, confidence scoring, deterministic seed/replay, and health endpoints.
- **Existing ERP**: PHP/IIS application and SQL Server/Azure SQL source-of-record boundary. Access is through an adapter/repository and documented read contracts.
- **Blob Storage**: 3D assets, scene manifests, uploaded reference documents, and replay/export artifacts.

### API boundaries
- Frontend calls only the ASP.NET Core API; it never calls SQL, Blob Storage, PHP internals, or the AI worker directly.
- ASP.NET Core calls the ERP adapter for ERP data and calls the AI worker for simulation jobs.
- AI worker returns versioned simulation results/events; it does not own ERP records or identity.
- USB depth ICP is local registration seeded by the previous pose, not full SLAM; first-pose setup, small overlapping camera motion, and physical-device validation are required. No room-plane extraction or watertight mesh is claimed.
- Blob access uses short-lived server-issued URLs or API proxying; containers are private.
- All requests carry `traceId`, authenticated subject, and schema version where applicable.

### Key endpoints
- `GET /api/v1/warehouses`
- `GET /api/v1/items?warehouseId=...`
- `GET /api/v1/inventory?warehouseId=...&itemId=...`
- `GET /api/v1/receiving`
- `GET /api/v1/picking`
- `GET /api/v1/work-orders`
- `GET /api/v1/twin/scenes/{warehouseId}`
- `GET /api/v1/twin/positions/{entityId}`
- `POST /api/v1/simulations` — validate parameters and create a run
- `POST /api/v1/simulations/{runId}/replay`
- `GET /api/v1/simulations/{runId}`
- `GET /api/v1/simulations/{runId}/events`
- `GET /api/v1/assets/{assetId}/download-url`
- `GET /api/v1/buildings`, `GET /api/v1/buildings/{buildingId}/floors`, `GET /api/v1/floors/{floorId}/rooms`
- `POST /api/v1/rooms/{roomId}/scans`, `GET /api/v1/rooms/{roomId}/scans/latest`
- `GET /position/usb-camera/status`, `POST /position/usb-camera/rooms/{roomId}/capture`, `GET /position/usb-camera/rooms/{roomId}/latest`
- `GET /health/live`, `GET /health/ready`

Commands that could change ERP state are deferred or protected behind an explicit feature flag and separate authorization policy.

## 5. Data Model & Contracts

### SQL Server/Azure SQL
- `twin_scene`: warehouse-to-scene manifest and revision.
- `twin_entity_binding`: Digital Twin object to ERP entity type/id.
- `twin_asset`: asset metadata, Blob key, checksum, revision.
- `simulation_run`: run id, scenario, parameter JSON, algorithm version, seed, status, timestamps, user and trace id.
- `simulation_event`: run id, sequence, timestamp, entity id, x/y/z, confidence, status, raw measurement summary.
- `simulation_calibration`: named calibration profile and version.
- `room_scan` / `room_surface`: versioned building/floor/room capture metadata and validated local-coordinate surface geometry.
- `integration_audit`: actor, operation, endpoint, ERP correlation id, outcome, and redacted payload hash.

ERP source entities remain external/read-only in the demo: `items`, `warehouses`, `inventory`, `receiving`, `picking`, `work_orders`.

### Contract rules
- IDs are opaque strings; timestamps are UTC ISO-8601.
- API uses OpenAPI, nullable fields explicitly declared, pagination on collections, and RFC 7807 problem details.
- Position units and coordinate-system/origin are explicit in every scene manifest.
- Parameter payload includes reflector geometry, receiver geometry, sampling/noise settings, calibration profile, confidence thresholds, algorithm version, and deterministic seed.
- Never persist access tokens, secrets, or unredacted sensitive ERP payloads.

## 6. Design System & UI

**Component Library**: Fluent UI v9
**Visual direction**: dark technical operations console with high-contrast status colors and accessible typography.
**Layout**: left navigation; central 3D canvas; right context panel; bottom timeline/event inspector.
**Core components**: `AppShell`, `WarehouseSelector`, `TwinViewport`, `SceneLayerToggle`, `EntityInspector`, `ErpRecordPanel`, `SimulationParameterForm`, `ReplayTimeline`, `ConfidenceBadge`, `EventTable`, `ErrorBanner`.
**3D interaction**: orbit/pan/zoom, selectable objects, hover labels, highlighted ERP binding, position trail, confidence heat/status overlay, and reset camera.
**Responsive/accessibility**: keyboard navigation for panels and controls, non-color status labels, reduced-motion option, loading/empty/error states, and a 2D event-table fallback.

## 7. Local Development & Configuration

### Repository structure
- `frontend/` React application, API client, scene components, UI tests.
- `ios/RoomPlanScanner/` native iOS RoomPlan capture app (requires macOS/Xcode and LiDAR iPhone for device validation).
- `services/integration-api/` ASP.NET Core solution, controllers, application services, ERP adapter, auth, OpenAPI.
- `services/position-worker/` Python package, FastAPI routes, simulation engine, fixtures, tests.
- `database/migrations/` SQL Server/Azure SQL migrations for Twin and simulation tables.
- `storage/scene-manifests/` non-secret demo manifests and sample metadata.
- `tests/contract/`, `tests/e2e/`, and `docs/architecture/`.

### Dev setup
1. Install Node.js LTS, .NET 8 SDK, Python 3.11+, SQL Server Express/Developer or Azure SQL dev database, and Azure Storage emulator (Azurite).
2. Configure `.env`/user-secrets locally; commit only `.env.example`.
3. Apply migrations and load synthetic demo records only (never production ERP data).
4. Start FastAPI, ASP.NET Core API, and React dev server with documented ports and CORS restricted to the frontend origin.
5. Run the seed scene manifest and deterministic simulation fixture.
6. Sign in with a dev Entra app registration or a documented local development identity mode that cannot be enabled in production.

Required configuration includes Entra tenant/client/audience, ERP base URL and server-side credentials, SQL connection, Blob endpoint/container, AI worker URL, allowed origins, and feature flags. Secrets use local secret stores or environment injection.

## 8. Security, Privacy & Reliability

- Validate JWT issuer, audience, signature, expiry, scopes, and tenant; use Entra OAuth2 Authorization Code + PKCE in the frontend.
- Enforce API policies: `Twin.Read`, `Simulation.Run`, `Simulation.Configure`, `Audit.Read`; default deny.
- Apply least-privilege SQL and Blob identities, private containers, HTTPS, strict CORS, security headers, and request-size limits.
- Require a session-specific high-entropy access token for development room-scan upload/read endpoints; do not expose room geometry over an unauthenticated tunnel.
- Validate all geometry/numeric inputs with safe bounds; prevent SSRF by allow-listing ERP/worker URLs; sanitize asset paths and filenames.
- Treat ERP data as sensitive: minimize fields, redact logs, and retain audit records according to policy.
- Add cancellation/timeouts, bounded simulation workload, idempotency key for run creation, correlation IDs, and clear degraded-mode behavior.
- Do not claim simulation accuracy until calibrated against the PDF methodology and approved sample measurements.

## 9. Testing & Acceptance Criteria

### Testing
- Frontend unit/component tests for parameter validation, API states, scene selection, and accessible controls.
- ASP.NET unit/integration tests for authorization, mappings, pagination, problem details, ERP adapter, and OpenAPI.
- Python tests for PDF-derived equations, units, calibration, noise, confidence, deterministic seed, invalid bounds, and replay ordering.
- Contract tests between frontend/API and API/worker.
- SQL migration tests and synthetic fixture verification.
- E2E smoke test: sign in → choose warehouse → load scene → inspect ERP entity → edit parameters → run/replay → see confidence/events.
- Room scan contract test: select building/floor/room → upload bounded RoomPlan geometry → retrieve latest scan → render surfaces in 3D.
- USB depth capture contract test: verify Orbbec SDK/device status, project a calibrated depth frame, refine overlapping views with ICP, reject low-confidence alignment, and render the accumulated cloud.
- Security checks: dependency scanning, secret scanning, OWASP API cases, token and authorization negative tests.

### Acceptance criteria
- A new developer can start all three services locally using documented commands and synthetic data.
- Entra-authenticated user can load a warehouse scene and retrieve all six required ERP entity types through the API.
- Selecting a 3D object resolves to the correct ERP entity binding and displays a deep link/summary.
- User can edit reflector, receiver, noise, calibration, and confidence values; invalid values are rejected with field-level errors.
- Same algorithm version, seed, inputs, and fixture produce identical ordered position events.
- Replay shows position, timestamp, confidence, status, and trail; low-confidence events are visibly marked and available in the event table.
- Every simulation run is auditable with actor, parameters/version, seed, timestamps, and correlation ID, without secrets.
- API never exposes SQL/Blob credentials and rejects unauthenticated or insufficiently scoped requests.
- Health/readiness endpoints and automated tests pass; no telemetry or Redis dependency is required.

## 10. Phased Implementation

### Phase 0 — Contract and demo foundation
Confirm PDF equations, units, coordinate conventions, representative warehouse scene, ERP field mappings, Entra app registration, and synthetic fixtures. Produce OpenAPI and worker schemas.

### Phase 1 — Dev demo vertical slice
Create React shell and 3D scene, ASP.NET API read endpoints, ERP adapter mocks/fixtures, Entra sign-in, scene/entity bindings, and Blob/Azurite asset loading.

### Phase 2 — AI simulation integration
Implement Python/FastAPI calculation and validation, parameter editor, run/replay endpoints, deterministic event persistence, confidence display, and audit trail.

### Phase 3 — ERP breadth and hardening
Add all six ERP entity mappings, pagination/filtering, error/degraded states, contract/E2E/security tests, migration automation, logging/metrics, and operator documentation.

### Phase 4 — Production readiness decision
Validate against approved measurements, decide whether to add queue/telemetry/Redis, select Azure hosting, complete threat model, performance/load testing, backup/retention, and deployment runbooks. Production deployment is out of scope until this plan is approved and the demo acceptance criteria pass.

## 11. Risks, Decisions & Open Validation

- The supplied reference repository currently contains only a README and `.gitignore`; no 3D source assets or implementation contract was found.
- The PDF must be reviewed by a domain owner to confirm exact reflector model, receiver geometry, units, calibration procedure, confidence formula, and expected accuracy. Until then, these are configurable versioned parameters, not asserted scientific conclusions.
- Existing ERP schema and authentication integration require a mapping workshop before replacing fixtures with live reads.
- Azure SQL is the target managed option; local SQL Server is the development equivalent.
- Any future live telemetry path must be designed separately so the demo remains deterministic and testable.

## 12. Approval Gate & Next Step

This plan has been explicitly approved. Scaffold the dev demo from this plan, then run integration verification against the acceptance criteria. Production deployment remains out of scope.
