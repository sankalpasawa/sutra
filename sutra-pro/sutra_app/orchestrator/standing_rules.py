"""Standing rules of a team and its practice pick (GAP2 rules-notes; the old function templates' floors, as guidance).

    rules = StandingRules(db, redact=...)
    rules.get("web")                          # TeamRulesOut: the owner's lines, the pick, the picks the owner said no to
    rules.put("web", [RuleIn(...)], pack="money-movement")      # the owner's whole list (and the pick); refused lines raise 422 `validation`
    rules.accept("web", "money-movement") / rules.decline("web", "money-movement")    # the org chat's suggestion card
    framing_for(conn, "web", framing)         # what `TaskService._run_spec` puts in a run's framing: the rules block, then the chat agent's own
                                              # paragraph; BYTE-IDENTICAL to `framing` for a team with no rules and no pick

Storage: one JSON document per team in the `meta` table under `rules:<dept_id>` (no new table, so no schema bump; the database is in every
backup). Rules are read when a task STARTS, so a queued task picks up an edit. They reach the team only as the engine host's one system
line "Context from the team lead: ...": guidance, not enforcement. Never read by J2's prompts or files.
"""
import logging
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sutra_app.library import practice
from sutra_app.library.practice import MAX_RULES, RULE_CHARS, RuleLine, clean_text, compose_framing, load_packs, normalise, pack_by_id, rule_faults
from sutra_app.library.types import violation
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import NotFound, validation_error
from sutra_app.orchestrator.owner_words import json_meta, refusal, save_meta

__all__ = ["StandingRules", "RuleIn", "RulesIn", "RuleOut", "PackOut", "PackLineOut", "PackRef", "TeamRulesOut", "framing_for", "KEY",
           "FRAMING_MAX", "packs_out"]

log = logging.getLogger(__name__)
KEY = "rules:{}"
FRAMING_MAX = 20_000                        # `RunSpec.framing`'s limit


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tag: Literal["always", "ask", "never"]
    text: str = Field(min_length=1, max_length=2000)


class RulesIn(BaseModel):
    """`PUT /api/departments/{id}/rules`. A key left out is left as it is; `pack: null` takes the pick off."""

    model_config = ConfigDict(extra="forbid", strict=True)
    rules: list[RuleIn] | None = Field(None, max_length=200)
    pack: str | None = Field(None, max_length=40)


class RuleOut(BaseModel):
    tag: str
    text: str


class PackLineOut(BaseModel):
    function: str
    tag: str
    text: str


class PackOut(BaseModel):
    id: str
    name: str
    use_case: str
    lines: list[PackLineOut]


class PackRef(BaseModel):
    id: str
    name: str


class TeamRulesOut(BaseModel):
    dept_id: str
    rules: list[RuleOut]
    pack: PackOut | None
    declined: list[str]
    max_rules: int = MAX_RULES
    max_chars: int = RULE_CHARS


def packs_out() -> list[PackOut]:
    return [_pack_out(pack) for pack in load_packs()]


def _pack_out(pack: practice.PracticePack) -> PackOut:
    return PackOut(id=pack.id, name=pack.name, use_case=pack.use_case,
                   lines=[PackLineOut(function=l.function, tag=l.tag, text=l.text) for l in pack.lines])


def _read(conn: sqlite3.Connection, dept_id: str) -> tuple[list[RuleLine], practice.PracticePack | None, list[str]]:
    """The stored rules, the picked pack and the declined pack ids; anything unreadable is skipped, never raised."""
    doc = json_meta(conn, KEY.format(dept_id))
    rules: list[RuleLine] = []
    for item in doc.get("rules", []) if isinstance(doc.get("rules"), list) else []:
        try:
            rules.append(RuleLine.model_validate(item))
        except ValueError:
            log.warning("a stored standing rule of %s is damaged and was skipped", dept_id)
    pack = pack_by_id(doc.get("pack")) if isinstance(doc.get("pack"), str) else None
    declined = [p for p in doc.get("declined", []) if isinstance(p, str)] if isinstance(doc.get("declined"), list) else []
    return rules[:MAX_RULES], pack, declined


def framing_for(conn: sqlite3.Connection, dept_id: str, framing: str) -> str:
    """The run framing of a task of `dept_id`: the standing-rules block in front of `framing`. `framing` itself when the team has no rule and
    no pick, and when the rules cannot be read (a task must start)."""
    try:
        rules, pack, _declined = _read(conn, dept_id)
        return compose_framing(rules, pack, framing, FRAMING_MAX)
    except Exception:                                    # noqa: BLE001  (a broken rules row must never keep a team from starting)
        log.exception("standing rules of %s could not be read; the task starts without them", dept_id)
        return framing


class StandingRules:
    """Reads and writes the rules documents. One writer at a time (`db.tx()`), so two edits never interleave."""

    def __init__(self, db: Database, redact: Any = None) -> None:
        self.db = db
        self._redact = redact

    # ---- reads --------------------------------------------------------------------------------------------------------------

    def get(self, dept_id: str) -> TeamRulesOut:
        conn = self.db.conn()
        self._need_team(conn, dept_id)
        rules, pack, declined = _read(conn, dept_id)
        return self._out(dept_id, rules, pack, declined)

    @staticmethod
    def _out(dept_id: str, rules: list[RuleLine], pack: practice.PracticePack | None, declined: list[str]) -> TeamRulesOut:
        return TeamRulesOut(dept_id=dept_id, rules=[RuleOut(tag=r.tag, text=r.text) for r in rules], pack=_pack_out(pack) if pack else None,
                            declined=declined)

    @staticmethod
    def _need_team(conn: sqlite3.Connection, dept_id: str) -> None:
        found = conn.execute("SELECT 1 FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone()
        if found is None:
            raise NotFound("that team")

    # ---- writes -------------------------------------------------------------------------------------------------------------

    def put(self, dept_id: str, rules: list[RuleIn] | None = None, *, pack: str | None | Literal[False] = False) -> TeamRulesOut:
        """The owner's whole list and/or the pick. `rules` None leaves the list as it is; `pack` False leaves the pick, None takes it off.
        Every refused line is named with its place; nothing is stored unless all lines pass."""
        with self.db.tx() as tx:
            conn = tx.conn
            self._need_team(conn, dept_id)
            current, picked, declined = _read(conn, dept_id)
            if pack is not False:
                if pack is None:
                    picked = None
                else:
                    found = pack_by_id(pack)
                    if found is None:
                        raise validation_error([violation("pack", "unknown_pack", "There is no practice called that. Choose one of: "
                                                          + ", ".join(p.id for p in load_packs()))])
                    picked = found
                    declined = [d for d in declined if d != found.id]
            if rules is not None:
                current = self._checked(rules, picked)
            self._write(conn, dept_id, current, picked, declined)
            return self._out(dept_id, current, picked, declined)

    def accept(self, dept_id: str, pack_id: str) -> TeamRulesOut:
        """The owner said yes to a suggested practice."""
        return self.put(dept_id, None, pack=pack_id)

    def decline(self, dept_id: str, pack_id: str) -> TeamRulesOut:
        """The owner said no: the team stays on the defaults and the suggestion is not made again."""
        with self.db.tx() as tx:
            conn = tx.conn
            self._need_team(conn, dept_id)
            rules, picked, declined = _read(conn, dept_id)
            if pack_by_id(pack_id) is not None and pack_id not in declined:
                declined = [*declined, pack_id]
            self._write(conn, dept_id, rules, picked, declined)
            return self._out(dept_id, rules, picked, declined)

    def _checked(self, rules: list[RuleIn], pack: practice.PracticePack | None) -> list[RuleLine]:
        problems = []
        out: list[RuleLine] = []
        seen: dict[str, int] = {}
        inherited = [(l.tag, l.text) for l in pack.lines] if pack is not None else []
        if len(rules) > MAX_RULES:
            raise validation_error([violation("rules", "too_many", f"A team can hold {MAX_RULES} rules. Take one out before adding another.")])
        for index, rule in enumerate(rules):
            text = clean_text(rule.text)
            said = refusal(text, self._redact, RULE_CHARS)
            if said is None:
                key = normalise(text)
                if key in seen:
                    said = f"The team already has this rule (rule {seen[key] + 1})."
                else:
                    faults = rule_faults(inherited, rule.tag, text)
                    said = faults[0] if faults else None
                seen.setdefault(key, index)
            if said is not None:
                problems.append(violation(f"rules.{index}.text", "refused", said))
            else:
                out.append(RuleLine(tag=rule.tag, text=text))
        if problems:
            raise validation_error(problems, "Some rules could not be kept")
        return out

    @staticmethod
    def _write(conn: sqlite3.Connection, dept_id: str, rules: list[RuleLine], pack: practice.PracticePack | None, declined: list[str]) -> None:
        doc: dict[str, Any] = {"v": 1, "rules": [{"tag": r.tag, "text": r.text} for r in rules], "pack": pack.id if pack else "", "declined": declined}
        save_meta(conn, KEY.format(dept_id), doc)
