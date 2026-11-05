"""Rows 10 to 12: the template library, one template version and a run's template decisions (engine design 7.1).

`/api/library` is J2's template library; the library package's schema routes live at `/api/schemas` (D79)."""
from fastapi import APIRouter

from .ctx import add_get

__all__ = ["ROUTES", "add_routes"]

ROUTES = (("/api/library", "library"), ("/api/library/{artifact}/{section}/{slug}/{version}", "library_item"),
          ("/api/run-templates", "run_templates"))


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        add_get(router, services, dept_dep, path, name)
