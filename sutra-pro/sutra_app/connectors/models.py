"""The shared connector models (connectors design 3.1). All are closed (`extra="forbid"`).

`Allowance` is the engine's class, re-exported: `engine/port.py` holds the single definition (S1-contracts-02).
`AskRequest.schema` shadows pydantic's deprecated `BaseModel.schema()`; the design names the field `schema`, so the
class bodies are built with that one warning silenced.
"""
from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import os
from sutra_app import oslayer
import warnings
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sutra_app.engine.port import Allowance, CallTag

from .env import is_secret_name

__all__ = [
    "Provider", "Effort", "Allowance", "CallTag", "RouteContext", "Message", "AskRequest", "JsonRequest", "Usage", "Quota", "QuotaWindow",
    "TurnResult", "JsonResult", "AuthStatus", "ModelInfo", "Capabilities", "SessionSpec", "SessionState",
    "ConnectorEvent", "ConnectorConfig", "SESSION_ID_PATTERN",
]

Provider = Literal["claude", "codex", "stub"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
SESSION_ID_PATTERN = r"[A-Za-z0-9_-]{1,64}"      # it names a directory, so nothing else is allowed


def _directory_name(value: str) -> str:
    if re.fullmatch(SESSION_ID_PATTERN, value) is None:
        raise ValueError("session_id must be 1 to 64 characters of letters, digits, '_' or '-' (it names a directory)")
    return value


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Usage(M):
    """One call's tokens, in disjoint parts; `reasoning_tokens` is a subset of `output_tokens`."""

    input_tokens: int = Field(0, ge=0)
    cached_input_tokens: int = Field(0, ge=0)
    cache_write_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    reasoning_tokens: int = Field(0, ge=0)

    @property
    def input_total(self) -> int:
        """What J2 reports as `input_tokens` (llm.py:145-147): fresh + cached + cache writes."""
        return self.input_tokens + self.cached_input_tokens + self.cache_write_tokens

    @property
    def total(self) -> int:
        return self.input_total + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(**{name: getattr(self, name) + getattr(other, name) for name in Usage.model_fields})

    def __sub__(self, other: "Usage") -> "Usage":
        """Part by part, never below zero (a counter that goes backwards is the caller's rule, usage.py)."""
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(**{name: max(0, getattr(self, name) - getattr(other, name)) for name in Usage.model_fields})


class QuotaWindow(M):
    """One usage window of a plan (GAP-providers): `key` as the provider names it (five_hour, seven_day, "120_min"), `label` in words
    ("5-hour", "Weekly"), `used` a fraction (0.62 = 62 %; None when the provider sent no figure, never 0), `resets_at` epoch seconds."""

    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    label: str = Field(min_length=1, max_length=60)
    used: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    resets_at: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


class Quota(M):
    """The last quota snapshot of a provider. `window`, `used` and `resets_at` describe the window that meters the call now (the one
    the router blocks on); `windows` is every window the plan has (`quota_windows.py`). `seen_at` is when the book got it (epoch s)."""

    status: Literal["ok", "warning", "exhausted", "unknown"] = "unknown"
    window: Optional[str] = None
    used: Optional[float] = None
    resets_at: Optional[float] = None
    plan: Optional[str] = None
    source: Literal["rate_limit_event", "rollout", "error", "none"] = "none"
    windows: list[QuotaWindow] = []
    seen_at: Optional[float] = None


class Message(M):
    role: Literal["user", "assistant", "system"]
    text: str
    images: list[str] = []            # PNG paths


class RouteContext(M):
    """Who a call is for and what it may spend. `avoid` is soft: those providers are tried last."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    tag: CallTag = Field(default_factory=CallTag)
    session_id: Optional[str] = None
    node_id: Optional[str] = None
    allowance: Allowance = Field(default_factory=Allowance)
    avoid: list[Provider] = []


with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=r'Field name "schema"')

    class AskRequest(M):
        model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

        system: str = ""
        user: str
        ctx: RouteContext = Field(default_factory=RouteContext)
        kind: Literal["text", "json"] = "text"
        effort: Optional[Effort] = None
        images: list[str] = []
        schema: Optional[dict] = None
        tools: tuple[str, ...] = ()
        timeout_s: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
        partials: bool = False
        scripted: Optional[Callable[[], str]] = Field(None, exclude=True)      # J2's `mock`; only the stub calls it

    class JsonRequest(AskRequest):
        kind: Literal["json"] = "json"
        schema: Optional[type[BaseModel] | dict] = None


class TurnResult(M):
    text: str
    structured: Any = None
    provider: Provider
    model: Optional[str]
    provider_session_id: Optional[str]
    usage: Usage
    usd: Optional[float]
    usd_basis: Literal["reported", "rate_card", "unknown", "none"]
    duration_ms: Optional[int]
    quota: Optional[Quota] = None
    subtype: Optional[str] = None          # Claude result.subtype, kept for J2's structured record


class JsonResult(M):
    value: Any
    usd: Optional[float]
    how: Literal["native", "prompted", "repaired", "stub"]
    turn: TurnResult
    calls_made: int = Field(ge=0)
    usd_spent: float = Field(ge=0)

    def as_tuple(self) -> tuple[Any, Optional[float], str]:
        """The diagram's (object, usd, how); usd None means unknown (Codex without rates)."""
        return (self.value, self.usd, self.how)


class AuthStatus(M):
    provider: Provider
    installed: bool
    version: Optional[str] = None
    signed_in: Optional[bool] = None          # None: cannot tell
    method: Optional[str] = None
    billing: Literal["subscription", "api_key", "unknown"] = "unknown"
    plan: Optional[str] = None
    account: Optional[str] = Field(None, repr=False)      # PII: shown to the local user, never logged
    detail: str = ""
    checked_at: float


class ModelInfo(M):
    slug: str
    label: str
    efforts: list[Effort]
    context_window: Optional[int]
    images: bool
    listed: bool
    note: str = ""                                   # one short line for a picker (model_catalog.py); empty when the provider has none
    group: Literal["main", "more"] = "main"          # "more": behind the "More models" fold (pinned snapshots, explicit 1M spellings)


class Capabilities(M):
    native_schema: bool
    resume: bool
    images: bool
    partials: bool
    mcp: bool


class SessionSpec(M):
    session_id: str
    provider: Optional[Provider] = None
    model: Optional[str] = None
    effort: Optional[Effort] = None
    tool_profile: str = "none"
    system: str = ""

    _check_id = field_validator("session_id")(_directory_name)


class SessionState(M):
    """`<work_root>/<session_id>/session.json`: authoritative for the provider session id (S1-contracts-08)."""

    session_id: str
    provider: Provider
    provider_session_id: Optional[str]
    model: str
    effort: Effort
    tool_profile: str = "none"
    workdir: str
    turns: int = Field(0, ge=0)
    switches: int = Field(0, ge=0)
    pinned: Optional[Provider] = None
    cum_usd: float = Field(0.0, ge=0)
    cum_usage: Usage = Field(default_factory=Usage)
    created_at: float

    _check_id = field_validator("session_id")(_directory_name)


class ConnectorEvent(M):
    kind: Literal["started", "text_delta", "text", "tool_call", "tool_result", "quota", "notice", "turn_done"]
    data: dict = {}


class ConnectorConfig(M):
    """Paths and executables; tests point these at the fakes. The running app's comes from `discover.connector_config` (the CLIs where
    installers put them, the owner's chosen file, and `claude_desktop`: Claude Desktop is installed, which ships no `claude` command)."""

    data_dir: Path
    work_root: Optional[Path] = None
    claude_exe: str = "claude"
    codex_exe: str = "codex"
    gh_exe: str = "gh"
    python: str = sys.executable
    extra_env: dict[str, str] = {}
    claude_desktop: bool = False

    @field_validator("extra_env")
    @classmethod
    def _no_secret_names(cls, value: dict[str, str]) -> dict[str, str]:
        bad = sorted(name for name in value if is_secret_name(name))
        if bad:
            raise ValueError(f"extra_env may not carry credentials: {', '.join(bad)} contains KEY, TOKEN, SECRET or PASSWORD")
        return value

    def resolved_work_root(self) -> Path:
        """`work_root`, else `<tempdir>/sutra-app-<uid>/work-<key>`, `<key>` naming THIS data folder; always through realpath so Claude's
        per-directory transcript key never changes (CD9). It sits outside the repo so no repo CLAUDE.md or AGENTS.md is read.
        The key keeps two data folders of one user apart: a chat session id is fixed per data folder (`cs_org`), so one shared root
        let a second app read the first one's session.json (its pinned model, its provider conversation id)."""
        root = self.work_root or Path(tempfile.gettempdir()) / f"sutra-app-{oslayer.user_token()}" / f"work-{_folder_key(self.data_dir)}"
        return Path(os.path.realpath(root))


def _folder_key(data_dir: Path) -> str:
    """Twelve hex digits naming a data folder: its realpath (case folded where the file system is), so a link or a `..` spelling of the
    same folder gives the same key."""
    real = os.path.normcase(os.path.realpath(data_dir))
    return hashlib.sha256(real.encode("utf-8", "surrogateescape")).hexdigest()[:12]
