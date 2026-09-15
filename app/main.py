"""Vercel FastAPI entrypoint — re-exports the demo app."""

from hiver_agent.web.app import app

__all__ = ["app"]
