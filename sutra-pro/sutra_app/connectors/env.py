"""The environment a model CLI child gets (connectors design 4, D27, S1-contracts-11).

`PASS_NAMES` is THE allowlist of the project: the orchestrator's launcher of the engine process imports it and adds
`SHELL`, `TERM`, `PYTHONPATH`, every `SUTRA_*` except `SUTRA_TOKEN` and the task-settings keys, so an engine host hands
its CLI children the same login directories, proxy and certificate settings; `child_env` then drops every `SUTRA_*`
again. Never passed: any name with KEY, TOKEN, SECRET or PASSWORD in it, `ANTHROPIC_*`, `OPENAI_*`, `CODEX_API_KEY`,
`GITHUB_TOKEN`, `CLAUDE_CODE_*`, `CLAUDECODE`, `SUTRA_*`. The allowlist alone runs both CLIs (probed 2026-11-04).
Gateway and proxy setups pass extra names through `ConnectorConfig.extra_env`, which has the same secret-name guard.
This module imports nothing from the app, so every package can use it.
"""
from __future__ import annotations

import os
import re
from typing import Mapping, Optional

__all__ = ["PASS_NAMES", "SECRET_PATTERN", "is_secret_name", "child_env"]

_PROXY = ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "ALL_PROXY")

PASS_NAMES: tuple[str, ...] = (
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
    "SSL_CERT_FILE", "SSL_CERT_DIR",
    *_PROXY, *(n.lower() for n in _PROXY),
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
    "CLAUDE_CONFIG_DIR", "CODEX_HOME",
)

SECRET_PATTERN = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)


def is_secret_name(name: str) -> bool:
    """True for a variable name that looks like a credential (KEY, TOKEN, SECRET or PASSWORD in it, any case)."""
    return SECRET_PATTERN.search(name) is not None


def child_env(provider: str, extra: Optional[Mapping[str, str]] = None, *, environ: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The exact environment of one CLI child: the names of `PASS_NAMES` found in `environ` (default: this process's),
    then `extra` on top. No `SUTRA_*` name is ever passed (not even through `extra`, which a model CLI must not see) and
    a secret-looking name in `extra` is refused with ValueError. `provider` names the child in that error; both CLIs get
    the same base (each needs its own login directory variable, and the other's is harmless)."""
    if not isinstance(provider, str) or not provider:
        raise ValueError("child_env needs the name of the provider it builds the environment for")
    source = os.environ if environ is None else environ
    env = {name: source[name] for name in PASS_NAMES if name in source and not name.startswith("SUTRA_")}
    for name, value in (extra or {}).items():
        if not isinstance(name, str) or not name or "=" in name or "\0" in name:
            raise ValueError(f"{provider}: {name!r} is not a usable environment variable name")
        if is_secret_name(name):
            raise ValueError(f"{provider}: environment variable {name} looks like a secret and is refused; "
                             "sign in to the CLI instead of passing credentials")
        if name.startswith("SUTRA_"):
            continue
        if not isinstance(value, str) or "\0" in value:
            raise ValueError(f"{provider}: the value of {name} must be a string without NUL")
        env[name] = value
    return env
