"""Vercel serverless entrypoint.

Vercel's Python runtime looks for an ASGI/WSGI callable named `handler`
(or falls back to common names) inside /api/*.py. We re-export the FastAPI
app from the monorepo package so the whole platform (API + live-rendered
responsive front-end) is served from a single serverless function.
"""
import sys
from pathlib import Path

# Make the repository root importable in the serverless bundle layout
# (/var/task/api/index.py -> repo root is one level up).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from applications.api.main import app  # noqa: E402,F401  (re-exported for Vercel)

# Some Vercel Python runtimes look for these names explicitly.
handler = app
