"""The models of `ChatPort` (absorb design 2.2, D107). All are closed (`extra="forbid"`).

`ChatPort` is the sibling of `ModelPort` for chat sessions. These types are the whole vocabulary of that seam: what a provider pill shows,
what a switch would carry, one turn in and out, and the events of a streamed turn.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import CallTag, Provider

__all__ = ["AttachmentRef", "ProviderPill", "Choice", "CarryPlan", "ChatTurnIn", "ChatTurnOut", "ChatEvent", "BlockType", "BlockKind",
           "EVENT_KINDS"]

BlockType = Literal["text", "thinking", "tool_use", "tool_result"]
BlockKind = Literal["read", "edit", "run", "search", "web", "other"]
EVENT_KINDS = ("partial", "block", "usage", "switched", "turn_done")


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttachmentRef(M):
    """A file the owner attached, stored once by content hash (ABS-4 fills the delivery; here it is only the reference)."""

    id: str = Field(pattern=r"^[0-9a-f]{64}$")           # sha256 of the content
    name: str = Field("", max_length=200)
    kind: Literal["image", "pdf", "text"] = "text"
    size: int = Field(0, ge=0)


class ProviderPill(M):
    """One provider as the pill shows it: `ready` with no `why_not`, or not ready with the reason."""

    name: Provider
    ready: bool
    why_not: str = ""
    model: Optional[str] = None
    models: list[str] = []
    plan: Optional[str] = None
    billing: str = "unknown"
    chosen: bool = False


class Choice(M):
    """The per-session choice. `provider=None` means the policy decides (nothing is pinned)."""

    session_id: str
    provider: Optional[Provider] = None
    model: Optional[str] = None


class CarryPlan(M):
    """The dry run of a provider switch: what the first prompt of the new session would carry. No process was started."""

    session_id: str
    target: Provider
    source: Optional[Provider] = None
    tier: Literal["none", "full", "digest"] = "none"       # nothing to carry, every message, or a digest plus the recent tail
    chars: int = Field(0, ge=0)
    kept_messages: int = Field(0, ge=0)
    omitted: int = Field(0, ge=0)
    scrub: dict[str, int] = {}                            # shape name -> count (egress, ABS-2)
    window_source: Literal["j2-cap", "known", "assumed-floor"] = "j2-cap"


class ChatTurnIn(M):
    text: str
    attachments: list[AttachmentRef] = []
    tag: CallTag = Field(default_factory=CallTag)


class ChatEvent(M):
    kind: Literal["partial", "block", "usage", "switched", "turn_done"]
    data: dict = {}


class ChatTurnOut(M):
    text: str
    provider: Provider
    model: Optional[str] = None
    usd: Optional[float] = None
    blocks: list[dict] = []
    switched: Optional[dict] = None                       # {"from", "to", "plan"} when this turn started a new provider session
