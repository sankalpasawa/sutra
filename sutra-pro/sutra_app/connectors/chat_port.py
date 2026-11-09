"""`ChatPort`: the seam of chat sessions, beside `ModelPort` (absorb design 2.1 and 2.2, D107).

`ModelPort` (one-shot calls of J2's five agents) keeps its exact shape. Chats get their own port, implemented once over the Router's
session API, so every chat improvement lives below every surface. The port never writes a message: the transcript is the app's own
(`ChatStore`, D32), the port reads it through the Router's `TranscriptSource` and hands events and results back to the orchestrator.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable, Iterator, Optional, Protocol, Sequence, runtime_checkable

from sutra_app import oslayer

from .attachments import AttachmentStore, deliver
from .base import write_private_file
from .chat_models import CarryPlan, Choice, ChatEvent, ChatTurnIn, ChatTurnOut, ProviderPill
from .errors import InvalidRequestError, NoProviderError
import re

from .models import SESSION_ID_PATTERN, AskRequest, ConnectorEvent, Message, Pick, RouteContext, SessionSpec
from .health import API_KEY_REFUSED
from .model_catalog import ModelOption, efforts_of, names_of, options_for
from .router import TRANSCRIPT_LIMIT, Router
from .tool_kinds import classify, title_of
from .transcript import FULL_CHARS, TAIL_MESSAGES, render_carry_over
from .usage import load_session_state, save_session_state

__all__ = ["ChatPort", "RouterChatPort"]

PROVIDERS = ("claude", "codex")             # the providers a person can choose; the stub is for tests and the offline demo


@runtime_checkable
class ChatPort(Protocol):
    def providers(self, session_id: Optional[str] = None) -> list[ProviderPill]: ...
    def choose(self, session_id: str, provider: Optional[str], model: Optional[str] = None, effort: Optional[str] = None) -> Choice: ...
    def check_choice(self, provider: Optional[str], model: Optional[str] = None, effort: Optional[str] = None) -> Choice: ...
    def default_pick(self, function: str = "") -> Pick: ...
    def plan_switch(self, session_id: str, target: str) -> CarryPlan: ...
    def send(self, session_id: str, turn: ChatTurnIn, on_event: Optional[Callable[[ChatEvent], None]] = None) -> ChatTurnOut: ...
    def stream(self, session_id: str, turn: ChatTurnIn) -> Iterator[ChatEvent]: ...
    def set_system(self, session_id: str, text: str) -> None: ...
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
            return status.detail or "CLI not found on PATH"          # the router's words: Claude Desktop is not Claude Code (GAP-providers)
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
        stored = load_session_state(self._work_dir(session_id)) if session_id else None
        pills = []
        for name in PROVIDERS:
            if name not in self.router.connectors:
                continue
            status = self.router.provider_summary(name, models=True)
            why = self._why_not(name)
            slugs = [m.slug for m in status.models]
            live = stored is not None and stored.provider == name         # this chat's session runs on this provider: its model and effort are known
            pills.append(ProviderPill(name=name, ready=not why, why_not=why, model=self.router.policy.model_for(name),    # type: ignore[arg-type]
                                      models=slugs, plan=status.plan, billing=status.billing, chosen=name == chosen, quota=status.quota,
                                      model_options=self._options(name), chat_model=stored.model if live else None,     # type: ignore[union-attr]
                                      chat_effort=stored.effort if live else None, can_pick=stored is None or live))                  # type: ignore[union-attr]
        return pills

    def _chosen(self, session_id: str) -> Optional[str]:
        stored = load_session_state(self._work_dir(session_id))
        if stored is not None and stored.pinned is not None:
            return stored.pinned
        return self.router._pins.get(session_id)          # the in-memory pin, until ABS-6 persists the choice

    def _options(self, provider: str) -> list[ModelOption]:
        return options_for(provider, self.router.connectors[provider])

    def _check_choice(self, provider: str, model: Optional[str], effort: Optional[str], current: Optional[str]) -> None:
        """A model the provider does not offer, or an effort the model does not accept, is refused HERE with the valid ones named: stored, it
        would fail at the next turn as `model_not_found`. A provider that cannot list its models (Codex when its CLI cannot be asked) is not
        narrowed: only the shape of the name is checked then, as before."""
        options = self._options(provider)
        if model is not None and options and model not in {o.slug for o in options}:
            raise InvalidRequestError(f"{model} is not a model {provider} offers. Choose one of: {names_of(options)}",
                                      detail={"models": [o.slug for o in options]})
        if effort is not None:
            allowed = efforts_of(options, model or current)
            if effort not in allowed:
                raise InvalidRequestError(f"{model or current or provider} does not accept the effort {effort}. Choose one of: {', '.join(allowed)}",
                                          detail={"efforts": allowed})

    def _ready(self, provider: str) -> None:
        """The provider must be one a person can choose and must be able to run now; the refusal says why (a 422 for the pill)."""
        pill = next((p for p in self.providers() if p.name == provider), None)
        if pill is None:
            raise InvalidRequestError(f"{provider} is not a provider you can choose")
        if not pill.ready:
            raise InvalidRequestError(f"{provider} cannot run: {pill.why_not}", detail={"why_not": pill.why_not})

    def check_choice(self, provider: Optional[str], model: Optional[str] = None, effort: Optional[str] = None) -> Choice:
        """The validation of a pick, pure: nothing is started, written or pinned. The provider is ready, the model is one it offers, the effort is one
        that model accepts (the valid ones are named in the refusal). `provider=None` is "Default" and takes no model or effort. This is what a function or
        step session's pill is checked with (the engine's calls are one-shot: no router session is made), and what `choose` checks before it pins."""
        if provider is None:
            if model is not None or effort is not None:
                raise InvalidRequestError("a model or an effort can be chosen only together with its provider")
            return Choice(session_id="")
        self._ready(provider)
        self._check_choice(provider, model, effort, self.router.policy.model_for(provider))      # type: ignore[arg-type]
        return Choice(session_id="", provider=provider, model=model, effort=effort)               # type: ignore[arg-type]

    def default_pick(self, function: str = "") -> Pick:
        """What an agent runs on when nobody chose: the first enabled provider of the policy's order for `function`'s agent turns, its policy model and the
        policy's effort. Nothing is asked of a CLI; an empty `Pick` when the policy names no provider a person can choose (the offline stub)."""
        try:
            resolved = self.router.policy.resolve_fields(function=function, purpose="agent_turn")
            name = next((n for n in resolved.order if n in PROVIDERS and n in self.router.connectors and self.router.policy.enabled(n)), None)    # type: ignore[arg-type]
            if name is None:
                return Pick()
            return Pick(provider=name, model=self.router.policy.model_for(name), effort=resolved.effort)         # type: ignore[arg-type]
        except Exception:                                                                       # noqa: BLE001  (a label for the page must not fail a request)
            return Pick()

    def choose(self, session_id: str, provider: Optional[str], model: Optional[str] = None, effort: Optional[str] = None) -> Choice:
        """Pins the provider for THIS session; `None` clears it. A `model` and an `effort` are per chat as well: both are checked against what
        the provider offers (a typo is refused here, not at the next turn), written to the chat's stored session state, and used from its next
        turn on. The policy default is never touched."""
        if provider is not None:
            self._ready(provider)
        if model is not None or effort is not None:
            if provider is None:
                raise InvalidRequestError("a model or an effort can be chosen only together with its provider")
            existing = load_session_state(self._work_dir(session_id))
            if existing is not None and existing.provider != provider:     # a switch starts a fresh session on the provider's policy model: never silently ignored
                what = "model" if model is not None else "effort"
                raise InvalidRequestError(f"the {what} of {provider} cannot be set while this chat runs on {existing.provider}; choose the provider first")
            self._check_choice(provider, model, effort, existing.model if existing is not None else self.router.policy.model_for(provider))      # type: ignore[arg-type]
            if existing is None:
                self.router.chat_start(SessionSpec(session_id=session_id, provider=provider, model=model, effort=effort), self._ctx)       # type: ignore[arg-type]
            else:                                                          # the chat keeps its provider session; its next turn runs on these
                changed = False
                if model is not None and existing.model != model:
                    existing.model, changed = model, True
                if effort is not None and existing.effort != effort:
                    existing.effort, changed = effort, True                # type: ignore[assignment]
                if changed:
                    save_session_state(existing)
        self.router.chat_pin(session_id, provider)
        stored = load_session_state(self._work_dir(session_id))
        return Choice(session_id=session_id, provider=provider, model=stored.model if stored is not None and provider else None,       # type: ignore[arg-type]
                      effort=stored.effort if stored is not None and provider else None)

    # ---- the dry run ----------------------------------------------------------------------------------------------------------------
    def _history(self, session_id: str) -> Sequence[Message]:
        source = self.router.transcripts
        return [] if source is None else list(source.messages(session_id, TRANSCRIPT_LIMIT))

    def _carried(self, session_id: str, message: Message) -> Sequence[Message]:
        """The history a switch caused by `message` carries: the stored transcript without the owner's new line, which is stored before the call and goes as
        the new message (the router drops it the same way, `Router._transcript`)."""
        history = self._history(session_id)
        return history[:-1] if history and history[-1].role == "user" and history[-1].text == message.text else history

    def plan_switch(self, session_id: str, target: str) -> CarryPlan:
        """What a switch to `target` would carry. Reads the stored state and transcript; starts no process and writes nothing."""
        if target not in PROVIDERS or target not in self.router.connectors:
            raise InvalidRequestError(f"{target} is not a configured provider")
        return self._plan(session_id, target, self._history(session_id))

    def _plan(self, session_id: str, target: str, messages: Sequence[Message]) -> CarryPlan:
        stored = load_session_state(self._work_dir(session_id))
        source = stored.provider if stored is not None else None
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
        """(partial | block | restart)* / usage / switched? / turn_done. The last event is always `turn_done` (errors raise while iterating).
        A `restart` marks a new attempt of this turn (the router retried): what the earlier attempt streamed is void, so the text and the blocks
        it produced are forgotten here and the caller starts again from the next event."""
        message = self._message(session_id, turn)
        before = load_session_state(self._work_dir(session_id))
        saw_partial = False
        begun = False
        blocks: list[dict] = []
        kinds: dict = {}
        for event in self.router.chat_stream(session_id, message, self._ctx_for(session_id, turn)):
            if event.kind == "started":                    # the first event of every attempt: the first one begins the turn, a later one is a retry
                if begun:
                    saw_partial = False
                    blocks.clear()
                    kinds.clear()
                    yield ChatEvent(kind="restart")
                begun = True
                continue
            out = self._map(event, saw_partial, kinds, before.provider if before is not None else "claude")
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
                            "plan": self._plan(session_id, after.provider, self._carried(session_id, message)).model_dump()} if moved and after else None
                yield ChatEvent(kind="usage", data={"usd": result.get("usd"), "usage": result.get("usage")})
                if switched is not None:
                    yield ChatEvent(kind="switched", data=switched)
                yield ChatEvent(kind="turn_done", data={
                    "text": result["text"], "provider": result["provider"], "model": result.get("model"), "usd": result.get("usd"),
                    "blocks": blocks, "switched": switched})
                return
            yield out

    def _map(self, event: ConnectorEvent, saw_partial: bool, kinds: dict, provider: str) -> Optional[ChatEvent]:
        if event.kind == "text_delta":
            return ChatEvent(kind="partial", data={"delta": event.data.get("text", "")}) if event.data.get("kind", "text") == "text" else None
        if event.kind == "text":
            return None if saw_partial else ChatEvent(kind="block", data={"type": "text", "kind": "other", "text": event.data.get("text", "")})
        if event.kind == "tool_call":
            name = str(event.data.get("name") or event.data.get("type") or "")
            kind = classify(name, event.data.get("input"), provider)
            kinds[event.data.get("id")] = (kind, name)
            return ChatEvent(kind="block", data={"type": "tool_use", "kind": kind, "name": name, "text": title_of(name, event.data.get("input"))})
        if event.kind == "tool_result":
            kind, name = kinds.get(event.data.get("tool_use_id"), ("other", ""))
            text = str(event.data.get("content") or "")
            data = {"type": "tool_result", "kind": kind, "name": name, "text": text, "is_error": bool(event.data.get("is_error"))}
            if event.data.get("truncated"):
                data["truncated"] = True            # a cut says it was cut
            return ChatEvent(kind="block", data=data)
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

    def set_system(self, session_id: str, text: str) -> None:
        """The system text of this session's next turns (the grounding of a direct chat): `<workdir>/system.txt`, mode 0600, replaced
        atomically; an empty text removes it. Claude reads the file on every turn; Codex on the first turn of a thread (a new session or a
        switch), so a resumed Codex thread keeps the text it began with. The caller scrubs the text; nothing else is written."""
        directory = self._work_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / "system.txt"
        if not text:
            target.unlink(missing_ok=True)
            return
        tmp = directory / f".system.{uuid.uuid4().hex[:8]}.tmp"
        try:
            write_private_file(tmp, text)
            oslayer.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)

    def stop(self, session_id: str) -> bool:
        return self.router.chat_stop(session_id)

    def close(self) -> None:
        self.router.close()
