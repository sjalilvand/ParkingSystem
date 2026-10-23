# ParkingSystem

سیستم مدیریت پارکینگ هوشمند مجتمع‌های مسکونی — Smart Parking Management System

Full-stack, offline-capable parking & access-control platform designed for Iranian
residential complexes: Iranian license-plate normalization, permit-based gate
decisions, CAD/DXF parking-spot mapping, finance, violations and reports — with a
fully RTL Persian UI and Jalali calendar.

## Architecture

| Layer      | Tech                                                                                             |
|------------|--------------------------------------------------------------------------------------------------|
| backend    | Python 3.11 - FastAPI (async) - SQLAlchemy 2 - Alembic - PostgreSQL/SQLite - Redis - Celery - MinIO |
| frontend   | React 18 - TypeScript - Vite - MUI v6 (RTL) - TanStack Query - Dexie (offline) - PWA              |
| gate-agent | Python - pluggable plate-reader/barrier adapters - local SQLite queue - offline decisions          |
| realtime   | WebSocket event hub at /ws/v1/events                                                              |

## Backend Modules

identity/RBAC - complexes - residents - vehicles - permits - parking (+CAD import) -
access-control (gate decision engine) - finance - violations - reports - files (MinIO) -
base-data - devices - notifications

## Quick Start (Development)

Run everything from repo root:

    .\start-all.ps1

**به‌روزرسانی و اجرای سریع (توصیه‌شده برای سرورها):**

    .\UPDATE-AND-RUN.ps1          # git pull + نصب وابستگی‌ها + alembic + build + اجرا
    .\UPDATE-AND-RUN.ps1 -Prod    # حالت production با docker-compose.prod.yml
    .\UPDATE-AND-RUN.ps1 -SkipPull  # فقط اجرا

Or individually:

    .\start-backend.ps1     # FastAPI on :8000  (Swagger: /api/docs)
    .\start-frontend.ps1    # Vite dev server on :5173
    .\start-agent.ps1       # Gate agent (mock hardware)

Default dev admin: admin / Admin@1234  (change in any real deployment!)

## Key Endpoints

- REST API:  http://localhost:8000/api/v1/   -   Swagger UI: /api/docs
- WebSocket: ws://localhost:8000/ws/v1/events?token=<access-token>
- Health:    /health/live  /health/ready  /health/database

## Security Model

- All secrets live in .env files (git-ignored) - copy .env.example to .env
- JWT access tokens (15m) + rotating refresh tokens (7d)
- Argon2 password hashing, RBAC via require_permission()
- Full audit logging (audit_logs table)

## Roadmap

- [x] Notifications module (in-app + WebSocket push)
- [x] Celery: daily reports + file retention cleanup
- [x] Production docker-compose + nginx
- [x] Policy decisions D1-D10 applied & runtime-configurable (`GET /api/v1/policy-settings`, docs/pending-decisions.md v1.0)
- [x] Plate OCR service (Iranian plate reader): `POST /api/v1/plate-ocr/read` + test page at `/plate-test/` (docs/plate-ocr.md)
- [ ] Real hardware adapters for plate-reader / barrier
- [ ] Field testing with real ANPR camera / barrier / thermal printer

## Plate Normalization

Iranian plates in any format are normalized, e.g.
    ۱۲ ب ۳۴۵ ایران ۶۷  ->  12B345IR67
Persian/Arabic digits, letter variants (ك->ک, ي->ی) are handled automatically.
