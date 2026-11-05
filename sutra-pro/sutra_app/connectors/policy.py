"""The routing policy (connectors design 3.6, "Policy"): a data table, not code.

    policy.default.json                     the packaged default; reproduces J2 (Claude first, Codex only as a fallback)
    <data_dir>/connectors/policy.json       an optional user file; it replaces the default only if it validates

`RoutingPolicy` is closed (`extra="forbid"`). `allow_api_key_billing` no longer exists (S1-contracts-17): an API-key login is
refused by the router with no override, so a file that still holds the key fails validation, and says why.

`resolve(req)` finds the first rule that matches the request (fnmatch on function, stage and role; exact on purpose, kind,
has_images and tools) and lays its overrides over `defaults`. Precedence for the two settings a caller can also send:

    effort     rule.effort > request.effort > defaults.effort_json (json) or effort_text (text)      J2: low / high
    timeout_s  rule.timeout_s > request.timeout_s > defaults.timeout_s

The rule wins because the policy file is the owner's explicit word; the engine sends an effort on every call, so with the
caller first the `summary` rule's `effort: low` could never apply.
"""
from __future__ import annotations

import json
import os
from sutra_app import oslayer
import tempfile
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from .errors import PolicyInvalidError
from .models import AskRequest, Effort, M, Provider

__all__ = [
    "RoutingPolicy", "ProviderPolicy", "Defaults", "Match", "Rule", "Rate", "Resolved", "PolicyLoad", "DEFAULT_POLICY_PATH",
    "REMOVED_KEYS", "parse_policy", "load_default_policy", "load_policy", "write_policy", "user_policy_path", "TOOL_PROFILES",
]

DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.default.json")
TOOL_PROFILES = ("none", "sutra", "sutra+github")
# keys that were once part of the policy and are now refused with their own message
REMOVED_KEYS = {
    "allow_api_key_billing": "allow_api_key_billing was removed (S1-contracts-17): an API-key login is always refused, "
                             "sign in with your subscription",
}
ToolProfile = Literal["none", "sutra", "sutra+github"]


def _removed_keys(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            where = f"{path}.{key}" if path else str(key)
            if key in REMOVED_KEYS:
                found.append(f"{where}: {REMOVED_KEYS[key]}")
            found.extend(_removed_keys(item, where))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_removed_keys(item, f"{path}[{index}]"))
    return found


class ProviderPolicy(M):
    enabled: bool = True
    model: str = Field(min_length=1)
    max_concurrency: int = Field(1, ge=1, le=64)
    sandbox: Optional[Literal["read-only", "workspace-write"]] = None       # Codex only; never danger-full-access


def _check_delays(value: list[float]) -> list[float]:
    if any(d < 0 or d != d or d == float("inf") for d in value):
        raise ValueError("retry_delays_s must be finite numbers of seconds, none negative")
    return value


class Defaults(M):
    order: list[Provider] = Field(min_length=1)
    effort_json: Effort = "low"          # J2 j2.py:3166: low for JSON replies, high otherwise
    effort_text: Effort = "high"
    timeout_s: float = Field(900, gt=0, allow_inf_nan=False)
    max_attempts: int = Field(2, ge=1, le=10)      # J2 `range(2)`, llm.py:156
    retry_delays_s: list[float] = Field(default_factory=lambda: [2.0, 5.0])
    repair_rounds: int = Field(2, ge=0, le=10)
    max_calls_per_request: int = Field(6, ge=1, le=100)
    fallback_on_invalid_json: bool = False
    tool_profile: ToolProfile = "none"
    idle_timeout_s: float = Field(120, gt=0, allow_inf_nan=False)

    @field_validator("retry_delays_s")
    @classmethod
    def _delays(cls, value: list[float]) -> list[float]:
        return _check_delays(value)

    @field_validator("order")
    @classmethod
    def _order_unique(cls, value: list[Provider]) -> list[Provider]:
        if len(set(value)) != len(value):
            raise ValueError("order lists a provider twice")
        return value


class Match(M):
    function: Optional[str] = Field(None, min_length=1)      # fnmatch
    stage: Optional[str] = Field(None, min_length=1)         # fnmatch
    role: Optional[str] = Field(None, min_length=1)          # fnmatch
    purpose: Optional[str] = Field(None, min_length=1)       # exact
    kind: Optional[Literal["text", "json"]] = None           # exact
    has_images: Optional[bool] = None                        # exact
    tools: Optional[list[str]] = None                        # exact, as a set: the order of the names does not matter

    def matches(self, *, function: str, stage: Optional[str], role: Optional[str], purpose: str, kind: str,
                has_images: bool, tools: Sequence[str]) -> bool:
        for pattern, value in ((self.function, function), (self.stage, stage), (self.role, role)):
            if pattern is not None and not fnmatchcase(value or "", pattern):
                return False
        if self.purpose is not None and self.purpose != purpose:
            return False
        if self.kind is not None and self.kind != kind:
            return False
        if self.has_images is not None and self.has_images != has_images:
            return False
        if self.tools is not None and sorted(self.tools) != sorted(tools):
            return False
        return True


class Rule(M):
    """`match` picks the request; every other field, when set, replaces the same field of `defaults`."""

    match: Match = Field(default_factory=Match)
    order: Optional[list[Provider]] = Field(None, min_length=1)
    effort: Optional[Effort] = None
    timeout_s: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    idle_timeout_s: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    max_attempts: Optional[int] = Field(None, ge=1, le=10)
    retry_delays_s: Optional[list[float]] = None
    repair_rounds: Optional[int] = Field(None, ge=0, le=10)
    max_calls_per_request: Optional[int] = Field(None, ge=1, le=100)
    fallback_on_invalid_json: Optional[bool] = None
    tool_profile: Optional[ToolProfile] = None

    @field_validator("order")
    @classmethod
    def _order_unique(cls, value: Optional[list[Provider]]) -> Optional[list[Provider]]:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("order lists a provider twice")
        return value

    @field_validator("retry_delays_s")
    @classmethod
    def _delays(cls, value: Optional[list[float]]) -> Optional[list[float]]:
        return None if value is None else _check_delays(value)


class Rate(M):
    """USD per million tokens. A null price means the owner did not fill it; the cost is then unknown (NULL), not zero."""

    in_per_mtok: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    cached_in_per_mtok: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    out_per_mtok: Optional[float] = Field(None, ge=0, allow_inf_nan=False)
    cache_write_per_mtok: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


class Resolved(M):
    """What one request gets from the policy: the matching rule laid over the defaults."""

    order: tuple[Provider, ...]
    effort: Effort
    timeout_s: float
    idle_timeout_s: float
    max_attempts: int
    retry_delays_s: tuple[float, ...]
    repair_rounds: int
    max_calls_per_request: int
    fallback_on_invalid_json: bool
    tool_profile: ToolProfile
    rule_index: Optional[int] = None         # which rule matched; None = defaults only

    def retry_delay(self, retry_no: int) -> float:
        """Seconds to wait before retry `retry_no` (0 = the first retry); the last delay repeats; no delays means none."""
        if not self.retry_delays_s:
            return 0.0
        return self.retry_delays_s[min(max(retry_no, 0), len(self.retry_delays_s) - 1)]


class RoutingPolicy(M):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    providers: dict[Provider, ProviderPolicy] = Field(min_length=1)
    defaults: Defaults
    rules: list[Rule] = []
    rates: dict[Provider, dict[str, Rate]] = {}

    @model_validator(mode="before")
    @classmethod
    def _refuse_removed_keys(cls, data: Any) -> Any:
        problems = _removed_keys(data)
        if problems:
            raise ValueError("; ".join(problems))
        return data

    @model_validator(mode="after")
    def _consistent(self) -> "RoutingPolicy":
        orders = [("defaults.order", self.defaults.order)] + [
            (f"rules[{i}].order", rule.order) for i, rule in enumerate(self.rules) if rule.order is not None]
        for where, order in orders:
            for name in order:
                if name != "stub" and name not in self.providers:
                    raise ValueError(f"{where} names {name!r}, which is not in providers")
        for name, provider in self.providers.items():
            if provider.sandbox is not None and name != "codex":
                raise ValueError(f"providers.{name}.sandbox: only codex has a sandbox")
        return self

    # ---- lookups ---------------------------------------------------------------------------------------------------
    def model_for(self, provider: Provider) -> Optional[str]:
        entry = self.providers.get(provider)
        return entry.model if entry is not None else None

    def enabled(self, provider: Provider) -> bool:
        entry = self.providers.get(provider)
        return bool(entry and entry.enabled)

    def max_concurrency(self, provider: Provider) -> int:
        entry = self.providers.get(provider)
        return entry.max_concurrency if entry is not None else 1

    # ---- resolve ---------------------------------------------------------------------------------------------------
    def resolve_fields(self, *, function: str = "", stage: Optional[str] = None, role: Optional[str] = None,
                       purpose: str = "agent_turn", kind: str = "text", has_images: bool = False,
                       tools: Sequence[str] = (), effort: Optional[str] = None, timeout_s: Optional[float] = None) -> Resolved:
        """First matching rule over `defaults`. `effort` and `timeout_s` are the request's own (the module doc gives the order)."""
        index: Optional[int] = None
        rule: Optional[Rule] = None
        for i, candidate in enumerate(self.rules):
            if candidate.match.matches(function=function, stage=stage, role=role, purpose=purpose, kind=kind,
                                       has_images=has_images, tools=tools):
                index, rule = i, candidate
                break
        d = self.defaults

        def pick(name: str):
            value = getattr(rule, name) if rule is not None else None
            return getattr(d, name) if value is None else value

        chosen_effort = (rule.effort if rule is not None else None) or effort or (
            d.effort_json if kind == "json" else d.effort_text)
        chosen_timeout = (rule.timeout_s if rule is not None else None) or timeout_s or d.timeout_s
        return Resolved(
            order=tuple(pick("order")), effort=chosen_effort, timeout_s=chosen_timeout, idle_timeout_s=pick("idle_timeout_s"),
            max_attempts=pick("max_attempts"), retry_delays_s=tuple(pick("retry_delays_s")),
            repair_rounds=pick("repair_rounds"), max_calls_per_request=pick("max_calls_per_request"),
            fallback_on_invalid_json=pick("fallback_on_invalid_json"), tool_profile=pick("tool_profile"), rule_index=index)

    def resolve(self, req: AskRequest) -> Resolved:
        tag = req.ctx.tag
        return self.resolve_fields(
            function=tag.function, stage=tag.stage, role=tag.role, purpose=tag.purpose, kind=req.kind,
            has_images=bool(req.images), tools=req.tools, effort=req.effort, timeout_s=req.timeout_s)

    def rate(self, provider: Provider, model: Optional[str]) -> Optional[Rate]:
        return self.rates.get(provider, {}).get(model or "")


# ---- loading -----------------------------------------------------------------------------------------------------------
def _error_lines(exc: ValidationError) -> list[str]:
    lines = []
    for err in exc.errors():
        where = ".".join(str(x) for x in err.get("loc") or ()) or "policy"
        msg = str(err.get("msg") or "not valid")
        lines.append(f"{where}: {msg.removeprefix('Value error, ')}")
    return lines


def parse_policy(data: "str | bytes | Mapping[str, Any]") -> RoutingPolicy:
    """Validate a policy given as JSON text or a mapping. Raises `PolicyInvalidError`; `detail["errors"]` lists the problems."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise PolicyInvalidError(f"the routing policy is not valid JSON: {exc}", detail={"errors": [f"policy: not JSON ({exc})"]}) from None
    if not isinstance(data, Mapping):
        raise PolicyInvalidError("the routing policy must be a JSON object", detail={"errors": ["policy: must be an object"]})
    try:
        return RoutingPolicy.model_validate(dict(data))
    except ValidationError as exc:
        lines = _error_lines(exc)
        raise PolicyInvalidError("the routing policy is not valid: " + "; ".join(lines[:5]), detail={"errors": lines}) from None


def load_default_policy() -> RoutingPolicy:
    """The packaged `policy.default.json`. A broken default is a build error and raises."""
    return parse_policy(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def user_policy_path(data_dir: "str | Path") -> Path:
    return Path(data_dir) / "connectors" / "policy.json"


class PolicyLoad(M):
    """What `load_policy` found: the policy in force, where it came from, and why a user file was not used."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    policy: RoutingPolicy
    source: Literal["default", "file"]
    error: Optional[str] = None          # `status().policy_error`: set when a user file exists but was not used
    errors: list[str] = []


def load_policy(data_dir: "str | Path | None" = None) -> PolicyLoad:
    """The user file if it validates, else the packaged default (with the reason when a file was there but invalid)."""
    default = load_default_policy()
    if data_dir is None:
        return PolicyLoad(policy=default, source="default")
    path = user_policy_path(data_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PolicyLoad(policy=default, source="default")
    except (OSError, UnicodeDecodeError) as exc:
        return PolicyLoad(policy=default, source="default", error=f"{path.name} cannot be read: {exc}", errors=[f"policy: unreadable ({exc})"])
    try:
        return PolicyLoad(policy=parse_policy(text), source="file")
    except PolicyInvalidError as exc:
        return PolicyLoad(policy=default, source="default", error=exc.user_message(), errors=list(exc.detail.get("errors", [])))


def write_policy(data_dir: "str | Path", body: "str | bytes | Mapping[str, Any]") -> RoutingPolicy:
    """Validate `body`, then store it as the user file (atomic: temp file and rename). Raises `PolicyInvalidError`; a bad body writes nothing."""
    policy = parse_policy(body)
    path = user_policy_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".policy-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(policy.model_dump(mode="json"), indent=2) + "\n")
        oslayer.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return policy
