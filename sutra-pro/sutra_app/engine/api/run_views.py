"""Rows 6 to 9, 14, 18 and 19: preview, documents, map, plan, agent, story and board (engine design 7.1)."""
from fastapi import APIRouter

from .ctx import add_get

__all__ = ["ROUTES", "add_routes"]

ROUTES = (("/api/preview", "preview"), ("/api/docs", "docs"), ("/api/map", "map"), ("/api/plan", "plan"), ("/api/agent", "agent"),
          ("/api/story", "story"), ("/api/board", "board"))


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        add_get(router, services, dept_dep, path, name)
