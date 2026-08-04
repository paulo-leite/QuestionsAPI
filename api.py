"""Entrypoint compatível com ``uvicorn api:app``."""

from deep_research.app import app


__all__ = ["app"]
