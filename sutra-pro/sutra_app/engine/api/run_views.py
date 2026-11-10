"""Rows 6 to 9, 14, 18 and 19, and J2's own routes of sync 4: preview, documents, map, plan, the plan as a map, agent, one function's
activity, the Simple view's record of a part or a deliverable, story and board (engine design 7.1; J2 sync 4, D140)."""
from fastapi import APIRouter

from .ctx import add_get

__all__ = ["ROUTES", "add_routes"]

ROUTES = (("/api/preview", "preview"), ("/api/docs", "docs"), ("/api/map", "map"), ("/api/plan", "plan"),
          ("/api/plan-map", "plan_map"), ("/api/agent", "agent"), ("/api/activity", "activity"), ("/api/record", "record"),
          ("/api/story", "story"), ("/api/board", "board"))


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        add_get(router, services, dept_dep, path, name)
