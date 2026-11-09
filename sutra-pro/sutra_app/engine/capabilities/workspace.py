"""The `workspace` capability (engine design 2.2, D127): every agent call of the engine may look at the owner's working folder, and only
the builders of an output that says so may change it. The capability reads no file and needs no folder: it is a table that turns
(purpose, function, output) into `CallTag.workspace`. The router turns the tag into a folder (`Router.folder_for`), capped by the access
the owner chose in Settings, and adds the folder's text below J2's own prompt, so J2's prompts and every prompt golden stay byte for byte.
"""
import re
from typing import Optional

from sutra_app.library.types import FUNCTIONS

from ..port import CallTag
from .base import Capability, EngineContext, output_spec

__all__ = ["WorkspaceCapability", "WORKSPACE_PURPOSES", "workspace_for"]

WORKSPACE_PURPOSES = ("agent_turn", "plan", "judge")     # an agent's own work; helpers (summary, template, review, change) get no folder
_BUILDER = re.compile(r"W-[0-9]+")


def workspace_for(function: str, purpose: str, output: Optional[str]) -> str:
    """`none`, `read` or `edit` for one call: the five functions and every builder may read; a builder of an output whose spec says
    `edit` may also change files; Audit only ever reads, so it checks the builders' work independently of them."""
    if purpose not in WORKSPACE_PURPOSES:
        return "none"
    if function in FUNCTIONS:
        return "read"
    if _BUILDER.fullmatch(function or ""):
        spec = output_spec(output)
        return "edit" if spec is not None and spec.workspace == "edit" else "read"
    return "none"


class WorkspaceCapability(Capability):
    name = "workspace"

    def tag(self, tag: CallTag, ctx: EngineContext) -> dict:
        if ctx.settings.workspace != "auto":
            return {}
        level = workspace_for(tag.function, tag.purpose, tag.stage or ctx.output)
        return {"workspace": level} if level != "none" else {}

    def settings(self) -> list:
        return [{"field": "workspace", "values": ["auto", "off"], "default": "auto"}]
