"""The models a person can pick for a chat, with names and notes (gap package welcome-settings, item 4; the old app's model catalog, ported).

    claude_options() -> list[ModelOption]                 Claude's table: the main rows first, then "More models"
    options_for(provider, connector) -> list[ModelOption] Claude: the table; any other provider: what its connector lists (empty when it cannot be asked)
    efforts_of(options, slug) -> list[str]                the efforts that model accepts (all five when the list does not say)
    names_of(options) -> str                              "best, opus, sonnet, ..." for a refusal that lists the valid choices

An id here is an id the installed Claude CLI accepts. The list was probed on Claude Code 2.1.308 (the version this app is tested with) with the old
app's probe, which spends no model turn because the run dies on the missing prompt after the model name was resolved:

    printf '' | claude --model <id> -p --output-format text
      known id    -> "Error: Input must be provided either through stdin or as a prompt argument when using --print"
      unknown id  -> "Claude Code doesn't recognize the model <id> ..."

Accepted: best, opus, sonnet, haiku, fable, claude-opus-4-8, claude-opus-4-7, claude-opus-4-6, claude-sonnet-4-6, opus[1m], sonnet[1m]. A control id
(totally-bogus-model) was refused, which is what makes the probe evidence. `tests/connectors/test_model_catalog.py` pins the list to that record, so an
id is added only together with a new probe.

`best` is the alias for the newest model the account can run; `fable` is the same model by its own name and sits under "More models", so the first
rows are the aliases that cannot go stale. The `[1m]` suffix is the CLI's own way to ask for the 1M-token window; it is part of the id that reaches
`--model`. Every Claude model takes the same five efforts (the CLI's own list); a Codex model's differ and come from Codex itself (`models()`).
Not here: the fast service tier, per-provider switches, DeepSeek.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

from .base import EFFORTS
from .budget import WINDOWS
from .errors import ConnectorError

__all__ = ["ModelOption", "claude_options", "options_for", "options_from", "efforts_of", "names_of", "CLAUDE_MAIN", "CLAUDE_MORE", "PROBED_ON"]

PROBED_ON = "2.1.308"
# (id, label, note)
CLAUDE_MAIN = (
    ("best", "Best available", "the newest model this account can run"),
    ("opus", "Opus", "most capable, slowest, highest cost"),
    ("sonnet", "Sonnet", "balanced default for most work"),
    ("haiku", "Haiku", "fastest and cheapest, least capable"),
)
CLAUDE_MORE = (
    ("fable", "Fable", "the newest model by its own name; Best available follows it"),
    ("claude-opus-4-8", "Opus 4.8", "pinned snapshot"),
    ("claude-opus-4-7", "Opus 4.7", "pinned snapshot"),
    ("claude-opus-4-6", "Opus 4.6", "pinned snapshot"),
    ("claude-sonnet-4-6", "Sonnet 4.6", "pinned snapshot"),
    ("opus[1m]", "Opus, 1M context", "Opus with the 1M-token window requested explicitly"),
    ("sonnet[1m]", "Sonnet, 1M context", "Sonnet with the 1M-token window requested explicitly"),
)


class ModelOption(BaseModel):
    """One row of a model list: what to send (`slug`), what to show (`label`, `note`), where (`group`), what it accepts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    slug: str
    label: str
    note: str = ""
    group: Literal["main", "more"] = "main"
    efforts: list[Literal["low", "medium", "high", "xhigh", "max"]]
    context_window: Optional[int] = None


def claude_options() -> list[ModelOption]:
    efforts = list(EFFORTS)
    window = WINDOWS.get("claude", {})
    rows = [(slug, label, note, "main") for slug, label, note in CLAUDE_MAIN] + [(slug, label, note, "more") for slug, label, note in CLAUDE_MORE]
    return [ModelOption(slug=slug, label=label, note=note, group=group, efforts=efforts, context_window=window.get(slug))     # type: ignore[arg-type]
            for slug, label, note, group in rows]


def options_from(provider: str, listed: Any) -> list[ModelOption]:
    """The options of `provider` given what its connector lists (`ModelInfo` rows). Claude's table is its own: the connector's list is not read."""
    if provider == "claude":
        return claude_options()
    return [ModelOption(slug=m.slug, label=m.label, efforts=list(m.efforts), context_window=m.context_window,
                        group=getattr(m, "group", "main"), note=getattr(m, "note", ""))
            for m in listed or ()]


def options_for(provider: str, connector: Any) -> list[ModelOption]:
    """Like `options_from`, asking `connector.models()` (no model call) for a provider with no table of its own; empty when it cannot be asked."""
    if provider == "claude":
        return claude_options()
    try:
        return options_from(provider, connector.models())
    except ConnectorError:
        return []


def efforts_of(options: list[ModelOption], slug: Optional[str]) -> list[str]:
    """The efforts `slug` accepts: its own list, else every effort (a model the list does not name, or one that lists none, is not narrowed here)."""
    found = next((o for o in options if o.slug == slug), None)
    return list(found.efforts) if found is not None and found.efforts else list(EFFORTS)


def names_of(options: list[ModelOption], limit: int = 12) -> str:
    slugs = [o.slug for o in options]
    return ", ".join(slugs[:limit]) + (f" and {len(slugs) - limit} more" if len(slugs) > limit else "")
