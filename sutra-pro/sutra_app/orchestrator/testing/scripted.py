"""`ScriptedConnector`: a `ConnectorPort` that answers from a list, for tests and the offline app (orchestrator 7, test doubles).

    ScriptedConnector([ {...reply...}, ConnectorFailure("timeout"), lambda call: {...}, ... ])

Each call pops the next item. A Mapping returns `(reply, 0.0, "stub")`. An exception (instance or class) is raised. A callable gets the
`Call` and returns the Mapping (or raises); it may be a coroutine function, so a test can hold a call open until it says so. A call
after the script ran out raises `ScriptExhausted`, which is an AssertionError: a test that asked for more calls than it scripted fails
loudly instead of getting an invented answer. `calls` keeps every `Call` (prompt, schema, function, step, context, tools, timeout).

`status` is what the preflight reads (default: one signed-in provider named `stub`); `set_status` changes it. With a `sink` (a callable
taking one `UsageIn`, for instance `UsageStore.record`) every call writes one stub usage row like the real router does, with the
context's session, node and atom ids, so the ledger invariants can be checked offline.
"""
import inspect
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, NamedTuple

from sutra_app.connectors.usage import UsageIn

__all__ = ["Call", "ScriptedConnector", "ScriptExhausted", "DEFAULT_STATUS"]

DEFAULT_STATUS: dict[str, dict[str, Any]] = {"stub": {"installed": True, "signed_in": True, "detail": "scripted"}}


class Call(NamedTuple):
    prompt: str
    schema: dict | None
    function: str
    step: str
    context: dict[str, str]
    tools: tuple[str, ...] = ()
    timeout: float = 120.0


class ScriptExhausted(AssertionError):
    """The script has no item left for this call."""


class ScriptedConnector:
    def __init__(self, script: Iterable[Mapping[str, Any] | BaseException | type | Callable[[Call], Any]] = (), *,
                 status: Mapping[str, Mapping[str, Any]] | None = None, sink: Callable[[UsageIn], Any] | None = None) -> None:
        self._script: deque[Any] = deque(script)
        self.calls: list[Call] = []
        self._status: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (DEFAULT_STATUS if status is None else status).items()}
        self.sink = sink

    # ---- the port --------------------------------------------------------------------------------------------------------

    @property
    def records_usage(self) -> bool:
        return self.sink is not None

    async def call_json(self, prompt: str, *, schema: dict | None = None, tools: Sequence[str] = (), timeout: float = 120.0,
                        function: str = "chat_agent", step: str = "plan",
                        context: Mapping[str, str] | None = None) -> tuple[dict, float | None, str]:
        call = Call(prompt, schema, function, step, dict(context or {}), tuple(tools), timeout)
        self.calls.append(call)
        if not self._script:
            self._usage(call, ok=False)
            raise ScriptExhausted(f"the script has no reply for call {len(self.calls)} (function {function}, step {step})")
        item = self._script.popleft()
        try:
            if isinstance(item, type) and issubclass(item, BaseException):
                raise item()
            if isinstance(item, BaseException):
                raise item
            if callable(item) and not isinstance(item, Mapping):
                item = item(call)
                if inspect.isawaitable(item):
                    item = await item
            if not isinstance(item, Mapping):
                raise TypeError(f"a script item must give a Mapping, got {type(item).__name__}")
        except BaseException:
            self._usage(call, ok=False)
            raise
        self._usage(call, ok=True)
        return dict(item), 0.0, "stub"

    def status(self) -> Mapping[str, Mapping[str, Any]]:
        return {k: dict(v) for k, v in self._status.items()}

    # ---- test helpers ------------------------------------------------------------------------------------------------------

    def set_status(self, status: Mapping[str, Mapping[str, Any]]) -> None:
        self._status = {k: dict(v) for k, v in status.items()}

    def push(self, *items: Any) -> None:
        """Add items at the end of the script."""
        self._script.extend(items)

    @property
    def remaining(self) -> int:
        return len(self._script)

    def _usage(self, call: Call, *, ok: bool) -> None:
        if self.sink is None:
            return
        ctx = call.context
        self.sink(UsageIn(
            provider="stub", model="", purpose=ctx.get("purpose") or "chat_plan", session_id=ctx.get("session_id"), node_id=ctx.get("node_id"),
            task_id=ctx.get("task_id"), fn=call.function, atom_id=ctx.get("atom_id"), usd=0.0, seconds=0.0, ok=ok,
            how="stub", call_ref=f"r:scripted-{len(self.calls)}"))
