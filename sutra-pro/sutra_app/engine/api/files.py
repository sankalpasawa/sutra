"""Rows 13, 15 to 17 and 22 to 25, the Artifacts groups and the Simple view's pages: artifacts, code, the artifact tree and groups, one
artifact file, screenshots, downloads, sites, and `/doc/{name}` and `/view` (a file of the run as a readable page; J2 sync 4, D140).

The sites (`/site/{key}`, saved with `?run=` and live without it) and html artifacts are generated, model-written HTML: their
responses carry the sandbox Content-Security-Policy that `reply.to_response` adds (D83)."""
from fastapi import APIRouter

from .ctx import add_get

__all__ = ["ROUTES", "add_routes"]

ROUTES = (("/api/artifacts", "artifacts"), ("/api/code", "code"), ("/api/artifacts/tree", "artifacts_tree"),
          ("/api/artifacts/groups", "artifacts_groups"), ("/api/artifact", "artifact"), ("/shot/{n}", "shot"),
          ("/file/{name}", "file"), ("/doc/{name}", "doc"), ("/view", "view"), ("/site/{key}", "site"))


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        add_get(router, services, dept_dep, path, name)
