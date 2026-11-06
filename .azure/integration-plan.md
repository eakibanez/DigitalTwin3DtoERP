# Integration hand-off
- Backend: `services/integration-api`; `dotnet run`; port 5080; build `dotnet build`; health `/health/live`, `/health/ready`.
- Frontend: `frontend`; `npm run build`; `npm run dev`; live-data seam: `frontend/src/api/index.ts` (add during integration; current UI is synthetic demo state).
- API routes: GET `/api/v1/warehouses`, `/items`, `/inventory`, `/receiving`, `/picking`, `/work-orders`, `/twin/scenes/{warehouseId}`; health endpoints; worker POST `/simulate`.
- Database: SQL Server/Azure SQL; `database/migrations/001_init.sql`; `ConnectionStrings__TwinDatabase`; apply schema only, NO seed data.
- Blob: Azurite/Azure Blob adapter settings in `appsettings.Development.json`; never commit credentials.
- Worker: `services/position-worker`; `uvicorn app:app --reload --port 8001`; Python 3.11.
- Services: Essential frontend, integration API, worker, SQL boundary. Enhancement Blob assets, Entra auth, real ERP adapter.
