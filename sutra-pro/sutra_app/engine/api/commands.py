"""The five POST routes, rows 26 to 30 (engine design 7.1, F3 and F9, S1-contracts-04).

`views.say`, `views.output` and `views.reset` keep J2's validation and bodies and ask a `Commands` object to act; here that
object is `DeptCommands`, which acts through the orchestrator:

    say      `deliver_to_department(dept, text, settings=page.next_settings)`; Busy is 409 `{"ok": false}`; the start page's
             output choice is cleared once a delivery created a task
    output   only while the page has no run: writes `page.json.next_settings.J2_OUTPUT`; otherwise 409 with the run's output
    reset    `stop_live(dept)`: False is 409 and touches nothing; True writes `page.json.since_run` (the latest run id)
    playbooks/clear, lessons/clear   the team's memory files (views)

Every route needs the token (`services.require_token`, a route dependency, so it runs before the team is looked up) and a
team that is not archived. Bodies are read by hand, so a body that is not a JSON object is J2's 400 `{"error": "bad json"}`.
"""
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .. import j2
from ..views import read_published
from . import ctx as ctxmod
from .ports import is_busy
from .reply import json_reply, to_response

__all__ = ["DeptCommands", "add_routes", "read_json_body"]

ROUTES = (("/api/say", "say"), ("/api/playbooks/clear", "playbooks_clear"), ("/api/lessons/clear", "lessons_clear"),
          ("/api/output", "output"), ("/api/reset", "reset"))


class DeptCommands:
    """The three commands of one team, over the server's services and the team's `page.json`."""

    def __init__(self, services, dept_id: str) -> None:
        self.services, self.dept_id = services, dept_id

    def say(self, text: str) -> bool:
        page = ctxmod.read_page(self.services.data_dir, self.dept_id)
        settings = dict(page.next_settings) or None
        try:
            delivery = self.services.deliver_to_department(self.dept_id, text, settings=settings)
        except Exception as exc:        # noqa: BLE001 - only the orchestrator's busy refusal is an answer, the rest is a bug
            if is_busy(exc):
                return False
            raise
        if settings and getattr(delivery, "delivered", None) == "follow_up":
            ctxmod.write_page(self.services.data_dir, self.dept_id, next_settings={})
        return True

    def set_output(self, out: Any) -> tuple[bool, str]:
        page = ctxmod.read_page(self.services.data_dir, self.dept_id)
        if ctxmod.current_ref(self.services, self.dept_id, page) is not None:        # a message exists: J2 refuses
            return False, self._output_of_current(page)
        kind = _output_type(out)
        ctxmod.write_page(self.services.data_dir, self.dept_id, next_settings={**page.next_settings, "J2_OUTPUT": kind})
        return True, kind

    def reset(self) -> bool:
        if not self.services.stop_live(self.dept_id):
            return False
        latest = self.services.resolve_run(None, self.dept_id)
        if latest is not None:
            ctxmod.write_page(self.services.data_dir, self.dept_id, since_run=latest.run_id)
        return True

    def _output_of_current(self, page) -> str:
        ref = ctxmod.current_ref(self.services, self.dept_id, page)
        folder = ctxmod.run_dir_of(self.services, self.dept_id, ref) if ref is not None else None
        published = read_published(folder) if folder else None
        out = (published.live.get("output") if published else None) or page.next_settings.get("J2_OUTPUT")
        return _output_type(out)


def _output_type(out: Any) -> str:
    """J2's `output_type`: a known type, anything else is the website (the process environment is not consulted)."""
    name = str(out or "").strip().lower()
    return name if name in j2.OUTPUTS else "website"


async def read_json_body(request: Request) -> Optional[dict]:
    """The JSON object of a POST; an empty body is {} (J2: `raw or b"{}"`); anything else that is not an object is None (a body nested too deeply
    to parse is one too: a 400 `bad json`, not a 500)."""
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    return body if isinstance(body, dict) else None


def add_routes(router: APIRouter, services, dept_dep) -> None:
    for path, name in ROUTES:
        def make(name=name):
            async def post(request: Request, dept: str = Depends(dept_dep)) -> Response:
                body = await read_json_body(request)
                if body is None:
                    return to_response(json_reply({"error": "bad json"}, 400), services.redact)
                return await run_in_threadpool(ctxmod.serve, services, name, request, dept,
                                               commands=DeptCommands(services, dept), body=body)
            post.__name__ = name
            return post
        router.post(path, dependencies=[Depends(services.require_token)], response_class=Response)(make())
