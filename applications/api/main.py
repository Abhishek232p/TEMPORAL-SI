from fastapi import FastAPI
from applications.api.routers import organizations, projects, datasets, auth
from packages.core.db.session import engine
from packages.core.db.models import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(datasets.router)

@app.get("/health")
def health():
    return {"status": "ok"}
