#!/usr/bin/env python3
"""qa/j2_metrics.py -- the proof run of the five functions (PRD M10.4, M10.5; amendment A1, package W2-PROOF).

It runs the scenario suite with its models stubbed (decision C2) on a records home that is kept, then reads the record
and nothing else, and reports the success metrics of PRD section 5: SM-1 to SM-12, SM-13 (writes the interface refused,
M10.5) and SM-14 (journey rows unproven, A3). A metric is `met`, `gap` (it names each gap), `pending` (it needs the nine
live Beta runs or the Human Simulation walk, which stay pending under C2), `recorded` (a figure that gates nothing) or
`not run` (its input is not there).

    qa/j2_metrics.py                 run the scenario suite, print the report; exit 0
    qa/j2_metrics.py --check         the same; exit 1 on a gap in SM-1, SM-2, SM-3, SM-4 or SM-13, or a failed lane (the gate's
                                     line)
    qa/j2_metrics.py --strict        exit 1 on any gap (SM-6, SM-7 and the rest too: W3-PROOF's rerun)
    qa/j2_metrics.py --records DIR   read a records home or a kept tree (a Beta home, a kept run) and run nothing
    --json | --out FILE | --keep DIR | --files a.py,b.py | --full | --workers N | --mode refuse|app | --ledger

THE RECORD. Per department: dept.json, runs.json, asks.json, board.jsonl, readings.jsonl, prices.jsonl, j2-events.jsonl,
j2-state.json, coordination.json. The files are read as they lie on disk (a torn line is skipped, as record.lines does);
no app module is imported, so the script reads a home the app is not running on. Three metrics read the repository
beside it: SM-2 (suites.sh, by name), SM-12 (the decision log) and SM-14 (the journeys' status files, which are the record
of the last gate; it runs no journey test).

REFUSE MODE (M10.5). The interface's mode is a code constant, never an environment variable. The suite's processes load
this module as a pytest plugin (`-p j2_metrics`, only when J2_METRICS_DUMP is set): it puts layer_schema.MODE at 'refuse'
before each test, counts the entries the interface adds to S.REFUSED and dumps them, so SM-13 is counted in refuse mode
whatever the app's constant says. `--mode app` leaves the constant alone.
"""
import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from functools import cached_property
from pathlib import Path

try:
    import pytest
    _impl = pytest.hookimpl
except Exception:  # noqa: BLE001 -- the script reads records without pytest; only the plugin hooks want it
    def _impl(**_kw):
        return lambda fn: fn

HERE = Path(__file__).resolve().parent
UI = HERE.parent                                                    # sutra-ui
SCHEMA = "j2.metrics.v1"

#: the scenario suite (M10.4): the department's life and this package's own proof scenarios (one department of each kind
#: to a real done). A node id runs only that class. A file that writes a record by hand, or provokes the interface on
#: purpose (test_layer_priority.py, test_layer_writers.py), is not a scenario: its rows would be read as the build's own.
SCENARIOS = ("test_j1.py", "test_j2.py", "test_j2_api.py", "test_j2_metrics.py::TestProofScenarios")
#: --full adds the layers' own files (about four minutes more). Some of their tests build a record by hand (test_layer_audit.py
#: calls J.audited with a made-up reading, which is a goal claim with no reading behind it), so a gap there may be a fixture's
FULL = ("test_j2_identity.py", "test_layer_identity.py", "test_layer_adaptation.py", "test_layer_audit.py",
        "test_layer_coordination.py", "test_layer_root.py", "test_covering_checks.py", "test_functions_view.py")
#: the lanes the department suite must run (SM-2, M0.1): suites.sh names each on a pytest line
DEPARTMENT_LANES = ("test_j2.py", "test_j2_api.py", "test_j1.py")
KINDS_TO_PROVE = ("website", "default", "organic")                  # SM-7
FUNCTIONS = ("Identity", "Adaptation", "Priority", "Coordination", "Audit", "Setup", "Root")
END_STATES = ("waiting", "blocked", "unread")                       # SM-6: the cycle stands and only the owner can move it
JOURNEYS = ("J1", "J2", "J3", "J4")                                 # SM-14
UNPROVEN = ("unproven", "failing", "fault")
RID = re.compile(r"^r-[0-9a-f]{8}$")
RANK = {"met": 0, "to_confirm": 1, "not_met": 2}                    # the worse verdict stands (A1-16); == R.VERDICT_RANK
TARGET = {"effort": 3, "calls": 40, "usd": 3.0, "share": 0.2}       # SM-8, SM-9 (Q15, proposed), SM-11
#: the metrics the gate's line fails on (--check): the ones the build already holds at 0
HARD = ("SM-1", "SM-2", "SM-3", "SM-4", "SM-13")
#: the metrics whose gaps are runs, posts or rows, which can run to hundreds: the text report lists the first few and a count,
#: and the report file (--out) names them all. Every other metric names each of its gaps in the text: "and 1 more" would hide the
#: one a person looks for (SM-6, one gap for each department that stands with no next move for the owner, was cut so)
LONG_LISTS = ("SM-3", "SM-4", "SM-11", "SM-14")
#: what stays pending under C2: the live runs spend the owner's subscription and need Sutra Beta installed
PENDING = (
    ("nine live Beta runs", "three briefs for each of website, default and organic, each inside its ceiling: they put "
     "SM-7, SM-8, SM-9 and SM-11 on live data (this report measures the same on the stubbed suite)"),
    ("the Human Simulation walk", "a person at the installed app's own buttons, with the narrowest-viewer check (nothing past "
     "either edge)"),
    ("SM-5 on a Beta walk", "the timestamps of a change and of the screen showing it; the JS timer-stub test is the "
     "suite's half"),
)


# ---- reading the record ----------------------------------------------------------------------------------------------
def _doc(p, default):
    """A document, or the default when it is not there or not readable (record.read)."""
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- a torn document reads as absent
        return default


def _lines(p):
    """A journal, oldest first; a torn line is skipped (record.lines)."""
    try:
        text = Path(p).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line) if line.strip() else None
        except ValueError:
            row = None
        if isinstance(row, dict):
            out.append(row)
    return out


def _list(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


class Dept:
    """One department, read from its folder: the record and nothing else."""

    def __init__(self, path, group=""):
        self.path, self.group = Path(path), group

    @cached_property
    def dept(self):
        d = _doc(self.path / "dept.json", {})
        return d if isinstance(d, dict) else {}

    @cached_property
    def runs(self):
        return _list(_doc(self.path / "runs.json", []))

    @cached_property
    def asks(self):
        return _list(_doc(self.path / "asks.json", []))

    @cached_property
    def board(self):
        return _lines(self.path / "board.jsonl")

    @cached_property
    def readings(self):
        return _lines(self.path / "readings.jsonl")

    @cached_property
    def prices(self):
        return _lines(self.path / "prices.jsonl")

    @cached_property
    def events(self):
        return _lines(self.path / "j2-events.jsonl")

    @cached_property
    def state(self):
        s = _doc(self.path / "j2-state.json", {})
        return s if isinstance(s, dict) else {}

    @cached_property
    def table(self):
        t = _doc(self.path / "coordination.json", {})
        return t if isinstance(t, dict) else {}

    @property
    def ref(self):
        return self.dept.get("ref") or self.path.name

    @property
    def kind(self):
        return self.dept.get("kind")

    @property
    def lives_j2(self):
        """The department lives a J2 cycle (j2-state.json names one); a root, and a department that began with the
        switch off, does not."""
        return bool(self.state.get("cycle_id"))

    @property
    def label(self):
        name = self.dept.get("name") or self.ref
        return "%s / %s (%s)" % (self.group, name, self.kind) if self.group else "%s (%s)" % (name, self.kind)

    def registered(self):
        """Every engine a registered workflow of this department names, and the engines the owner added (J5)."""
        names = set()
        for w in _list(self.dept.get("workflows")):
            for e in w.get("engines") or []:
                names.add(e.get("name") if isinstance(e, dict) else e)
        names.update(self.table.get("grown") or [])
        return names


def find_departments(root):
    """Every department folder under `root`: a records home (<home>/<ref>/dept.json) or a kept tree
    (<lane>/bt/<test>/departments/<ref>/dept.json). A link is not followed: pytest's `current` link would count a test twice."""
    root, out = Path(root), []
    for dirpath, dirnames, filenames in os.walk(root):
        if "dept.json" in filenames:
            dirnames[:] = []                                        # a department holds no department
            parts = Path(dirpath).relative_to(root).parts
            group = "/".join(p for p in parts[:parts.index("departments")] if p != "bt") if "departments" in parts else ""
            out.append(Dept(dirpath, group))
        else:
            dirnames.sort()
    return sorted(out, key=lambda d: (d.group, d.ref))


# ---- the metrics -----------------------------------------------------------------------------------------------------
def _m(sid, name, target, value, ok, gaps=(), note="", status=None, **more):
    """One metric. `status` is met or gap by `ok` unless it is given; `gaps` names each way the target is not met."""
    out = {"id": sid, "name": name, "target": target, "value": value, "status": status or ("met" if ok else "gap"),
           "gaps": list(gaps), "note": note}
    out.update(more)
    return out


def _reading_ids(event):
    """The readings an event cites, as ids, and the (artifact, version) pairs it cites in the shape the ledger wrote
    before Identity's covering took the claim: evidence_refs of {artifact, version}, or a reading id (as a string, or as
    the value of a `reading` key), or payload.reading."""
    ids, pairs = [], []
    refs = list(event.get("evidence_refs") or []) + [(event.get("payload") or {}).get("reading")]
    for r in refs:
        if isinstance(r, str) and RID.match(r):
            ids.append(r)
        elif isinstance(r, dict):
            for key in ("reading", "reading_id", "id", "ref"):
                if isinstance(r.get(key), str) and RID.match(r[key]):
                    ids.append(r[key])
            art, ver = r.get("artifact"), r.get("version", r.get("v"))
            if art and isinstance(ver, int):
                pairs.append((art, ver))
    return ids, pairs


def _reading_fault(d, reading):
    """Why a reading does not clear done-when, or None: it was read, it holds a row for every done-when item of the
    department, the worse row of each is met, and it holds no high finding."""
    if not reading.get("read"):
        return "its reading says it was not read (%s)" % (reading.get("why_not_read") or "no reason given")
    ids = [i.get("id") for i in _list(d.dept.get("done_items")) if i.get("id")]
    if not ids:
        return "the department has no done-when item to read it against"
    stand = {}
    for row in _list(reading.get("items")):
        v = row.get("verdict")
        if row.get("id") and v in RANK and RANK[v] >= RANK.get(stand.get(row["id"]), -1):
            stand[row["id"]] = v
    bad = ["%s %s" % (i, stand[i].replace("_", " ") if i in stand else "has no row") for i in ids if stand.get(i) != "met"]
    if bad:
        return "its reading does not show every item met: %s" % "; ".join(bad[:3])
    high = [f.get("id") or "a finding" for f in _list(reading.get("findings")) if f.get("severity") == "high"]
    if high:
        return "its reading holds a high finding (%s)" % ", ".join(high[:3])
    return None


def claim_fault(d, event):
    """Why one goal.reached event is a claim without the reading it needs, or None when the reading stands behind it."""
    ids, pairs = _reading_ids(event)
    if not ids and not pairs:
        return "it cites no reading and no version"
    cited = [r for r in d.readings if r.get("id") in ids or (r.get("artifact"), r.get("v")) in pairs]
    if not cited:
        return "no reading of %s is on the record" % (", ".join(ids) or " / ".join("%s v%s" % p for p in pairs))
    at = str(event.get("occurred_at") or "")
    before = [r for r in cited if not at or str(r.get("at") or "") <= at]
    if not before:                                                  # a reading made after the claim is not behind it
        return "%s came after the claim" % ("its only reading" if len(cited) == 1 else "every reading it cites")
    return _reading_fault(d, before[-1])


def sm1(depts):
    claims, gaps = 0, []
    for d in depts:
        for e in d.events:
            if e.get("action") == "goal.reached":
                claims += 1
                why = claim_fault(d, e)
                if why:
                    gaps.append("%s: goal reached (event %s) and %s" % (d.label, e.get("event_id") or e.get("seq"), why))
    return _m("SM-1", "'Goal reached' claimed without a reading of every done-when item", "0", len(gaps), not gaps, gaps,
              "matches each goal.reached to the reading of the version it cites, made at or before the claim", claims=claims, read="%d claims" % claims)


def sm3(depts):
    runs, scope, gaps = 0, 0, []
    for d in depts:
        if not d.lives_j2:
            continue
        scope += 1
        ok = d.registered() | set(FUNCTIONS)
        for r in d.runs:
            runs += 1
            if r.get("engine") not in ok:
                gaps.append("%s: ran %s (run %s, %s), on no registered line and not added through J5" % (
                    d.label, r.get("engine"), r.get("id"), r.get("slot") or "no slot"))
    return _m("SM-3", "Runs of an engine on no registered line and not added through J5", "0", len(gaps), not gaps, gaps,
              "runs.json against the union of dept.workflows, the engines added (grown) and the five functions",
              departments=scope, runs=runs, read="%d runs of %d departments" % (runs, scope))


def sm4(depts):
    posts, gaps = 0, []
    for d in depts:
        for p in d.board:
            if any(str(x).lower() in ("owner", "user") for x in p.get("dst") or []):
                posts += 1
                if p.get("src") != "Identity":
                    gaps.append("%s: %s posted to the owner (board %s, %s)" % (d.label, p.get("src"), p.get("n"), p.get("msg_type")))
    return _m("SM-4", "Posts to the owner from anyone but Identity", "0", len(gaps), not gaps, gaps,
              "board.jsonl: every post whose destination is the owner", posts=posts, read="%d posts to the owner" % posts)


def sm6(depts):
    seen, gaps, unread = 0, [], 0
    for d in depts:
        st = d.state.get("state")
        if st not in END_STATES:
            continue
        seen += 1
        pending = [a for a in d.asks if a.get("status") == "pending"]
        if st == "blocked":
            pending = [a for a in pending if a.get("options")]
        if not pending:
            unread += st == "unread"
            gaps.append("%s: stands %s and holds no pending ask%s: the owner has no next move" % (
                d.label, st, " with options" if st == "blocked" else ""))
    # an unread cycle is a product gap, not this report's: J.not_read leaves the cycle unread and files no ask. It is carried
    # to W3-PROOF in the report itself, so the gap does not sit in a number alone
    carried = ["%d of these stand unread: Audit could not read the version (the stubbed suite has no model to read it), so J.not_read "
               "leaves the cycle unread and no ask is filed. Either Identity files an ask for an unread cycle (a product change "
               "outside this package), or W3-PROOF rules that a cycle that is retried is not a dead end; until one of them, "
               "--strict fails on SM-6" % unread] if unread else []
    return _m("SM-6", "Dead-end states: the owner has no next move", "0", len(gaps), not gaps, gaps,
              "an end state that is not done (waiting, blocked or unread; stopped has Start) holds a pending ask; a "
              "question the owner answers in words counts as a next move, a blocked cycle needs options", end_states=seen,
              unread=unread, carried=carried, read="%d end states" % seen)


def real_done(d):
    """The department's goal is reached by a claim a reading stands behind (no hand-written state counts)."""
    claims = [e for e in d.events if e.get("action") == "goal.reached"]
    return d.state.get("state") == "done" and bool(claims) and all(claim_fault(d, e) is None for e in claims)


def sm7(depts):
    done = {k: [d for d in depts if d.kind == k and real_done(d)] for k in KINDS_TO_PROVE}
    got = [k for k in KINDS_TO_PROVE if done[k]]
    gaps = ["no %s department reached a done a reading stands behind" % k for k in KINDS_TO_PROVE if k not in got]
    return _m("SM-7", "Kinds that reach a real done", "3 of 3 (website, default, organic)", len(got), not gaps, gaps,
              "a department of the kind whose cycle is done by a goal.reached its reading stands behind",
              of=len(KINDS_TO_PROVE), reached=got, read="of %d: %s" % (len(KINDS_TO_PROVE), ", ".join(got) or "none"))


def _median(xs):
    return statistics.median(xs) if xs else None


def sm8(depts):
    by_ref = {d.ref: d for d in depts}
    effort, rows = [], []
    for d in depts:
        if d.kind == "root" or not real_done(d):
            continue
        root = by_ref.get(d.dept.get("parent") or d.dept.get("root"))
        asked = len(d.asks) + (len([p for p in root.board if p.get("src") == "Identity" and "Owner" in (p.get("dst") or [])
                                    and (p.get("payload") or {}).get("word") == "question"]) if root else 0)
        effort.append(asked)
        rows.append("%s: %d" % (d.label, asked))
    med = _median(effort)
    ok = med is not None and med <= TARGET["effort"]
    gaps = [] if med is None or ok else ["median %s is over %d: %s" % (med, TARGET["effort"], "; ".join(rows[:6]))]
    return _m("SM-8", "Owner effort from birth to goal (questions and asks)", "median %d or fewer (proposed, Q15)" % TARGET["effort"],
              med, ok, gaps, "the asks in asks.json and Identity's questions on the root's board, per department that "
              "reached done; stubbed suite, so a floor", departments=len(effort),
              status="gap" if med is not None and not ok else ("met" if ok else "not run"))


def sm9(depts):
    calls, usd, rows = [], [], []
    for d in depts:
        if d.kind != "website" or not real_done(d):
            continue
        c = sum(int((r.get("spend") or {}).get("calls") or 0) for r in d.runs)
        u = round(sum(float((r.get("spend") or {}).get("usd") or 0) for r in d.runs), 4)
        calls.append(c)
        usd.append(u)
        rows.append("%s: %d calls, %.2f USD" % (d.label, c, u))
    mc, mu = _median(calls), _median(usd)
    ok = mc is not None and mc <= TARGET["calls"] and mu <= TARGET["usd"]
    gaps = [] if mc is None or ok else ["median %s calls and %s USD against %d and %.0f: %s" % (
        mc, mu, TARGET["calls"], TARGET["usd"], "; ".join(rows[:6]))]
    return _m("SM-9", "Cost of a website department from birth to goal", "median %d or fewer calls and %.0f USD or less (proposed, Q15)" % (
        TARGET["calls"], TARGET["usd"]), {"calls": mc, "usd": mu} if mc is not None else None, ok, gaps,
        "the spend in runs.json per website department that reached done; a stubbed model prices a call at 0.01 "
        "USD, so the live figure waits for the Beta runs", departments=len(calls),
        status="gap" if mc is not None and not ok else ("met" if ok else "not run"))


def _day(r):
    return str(r.get("started") or "")[:10]


def sm11(depts):
    total, flagged, gaps = 0, 0, []
    for d in depts:
        work = sorted((r for r in d.runs if not r.get("system")), key=lambda r: str(r.get("started") or ""))
        slots = Counter(r.get("slot") for r in work if r.get("slot"))
        env, spent = d.dept.get("envelopes") or {}, defaultdict(lambda: [0, 0.0])
        for i, r in enumerate(work):
            total += 1
            why = []
            s = spent[(r.get("engine"), _day(r))]
            s[0] += int((r.get("spend") or {}).get("calls") or 0)
            s[1] += float((r.get("spend") or {}).get("usd") or 0)
            e = env.get(r.get("engine")) or {}
            if e and (s[0] > float(e.get("calls", "inf")) or s[1] > float(e.get("usd", "inf"))):
                why.append("overspent its envelope")
            if r.get("slot") and slots[r["slot"]] > 1:
                why.append("shares slot %s with another run" % r["slot"])
            for o in work[:i]:
                if (o.get("ended") is None and o.get("status") == "running") or str(o.get("ended") or "") > str(r.get("started") or ""):
                    why.append("started while %s was open" % o.get("engine"))
                    break
            if why:
                flagged += 1
                gaps.append("%s: %s (run %s) %s" % (d.label, r.get("engine"), r.get("id"), " and ".join(why)))
    share = round(flagged / total, 3) if total else None
    ok = share is None or share < TARGET["share"]
    return _m("SM-11", "Runs that overspend their envelope or clash in a slot", "fewer than 1 run in 5 (over 4 weeks on Beta)",
              share, ok, [] if ok else gaps, "runs.json against the envelopes, here on the stubbed suite, which proves the "
              "count and not the four weeks; a run retried on its slot counts as sharing it" + ("" if ok else "."),
              runs=total, flagged=flagged, status=None if total else "not run", flagged_runs=gaps[:12])


def sm12(ui=UI):
    p = Path(ui) / "design" / "PRD-FIVE-FUNCTIONS-DECISIONS.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return _m("SM-12", "Marks before stable", "100 percent", None, False, [], "the decision log is not there", status="not run")
    marks = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.fullmatch(r"MK-\d+", cells[0]) and cells[0] not in marks:
            marks[cells[0]] = bool(cells[2])
    done = sum(marks.values())
    pct = round(100.0 * done / len(marks), 1) if marks else None
    return _m("SM-12", "Marks before stable", "100 percent of MK rows marked", pct, bool(marks) and done == len(marks),
              ["%s has no decision" % k for k, v in marks.items() if not v],
              "each MK row of the decision log carries what was taken; every one is a default taken without the owner "
              "(the owner asked for the build not to wait), so none ships to stable as the owner's mark",
              marked=done, of=len(marks))


def sm2(lanes, suites_text):
    """Lanes that report pass with no test run, and the department lanes the gate must name (M0.1)."""
    gaps = ["%s ran 0 tests" % ln["lane"] for ln in lanes if ln["tests"] == 0]
    if suites_text is not None:
        gaps += ["qa/walks/suites.sh does not run %s" % f for f in DEPARTMENT_LANES if f not in suites_text]
    return _m("SM-2", "Test lanes that report pass with 0 tests run", "0; test_j2, test_j2_api and test_j1 run in the "
              "department suite", len(gaps), not gaps, gaps, "the lanes of this run, and suites.sh by name"
              if lanes else "no lane was run (records only); suites.sh read by name", lanes=len(lanes),
              tests=sum(ln["tests"] for ln in lanes), status=None if (lanes or gaps) else "not run")


OWNERSHIP = re.compile(r"\$\.(\w+): is (\w+)'s, and (\w+) wrote it")


def ownership_rows(depts, lanes=()):
    """Rows written with `by` for a department key another layer owns: {dept, key, owner, writer, kept}. From the rows the
    interface put on runs.json, and from the entries the suite's processes dumped (a fault with no department leaves only
    an entry); one that both show is listed once."""
    out = []
    for d in depts:
        for r in d.runs:
            what = str(r.get("what") or "")
            m = OWNERSHIP.search(what)
            if m and what.startswith(("refused a write", "kept a record")):
                out.append({"dept": d.label, "key": m.group(1), "owner": m.group(2), "writer": m.group(3),
                            "kept": what.startswith("kept")})
    seen = {(o["key"], o["owner"], o["writer"]) for o in out}
    for ln in lanes:
        for r in ln.get("refused_rows") or []:
            for f in r.get("faults") or []:
                m = OWNERSHIP.search(str(f))
                if m and (m.group(1), m.group(2), m.group(3)) not in seen:
                    seen.add((m.group(1), m.group(2), m.group(3)))
                    out.append({"dept": "%s (%s)" % (r.get("test") or ln.get("lane"), r.get("ref") or "no department"), "key": m.group(1),
                                "owner": m.group(2), "writer": m.group(3), "kept": bool(r.get("kept"))})
    return out


def sm13(depts, lanes=(), mode=None):
    """Writes the interface refused (M10.5): runs.json rows that begin 'refused a write', the faults it kept in the
    paths that never refuse (a row 'kept a record'), and the entries the suite's processes added to S.REFUSED. A fault
    with a department leaves a row and an entry, one without leaves an entry only, so the larger count is the faults."""
    refused = [(d, r) for d in depts for r in d.runs if str(r.get("what") or "").startswith("refused a write")]
    kept = [(d, r) for d in depts for r in d.runs if str(r.get("what") or "").startswith("kept a record")]
    entries = sum(ln.get("refused_entries", 0) for ln in lanes)
    own = ownership_rows(depts, lanes)
    value = max(len(refused) + len(kept), entries)
    gaps = ["%s: %s" % (d.label, str(r.get("what"))[:200]) for d, r in (refused + kept)[:20]]
    gaps += ["%s: %d entries in S.REFUSED" % (ln["lane"], ln["refused_entries"]) for ln in lanes if ln.get("refused_entries")]
    gaps += ["ownership: %s wrote %s, which is %s's (%s)" % (o["writer"], o["key"], o["owner"], o["dept"]) for o in own]
    return _m("SM-13", "Writes refused by the interface", "0, and no ownership row", value, value == 0 and not own, gaps,
              "mode: %s; %d refused rows, %d kept rows, %d entries in S.REFUSED, %d ownership rows" % (
                  mode or "not stated", len(refused), len(kept), entries, len(own)),
              refused_rows=len(refused), kept_rows=len(kept), entries=entries, ownership=own, mode=mode)


def _fresh(ui, jid, sha):
    """Whether a status file's hash is the journey's now: True, False, or None when the journey file is not there. The
    hash is the sha256 of the journey's canonical JSON (sorted keys, no spaces); where that does not match, the loader's
    own (journeys.definitions_sha) decides, when the package is on main."""
    j = _doc(Path(ui) / "journeys" / (jid + ".json"), None)
    if not isinstance(j, dict):
        return None
    if any(sha == hashlib.sha256(json.dumps(j, sort_keys=True, separators=(",", ":"), ensure_ascii=a).encode("utf-8")).hexdigest()
           for a in (True, False)):
        return True
    try:
        if str(ui) not in sys.path:
            sys.path.insert(0, str(ui))
        import journeys
        return sha == journeys.definitions_sha(jid)
    except Exception:  # noqa: BLE001 -- no loader, or it refuses the file: the canonical hash did not match, so it is stale
        return False


def _backlog_id(journey, jid, key):
    """The backlog entry a waiting row names: the journey's backlog list says which row it is for ('step:8', 'edge:J2.8',
    'build:B4'); failing that, the row's own `backlog` field. A status key may carry the journey id ('J2:step:8')."""
    key = key[len(jid) + 1:] if key.startswith(jid + ":") else key
    for b in _list(journey.get("backlog")):
        if b.get("row") == key:
            return b.get("id")
    kind, _, ident = key.partition(":")
    for r in _list(journey.get("steps" if kind == "step" else "edges")):
        if str(r.get("n") if kind == "step" else r.get("id")) == ident and r.get("backlog"):
            return r["backlog"]
    return None


def sm14(ui=UI):
    """Rows of J1 to J4 whose state, in journeys/status/<id>.json, is unproven, failing or fault (A3). The files are
    the record of the last gate; this reads them and runs no journey test. A file that is absent or stale is not run."""
    gaps, listed, not_run, counted, rows = [], [], [], 0, 0
    for jid in JOURNEYS:
        doc = _doc(Path(ui) / "journeys" / "status" / (jid + ".json"), None)
        if not isinstance(doc, dict) or not isinstance(doc.get("rows"), dict):
            not_run.append("%s (no status file)" % jid)
            continue
        if _fresh(ui, jid, doc.get("definitions_sha")) is not True:
            not_run.append("%s (stale)" % jid)
            continue
        counted += 1
        journey = _doc(Path(ui) / "journeys" / (jid + ".json"), {})
        for key, row in sorted(doc["rows"].items()):
            rows += 1
            st = (row or {}).get("state")
            if st in UNPROVEN:
                gaps.append("%s %s is %s" % (jid, key, st))
            elif st in ("partly", "wanted"):
                listed.append("%s %s is %s (%s)" % (jid, key, st, _backlog_id(journey, jid, key) or "no backlog id named"))
    if not counted:
        return _m("SM-14", "Journey rows unproven", "0", None, False, [], "no journey status file to read yet (%s)" % ", ".join(
            not_run), status="not run", not_run=not_run)
    return _m("SM-14", "Journey rows unproven", "0", len(gaps), not gaps, gaps,
              "the status files of the last gate, read and not run%s" % ("; not run: " + ", ".join(not_run) if not_run else ""),
              rows=rows, not_run=not_run, waiting=listed)


def sm5():
    return _m("SM-5", "Freshness of the five-function view", "within 3 s for 95 percent of changes", None, False, [],
              "this report reads no screen: the JS timer-stub test and a Beta walk's timestamps measure it", status="pending")


def sm10(p95):
    if p95 is None:
        return _m("SM-10", "Ledger append time", "p95 5 ms or less at 10,000 events", None, False, [],
                  "test_j2_ledger.py records the figure (sm10_append_p95_ms); run with --ledger to read it here; it gates nothing",
                  status="pending")
    return _m("SM-10", "Ledger append time", "p95 5 ms or less at 10,000 events", p95, p95 <= 5.0, [],
              "recorded by test_j2_ledger.py; it gates nothing%s" % ("" if p95 <= 5.0 else " (over the target)"), status="recorded")


# ---- running the suite -----------------------------------------------------------------------------------------------
def _slug(node):
    return re.sub(r"[^A-Za-z0-9]+", "-", node).strip("-")


def parse_junit(path):
    """{tests, failed, skipped, props}: the testcases of one junit file, and the properties tests recorded."""
    out = {"tests": 0, "failed": 0, "skipped": 0, "props": {}}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return out
    for case in root.iter("testcase"):
        if case.find("skipped") is not None:
            out["skipped"] += 1
            continue
        out["tests"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            out["failed"] += 1
        for prop in case.iter("property"):
            out["props"][prop.get("name")] = prop.get("value")
    return out


def run_lane(node, out, mode, timeout=1500):
    """One pytest process for one file (or node id): a records home and a base temp folder of its own, kept; its junit
    file; and the dump the plugin writes. Returns the lane's row."""
    lane = _slug(node)
    d = Path(out) / lane
    (d / "home").mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    env.update(SUTRA_NATIVE_HOME=str(d / "home"), J2_METRICS_DUMP=str(d / "dump.json"), J2_METRICS_MODE=mode,
               J2_METRICS_LANE=node, PYTHONPATH=os.pathsep.join(filter(None, [str(HERE), os.environ.get("PYTHONPATH")])))
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "j2_metrics", "--basetemp", str(d / "bt"),
           "--junitxml", str(d / "junit.xml"), node]
    t0, note = time.time(), None
    try:
        proc = subprocess.run(cmd, cwd=str(UI), env=env, capture_output=True, text=True, timeout=timeout)
        rc, tail = proc.returncode, (proc.stdout.strip().splitlines() or [""])[-1]
    except subprocess.TimeoutExpired:
        rc, tail, note = -1, "", "timed out after %d s" % timeout
    got = parse_junit(d / "junit.xml")
    dump = _doc(d / "dump.json", {})
    return {"lane": node, "rc": rc, "tests": got["tests"], "failed": got["failed"], "skipped": got["skipped"],
            "seconds": round(time.time() - t0, 1), "summary": note or tail, "props": got["props"],
            "refused_entries": int(dump.get("entries") or 0), "refused_rows": dump.get("rows") or [],
            "mode": dump.get("mode")}


def run_suite(files, out, mode="refuse", workers=4):
    """The scenario suite, one pytest process for each file (their fixtures reload modules), up to `workers` at once."""
    with futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda f: run_lane(f, out, mode), files))


# ---- the plugin: the suite's processes load this module (-p j2_metrics) ---------------------------------------------
def _on():
    return bool(os.environ.get("J2_METRICS_DUMP"))


_STATE = {"entries": 0, "rows": []}


def _schema():
    return sys.modules.get("layer_schema")


@_impl(tryfirst=True)
def pytest_runtest_call(item):
    """Refuse mode for the test (M10.5), after its fixtures have loaded the interface and before its body runs."""
    S = _schema()
    if _on() and S is not None and os.environ.get("J2_METRICS_MODE", "refuse") == "refuse":
        S.MODE = "refuse"


@_impl(tryfirst=True)
def pytest_runtest_setup(item):
    S = _schema()
    item._j2_seen = (S.REFUSED, S.REFUSED["count"], len(S.REFUSED["rows"])) if (_on() and S is not None) else None


@_impl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """What the test added to S.REFUSED and left there (a fault inside S.expect_refused() is taken off on the way out,
    so only a fault nobody expected is counted)."""
    yield
    S = _schema()
    if not _on() or S is None:
        return
    seen = getattr(item, "_j2_seen", None)
    base, start = (seen[1], seen[2]) if seen and seen[0] is S.REFUSED else (0, 0)
    grew = S.REFUSED["count"] - base
    if grew > 0:
        _STATE["entries"] += grew
        _STATE["rows"] += [dict(r, test=item.nodeid) for r in S.REFUSED["rows"][start:]][:20]


def pytest_sessionfinish(session, exitstatus):
    if not _on():
        return
    S = _schema()
    try:
        Path(os.environ["J2_METRICS_DUMP"]).write_text(json.dumps({
            "lane": os.environ.get("J2_METRICS_LANE"), "mode": S.MODE if S is not None else None,
            "entries": _STATE["entries"], "rows": _STATE["rows"][:40]}, indent=1), encoding="utf-8")
    except OSError:
        pass


# ---- the report ------------------------------------------------------------------------------------------------------
def app_mode(ui=UI):
    """The interface's own constant, read from the source (this script imports no app module)."""
    try:
        m = re.search(r"^MODE\s*=\s*['\"](\w+)['\"]", (Path(ui) / "layer_schema.py").read_text(encoding="utf-8"), re.M)
    except OSError:
        m = None
    return m.group(1) if m else "unknown"


def build(depts, lanes=(), mode=None, ui=UI, basis="the scenario suite with stubbed models (C2)"):
    """The report: every metric, what stays pending, and whether the gate's line passes."""
    mode = mode or app_mode(ui)
    suites = Path(ui) / "qa" / "walks" / "suites.sh"
    try:
        text = suites.read_text(encoding="utf-8")
    except OSError:
        text = None
    p95 = next((float(ln["props"]["sm10_append_p95_ms"]) for ln in lanes if "sm10_append_p95_ms" in ln.get("props", {})), None)
    ms = [sm1(depts), sm2(list(lanes), text), sm3(depts), sm4(depts), sm5(), sm6(depts), sm7(depts), sm8(depts), sm9(depts),
          sm10(p95), sm11(depts), sm12(ui), sm13(depts, lanes, mode), sm14(ui)]
    lane_faults = ["lane %s: %s" % (ln["lane"], ln["summary"] or "exit %s" % ln["rc"]) for ln in lanes if ln["rc"] != 0]
    hard = [m["id"] for m in ms if m["id"] in HARD and m["status"] == "gap"]
    return {"schema": SCHEMA, "basis": basis, "departments": len(depts), "mode": {"run": mode, "app": app_mode(ui)},
            "lanes": [{k: v for k, v in ln.items() if k not in ("refused_rows", "props")} for ln in lanes],
            "metrics": ms, "pending": [{"what": a, "why": b} for a, b in PENDING], "lane_faults": lane_faults,
            "hard_gaps": hard, "gaps": [m["id"] for m in ms if m["status"] == "gap"],
            "ok": not hard and not lane_faults}


def render(rep, width=8):
    """The report as text: one line a metric, its gaps under it, the pending list, and a last line the gate shows."""
    out = ["The proof run: %s; %d departments read; interface mode %s (the app's constant: %s)" % (
        rep["basis"], rep["departments"], rep["mode"]["run"], rep["mode"]["app"]), ""]
    for ln in rep["lanes"]:
        out.append("  lane %-44s %4d tests, %d failed, %s s%s" % (ln["lane"], ln["tests"], ln["failed"], ln["seconds"],
                                                              "" if ln["rc"] == 0 else "  (exit %s)" % ln["rc"]))
    out.append("")
    for m in rep["metrics"]:
        v = m["value"] if not isinstance(m["value"], dict) else ", ".join("%s %s" % (k, x) for k, x in m["value"].items())
        out.append("%-5s %-8s %s: %s%s  [target %s]" % (m["id"], m["status"], m["name"], "-" if v is None else v,
                                                         " (%s)" % m["read"] if m.get("read") else "", m["target"]))
        out += textwrap.wrap(m["note"], 120, initial_indent="        how: ", subsequent_indent="             ") if m["note"] else []
        shown = m["gaps"][:width] if m["id"] in LONG_LISTS else m["gaps"]
        for g in shown:
            out.append("        gap: %s" % g)
        if len(shown) < len(m["gaps"]):
            out.append("        and %d more (the report file, --out, names every one)" % (len(m["gaps"]) - len(shown)))
        for c in m.get("carried") or []:
            out += textwrap.wrap(c, 120, initial_indent="        carried to W3-PROOF: ", subsequent_indent=" " * 29)
        for w in (m.get("waiting") or [])[:width]:
            out.append("        waits: %s" % w)
    out += ["", "Pending under C2 (live runs spend the owner's subscription):"] + ["  %s: %s" % (p["what"], p["why"]) for p in rep["pending"]]
    for f in rep["lane_faults"]:
        out.append("FAILED %s" % f)
    pick = {m["id"]: m for m in rep["metrics"]}
    named = [i for i in rep["gaps"] if i not in rep["hard_gaps"]]
    out.append("proof run: %s; %s" % (", ".join("%s %s" % (i, pick[i]["value"]) for i in ("SM-1", "SM-3", "SM-4", "SM-6", "SM-13")),
                                       ("ok" + ("; gaps named, not the gate's: " + ", ".join(named) if named else "")) if rep["ok"]
                                       else "NOT OK: " + ", ".join(rep["hard_gaps"] + rep["lane_faults"][:1])))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 on a gap in SM-1, SM-2, SM-3, SM-4 or SM-13, or a lane that failed")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any gap")
    ap.add_argument("--records", action="append", help="read this records home or kept tree, and run nothing")
    ap.add_argument("--keep", help="keep the suite's records in this folder (default: a temporary one, removed after)")
    ap.add_argument("--files", help="comma-separated scenario files or node ids, in place of the default suite")
    ap.add_argument("--full", action="store_true", help="add the layers' own files (some build records by hand: a gap there may be a fixture's)")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--mode", choices=("refuse", "app"), default="refuse", help="the interface's mode for the suite: refuse, or the app's constant")
    ap.add_argument("--ledger", action="store_true", help="also run the ledger benchmark and read SM-10")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="write the report (JSON) here")
    a = ap.parse_args(argv)
    tmp = None
    try:
        if a.records:
            lanes, mode, basis = [], "as the records were written", "the records at " + ", ".join(a.records)
            depts = [d for r in a.records for d in find_departments(r)]
        else:
            files = a.files.split(",") if a.files else list(SCENARIOS) + (list(FULL) if a.full else [])
            if a.ledger:
                files.append("test_j2_ledger.py::test_ten_thousand_appends_each_grow_the_journal_by_one_line_and_p95_is_recorded")
            tmp = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="sutra-metrics-"))
            tmp.mkdir(parents=True, exist_ok=True)
            lanes = run_suite(files, tmp, a.mode, a.workers)
            mode, basis = ("refuse" if a.mode == "refuse" else app_mode()), "the scenario suite with stubbed models (C2)"
            depts = find_departments(tmp)
        rep = build(depts, lanes, mode, basis=basis)
        if a.keep:
            rep["kept"] = str(tmp)
    finally:
        if tmp is not None and not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str) if a.json else render(rep))
    if a.strict:
        return 0 if rep["ok"] and not rep["gaps"] else 1
    return (0 if rep["ok"] else 1) if a.check else 0


if __name__ == "__main__":
    sys.exit(main())
