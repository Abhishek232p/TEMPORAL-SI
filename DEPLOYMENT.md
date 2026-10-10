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
3. Create a **private Vercel Blob store** and connect it to this Vercel project
   for Production and Preview. The Python API uses the official Vercel Blob SDK
   and reads the connected store's `BLOB_STORE_ID` and `VERCEL_OIDC_TOKEN`
   automatically. A `BLOB_READ_WRITE_TOKEN` is supported for local development
   or non-Vercel deployments; keep it in the provider's environment settings.
   Without Blob credentials the API falls back to local storage, which is
   ephemeral on Vercel.
4. Set `CORS_ORIGINS` only when the frontend calls the API from a different
   origin. Same-domain Vercel rewrites do not require cross-origin browser
   access.
5. Configure credentials in the hosting provider's environment settings. Do
   not commit tokens, database URLs, or model keys.

The `/health` endpoint checks API, database connectivity, and the configured
artifact store. It reports the storage driver and persistence mode. For Blob it
creates a private health marker if absent and reads it back to confirm remote
connectivity. On Vercel it reports `degraded` while the database is SQLite or
artifacts are stored on the local filesystem. A responding function is not
evidence that uploads and reports will survive a restart.

## Vercel deployment

Use the Vercel project already associated with this repository, or explicitly
link the correct project before running a production deployment:

```powershell
npx vercel@latest login
npx vercel@latest link
npx vercel@latest --prod
```

After connecting the Blob store and configuring the production database, verify
the health endpoint:

```powershell
curl https://<your-deployment>.vercel.app/health
```

Require `status: "ok"` and verify database and artifact persistence independently
before treating the service as production-ready. The health response remains
`degraded` until both durable PostgreSQL and connected Blob storage are active.

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
