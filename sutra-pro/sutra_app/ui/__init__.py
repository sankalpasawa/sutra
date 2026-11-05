"""The UI package: the only server of HTML pages and static files (D72, S3-web-01).

`mount(app, services)` is the plug-in call of the orchestrator's `create_app` (it runs last, after the engine and
the connectors). The department lookup is `Services.department`, the one lookup for every plug-in (S3-web-02); there is
no `sutra_app.web` alias and no second boot injector.
"""
from __future__ import annotations

from fastapi import FastAPI

from .boot import BootContext, BootMarkerError, DeptLike, csp_header, inline_script_hashes, render_page
from .routes import PAGES_DIR, STATIC_DIR, build_router, mount_static

__all__ = [
    "PAGES_DIR",
    "STATIC_DIR",
    "BootContext",
    "BootMarkerError",
    "DeptLike",
    "build_router",
    "csp_header",
    "inline_script_hashes",
    "mount",
    "mount_static",
    "render_page",
]

_MOUNTED = "sutra_ui_mounted"


def mount(app: FastAPI, services) -> None:
    """Add the pages and the `/ui` static files to `app`. Reads exactly three members of `services`:
    `settings.token`, `version` and `department`. A second call adds nothing."""
    if getattr(app.state, _MOUNTED, False):
        return
    router = build_router(
        token=services.settings.token,
        department=services.department,
        version=services.version,
        pages_dir=PAGES_DIR,
    )
    app.include_router(router)
    mount_static(app, STATIC_DIR)
    setattr(app.state, _MOUNTED, True)
