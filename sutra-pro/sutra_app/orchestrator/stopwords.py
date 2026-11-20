"""How a stop is said to the owner (D394). The engine ends a stopped run with the same words whoever asked ("Stopped: stopped on request"), and a task that waited for one that did not finish says
"waiting task X did not finish". The owner knows who stopped it: they, the kill switch or a limit. Pure text; the project page does the same in `project_view.js` (`stopWords`)."""
from __future__ import annotations

import re

__all__ = ["plain_stop", "plain_outcome"]

_ENGINE_STOP = re.compile(r"^stopped:\s*stopped on request\.?$", re.I)
_WAITING = re.compile(r"^waiting task .* did not finish\.?$", re.I)


def plain_stop(reason: str) -> str:
    """A project's stop reason as the owner reads it: "You stopped it", "The kill switch was used", else the reason with its machine prefix off and a capital."""
    raw = re.sub(r"^stopped:\s*", "", (reason or "").strip(), flags=re.I).rstrip(". ")
    low = raw.lower()
    if not raw:
        return ""
    if "kill switch" in low or "kill file" in low:
        return "The kill switch was used"
    if low in ("stopped by you", "reset by you"):
        return "You stopped it"
    return raw[:1].upper() + raw[1:]


def plain_outcome(outcome: str, project_reason: str = "") -> str:
    """The words of a step's end on a card. Only the engine's two stock sentences are put into words: how the project was stopped when it was, else "It was stopped before it finished"; and "The step before it did
    not finish". Anything else the step said is shown as it is."""
    text = (outcome or "").strip()
    if _ENGINE_STOP.match(text):
        said = plain_stop(project_reason)
        return said if said and not _ENGINE_STOP.match(said) else "It was stopped before it finished"
    if _WAITING.match(text):
        return "The step before it did not finish"
    return outcome
