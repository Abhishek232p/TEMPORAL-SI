import os
import logging
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from applications.api.routers import organizations, projects, datasets, auth, chat
from packages.core.db.session import engine
from packages.core.db.models import Base
from packages.core.storage.factory import get_artifact_storage

Base.metadata.create_all(bind=engine)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")
logger = logging.getLogger(__name__)

cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(datasets.router)
app.include_router(chat.router)

@app.get("/health")
def health():
    services = {
        "api": {"status": "ok"},
        "database": {"status": "ok"},
        "storage": {"status": "ok"},
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        services["database"]["status"] = "unavailable"

    storage = get_artifact_storage()
    services["storage"].update({
        "driver": storage.driver,
        "persistence": storage.persistence,
    })
    try:
        storage.check_health()
    except Exception:
        logger.exception("Artifact storage health check failed")
        services["storage"]["status"] = "unavailable"

    on_vercel = bool(os.environ.get("VERCEL"))
    if on_vercel:
        services["database"]["persistence"] = (
            "ephemeral" if engine.dialect.name == "sqlite" else "configured"
        )

    ready = all(service["status"] == "ok" for service in services.values())
    if any(service.get("persistence") == "ephemeral" for service in services.values()):
        ready = False

    return {
        "status": "ok" if ready else "degraded",
        "services": services,
    }

# Serve the web UI from the same origin as the API so the browser never issues a
# cross-origin request (and no CORS middleware is required).
WEB_DIR = Path(__file__).resolve().parents[2] / "apps" / "web" / "dist"

if WEB_DIR.is_dir():
    assets_dir = WEB_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def index():
        return FileResponse(str(WEB_DIR / "index.html"))
