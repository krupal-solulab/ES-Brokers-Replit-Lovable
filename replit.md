# Insurance OS — E&S Broker Platform

Full-stack insurance workflow platform for Excess & Surplus (E&S) brokers. Shared Python/FastAPI backend powering a React/TanStack frontend.

## Project structure

```
BE-ES-Brokers/   Python FastAPI backend (port 4000)
FE-ES-Brokers/   React + TanStack Start frontend (port 5000)
```

## Running on Replit

Two workflows are configured and start automatically:

| Workflow | Command | Port |
|---|---|---|
| **Backend API** | `cd BE-ES-Brokers && uvicorn main:app --app-dir src --host 0.0.0.0 --port 4000 --reload` | 4000 (console) |
| **Start application** | `cd FE-ES-Brokers && npm run dev -- --port 5000 --host 0.0.0.0` | 5000 (webview) |

The frontend's Vite dev server proxies all `/api` requests to `http://localhost:4000`, so both services work together without cross-origin issues.

## Database

Uses Replit's managed **PostgreSQL** database (injected as `DATABASE_URL`). The backend normalizes the URL to use `asyncpg` driver automatically.

- Migrations: `cd BE-ES-Brokers && python -m alembic upgrade head`
- Seed demo data: `cd BE-ES-Brokers && python src/core/seed.py`

Demo credentials (header-stub auth, Phase 0):
- Tenant: `demo-es`
- Users: `junior@demo-es.example`, `senior@demo-es.example`, `admin@demo-es.example`
- Admin password: `Pa$$w0rd!`

## Environment variables

Set via Replit Secrets / env vars:

| Key | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Set to `""` (empty) — frontend uses Vite proxy |
| `VITE_DEMO_TENANT_ID` | `demo-es` |
| `VITE_DEMO_USER_ID` | `demo-es-junior` |
| `VITE_DEMO_ROLE` | `junior` |
| `OPENAI_API_KEY` | Required for LLM features (Phase 1) |

## Tech stack

- **Backend**: Python 3.12, FastAPI, SQLModel/SQLAlchemy, Alembic, asyncpg, Arq/Redis, OpenAI
- **Frontend**: React 19, TanStack Router + Start, Vite, Tailwind CSS v4, shadcn/ui, Recharts

## User preferences

- Keep project's existing structure — do not restructure or migrate.
