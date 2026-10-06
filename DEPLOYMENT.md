# Deploying to Vercel

The API is a FastAPI app located at `applications/api/main.py`. Vercel's Python
runtime auto-detects entrypoints only at the repo root (`app.py`, `index.py`,
`server.py`, `main.py`, `wsgi.py`, `asgi.py`) or in `src/`, `app/`, `api/`.
Because this app lives under `applications/api/`, the entrypoint is declared
explicitly in `pyproject.toml`:

```toml
[tool.vercel]
entrypoint = "applications.api.main:app"
```

## Deploy

```powershell
npx vercel@latest login          # one-time, interactive browser auth
npx vercel@latest --prod         # deploy to production
```

Or, non-interactively with a token from <https://vercel.com/account/tokens>:

```powershell
$env:VERCEL_TOKEN = "<your-token>"
npx vercel@latest --prod --token $env:VERCEL_TOKEN --yes
```

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Recommended | Postgres connection string. Without it the app falls back to SQLite in `/tmp`, which is **ephemeral per function instance** — data does not persist between invocations. Use Vercel Postgres / Neon for real persistence. |
| `STORAGE_PATH` | Optional | Overrides the artifact directory. Defaults to `/tmp/.storage` on Vercel. |

## Serverless filesystem notes

Vercel Functions have a read-only filesystem except for `/tmp`. The app adapts
automatically when the `VERCEL` environment variable is set (Vercel sets this
itself):

- `packages/core/db/session.py` → SQLite fallback becomes `sqlite:////tmp/temporal_intelligence.db`
- `packages/core/storage/local.py` → artifact storage becomes `/tmp/.storage`

For production you should supply a real `DATABASE_URL`; the `/tmp` SQLite
fallback exists only so the app boots rather than crashing on import.

## Verifying a deployment

```powershell
curl https://<your-deployment>.vercel.app/health
# {"status":"ok"}
```

Then run the end-to-end suite against the live URL by pointing `API_URL` in
`smoke_test.py` at the deployment.
