"""The six POST routes, rows 26 to 30 and J2's `/api/ask` (engine design 7.1, F3 and F9, S1-contracts-04; J2 sync 4, D147).

`views.say`, `views.ask`, `views.output` and `views.reset` keep J2's validation and bodies and ask a `Commands` object to act; here
that object is `DeptCommands`, which acts through the orchestrator:

    say      `deliver_to_department(dept, text, settings=page.next_settings)`; Busy is 409 `{"ok": false}`; the start page's
             output choice is cleared once a delivery created a task
    ask      a question to one function about a run: J2's `j2_agent.answer`, asked of the function's own chat session when the
             orchestrator offers a turn for it (`services.agent_chat`, optional: `ports.AgentChatTurn`), else from the run's records
    output   only while the page has no run: writes `page.json.next_settings.J2_OUTPUT` (`auto`, or any registered output: D129); otherwise 409 with the run's output
    reset    `stop_live(dept)`: False is 409 and touches nothing; True writes `page.json.since_run` (the latest run id)
    playbooks/clear, lessons/clear   the team's memory files (views)

Every route needs the token (`services.require_token`, a route dependency, so it runs before the team is looked up) and a
team that is not archived. Bodies are read by hand, so a body that is not a JSON object is J2's 400 `{"error": "bad json"}`.
"""
import json
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .. import j2, j2_agent
from ..views import AskBusy, read_published
from . import ctx as ctxmod
from .ports import AskFailed, is_busy
from .reply import json_reply, to_response

__all__ = ["DeptCommands", "add_routes", "read_json_body"]

ROUTES = (("/api/say", "say"), ("/api/ask", "ask"), ("/api/playbooks/clear", "playbooks_clear"),
          ("/api/lessons/clear", "lessons_clear"), ("/api/output", "output"), ("/api/reset", "reset"))


class DeptCommands:
    """The commands of one team, over the server's services and the team's `page.json`."""

    def __init__(self, services, dept_id: str) -> None:
        self.services, self.dept_id = services, dept_id

    def ask(self, who: str, question: Any, run_id: str) -> dict:
        """J2's answer `{who, answer, from}` to a question about a run (D147 to D149), plus, when the function's own chat took part,
        `session_id`, `question_id`, `answer_id` and, when the answer is from the records for a reason the owner should read, `note`.

        The run is the one named when it is a run of this team, else the run the page shows. When the orchestrator offers a turn for
        the function (`services.agent_chat`: it has a chat session of its own for that run) the question and the answer are lines
        of that session and the model answer is a call of it. Without a turn (a fake, the validator, a function that never worked in
        the run, an empty question) nothing is stored and no model is called: `answer(..., ask=None)` reads the records. A model
        that cannot answer (`AskFailed`) or a turn that cannot ask (offline, the owner's limit) gives the records' answer with the
        reason in `note`. `AskBusy` (409) when the session is answering another question."""
        q = " ".join(str(question or "").split())
        ref = self._ask_ref(run_id)
        folder = ctxmod.run_dir_of(self.services, self.dept_id, ref) if ref is not None else None
        make = getattr(self.services, "agent_chat", None)
        turn = make(self.dept_id, ref.run_id, who) if make is not None and ref is not None and q else None
        if turn is None:
            return j2_agent.answer(folder, who, q, ask=None)
        try:
            turn.begin(q)
        except Exception as exc:        # noqa: BLE001 - only the orchestrator's busy refusal is an answer, the rest is a bug
            if is_busy(exc):
                raise AskBusy(str(exc)) from exc
            raise
        got: Optional[dict] = None
        try:
            got = self._answer(folder, who, q, turn)
        finally:                        # the busy mark is released on every path; an unexpected error stores no answer and goes on as a 500
            stored = turn.end(None if got is None else got["answer"], "records" if got is None else got["from"])
        return {**got, **(stored or {})}

    @staticmethod
    def _answer(folder: Optional[str], who: str, q: str, turn) -> dict:
        if not turn.can_ask:
            got = j2_agent.answer(folder, who, q, ask=None)
            if turn.reason:
                got["note"] = turn.reason
            return got
        try:
            return j2_agent.answer(folder, who, q, ask=turn.ask)
        except AskFailed as exc:
            got = j2_agent.answer(folder, who, q, ask=None)
            got["note"] = f"The model could not answer ({exc.reason}); this is from the records only."
            return got

    def _ask_ref(self, run_id: str):
        """The run a question is about: the run it names when that is a run of this team, else the run the page shows (or None)."""
        if run_id and re.fullmatch(ctxmod.RUN_PARAM_RE, run_id):
            ref = self.services.resolve_run(run_id, self.dept_id)
            if ref is not None and getattr(ref, "dept_id", self.dept_id) == self.dept_id and ref.run_id == run_id:
                return ref
        return ctxmod.current_ref(self.services, self.dept_id)

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
    """J2's `output_type` and the one the engine adds: `auto` (the engine picks the output for the brief when the run starts, D129) or any
    registered output; anything else is the website (the process environment is not consulted). `j2.output_type` alone would turn `auto`
    into the website."""
    name = str(out or "").strip().lower()
    return name if name == "auto" or name in j2.OUTPUTS else "website"


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
