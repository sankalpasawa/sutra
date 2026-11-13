"""Rows 10 to 12 and the catalog: the template library, one template version, a run's template decisions and the shared library
page's data (engine design 7.1; J2 sync 4, D141).

`/api/library` is J2's template library; the library package's schema routes live at `/api/schemas` (D79). `/api/catalog` is a team
route over the one global library (D26): the team in `?dept=` picks the page that asks and the Artifacts shelf, which lists that team's
finished runs only (J2 sync 6, D184). `/api/run-template?id=` is one run template, with `enabled` from the team's settings (D183)."""
from fastapi import APIRouter

from .ctx import add_get

__all__ = ["ROUTES", "add_routes"]

ROUTES = (("/api/library", "library"), ("/api/library/{artifact}/{section}/{slug}/{version}", "library_item"),
          ("/api/run-template", "run_template"), ("/api/run-templates", "run_templates"), ("/api/catalog", "catalog"))


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        add_get(router, services, dept_dep, path, name)
