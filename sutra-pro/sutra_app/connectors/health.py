"""What the router knows about each provider before it spends a call (connectors design 3.6, "Health and quota before a call").

`HealthBook` never makes a model call and never reads another program's credentials (CD8). It keeps, per provider, on an
injected clock:

    installed     `shutil.which` result, cached 60 s (the caller passes the probe)
    auth          `AuthStatus` from the status command, cached 30 s; dropped by a `not_signed_in` error
    cooldown      set by errors: quota until `resets_at` else +15 min (Claude) / +30 min (Codex); rate_limited +60 s;
                  overloaded +30 s; a flag error +10 min. Several cooldowns keep the latest end
    breaker       3 `crashed` within 60 s open it for 60 s
    quota         the last `Quota` snapshot (Claude `rate_limit_event`, Codex rollout); `exhausted` blocks until `resets_at`
                  (no `resets_at`: the quota cooldown from the moment it was seen)

A success (`ok`) clears cooldowns, the breaker's crash history and any exhausted snapshot; the next snapshot may block again.
`skip_reason()` is the one question the plan asks: why should this provider be skipped, or None. The book is thread-safe.

Quota snapshots outlive a restart (GAP-providers): `set_quota` stamps `seen_at`, every change of a snapshot (a new one, an exhausted
one cleared by a success) goes to the listeners of `on_quota_change` (quota_store.py writes the file), and `restore_quota` puts a
stored snapshot back with its own `seen_at`, so an exhausted one still blocks until its `resets_at` after the app starts again.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Literal, Mapping, Optional

from .errors import ConnectorError
from .models import AuthStatus, M, Provider, Quota

__all__ = [
    "HealthBook", "HealthState", "Cooldown", "INSTALLED_TTL_S", "AUTH_TTL_S", "QUOTA_COOLDOWN_S", "RATE_LIMITED_COOLDOWN_S",
    "OVERLOADED_COOLDOWN_S", "FLAG_COOLDOWN_S", "BREAKER_CRASHES", "BREAKER_WINDOW_S", "BREAKER_OPEN_S", "API_KEY_REFUSED",
]

INSTALLED_TTL_S = 60.0
AUTH_TTL_S = 30.0
QUOTA_COOLDOWN_S = {"claude": 15 * 60.0, "codex": 30 * 60.0, "stub": 15 * 60.0}     # when the provider names no reset time
RATE_LIMITED_COOLDOWN_S = 60.0
OVERLOADED_COOLDOWN_S = 30.0
FLAG_COOLDOWN_S = 10 * 60.0
BREAKER_CRASHES = 3
BREAKER_WINDOW_S = 60.0
BREAKER_OPEN_S = 60.0
# the reason shown for an API-key login (D7, S1-contracts-17): refused with no override
API_KEY_REFUSED = "API-key login refused (D7): sign in with your subscription"
_NAMES = {"claude": "Claude", "codex": "Codex", "stub": "Stub"}
log = logging.getLogger("sutra_app.connectors.health")

HealthName = Literal["ok", "cooldown", "quota", "breaker", "signed_out", "missing"]


class Cooldown(M):
    """A block on a provider until `until` (epoch seconds). `kind` says why; `code` is the error code that set it."""

    until: float
    kind: Literal["quota", "rate_limited", "overloaded", "flag", "breaker"]
    reason: str
    code: Optional[str] = None


class HealthState(M):
    """The `health` object of `GET /api/connectors/status` and the payload of `connector.health`."""

    state: HealthName = "ok"
    until: Optional[float] = None
    reason: Optional[str] = None


class _Slot:
    """Everything known about one provider."""

    def __init__(self) -> None:
        self.installed: Optional[tuple[bool, float]] = None        # (value, checked_at)
        self.auth: Optional[tuple[AuthStatus, float]] = None
        self.cooldowns: dict[str, Cooldown] = {}                   # by kind: the latest end wins
        self.crashes: list[float] = []
        self.quota: Optional[Quota] = None
        self.quota_seen_at: float = 0.0


class HealthBook:
    def __init__(self, *, clock: Callable[[], float] = time.time, installed_ttl: float = INSTALLED_TTL_S,
                 auth_ttl: float = AUTH_TTL_S) -> None:
        self._clock = clock
        self._installed_ttl = installed_ttl
        self._auth_ttl = auth_ttl
        self._slots: dict[str, _Slot] = {}
        self._lock = threading.RLock()
        self._quota_listeners: list[Callable[[str, Optional[Quota]], None]] = []

    def _slot(self, provider: str) -> _Slot:
        slot = self._slots.get(provider)
        if slot is None:
            slot = self._slots[provider] = _Slot()
        return slot

    # ---- cached probes ---------------------------------------------------------------------------------------------
    def installed(self, provider: Provider, probe: Callable[[], bool]) -> bool:
        """Whether the CLI is on PATH; `probe` runs only when the cached answer is older than 60 s."""
        with self._lock:
            slot = self._slot(provider)
            now = self._clock()
            if slot.installed is not None and now - slot.installed[1] < self._installed_ttl:
                return slot.installed[0]
        value = bool(probe())
        with self._lock:
            self._slot(provider).installed = (value, self._clock())
        return value

    def auth(self, provider: Provider, probe: Callable[[], AuthStatus], *, refresh: bool = False) -> AuthStatus:
        """The sign-in status; `probe` runs only when the cached one is older than 30 s, was dropped, or `refresh` is true."""
        with self._lock:
            slot = self._slot(provider)
            now = self._clock()
            if not refresh and slot.auth is not None and now - slot.auth[1] < self._auth_ttl:
                return slot.auth[0]
        status = probe()
        with self._lock:
            self._slot(provider).auth = (status, self._clock())
        return status

    def forget_auth(self, provider: Provider) -> None:
        with self._lock:
            self._slot(provider).auth = None

    def forget_installed(self, provider: Provider) -> None:
        with self._lock:
            self._slot(provider).installed = None

    def peek_auth(self, provider: Provider) -> Optional[AuthStatus]:
        """The cached status if still fresh, without probing (for `preflight` and `status` that may not spawn)."""
        with self._lock:
            entry = self._slot(provider).auth
            if entry is not None and self._clock() - entry[1] < self._auth_ttl:
                return entry[0]
            return None

    # ---- outcomes --------------------------------------------------------------------------------------------------
    def _block(self, slot: _Slot, cooldown: Cooldown) -> None:
        old = slot.cooldowns.get(cooldown.kind)
        if old is None or cooldown.until >= old.until:
            slot.cooldowns[cooldown.kind] = cooldown

    def failed(self, provider: Provider, err: ConnectorError) -> Optional[Cooldown]:
        """Record a failed attempt. Returns the cooldown it set, if any."""
        now = self._clock()
        code = err.code
        with self._lock:
            slot = self._slot(provider)
            if code == "not_signed_in":
                slot.auth = None
                return None
            if code == "cli_missing":
                slot.installed = (False, now)
                return None
            cooldown: Optional[Cooldown] = None
            if code == "quota":
                until = err.resets_at if err.resets_at is not None and err.resets_at > now else now + QUOTA_COOLDOWN_S.get(provider, 900.0)
                cooldown = Cooldown(until=until, kind="quota", reason="usage limit reached", code=code)
            elif code == "rate_limited":
                cooldown = Cooldown(until=now + RATE_LIMITED_COOLDOWN_S, kind="rate_limited", reason="rate limited", code=code)
            elif code == "overloaded":
                cooldown = Cooldown(until=now + OVERLOADED_COOLDOWN_S, kind="overloaded", reason="overloaded", code=code)
            elif code == "cli_flag_unsupported":
                cooldown = Cooldown(until=now + FLAG_COOLDOWN_S, kind="flag", reason="the CLI does not accept a needed flag", code=code)
            elif code == "crashed":
                slot.crashes = [t for t in slot.crashes if now - t < BREAKER_WINDOW_S] + [now]
                if len(slot.crashes) >= BREAKER_CRASHES:
                    cooldown = Cooldown(until=now + BREAKER_OPEN_S, kind="breaker",
                                        reason=f"{len(slot.crashes)} crashes within {int(BREAKER_WINDOW_S)} s", code=code)
            if cooldown is not None:
                self._block(slot, cooldown)
            return cooldown

    def ok(self, provider: Provider) -> None:
        """A call succeeded: every block is lifted and the crash history is forgotten."""
        with self._lock:
            slot = self._slot(provider)
            slot.cooldowns.clear()
            slot.crashes.clear()
            if slot.quota is not None and slot.quota.status == "exhausted":
                slot.quota = None
                self._quota_changed(provider, None)

    def set_quota(self, provider: Provider, quota: Quota) -> None:
        """Keep the latest snapshot, stamped with `seen_at`. A fresh `ok` or `warning` lifts a quota block; `exhausted` makes one."""
        with self._lock:
            slot = self._slot(provider)
            now = self._clock()
            slot.quota = quota if quota.seen_at is not None else quota.model_copy(update={"seen_at": now})
            slot.quota_seen_at = now
            if quota.status != "exhausted":
                slot.cooldowns.pop("quota", None)
            self._quota_changed(provider, slot.quota)

    def restore_quota(self, provider: Provider, quota: Quota) -> None:
        """Put back a stored snapshot (start-up): it keeps its own `seen_at`, it lifts no cooldown and no listener hears it."""
        with self._lock:
            slot = self._slot(provider)
            slot.quota = quota
            slot.quota_seen_at = quota.seen_at if quota.seen_at is not None else self._clock()

    def on_quota_change(self, listener: Callable[[str, Optional[Quota]], None]) -> None:
        """`listener(provider, quota or None)` after every change of a snapshot, under the book's lock (writes stay in order)."""
        with self._lock:
            self._quota_listeners.append(listener)

    def _quota_changed(self, provider: str, quota: Optional[Quota]) -> None:
        for listener in list(self._quota_listeners):
            try:
                listener(provider, quota)
            except Exception:                      # a lost snapshot file must not turn a model answer into a failure
                log.warning("a quota listener failed for %s", provider, exc_info=True)

    def quota(self, provider: Provider) -> Optional[Quota]:
        with self._lock:
            return self._slot(provider).quota

    def update(self, provider: Provider, *, error: Optional[ConnectorError] = None, quota: Optional[Quota] = None) -> None:
        """What the router calls after each attempt: the outcome first, then the quota snapshot that came with it."""
        if error is not None:
            self.failed(provider, error)
        else:
            self.ok(provider)
        if quota is not None:
            self.set_quota(provider, quota)

    # ---- questions -------------------------------------------------------------------------------------------------
    def _blocks(self, provider: str) -> list[Cooldown]:
        now = self._clock()
        slot = self._slot(provider)
        blocks = [c for c in slot.cooldowns.values() if c.until > now]
        quota = slot.quota
        if quota is not None and quota.status == "exhausted":
            until = quota.resets_at if quota.resets_at is not None else slot.quota_seen_at + QUOTA_COOLDOWN_S.get(provider, 900.0)
            if until > now:
                blocks.append(Cooldown(until=until, kind="quota", reason="usage limit reached", code="quota"))
        return blocks

    def cooldown(self, provider: Provider) -> Optional[Cooldown]:
        """The block that ends last, or None when the provider may be tried now."""
        with self._lock:
            blocks = self._blocks(provider)
        return max(blocks, key=lambda c: c.until) if blocks else None

    def state(self, provider: Provider) -> HealthState:
        """The coarse state without probing: cached facts only (a provider never probed is `ok`)."""
        with self._lock:
            slot = self._slot(provider)
            now = self._clock()
            block = max(self._blocks(provider), key=lambda c: c.until, default=None)
            if block is not None:
                name = "breaker" if block.kind == "breaker" else "quota" if block.kind == "quota" else "cooldown"
                return HealthState(state=name, until=block.until, reason=block.reason)
            if slot.installed is not None and not slot.installed[0] and now - slot.installed[1] < self._installed_ttl:
                return HealthState(state="missing", reason="CLI not installed")
            if slot.auth is not None and now - slot.auth[1] < self._auth_ttl and slot.auth[0].signed_in is False:
                return HealthState(state="signed_out", reason="not signed in")
            return HealthState()

    def skip_reason(self, provider: Provider, *, installed_probe: Callable[[], bool],
                    auth_probe: Optional[Callable[[], AuthStatus]] = None) -> Optional[str]:
        """Why the plan drops this provider before any spawn, or None. Order: installed, signed in, API-key login, blocks."""
        name = _NAMES.get(provider, provider)
        if not self.installed(provider, installed_probe):
            return f"{name} CLI is not installed"
        if auth_probe is not None:
            status = self.auth(provider, auth_probe)
            if status.signed_in is False:
                return f"{name} is not signed in"
            if status.billing == "api_key":            # only a positive api_key status; an unknown method is allowed
                return API_KEY_REFUSED
        block = self.cooldown(provider)
        if block is not None:
            return f"{block.reason}, retry after {datetime.fromtimestamp(block.until).strftime('%H:%M:%S')}"
        return None

    def snapshot(self) -> Mapping[str, HealthState]:
        with self._lock:
            known = list(self._slots)
        return {p: self.state(p) for p in known}       # type: ignore[arg-type]
