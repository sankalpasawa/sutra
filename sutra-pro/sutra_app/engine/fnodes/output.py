"""What a function turn produced, in plain words (D157, function-nodes.md section 5.5).

The layer asks for this each time it records a transition of the atom of a turn (a failed try, the close, an abandon). It reads
only what the hooks buffered (`TurnBuffer`: the node's calls and replies, the messages posted, the record files saved) and gives
back what goes on the atom, through `Seen`:

    turn_output(buf)       (items, reply): `items` are the `OutputItem`s of `Atom.produced`, one plain sentence each, and `reply`
                           is the last reply the model gave, printed (two-space indents) and cut to 4,000 characters, or None
    manual_output(buf)     the same for the manual atom of a question: the owner's answer
    reply_record(buf)      the `AtomReply` alone

What a turn produced, per function (the `yields` of its spec; the sentence reads the reply tolerantly, because a failed try is
exactly the reply that does not fit its class):

    identity       the charter (`the charter: <name>, 7 done-when items`), a rule (`ruled for Adaptation: <clause>`, or a split),
                   a question (`asked you 2 questions: <first>`), and what Identity decided on the way (the goal is reached,
                   more budget approved, the owner's answer read)
    adaptation     a proposal (`a proposal of 2 workflows: W-1 Build the page, W-2 ...`), a revision, an accepted or parked
                   proposal, a question to Identity, a dispute, the verdict on a failed atom
    priority       GRANT, COUNTER or REFUSE with the workflows it priced, or HOLD / REQUEST_APPROVAL for an envelope
    coordination   the order (`scheduled 3 workflows: W-1, W-2, W-3`), its rule and what it held
    audit          one finding per item: the count by verdict, and each finding that does not pass with its evidence

Every turn also says what it DID: `posted 3 messages to Coordination` (its own messages and who they went to), `code posted 1
message: <its first line>` (what J2's own code said during the turn), `saved the findings` (a record file no sentence above already
covers). A turn that made nothing says so (`nothing: ...`), so that an atom with nothing recorded at all is only an atom from
before D157.

Nothing here reads a clock or a file, and nothing raises on a reply of an odd shape: a word that cannot be read is left out.
"""
import json
import re
from collections.abc import Mapping
from typing import Any, Final, Optional

from sutra_app.library.atom import REPLY_TEXT_MAX, AtomReply, OutputItem
from sutra_app.library.types import clip

from .checks import TurnBuffer

__all__ = ["LINE", "NOTHING", "RECORD_WORDS", "reply_record", "turn_output", "manual_output"]

LINE: Final = 300                 # the longest name or ref of an OutputItem
SNIP: Final = 100                 # how much of a sentence of the reply the words keep
ROWS: Final = 5                   # findings told one by one; the rest are counted
NOTHING: Final = "nothing: no usable reply, no message posted, no record saved"
THE_REPLY: Final = "the reply"    # the ref of something the reply said that no record file holds
# The record files the checks read, in the owner's words.
RECORD_WORDS: Final = {"goal.json": "the charter", "workflows.json": "the workflows", "audits.json": "the findings",
                       "realization.json": "the plan", "conflicts.json": "the conflict log"}
_ID: Final = re.compile(r"^[A-Za-z]{1,2}-[0-9]{1,4}$")
_VERDICTS: Final = {                  # the plural and the singular of each verdict of a finding
    "PASS": ("pass", "passes"), "PASS_WITH_WARNING": ("pass with a warning", "passes with a warning"),
    "NEEDS_REVISION": ("need revision", "needs revision"),
    "BLOCKED_BY_EVIDENCE": ("are blocked by missing evidence", "is blocked by missing evidence"),
    "POLICY_CONCERN": ("raise a policy concern", "raises a policy concern"),
}
_PASSING: Final = ("PASS", "PASS_WITH_WARNING")


# ---- small readers: a reply is untrusted, so every one of these answers "nothing" instead of raising --------------------------

def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _snip(value: Any, limit: int = SNIP) -> str:
    return clip(_text(value), limit)


def _first(*values: Any) -> str:
    return next((text for text in map(_text, values) if text), "")


def _dicts(value: Any) -> list[Mapping]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [text for text in map(_text, value) if text] if isinstance(value, list) else []


def _whole(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _count(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many or one + 's'}"


def _tail(head: str, rest: Any) -> str:
    """`head: rest`, or just `head` when there is no rest."""
    rest = _text(rest)
    return f"{head}: {rest}" if rest else head


def _and(words: list[str], limit: int = 4) -> str:
    """Short words as a phrase: `a`, `a and b`, `a, b and c`; more than `limit` ends `... and 3 more`."""
    words = [w for w in words if w]
    if len(words) > limit:
        words = [*words[:limit], f"{len(words) - limit} more"]
    return ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else (words[0] if words else "")


def _list(words: list[str], limit: int = 4) -> str:
    """Names that hold spaces of their own, one after the other: `W-1 Build the page, W-2 Write the copy`; more than `limit` ends
    `, and 3 more` (an "and" between two of them would read as one name)."""
    words = [w for w in words if w]
    return ", ".join(words[:limit]) + (f", and {len(words) - limit} more" if len(words) > limit else "")


def _item(verb: str, name: str, form: str, ref: str) -> OutputItem:
    return OutputItem(verb=verb, name=clip(_text(name), LINE) or "something", form=form, ref=clip(_text(ref), LINE) or THE_REPLY)


def _do(name: str, form: str, ref: str = "chat") -> OutputItem:
    """A deed: a decision, a question, a ruling. It lives in the chat unless a record file says more."""
    return _item("do", name, form, ref)


def _where(file: str, saved: set[str]) -> str:
    """Where a thing the reply said lives: its record file when the turn saved it, else only the reply."""
    return file if file in saved else THE_REPLY


def _workflows(value: Any) -> list[str]:
    """`W-1 Build the page` for each workflow a reply names: its id when it looks like one, then its name."""
    out = []
    for w in _dicts(value):
        wid, name = _text(w.get("id")), _text(w.get("name"))
        out.append(f"{wid} {name}" if _ID.match(wid) and name else (name or (wid if _ID.match(wid) else "")))
    return [clip(w, 60) for w in out if w]


def _asked(value: Any) -> str:
    """The question of a `user_question` (an object with `question`, or the text itself)."""
    return _snip(value.get("question") if isinstance(value, Mapping) else value)


# ---- the reply, per function -------------------------------------------------------------------------------------------------

def _identity(r: Mapping, saved: set[str]) -> list[OutputItem]:
    questions = [q for q in (_text(d.get("question")) for d in _dicts(r.get("questions"))) if q] or _strings(r.get("questions"))
    goal = r.get("goal") if isinstance(r.get("goal"), Mapping) else None
    decision, asked = _text(r.get("decision")), r.get("user_question")
    if goal is not None and r.get("enough") is not False:                                   # intake: enough to write the charter
        name = _snip(_first(goal.get("site_name"), goal.get("product_name"), goal.get("statement")), 60)
        done = len(goal.get("done_when")) if isinstance(goal.get("done_when"), list) else 0
        return [_item("make", f"{_tail('the charter', name)}, {_count(done, 'done-when item')}", "charter", _where("goal.json", saved))]
    if questions:                                                                              # intake: not enough, ask
        return [_do(f"asked you {_count(len(questions), 'question')}: {_snip(questions[0])}", "question")]
    if "resolved" in r:                                                                        # a ruling on a conflict
        who, names = _text(r.get("ruling")), _strings(r.get("workflows"))
        if r.get("resolved") is True and who.lower() == "split":
            return [_do(_tail("ruled to split the proposal", _list(names)), "ruling", _where("conflicts.json", saved))]
        if r.get("resolved") is True:
            return [_do(_tail("ruled" + (f" for {who.capitalize()}" if who else ""), r.get("clause")), "ruling", _where("conflicts.json", saved))]
        return [_do(f"asked you: {_asked(asked)}", "question")] if asked else []
    if "approved" in r:                                                                        # the owner's answer on more budget
        more = _whole(r.get("budget_increase"))
        if r.get("approved") is True:
            return [_do("approved more budget" + (f" (+{more})" if more and more > 0 else ""), "decision")]
        return [_do("did not approve more budget", "decision")]
    if decision.upper() in ("DENY", "ASK"):                                                    # Priority asked for approval
        if decision.upper() == "DENY":
            return [_do("denied the request for more budget", "decision")]
        return [_do(_tail("asked you to approve", _asked(asked)), "decision")]
    if decision.lower() in ("continue", "drop", "ship", "stop"):                               # the owner's answer, read
        drops = r.get("drop_items") if isinstance(r.get("drop_items"), list) else []
        leave = "leave out " + (_count(len(drops), "item") if drops else "items")
        said = {"continue": "carry on", "ship": "finish as it is", "stop": "stop", "drop": leave}
        return [_do(f"read your answer: {said[decision.lower()]}", "decision")]
    if isinstance(r.get("done"), bool):                                                        # is the goal reached?
        ask = _strings(r.get("requester_questions"))
        said = "decided the goal is reached" if r["done"] else "decided the goal is not reached yet"
        return [_do(said + (f"; needs you: {_snip(ask[0])}" if ask and not r["done"] else ""), "decision")]
    return []


def _adaptation(r: Mapping, saved: set[str]) -> list[OutputItem]:
    act, verdict = _text(r.get("act")).upper(), _text(r.get("verdict")).upper()
    names = _workflows(r.get("workflows"))
    if verdict in ("CHECK_WRONG", "BUILD_WRONG"):                                              # a failed atom's verdict
        atom = f" for {_text(r.get('atom'))}" if _text(r.get("atom")) else ""
        if verdict == "CHECK_WRONG":
            checks = len(r.get("verification")) if isinstance(r.get("verification"), list) else 0
            return [_do(f"judged the check wrong{atom}: sent {_count(checks, 'corrected check')}", "verdict")]
        return [_do(_tail(f"judged the build wrong{atom}", _snip(_first(r.get("build_wrong_reason"), r.get("say")))), "verdict")]
    if act == "PROPOSE" or (not act and names):
        left = len(r.get("left_out")) if isinstance(r.get("left_out"), list) else 0
        said = _tail(f"a proposal of {_count(len(names), 'workflow')}", _list(names)) + (f"; left out {_count(left, 'item')}" if left else "")
        return [_item("make", said, "proposal", _where("workflows.json", saved))]
    if act == "REVISE":
        said = _tail(f"a revised proposal of {_count(len(names), 'workflow')}", _list(names))
        return [_item("make", said, "proposal", _where("workflows.json", saved))]
    if act == "POLICY_QUESTION":
        return [_do(f"asked Identity: {_snip(r.get('question'))}", "question")]
    if act == "DISPUTE":
        d = r.get("dispute") if isinstance(r.get("dispute"), Mapping) else {}
        about, with_ = _text(d.get("about")) or "a finding", _text(d.get("with")) or "its owner"
        return [_do(_tail(f"disputed {about} with {with_}", _snip(d.get("reason"))), "dispute", _where("conflicts.json", saved))]
    if act in ("ACCEPT", "PARK"):
        return [_do("accepted Priority's decision" if act == "ACCEPT" else "parked the proposal", "decision")]
    return []


def _priced(w: Mapping) -> str:
    label = _workflows([w])
    limit = _whole((w.get("envelope") or {}).get("money_limit")) if isinstance(w.get("envelope"), Mapping) else None
    return clip((label[0] if label else "a workflow") + (f" (money {limit})" if limit is not None else ""), 80)


def _priority(r: Mapping, saved: set[str]) -> list[OutputItem]:
    decision = _text(r.get("decision")).upper()
    priced = _list([_priced(w) for w in _dicts(r.get("workflows"))])
    count = _count(len(_dicts(r.get("workflows"))), "workflow")
    where = _where("workflows.json", saved)
    if decision == "GRANT":
        return [_do(_tail(f"GRANT: funded {count}", priced), "decision", where)]
    if decision == "COUNTER":
        return [_do(_tail(f"COUNTER: {count} at another price", priced), "decision", where)]
    if decision == "REFUSE":
        return [_do("REFUSE: funded nothing", "decision", where)]
    if decision == "HOLD":
        return [_do("HOLD: the workflow waits, it is over its envelope", "decision")]
    if decision == "REQUEST_APPROVAL":
        return [_do("REQUEST_APPROVAL: asked Identity to approve more", "decision")]
    return []


def _coordination(r: Mapping, saved: set[str]) -> list[OutputItem]:
    holds, rule = _dicts(r.get("holds")), _snip(r.get("rule"), 120)
    if not isinstance(r.get("order"), list) and not holds and not rule:
        return []
    order = _strings(r.get("order"))
    where = _where("workflows.json", saved)
    said = f"scheduled {_count(len(order), 'workflow')} in this order: {_list(order, 6)}" if order else "scheduled nothing to run"
    items = [_item("make", said + (f". Rule: {rule}" if rule else ""), "order", where)]
    if holds:
        why = [(_text(h.get("id")) or "a workflow") + (f" (missing {_snip(h.get('missing'), 60)})" if _text(h.get("missing")) else "") for h in holds]
        items.append(_do(f"held {_count(len(holds), 'workflow')}: {_list(why, 3)}", "hold", where))
    return items


def _audit(r: Mapping, saved: set[str]) -> list[OutputItem]:
    findings, rubric = _dicts(r.get("findings")), _dicts(r.get("rubric"))
    rows = [("finding", row) for row in findings] + [("rubric row", row) for row in rubric]
    if not rows:
        return []
    where = _where("audits.json", saved)
    tally: dict[str, int] = {}
    for _, row in rows:
        key = _text(row.get("verdict")).upper()
        tally[key] = tally.get(key, 0) + 1
    parts = []
    for key in sorted(tally, key=lambda k: list(_VERDICTS).index(k) if k in _VERDICTS else len(_VERDICTS)):      # always the same order: passes first
        plural, single = _VERDICTS.get(key, (key.lower().replace("_", " ") or "unjudged", ""))
        parts.append(f"{tally[key]} {single if tally[key] == 1 and single else plural}")
    what = {(True, False): "finding", (False, True): "rubric row"}.get((bool(findings), bool(rubric)))
    what = _count(len(rows), what) if what else f"{len(rows)} findings and rubric rows"
    items = [_item("make", f"{what}: {', '.join(parts)}", "findings", where)]
    shown = [(kind, row) for kind, row in rows if _text(row.get("verdict")).upper() not in _PASSING]
    for kind, row in shown[:ROWS]:
        key = _text(row.get("verdict")).upper()
        verdict = _VERDICTS.get(key, (key.lower().replace("_", " ") or "not judged",) * 2)[1]
        evidence = _snip(row.get("evidence"))
        items.append(_item("make", f"{kind} {_text(row.get('id')) or '?'}: {verdict}" + (f", {evidence}" if evidence else ""), "finding", where))
    if len(shown) > ROWS:
        items.append(_item("make", f"and {len(shown) - ROWS} more that do not pass", "findings", where))
    return items


_BY_FUNCTION: Final = {"identity": _identity, "adaptation": _adaptation, "priority": _priority, "coordination": _coordination, "audit": _audit}


def _said(r: Mapping) -> list[OutputItem]:
    """The fallback: the reply's own sentence, when its kind has no words of its own or it does not read as its kind."""
    text = _first(r.get("say"), r.get("to_requester"), r.get("to_agents"), r.get("text"))
    return [_do(f"said: {_snip(text, 160)}", "reply", THE_REPLY)] if text else []


# ---- what the turn did -------------------------------------------------------------------------------------------------------

def _target(word: Any) -> str:
    """Who a message went to: `user` and `requester` are the owner (`you`), a function or a builder keeps its name."""
    text = _text(word)
    return "you" if text.lower() in ("user", "requester") else (text[:1].upper() + text[1:] if text else "")


def _posted(buf: TurnBuffer) -> list[OutputItem]:
    mine = [m for m in buf.posted if isinstance(m, Mapping) and m.get("who") == buf.turn.function]
    if not mine:
        return []
    to = [t for t in dict.fromkeys(_target(m.get("next")) for m in mine) if t]
    return [_item("do", f"posted {_count(len(mine), 'message')}" + (f" to {_and(to)}" if to else ""), "message", "chat")]


def _code(buf: TurnBuffer) -> list[OutputItem]:
    """What J2's own code said during the turn (the system and the validator: a hand-off by code, a rejection, the checks it ran), told
    by its first line: a turn can be only that, as Coordination's is when the queue is empty."""
    voices = [m for m in buf.posted if isinstance(m, Mapping) and m.get("who") in ("system", "validator") and _text(m.get("text"))]
    if not voices:
        return []
    return [_item("do", f"code posted {_count(len(voices), 'message')}: {_snip(voices[0].get('text'), 140)}", "message", "chat")]


def _saved(buf: TurnBuffer, told: list[OutputItem]) -> list[OutputItem]:
    """The record files the turn saved that no sentence about the reply already names."""
    covered = {item.ref for item in told}
    left = [name for name in dict.fromkeys(buf.saved) if name in RECORD_WORDS and name not in covered]
    if not left:
        return []
    return [_item("make", "saved " + _and([RECORD_WORDS[name] for name in left]), "record", left[0])]


# ---- the two entry points ----------------------------------------------------------------------------------------------------

def reply_record(buf: TurnBuffer) -> Optional[AtomReply]:
    """The last reply the node got, printed, cut to `REPLY_TEXT_MAX` characters. None when the node's latest call gave no object
    (an older reply is not shown for a newer call that gave none: the checks judge the latest call too)."""
    call = buf.calls[-1] if buf.calls else None
    if call is None or not isinstance(call.reply, dict):
        return None
    try:
        text = json.dumps(call.reply, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return None
    return AtomReply(text=clip(text, REPLY_TEXT_MAX), clipped=len(text) > REPLY_TEXT_MAX)


def turn_output(buf: TurnBuffer) -> tuple[list[OutputItem], Optional[AtomReply]]:
    """What a function's turn has produced so far, as the plain sentences of `Atom.produced` and the last reply."""
    function = buf.turn.function
    reply = buf.calls[-1].reply if buf.calls and isinstance(buf.calls[-1].reply, dict) else None
    saved = set(buf.saved)
    told: list[OutputItem] = []
    if reply is not None:
        told = (_BY_FUNCTION[function](reply, saved) if function in _BY_FUNCTION else []) or _said(reply)
    items = [*told, *_posted(buf), *_code(buf)]
    items += _saved(buf, told)
    return (items or [_item("do", NOTHING, "nothing", "this turn")])[:40], reply_record(buf)


def manual_output(buf: TurnBuffer) -> list[OutputItem]:
    """The manual atom of a question is done by the owner: what it produced is their answer (none until they give it)."""
    answers = [m for m in buf.posted if isinstance(m, Mapping) and m.get("who") == "user" and _text(m.get("text"))]
    if not answers:
        return []
    last = answers[-1]
    return [_item("do", f"you answered: {_snip(last.get('text'), 200)}", "answer", f"chat message {last.get('id')}" if last.get("id") else "chat")]
