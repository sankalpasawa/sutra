"""The model and effort chosen for each agent of a run, and how the engine hears of them (D131).

    build_choices(rev, default, agents) -> dict          the body of `<run>/choices.json` (server side)
    write_choices(path, body) -> bool                    atomic, mode 0600; False when the file already holds this body
    AgentPicks(path).for_tag(tag) -> Pick | None         the engine side: the pick of the agent a call is tagged for, else the run's default pick

    {"schema": "agent-choices/1", "rev": 7, "default": {"provider": "claude", "model": "sonnet", "effort": "high", "from": "run"},
     "agents": {"identity": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "medium"}, "W-3": {"provider": "claude", "model": "haiku", "effort": "low"}}}

The server owns the database and is the only writer; the engine only reads (as it only reads `inbox.jsonl`). `default` is the run's pick, else the team's (or
null); `agents` holds only the agents that have a choice of their own, keyed by the name the engine tags (`CallTag.function`: identity, ..., W-3). The file is
rebuilt from the database whenever a pick changes and at every server start, so a restart loses nothing. The reader re-reads on a changed `(mtime_ns, size)`,
validates, and ignores a file it cannot use (one warning, then the policy answers); it never raises into a model call.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from sutra_app import oslayer
from sutra_app.engine.port import CallTag

from .base import write_private_file
from .models import Pick

__all__ = ["SCHEMA", "CHOICES_FILE", "build_choices", "write_choices", "AgentPicks"]

log = logging.getLogger("sutra_app.connectors.agent_picks")

SCHEMA = "agent-choices/1"
CHOICES_FILE = "choices.json"
MAX_AGENTS = 500


def _entry(pick: Optional[Pick], source: str = "") -> Optional[dict[str, Any]]:
    if pick is None or not pick.provider:
        return None
    body: dict[str, Any] = {"provider": pick.provider, "model": pick.model, "effort": pick.effort}
    if source:
        body["from"] = source
    return body


def build_choices(rev: int, default: Optional[Pick], agents: dict[str, Pick], *, default_from: str = "") -> dict[str, Any]:
    """The file's body. A pick with no provider is "Default" and is left out; `rev` only has to differ when the content does."""
    return {"schema": SCHEMA, "rev": int(rev), "default": _entry(default, default_from),
            "agents": {name: e for name, pick in sorted(agents.items())[:MAX_AGENTS] if (e := _entry(pick)) is not None}}


def write_choices(path: "str | Path", body: dict[str, Any]) -> bool:
    """Atomically replace `path` (mode 0600). False, touching nothing, when the file already holds this body (`rev` aside)."""
    target = Path(path)

    def same(old: Any) -> bool:
        return isinstance(old, dict) and {k: v for k, v in old.items() if k != "rev"} == {k: v for k, v in body.items() if k != "rev"}

    try:
        if same(json.loads(target.read_text(encoding="utf-8"))):
            return False
    except (OSError, ValueError):
        pass
    tmp = target.parent / f".{target.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        write_private_file(tmp, json.dumps(body, ensure_ascii=False, indent=2) + "\n")
        oslayer.replace(tmp, target)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return True


class AgentPicks:
    """The engine's reader. Safe from any thread; cheap: one `stat` per call, a parse only when the file changed."""

    def __init__(self, path: "str | Path") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._stamp: Optional[tuple[int, int]] = None
        self._default: Optional[Pick] = None
        self._agents: dict[str, Pick] = {}
        self._warned = False

    def _load(self) -> None:
        try:
            st = self.path.stat()
        except OSError:
            self._stamp, self._default, self._agents = None, None, {}          # no file: nobody chose anything
            return
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self._stamp:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
                raise ValueError("not an agent-choices/1 file")
            default = raw.get("default")
            agents = raw.get("agents", {})
            if not isinstance(agents, dict):
                raise ValueError("agents is not an object")
            parsed_default = Pick.model_validate({k: v for k, v in default.items() if k != "from"}) if isinstance(default, dict) else None
            parsed = {str(name): Pick.model_validate({k: v for k, v in body.items() if k != "from"}) for name, body in list(agents.items())[:MAX_AGENTS]}
        except (OSError, ValueError, ValidationError, AttributeError) as exc:
            if not self._warned:
                log.warning("the agent choices file %s is not used (%s)", self.path, type(exc).__name__)
                self._warned = True
            self._stamp, self._default, self._agents = stamp, None, {}
            return
        self._stamp, self._default, self._agents, self._warned = stamp, parsed_default, parsed, False

    def for_tag(self, tag: CallTag) -> Optional[Pick]:
        """The agent's own pick, else the run's default; None when nobody chose (the policy answers). Never raises."""
        try:
            with self._lock:
                self._load()
                found = self._agents.get(tag.function) or self._default
        except Exception:                                      # noqa: BLE001  (a model call must never fail because of this file)
            log.warning("could not read the agent choices", exc_info=True)
            return None
        return found if found is not None and found.provider else None
