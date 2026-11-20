"""The Ask mode of the direct chat (DV-1, flag SUTRA_ASK_V1, decisions D350 to D353): a read-only answer about the owner's folder whose sources code checks.

    POST /api/chats/{sid}/direct  {text, mode: "ask"}         the same route, the same turn, held to read access, with a card of sources after the answer
    POST /api/chats/{sid}/direct/retry  {message_id, mode: "ask"}

`mode` is "ask" or "do" ("do" is the chat as it was: the same as no mode). With the flag off the word `mode` does not exist: the request models are closed, so a body that names it
is refused as an unknown field, exactly as before this package, and nothing here reads the body at all (`AskRoute` looks at the flag first). With the flag on the route class takes
`mode` out of the body before the request model sees it, remembers it for the route (`requested`), and the route does the rest. A body without `mode` is untouched, byte for byte.

What an Ask turn is, and where each part is held:
  * read only: the turn's tag asks for `workspace: read`, and the router (`Router._chat_turn`) never gives such a turn more than the owner's folder with the file tools that look, even when
    Settings, Working folder lets the team change files. For Claude that is exactly four tools (Read, Glob, Grep, LS): no write tool, no command and no web tool is offered to it.
    Codex has no tool list: its sandbox is read-only (no write, no network) and its shell may still run commands that only read, anywhere on the disk; the same holds for the file
    tools of Claude, which are not confined to the folder (D350). With no folder the sandbox is read-only too. The grounding says so (`chat_ground.ground(ask=True)`).
  * limited as a function's question is (`agent_ask`: 2 calls, $0.25, 120 s), through the turn's own `Allowance`: the calls and the deadline hold for both providers (a gate before every
    process, and the turn's timeout is cut to the deadline). The dollars are a real ceiling for Claude only (the remaining budget goes to the process as `--max-budget-usd`);
    Codex has no such flag, so for it $0.25 is a check before each process, not a cap inside one. The owner's monthly limit and plan window do not hold a direct chat back, and they
    do not hold an Ask back: the read-only way is never refused while the writing way works (D350).
  * scrubbed: the owner's line and the grounding go through the same secret scrub as every direct chat; what is written on the card goes through it too.
  * the sources: after the answer, ONE card (`AnswerCard`, a message of kind `card`) stored in the same transaction as the answer. Its labels come from `citations.check_answer` and from
    nothing a model wrote. A turn that was stopped or failed has no card: nothing was claimed. The card proves the citation (the file, the lines, the quoted words), never the claim:
    a model can paraphrase what it read wrongly and still cite it.
  * the mode is stored with the owner's line (`mode: "ask"` in its meta), so a Retry stays an Ask whatever the page says (`retry_mode`): a grant only narrows.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.egress import scan
from sutra_app.connectors.models import Allowance, CallTag
from sutra_app.library.types import clip, violation
from sutra_app.orchestrator import citations
from sutra_app.orchestrator.agent_ask import ASK_MAX_CALLS, ASK_MAX_USD, ASK_TIMEOUT_S
from sutra_app.orchestrator.direct_turns import CardEnding, Ending, ref_of
from sutra_app.orchestrator.errors import AppError, validation_error
from sutra_app.orchestrator.models import AnswerCard, AnswerSource

__all__ = ["AskRoute", "AskTurn", "begin", "requested", "retry_mode", "failure_words", "LIMIT_WORDS", "ask_on", "MODES", "MODE_KEY", "MODE_WORDS", "ASK_MAX_CALLS", "ASK_MAX_USD", "ASK_TIMEOUT_S"]

log = logging.getLogger(__name__)
MODES = ("ask", "do")
MODE_KEY = "sutra.ask_mode"                       # the request scope's key for the mode the route class took out of the body
MODE_WORDS = "mode is ask or do"
QUESTION_CHARS = 500


def ask_on(services: Any) -> bool:
    """The flag, read from the app's settings; a `Services` without settings (a test's stand-in) is off."""
    return getattr(getattr(services, "settings", None), "ask_v1", False) is True


# ---- the request ------------------------------------------------------------------------------------------------------------------

class AskRoute(APIRoute):
    """The route class of the two direct-chat routes. With the flag off it does nothing at all. With the flag on, a JSON body that names `mode` has it taken out before the request model is
    checked (the model stays closed and unchanged) and kept for `requested`; a body without it goes through untouched. The token is still checked first by the route itself, and the
    value of `mode` is checked by `requested` after it, so a request without the token learns nothing from the shape of its body."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            services = getattr(request.app.state, "services", None)
            if ask_on(services):
                request = await _take_mode(request)
            return await original(request)

        return handler


async def _take_mode(request: Request) -> Request:
    raw = await request.body()
    try:
        doc = json.loads(raw)
    except (ValueError, RecursionError):
        return request                                 # not JSON (or nested past what the parser takes): the route's own refusal says so
    if not isinstance(doc, dict) or "mode" not in doc:
        return request
    mode = doc.pop("mode")
    request.scope[MODE_KEY] = mode
    changed = Request(request.scope, request.receive)
    # what the request model reads; the closed model never sees `mode`. ASCII with escapes, so that a lone surrogate the owner's client wrote (`\ud800`) is carried on as it came
    # and refused by the model's own check, instead of failing to encode here: this runs before the token is looked at, so it must never fail
    changed._body = json.dumps(doc, ensure_ascii=True).encode("ascii")
    return changed


def requested(request: Request) -> str | None:
    """The mode the request named (`ask`, `do`), or None when it named none or the flag is off. Any other value is a 422 that says what the modes are."""
    if MODE_KEY not in request.scope:
        return None
    found = request.scope[MODE_KEY]
    if not isinstance(found, str) or found not in MODES:
        raise validation_error([violation("mode", "enum", MODE_WORDS)], MODE_WORDS)
    return found


LIMIT_WORDS = "Sutra stopped this answer: it reached the limit for one question (2 tries, about $0.25 or 2 minutes). Ask again, or ask something smaller."


def failure_words(exc: BaseException) -> str:
    """The sentence for the owner when an Ask turn is stopped by its own limits, instead of the connector's developer words ("the envelope allows ..."); "" for any other failure."""
    from sutra_app.connectors.errors import EnvelopeExceededError
    return LIMIT_WORDS if isinstance(exc, EnvelopeExceededError) else ""


def retry_mode(stored: str | None, named: str | None) -> str | None:
    """The mode a Retry runs in, from the mode stored with the owner's line (`ask` or None) and the one the body named (`ask`, `do` or None). A grant can only narrow: a line that was an Ask is
    retried as an Ask, with no body mode or with `ask`, and a body that names `do` for it is refused; a line that was not an Ask is an Ask only when the body says so."""
    if stored == "ask":
        if named == "do":
            raise AppError("validation", "That question was asked read only (Ask), so it can only be asked again that way.")
        return "ask"
    return "ask" if named == "ask" else None


# ---- one Ask turn -----------------------------------------------------------------------------------------------------------------

@dataclass
class AskTurn:
    """What an Ask turn carries from the start of the turn to its end: the folder the sources are checked in (read when the turn started), the owner's question, the limits, the scrub."""
    folder: str
    question: str
    allowance: Allowance
    scrub: Callable[[str], str]

    def turn_in(self, text: str, attachments: list) -> ChatTurnIn:
        """The turn as the chat port takes it: `workspace: read` (the router caps the folder at read), and the limits of a function's question."""
        return ChatTurnIn(text=text, attachments=attachments, tag=CallTag(workspace="read"), allowance=self.allowance)

    @staticmethod
    def tried(blocks: Any) -> int:
        """How many tool calls of the turn were of kind edit or web (`tool_kinds`, as the blocks already say): Ask does not allow them, and a turn that made one says so on its card.
        A `run` is not counted: Codex reads files through its read-only shell, which is its normal way of looking."""
        return sum(1 for b in (blocks if isinstance(blocks, list) else []) if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("kind") in ("edit", "web"))

    def card(self, answer: str, blocks: Any = None) -> dict[str, Any]:
        """The card of `answer`: every mark checked in the folder by code, scrubbed, as the wire shape. No mark makes an empty list: the card says so."""
        report = citations.check_answer(answer, self.folder)
        sources = [AnswerSource(
            path=clip(self.scrub(s.path), 300) or "?", start=s.start, end=s.end, quote=clip(self.scrub(s.quote), 1000) if s.quote else None,
            label=s.label, how=s.how or None, reason=s.reason) for s in report.sources]
        card = AnswerCard(type="answer_sources", question=clip(self.question, QUESTION_CHARS), sources=sources, checked=report.checked, missing=report.missing,
                          more=report.more, tried=self.tried(blocks))
        return card.model_dump(mode="json")

    def with_card(self, endings: list[Ending], user_id: int, attempt: int, answer: str, blocks: Any = None) -> list[Ending]:
        """The endings of a finished turn and, after them, the card of its answer. A card that cannot be made is logged and left out: it never fails an answer."""
        try:
            card = self.card(answer, blocks)
            return [*endings, CardEnding(src_ref=ref_of(user_id, "sources", attempt), card=card)]
        except Exception:                                  # noqa: BLE001  (a bug in the check must not cost the owner the answer)
            log.exception("the sources of the answer to line %s could not be checked", user_id)
            return endings


def _router(services: Any, port: Any) -> Any:
    return getattr(services, "connector_router", None) or getattr(port, "router", None)


def _folder(router: Any) -> str:
    found = getattr(router, "chat_folder", None)
    try:
        return str(found() or "") if callable(found) else ""
    except Exception:                                      # noqa: BLE001  (no folder is an answer: every source is then "no working folder is set")
        log.warning("the working folder could not be read for an Ask turn", exc_info=True)
        return ""


def begin(services: Any, port: Any, session: Any, question: str, scrub: Callable[[str], str]) -> AskTurn:
    """Start an Ask turn: read the folder and make the turn's limits. `question` is the owner's line as stored. Reads a file (the working folder's setting), so the routes call it
    off the event loop (`run_blocking`). Nothing here refuses: the owner's monthly limit and plan window do not hold a direct chat back and do not hold an Ask back either (D350)."""
    router = _router(services, port)
    now = float(getattr(router, "_clock", time.time)())            # the deadline is in the router's own time, as agent_ask has it
    return AskTurn(folder=_folder(router), question=question, scrub=scrub,
                   allowance=Allowance(max_calls=ASK_MAX_CALLS, max_usd=ASK_MAX_USD, deadline=now + ASK_TIMEOUT_S))
