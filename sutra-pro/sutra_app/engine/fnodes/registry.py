"""The verify registry: 14 named checks, each a pure function `fn(ev: Evidence, args: tuple[str, ...]) -> Outcome`
(function-nodes.md section 4, S4-fnodes-02).

A check has no clock, no network and no file access, and it changes nothing it is given: it reads `Evidence` (evidence.py)
and answers with an `Outcome`. The layer's runner (WP E6) calls `REGISTRY.run(name, evidence, args)` and turns the Outcome
into the library's `CheckResult` (exit 0 for ok or na, 1 for a failure, 127 when it cannot run a check at all).

How an Outcome is read (the runner's contract):

    ok, nothing else        the check passed
    ok, changed=(...)       passed because J2's own code repaired, templated or dropped something: the atom closes
                            `RECOVERED: <evidence>`; `changed` names what code changed
    ok, waived=True         passed because J2 accepted a concern on record: the atom closes `WAIVED: <evidence>`
    ok, na=True             the check does not apply to this reply or turn
    not ok                  a failure; `evidence` says what is missing or wrong

The kinds: a `gate` check judges what J2 retried or accepted; an `override` check proves the outcome after J2's code
corrected the reply (the evidence narrates the correction). The phases: `reply` (judged on each reply of the node, a
failure is a live try), `turn` (judged once at turn end on the whole turn) and `event` (judged when its event arrives). A
check that serves two phases tells them apart by `ev.outcome` (None before the turn has ended).

J2's own functions are the oracle. `stamp_check`, `workable_problems` and the three regexes are ports of the vendored
`j2.py` code (the parity tests tie them to it); `design_problems` and `problems` are `j2_check`'s own functions; the gate
is `j2_realization.THRESHOLD`'s value. Four checks read strings J2 posts (`Validator rejected`, the two Priority price
notes, the charter acceptance note, the `Budget n/m used` line): the constants below hold them and the parity tests pin
each against the vendored source.
"""
import json
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

import sutra_app.library.functions  # noqa: F401  (registers the reply families that reply-valid parses against)
from sutra_app.engine import j2_check
from sutra_app.library.atom import REGISTRY_CHECKS, check_arity
from sutra_app.library.node import may_hand_off
from sutra_app.library.registry import RegistryError
from sutra_app.library.replies import ReplyInvalid, ReplyParser
from sutra_app.library.types import clip

from .evidence import Evidence

__all__ = [
    "Outcome", "CheckSpec", "CheckRegistry", "REGISTRY", "CheckFn", "CheckArgsError", "UnknownCheck", "GATE", "NOT_CHECKABLE",
    "AGENT_CONTENT", "USER_CONTENT", "J2_ROUTES", "stamp_check", "workable_problems", "J2_STRINGS",
]

EVIDENCE_MAX: Final = 2000
GATE: Final = 0.80                         # j2_realization.THRESHOLD, the plan confidence the judge gate asks for

# J2's own regexes, character for character (j2.py `J2Run.NOT_CHECKABLE`, `AGENT_CONTENT`, `USER_CONTENT`)
NOT_CHECKABLE: Final = re.compile(r"\b(requester|audit\w*|launch\w*|go(?:es|ing)? live|verif\w*|approv\w*|sign(?:ed)?[- ]?off)\b",
                                  re.I)
AGENT_CONTENT: Final = re.compile(r"@(?!Requester\b)[A-Za-z]|\b[WFRC]-\d+\b|\bre-?pric|\b\d+\s*units?\b|\b(?:Adaptation|"
                                  r"Priority|Coordination|Validator|Audit)\b|\b(?:workflows?|GRANT|COUNTER|REFUSE|envelope|"
                                  r"rate[- ]card)\b", re.I)
USER_CONTENT: Final = re.compile(r"@Requester\b|\bthank(?:s| you)\b|\bI(?:'ll| will) start\b|\bwould you like\b|"
                                 r"\bdo you want\b|\byour (?:site|website|shop|store|business|brief)\b", re.I)
_QUOTED: Final = re.compile(r"'[^']*'|\"[^\"]*\"|‘[^’]*’|“[^”]*”")
_FINDING_ID: Final = re.compile(r"F-\d+")

# What J2 posts or writes that the checks read; the parity test finds each fragment in the vendored j2.py
CHARTER_ACCEPTED: Final = "Charter accepted after two attempts"
REJECTED_PREFIX: Final = "Validator rejected '"
KEPT_PRICE: Final = "carried no price for"
KEPT_PRICE_TAIL: Final = "code keeps the price it had already computed: "
OVER_BUDGET_NOTE: Final = "exceeds the remaining budget ("
NO_FINDING_NOTE: Final = "Audit filed no finding for this item."
NO_EVIDENCE_NOTE: Final = "Marked PASS with no evidence"
MEASURED_NOTE: Final = "Measured by code: "
CODE_HANDOFF: Final = "Hand-off by code"
J2_STRINGS: Final = (CHARTER_ACCEPTED, REJECTED_PREFIX, KEPT_PRICE, KEPT_PRICE_TAIL, OVER_BUDGET_NOTE, "Budget {self.spent}/{self.budget} used",
                     NO_FINDING_NOTE, NO_EVIDENCE_NOTE, MEASURED_NOTE, CODE_HANDOFF)

# j2.py `ROUTES`: who may hand the turn to whom in J2. The library's HANDOFFS narrow it for the app (audit -> identity only), but
# a DISPUTE turn is J2's own route to the party disputed, so there J2's table also counts.
J2_ROUTES: Final = MappingProxyType({
    "identity": ("user", "adaptation", "priority", "coordination", "audit"), "adaptation": ("priority", "identity", "audit", "coordination"),
    "priority": ("adaptation", "identity", "coordination"), "coordination": ("priority", "adaptation", "identity"),
    "audit": ("adaptation", "identity")})

_BUDGET_USED_RE: Final = re.compile(r"Budget (\d+)/(\d+) used")
_LEFT_RE: Final = re.compile(r"(\d+) left")
_REMAINING_RE: Final = re.compile(r"remaining budget (\d+)")
_TABLE_COST_RE: Final = re.compile(r"\(cost (\d+),")
_OVER_RE: Final = re.compile(r"GRANT of (\d+) exceeds the remaining budget \((\d+)\)")
_KEPT_PAIR_RE: Final = re.compile(r"(?:^|, )(.+?) \((-?\d+)\)(?=, |\.?$)")


class UnknownCheck(KeyError):
    """A check name that is not one of the 14 (the runner reports exit code 127)."""


class CheckArgsError(ValueError):
    """The wrong number of arguments for a check (the library's `check_arity` is the rule)."""


class Outcome(BaseModel):
    """What one check says. See the module docstring for how the runner reads the flags."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    evidence: str = ""
    changed: tuple[str, ...] = ()
    na: bool = False
    waived: bool = False

    @model_validator(mode="before")
    @classmethod
    def _clip_evidence(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and isinstance(data.get("evidence"), str):
            return {**data, "evidence": clip(data["evidence"], EVIDENCE_MAX)}
        return data

    @model_validator(mode="after")
    def _flags_fit_together(self) -> "Outcome":
        if not self.ok and (self.na or self.waived or self.changed):
            raise ValueError("a failed outcome cannot be na, waived or changed")
        if self.na and (self.waived or self.changed):
            raise ValueError("an outcome that does not apply cannot be waived or changed")
        if self.waived and self.changed:
            raise ValueError("an outcome is recovered or waived, not both")
        return self

    @property
    def exit_code(self) -> int:
        """The plugin's exit code for the library's `CheckResult`: 0 passed (or does not apply), 1 failed."""
        return 0 if self.ok else 1


def _ok(evidence: str, *, changed: tuple[str, ...] = (), waived: bool = False) -> Outcome:
    return Outcome(ok=True, evidence=evidence, changed=changed, waived=waived)


def _fail(evidence: str) -> Outcome:
    return Outcome(ok=False, evidence=evidence)


def _na(evidence: str) -> Outcome:
    return Outcome(ok=True, evidence=evidence, na=True)


def _missing(what: str) -> Outcome:
    return _fail(f"missing: {what}")


CheckFn = Callable[[Evidence, tuple[str, ...]], Outcome]


# ---- ports of J2's own code -------------------------------------------------------------------------------------------

def stamp_check(goal: Optional[Mapping]) -> tuple[bool, str]:
    """`J2Run._stamp_check`: (passes, why). The charter has a statement, at least 3 done-when items, and none that depends
    on the Requester, Audit, verification, approval or launch (quoted text is a label the site shows, not a dependency)."""
    g = goal or {}
    if not g.get("statement"):
        return False, "goal has no statement"
    if len(g.get("done_when") or []) < 3:
        return False, "fewer than 3 'done when' criteria"
    unquoted = lambda d: _QUOTED.sub("", str(d))
    bad = [d for d in g["done_when"] if NOT_CHECKABLE.search(unquoted(d))]
    if bad:
        return False, ("these done-when items can't be checked by reading the site (they depend on the Requester, "
                       "Audit, verification, approval or launch); rephrase them as something the site shows, and "
                       "record a fact only the Requester can give in to_be_confirmed: " + json.dumps(bad))
    return True, "passes code checks"


def _blocks(c: Mapping) -> bool:
    """j2.py `blocks`: an unmet condition that stops workable() (a warning never does)."""
    return not c["met"] and c.get("severity") != "warn"


def workable_problems(audit: Optional[Mapping]) -> list[str]:
    """j2.py `workable(audit)`: code's verdict on an audit, no model; [] means workable."""
    if not audit:
        return ["no site has been audited yet"]
    num = lambda r: r["id"][2:] if _FINDING_ID.fullmatch(str(r["id"])) else r["item"]
    ok = set(audit.get("accepted") or [])
    out = [f"done-when item {num(r)} ({r['id']} {r['verdict']}): {r['criterion']}" for r in audit["results"]
           if not r["pass"] and r["criterion"] not in ok]
    if audit.get("output", "website") != "website":
        return (out + [f"document rubric {r['id']} ({r['verdict']}): {r['criterion']}" for r in audit.get("rubric", [])
                       if not r["pass"]]
                + [f"necessary condition {c['id']} not met: {c['text']} ({c['evidence']})"
                   for c in audit.get("conditions") or [] if _blocks(c)])
    out += [f"design rubric {r['id']} ({r['verdict']}): {r['criterion']}" for r in audit.get("rubric", [])
            if not r["pass"] and r["id"] not in ok]
    out += [f"necessary condition {c['id']} not met: {c['text']} ({c['evidence']})"
            for c in audit.get("conditions") or [] if _blocks(c) and c["id"] not in ok]
    mech = audit.get("mechanical") or {}
    if not mech.get("available"):
        return out + [f"render check didn't run, so JS errors, overflow and forms are unverified: {mech.get('note')}"]
    return out + j2_check.problems(mech)


def _as_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def _granted(w: Mapping) -> int:
    """The money a granted workflow carries as the reply states it: `envelope.money_limit`, else its cost or estimate
    (j2.py `granted` without the rate card, which is run state a pure check cannot see)."""
    limit = _as_int((w.get("envelope") or {}).get("money_limit")) if isinstance(w.get("envelope"), Mapping) else 0
    if limit > 0:
        return limit
    est = w.get("estimated_resources") if isinstance(w.get("estimated_resources"), Mapping) else {}
    return _as_int(w.get("cost") or est.get("money"))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _names(items: list[str]) -> str:
    return ", ".join(dict.fromkeys(items))


# ---- the checks -----------------------------------------------------------------------------------------------------

_PARSER: Final = ReplyParser()


def reply_valid(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """The node's reply is accepted by the library's closed model of `family` and `kind` (`a|b` lists alternatives)."""
    family, kinds = args
    if ev.call is None and ev.reply is None:
        return _na("the turn made no call by this function")
    if ev.reply is None:
        return _missing("the call has no reply")
    best: Optional[ReplyInvalid] = None
    for kind in [k for k in kinds.split("|") if k]:
        try:
            parsed = _PARSER.parse(family, ev.reply, kind=kind, clip_text=True)
        except ReplyInvalid as exc:
            if best is None or len(exc.violations) < len(best.violations):
                best = exc
        except RegistryError as exc:
            return _fail(f"{family}/{kind} is not a registered reply: {exc}")
        else:
            if parsed.clipped:      # D158: a text over its cap is read cut to it, and the cut is a concern on record
                shown = ", ".join(parsed.clipped[:6]) + (f" and {len(parsed.clipped) - 6} more" if len(parsed.clipped) > 6 else "")
                return _ok(f"text over its limit, read cut to it: {shown}", changed=tuple(parsed.clipped))
            return _ok("ok")
    if best is None:
        return _fail(f"no reply kind named in {kinds!r}")
    return _fail("; ".join(f"{v.path}: {v.message}" if v.path else v.message for v in best.violations[:3]) or best.code)


def turn_posted(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """The turn posted a message or saved a record, and each message it posted names a next speaker it may hand to."""
    function = ev.turn.function
    count = len(ev.posted) or (len(ev.outcome.messages) if ev.outcome else 0)
    saved = sorted(ev.saved_names)
    if not count and not saved:
        return _fail("no message, no record")
    targets: list[str] = []
    bad: list[str] = []
    for m in ev.posted:
        nxt = str(m.get("next") or "").strip().lower()
        if m.get("who") != function or not nxt:
            continue
        target = "requester" if nxt == "user" else nxt
        targets.append(target.capitalize())
        if m.get("auto") or CODE_HANDOFF in str(m.get("text") or ""):
            continue
        if not may_hand_off(function, target) and not (ev.turn.kind == "dispute" and nxt in J2_ROUTES.get(function, ())):
            bad.append(f"next={target} is no route of {function}")
    if bad:
        return _fail("; ".join(dict.fromkeys(bad)))
    said = f"posted {_plural(count, 'message')}" if count else "no message"
    if targets:
        said += f" to {_names(targets)}"
    return _ok(said + (f", saved {', '.join(saved)}" if saved and not count else ""))


def charter_stamp(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """The charter saved this turn passes J2's stamp, or the owner is being asked (na); a second failure that J2 accepted
    on record ("Charter accepted after two attempts") closes the atom waived."""
    reply = ev.reply
    if isinstance(reply, dict) and not reply.get("enough") and reply.get("questions"):
        return _na("the owner is asked")
    if "goal.json" not in ev.saved_names:
        return _missing("goal.json not saved this turn")
    goal = ev.records.get("goal.json")
    if not isinstance(goal, dict):
        return _missing("goal.json holds no charter")
    passed, why = stamp_check(goal)
    if passed:
        return _ok(f"statement present, {_plural(len(goal['done_when']), 'done-when item')}")
    if any(CHARTER_ACCEPTED in text for text in ev.system_texts()):
        return _ok(why, waived=True)
    return _fail(why)


def workable(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """Identity does not declare the goal reached while J2's own `workable(audit)` lists problems; code wins."""
    audit = ev.last_audit()
    if audit is None:
        return _missing("no audit in audits.json")
    try:
        problems = workable_problems(audit)
    except (KeyError, TypeError, AttributeError) as exc:
        return _fail(f"the audit record is malformed: {type(exc).__name__}: {exc}")
    out = ev.outcome
    ended = out is not None and out.next is None and out.result != "paused" and out.result != "error"
    n = _plural(len(problems), "problem")
    if ended:
        return _fail(f"ended with {n} open") if problems else _ok("workable (code): yes, goal reached")
    if not problems:
        return _ok("workable (code): yes, the turn goes on")
    said_done = isinstance(ev.reply, dict) and ev.reply.get("done") is True
    return _ok(f"not workable: {n}, back to J2.b", changed=("done=true overridden",) if said_done else ())


def _audience_problems(req: str, agents: str) -> list[str]:
    return ([f"to_requester has agent content ({m.group(0)!r})"] if (m := AGENT_CONTENT.search(req)) else []) \
        + ([f"to_agents reads as user-facing ({m.group(0)!r})"] if (m := USER_CONTENT.search(agents)) else [])


def audience_split(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """One message, one addressee: no team content in `to_requester`, nothing user-facing in `to_agents`; at turn end the
    texts J2 posted obey the same rules. A mixed reply that J2 regenerated or templated is recovered."""
    reply = ev.reply
    if not isinstance(reply, dict) or "to_requester" not in reply:
        return _na("the reply has no to_requester")
    if reply.get("enough") is False:
        return _na("the owner is asked")
    req = str(reply.get("to_requester") or "")
    agents = str(reply["to_agents"] if "to_agents" in reply else reply.get("say") or "")
    reply_bad = _audience_problems(req, agents)
    if ev.outcome is None:
        return _fail("; ".join(reply_bad)) if reply_bad else _ok("to_requester is plain")
    posted_bad: list[str] = []
    tagged = 0
    for m in ev.posted:
        if m.get("who") != "identity" or not m.get("audience"):
            continue
        tagged += 1
        text = str(m.get("text") or "")
        if m.get("audience") == "user":
            posted_bad += _audience_problems(text, "")
        else:
            posted_bad += _audience_problems("", text)
    if posted_bad:
        return _fail("; ".join(posted_bad))
    if reply_bad and not tagged:
        return _fail("; ".join(reply_bad) + " (nothing posted shows the fix)")
    if reply_bad:
        return _ok("to_requester is plain after the fix; " + "; ".join(reply_bad), changed=("template",))
    return _ok("to_requester is plain")


def _is_atom_rejection(m: Mapping) -> bool:
    return (m.get("who") == "system" and isinstance(m.get("rejected"), str) and m["rejected"] not in ("plan", "charter", "")
            and str(m.get("text") or "").startswith(REJECTED_PREFIX))


def _reason_of(m: Mapping) -> str:
    text = str(m.get("text") or "")
    reason = text.partition("': ")[2]
    return reason[:-1] if reason.endswith(".") else reason


def _drawn_by_last_reply(rejections: list[dict], replies: int) -> list[dict]:
    """The rejection posts that followed the node's last reply. With `after_reply` on the messages it is exact; without it
    J2's flow is the guide: a rejection makes J2 ask once more, so a batch of rejections belongs to each reply but the
    last one clean, and a name that comes up again starts the next batch."""
    if not rejections:
        return []
    if any("after_reply" in m for m in rejections):
        return [m for m in rejections if _as_int(m.get("after_reply"), 0) >= replies]
    batches: list[list[dict]] = [[]]
    for m in rejections:
        if any(x["rejected"] == m["rejected"] for x in batches[-1]):
            batches.append([])
        batches[-1].append(m)
    return batches[-1] if len(batches) >= 2 or replies <= 1 else []


def atom_rules(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """Adaptation's last reply drew no `Validator rejected` post. A rejection after the last reply means J2 drops the
    incomplete workflows (recovered); the check fails when nothing is left or the turn broke off."""
    reply = ev.reply
    workflows = reply.get("workflows") if isinstance(reply, dict) else None
    if not isinstance(workflows, list):
        return _na("the reply proposes no workflows")
    rejections = [m for m in ev.posted if _is_atom_rejection(m)]
    last = _drawn_by_last_reply(rejections, len(ev.replies) or 1)
    total = _plural(len([w for w in workflows if isinstance(w, dict)]), "workflow")
    if not last:
        return _ok(f"{total}, atoms complete" + (" after a retry" if rejections else ""))
    names = list(dict.fromkeys(m["rejected"] for m in last))
    said = "; ".join(f"{m['rejected']} ({_reason_of(m)})" for m in last)
    kept = [w for w in workflows if isinstance(w, dict) and w.get("name") not in names]
    if kept and not (ev.outcome and ev.outcome.result == "error"):
        return _ok(f"{_plural(len(kept), 'workflow')} kept; rejected: {said}", changed=(f"dropped {_names(names)}",))
    return _fail(f"rejected: {said}")


def judge_gate(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """The plan saved this turn (the first website plan or a full re-plan) has plan confidence of 0.80 or more; below the
    gate J2 does not fund the workflows that are not ready, which it accepts on record (waived)."""
    if "realization.json" not in ev.saved_names:
        return _na("no plan saved this turn")
    plan = ev.records.get("realization.json")
    conf = plan.get("plan_confidence") if isinstance(plan, dict) else None
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return _missing("realization.json has no plan_confidence")
    rounds = [r for r in plan.get("rounds") or [] if isinstance(r, dict)]
    steps: list[float] = []
    for r in rounds:
        scores = [s.get("score") for s in (r.get("scores") or {}).values() if isinstance(s, dict)
                  and isinstance(s.get("score"), (int, float))]
        if scores:
            steps.append(min(scores))
    after = ""
    if len(rounds) > 1:
        after = f" after {_plural(len(rounds) - 1, 'revision round')}" + (f" ({', '.join(f'{s:.2f}' for s in steps)})" if steps else "")
    if conf >= GATE:
        return _ok(f"plan {conf:.2f}{after}")
    not_ready = [str(x.get("workflow")) for x in plan.get("not_ready") or [] if isinstance(x, dict)]
    return _ok(f"plan {conf:.2f} < {GATE:.2f}; not ready: {', '.join(not_ready) or 'none named'}", waived=True)


def _kept_prices(texts: list[str]) -> dict[str, int]:
    """Name -> price from the system notes `Priority's GRANT carried no price for ...; code keeps the price ...: A (12).`"""
    kept: dict[str, int] = {}
    for text in texts:
        if KEPT_PRICE in text and KEPT_PRICE_TAIL in text:
            for name, amount in _KEPT_PAIR_RE.findall(text.partition(KEPT_PRICE_TAIL)[2]):
                kept[name] = int(amount)
    return kept


def price_kept(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """A GRANT prices every workflow it funds; a price Priority dropped is kept by code (recovered), else the check fails."""
    reply = ev.reply
    if not isinstance(reply, dict):
        return _missing("no Priority reply")
    decision = str(reply.get("decision") or "").upper()
    if decision != "GRANT":
        return _ok(f"{decision or 'no decision'}: nothing granted")
    workflows = [w for w in reply.get("workflows") or [] if isinstance(w, dict)]
    if not workflows:
        return _ok("GRANT of the table: its prices are code's")
    kept = _kept_prices(ev.system_texts())
    priced: list[str] = []
    recovered: list[str] = []
    lost: list[str] = []
    for w in workflows:
        name = str(w.get("name") or "?")
        amount = _granted(w)
        if amount > 0:
            priced.append(f"{name} {amount}")
        elif name in kept:
            recovered.append(f"{name} ({kept[name]})")
        else:
            lost.append(name)
    if lost:
        return _fail(f"no price for {', '.join(lost)} after the second ask")
    if recovered:
        return _ok(f"price kept for {', '.join(recovered)}", changed=tuple(f"price kept for {r}" for r in recovered))
    return _ok(f"GRANT priced: {', '.join(priced)}")


def _budget_left(ev: Evidence) -> Optional[int]:
    if ev.call is not None:
        for pair in ev.call.inputs:
            if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] == "ledger" and (m := _LEFT_RE.search(str(pair[1]))):
                return int(m.group(1))
    if ev.prompt and (m := _REMAINING_RE.search(ev.prompt)):
        return int(m.group(1))
    return None


def within_budget(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """Price and ruling: a GRANT stays within the budget left, or the posted decision is REFUSE (code turned it). Envelope:
    an `allowed` post only when what is spent fits the budget."""
    kind = ev.turn.kind
    if kind == "envelope":
        posts = [m for m in ev.posted if m.get("who") == "priority" and "envelope" in m]
        if not posts:
            return _missing("no envelope post by Priority")
        post = posts[-1]
        if post["envelope"] != "allowed":
            return _ok(f"envelope {post['envelope']}: the run does not start")
        m = _BUDGET_USED_RE.search(str(post.get("text") or ""))
        if not m:
            return _missing("the allowed post names no budget")
        spent, budget = int(m.group(1)), int(m.group(2))
        return _ok(f"allowed, budget {spent}/{budget} used") if spent <= budget else _fail(f"allowed with budget {spent}/{budget} used")
    if kind not in ("price", "ruling", "proposal"):
        return _na("no price or envelope in this turn")
    reply = ev.reply
    if not isinstance(reply, dict):
        return _missing("no Priority reply")
    if str(reply.get("decision") or "").upper() != "GRANT":
        return _ok(f"{str(reply.get('decision') or 'no decision').upper()}: nothing granted")
    left = _budget_left(ev)
    workflows = [w for w in reply.get("workflows") or [] if isinstance(w, dict)]
    total: Optional[int] = sum(_granted(w) for w in workflows) if workflows else None
    if total is None and ev.prompt and (m := _TABLE_COST_RE.search(ev.prompt)):
        total = int(m.group(1))
    note = next((m for t in ev.system_texts() if (m := _OVER_RE.search(t))), None)
    if note is not None:
        total, left = int(note.group(1)), int(note.group(2))
    if left is None:
        return _missing("the budget left (no ledger line in the call)")
    if total is None:
        return _ok(f"GRANT of the table, {left} left")
    if total <= left:
        return _ok(f"GRANT {total} of {left} left")
    posted = [str(m.get("decision") or "").upper() for m in ev.posted if m.get("who") == "priority" and m.get("decision")]
    if not posted:
        return _missing("no Priority decision posted")
    said = f"GRANT {total} > {left} left, posted {posted[-1]}"
    return _ok(said, changed=("GRANT turned into REFUSE",)) if posted[-1] == "REFUSE" else _fail(said)


def order_registered(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """The schedule names only workflows registered at turn start, each once, and every registered workflow that is not
    held appears. What code filtered or appended is narrated (recovered)."""
    workflows = ev.before.get("workflows.json")
    if not isinstance(workflows, list):
        return _missing("workflows.json at turn start")
    registered = [str(w["id"]) for w in workflows if isinstance(w, dict) and w.get("status") in ("registered", "held") and "id" in w]
    reply = ev.reply if isinstance(ev.reply, dict) else None
    if reply is None:
        return _na("no workflow is registered, nothing to schedule") if not registered else _missing("no Coordination reply")
    ordered = [str(i) for i in reply.get("order") or []]
    held = [str(h.get("id")) for h in reply.get("holds") or [] if isinstance(h, dict) and str(h.get("id")) in registered]
    posts = [m for m in ev.posted if m.get("who") == "coordination" and "schedule" in m]
    scheduled = [str(i) for i in posts[-1]["schedule"] or []] if posts else [i for i in ordered if i not in held]
    problems = [f"{i} is not registered" for i in dict.fromkeys(scheduled) if i not in registered]
    problems += [f"{i} is scheduled twice" for i in dict.fromkeys(scheduled) if scheduled.count(i) > 1]
    problems += [f"{i} is neither scheduled nor held" for i in registered if i not in scheduled and i not in held]
    if problems:
        return _fail("; ".join(problems))
    dropped = [i for i in dict.fromkeys(ordered) if i not in registered]
    appended = [i for i in scheduled if i not in ordered]
    said = f"schedule {' > '.join(scheduled) or 'none'}" + (f"; {', '.join(dict.fromkeys(held))} held" if held else "")
    changes = [f"dropped {i} (not registered)" for i in dropped] + [f"appended {i}" for i in appended]
    return _ok("; ".join([said, *changes]) if changes else said, changed=tuple(changes))


def _rows(audit: Mapping, *keys: str) -> list[dict]:
    return [r for key in keys for r in (audit.get(key) or []) if isinstance(r, dict)]


def finding_per_item(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """The audit saved this turn has exactly one result per done-when item (1..n, each once), and no row names an atom
    owned by this department's Audit. An item J2 filled in as BLOCKED_BY_EVIDENCE is narrated (recovered)."""
    if "audits.json" not in ev.saved_names:
        return _missing("audits.json not saved this turn")
    audit = ev.last_audit()
    goal = ev.records.get("goal.json")
    if audit is None:
        return _missing("no audit in audits.json")
    done_when = goal.get("done_when") if isinstance(goal, dict) else None
    if not isinstance(done_when, list):
        return _missing("goal.json done_when")
    n = len(done_when)
    items = [_as_int(r.get("item"), -1) for r in _rows(audit, "results")]
    problems = [f"item {i} has no finding" for i in range(1, n + 1) if i not in items]
    problems += [f"item {i} has {items.count(i)} findings" for i in range(1, n + 1) if items.count(i) > 1]
    problems += [f"a finding is about item {i}, which the charter does not have" for i in dict.fromkeys(items) if i < 1 or i > n]
    mine = f"{ev.turn.dept_id}.audit"
    for row in _rows(audit, "results", "rubric", "extra_issues"):
        atom = row.get("atom")
        if atom and ev.owners.get(str(atom)) in (mine, "audit"):
            problems.append(f"{row.get('id')} names atom {atom}, which Audit owns")
    if problems:
        return _fail("; ".join(problems))
    filled = [f"item {_as_int(r.get('item'))} had no finding: recorded BLOCKED_BY_EVIDENCE ({r.get('id')})"
              for r in _rows(audit, "results") if str(r.get("note") or "").startswith(NO_FINDING_NOTE)]
    return _ok("; ".join([f"{_plural(n, 'item')}, {_plural(len(items), 'finding')}", *filled]), changed=tuple(filled))


def pass_needs_proof(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """No result or rubric row of the audit saved this turn has `pass` true with an empty note. A PASS that J2 downgraded
    to BLOCKED_BY_EVIDENCE is narrated (recovered)."""
    if "audits.json" not in ev.saved_names:
        return _missing("audits.json not saved this turn")
    audit = ev.last_audit()
    if audit is None:
        return _missing("no audit in audits.json")
    rows = _rows(audit, "results", "rubric")
    bare = [str(r.get("id")) for r in rows if r.get("pass") is True and not str(r.get("note") or "").strip()]
    if bare:
        return _fail("; ".join(f"{i} PASS without evidence" for i in bare))
    downgraded = [f"{r.get('id')} PASS without evidence: BLOCKED_BY_EVIDENCE" for r in rows
                  if str(r.get("note") or "").startswith(NO_EVIDENCE_NOTE)]
    passes = len([r for r in rows if r.get("pass") is True])
    return _ok("; ".join([f"{passes} PASS rows, each with evidence", *downgraded]), changed=tuple(downgraded))


def code_measure_wins(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """Every rubric item that code measured as failing (`j2_check.design_problems`) is NEEDS_REVISION with `Measured by
    code:`, whatever Audit said. Na for a document (no render measurements)."""
    if "audits.json" not in ev.saved_names:
        return _missing("audits.json not saved this turn")
    audit = ev.last_audit()
    if audit is None:
        return _missing("no audit in audits.json")
    mech = audit.get("mechanical")
    if not mech:
        return _na("no render measurements")
    measured = j2_check.design_problems(mech)
    by_id = {str(r.get("id")).upper(): r for r in _rows(audit, "rubric")}
    wrong = []
    for rid in measured:
        row = by_id.get(rid)
        if row is None:
            wrong.append(f"{rid} measured but has no rubric row")
        elif row.get("verdict") != "NEEDS_REVISION" or not str(row.get("note") or "").startswith(MEASURED_NOTE):
            wrong.append(f"{rid} measured but recorded {row.get('verdict')}")
    if wrong:
        return _fail("; ".join(wrong))
    if not measured:
        return _ok("no design problems measured")
    return _ok(f"{', '.join(measured)} measured, recorded NEEDS_REVISION")


def answer_recorded(ev: Evidence, args: tuple[str, ...]) -> Outcome:
    """A message by the owner (`user`) with an id higher than the question's was posted."""
    (question,) = args
    try:
        asked = int(question)
    except ValueError:
        return _fail(f"the question message id {question!r} is not a number")
    for m in ev.posted:
        if m.get("who") == "user" and _as_int(m.get("id"), -1) > asked:
            return _ok(f"answer recorded as message {m['id']}: \"{clip(str(m.get('text') or ''), 80)}\"")
    return _fail(f"no answer to message {asked} yet")


# ---- the registry ---------------------------------------------------------------------------------------------------

Phase = Literal["reply", "turn", "event"]


@dataclass(frozen=True)
class CheckSpec:
    """What a layer needs to know about a check besides its function."""

    name: str
    fn: CheckFn
    text: str                          # the plain sentence people read (Check.text and its default relevance)
    phases: tuple[Phase, ...]
    kind: Literal["gate", "override"]
    functions: tuple[str, ...]         # the function nodes it serves; () means every function
    task_kinds: tuple[str, ...]        # the turn kinds it serves; () means every kind
    stage: str                         # the J2 stage letter(s), "" for the floors and answer-recorded
    tries: int                         # how many tries J2 gives the node before the check stands (function-nodes.md section 4)
    args: str                          # what the arguments are, for readers


_SPECS: Final = (
    CheckSpec("reply-valid", reply_valid, "The reply follows the closed model of its function and turn.", ("reply",), "gate",
              (), (), "", 3, "family, kind (a|b lists alternative kinds)"),
    CheckSpec("turn-posted", turn_posted, "The turn posted a message or saved a record, and every message goes to a function this one may hand to.",
              ("turn",), "gate", (), (), "", 1, "none"),
    CheckSpec("charter-stamp", charter_stamp, "The charter has a statement, at least 3 done-when items, and none that depends on someone's later action.",
              ("turn",), "gate", ("identity",), ("intake",), "a", 1, "none"),
    CheckSpec("workable", workable, "The goal is declared reached only when code finds the site workable.",
              ("turn",), "override", ("identity",), ("audit",), "h", 1, "none"),
    CheckSpec("audience-split", audience_split, "The text for the owner has no team content and the text for the team has nothing meant for the owner.",
              ("reply", "turn"), "gate", ("identity",), ("intake", "audit", "requester_answered", "approval", "ruling_budget"), "a h", 2, "none"),
    CheckSpec("atom-rules", atom_rules, "Every proposed workflow has complete work atoms that follow the atom rules.",
              ("turn",), "gate", ("adaptation",), ("propose", "respond"), "b e", 2, "none"),
    CheckSpec("judge-gate", judge_gate, "The plan reaches the judge's confidence gate of 0.80.",
              ("turn",), "gate", ("adaptation",), ("propose",), "b", 1, "none"),
    CheckSpec("price-kept", price_kept, "Every workflow Priority grants has a price and a money limit.",
              ("turn",), "override", ("priority",), ("price", "ruling"), "c", 2, "none"),
    CheckSpec("within-budget", within_budget, "A grant stays within the budget left and a run starts only within its envelope.",
              ("turn",), "override", ("priority",), ("price", "ruling", "envelope"), "c f", 1, "none"),
    CheckSpec("order-registered", order_registered, "The schedule names only registered workflows, each once, and every one not held.",
              ("turn",), "override", ("coordination",), ("schedule",), "f", 1, "none"),
    CheckSpec("finding-per-item", finding_per_item, "Every done-when item has exactly one finding, and none cites work Audit owns.",
              ("turn",), "override", ("audit",), ("audit",), "g", 1, "none"),
    CheckSpec("pass-needs-proof", pass_needs_proof, "No finding or rubric row passes without evidence.",
              ("turn",), "override", ("audit",), ("audit",), "g", 1, "none"),
    CheckSpec("code-measure-wins", code_measure_wins, "Every rubric item that code measured as failing is recorded as needing revision.",
              ("turn",), "override", ("audit",), ("audit",), "g", 1, "none"),
    CheckSpec("answer-recorded", answer_recorded, "The owner's answer to the question is recorded.",
              ("event",), "gate", ("identity",), (), "", 1, "the id of the question message"),
)


class CheckRegistry:
    """The 14 checks by name. Built once at import and never changed: there is no way to add, replace or remove a check."""

    __slots__ = ("_specs",)

    def __init__(self, specs: tuple[CheckSpec, ...]) -> None:
        object.__setattr__(self, "_specs", MappingProxyType({s.name: s for s in specs}))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("the verify registry is frozen")

    def __getitem__(self, name: str) -> CheckSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise UnknownCheck(name) from None

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def for_phase(self, phase: Phase) -> tuple[str, ...]:
        return tuple(name for name, s in self._specs.items() if phase in s.phases)

    def run(self, name: str, ev: Evidence, args: tuple[str, ...] | list[str] = ()) -> Outcome:
        """Run one check. Raises `UnknownCheck` for another name and `CheckArgsError` for the wrong number of arguments
        (a check function that raises is a bug; the runner reports it as exit code 127)."""
        spec = self[name]
        arity = check_arity(name)
        got = tuple(args)
        if arity is not None and not arity[0] <= len(got) <= arity[1]:
            raise CheckArgsError(f"{name} takes {arity[0]} to {arity[1]} arguments, got {len(got)}")
        return spec.fn(ev, got)


REGISTRY: Final = CheckRegistry(_SPECS)

if REGISTRY.names() != tuple(REGISTRY_CHECKS):         # the library lists the same 14 names in the same order
    raise ImportError(f"the verify registry {REGISTRY.names()} differs from the library's CheckTemplate {tuple(REGISTRY_CHECKS)}")
