"""Standing rules and practice packs (GAP2 rules-notes; the old app's function templates, ported as guidance).

    RuleLine {tag, text}            one owner rule: `always`, `ask` (ask the owner first) or `never`
    PackLine {function, tag, text}  one line a practice pack adds for one of the five functions
    PracticePack                    `money-movement` or `product-build`: only the lines it ADDS to a team's defaults
    load_packs() / pack_by_id()     the packs of `specs/practice_packs.json`, checked by `law_problems` when read
    law_problems(packs)             what the old template law refused, as sentences: a pack never drops or loosens a default line (it only
                                    adds, and a line that waives, skips or bypasses something is refused), a line is plain words (the screen's
                                    banned words, no founder-only ids, a check is never a score), Priority never orders the queue
    normalise(text) / rule_faults() the old `tighten.py`: lines compared as normalised text; an owner rule that says the same line more loosely
                                    than a pack line is refused with one plain sentence
    clean_text(text)                one line of white space-collapsed text, as every rule and note is stored
    compose_block(rules, pack)      the text the team reads: a fixed heading, the owner's rules, then the pack's lines per function ("" when there
                                    is nothing to say, so a team with no rules gets no heading at all)
    compose_framing(rules, pack, framing, limit)
                                    that block in front of the chat agent's own paragraph, bounded to `limit` characters; byte-identical to
                                    `framing` when there is nothing to say

Guidance, not enforcement: J2 acts on files and web artifacts, so the lines reach the team as one "Context from the team lead" line; a rule the
team drops is caught by the `rules-in-charter` check. This module imports nothing from the engine, the connectors or the orchestrator.
"""
import json
import re
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from .base import Value
from .types import FUNCTIONS, FunctionName, clip

__all__ = [
    "RULE_TAGS", "TAG_WORDS", "MAX_RULES", "RULE_CHARS", "MAX_PACK_LINES", "BLOCK_HEADING", "BLOCK_CHARS", "PACKS_PATH", "RuleLine", "PackLine",
    "PracticePack", "clean_text", "normalise", "rank", "rule_faults", "law_problems", "load_packs", "pack_by_id", "compose_block",
    "compose_framing", "block_of", "RULES_MARK",
]

RULE_TAGS = ("always", "ask", "never")
TAG_WORDS = {"always": "Always", "ask": "Ask the owner first", "never": "Never"}
MAX_RULES = 20                       # owner rules per team
RULE_CHARS = 300                     # one line
MAX_PACK_LINES = 8                   # a pack adds at most this many lines per function
BLOCK_HEADING = "Standing rules from the owner"
RULES_MARK = BLOCK_HEADING           # what a run's framing starts with when it carries the block (the `rules-in-charter` check looks for it)
BLOCK_CHARS = 8000                   # the block is never longer: 20 owner rules of 300 characters and the lines of a pack fit
PACKS_PATH = Path(__file__).resolve().parent / "specs" / "practice_packs.json"

_LINE = Annotated[str, StringConstraints(min_length=1, max_length=RULE_CHARS)]
_ID = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,39}$")]


class RuleLine(Value):
    tag: Literal["always", "ask", "never"]
    text: _LINE


class PackLine(Value):
    function: FunctionName
    tag: Literal["always", "ask", "never"]
    text: _LINE


class PracticePack(Value):
    """A starter pick. `keywords` are lowercase words (3 letters or more) the org agent matches a new team's name and purpose against."""

    id: _ID
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    use_case: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    keywords: Annotated[list[Annotated[str, StringConstraints(pattern=r"^[a-z0-9]{3,20}$")]], Field(min_length=3, max_length=30)]
    lines: Annotated[list[PackLine], Field(min_length=1, max_length=len(FUNCTIONS) * MAX_PACK_LINES)]


# ---- text -----------------------------------------------------------------------------------------------------------------------

_CONTROL = re.compile(r"[\u0000-\u001f\u007f]+")


def clean_text(text: object) -> str:
    """The text on one line: control characters and runs of white space become one space, then the ends are trimmed."""
    return " ".join(_CONTROL.sub(" ", str(text if text is not None else "")).split())


_APOSTROPHES = "’‘ʼ`"
_LEAD = re.compile(r"^(?:always|never|do\s+not|don't)\b")
_PROHIBITION = re.compile(r"^(?:never|do\s+not|don't)\b")


def _fold(text: object) -> str:
    folded = " ".join(str(text or "").casefold().split())
    for mark in _APOSTROPHES:
        folded = folded.replace(mark, "'")
    return re.sub(r"^\W+", "", folded)


def normalise(text: object) -> str:
    """A line as rules are compared (the old `tighten.normalise`): case folded, a leading always / never / do not / don't taken off, the
    punctuation taken off, the white space collapsed. 'Never publish prices.' and 'publish  PRICES' are the same line."""
    return " ".join(re.sub(r"[^\w\s]", " ", _LEAD.sub("", _fold(text), count=1)).split())


_RANKS = {"ask": 1, "never": 2}


def rank(tag: str, text: str) -> int | None:
    """How strict a rule is: `ask` 1, `never` 2; an `always` rule is 2 when its line is a prohibition ('Never ...'), else it has no rank (a
    positive requirement is never compared with a stricter one)."""
    if tag in _RANKS:
        return _RANKS[tag]
    if tag == "always" and _PROHIBITION.match(_fold(text)):
        return _RANKS["never"]
    return None


_SAYS = {"ask": "it asks you first", "never": "it never does this", "always": "it always does this"}


def rule_faults(inherited: Iterable[tuple[str, str]], tag: str, text: str) -> list[str]:
    """One plain sentence for each inherited (tag, text) line that says the same thing more strictly than the new rule; [] when the new
    rule loosens nothing. A line that cannot be ranked, on either side, is never compared. By the normalised text, not by meaning."""
    mine, key = rank(tag, text), normalise(text)
    if mine is None or not key:
        return []
    found = []
    for their_tag, their_text in inherited:
        theirs = rank(their_tag, their_text)
        if theirs is None or theirs <= mine or normalise(their_text) != key:
            continue
        says = _SAYS["never"] if theirs == _RANKS["never"] else _SAYS.get(their_tag, "it holds")
        found.append(f"The practice already says: {clean_text(their_text).rstrip('.')} ({says}). A rule cannot say it more loosely.")
    return found


# ---- the law of the packs (the old template tests, in Pro's words) -----------------------------------------------------------------

#: the words the screen does not say (the old interface's list), and the old engine's own vocabulary
BANNED = re.compile(r"\b(charters?|ceo|requesters?|grant(?:s|ed)?|counter(?:s|ed)?|refus\w*|internal systems?|stamp(?:s|ed)?|root|engines?)\b", re.I)
FOUNDER_ID = re.compile(r"\b(?:DS|D|A|R|LOCK|AMEND)-?\d|dref-", re.I)
#: wording that waives, skips or bypasses something: a pack only adds or tightens
LOOSENS = re.compile(r"\b(without (?:asking|approval|checking|a check)|no need to|skips?|skipped|waive[sd]?|bypass(?:es|ed)?|overrid(?:e|es|den)|may ignore)\b", re.I)
PRIORITY_NEVER_SAY = re.compile(r"order|what runs next", re.I)           # Priority prices and holds the budget; who goes first is Coordination's


def law_problems(packs: Sequence[PracticePack]) -> list[str]:
    """What breaks the law of the packs, as sentences ([] when all is well)."""
    found: list[str] = []
    seen_ids: set[str] = set()
    for pack in packs:
        where = f"pack {pack.id}"
        if pack.id in seen_ids:
            found.append(f"{where}: the id is used twice")
        seen_ids.add(pack.id)
        per_function = {fn: [line for line in pack.lines if line.function == fn] for fn in FUNCTIONS}
        for fn, lines in per_function.items():
            if len(lines) > MAX_PACK_LINES:
                found.append(f"{where}: {fn} has {len(lines)} lines, at most {MAX_PACK_LINES}")
            keys = [normalise(line.text) for line in lines]
            if len(set(keys)) != len(keys):
                found.append(f"{where}: {fn} says one line twice")
        for line in pack.lines:
            about = f"{where}, {line.function}: {clip(line.text, 60)!r}"
            if BANNED.search(line.text):
                found.append(f"{about} uses a word the screen does not say")
            if FOUNDER_ID.search(line.text):
                found.append(f"{about} carries a founder-only id or a reference")
            if LOOSENS.search(line.text):
                found.append(f"{about} loosens: a pack only adds or tightens")
            if "score" in line.text.lower() and not re.search(r"never a score|as a score|into a score", line.text, re.I):
                found.append(f"{about} treats a check as a score")
            if line.function == "priority" and PRIORITY_NEVER_SAY.search(line.text):
                found.append(f"{about} orders the queue, which is Coordination's")
        if len(set(normalise(line.text) for line in pack.lines)) != len(pack.lines):
            found.append(f"{where}: two functions say one line")
    return found


@lru_cache(maxsize=1)
def _packs() -> tuple[PracticePack, ...]:
    document = json.loads(PACKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("kind") != "practice_packs":
        raise ValueError("practice_packs.json is not a practice_packs document")
    packs = tuple(PracticePack.model_validate(item) for item in document.get("packs", []))
    problems = law_problems(packs)
    if problems:
        raise ValueError("practice_packs.json breaks the law of the packs: " + "; ".join(problems))
    return packs


def load_packs() -> list[PracticePack]:
    """The shipped packs, checked once. A broken file raises ValueError (the tests fail first)."""
    return list(_packs())


def pack_by_id(pack_id: str | None) -> PracticePack | None:
    return next((pack for pack in _packs() if pack.id == pack_id), None) if pack_id else None


# ---- what the team reads --------------------------------------------------------------------------------------------------------

def compose_block(rules: Sequence[RuleLine], pack: PracticePack | None) -> str:
    """The standing rules as the team reads them. "" when there is no rule and no pack (no heading, nothing). Cut to `BLOCK_CHARS` by whole
    lines from the end of the pack's part, never into the owner's rules."""
    if not rules and pack is None:
        return ""
    lines = [f"{BLOCK_HEADING} (they apply to every task of this team and come before the request; where one meets the request, ask the owner):"]
    for tag in RULE_TAGS:
        lines.extend(f"- {TAG_WORDS[tag]}: {clean_text(r.text)}" for r in rules if r.tag == tag)
    if pack is not None:
        lines.append(f"Practice \"{pack.name}\" (added to the defaults, never loosening them):")
        for fn in FUNCTIONS:
            lines.extend(f"- {fn.capitalize()}, {TAG_WORDS[line.tag].lower()}: {clean_text(line.text)}" for line in pack.lines if line.function == fn)
    block = "\n".join(lines)
    if len(block) <= BLOCK_CHARS:
        return block
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > BLOCK_CHARS - 60:
            kept.append("(more lines were left out)")
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept)


def _squeeze(text: str, limit: int) -> str:
    """`text` cut to `limit` characters in the middle: its start (the brief) and its end (a retry's note) stay."""
    if len(text) <= limit:
        return text
    mark = " [...] "
    head = max((limit - len(mark)) * 6 // 10, 0)
    tail = max(limit - len(mark) - head, 0)
    return text[:head] + mark + (text[len(text) - tail:] if tail else "")


def compose_framing(rules: Sequence[RuleLine], pack: PracticePack | None, framing: str, limit: int) -> str:
    """The block, a blank line, then `framing`; at most `limit` characters (the framing is squeezed, the block is not). With nothing to say
    the framing is returned untouched."""
    block = compose_block(rules, pack)
    if not block:
        return framing
    if not framing.strip():
        return block[:limit]
    room = limit - len(block) - 2
    return block + "\n\n" + (_squeeze(framing, room) if room > 0 else "")


def block_of(framing: str) -> str:
    """The standing-rules block at the start of a run's framing, or "" when the framing carries none."""
    if not framing.startswith(BLOCK_HEADING):
        return ""
    head, _, _rest = framing.partition("\n\n")
    return head
