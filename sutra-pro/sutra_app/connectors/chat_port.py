"""`ChatPort`: the seam of chat sessions, beside `ModelPort` (absorb design 2.1 and 2.2, D107).

`ModelPort` (one-shot calls of J2's five agents) keeps its exact shape. Chats get their own port, implemented once over the Router's
session API, so every chat improvement lives below every surface. The port never writes a message: the transcript is the app's own
(`ChatStore`, D32), the port reads it through the Router's `TranscriptSource` and hands events and results back to the orchestrator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator, Optional, Protocol, Sequence, runtime_checkable

from .attachments import AttachmentStore, deliver
from .chat_models import CarryPlan, Choice, ChatEvent, ChatTurnIn, ChatTurnOut, ProviderPill
from .errors import InvalidRequestError, NoProviderError
import re

from .models import SESSION_ID_PATTERN, AskRequest, ConnectorEvent, Message, RouteContext, SessionSpec
from .health import API_KEY_REFUSED
from .router import TRANSCRIPT_LIMIT, Router
from .transcript import FULL_CHARS, TAIL_MESSAGES, render_carry_over
from .usage import load_session_state

__all__ = ["ChatPort", "RouterChatPort"]

PROVIDERS = ("claude", "codex")             # the providers a person can choose; the stub is for tests and the offline demo


@runtime_checkable
class ChatPort(Protocol):
    def providers(self, session_id: Optional[str] = None) -> list[ProviderPill]: ...
    def choose(self, session_id: str, provider: Optional[str], model: Optional[str] = None) -> Choice: ...
    def plan_switch(self, session_id: str, target: str) -> CarryPlan: ...
    def send(self, session_id: str, turn: ChatTurnIn, on_event: Optional[Callable[[ChatEvent], None]] = None) -> ChatTurnOut: ...
    def stream(self, session_id: str, turn: ChatTurnIn) -> Iterator[ChatEvent]: ...
    def stop(self, session_id: str) -> bool: ...
    def close(self) -> None: ...


class RouterChatPort:
    def __init__(self, router: Router, *, ctx: Optional[RouteContext] = None, attachments: Optional[AttachmentStore] = None) -> None:
        self.router = router
        self.attachments = attachments
        self._ctx = ctx or RouteContext()

    # ---- the pill -----------------------------------------------------------------------------------------------------------------
    def _work_dir(self, session_id: str) -> Path:
        if re.fullmatch(SESSION_ID_PATTERN, session_id or "") is None:
            raise InvalidRequestError("session_id must be 1 to 64 characters of letters, digits, '_' or '-'")
        connectors = self.router.connectors
        if not connectors:
            raise NoProviderError("no connector is configured")
        return Path(next(iter(connectors.values())).cfg.resolved_work_root()).resolve() / session_id

    def _why_not(self, name: str) -> str:
        status = self.router.provider_summary(name)
        entry = self.router.policy.providers.get(name)      # type: ignore[call-overload]
        if entry is None:
            return "not in the routing policy"
        if not entry.enabled:
            return "disabled in the routing policy"
        if not status.installed:
            return "CLI not found on PATH"
        if status.signed_in is False:
            return "not signed in"
        if status.billing == "api_key":
            return API_KEY_REFUSED
        if status.health.state in ("cooldown", "breaker", "quota"):
            return status.health.reason or "cooling down after an error"
        return ""

    def providers(self, session_id: Optional[str] = None) -> list[ProviderPill]:
        """The providers a person can choose, each with the reason when it cannot run. The chosen one (pinned for this session) is marked."""
        chosen = self._chosen(session_id) if session_id else None
        pills = []
        for name in PROVIDERS:
            if name not in self.router.connectors:
                continue
            status = self.router.provider_summary(name, models=True)
            why = self._why_not(name)
            slugs = [m.slug for m in status.models]
            pills.append(ProviderPill(name=name, ready=not why, why_not=why, model=self.router.policy.model_for(name),    # type: ignore[arg-type]
                                      models=slugs, plan=status.plan, billing=status.billing, chosen=name == chosen))
        return pills

    def _chosen(self, session_id: str) -> Optional[str]:
        stored = load_session_state(self._work_dir(session_id))
        if stored is not None and stored.pinned is not None:
            return stored.pinned
        return self.router._pins.get(session_id)          # the in-memory pin, until ABS-6 persists the choice

    def choose(self, session_id: str, provider: Optional[str], model: Optional[str] = None) -> Choice:
        """Pins the provider for THIS session; `None` clears it. The policy default is never touched."""
        if provider is not None:
            pill = next((p for p in self.providers() if p.name == provider), None)
            if pill is None:
                raise InvalidRequestError(f"{provider} is not a provider you can choose")
            if not pill.ready:
                raise InvalidRequestError(f"{provider} cannot run: {pill.why_not}", detail={"why_not": pill.why_not})
        if model is not None and provider is not None and load_session_state(self._work_dir(session_id)) is None:
            self.router.chat_start(SessionSpec(session_id=session_id, provider=provider, model=model), self._ctx)
        self.router.chat_pin(session_id, provider)
        stored = load_session_state(self._work_dir(session_id))
        return Choice(session_id=session_id, provider=provider, model=stored.model if stored is not None and provider else None)

    # ---- the dry run ----------------------------------------------------------------------------------------------------------------
    def _history(self, session_id: str) -> Sequence[Message]:
        source = self.router.transcripts
        return [] if source is None else list(source.messages(session_id, TRANSCRIPT_LIMIT))

    def plan_switch(self, session_id: str, target: str) -> CarryPlan:
        """What a switch to `target` would carry. Reads the stored state and transcript; starts no process and writes nothing."""
        if target not in PROVIDERS or target not in self.router.connectors:
            raise InvalidRequestError(f"{target} is not a configured provider")
        stored = load_session_state(self._work_dir(session_id))
        source = stored.provider if stored is not None else None
        messages = self._history(session_id)
        text = render_carry_over(messages, from_provider=source, to_provider=target)      # type: ignore[arg-type]
        if not messages:
            return CarryPlan(session_id=session_id, target=target, source=source)           # type: ignore[arg-type]
        full = len("\n".join(f"{m.role}: {m.text}" for m in messages)) <= FULL_CHARS or len(messages) <= TAIL_MESSAGES
        omitted = 0 if full else len(messages) - TAIL_MESSAGES
        return CarryPlan(session_id=session_id, target=target, source=source, tier="full" if full else "digest",    # type: ignore[arg-type]
                         chars=len(text), kept_messages=len(messages) - omitted if full else TAIL_MESSAGES, omitted=omitted)

    # ---- a turn ---------------------------------------------------------------------------------------------------------------------
    def _message(self, session_id: str, turn: ChatTurnIn) -> Message:
        if not turn.attachments:
            return Message(role="user", text=turn.text)
        if self.attachments is None:
            raise InvalidRequestError("attachments are not available here", detail={"names": [a.name for a in turn.attachments]})
        provider = self._chosen(session_id) or self.router.plan(AskRequest(user="chat", ctx=self._ctx_for(session_id, turn))).order[0]
        d = deliver(self.attachments, turn.attachments, provider)
        return Message(role="user", text=turn.text + d.text, images=list(d.images))

    def _ctx_for(self, session_id: str, turn: ChatTurnIn) -> RouteContext:
        return self._ctx.model_copy(update={"session_id": session_id, "tag": turn.tag})

    def stream(self, session_id: str, turn: ChatTurnIn) -> Iterator[ChatEvent]:
        """partial* / block* / usage / switched? / turn_done. The last event is always `turn_done` (errors raise while iterating)."""
        message = self._message(session_id, turn)
        before = load_session_state(self._work_dir(session_id))
        saw_partial = False
        blocks: list[dict] = []
        for event in self.router.chat_stream(session_id, message, self._ctx_for(session_id, turn)):
            out = self._map(event, saw_partial)
            if event.kind == "text_delta" and event.data.get("kind", "text") == "text":
                saw_partial = True
            if out is None:
                continue
            if out.kind == "block":
                blocks.append(out.data)
            if out.kind == "turn_done":
                result = event.data["result"]
                after = load_session_state(self._work_dir(session_id))
                moved = before is not None and after is not None and before.provider != after.provider
                switched = {"from": before.provider, "to": after.provider,           # type: ignore[union-attr]
                            "plan": self.plan_switch(session_id, after.provider).model_dump()} if moved and after else None
                yield ChatEvent(kind="usage", data={"usd": result.get("usd"), "usage": result.get("usage")})
                if switched is not None:
                    yield ChatEvent(kind="switched", data=switched)
                yield ChatEvent(kind="turn_done", data={
                    "text": result["text"], "provider": result["provider"], "model": result.get("model"), "usd": result.get("usd"),
                    "blocks": blocks, "switched": switched})
                return
            yield out

    @staticmethod
    def _map(event: ConnectorEvent, saw_partial: bool) -> Optional[ChatEvent]:
        if event.kind == "text_delta":
            return ChatEvent(kind="partial", data={"delta": event.data.get("text", "")}) if event.data.get("kind", "text") == "text" else None
        if event.kind == "text":
            return None if saw_partial else ChatEvent(kind="block", data={"type": "text", "kind": "other", "text": event.data.get("text", "")})
        if event.kind == "tool_call":
            return ChatEvent(kind="block", data={"type": "tool_use", "kind": "other", "name": str(event.data.get("name") or event.data.get("type") or ""),
                                                  "text": ""})
        if event.kind == "tool_result":
            return ChatEvent(kind="block", data={"type": "tool_result", "kind": "other", "name": "", "text": ""})
        if event.kind == "turn_done":
            return ChatEvent(kind="turn_done")
        return None

    def send(self, session_id: str, turn: ChatTurnIn, on_event: Optional[Callable[[ChatEvent], None]] = None) -> ChatTurnOut:
        done: Optional[ChatEvent] = None
        for event in self.stream(session_id, turn):
            if event.kind == "turn_done":
                done = event
            elif on_event is not None:
                on_event(event)
        assert done is not None
        d = done.data
        return ChatTurnOut(text=d["text"], provider=d["provider"], model=d.get("model"), usd=d.get("usd"), blocks=d["blocks"], switched=d["switched"])

    def stop(self, session_id: str) -> bool:
        return self.router.chat_stop(session_id)

    def close(self) -> None:
        self.router.close()
