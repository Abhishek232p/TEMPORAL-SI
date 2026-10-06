from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from applications.api.routers import organizations, projects, datasets, auth, chat
from packages.core.db.session import engine
from packages.core.db.models import Base

Base.metadata.create_all(bind=engine)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    return {"status": "ok"}

# Serve the web UI from the same origin as the API so the browser never issues a
# cross-origin request (and no CORS middleware is required).
WEB_DIR = Path(__file__).resolve().parents[2] / "apps" / "web"

if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(WEB_DIR / "index.html"))
