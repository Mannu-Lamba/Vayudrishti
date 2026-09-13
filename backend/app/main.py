"""ASGI entry point for `uvicorn app.main:app` (run from backend/).

The application is server.py; this module re-exports it, so `server:app` and `app.main:app` serve the same
single app — one model registry, one MongoDB connection, the same routes.
"""

from server import app

__all__ = ["app"]
