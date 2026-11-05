"""Department: the record of a department (library design section 5, S2-models-14, D48).

A department record holds three things and nothing else: its id (= the OrgNode id of the chart), the folder it lives in
(relative to the data dir) and when it was made. Every other fact about a department has one owner already:

    name, purpose   the org chart (OrgChart is their one owner, so a rename cannot leave a stale copy here)
    charter         the run folder's goal.json (family "goal"); D65: no table copies it
    runs            the tasks table
    budget          the run summary (wire.py, L9: {start, granted, used, raises})

`ChartStore.apply` writes the record in the same transaction that adds the department to the chart; the shipped cross
rule `department.in_chart` (gate.py) refuses a record for a department the chart does not hold. A department is never
archived, moved or merged (DL5), so the record has no status and no revision.
"""
from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator

from .base import Record
from .registry import record
from .types import NodeId, Ts

__all__ = ["Department"]


@record
class Department(Record):
    """`home_dir` is `departments/<id>` as the store writes it; this class only guarantees it is a safe relative path."""

    FAMILY = "department"
    kind: Literal["department"] = "department"
    id: NodeId
    home_dir: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    ts_created: Ts

    @field_validator("home_dir")
    @classmethod
    def _relative_and_contained(cls, value: str) -> str:
        """A path under the data dir: not absolute, no `..`, no empty or `.` part, no backslash, no control character."""
        if value.startswith("/") or "\\" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("home_dir must be a relative path under the data dir (no leading /, no backslash, no control characters)")
        if any(part in ("", ".", "..") for part in value.split("/")):
            raise ValueError("home_dir must not contain an empty, '.' or '..' part")
        return value
