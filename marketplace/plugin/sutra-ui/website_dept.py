"""website_dept.py -- a department that builds a website, run by the motor inside the app.

The first build of the Native design (holding/website/native/system/first-build.html):
one department, four engines in a line, and the one motor that starts every run.

    Brief --Plan--> Site plan --Write--> Pages --Check--> Build --Publish--> Live site

THE RECORD (one folder per department, under SUTRA_NATIVE_DEPT_HOME or
~/.sutra-ui/native/<ref>/)
    dept.json        the department: name, owner, rules, control, envelopes, stopped
    artifacts/<slug>/versions.json   one row per version: v, made_from, run, check
    artifacts/<slug>/v<N>/...        the version's files; a version is never edited
    runs.json        one row per run of an engine or of one of the five systems
    asks.json        asks waiting for a stamp, and escalations
    requests.json    what the owner asked for; each one becomes a new Brief version

THE MOTOR
    One thread inside the app's server. Every tick it reads the record and starts
    the first due slot of each department: a slot is an engine plus the input
    version it would read, so a slot never runs twice. It decides nothing: the
    order is the line above, the budget is the envelope Priority granted, the
    gate is Identity's rules (the first publish asks). The app closed means
    nothing runs; on return each missed slot runs once, because it is still due.

Engines that write (Plan, Write) call the model the way routines.py does; when
the model is not there (SUTRA_WEBSITE_OFFLINE=1, or the call fails) they fall
back to a plain deterministic draft, and the run says which it used.
"""
import contextvars
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import layer_schema as S           # the interface of Root and the five layers (PRD A1): this file's writes are its sink
import record                      # the platform product: rows and documents, deployed into each thing's own folder
import versions as VERS            # the platform product: versions, deployed into each artifact's own folder

ENGINES = (  # name, reads, writes, runs as
    ("Plan", "Brief", "Site plan", "model"),
    ("Write", "Site plan", "Pages", "model"),
    ("Check", "Pages", "Build", "code"),
    ("Publish", "Build", "Live site", "code"),
)
ARTIFACTS = ("Brief", "Site plan", "Pages", "Build", "Live site")
SYSTEMS = ("Identity", "Adaptation", "Priority", "Coordination", "Audit")
PAUSED_SYSTEMS = ("Adaptation", "Audit")      # growth is paused in the first build
CHAIN_LIMIT = 12                              # runs one owner's ask may cause before it stops and asks
ENVELOPE = {"calls": 30, "usd": 6.0}          # per engine, per day: the first build's constant; a runtime department takes Priority's template
HOST_DEFAULT = "this app's own server"        # where a site is served from unless the owner says another (asked at the first publish)
TICK_S = 3.0
DEFAULT_HOME = "~/.sutra-ui/native"
MODEL_TIMEOUT_S = 420
STALE_ASK_S = 30 * 60
# The kinds of department, from the definitions (engine_defs/website.json): each names its line of work engines, its
# artifacts, and the goal, done line and rules it is born with. Read here as data; the runtime validates the whole file
# when it loads. Root is a kind: one for one organisational structure, and it spawns every other department.
_DEFS = json.loads((Path(__file__).parent / "engine_defs" / "website.json").read_text(encoding="utf-8"))
KINDS = _DEFS.get("kinds") or {}
RULES = [dict(r) for r in KINDS.get("website", {}).get("rules") or []]
# Done-when as items (PRD M3.2, MK-2): each item says how it is checked (by a program, by an AI reading what was made,
# or only by the owner) and what it is (a target the work must have, or an outcome it must achieve). A kind's own done
# line stands as D1 when Root drafted none, checked as the kind says.
DONE_HOW = ("code", "model", "person")
DONE_LEVELS = ("target", "outcome")
KIND_DONE_HOW = {"website": "code", "root": "code"}
DONE_ITEMS_MAX = 12


def done_items(raw, kind=None):
    """Done-when items as the record keeps them: [{id, text, how, level}], numbered D1, D2, ... in the order given; a blank
    item is dropped, and how and level are kept as said (lowercased) for a covering to judge. An item that rests on a
    fact nobody gave carries `confirm`, why it is to be confirmed. With none given, the kind's own done line is D1."""
    out = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        text = " ".join(str(x.get("text") or "").split())[:300]
        if not text:
            continue
        item = {"id": "D%d" % (len(out) + 1), "text": text, "how": str(x.get("how") or "").strip().lower(),
                "level": str(x.get("level") or "").strip().lower()}
        why = " ".join(str(x.get("confirm") or "").split())[:200]
        if why:
            item["confirm"] = why
        out.append(item)
    if not out and kind in KINDS:
        out = [{"id": "D1", "text": KINDS[kind]["done"], "how": KIND_DONE_HOW.get(kind, "model"), "level": "outcome"}]
    return out[:DONE_ITEMS_MAX]


def done_line(items):
    """The done-when items as one line, for the readers that read `done` (done stays as joined text)."""
    return "; ".join(str(i.get("text") or "").rstrip(".") for i in items or [] if str(i.get("text") or "").strip())


def items_of(d):
    """The record's done-when items as an ask carries them: each with its confirm note when it is to be confirmed, so a
    change renumbers them and the notes go with their items."""
    why = {c.get("item"): c.get("why") for c in d.get("to_be_confirmed") or [] if isinstance(c, dict)}
    return [dict(i, **({"confirm": why[i.get("id")]} if why.get(i.get("id")) else {})) for i in d.get("done_items") or []
            if isinstance(i, dict)]


#: one done-when item as dept.json keeps it; its confirm note lives in to_be_confirmed, beside it
DONE_ITEM_FIELDS = ("id", "text", "how", "level")


def stored_done_items(items):
    """Done-when items (numbered by done_items) as dept.json keeps them: {id, text, how, level}, defined here once."""
    return [{x: i[x] for x in DONE_ITEM_FIELDS} for i in items]


def to_confirm(items):
    """The items that rest on a fact nobody gave, as dept.json's to_be_confirmed keeps them: [{item, why}]."""
    return [{"item": i["id"], "why": i["confirm"]} for i in items if i.get("confirm")]


def answered_items(d, text):
    """The done-when items an answer to Identity's done-when question makes (PRD M3.1): the owner's words become the next
    item, read by an AI (an outcome), after the record's items that say how they are checked. A record whose done line
    is empty has no done-when to keep, so the answer stands alone."""
    keep = [i for i in items_of(d) if i.get("how") in DONE_HOW] if str(d.get("done") or "").strip() else []
    return keep + [{"text": " ".join(str(text or "").split()), "how": "model", "level": "outcome"}]


def put_done_items(ref, items):
    """Done-when becomes `items` (numbered again): done is their joined text, and to_be_confirmed holds the notes of the
    items that carry one; the goal is never touched. A revision of the identity (bump_identity), so the Org screen's
    copy follows. The one writer of done-when: a stamped done_items ask, and an answer to Identity's question."""
    with _lock(ref):
        d = dept(ref)
        items = done_items(items, d.get("kind"))
        d["done_items"] = stored_done_items(items)
        d["done"] = done_line(items)
        d["to_be_confirmed"] = to_confirm(items)
        return bump_identity(ref, d)


# Rules (PRD M3.4): every rule the record keeps is tagged (go: it may; ask: it asks the owner first; refuse: it never
# does; always: it always does) and says when and from whose words it came. Built here only, so the record holds one shape.
RULE_TAGS = S.RULE_TAGS                      # the interface's (PRD A1.3): tagged as the covering reads them


def rule_row(tag, line, words=None, scope=None):
    """One rule as the record keeps it: {id, tag, line, since, from}; a rule for this once only says so in `scope`."""
    row = {"id": "u-" + uuid.uuid4().hex[:6], "tag": tag, "line": " ".join(str(line or "").split()), "since": now(), "from": words}
    if scope and scope != "standing":
        row["scope"] = scope
    return row


def done_items_ask(text, items, why, words=None, thread=None, slot=None, **more):
    """A change to the done-when items, as an ask the owner stamps (PRD M3.4): `items` as they will stand, numbered
    again. Its own kind, never the goal's tag: its stamp writes the items and leaves the goal as it was. The one shape
    every caller files: Identity's reading of the owner's words, and a blocked plan's 'leave an item out' (M3.5)."""
    return dict({"id": "a-" + uuid.uuid4().hex[:8], "kind": "done_items", "engine": "Identity", "slot": slot, "text": text,
                 "items": done_items(items), "why": why, "words": words, "status": "pending", "created": now(), "thread": thread},
                **more)


def j2_identity_ask(text, cycle_id, missing, why="", points=None, standard=False):
    """Identity's question to the owner (PRD M0.5, M3.3): an ask that takes words, never a stamp, one open at a time.
    `missing` is the point it asks about (or 'words', when the first words named nothing to build from), `points` every
    point of Identity's standard found unmet, and `standard` says Identity's reading of its standard in a step asked it
    (that reading reads the answer again, and the card takes 'just do it'). Built here only, so every question Identity
    puts has one shape: {id, kind, text, why, status, created, cycle_id, missing, points, standard, answer}."""
    return {"id": "a-j2-" + uuid.uuid4().hex[:8], "kind": "j2_identity", "text": str(text), "why": str(why or ""),
            "status": "pending", "created": now(), "cycle_id": cycle_id, "missing": missing, "points": list(points or []),
            "standard": bool(standard), "answer": "words"}


# Asks with options (PRD M3.5, screen S10): a card that offers up to three ways forward, each a label and what it costs,
# the first the one Identity recommends; the owner's one click is the answer, and code applies it. Built here only, so
# every such ask has one shape: {id, kind, engine, text, options: [{id, label, cost}], chosen, status, created, ...}.
OPTIONS_MAX = 3
WORDS_OPTION = "words"                       # the option that carries the owner's own words, from the card's answer box
STOP_OPTION = "stop"                         # the option that stops the department where it is


class AskError(ValueError):
    """A choice an ask cannot take, by a stable code: UNKNOWN_OPTION, ALREADY_HANDLED, EMPTY_ANSWER."""

    def __init__(self, code, why=""):
        super().__init__("%s: %s" % (code, why) if why else code)
        self.code = code


def option(oid, label, cost):
    """One way forward on an ask: what the button says, and what it costs (said beside it, and in its title)."""
    return {"id": str(oid), "label": str(label), "cost": str(cost)}


def options_ask(kind, text, options, **more):
    """An ask whose answer is one of its options, at most three."""
    return dict({"id": "a-" + uuid.uuid4().hex[:8], "kind": kind, "engine": "Identity", "text": text,
                 "options": [option(o["id"], o["label"], o["cost"]) for o in options][:OPTIONS_MAX], "chosen": None,
                 "status": "pending", "created": now()}, **more)


def chosen(option, words=None, by="the owner", at=None):
    """The option the owner chose on an ask, as the ask keeps it: {id, label, at, by, words}. Built here only."""
    return {"id": option["id"], "label": option["label"], "at": at or now(), "by": by, "words": words or None}


def offered(d, a):
    """The options an ask offers now, as the card shows them and a choice is read against: all of them, but Stop while
    the department is stopped, since it is where Stop would put it (found by a verifier 2026-10-26: Stop chosen again on a
    stopped department stopped it again on Start)."""
    opts = [o for o in (a or {}).get("options") or []]
    if (d or {}).get("stopped"):
        opts = [o for o in opts if o.get("id") != STOP_OPTION]
    return opts


def choose_option(ref, aid, oid, text=None, by="the owner"):
    """The owner chose one of an ask's options: the ask is answered once, with the choice and when, and the runtime
    applies it as a step of Identity's (on_stamp, in the ask's own thread). An option the ask does not offer now
    (offered) is UNKNOWN_OPTION; the same choice again is the same answer; another one after it is ALREADY_HANDLED. The
    words option takes the owner's words, and none is EMPTY_ANSWER. A choice the runtime could not post is no choice:
    the card waits as it was, so it never says 'You chose' over nothing applied."""
    text = " ".join(str(text or "").split())[:2000]
    with _lock(ref):
        a = next((x for x in asks(ref) if x["id"] == aid), None)
        if not a:
            raise ValueError("no such ask")
        if a["status"] != "pending" and (a.get("chosen") or {}).get("id") == oid:
            return a                               # the same choice again is the same answer
        offer = {o["id"]: o for o in offered(dept(ref), a)}
        if oid not in offer:
            raise AskError("UNKNOWN_OPTION", "this ask offers %s" % (", ".join(offer) or "no options"))
        if a["status"] != "pending":
            raise AskError("ALREADY_HANDLED")
        if oid == WORDS_OPTION and not text:
            raise AskError("EMPTY_ANSWER")
        before = dict(a)
        at = now()
        a.update({"status": "chosen", "decided": at, "by": by, "chosen": chosen(offer[oid], text, by, at)})
        _put_ask(ref, a)
    rt = _runtime(ref)
    if rt and a.get("thread"):
        # posted in the ask's thread; Identity applies the choice as a step
        if rt.on_stamp(ref, a, True) is None:
            _put_ask(ref, before)
            raise ValueError("the choice did not reach Identity; choose again")
    return a


def apply_done_items(ref, ask):
    """A stamped done_items ask: done-when becomes its items (put_done_items); the goal is never touched."""
    return put_done_items(ref, ask.get("items"))


def engines_of(d):
    """The work engines of a department, in its line: the engines on its record (TPL-1: what it was born with, from the
    Library), the kind's line for one born before the record carried them; (name, reads, writes, runs as). A department
    born the old way keeps the first build's four."""
    if (d or {}).get("runtime") != 2:
        return ENGINES
    import engine_runtime                      # the Library's engines, templates and all; lazy, as it imports this module
    engines = engine_runtime.defs()["engines"]
    out = []
    for n in (d or {}).get("engines") or KINDS.get((d or {}).get("kind") or "website", KINDS["website"])["line"]:
        e = engines.get(n) or {}
        soft = any(s.get("prompt") for s in e.get("steps") or [])
        out.append((n, e.get("reads"), e.get("writes"), "model" if soft else "code"))
    return tuple(out)


def artifacts_of(d):
    """What a department files, first to last: its kind's artifacts; the first build's five for one born the old way."""
    if (d or {}).get("runtime") != 2:
        return ARTIFACTS
    return tuple((d or {}).get("artifacts") or KINDS.get((d or {}).get("kind") or "website", KINDS["website"])["artifacts"])


def kind_of(d):
    return KINDS.get((d or {}).get("kind") or "website") or KINDS["website"]
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_BUSY = set()
_MOTOR = {"thread": None, "stop": False, "started": None, "kick": None}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ts(s):
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


def under_test():
    """Is this process a test run? The house detector (shadow_ledger), which
    knows pytest, unittest and a test file run by name. Never raises."""
    try:
        import shadow_ledger
        return bool(shadow_ledger.running_under_test())
    except Exception:  # noqa: BLE001
        return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def home():
    """The records home, resolved at call time.

    REFUSES THE DEFAULT HOME UNDER ANY TEST RUNNER, by the house rule
    (shadow_ledger.shadow_home, lib/placement_engine). Found 2026-09-28: a lane
    of the release gates started the app, the app started the motor, and the
    motor took its lock in the operator's live home. Nothing ran, because no
    department lived there yet; with one there, a test process would have
    started its runs. A test binds SUTRA_NATIVE_DEPT_HOME to a temp folder, or
    says SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1.

    The read is written in the two-argument form on purpose:
    test_channel_isolation.py finds data paths by that form, and a path it
    cannot see is a path the beta app shares with production.
    """
    h = os.path.expanduser(os.environ.get("SUTRA_NATIVE_DEPT_HOME", "~/.sutra-ui/native") or DEFAULT_HOME)
    if os.environ.get("SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS") != "1" \
            and os.path.realpath(h) == os.path.realpath(os.path.expanduser(DEFAULT_HOME)) \
            and under_test():
        raise RuntimeError(
            "website_dept: refusing to touch the live records home %s from a test. "
            "Set SUTRA_NATIVE_DEPT_HOME to a temp folder, or declare a deliberate "
            "integration test with SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1." % h)
    return Path(h)


def ddir(ref):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", ref or ""):
        raise ValueError("not a department ref: %r" % ref)
    return home() / ref


def _lock(ref):
    with _LOCKS_GUARD:
        if ref not in _LOCKS:
            _LOCKS[ref] = threading.RLock()
        return _LOCKS[ref]


def _read(p, default):
    return record.read(p, default)


#: the department save_dept is writing now: dept.json written past save_dept is a fault in itself (PRD A1.20)
_SAVING = contextvars.ContextVar("website_dept_saving", default=None)


def _sink_ref(p):
    """The department whose own file `p` is (<home>/<ref>/<name>), else None."""
    try:
        p = Path(p)
        return p.parent.name if p.parent.parent == home() else None
    except Exception:  # noqa: BLE001 -- a path outside any department is no interface file
        return None


def _check_sink(p, name, ref, obj):
    """An interface file of a department, checked before it is written (PRD A1.20, the sink): dept.json only through
    save_dept; each asks.json row that is new or changed against the stored rows, whoever writes the file; Coordination's
    table and the owner's instructions whole. In warn mode a fault is a row and the write goes on."""
    if name == "dept.json":
        if _SAVING.get() != ref:
            S.report("department", ["$: dept.json is written only by save_dept"], ref=ref, owner="root")
        return
    if name == "asks.json":
        if not isinstance(obj, list):
            S.report("identity.ask", ["$: asks.json is not a list"], ref=ref, owner="identity")
            return
        stored = {r.get("id"): r for r in _read(p, []) or [] if isinstance(r, dict)}
        for row in obj:
            if not isinstance(row, dict) or stored.get(row.get("id")) != row:
                S.check("identity.ask", row, ref=ref, owner="identity")
        return
    S.check(S.SINK[name], obj, ref=ref, owner={"coordination.json": "coordination"}.get(name, "identity"))


def _write(p, obj):
    name = Path(p).name
    if name in S.SINK:
        ref = _sink_ref(p)
        if ref:
            _check_sink(p, name, ref, obj)
    record.write(p, obj)


def append_row(ref, name, row):
    """One row onto one of the layers' journals (readings, prices, rounds, spot checks: S.SINK_JOURNALS), checked as
    the interface types it, under the department's lock (PRD A1.20). Returns the row."""
    if name not in S.SINK_JOURNALS:
        raise ValueError("no journal named %s" % name)
    with _lock(ref):
        S.check(S.SINK_JOURNALS[name], row, ref=ref)
        return record.append(ddir(ref) / name, row)


def rows(ref, name):
    """One of the layers' journals, oldest first."""
    if name not in S.SINK_JOURNALS:
        raise ValueError("no journal named %s" % name)
    return record.lines(ddir(ref) / name)


# ---- the record --------------------------------------------------------------------------------------------------
def dept(ref):
    """The department's record, read as the interface's current schema version (a record from before A1 is migrated
    on the read, never written by it: the next save writes it back)."""
    d = _read(ddir(ref) / "dept.json", None)
    if not isinstance(d, dict) or d.get("kind") not in KINDS:
        return None
    return d if d.get("schema_version") == S.SCHEMA_VERSION else S.migrate("department", d)


def list_depts():
    out = []
    if home().is_dir():
        for p in sorted(home().iterdir()):
            if not p.is_dir() or p.name.startswith(("_", ".")):
                continue
            d = _read(p / "dept.json", None)
            if isinstance(d, dict) and d.get("kind") in KINDS:
                out.append(d)
    return out


def save_dept(ref, d, by=None):
    """The department's record, written whole, after the interface checks the keys this save changes against the stored
    record (PRD A1.20): a fault is a row in warn mode; stopped and control always land. `by` is the layer saving, when it
    says, and a key another layer owns is a row."""
    p = ddir(ref) / "dept.json"
    S.check_department(d, ref, before=_read(p, None), by=by)
    token = _SAVING.set(ref)
    try:
        _write(p, d)
    finally:
        _SAVING.reset(token)


def bump_identity(ref, d):
    """Who the department is changed (its goal, done-when or rules): the revision goes up, the record is saved, and
    the Org screen's copy follows it as a one-way mirror (PRD M3.1; founding.mirror files and applies it through the
    proposals path, decision C1). The record is the truth: a copy that cannot be written never fails the change, and a
    row says so."""
    d["identity_revision"] = int(d.get("identity_revision") or 1) + 1
    save_dept(ref, d, by="identity")
    try:
        import founding
        founding.mirror(ref)
    except Exception as exc:  # noqa: BLE001 -- the mirror never fails the identity it follows
        system_run(ref, "Identity", "could not copy the identity to the Org screen: %s" % exc)
    return d


# An artifact deploys the versions product in its own folder; this file names the folder, nothing more.
def _abase(ref, art):
    return ddir(ref) / "artifacts" / slug(art)


def versions(ref, art):
    return VERS.rows(_abase(ref, art))


def latest(ref, art, passed=False):
    return VERS.latest(_abase(ref, art), passed)


def vdir(ref, art, v):
    return VERS.vdir(_abase(ref, art), v)


def read_files(ref, art, v):
    return VERS.files(_abase(ref, art), v)


def add_version(ref, art, files, made_from, run, check, note=""):
    """A version, with the artifact's own check beside the engine's: the template in the Library says what a good one
    is, and a version that fails it is filed and never read as passed (founder, 2026-09-28: operable artifacts)."""
    import artifacts
    own = artifacts.check(art, files, default=art in artifacts_of(dept(ref)))   # an artifact the department names: the Default when the Library has no template of its own
    if own is not None:
        check = dict(check or {})
        check["ok"] = bool(check.get("ok")) and own["ok"]
        check["notes"] = list(check.get("notes") or []) + own["notes"]
    return VERS.add(_abase(ref, art), files, made_from, run, check, now(), note=note, lock=_lock(ref))


def runs(ref):
    return _read(ddir(ref) / "runs.json", [])


def working_now(ref):
    """The engines running now, the same rows the working line reads: run rows still open, but not one a dead process
    left open past the model's timeout twice over."""
    out = []
    for r in runs(ref):
        if r.get("status") != "running":
            continue
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(r.get("started"))).astimezone(timezone.utc)).total_seconds()
        except (TypeError, ValueError):
            age = 0
        if age < MODEL_TIMEOUT_S * 2:
            out.append(r["engine"])
    return out


def _put_run(ref, row):
    with _lock(ref):
        rows = runs(ref)
        for i, r in enumerate(rows):
            if r["id"] == row["id"]:
                rows[i] = row
                break
        else:
            rows.append(row)
        _write(ddir(ref) / "runs.json", rows)
        return row


def system_run(ref, system, what, wrote=None):
    """The five internal systems are engines too: each of their runs is a row."""
    return _put_run(ref, {"id": "r-" + uuid.uuid4().hex[:10], "engine": system, "system": True, "slot": None,
                          "status": "ok", "started": now(), "ended": now(), "what": what, "wrote": wrote,
                          "chain": None, "spend": {"calls": 0, "usd": 0.0}, "retries": 0})


def asks(ref):
    return _read(ddir(ref) / "asks.json", [])


def _put_ask(ref, row):
    with _lock(ref):
        rows = asks(ref)
        for i, r in enumerate(rows):
            if r["id"] == row["id"]:
                rows[i] = row
                break
        else:
            rows.append(row)
        _write(ddir(ref) / "asks.json", rows)
        return row


def requests(ref):
    return _read(ddir(ref) / "requests.json", [])


# ---- the engine runtime, behind its switch --------------------------------------------------------------------------
def _runtime(ref):
    """engine_runtime.py, for a department whose record says `runtime: 2`; None for every other. The way is on the
    record, written at birth, so a department never changes how it runs in the middle of its life. Every department
    is born on the runtime since 2026-09-28; a department born before that day, or one made with
    SUTRA_ENGINE_RUNTIME=1 by the first build's suites, runs the old way."""
    d = dept(ref)
    if d and d.get("runtime") == 2:
        import engine_runtime
        return engine_runtime
    return None


# ---- the department's birth ----------------------------------------------------------------------------------------
def birth_faults(kind):
    """The kind's line held to Root's standards at birth (PRD A1.14, M7.1): the standards that apply to a Library line the
    moment a department of the kind is born, none for a kind whose line is empty (Adaptation shapes it). [] when the line
    meets them; else one sentence for each that does not, naming the standard, its words and what is wrong. Nothing is
    written, so Setup asks it before founding makes anything (engine_runtime.setup_make)."""
    k = KINDS.get(kind) or {}
    line = list(k.get("line") or [])
    d = {"kind": kind, "engines": line}
    says = {sid: text for sid, text, _, _ in S.WORKFLOW_STANDARDS}
    return ["%s (%s): %s" % (r["check"], says[r["check"]], r["why"]) if r["check"] in says else str(r["why"])
            for r in S.validate_workflow(S.as_workflow(line, "library", d), "birth", d) if not r["passed"]]


def create(ref, name, brief, owner="the owner", parent=None, kind="website", goal=None):
    """A new department of its kind: Identity's rules, Priority's envelopes, Coordination's table, and its first
    artifact from the owner's words. Every department is born on the engine runtime (founder, 2026-09-28: "I don't
    want to create the old way. I want it to be organic only"); SUTRA_ENGINE_RUNTIME=1 keeps the first build's way
    only for its own suites and for the departments born before that day, which the record says.

    `goal` is the owner's own words for it, as Root shaped them (PRD M3.1): dept.json is the one record of who the
    department is, so its goal is those words; with none, the kind's own goal line."""
    if dept(ref):
        raise ValueError("%s already has a department" % ref)
    if kind not in KINDS:
        raise ValueError("the Library has no department kind named %s" % kind)
    brief = " ".join(str(brief or "").split())
    k = KINDS[kind]
    d = {"kind": kind, "ref": ref, "name": name, "owner": owner, "parent": parent, "created": now(),
         "goal": " ".join(str(goal or "").split()) or k["goal"].format(name=name), "done": k["done"],
         "done_items": done_items(None, kind),
         "runtime": 1 if os.environ.get("SUTRA_ENGINE_RUNTIME") == "1" else 2,
         "rules": [dict(r) for r in k["rules"]], "control": "granted", "stopped": False,
         "envelopes": {e[0]: dict(ENVELOPE) for e in ENGINES},
         "windows": {"Plan": 15, "Write": 30, "Check": 5, "Publish": 10},
         # what it was born with, from the Library (TPL-1): its line and its artifacts, read from here from now on
         "engines": list(k["line"]), "artifacts": list(k["artifacts"])}
    if d["runtime"] == 1 and kind != "website":
        raise ValueError("only a website department is born the old way")
    by_plan = False
    if d["runtime"] == 2:
        # The limits come from Priority's template (founder, 2026-09-28: "some default limits which are in the priority
        # templates"); the owner changes a department's own on Priority's card. A step is a call, so a work engine is
        # given work_calls times the calls, Write costing a call a page where it cost one a run. The money is the same.
        # A department that lives J2 is born with its functions' limits only: each engine is given its own by Priority
        # when the plan that names it is registered (PRD M4.1), so every engine's grant is Priority's, on the ledger.
        import engine_runtime
        import j2_runtime
        by_plan = kind != "root" and j2_runtime.enabled()
        d["envelopes"] = {} if by_plan else {e[0]: engine_runtime.engine_limit(e[0]) for e in engines_of(d)}
        d["envelopes"].update({s: engine_runtime.engine_limit(s) for s in SYSTEMS})
        # the kind's line is held to Root's standards before anything is written (PRD A1.14): a kind whose line breaks one
        # makes no department, and the failure names the standard, as an unknown kind is refused above
        bad = birth_faults(kind)
        if bad:
            raise ValueError("a %s department is not made: its line breaks Root's standards: %s" % (kind, "; ".join(bad)))
    # the implementation of each layer this department runs (A1.18), and the version of the interface its record is in
    d["layers"] = dict(S.DEFAULT_PINS)
    d["schema_version"] = S.SCHEMA_VERSION
    ddir(ref).mkdir(parents=True, exist_ok=True)
    save_dept(ref, d)       # no `by`: birth hands each layer its first values (A1.6 lists this as their writer), not one layer writing another's key
    system_run(ref, "Identity", "set its rules within the parent's")
    system_run(ref, "Priority", "granted an envelope to each function" if by_plan else "granted an envelope to each engine")
    system_run(ref, "Coordination", "timetabled each engine after its input's new version")
    if d["runtime"] == 2:
        _runtime(ref).born(ref)                        # Coordination writes its table: who goes first, who may post
    row = give_goal(ref, brief) if brief else None
    return d, row


def give_goal(ref, text):
    """The owner gives the department its goal: Brief v1, and the line starts on
    its own. A department that already has a goal takes the words as an ask."""
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("say what the website is for")
    d = dept(ref)
    if not d:
        raise ValueError("no website department at %s" % ref)
    rt = _runtime(ref)
    if rt:
        return rt.request(ref, text)[1]        # the words go to Identity on the board; Identity files the Brief
    if versions(ref, "Brief"):
        return owner_ask(ref, text)[1]
    system_run(ref, "Identity", "took the goal from the owner")
    system_run(ref, "Priority", "admitted the goal as work")
    return add_version(ref, "Brief", {"brief.md": "# " + d["name"] + "\n\n" + text + "\n"},
                       [{"ask": text, "at": now()}], "owner", {"ok": True, "notes": ["the owner's goal"]})


def owner_ask(ref, text, about=None, message_id=None):
    """A person asks for something extra (the Ask control). Identity takes it,
    Priority admits it, and it becomes the next Brief version, so the line runs
    again from Plan. On a Root, the words arrive at the front door; `about` is
    the department the person stood in when he said them."""
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("say what to add or change")
    d = dept(ref)
    if not d:
        raise ValueError("no website department at %s" % ref)
    rt = _runtime(ref)
    if rt:
        return rt.request(ref, text, about=about, message_id=message_id)[0], None
    with _lock(ref):
        reqs = requests(ref)
        rq = {"id": "q-" + uuid.uuid4().hex[:8], "text": text, "at": now()}
        reqs.append(rq)
        _write(ddir(ref) / "requests.json", reqs)
        cur = latest(ref, "Brief")
        base = read_files(ref, "Brief", cur["v"]).get("brief.md", "") if cur else ""
        body = base.rstrip() + ("\n\n## Asked since\n" if "## Asked since" not in base else "\n") + "- " + text + "\n"
        system_run(ref, "Identity", "took the owner's ask: " + text)
        system_run(ref, "Priority", "admitted it as work")
        row = add_version(ref, "Brief", {"brief.md": body},
                          [{"art": "Brief", "v": cur["v"]} if cur else {}, {"ask": text, "at": rq["at"]}],
                          "owner", {"ok": True, "notes": ["the owner's ask"]})
    return rq, row


def set_stopped(ref, stopped):
    with _lock(ref):
        d = dept(ref)
        if not d:
            raise ValueError("no website department at %s" % ref)
        d["stopped"] = bool(stopped)
        save_dept(ref, d)
    if not stopped:
        # Start after Stop: the department's J2 cycle goes on from the step it stood on (the two never disagree)
        try:
            import j2_runtime
            if (j2_runtime._state(ref) or {}).get("state") == "stopped":
                j2_runtime.resume(ref)
        except Exception:  # noqa: BLE001 -- the switch is thrown whether or not the lifecycle record follows
            pass
    if d.get("runtime") == 2:
        # Start and Stop are one button, and a signal to every engine of the department (founder, 2026-09-28).
        system_run(ref, "Identity", "stopped by the owner: every engine stops" if stopped
                   else "started by the owner: every engine looks to its own triggers")
        rt = _runtime(ref)
        if rt:
            rt.tell_switch(ref, d, bool(stopped))       # a turn of the chat: the person's own act, said back
        signal()
    else:
        system_run(ref, "Identity", "stopped by the owner" if stopped else "resumed by the owner")
    return d


def decide_ask(ref, aid, approve, by="the owner"):
    for a in asks(ref):
        if a["id"] == aid:
            if a.get("kind") == "j2_identity":
                # Identity's question takes words (j2_runtime.answer); a stamp would close it with nothing said (M0.6)
                raise ValueError("Identity's question takes words: answer it in the chat")
            if a.get("options"):
                # an ask with options takes one of them (choose_option); a stamp would choose nothing (M3.5)
                raise ValueError("this ask takes one of its options")
            if a["status"] != "pending":
                if a["status"] == ("stamped" if approve else "refused"):
                    return a
                raise ValueError("that ask is already %s" % a["status"])
            a["status"] = "stamped" if approve else "refused"
            a["decided"] = now()
            a["by"] = by
            _put_ask(ref, a)
            if approve and a.get("kind") == "publish":
                # the first publish ask carries the question where the site is served from; a stamp with no
                # other answer takes the default, and the answer stays on the record for Publish to read
                d = dept(ref)
                if d is not None and not d.get("host"):
                    d["host"] = HOST_DEFAULT
                    save_dept(ref, d, by="identity")
            rt = _runtime(ref)
            if rt and a.get("thread"):
                rt.on_stamp(ref, a, approve)       # posted in the ask's thread; Identity applies it as a step
            else:
                system_run(ref, "Identity", ("stamped: " if approve else "refused: ") + a["text"])
            return a
    raise ValueError("no such ask")


def _place(d, name, reads, before=None):
    """The line an engine named `name`, reading `reads`, joins on the department's record, and the engine it goes before
    (None: last): the one said (as Research goes before Plan); an engine that reads the Brief goes first (what it files,
    the line reads). (line, before)."""
    line = [x[0] for x in engines_of(d)]
    arts0 = list(artifacts_of(d))
    if before is None and line and arts0 and reads == arts0[0]:
        before = line[0]                             # an engine that reads the Brief goes first: what it files, the line reads
    if before in line:
        line.insert(line.index(before), name)
    else:
        line.append(name)
    return line, before


class GrowRefused(ValueError):
    """add_engine's refusal at the grow stage (PRD A1.14, J5): a ValueError that says the line would break Root's standards,
    and carries `broken`, [(standard id, the standard's words, what is wrong)], for whoever tells the owner why."""

    def __init__(self, message, broken):
        super().__init__(message)
        self.broken = list(broken)


def grow_broken(d, name, e=None, shape=None, before=None):
    """The line `name` would make, held to Root's standards at the grow stage (PRD A1.14, J5): what the line would break
    that it did not break before, as (standard id, the standard's words, what is wrong); [] when it breaks none. `e` is the
    engine's definition when the Library has it, else `shape` says what a new one reads and writes. A fault the line
    already had is not the new engine's, so it never stops one joining."""
    reads = (e or {}).get("reads") or str((shape or {}).get("reads") or "Brief")
    writes = (e or {}).get("writes") or str((shape or {}).get("writes") or name)[:40]
    now = [x[0] for x in engines_of(d)]
    after = _place(d, name, reads, before)[0]
    source = "library" if e else "shaped"
    says = {sid: text for sid, text, _, _ in S.WORKFLOW_STANDARDS}

    def broken(line):
        rows = [{"name": n} for n in line]
        if name in line:
            rows[line.index(name)] = {"name": name, "reads": reads, "writes": writes}
        return [(r["check"], r["why"]) for r in S.validate_workflow(S.as_workflow(rows, source, d), "grow", d, {}) if not r["passed"]]
    was = broken(now)
    return [(c, says.get(c), why) for c, why in broken(after) if (c, why) not in was]


def _broken_lines(broken):
    """grow_broken's rows, one sentence for each, naming the standard, its words and what is wrong."""
    return ["%s (%s): %s" % (c, says, why) if says else why for c, says, why in broken]


def grow_faults(d, name, e=None, shape=None, before=None):
    """grow_broken as sentences; [] when the line breaks nothing."""
    return _broken_lines(grow_broken(d, name, e, shape, before))


def add_engine(ref, name, shape=None, by="the owner's stamp", before=None, registered=False):
    """An engine added to a live department on the owner's stamp (TPL-1 slice 2, founder 2026-09-29: "the engines are
    supposed to be created by the five functions of the department"): a Library engine template by name, or one shaped
    on the fly (name, use case, instruction, what it writes), born into the Library from Do with made_by. The record
    gains the engine, its artifact and a window; then Coordination's line grows and Priority gives it its limit, each in
    its handler for an engine born (PRD M4.1); the engine then starts on its own trigger, like every other.

    The line it would make is held to Root's standards at the grow stage first (PRD A1.14, J5): an engine that reads
    what nothing files, or writes what is already written, is not added, nothing is born for it, and the ValueError
    names the standard. A plan Root is registering has been held to them whole, at registration, so it is not held again.

    by: whose word added it, whole, as the run line says it after 'on' ("the owner's stamp", "Priority's yes",
    "Identity's ruling": engine_runtime.SETTLED_BY's keys), so the line never says a stamp nobody gave (PRD M1.7).

    registered: the engine is one of a plan Root is registering (J2 step 5). The record gains it here, and Coordination's
    line and Priority's limit follow from the registration itself, not from here."""
    import engine_runtime as R
    d = dept(ref)
    if not d or d.get("runtime") != 2:
        raise ValueError("no department on the engine runtime at %s" % ref)
    name = " ".join(str(name or "").split())[:40]
    if not name:
        raise ValueError("name the engine")
    engines = R.defs()["engines"]
    born = None
    if name not in engines and not shape:
        raise ValueError("the Library has no engine named %s" % name)
    if name in engines and engines[name].get("kind") != "work":
        raise ValueError("%s is a function, not an engine of the line" % name)
    if name in [x[0] for x in engines_of(d)]:
        raise ValueError("%s already runs %s" % (d.get("name"), name))
    if not registered:
        bad = grow_broken(d, name, engines.get(name), shape, before)
        if bad:
            raise GrowRefused("%s is not added to %s: the line would break Root's standards: %s" % (
                name, d.get("name"), "; ".join(_broken_lines(bad))), bad)
    if name not in engines:
        born = R.born_template(name, shape, ref)
        engines = R.defs()["engines"]
    e = engines[name]
    if e.get("kind") != "work":
        raise ValueError("%s is a function, not an engine of the line" % name)
    with _lock(ref):
        d = dept(ref)
        line = [x[0] for x in engines_of(d)]
        if name in line:
            raise ValueError("%s already runs %s" % (d.get("name"), name))
        line, before = _place(d, name, e.get("reads"), before)
        d["engines"] = line
        arts = list(artifacts_of(d))
        if e.get("writes") and e["writes"] not in arts:
            # right after what it reads, so the kind's last artifact (the one that goes out) stays last
            arts.insert(arts.index(e["reads"]) + 1 if e.get("reads") in arts else len(arts), e["writes"])
        d["artifacts"] = arts
        save_dept(ref, d, by="root")                  # Root records the engine and its artifact; its window is Identity's, below
        d.setdefault("windows", {})[name] = 15
        save_dept(ref, d, by="identity")
    if registered:
        # the plan's engine is Adaptation's (it shaped it): Root records the plan, and never makes an engine (S-10)
        system_run(ref, "Adaptation", "brought the engine %s into the plan%s" % (name, " (born into the Library)" if born else ""))
    else:
        R.engine_added(ref, name, before)
        system_run(ref, "Identity", "added the engine %s on %s%s" % (name, by, " (born into the Library)" if born else ""))
    return {"ref": ref, "engine": name, "engines": line, "born": str(born) if born else None}


def limit_of(d, name):
    """An engine's limit, a day ({calls, usd}): the one on its record; for an engine on the engine runtime that Priority
    has not given one yet (a plan not registered yet), the one Priority gives (engine_runtime.engine_limit); the first
    build's constant for a department born the old way."""
    env = ((d or {}).get("envelopes") or {}).get(name)
    if isinstance(env, dict) and env:
        return env
    if (d or {}).get("runtime") == 2:
        import engine_runtime
        return engine_runtime.engine_limit(name)
    return ENVELOPE


def set_envelope(ref, name, calls=None, usd=None, by="the owner"):
    """The owner's own limits for one engine, set on Priority's card. The defaults came from Priority's template
    at birth (founder, 2026-09-28: "These limits can be configured in the relevant priority")."""
    d = dept(ref)
    if not d:
        raise ValueError("no website department here")
    if name not in {e[0] for e in engines_of(d)} | set(SYSTEMS):
        raise ValueError("no engine named %s" % name)
    env = dict(limit_of(d, name))
    if calls is not None:
        env["calls"] = max(0, int(calls))
    if usd is not None:
        env["usd"] = max(0.0, float(usd))
    d.setdefault("envelopes", {})[name] = env
    save_dept(ref, d, by="priority")      # the envelope is Priority's key, whoever asked (`by` above is who, in words)
    system_run(ref, "Priority", "%s set %s's envelope: %d calls, %.2f USD a day" % (by, name, env["calls"], env["usd"]))
    return env


def set_host(ref, host, by="the owner"):
    """Where the site is served from: the owner's answer to the question the first publish asks, kept on the record;
    Publish reads it (founder, 2026-09-28: "more of a question to the user and should be asked to the user")."""
    d = dept(ref)
    if not d:
        raise ValueError("no website department here")
    host = " ".join(str(host or "").split())[:200] or HOST_DEFAULT
    d["host"] = host
    save_dept(ref, d, by="identity")
    system_run(ref, "Identity", "%s said where the site is served from: %s" % (by, host))
    return host


def put_back(ref, art, v, by="the owner"):
    """Undo: the chosen version becomes the newest one again, as a new version
    (nothing is edited or deleted). Putting back the live site republishes it."""
    arts = artifacts_of(dept(ref))
    if art not in arts or art == arts[0]:
        raise ValueError("only made work can be put back")
    rows = versions(ref, art)
    src = next((r for r in rows if r["v"] == int(v)), None)
    if not src:
        raise ValueError("no version %s of %s" % (v, art))
    rid = "r-" + uuid.uuid4().hex[:10]
    row = add_version(ref, art, read_files(ref, art, src["v"]), [{"art": art, "v": src["v"]}], rid,
                      dict(src.get("check") or {}), note="Put back by %s" % by)
    _put_run(ref, {"id": rid, "engine": "Put back", "system": False, "slot": None, "status": "ok", "started": now(),
                   "ended": now(), "what": "%s put back to an earlier version" % art,
                   "wrote": {"art": art, "v": row["v"]}, "chain": None, "spend": {"calls": 0, "usd": 0.0}, "retries": 0})
    if art == "Live site":
        _publish_files(ref, read_files(ref, art, row["v"]))
    return row


# ---- the model -----------------------------------------------------------------------------------------------------
def _login_path():
    try:
        import routines
        return routines.login_path()
    except Exception:  # noqa: BLE001
        return os.environ.get("PATH", "")


MODEL_TOOLS = ("WebSearch", "WebFetch")       # the tools a step may name: the model reaches the internet, nothing else


def model_json(prompt, timeout=MODEL_TIMEOUT_S, tools=None):
    """(object or None, usd, why). One headless model call, as routines.py makes
    them: plan billing, quiet hooks, JSON back. Never raises. With `tools`, the
    step's own tools (MODEL_TOOLS only) are the ones the model may use: a
    Research step searches the web through them (founder, 2026-09-29: "I want
    the data to be fetched from the internet by the department")."""
    if os.environ.get("SUTRA_WEBSITE_OFFLINE") == "1":
        return None, 0.0, "offline"
    env = dict(os.environ)
    env["PATH"] = _login_path()
    env.pop("ANTHROPIC_API_KEY", None)
    env["SUTRA_ROUTINE"] = "1"
    env["SUTRA_DEFAULTS_DISABLED"] = "1"
    claude = shutil.which("claude", path=env["PATH"]) or "claude"
    args = [claude, "-p", prompt, "--output-format", "json", "--permission-mode", "dontAsk",
            "--setting-sources", "user", "--model", os.environ.get("SUTRA_WEBSITE_MODEL", "sonnet")]
    use = [t for t in (tools or []) if t in MODEL_TOOLS]
    if use:
        args += ["--tools"] + use + ["--allowedTools"] + use
    # The model runs in a folder of its own: whatever a headless session leaves
    # behind (its hooks write ledgers into the working folder) stays out of the
    # departments' records.
    scratch = home() / "_model"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(args, cwd=str(scratch), env=env, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return None, 0.0, "model call failed: %s" % exc
    try:
        out = json.loads(p.stdout or "{}")
    except Exception:  # noqa: BLE001
        return None, 0.0, "model answered no JSON (exit %s)" % p.returncode
    if not isinstance(out, dict):
        return None, 0.0, "model answered no JSON (exit %s)" % p.returncode
    usd = float(out.get("total_cost_usd") or 0.0)
    if out.get("is_error"):
        # the CLI answered, with exit 0, that the call itself failed (no such model, not signed in, over the limit): that is
        # the model being away, not an answer of the wrong shape (found live 2026-10-07: it was read as a bad answer and the
        # step went to the person by hand after ten seconds, never waiting the 30, 120 and 600 s)
        return None, usd, "model call failed: %s" % str(out.get("result") or out.get("subtype") or "the CLI reported an error")[:200]
    text = str(out.get("result") or "")
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        return None, usd, "model result had no JSON object"
    try:
        return json.loads(m.group(1)), usd, "model"
    except Exception:  # noqa: BLE001
        return None, usd, "model JSON did not parse"


# ---- the four engines ----------------------------------------------------------------------------------------------
BASE_PAGES = [("index", "Home", "who the hospital is and how to get care"),
              ("about", "About", "the hospital's story, values and accreditation"),
              ("departments", "Departments", "the clinical departments and what each treats"),
              ("doctors", "Doctors", "the doctors, their specialities and hours"),
              ("appointments", "Appointments", "how to book, change or cancel a visit"),
              ("contact", "Contact", "address, phone numbers, emergency line and map directions")]


def _asked_pages(brief_text):
    extra = []
    for line in brief_text.splitlines():
        m = re.search(r"\b(?:add|create|include|new)\s+(?:an?\s+|the\s+)?([a-z][a-z &-]{1,40}?)\s+(?:page|section)\b", line, re.I)
        if m:
            title = m.group(1).strip().title()
            extra.append((slug(title), title, "what the owner asked for: " + line.strip("- ").strip()))
    return extra


def _fallback_plan(name, brief_text):
    pages = list(BASE_PAGES)
    have = {p[0] for p in pages}
    for s, t, purpose in _asked_pages(brief_text):
        if s not in have:
            pages.append((s, t, purpose))
            have.add(s)
    return {"site_name": name, "tagline": "Care you can reach, every day",
            "palette": {"primary": "#0f5e7a", "accent": "#c4956a"},
            "pages": [{"slug": s, "title": t, "purpose": p, "sections": [t, "What to know", "Next step"]} for s, t, p in pages]}


def engine_plan(ref, d, inp):
    text = read_files(ref, "Brief", inp["v"]).get("brief.md", "")
    prompt = ("You are the Plan engine of a department that builds a website. Read the brief and every ask in it, "
              "and return ONLY a JSON object, no prose: {\"site_name\": str, \"tagline\": str, "
              "\"palette\": {\"primary\": \"#hex\", \"accent\": \"#hex\"}, \"pages\": [{\"slug\": \"lowercase-hyphen\", "
              "\"title\": str, \"purpose\": str, \"sections\": [str]}]}. The first page's slug is index. Include every page "
              "the brief or an ask names. Six to ten pages.\n\nBRIEF:\n" + text)
    plan, usd, how = model_json(prompt)
    if not (isinstance(plan, dict) and isinstance(plan.get("pages"), list) and plan["pages"]):
        plan, how = _fallback_plan(d["name"], text), ("fallback draft (" + how + ")")
    for p in plan["pages"]:
        p["slug"] = slug(str(p.get("slug") or p.get("title") or "page")) or "page"
    if plan["pages"][0]["slug"] != "index":
        plan["pages"].insert(0, {"slug": "index", "title": "Home", "purpose": "the front door", "sections": ["Welcome"]})
    for s, t, purpose in _asked_pages(text):
        if s not in {p["slug"] for p in plan["pages"]}:
            plan["pages"].append({"slug": s, "title": t, "purpose": purpose, "sections": [t]})
    ok = len(plan["pages"]) >= 2
    return ({"site-plan.json": json.dumps(plan, indent=1)}, {"ok": ok, "notes": ["%d pages" % len(plan["pages"]), how]},
            {"calls": 1 if how == "model" else 0, "usd": usd})


def _fallback_body(page, plan):
    parts = ["<section class=\"hero\"><h1>%s</h1><p>%s</p></section>" % (_esc(page["title"]), _esc(page.get("purpose") or ""))]
    for s in page.get("sections") or []:
        parts.append("<section><h2>%s</h2><p>%s at %s. Call the front desk or visit us any day of the week.</p></section>"
                     % (_esc(s), _esc(page.get("purpose") or s), _esc(plan.get("site_name") or "")))
    if page["slug"] != "appointments":
        parts.append("<p><a class=\"cta\" href=\"appointments.html\">Book an appointment</a></p>")
    return "\n".join(parts)


def engine_write(ref, d, inp):
    plan = json.loads(read_files(ref, "Site plan", inp["v"]).get("site-plan.json", "{}"))
    prompt = ("You are the Write engine of a department that builds a website. Write the body of every page in this "
              "site plan. Return ONLY a JSON object, no prose: {\"pages\": [{\"slug\": str, \"title\": str, "
              "\"body_html\": str}]}. body_html is the inside of <main> only: semantic HTML (section, h1, h2, p, ul, a), "
              "no <html>, <head>, <script> or <style>, no external images or links. Link to other pages as "
              "'<slug>.html' and only to slugs in the plan. Real, specific, warm copy for patients.\n\nPLAN:\n"
              + json.dumps(plan))
    out, usd, how = model_json(prompt)
    by_slug = {}
    if isinstance(out, dict) and isinstance(out.get("pages"), list):
        for p in out["pages"]:
            if isinstance(p, dict) and p.get("slug") and p.get("body_html"):
                by_slug[slug(str(p["slug"]))] = str(p["body_html"])
    files = {}
    for page in plan.get("pages", []):
        body = by_slug.get(page["slug"]) or _fallback_body(page, plan)
        files[page["slug"] + ".html"] = json.dumps({"title": page["title"], "body_html": body})
    files["_plan.json"] = json.dumps(plan)
    written_by = "model" if by_slug else "fallback draft (" + how + ")"
    return files, {"ok": bool(files), "notes": ["%d pages" % (len(files) - 1), written_by]}, {"calls": 1 if by_slug else 0, "usd": usd}


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.scripts, self.text = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self.links.append(href)
        if tag == "script":
            self.scripts += 1

    def handle_data(self, data):
        self.text += len(data.strip())


CSS = """*{box-sizing:border-box}body{margin:0;font:16px/1.6 system-ui,-apple-system,sans-serif;color:#1c1a17;background:#fafaf9}
header{background:%(primary)s;color:#fff;padding:18px 28px;display:flex;flex-wrap:wrap;gap:18px;align-items:center}
header .name{font:700 20px/1.2 ui-serif,Georgia,serif;margin-right:auto}header a{color:#fff;text-decoration:none;opacity:.9}
header a.on{text-decoration:underline;opacity:1}main{max-width:920px;margin:0 auto;padding:28px}
section{margin:0 0 26px}h1{font:700 34px/1.2 ui-serif,Georgia,serif;margin:0 0 10px}h2{font-size:21px;margin:0 0 8px}
.hero{padding:26px;border-radius:14px;background:#fff;border:1px solid #e2e0dd}a.cta{display:inline-block;background:%(accent)s;color:#fff;
padding:10px 18px;border-radius:22px;text-decoration:none}footer{padding:22px 28px;color:#57534e;border-top:1px solid #e2e0dd;font-size:14px}"""


def engine_check(ref, d, inp):
    """Code, not a model: assemble each page in one layout, then check it. The
    verdict rides on the Build version; a failed one is filed and never published."""
    src = read_files(ref, "Pages", inp["v"])
    plan = json.loads(src.get("_plan.json", "{}"))
    pages = [p for p in plan.get("pages", []) if (p["slug"] + ".html") in src]
    slugs = {p["slug"] for p in pages}
    pal = plan.get("palette") or {}
    colors = {"primary": pal.get("primary") or "#0f5e7a", "accent": pal.get("accent") or "#c4956a"}
    for k, v in list(colors.items()):
        if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", str(v)):
            colors[k] = "#0f5e7a" if k == "primary" else "#c4956a"
    files, notes, ok = {"style.css": CSS % colors}, [], True
    for p in pages:
        data = json.loads(src[p["slug"] + ".html"])
        nav = "".join('<a href="%s.html"%s>%s</a>' % (q["slug"], ' class="on"' if q["slug"] == p["slug"] else "", _esc(q["title"])) for q in pages)
        doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
               "<title>%s | %s</title><link rel=\"stylesheet\" href=\"style.css\"></head><body><header><span class=\"name\">%s</span>%s</header>"
               "<main>%s</main><footer>%s &#183; %s</footer></body></html>"
               % (_esc(data["title"]), _esc(plan.get("site_name") or d["name"]), _esc(plan.get("site_name") or d["name"]), nav,
                  data["body_html"], _esc(plan.get("site_name") or d["name"]), _esc(plan.get("tagline") or "")))
        files[p["slug"] + ".html"] = doc
        lp = _Links()
        try:
            lp.feed(data["body_html"])
        except Exception:  # noqa: BLE001
            ok = False
            notes.append("%s: does not parse" % p["slug"])
            continue
        if lp.scripts:
            ok = False
            notes.append("%s: carries a script" % p["slug"])
        if lp.text < 40:
            ok = False
            notes.append("%s: almost no text" % p["slug"])
        for href in lp.links:
            if href.startswith(("http:", "https:", "mailto:", "tel:", "#")):
                continue
            target = href.split("#")[0]
            if target.endswith(".html") and target[:-5] not in slugs:
                ok = False
                notes.append("%s: links to %s, which is not a page" % (p["slug"], target))
    if "index" not in slugs:
        ok = False
        notes.append("no home page")
    size = sum(len(v) for v in files.values())
    if size > 2_000_000:
        ok = False
        notes.append("the build is over 2 MB")
    if ok:
        notes.insert(0, "%d pages render, every link resolves" % len(pages))
    return files, {"ok": ok, "notes": notes}, {"calls": 0, "usd": 0.0}


def live_dir(ref):
    return ddir(ref) / "live"


def _publish_files(ref, files):
    tmp = ddir(ref) / "live.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for name, text in files.items():
        (tmp / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp / name).write_text(text, encoding="utf-8")
    if live_dir(ref).exists():
        shutil.rmtree(live_dir(ref))
    os.replace(tmp, live_dir(ref))


def engine_publish(ref, d, inp):
    files = read_files(ref, "Build", inp["v"])
    _publish_files(ref, files)
    ok = (live_dir(ref) / "index.html").is_file()
    host = (d or {}).get("host") or HOST_DEFAULT
    return files, {"ok": ok, "notes": ["live at the department's site address, served from %s" % host if ok
                                        else "the live copy has no home page"]}, {"calls": 0, "usd": 0.0}


ENGINE_FN = {"Plan": engine_plan, "Write": engine_write, "Check": engine_check, "Publish": engine_publish}


# ---- the motor -----------------------------------------------------------------------------------------------------
def _slot_id(engine, art, v):
    return "%s@%s.v%d" % (engine, slug(art), v)


def _today_spend(ref, engine):
    today = datetime.now().astimezone().date().isoformat()
    calls, usd = 0, 0.0
    for r in runs(ref):
        if r.get("engine") == engine and str(r.get("started", "")).startswith(today):
            calls += int((r.get("spend") or {}).get("calls") or 0)
            usd += float((r.get("spend") or {}).get("usd") or 0.0)
    return calls, usd


def _chain_of(ref, art, v):
    """The Brief version a piece of work descends from: its chain id."""
    seen = 0
    while art != "Brief" and seen < 20:
        row = next((r for r in versions(ref, art) if r["v"] == v), None)
        src = next((m for m in (row or {}).get("made_from") or [] if m.get("art")), None)
        if not src:
            return None
        art, v, seen = src["art"], src["v"], seen + 1
    return "brief.v%d" % v if art == "Brief" else None


def due(ref, peek=False):
    """The first slot the motor may start now, or a reason it may not. Returns
    (engine, input_row, slot) or (None, None, why). peek: a panel read asking; it writes nothing and never waits on the model."""
    rt = _runtime(ref)
    if rt:
        return rt.next_due(ref, peek=peek)
    d = dept(ref)
    if not d:
        return None, None, "no department"
    if d.get("stopped"):
        return None, None, "stopped"
    done = {r["slot"] for r in runs(ref) if r.get("slot") and r.get("status") in ("ok", "failed", "skipped")}
    running = [r for r in runs(ref) if r.get("status") == "running"]
    if running:
        return None, None, "running"
    for name, reads, writes, how in ENGINES:
        inp = latest(ref, reads, passed=(name == "Publish"))
        if not inp:
            continue
        slot = _slot_id(name, reads, inp["v"])
        if slot in done:
            continue
        if name == "Publish" and not versions(ref, "Live site"):
            a = next((x for x in asks(ref) if x.get("slot") == slot), None)
            if a is None:
                _put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "publish", "engine": "Publish", "slot": slot,
                               "text": "Publish: go live for the first time", "status": "pending", "created": now()})
                system_run(ref, "Identity", "routed the first publish to the owner")
                return None, None, "waits for the stamp"
            if a["status"] == "pending":
                return None, None, "waits for the stamp"
            if a["status"] == "refused":
                _put_run(ref, {"id": "r-" + uuid.uuid4().hex[:10], "engine": name, "system": False, "slot": slot,
                               "status": "skipped", "started": now(), "ended": now(), "what": "refused by the owner",
                               "wrote": None, "chain": _chain_of(ref, reads, inp["v"]), "spend": {"calls": 0, "usd": 0.0}, "retries": 0})
                continue
        calls, usd = _today_spend(ref, name)
        env = limit_of(d, name)
        if calls >= env.get("calls", 0) or usd >= env.get("usd", 0):
            if not any(x.get("kind") == "envelope" and x.get("engine") == name and x["status"] == "pending" for x in asks(ref)):
                _put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "envelope", "engine": name, "slot": slot,
                               "text": "%s is out of today's envelope" % name, "status": "pending", "created": now(), "escalated": True})
            return None, None, "%s is out of its envelope" % name
        chain = _chain_of(ref, reads, inp["v"])
        if chain and sum(1 for r in runs(ref) if r.get("chain") == chain) >= CHAIN_LIMIT:
            return None, None, "the chain from %s hit its limit" % chain
        return name, inp, slot
    return None, None, "nothing due"


def run_slot(ref, name, inp, slot):
    rt = _runtime(ref)
    if rt:
        return rt.run_engine(ref, name, inp, slot)
    d = dept(ref)
    reads = next(e[1] for e in ENGINES if e[0] == name)
    writes = next(e[2] for e in ENGINES if e[0] == name)
    prior = [r for r in runs(ref) if r.get("slot") == slot and r.get("status") == "interrupted"]
    row = _put_run(ref, {"id": "r-" + uuid.uuid4().hex[:10], "engine": name, "system": False, "slot": slot,
                         "status": "running", "started": now(), "ended": None, "what": "reading %s" % reads,
                         "wrote": None, "chain": _chain_of(ref, reads, inp["v"]), "spend": {"calls": 0, "usd": 0.0},
                         "retries": len(prior)})
    try:
        files, check, spend = ENGINE_FN[name](ref, d, inp)
        out = add_version(ref, writes, files, [{"art": reads, "v": inp["v"]}], row["id"], check)
        row.update({"status": "ok" if check.get("ok") else "failed", "ended": now(), "spend": spend,
                    "wrote": {"art": writes, "v": out["v"]},
                    "what": "%s from %s, check %s" % (writes, reads, "passed" if check.get("ok") else "failed")})
    except Exception as exc:  # noqa: BLE001 -- a failed run is a row, never a crash of the motor
        row.update({"status": "failed", "ended": now(), "what": "failed: %s" % exc})
    return _put_run(ref, row)


def motor_tick(inline=False, at=None):
    """One tick: a heartbeat, then at most one new run per department."""
    _write((Path(at) if at else home()) / "motor.json",
           {"last_tick": now(), "started": _MOTOR.get("started") or now(), "pid": os.getpid()})
    started = []
    for d in list_depts():
        ref = d["ref"]
        if d.get("runtime") == 2:
            try:
                _runtime(ref).sweep(ref)           # threads past their bound; runs past their window
            except Exception:  # noqa: BLE001 -- a sweep never stops the tick
                pass
        if ref in _BUSY:
            continue
        name, inp, slot = due(ref)
        if not name:
            continue
        started.append((ref, name, slot))
        if inline:
            run_slot(ref, name, inp, slot)
        else:
            _BUSY.add(ref)

            def work(r=ref, n=name, i=inp, s=slot):
                try:
                    run_slot(r, n, i, s)
                finally:
                    _BUSY.discard(r)
                    if (dept(r) or {}).get("runtime") == 2:
                        signal()                       # what it filed is the next engine's trigger
            threading.Thread(target=work, name="motor-" + ref, daemon=True).start()
    return started


def recover():
    """At start: a run left 'running' by a closed app is interrupted, so its slot is due again once."""
    for d in list_depts():
        for r in runs(d["ref"]):
            if r.get("status") == "running":
                r.update({"status": "interrupted", "ended": now(), "what": (r.get("what") or "") + "; the app closed mid-run"})
                _put_run(d["ref"], r)


def signal():
    """A trigger just happened: a post, a new version, a stamp, Start. The motor looks now, not at its next tick.
    An engine waits on no clock (founder, 2026-09-28); the tick is left as the system clock, for timers, and as the
    way a trigger written by another process is found."""
    k = _MOTOR.get("kick")
    if k is not None:
        k.set()


def run_until_idle(ref, limit=40):
    """Tests and the walk script: run the motor inline until nothing is due."""
    n = 0
    while n < limit:
        name, inp, slot = due(ref)
        if not name:
            return n
        run_slot(ref, name, inp, slot)
        n += 1
    return n


_LOCK = {"fd": None}


def hold_motor(at=None):
    """True when THIS process is the motor of this record. One motor per record,
    across processes: two windows of the app, Sutra beside Sutra Beta, or a
    server that is slow to stop would otherwise each tick the same record and
    start the same slot twice. The lock is the operating system's, so it is let
    go the instant its holder dies, and the next process to ask takes over."""
    if _LOCK["fd"] is not None:
        return True
    h = Path(at) if at else home()
    h.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(h / "motor.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    _LOCK["fd"] = fd
    # Only the motor may call a run interrupted: a second process that did this
    # at its own start would cut the first one's live run in two.
    recover()
    return True


def stop_motor(wait_s=4.0):
    """The app is closing: stop ticking now, and let the record go.

    WAITS FOR THE THREAD. Setting a flag and returning left a thread that could
    still take the lock and tick once more, after its owner had moved on. The
    thread is told through its own event, so a module reloaded under it cannot
    hand it a fresh, unset flag."""
    _MOTOR["stop"] = True
    ev, th = _MOTOR.get("event"), _MOTOR.get("thread")
    if ev is not None:
        ev.set()
    signal()                                           # wake it, so it sees the stop at once
    if th is not None and th is not threading.current_thread() and th.is_alive():
        th.join(wait_s)
    fd, _LOCK["fd"] = _LOCK["fd"], None
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass


def start_motor():
    """Start the one motor thread, on the launcher's word and no other.

    SUTRA_MOTOR=1 is that word: the Electron shell and the panel's launchers
    (run.sh, sutra-ui.sh, the one install.sh writes) say it; nothing else
    does. A server a test stands up, in its own process or as
    a child, never says it, so it never ticks anybody's record. The detector
    is asked as well, for the case where the word leaks into a test's
    environment from the shell that ran it.
    """
    if _MOTOR["thread"] is not None or os.environ.get("SUTRA_MOTOR") != "1" \
            or os.environ.get("SUTRA_MOTOR_OFF") == "1" or under_test():
        return False
    try:
        bound = os.path.realpath(str(home()))
    except RuntimeError:
        return False
    stop, kick = threading.Event(), threading.Event()
    _MOTOR.update({"started": now(), "stop": False, "event": stop, "home": bound, "kick": kick})

    def loop():
        # ONE MOTOR, ONE HOME. The motor serves the records home it was started
        # for. If the environment later names another, it stops; it never
        # follows. Found 2026-09-28: a thread outliving its test's temp home
        # landed on the operator's live one.
        while not stop.is_set():
            try:
                if os.path.realpath(str(home())) != bound:
                    break
                if hold_motor(bound):
                    motor_tick(at=bound)
            except Exception:  # noqa: BLE001 -- the motor never dies of one department
                pass
            kick.wait(TICK_S)                          # a signal, or the system clock's next tick
            kick.clear()
    _MOTOR["thread"] = threading.Thread(target=loop, name="sutra-motor", daemon=True)
    _MOTOR["thread"].start()
    return True


# ---- what the screens read -----------------------------------------------------------------------------------------
def status(ref):
    rs, ak = runs(ref), asks(ref)
    pend = [a for a in ak if a["status"] == "pending"]
    name, inp, why = due(ref, peek=True) if not any(r["status"] == "running" for r in rs) else (None, None, "running")
    waits = [{"what": a["engine"], "why": "for the stamp" if a["kind"] == "publish" else a["text"], "since": a["created"]} for a in pend]
    rt = _runtime(ref)
    if rt:                                     # the owner's own words nobody has answered yet (ER-9)
        waits += [{"what": "Identity", "why": "your words wait: " + w["words"], "since": w["since"]} for w in rt.front_state(ref)["waiting"]]
    return {"asks": [a for a in pend if not a.get("escalated")],
            "escalated": [a for a in pend if a.get("escalated")],
            "waits": waits,
            "running": [{"engine": r["engine"], "since": r["started"], "what": r.get("what")} for r in rs if r["status"] == "running"],
            "stopped": bool((dept(ref) or {}).get("stopped")), "next": why}


def health(ref):
    rs, ak = runs(ref), asks(ref)
    m = _read(home() / "motor.json", {})
    age = time.time() - _ts(m.get("last_tick", "")) if m else 1e9
    checks = []
    checks.append(("Motor", "ok" if age < 15 else ("warn" if age < 90 else "block"),
                   "Ticking" if age < 15 else ("Slow" if age < 90 else "Not ticking")))
    slots = [r["slot"] for r in rs if r.get("slot") and r.get("status") in ("ok", "failed")]
    twice = sorted({s for s in slots if slots.count(s) > 1})
    checks.append(("Slots", "block" if twice else "ok", "A slot ran twice" if twice else "Each slot ran once"))
    d = dept(ref) or {}
    arts = artifacts_of(d)
    gaps = [a for a in arts[1:] for v in versions(ref, a) if not v.get("run") or "check" not in v]
    checks.append(("Versions", "block" if gaps else "ok", "Every version has its run and its check" if not gaps else "A version with no run"))
    stale = [a for a in ak if a["status"] == "pending" and time.time() - _ts(a["created"]) > STALE_ASK_S]
    pending = [a for a in ak if a["status"] == "pending"]
    checks.append(("Stuck", "warn" if stale or pending else "ok", "An ask is waiting" if pending else "Nothing is waiting"))
    rt = _runtime(ref)
    if rt:                                     # the front door (ER-9): the owner's words answered, waiting, or lost at a bound
        fs = rt.front_state(ref)
        checks.append(("Front door", "warn" if fs["waiting"] or fs["lost"] else "ok",
                       "Your words are waiting" if fs["waiting"] else ("A request was lost at its bound" if fs["lost"] else "Every request answered")))
    checks.append(("Awake", "ok", "All five functions run as engines" if (dept(ref) or {}).get("runtime") == 2
                   else "Identity, Priority and Coordination run; Adaptation and Audit are paused"))
    envs = (dept(ref) or {}).get("envelopes", {})
    over = []
    # an envelope is two limits, and either one stops the engine (Priority's gate); an engine Priority has not given its
    # own yet (its plan not registered, PRD M4.1) is read against the one it would be given (limit_of)
    for e in list(envs) + [n for n in (x[0] for x in engines_of(d)) if n not in envs]:
        calls, usd = _today_spend(ref, e)
        env = (envs[e] if e in envs else limit_of(d, e)) or {}
        if calls >= int(env.get("calls", ENVELOPE["calls"])) or usd >= float(env.get("usd", ENVELOPE["usd"])):
            over.append(e)
    checks.append(("Budget", "warn" if over else "ok", "Inside every envelope" if not over else "Over: " + ", ".join(over)))
    if d.get("runtime") == 2:
        # an engine the record names that this app's Library does not define (born in an older bundle, or its file gone):
        # said here, and its card says Missing; the rest of the line runs (found live 2026-09-29, Beta 2.306.16)
        import engine_runtime
        lost = engine_runtime.missing_engines(d)
        checks.append(("Library", "block" if lost else "ok",
                       "Every engine on the record has its template" if not lost
                       else "; ".join("%s has no template in this app's Library; say its idea again to shape it anew" % n for n in lost)))
    live = latest(ref, arts[-1])
    dw = kind_of(d).get("done_words") or ["The site is live", "Not live yet"]
    checks.append(("Done", "ok" if live and (live.get("check") or {}).get("ok") else "warn", dw[0] if live else dw[1]))
    work = {e[0] for e in engines_of(d)}
    never = [("A run with no slot", not any(r for r in rs if not r.get("system") and r["engine"] in work and not r.get("slot"))),
             ("A version with no run", not gaps), ("A slot run twice", not twice),
             ("An uncounted retry", True), ("A hidden exchange", True),
             ("A silent skip", all(r.get("what") for r in rs if r.get("status") == "skipped"))]
    timeline = [{"engine": r["engine"], "system": bool(r.get("system")), "status": r["status"], "started": r["started"],
                 "ended": r.get("ended"), "slot": r.get("slot"), "what": r.get("what"), "words": r.get("words")} for r in rs[-60:]]
    return {"motor": {"last_tick": m.get("last_tick"), "age_s": round(age) if age < 1e8 else None},
            "checks": [{"name": n, "state": s, "line": l} for n, s, l in checks],
            "never": [{"name": n, "ok": bool(ok)} for n, ok in never], "timeline": timeline}


def engine_view(ref, name):
    d = dept(ref) or {}
    reads, writes, how = next(((e[1], e[2], e[3]) for e in engines_of(d) if e[0] == name), (None, None, None))
    rs = [r for r in runs(ref) if r["engine"] == name]
    calls, usd = _today_spend(ref, name)
    env = limit_of(d, name)
    if not reads:
        if name not in (d.get("engines") or []):
            return None
        # on the record, but no template in this app's Library (born in an older bundle): a card that says so, never a crash
        return {"name": name, "reads": None, "writes": None, "runs_as": None, "slot": None, "state": "Missing", "missing": True,
                "envelope": {"calls": env["calls"], "usd": env["usd"], "used_calls": calls, "used_usd": round(usd, 3)},
                "window_min": (d.get("windows") or {}).get(name), "runs": list(reversed(rs[-20:]))}
    state = "Running" if any(r["status"] == "running" for r in rs) else ("Stopped" if d.get("stopped") else "Idle")
    return {"name": name, "reads": reads, "writes": writes, "runs_as": how, "slot": "after a new " + reads,
            "state": state, "envelope": {"calls": env["calls"], "usd": env["usd"], "used_calls": calls, "used_usd": round(usd, 3)},
            "window_min": (d.get("windows") or {}).get(name), "runs": list(reversed(rs[-20:]))}


def trace(ref, art, v):
    out, seen = [], 0
    while art and seen < 12:
        row = next((r for r in versions(ref, art) if r["v"] == int(v)), None)
        if not row:
            break
        out.append({"kind": "version", "art": art, "v": row["v"], "at": row["at"], "check": row.get("check"), "note": row.get("note")})
        run = next((r for r in runs(ref) if r["id"] == row.get("run")), None)
        if run:
            out.append({"kind": "run", "engine": run["engine"], "at": run["started"], "slot": run.get("slot"),
                        "spend": run.get("spend"), "status": run["status"]})
        nxt = next((m for m in row.get("made_from") or [] if m.get("art")), None)
        for m in row.get("made_from") or []:
            if m.get("ask"):
                out.append({"kind": "ask", "text": m["ask"], "at": m.get("at")})
        if not nxt:
            break
        art, v, seen = nxt["art"], nxt["v"], seen + 1
    return out


def map_view(ref):
    d = dept(ref)
    if not d:
        return None
    rs = runs(ref)
    st = status(ref)
    systems = []
    for s in SYSTEMS:
        paused = s in PAUSED_SYSTEMS and d.get("runtime") != 2
        last = next((r for r in reversed(rs) if r["engine"] == s), None)
        # a line that ends with the owner's own words carries them (words), so the screen shows them as said (PRD M1.7)
        systems.append({"name": s, "state": "paused" if paused else "running", "last": last and last.get("what"),
                        "words": last and last.get("words")})
    engines = [x for x in (engine_view(ref, e[0]) for e in engines_of(d)) if x]
    rt = _runtime(ref)
    table = rt.coordination(ref) if rt else {}
    line = set(table.get("line") or []) if rt else None
    # before Root's check the line it was born with is not a plan (S1, Empty: Brief v1 and 'No plan yet'): the same test
    # as Coordination's pane (functions_view.no_plan), so the Map and S7 never disagree on whether a plan exists
    planned = True
    if rt:
        import functions_view
        planned = not functions_view.no_plan(ref, d, table)
    left = {r.get("engine") for r in table.get("left_out") or [] if isinstance(r, dict)}
    slots = {r.get("engine"): r for r in table.get("timetable") or [] if isinstance(r, dict)}
    for e in engines:
        e.pop("runs", None)
        last = next((r for r in reversed(rs) if r["engine"] == e["name"]), None)
        e["last"] = last and {"status": last["status"], "at": last["started"], "what": last.get("what"), "words": last.get("words")}
        if any(a["engine"] == e["name"] and a["status"] == "pending" for a in asks(ref)):
            e["state"] = "Waits"
        # an engine the registered plan left out stays on the record and never runs (PRD M4.2): it says so
        e["in_line"] = line is None or e["name"] in line
        if e["name"] in left and e["state"] not in ("Running", "Missing"):
            e["state"] = "Left out"
        e["timetable"] = slots.get(e["name"])           # its slot in Coordination's timetable, as Coordination wrote it (PRD M4.3)
    names = artifacts_of(d)
    arts = []
    for a in names:
        vs = versions(ref, a)
        arts.append({"name": a, "slug": slug(a), "versions": len(vs), "latest": vs[-1] if vs else None})
    recent = [{"engine": r["engine"], "system": bool(r.get("system")), "status": r["status"], "at": r["started"], "what": r.get("what"),
               "words": r.get("words")} for r in reversed(rs[-10:])]
    kind = d.get("kind") or "website"
    return {"ref": ref, "name": d["name"], "goal": d["goal"], "done": d["done"], "rules": d["rules"], "owner": d["owner"],
            "control": d["control"], "stopped": d.get("stopped"), "systems": systems, "engines": engines, "artifacts": arts,
            "status": st, "health": health(ref), "recent": recent,
            "live": "Live site" in names and bool(latest(ref, "Live site")), "requests": requests(ref)[-10:],
            # a Root is born with its goal: it makes departments; every other kind takes its goal from the owner's words
            "has_goal": kind == "root" or bool(versions(ref, names[0])) or bool(requests(ref)), "templates": d.get("templates") or {},
            "runtime": d.get("runtime") or 1, "kind": kind, "say": kind_of(d).get("say") or "", "planned": planned,
            "root": ref if kind == "root" else d.get("root"), "host": d.get("host")}
