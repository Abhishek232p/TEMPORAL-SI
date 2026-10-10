# Temporal Intelligence Platform

The Temporal Intelligence Platform helps data science and ML teams inspect
time-series datasets before using them in forecasting workflows. It is a
dataset-first workbench for profiling, data-quality validation, and temporal
leakage-risk analysis—not a chatbot or a forecasting-accuracy guarantee.

## What works today

- Organization- and project-scoped workspaces with authenticated API access.
- Versioned CSV and Parquet dataset uploads, content hashes, and schema metadata.
- Dataset profiles, data-quality reports, and temporal causal-safety reports.
- Persisted findings with rule IDs, severity, evidence, detection type, and
  confidence where the analysis produces it.
- A web workbench for creating workspaces/projects/datasets, uploading versions,
  running the analyses, and reviewing results.
- `/health` probes the API, database, and artifact storage and distinguishes
  service availability from persistence readiness.

Temporal safety heuristics are review signals, not causal proof. Structural
checks and statistical suspicions are reported separately. Findings describe
the inspected data; they do not guarantee forecast performance.

## Run locally

Start the API in one terminal from the repository root:

```powershell
python -m uvicorn applications.api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
cd apps/web
npm ci
npm run dev
```

Open the Vite URL (normally `http://localhost:5173`). The development server
proxies `/health` and `/v1` to the API at `http://127.0.0.1:8000`. A first sign-in
creates a user; create a workspace and project, then upload a CSV or Parquet
dataset version.

## Validate

```powershell
python -m pytest tests -q
cd apps/web
npm run build
npm run lint
```

For a running local API, the repository end-to-end smoke journey is:

```powershell
python smoke_test.py
```

## Architecture and operations

- `applications/api`: FastAPI routes and request/response schemas.
- `packages/core`: authentication, storage, profiling, quality, and temporal
  safety logic.
- `apps/web`: React/TypeScript workbench built with Vite.
- `database/migrations`: Alembic schema history.
- `docs/`: architecture, data, security, and deployment documentation.

See [DEPLOYMENT.md](DEPLOYMENT.md) before publishing a production deployment.
The Vercel filesystem is ephemeral; durable production artifact storage is not
implemented by the current local-filesystem adapter. Production readiness must
not be inferred from a successful API health response alone.
