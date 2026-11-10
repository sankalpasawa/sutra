"""The `workspace` capability (engine design 2.2, D127): every agent call of the engine may look at the owner's working folder, and only
the builders of an output that says so may change it. The capability reads no file and needs no folder: it is a table that turns
(purpose, function, output) into `CallTag.workspace`. The router turns the tag into a folder (`Router.folder_for`), capped by the access
the owner chose in Settings, and adds the folder's text below J2's own prompt, so J2's prompts and every prompt golden stay byte for byte.

The same table also says what the TEAM may do (`CallTag.team_workspace`, D135): in a run of an output whose builders change files, every agent's folder
text states that, so Identity (whose own tools only read) plans for the builders' reach and does not write its own read-only tools into the charter
as a limit of the run.
"""
import re
from typing import Optional

from sutra_app.library.types import FUNCTIONS

from ..port import CallTag
from .base import Capability, EngineContext, output_spec

__all__ = ["WorkspaceCapability", "WORKSPACE_PURPOSES", "workspace_for", "team_workspace_for"]

WORKSPACE_PURPOSES = ("agent_turn", "plan", "judge")     # an agent's own work; helpers (summary, template, review, change) get no folder
_BUILDER = re.compile(r"W-[0-9]+")


def workspace_for(function: str, purpose: str, output: Optional[str]) -> str:
    """`none`, `read`, `inspect` or `edit` for one call: the five functions and every builder may read; a builder of an output whose spec says
    `edit` may also change files; Audit only ever reads, so it checks the builders' work independently of them, and in a run whose builders change
    files it may also run the four git reads (`inspect`), because "check every claimed change with `git diff`" cannot be done with file tools alone
    (a live run: "I could not run git, so the git claims rest on the earlier report", D135). The owner's access caps it like every level."""
    if purpose not in WORKSPACE_PURPOSES:
        return "none"
    if function in FUNCTIONS:
        return "inspect" if function == "audit" and team_workspace_for(output) == "edit" else "read"
    if _BUILDER.fullmatch(function or ""):
        spec = output_spec(output)
        return "edit" if spec is not None and spec.workspace == "edit" else "read"
    return "none"


def team_workspace_for(output: Optional[str]) -> str:
    """`edit` when the builders of this output may change files, else `none` (say nothing about the team). It goes on EVERY agent's call of such a
    run, so Identity, which only reads, is told what the team it plans for can do (D135); the router caps it by the owner's access choice."""
    spec = output_spec(output)
    return "edit" if spec is not None and spec.workspace == "edit" else "none"


class WorkspaceCapability(Capability):
    name = "workspace"

    def tag(self, tag: CallTag, ctx: EngineContext) -> dict:
        if ctx.settings.workspace != "auto":
            return {}
        stage = tag.stage or ctx.output
        level = workspace_for(tag.function, tag.purpose, stage)
        if level == "none":
            return {}
        team = team_workspace_for(stage)
        return {"workspace": level, "team_workspace": team} if team != "none" else {"workspace": level}

    def settings(self) -> list:
        return [{"field": "workspace", "values": ["auto", "off"], "default": "auto"}]
