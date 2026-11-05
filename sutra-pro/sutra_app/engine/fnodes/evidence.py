"""What a verify check reads: `Evidence`, and the read-only reader of the run folder (function-nodes.md section 4).

`Evidence` is a frozen bundle the layer builds from hook data only (no new hook, no change to j2.py):

    turn      the `TurnInfo` of the function turn
    outcome   the `TurnOutcome`; None until the turn has ended (reply-phase and event-phase checks see None)
    reply     the latest reply of the node (`CallInfo.reply`); defaults to the last of `replies`
    replies   every reply of the node in this turn, oldest first (J2's re-asks are tries of the same atom)
    call      the latest `CallInfo` of the node (its `inputs` hold the ledger line, "N left")
    posted    the chat messages posted since the turn started, in order, each with its meta flattened in (J2's `post`
              builds `{id, t, who, text, step, **meta}`). The layer MAY add `after_reply`: how many replies of the node
              had arrived when the message was posted; `atom-rules` uses it to tell which reply drew a rejection
    records   the latest data of goal.json, workflows.json, audits.json, realization.json and conflicts.json: as saved
              this turn, else as read at turn start (`merge_records`)
    before    the same files as read at turn start (`read_records`)
    owners    atom id -> owner node id (`<dept>.<function>`), from the layer's own opens and J2's builder ids
    prompt    the user prompt of the latest call, when the layer has it
    saved     the record names saved this turn. Optional: when None it is derived (a name whose data differs from
              `before`), so a layer that builds only the fields above still works

A check never opens a file, reads a clock or touches the network: everything it may know is in this object. Missing
evidence is a failure the check reports itself (`missing: goal.json not saved this turn`).
"""
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from sutra_app.engine.hooks import CallInfo, TurnInfo, TurnOutcome

__all__ = ["RECORD_NAMES", "MAX_RECORD_BYTES", "Evidence", "read_records", "merge_records"]

RECORD_NAMES = ("goal.json", "workflows.json", "audits.json", "realization.json", "conflicts.json")
MAX_RECORD_BYTES = 16_000_000


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn: TurnInfo
    outcome: Optional[TurnOutcome] = None
    reply: Optional[dict] = None
    replies: list[dict] = []
    call: Optional[CallInfo] = None
    posted: list[dict] = []
    records: dict[str, Any] = {}
    before: dict[str, Any] = {}
    owners: dict[str, str] = {}
    prompt: Optional[str] = None
    saved: Optional[tuple[str, ...]] = None

    @model_validator(mode="before")
    @classmethod
    def _latest_reply_by_default(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and data.get("reply") is None and data.get("replies"):
            return {**data, "reply": data["replies"][-1]}
        return data

    @property
    def saved_names(self) -> frozenset[str]:
        """The record names saved during this turn."""
        if self.saved is not None:
            return frozenset(self.saved)
        return frozenset(name for name, data in self.records.items() if name not in self.before or self.before[name] != data)

    def last_audit(self) -> Optional[dict]:
        """The latest audit of audits.json; a board re-check entry (`kind` "recheck") is not an audit (j2.py `run_views`)."""
        rows = self.records.get("audits.json")
        if not isinstance(rows, list):
            return None
        return next((r for r in reversed(rows) if isinstance(r, dict) and r.get("kind") != "recheck"), None)

    def system_texts(self) -> list[str]:
        return [str(m.get("text") or "") for m in self.posted if m.get("who") == "system"]


def read_records(run_dir: str | Path, names: tuple[str, ...] = RECORD_NAMES, *, problems: Optional[list[str]] = None) -> dict[str, Any]:
    """The run files a check may read, parsed: `{name: data}` for each of `names` that exists and holds JSON. Read-only
    (files are opened for reading only, never created or changed). A file that is missing is simply absent; one that cannot
    be used (a bad name, a symlink leaving the folder, over `MAX_RECORD_BYTES`, not JSON) is absent too, and the reason is
    appended to `problems` when a list is given."""
    notes = problems if problems is not None else []
    try:
        root = Path(run_dir).resolve(strict=True)
    except OSError as exc:
        notes.append(f"run folder {run_dir}: {exc.strerror or exc}")
        return {}
    if not root.is_dir():
        notes.append(f"run folder {run_dir}: not a folder")
        return {}
    out: dict[str, Any] = {}
    for name in names:
        if name not in RECORD_NAMES:
            notes.append(f"{name}: not a record the checks read")
            continue
        path = root / name
        try:
            if not path.is_file():
                continue
            if path.resolve(strict=True).parent != root:
                notes.append(f"{name}: a link that leaves the run folder")
                continue
            if path.stat().st_size > MAX_RECORD_BYTES:
                notes.append(f"{name}: larger than {MAX_RECORD_BYTES} bytes")
                continue
            with open(path, encoding="utf-8") as f:
                out[name] = json.load(f)
        except (OSError, ValueError) as exc:
            notes.append(f"{name}: {type(exc).__name__}: {exc}")
    return out


def merge_records(before: Mapping[str, Any], saved: Mapping[str, Any]) -> dict[str, Any]:
    """`Evidence.records`: what was saved this turn, else what was read at turn start."""
    return {**before, **saved}
