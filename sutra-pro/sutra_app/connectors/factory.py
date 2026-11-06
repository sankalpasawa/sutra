"""`build_router`: the one place that turns the app's settings into a running `Router` (connectors design 5.5, S1-contracts-08).

    router = build_router(settings, usage_sink=ledger, events=bus.publish_one, transcripts=chat_transcripts, session_hook=chats.set_provider)

It reads exactly three fields of `settings` and nothing else (ORCH's `Settings` satisfies that; so does any object with these
names): `data_dir` (where the optional `connectors/policy.json` lives), `connector` (auto | claude | codex | stub) and
`offline` (true: nothing but the stub answers). The environment variables `SUTRA_CONNECTOR` and `SUTRA_OFFLINE` are already
resolved by `Settings`; this module reads no environment. Without a `config`, `discover.connector_config` finds the CLIs (the owner's
chosen file in `connectors/bins.json`, PATH, then the folders installers use; it reads PATH and HOME and runs nothing).

An optional `replybook` goes to the stub of a stub-only router (the offline demo, GAP-DEMO); nothing else changes.

Start-up, in order:
  1. the routing policy is loaded (a user file that does not validate is not used; the reason rides in `status().policy.error`);
  2. the connectors are built: `stub` and offline give a stub-only router (no process is ever started, the CLIs are not even
     probed); otherwise `claude` and `codex` as the policy lists them, narrowed by `connector` (`build_connectors` of the engine port);
  3. each CLI is asked for its `--help` once. A flag that EVERY call needs but the CLI no longer lists marks the provider
     `degraded`: `HealthBook` has no state of that name, so it is recorded as the existing `flag` cooldown (state `cooldown`, reason
     "the CLI does not accept a needed flag", 10 minutes), the plan skips the provider and falls back, and a
     `connector.health` event goes out. A CLI that is not installed is not degraded (the plan says "CLI not found");
  4. a CLI version other than the tested ones (claude 2.1.308, codex 0.146.0) is logged as a warning;
  5. `connector.mode {mode}` is published.
The last quota snapshots are loaded from `<data>/connectors/quota.json` before the flags are probed, and kept there (quota_store.py).
Nothing here calls a model.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from .base import ModelConnector
from .discover import connector_config
from .engine_port import build_connectors
from .egress import Egress
from .errors import ConnectorError, FlagUnsupportedError
from .models import ConnectorConfig, Provider
from .policy import load_policy
from .quota_store import QUOTA_FILE, attach_quota_store
from .router import Router, TranscriptSource
from .stub import ReplyBook, StubConnector

__all__ = ["build_router", "REQUIRED_FLAGS", "TESTED_VERSIONS"]

log = logging.getLogger("sutra_app.connectors.factory")

TESTED_VERSIONS = {"claude": "2.1.308", "codex": "0.146.0"}

# The flags that every call of the connector puts on the command line (`build_command` of claude.py and codex.py), as listed by
# `claude --help` and `codex exec --help`. The other probed flags are optional features with their own fallback (a schema,
# images, tools, resume, a system prompt file): their absence is a per-call error, not a degraded provider.
REQUIRED_FLAGS: dict[str, tuple[str, ...]] = {
    "claude": ("--output-format", "--verbose", "--model", "--effort", "--system-prompt", "--tools", "--strict-mcp-config",
               "--disable-slash-commands", "--setting-sources", "--no-session-persistence"),
    "codex": ("--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--sandbox", "--cd",
              "--model", "--config"),
}


def build_router(settings: Any, *, usage_sink: Any = None, events: Optional[Callable[[str, dict], None]] = None,
                 transcripts: Optional[TranscriptSource] = None,
                 session_hook: Optional[Callable[[str, Provider, str, Optional[str]], None]] = None,
                 config: Optional[ConnectorConfig] = None, replybook: Optional[ReplyBook] = None, redactor: Any = None,
                 **router_kw: Any) -> Router:
    """A `Router` for these settings. `config` (tests point the executables at the fakes) and `router_kw` (a clock, a sleep, a
    health book) are extras beyond the specified signature; the three settings fields and the four wiring arguments are the contract.
    `replybook` (GAP-DEMO, D97) is the stub's canned replies; it is used only by a stub-only router (offline or `stub`), and the
    stub class is the book's `connector_class` when it has one (the demo book's stub reads the prompt), else `StubConnector`.
    `redactor` (the app's `Redactor`, anything with `secrets()`) lets the egress scrub the app's known secret VALUES, not only the shapes."""
    data_dir = Path(settings.data_dir)
    mode = settings.connector
    offline = bool(settings.offline)
    cfg = config or connector_config(data_dir)            # the CLIs where installers put them, or the file the owner chose (discover.py)
    load = load_policy(data_dir)
    if load.error:
        log.warning("the routing policy file is not used: %s", load.error)
    stub_only = offline or mode == "stub"
    connectors: dict[str, ModelConnector]
    if stub_only:
        connectors = {"stub": getattr(replybook, "connector_class", StubConnector)(cfg, book=replybook)}
    else:
        connectors = build_connectors(cfg, load.policy, only=None if mode == "auto" else mode)
    router = Router(connectors, load.policy, usage_sink=usage_sink, transcripts=transcripts, events=events, session_hook=session_hook,
                    connector=mode, offline=offline, policy_source=load.source, policy_error=load.error, **router_kw)
    if not stub_only:
        router.egress = Egress(data_dir / "connectors" / "egress.jsonl", redactor=redactor)
        attach_quota_store(router.health, data_dir / "connectors" / QUOTA_FILE)          # the plan meters survive a restart
        for name, connector in connectors.items():
            _probe_flags(router, name, connector, events)
            _check_version(name, connector)
    _publish(events, "connector.mode", {"mode": router.mode})
    return router


def _publish(events: Optional[Callable[[str, dict], None]], type_: str, data: dict) -> None:
    if events is None:
        return
    try:
        events(type_, data)
    except Exception:
        log.warning("the event callback failed for %s", type_, exc_info=True)


def _probe_flags(router: Router, name: str, connector: ModelConnector, events: Optional[Callable[[str, dict], None]]) -> None:
    try:
        flags = connector.flags()
    except ConnectorError as e:                      # not installed, or --help did not run: the plan reports it per call
        log.info("%s flags were not probed: %s", name, e.user_message())
        return
    except Exception:
        log.warning("probing the flags of %s failed", name, exc_info=True)
        return
    missing = [flag for flag in REQUIRED_FLAGS.get(name, ()) if not flags.get(flag, False)]
    if not missing:
        return
    version = _version(connector)
    log.warning("%s%s does not list the flag(s) %s: the provider is marked degraded", name, f" {version}" if version else "",
                ", ".join(missing))
    router.health.failed(name, FlagUnsupportedError(provider=name, detail={"flag": missing[0], "missing": missing, "version": version,
                                                                         "cli": name}))     # type: ignore[arg-type]
    state = router.health.state(name)                # type: ignore[arg-type]
    _publish(events, "connector.health", {"provider": name, "state": state.state, "until": state.until, "reason": state.reason})


def _version(connector: ModelConnector) -> Optional[str]:
    getter = getattr(connector, "version", None)
    if getter is None:
        return None
    try:
        return getter()
    except Exception:
        return None


def _check_version(name: str, connector: ModelConnector) -> None:
    tested = TESTED_VERSIONS.get(name)
    version = _version(connector)
    if tested is not None and version is not None and version != tested:
        log.warning("%s CLI version %s differs from the tested version %s: behaviour is unverified", name, version, tested)
