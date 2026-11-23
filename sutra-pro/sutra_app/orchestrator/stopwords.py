"""How a stop is said to the owner (D394). The engine ends a stopped run with the same words whoever asked ("Stopped: stopped on request"), and a task that waited for one that did not finish says
"waiting task X did not finish". The owner knows who stopped it: they, the kill switch or a limit. Pure text; the project page does the same in `project_view.js` (`stopWords`)."""
from __future__ import annotations

import re

__all__ = ["plain_stop", "plain_outcome"]

_ENGINE_STOP = re.compile(r"^stopped:\s*stopped on request\.?$", re.I)
_WAITING = re.compile(r"^waiting task .* did not finish\.?$", re.I)
JARGON = re.compile(r"done-when|rubric|necessary condition|work report|\bworkable\b|Requester|workflow|charter|\bAdaptation\b|\bIdentity\b|\bAudit\b|\bJ2\b|run template", re.I)       # the engine's own words (D410)
_WORKABLE = re.compile(r"^done:\s*the .+? (?:is|are) workable\.\s*every done-when item.*$", re.I | re.S)
_NOTHING_TO_BUILD = re.compile(r"^done:\s*the change left the charter.*nothing to build\.?$", re.I | re.S)
_SELECTED = re.compile(r"^done:\s*the selected workflows of run template .*? are built \((\d+) of (\d+)\)", re.I | re.S)
_STOPPED_ENGINE = (
    (re.compile(r"^stopped:\s*identity couldn't", re.I), "It stopped: it could not understand the request well enough to start."),
    (re.compile(r"^stopped:\s*adaptation planned no workflows", re.I), "It stopped: it found nothing to build for this request."),
    (re.compile(r"^stopped:\s*the plan chose nothing", re.I), "It stopped: it found nothing to build for this request."),
    (re.compile(r"^stopped\b.*:\s*nothing was built", re.I), "It stopped: nothing was built."),
    (re.compile(r"dry run changed the requester's real folders", re.I), "It stopped: a trial run changed folders it was not meant to touch."))
_OPEN_ITEMS = re.compile(r"^done with open items\s*[:.-]?\s*", re.I)


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
    if _WORKABLE.match(text):
        return "Done. Every check passed."
    if _NOTHING_TO_BUILD.match(text):
        return "Done. Nothing needed building."
    chosen = _SELECTED.match(text)
    if chosen:
        return f"Done. {chosen.group(1)} of {chosen.group(2)} parts are built; the rest was not chosen."
    for pattern, said in _STOPPED_ENGINE:
        if pattern.search(text):
            return said
    if _OPEN_ITEMS.match(text):
        return _plain_open_items(text)
    if JARGON.search(text):                                        # anything else of the engine's own that still has its words: said by how it began, never in the engine's words (D410)
        return "Done." if text.lower().startswith("done") else "It stopped before it finished." if text.lower().startswith("stopped") else outcome
    return outcome


_ITEM_HEAD = re.compile(r"^(?:done-when item\s+\S+|(?:document|design|site|code)?\s*rubrics?\s+[^:]*?|necessary conditions?\s+\S+\s+not met)\s*(?:\([^)]*\))?\s*:?\s*", re.I)
_EVIDENCE = re.compile(r"\s*\((?:evidence|note)\s*:[^)]*\)", re.I)
_ID = re.compile(r"\b[A-Z]{1,3}-\d+\b")
_CODE = re.compile(r"\b[A-Z][A-Z_]{3,}\b")


def _plain_item(item: str) -> str:
    """One thing the engine named as still open, without its ids: "done-when item 3 (F-3 NEEDS_REVISION): the page lists prices" is "the page lists prices"; "design rubric D-2 (FAILED): contrast is low" is
    "contrast is low"; "necessary condition NC-1 not met: privacy page (evidence: missing)" is "privacy page"."""
    item = _ITEM_HEAD.sub("", item.strip(), count=1)
    item = _EVIDENCE.sub("", item)
    item = re.sub(r"\([^)]*\b(?:[A-Z][A-Z_]{3,}|[A-Z]{1,3}-\d+)\b[^)]*\)", "", item)        # a parenthesis that holds an id or a code word
    item = _CODE.sub("", _ID.sub("", item))
    item = re.sub(r"\b(?:rubrics?|done-when|necessary conditions?)\b", "", item, flags=re.I)
    return re.sub(r"\s+", " ", item).strip(" .;:,-")


def _plain_open_items(text: str) -> str:
    """The engine's "Done with open items: <how it was shipped>. Still not workable: <item>; <item> ..." (or "... Not made: <left>.") in the owner's words (D402, r-1): no id, no code word, no rubric, no "Requester"
    (the owner is "you", "the Requester's decision" is "your decision"). What the engine named as open stays, one item at a time, in its own plain part."""
    rest = _OPEN_ITEMS.sub("", text, count=1)
    why, items_part = rest, ""
    parts = re.split(r"(?i)(still not workable|not made)\s*:", rest, maxsplit=1)
    if len(parts) == 3:
        why, items_part = parts[0], parts[2]
    chose = bool(re.search(r"as is|as it is|requester|decision|accepted", why, re.I))
    items = [it for it in (_plain_item(x) for x in re.split(r";\s*", items_part.strip(" .")) if x.strip()) if it]
    head = "Done, with some things still open." if len(items) > 1 else "Done, with one thing still open."
    tail = ("Still open: " + "; ".join(i[:1].upper() + i[1:] if k == 0 else i for k, i in enumerate(items)) + ".") if items else ""
    return " ".join(part for part in (head, "You chose to take it as it is." if chose else "", tail) if part)
