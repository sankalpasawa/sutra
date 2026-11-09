"""The model seam between the engine and the connector layer (engine design 4.1, D17).

Everything the engine asks of a model is a `CompletionRequest` with a `CallTag`; everything it gets back is a
`CompletionResult`. The engine calls `ModelPort.complete`; the connector section provides the real port
(`connectors/engine_port.py:make_port(spec: PortSpec, *, usage_sink=...)`), and `llm.ScriptedPort` is J2's mock mode as the
same interface. This module is imported by the connector layer, so it imports nothing from the rest of the app and
`PortSpec` and `Allowance` live here, not in `spec.py` (S1-contracts-02). The router retries once and falls back across
providers before it raises; the engine never retries a failed call itself (D19).
"""
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CallTag", "Allowance", "PortSpec", "CompletionRequest", "CompletionResult", "PortInfo", "PreflightResult",
    "ModelPort", "UsageRecorder", "ModelError", "NoModelAvailable", "CliMissing", "NotSignedIn", "QuotaExhausted",
    "ModelTimeout", "StructuredOutputFailed", "PURPOSE_PATTERN",
]

PURPOSE_PATTERN = r"^[a-z_]{1,24}$"   # an open string, not a Literal (S1-contracts-07)


class CallTag(BaseModel):
    """Who a model call is for. Frozen: `llm.tagged` builds a new tag for each nested block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = ""
    dept_id: str = ""
    task_id: Optional[str] = None
    # identity|adaptation|priority|coordination|audit|validator|"W-<n>"|reviewer|summariser|template|chat_agent
    function: str = ""
    role: Optional[str] = None            # planner | judge | builder (inside a function)
    stage: Optional[str] = None           # website|prd|hld|lld|send_email|... (J2Run.stage_kind or the output)
    step: int = Field(0, ge=0)            # the J2 step number 1..8 = J2.a..J2.h, 0 when unknown (never ORCH's string step)
    cycle: int = Field(0, ge=0)
    call_no: int = Field(0, ge=0)         # the "id" of the call in calls.jsonl, 0 for a call J2 does not log
    # The atom this call is charged to: a builder's own J2 id (an explicit tag wins), else the function atom bound with
    # `llm.bind_atom`, else the run overhead key (S4-fnodes-07).
    atom: Optional[str] = None
    # agent_turn, summary, template, review, plan, judge, change, chat_plan, chat; the policy matches it exactly
    purpose: str = Field("agent_turn", pattern=PURPOSE_PATTERN)
    # The most this call may do in the owner's working folder (D127): "none" (no folder), "read" (look at files) or "edit" (also change
    # them). Set by the workspace capability; the router (`Router.folder_for`) turns it into a folder, capped by the owner's own access choice.
    workspace: Literal["none", "read", "edit"] = "none"


class Allowance(BaseModel):
    """What the caller's envelope lets ONE request spend. Closed. The engine sends none in v1: `J2Run` keeps its own
    envelope (credits, model-call and retry counts) and the router applies only its own ceiling (S1-contracts-06)."""

    model_config = ConfigDict(extra="forbid")

    max_calls: Optional[int] = Field(None, ge=0)
    max_usd: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    deadline: Optional[float] = Field(None, allow_inf_nan=False)    # epoch seconds
    envelope_id: Optional[str] = None


class PortSpec(BaseModel):
    """What `make_port` receives (the host builds it from the task). Frozen and closed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mock: bool
    connector: Literal["auto", "claude", "codex", "stub"] = "auto"
    run_id: str
    dept_id: str
    task_id: Optional[str] = None
    data_dir: str


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    system: str
    user: str
    max_tokens: int = Field(1500, ge=1)
    effort: Literal["low", "high"] = "high"
    json_mode: bool = False
    images: list[str] = []                        # PNG paths that exist (llm.ask drops the others)
    json_schema: Optional[dict] = None            # draft-07, advisory: connectors enforce when they can; the engine validates
    timeout_s: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    tag: CallTag = CallTag()
    allowance: Optional[Allowance] = None         # the engine sends None (S1-contracts-02, S1-contracts-06)
    scripted: Optional[Callable[[], str]] = Field(None, exclude=True)   # J2's `mock`; only the stub path calls it


class CompletionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    model: Optional[str] = None
    provider: Optional[str] = None                # claude | codex | stub
    input_tokens: Optional[int] = None            # input_total: cache reads and writes counted, as J2's llm._cli_meta did
    output_tokens: Optional[int] = None
    usd: Optional[float] = None
    duration_ms: Optional[int] = None
    session_id: Optional[str] = None
    structured: Optional[dict] = None             # {"provider", "subtype", "present"} when json_schema was sent
    note: Optional[str] = None                    # e.g. "claude out of quota, answered by codex"
    detail: Optional[dict] = None                 # = UsageIn.detail; copied into calls.jsonl, never read by J2 code


class PortInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Optional[str]
    model: Optional[str]
    mock: bool


class PreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    message: str
    providers: list[dict]                         # name, installed, signed_in, detail


@runtime_checkable
class ModelPort(Protocol):
    def describe(self) -> PortInfo: ...

    def preflight(self) -> PreflightResult: ...

    def complete(self, req: CompletionRequest, on_progress: Optional[Callable[[dict], None]] = None) -> CompletionResult: ...

    def close(self) -> None: ...                  # kills child CLIs


@runtime_checkable
class UsageRecorder(Protocol):
    """What a port hands each usage row to: `connectors.usage.UsageSink` and `events.EventUsageSink` both fit. The row is
    a `UsageIn` or a plain mapping with the same keys; `record` returns a local counter."""

    def record(self, row: Any) -> int: ...


class ModelError(RuntimeError):
    """Every failure of a model call. A RuntimeError, so J2's `except RuntimeError` and its crash path keep working (D19)."""

    code = "model_error"
    retryable = False


class NoModelAvailable(ModelError):
    code = "no_model"


class CliMissing(ModelError):
    code = "cli_missing"


class NotSignedIn(ModelError):
    code = "not_signed_in"


class QuotaExhausted(ModelError):
    code = "quota"


class ModelTimeout(ModelError):
    code = "timeout"
    retryable = True


class StructuredOutputFailed(ModelError):
    code = "structured"
