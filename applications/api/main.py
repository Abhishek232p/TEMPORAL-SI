from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from applications.api.routers import organizations, projects, datasets, auth
from packages.core.db.session import engine
from packages.core.db.models import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")

# ---------------------------------------------------------------------------
# CORS – configurable via env for real deployments (comma-separated origins).
# Default allows any origin so every device/browser can reach the API.
# ---------------------------------------------------------------------------
import os as _os

_cors_origins = _os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=("*" not in _cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(datasets.router)

# ---------------------------------------------------------------------------
# Server-rendered Web UI ("live render"): Jinja2 templates + static assets.
# The same app serves the REST API and the responsive front-end so the whole
# product renders end-to-end from a single process.
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "web" / "templates"))

app.mount("/static", StaticFiles(directory=str(APP_DIR / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def render_home(request: Request):
    """Live-rendered landing/dashboard shell (fully responsive, all devices)."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    """Deep health check used by load balancers / orchestrators."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:  # pragma: no cover
        return {"status": "degraded", "database": str(exc)}
