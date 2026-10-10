# Deployment and production readiness

The repository includes a Vercel multi-service configuration: a Vite web
frontend and a FastAPI API. The API is defined in `applications/api/main.py`
and exposed to the web service through the `/v1/*` and `/health` rewrites.
Vite proxies those paths to a local API during development.

## Production prerequisites

1. Link the repository to the intended Vercel project and verify its production
   domain, build output, and environment-variable scope before deployment.
2. Configure `DATABASE_URL` with a managed PostgreSQL connection. Do not rely
   on the SQLite `/tmp` fallback for production data.
3. Provide durable artifact storage before accepting production uploads. The
   current `LocalDiskStorage` writes to the instance filesystem. Vercel's
   writable `/tmp` is temporary, and setting `STORAGE_PATH` does not make that
   filesystem durable. A persistent object-storage adapter is not present yet.
4. Set `CORS_ORIGINS` only when the frontend calls the API from a different
   origin. Same-domain Vercel rewrites do not require cross-origin browser
   access.
5. Configure credentials in the hosting provider's environment settings. Do
   not commit tokens, database URLs, or model keys.

The `/health` endpoint checks API, database connectivity, and filesystem
availability. On Vercel it reports `degraded` while database or artifact
persistence is ephemeral. This is deliberate: a responding function is not
evidence that uploads and reports will survive a restart.

## Vercel deployment

Use the Vercel project already associated with this repository, or explicitly
link the correct project before running a production deployment:

```powershell
npx vercel@latest login
npx vercel@latest link
npx vercel@latest --prod
```

After configuring production environment variables, verify the health endpoint:

```powershell
curl https://<your-deployment>.vercel.app/health
```

Require `status: "ok"` and verify database and artifact persistence independently
before treating the service as production-ready. The current filesystem adapter
will remain ephemeral on Vercel until durable object storage is implemented;
the health response will say `degraded` even if API requests succeed.

## Render

`render.yaml` currently describes the Python API service only. It does not
configure a durable database, persistent artifact disk, or a separately hosted
web frontend. Those resources must be selected and configured before Render can
provide a durable production deployment.

## Live verification

`smoke_test.py` exercises login, organization/project creation, CSV upload,
profiling, quality validation, temporal safety, report retrieval, and tenant
isolation against its local development URL. Run it only with a disposable local
database: it uses fixed demo credentials and creates test workspaces. Do not run
it against a production tenant.
