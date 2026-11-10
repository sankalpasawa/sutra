"""Rows 3, 4, 5, 20 and 21: the state, the run list, one call, the audits and the reference texts (engine design 7.1), and the
two read-only routes Run settings and the build journey use, `/api/runlist` and `/api/changes` (J2's own since sync 4: they were
patch P13 before, D140)."""
from fastapi import APIRouter

from .ctx import add_get

__all__ = ["ROUTES", "add_routes"]

ROUTES = (("/api/state", "state"), ("/api/runs", "runs"), ("/api/call", "call"), ("/api/audits", "audits"), ("/api/refs", "refs"),
          ("/api/runlist", "runlist"), ("/api/changes", "changes"))         # the last two: J2's own since sync 4


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        add_get(router, services, dept_dep, path, name)
