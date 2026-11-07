"""Suggesting a practice pick when a team is added (GAP2 rules-notes; the old Adaptation floor "proposes templates from its use case", in code).

    suggest_pack(name, purpose, packs)     the pack whose keywords the new team's name and purpose share at least `MIN_SCORE` (2) words with, and
                                           more than any other pack does, else None
    pack_ref(dept_id, pack_id) / parse_ref(src_ref)    the `src_ref` of the choice card: `pack:<team id>:<pack id>`
    card_for(name, pack)                   the choice card: a template question, Yes and No (no model prose, D64)

The match is by words (`textutil.tokens`, plural `s` stripped) and conservative on purpose: a false suggestion on every added team would be noise, so
one shared word is never enough and a tie suggests nothing. Nothing changes without the owner's click: Yes puts the pick on the team, No leaves it on
the defaults and is remembered, so the same pick is not asked about the same team again.
"""
import re
from collections.abc import Sequence

from sutra_app.library.practice import PracticePack
from sutra_app.orchestrator.agent.planner import MIN_SCORE, line
from sutra_app.orchestrator.textutil import stem, tokens

__all__ = ["suggest_pack", "pack_ref", "parse_ref", "card_for", "PACK_REF", "YES", "NO"]

YES, NO = "yes", "no"
PACK_REF = re.compile(r"pack:([a-z][a-z0-9-]{1,39}):([a-z][a-z0-9-]{1,39})")


def _words(text: str) -> frozenset[str]:
    return frozenset(stem(word) for word in tokens(text))


def suggest_pack(name: str, purpose: str, packs: Sequence[PracticePack]) -> PracticePack | None:
    """The one pack that fits a team called `name` that is for `purpose`; None when nothing fits well enough or two fit equally."""
    team = _words(f"{name} {purpose}")
    scored = sorted(((len(team & {stem(k) for k in pack.keywords}), index, pack) for index, pack in enumerate(packs)), key=lambda s: (-s[0], s[1]))
    if not scored or scored[0][0] < MIN_SCORE:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][2]


def pack_ref(dept_id: str, pack_id: str) -> str:
    return f"pack:{dept_id}:{pack_id}"


def parse_ref(src_ref: str | None) -> tuple[str, str] | None:
    found = PACK_REF.fullmatch(src_ref or "")
    return (found.group(1), found.group(2)) if found else None


def card_for(name: str, pack: PracticePack) -> dict:
    return {"type": "choice", "question": line("suggest", name=name, fits=pack.fits, pack=pack.name),
            "options": [{"id": YES, "label": "Yes"}, {"id": NO, "label": "No"}]}
