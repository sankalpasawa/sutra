"""functions_view.py -- the department's five functions, as one read of the record (PRD M1.1, M1.2, M1.7).

The Map, the list column, each function's pane and the All five overview read the five functions here, and only here,
so they agree with each other and with the record in every state of the J2 cycle. This module is a projection and
nothing more: it reads the department's own record (dept.json, runs.json, asks.json, board.jsonl, exchanges.json,
steps.jsonl, ladder.json, the J2 cycle and its ledger) and the definitions, and it writes nothing and never calls the
model. The state rules are the J2 prototype's map/1 function node (j2_map._functions), ported onto Sutra's records:

    who holds the turn     the cycle's state says it: assessing, waiting, closing and blocked are Identity's; adapting
                           and reshaping are Adaptation's; bargaining is Priority's; running is Coordination's and the
                           running engine's; checking is Root's, and Adaptation waits on it
    waiting                the src of an open thread that wrote its latest post waits on the thread's decider (dst[0])
    waits on you           Identity, the one that asks: a pending ask, the cycle's open question, or a blocked cycle
    fault                  a failed step check, or a start that should have fired and did not (Audit with no run after
                           the version it starts on; Coordination idle while two engines are ready)
    quiet                  anything else; a department that is stopped or done is quiet throughout, never working, and a
                           stopped one's word is 'stopped' on every function

There is no 'asleep' state: the order the five wake in is not ruled (PRD Q9), so only states the record has are shown.
What the record does not hold is named in not_recorded and never guessed (the prototype's "not recorded" list).
"""
import re
import time
from datetime import datetime

import engine_runtime as R
import j2_runtime as J
import owner_words
import website_dept as W

FUNCS = tuple(R.FUNCTIONS)                      # Identity, Adaptation, Priority, Coordination, Audit: the canonical order
STATES = ("working", "waiting", "waiting_on_you", "fault", "quiet")
WORDS = {"working": "working", "waiting": "waiting", "waiting_on_you": "waits on you", "fault": "fault", "quiet": "quiet"}
OPEN = ("submitted", "working")                 # a thread between functions that still waits on its decider
FIRE_GRACE_S = 300                              # how long a start may lag its trigger before it is a fault: the motor ticks every 3 s
PATHLIKE = re.compile(r"(?:~|\b[A-Za-z]:)?(?:/[\w.@-]+){2,}/?")

# The cycle's state, read as who holds the turn and what that function is doing. checking is Root's (step 5): Root is
# not one of the five, so Adaptation waits on it.
TURN = {"assessing": ("Identity", "reading your words"), "closing": ("Identity", "settling a disagreement"),
        "adapting": ("Adaptation", "proposing the work"), "reshaping": ("Adaptation", "reshaping the plan"),
        "bargaining": ("Priority", "pricing the plan")}
# What the cycle says, in the owner's words (PRD S4); running names the engine instead
SAYS = {"not_started": "Not started", "not_ready": "Not started", "assessing": "Reading your words",
        "waiting": "Waiting for your answer", "adapting": "Proposing the work", "bargaining": "Pricing the plan",
        "closing": "Settling a disagreement", "checking": "Root is reviewing the plan", "reshaping": "Reshaping the plan",
        "running": "The work is running", "unread": "Audit has not read the result", "pursuing": "Working on what Audit found",
        "blocked": "Stuck: needs your words", "stopped": "Stopped by you", "done": "Goal reached"}
STEPS = ((1, "Enough to work"), (2, "Propose"), (3, "Price"), (4, "Settle"), (5, "Root's review"), (6, "Run"), (7, "Read"),
         (8, "Next or done"))
# an act on the board, in the words a person reads (the owner's words: said yes, asked for less, said no)
ACT_WORDS = {"request": "asks", "agree": "agrees with", "refuse": "says no to", "propose": "proposes to",
             "accept-proposal": "says yes to", "reject-proposal": "says no to", "inform": "tells", "failure": "says it could not to",
             "cancel": "lets go of", "not-understood": "did not follow"}
RUNG_BY = {"C2": "code", "C1": "AI", "C0": "AI", "P": "person"}


# ---- the site's function pages: what each function is, as its page says it ------------------------------------------
# The one line, what it holds, who it hands to, its version 1 scope and its journeys come from the department's site
# page for each function (PRD section 6). A journey names the ledger actions and the record rows that are its moves, so
# its live status is read from the record, never written here. built: built, partly built, not built yet, or later.
PAGES = {
    "Identity": {
        "vsm": "VSM S5: identity and policy",
        "line": "The department's voice and conscience. It hears you, checks that the identity is good enough, gates every "
                "effect by rule, closes conflicts, and says when the goal is reached.",
        "holds": "Goal, done-when, rules (go, ask, refuse, always), budget, owner and parent, and each engine's window.",
        "hands_to": "Adaptation: a request for a line, and the next thing to correct. Coordination: verdicts on gates. "
                    "You: it is the only function that speaks to you.",
        "keeps": "Never makes anything; the maker is an engine. Asks only when a rule says ask. Approvals only tighten. "
                 "Never invents a goal or a rule, and asks one question at a time.",
        "v1": "Your words become the Brief, one question when the words are thin, the ask before the first publish, and a tell.",
        "journeys": [("FI1", "Enough to work?", "built", ("identity.assessed", "identity.questioned"), "answered"),
                     ("FI2", "Words after go-live", "built", (), "owner_words"),
                     ("FI3", "The gates", "built", (), "identity_gates"),
                     ("FI4", "Closes a conflict", "built", ("conflict.raised", "identity.ruled"), None)],
    },
    "Adaptation": {
        "vsm": "VSM S4: outside and future",
        "line": "Decides how the department gets there. It proposes the workflows the goal needs, from the Library, fitted, "
                "or made fresh, and after each reading it proposes the next round, until the goal holds.",
        "holds": "Its proposals on the board, the ideas it parked, the ladder of every step, and its rounds.",
        "hands_to": "Priority: every proposal and every round. Identity: conflicts, and a round Priority said yes to, to file. "
                    "Root: the line Priority said yes to, for its check.",
        "keeps": "Senses and proposes; never applies. Every proposal passes Priority first. May leave out an engine its "
                 "template does not mark required. Engines come from Adaptation, never from Root.",
        "v1": "Two to five workflows from the Library or shaped for the goal; no loop and no Make module yet.",
        "journeys": [("FA1", "The first workflows", "partly built",
                      ("proposal.requested", "proposal.created", "workflow.validated", "workflow.registered", "workflow.blocked"), None),
                     ("FA2", "Pursue until done", "not built yet", (), None),
                     ("FA3", "Crystallize a step", "built", (), "ladder_moves"),
                     ("FA4", "Grow out", "later", (), None),
                     ("FA5", "Learn", "later", (), None)],
    },
    "Priority": {
        "vsm": "VSM S3: inside and now",
        "line": "Prices every proposal against the room actually left and holds the budget. It says yes, asks for less, or "
                "says no. Who goes first is never its call.",
        "holds": "One limit per engine (calls and money a day) and the bargain threads.",
        "hands_to": "Adaptation: said yes, asked for less, or said no. Identity: through Adaptation's conflict, when a limit is hit.",
        "keeps": "Prices and holds the budget; who goes first is Coordination's call. Never starts a run and never says no "
                 "over method. Never changes the goal or speaks to you.",
        "v1": "The limit on every start, as built. Nothing else.",
        "journeys": [("FP1", "The limit on every start", "built", ("envelope.held",), "priority_gates"),
                     ("FP2", "The bargain with Adaptation", "partly built",
                      ("proposal.granted", "proposal.countered", "proposal.refused"), None)],
    },
    "Coordination": {
        "vsm": "VSM S2: timetables and standards",
        "line": "Keeps the timetable: a slot for each engine, who goes first, one run at a time, hand-offs, a chain that "
                "stops at its limit, and an alarm past a window. It judges nothing about content.",
        "holds": "Its table: the order, the line and who may post to whom; the run rows and each thread's bounds.",
        "hands_to": "Identity: alarms, lost requests and verdict asks. Priority: verdict asks.",
        "keeps": "No model call inside a tick; a missed slot runs once, and each slot runs once. The engine starts itself in "
                 "its slot. Never changes limits, scope or quality calls.",
        "v1": "As built.",
        "journeys": [("FC1", "Who goes first", "built", ("slot.assigned",), "coord_picks"),
                     ("FC2", "A lost request", "built", (), "lost")],
    },
    "Audit": {
        "vsm": "VSM S3*: sporadic direct inspection",
        "line": "The second pair of eyes. It reads what the department actually filed, item by item against done-when, "
                "with code checks first, and it also drops in unannounced. Its findings go to Identity.",
        "holds": "Its readings and its findings.",
        "hands_to": "Identity only: readings and findings.",
        "keeps": "The checker is never the writer; it never touches a workflow or a version. A check is a check, never a "
                 "score. It reads what the department did, never only its goal.",
        "v1": "As built: read the live site against the words.",
        "journeys": [("FAU1", "Read the result", "partly built", ("audit.finding_filed",), "audit_runs")],
    },
}
NOT_RUN = {"built": "not run yet", "partly built": "not run yet", "not built yet": "not built yet", "later": "later"}
# a ledger row's state, as the word a journey row carries
LIVE = {"complete": "done", "filed": "done", "recorded": "done", "done": "done", "granted": "said yes", "assigned": "running",
        "running": "running", "waiting": "waiting", "pending": "waiting", "held": "held", "refused": "said no",
        "failed": "failed", "run": "done", "drop": "dropped", "ask": "waiting", "stopped": "stopped"}


# ---- small readers -------------------------------------------------------------------------------------------------
def _clean(value):
    """No private key and no path ever leaves this read: a key in the ledger's private set is dropped, and a string
    that names a file on this machine keeps the file's name only (names, never paths)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if str(k).lower() not in J.PRIVATE_KEYS}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, str):
        return PATHLIKE.sub(lambda m: m.group(0).rstrip("/").rsplit("/", 1)[-1], value)
    return value


def _cap(s):
    s = str(s or "").strip()
    return s[:1].upper() + s[1:]


def _short(s, n=140):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _cycle_state(ref):
    """The J2 cycle as its own record says it, or the state of a department with no cycle (born before J2, or J2 off)."""
    try:
        return J.status(ref)
    except Exception:  # noqa: BLE001 -- the read never fails the screen
        return {"state": "not_started", "step": None, "cycle_id": None, "open_ask": None}


def _events(ref, cycle_id=None):
    try:
        rows = J.events(ref)
    except Exception:  # noqa: BLE001
        rows = []
    return [e for e in rows if cycle_id is None or e.get("cycle_id") == cycle_id]


def _rows(ref):
    try:
        return R.step_rows(ref)
    except Exception:  # noqa: BLE001
        return []


def _spend(ref, d, name):
    """Today's spend against the limit, as shares for a bar; the numbers stay in the read for a title, never at rest."""
    calls, usd = W._today_spend(ref, name)
    env = (d.get("envelopes") or {}).get(name) or W.ENVELOPE
    cap_c, cap_u = int(env.get("calls") or 0), float(env.get("usd") or 0.0)
    share = max(calls / cap_c if cap_c else 0.0, usd / cap_u if cap_u else 0.0)
    return {"calls": calls, "usd": round(usd, 3), "calls_limit": cap_c, "usd_limit": cap_u, "share": round(min(1.0, share), 3)}


def _ready_now(ref, d):
    """The engines and functions ready by their own start right now, asked the way a panel read asks (peek): no row,
    no ask and no model call is made. Empty on any error, so the read never fails on Coordination's internals."""
    try:
        ctx = R._coord_ctx(ref, d)
        ctx["peek"] = True
        out = []
        for name in list(ctx["table"].get("line") or []) + list(ctx["table"].get("functions") or []):
            got = R.ready(ctx, name, ("version", "timer"))
            if got and got[1]:
                out.append(name)
        return out
    except Exception:  # noqa: BLE001
        return []


def slot_clashes(rs):
    """SM-11's clash in a slot, read off the run rows (PRD M4.3): two runs that finished on one slot id, or a start while
    another run of the department was open. [{slot, why}]; empty when the timetable held. A run row with no slot is a
    function's note of what it did, never a start."""
    out, ended = [], {}
    starts = [r for r in rs if r.get("slot")]
    for r in starts:
        if r.get("status") in ("ok", "failed"):
            if r["slot"] in ended:
                out.append({"slot": r["slot"], "why": "the slot ran twice"})
            ended[r["slot"]] = r
    spans = sorted(((W._ts(r.get("started") or ""), W._ts(r.get("ended") or "") if r.get("ended") else float("inf"), r)
                    for r in starts), key=lambda x: x[0])
    for i, (a0, a1, a) in enumerate(spans):
        for b0, _, b in spans[i + 1:]:
            if b0 >= a1:
                break
            if b0 > a0:
                out.append({"slot": b["slot"], "why": "it started while %s was running" % a.get("engine")})
    return out


# ---- M1.2: who spoke to whom, who made what and who reads it -------------------------------------------------------
def speaks(ref, posts=None):
    """Every pair that spoke on the board, src > dst, the owner and Root included: how often, and when last."""
    pairs = {}
    for p in (R.board(ref) if posts is None else posts):
        for dst in p.get("dst") or []:
            k = (p.get("src"), dst)
            row = pairs.setdefault(k, {"from": p.get("src"), "to": dst, "n": 0, "at": None})
            row["n"] += 1
            row["at"] = p.get("at") or row["at"]
    return sorted(pairs.values(), key=lambda r: (-r["n"], str(r["from"]), str(r["to"])))


def made(ref, d, nr):
    """Every artifact the department files: who made each version (runs.json wrote, or the owner's own words), and who
    reads it (each engine's reads in the definitions and the born templates). A version whose maker is not on the
    record goes to not_recorded."""
    rs = {r["id"]: r for r in W.runs(ref) if r.get("id")}
    defs = R.defs()["engines"]
    line = [e[0] for e in W.engines_of(d)]
    readers_of = {}
    for name in line + list(FUNCS):
        reads = (defs.get(name) or {}).get("reads")
        if reads:
            readers_of.setdefault(reads, []).append(name)
    by_run = {}
    for r in rs.values():
        wrote = r.get("wrote") or {}
        if wrote.get("art"):
            by_run[(wrote["art"], int(wrote.get("v") or 0))] = r["engine"]
    out = []
    for art in W.artifacts_of(d):
        vs = W.versions(ref, art)
        by_v, lost = {}, []
        for v in vs[-20:]:
            if v.get("run") == "owner":
                by_v[str(v["v"])] = "Owner"
            elif v.get("run") in rs:
                by_v[str(v["v"])] = rs[v["run"]]["engine"]
            elif (art, int(v["v"])) in by_run:
                by_v[str(v["v"])] = by_run[(art, int(v["v"]))]
            else:
                lost.append(v["v"])
        if lost:
            nr.append("who made %s v%s" % (art, lost[-1]))
        latest = vs[-1] if vs else None
        makers = []
        for m in by_v.values():
            if m not in makers:
                makers.append(m)
        out.append({"art": art, "slug": W.slug(art), "v": latest["v"] if latest else None,
                    "by": by_v.get(str(latest["v"])) if latest else None, "makers": makers, "by_v": by_v,
                    "readers": list(readers_of.get(art) or [])})
    for name in line:
        if name not in defs:
            nr.append("what %s reads and writes: it has no template in this app's Library" % name)
    return out


# ---- M1.1: the five, and the cycle --------------------------------------------------------------------------------
def _waits_from_threads(ref, board_rows=None):
    """The thread rule: the src of an open thread that wrote its latest post waits on the decider (dst[0]); between the
    five only, since a wait on the owner is read from the asks."""
    posts = {}
    for p in (R.board(ref) if board_rows is None else board_rows):
        posts.setdefault(p.get("thread"), []).append(p)
    out = {}
    for th in R.threads(ref):
        if th.get("state") not in OPEN:
            continue
        mine = posts.get(th["id"]) or []
        if not mine:
            continue
        last = mine[-1]
        src, dst = last.get("src"), list(last.get("dst") or [])
        if src in FUNCS and dst and dst[0] in FUNCS and dst[0] != src:
            out.setdefault(src, {"on": dst[0], "at": last.get("at"), "topic": th.get("topic")})
    return out


def _faults(ref, d, rs, rows, now_s):
    """A failed step check, or a start that should have fired: {function: why}."""
    out = {}
    for fn in FUNCS:
        mine = [r for r in rows if r.get("engine") == fn]
        if mine and mine[-1].get("status") == "failed":
            out[fn] = _short(_plain(mine[-1].get("why")) or "a step of %s failed its check" % fn)
            continue
        runs_fn = [r for r in rs if r.get("engine") == fn and r.get("status") != "running"]
        if runs_fn and runs_fn[-1].get("status") == "failed":
            out[fn] = _short(_plain(runs_fn[-1].get("what")) or "%s's last run failed" % fn)
    if d.get("stopped") or any(r.get("status") == "running" for r in rs):
        return out
    # should have fired: Audit by its own start (a checked version of what it reads), past the grace window
    audit = R.engine_def("Audit") or {}
    for trig in ((audit.get("start") or {}).get("on") or []):
        if trig.get("kind") != "version" or trig.get("of") not in W.artifacts_of(d):
            continue
        v = W.latest(ref, trig["of"], passed=bool(trig.get("checked")))
        if not v or now_s - W._ts(v.get("at") or "") < FIRE_GRACE_S:
            continue
        slot = W._slot_id("Audit", trig["of"], v["v"])
        if not any(r.get("slot") == slot for r in rs):
            out.setdefault("Audit", "Audit has not read %s v%s" % (trig["of"], v["v"]))
    # should have fired: Coordination idle while two engines are ready, past the grace window
    last = max((W._ts(r.get("started") or "") for r in rs), default=0.0)
    if now_s - last >= FIRE_GRACE_S:
        ready = _ready_now(ref, d)
        if len(ready) >= 2:
            out.setdefault("Coordination", "%s are ready and nothing has started" % " and ".join(ready[:2]))
    return out


# What a post was about, by its topic word, as the last act names it
ABOUT = {"line": "the plan", "plan": "the plan", "verdict": "a verdict", "conflict": "a disagreement", "alarm": "an alarm",
         "rung": "a step's rung", "idea": "where an idea went", "lost": "a lost request", "engine": "an engine",
         "publish": "going live", "rule": "a rule", "answer": "an answer"}


def _did(p):
    """A post as the act its function did, in the owner's words: the act and to whom (Priority's answers are said yes,
    asked for less and said no). What the post carried is never the act: the owner's words that Identity hands on, or
    that Adaptation proposes from, are the owner's, not the function's."""
    act, word = p.get("msg_type"), (p.get("payload") or {}).get("word")
    to = ", ".join("you" if x == R.OWNER else x for x in p.get("dst") or []) or "the board"
    about = ABOUT.get(word)
    if act == "propose":
        return "asked %s for less" % to if p.get("src") == "Priority" else "proposed %s to %s" % (about or "a change", to)
    if act in ("accept-proposal", "reject-proposal"):
        return ("said yes to %s" if act == "accept-proposal" else "said no to %s") % (about or to)
    if act == "request":
        return "asked %s for the plan" % to if word == "line" else "asked %s%s" % (to, " about " + about if about else "")
    if act == "inform":
        if word == "finding":
            return "told %s what it found" % to
        if word == "request":
            return "answered %s" % to
        return "told %s%s" % (to, " about " + about if about else "")
    return {"agree": "agreed with %s", "refuse": "said no to %s", "failure": "told %s it could not", "cancel": "let %s go",
            "not-understood": "did not follow %s"}.get(act, "posted to %s") % to


def _last_act(fn, rs, posts):
    """What the function did last: its last finished run, as the run says it, or a post of its own when that came later;
    the act is 'what', and what it acted on (the plan's names, the owner's words, a run's own detail) is 'detail'."""
    run = next((r for r in reversed(rs) if r.get("engine") == fn and r.get("status") != "running" and r.get("what")), None)
    post = next((p for p in reversed(posts) if p.get("src") == fn), None)
    best = None
    if run:
        what, _, detail = _plain(run.get("what")).partition(": ")
        best = {"what": _short(what), "detail": _short(detail) or None, "at": run.get("ended") or run.get("started")}
    # a post inside a run is stamped before the run ends: on the same second the run, which says the act, is the one
    if post and (not best or W._ts(post.get("at") or "") > W._ts(best["at"] or "")):
        best = {"what": _did(post), "detail": _short(_plain(R._line(post))) or None, "at": post.get("at")}
    return best


BETWEEN = 3                                      # All five's Between them: the last three messages between the five (S2)


def _between(posts):
    """The last messages between the five, newest first, each as the act its function did, in the owner's words (the
    last act's own rule, _did): 'proposed the plan to Priority', 'said yes to the plan'. What a post carried (the owner's
    goal that Identity hands on, Priority's why) is its detail, for the hover, never the act."""
    out = []
    for p in reversed(posts):
        to = [x for x in p.get("dst") or [] if x in FUNCS and x != p.get("src")]
        if p.get("src") not in FUNCS or not to:
            continue
        out.append({"n": p.get("n"), "thread": p.get("thread"), "from": p.get("src"), "to": to, "act": _did(p),
                    "detail": _short(_plain(R._line(p))) or None, "at": p.get("at")})
        if len(out) == BETWEEN:
            break
    return out


def _steps(cur, events, state):
    """The eight step pills: done, now, next, or skipped (Settle, when no conflict was raised)."""
    step = int(cur.get("step") or 0)
    conflict = any(e.get("action") == "conflict.raised" for e in events)
    out = []
    for n, name in STEPS:
        last = next((e for e in reversed(events) if e.get("step") == n), None)
        if state == "done":
            word = "skipped" if n == 4 and not conflict else "done"
        elif not step:
            word = "next"
        elif n < step:
            word = "skipped" if n == 4 and not conflict else "done"
        elif n == step:
            word = "now"
        else:
            word = "next"
        out.append({"step": n, "name": name, "state": word,
                    "last": last and {"summary": _short(_plain(last.get("summary"))), "at": last.get("occurred_at")}})
    return out


def functions(ref):
    """The five function nodes, the cycle and what the record does not hold, for a department on the engine runtime;
    None for every other. Reads only."""
    d = W.dept(ref)
    if not d or d.get("runtime") != 2:
        return None
    now_s = time.time()
    rs, ak, posts, rows = W.runs(ref), W.asks(ref), R.board(ref), _rows(ref)
    cur = _cycle_state(ref)
    state = str(cur.get("state") or "not_started")
    if d.get("stopped") and state not in ("done",):
        state = "stopped"
    # the department is stopped by its switch or by its cycle; a goal reached and then switched off stays done in the
    # cycle's words, but it is stopped all the same, and every surface says so in one word
    stopped = bool(d.get("stopped")) or state == "stopped"
    events = _events(ref, cur.get("cycle_id")) if cur.get("cycle_id") else []
    pending = [a for a in ak if a.get("status") == "pending"]
    running = [r for r in rs if r.get("status") == "running"]
    work_running = [r for r in running if not r.get("system")]
    waits = _waits_from_threads(ref, posts)
    faults = _faults(ref, d, rs, rows, now_s)
    nr = []
    mades = made(ref, d, nr)
    pairs = speaks(ref, posts)
    question = None
    if cur.get("open_ask"):
        question = next((a for a in ak if a.get("id") == cur["open_ask"] and a.get("status") == "pending"), None)
    finding = next((a for a in pending if a.get("kind") == "finding"), None)

    nodes = []
    for fn in FUNCS:
        node = {"id": "fn:" + fn.lower(), "fn": fn.lower(), "name": fn, "state": "quiet", "word": WORDS["quiet"],
                "waits_on": None, "line": "", "why": None}
        # the turn, by the cycle's state
        if state in TURN and TURN[state][0] == fn:
            node.update(state="working", line=TURN[state][1])
        elif state == "running" and fn == "Coordination" and (work_running or not pending):
            node.update(state="working", line=("%s's turn" % work_running[0]["engine"]) if work_running else "keeping the timetable")
        elif state == "checking" and fn == "Adaptation":
            node.update(state="waiting", waits_on="Root", line="waits on Root's review")
        # a run of the function's own: while it runs, its line is the handler's name, which carries the inside word
        # ('Priority granted the line'), so it is said in the owner's words like every other line of this read
        mine = [r for r in running if r.get("engine") == fn]
        if mine and node["state"] != "working":
            node.update(state="working", line=_short(_plain(mine[0].get("what")) or "working"))
        # the thread rule
        if node["state"] == "quiet" and fn in waits:
            node.update(state="waiting", waits_on=waits[fn]["on"], line="waits on %s" % waits[fn]["on"])
        # Identity asks: a pending ask, the cycle's open question, a blocked cycle; pursuing waits while a finding is asked
        if fn == "Identity":
            ask = question or finding or (pending[0] if pending else None)
            if state == "blocked":                  # Identity closed a conflict by dropping the plan (J.ruled 'drop')
                node.update(state="waiting_on_you", waits_on="you", line="the plan was dropped; it needs your words")
            elif state == "waiting" or ask:
                # the ask's own text is Identity's line, at rest on All five and its pane: a conflict's ask quotes
                # Priority's no and names the owner's buttons, so it is said in the owner's words too
                node.update(state="waiting_on_you", waits_on="you",
                            line=_short(_plain((ask or {}).get("text")) or "waits for your answer"))
        if fn in faults:
            node.update(state="fault", why=faults[fn], line=faults[fn])
        # a department that is stopped, or whose goal is reached, is quiet throughout; a stopped one says so in one word,
        # the word every surface prints (the Map, the list, All five and the pane print node.word and nothing else),
        # whether its cycle stopped or its switch is off after the goal was reached
        if state in ("stopped", "done") or stopped:
            node.update(state="quiet", waits_on=None, line="", why=None)
        node["word"] = "stopped" if stopped else WORDS[node["state"]]
        node["last"] = _last_act(fn, rs, posts)
        node["spend"] = _spend(ref, d, fn)
        node["speaks_to"] = [{"to": p["to"], "n": p["n"]} for p in pairs if p["from"] == fn]
        node["made"] = [m["art"] for m in mades if fn in m["makers"]]
        if not node["last"]:
            nr.append("what %s did" % fn)
        nodes.append(node)

    says = SAYS.get(state, _cap(state.replace("_", " ")))
    if state == "running" and work_running:
        says = "%s is working" % work_running[0]["engine"]
    needs = bool(pending) or state in ("waiting", "blocked")
    cycle = {"state": state, "step": cur.get("step"), "journey": cur.get("journey"), "says": says,
             "steps": _steps(cur, events, state) if cur.get("cycle_id") else [],
             "needs_you": needs and state not in ("stopped", "done"), "asks": len(pending),
             "running": [r["engine"] for r in work_running],
             "ceiling": ((d.get("envelopes") or {}).get("_goal") or None), "round": cur.get("round")}
    return _clean({"ref": ref, "name": d.get("name"), "kind": d.get("kind"), "stopped": stopped,
                   "functions": nodes, "cycle": cycle, "speaks": pairs, "made": mades, "between": _between(posts),
                   "budget": _budget(ref, d), "not_recorded": nr})


def _budget(ref, d):
    """The whole goal's spend against its ceiling, for the Map's Budget bar: today's spend of every engine against the
    sum of their limits until Priority holds a ceiling for the goal (M9.2)."""
    envs = {k: v for k, v in (d.get("envelopes") or {}).items() if not str(k).startswith("_")}
    calls = usd = cap_c = cap_u = 0
    for name, env in envs.items():
        c, u = W._today_spend(ref, name)
        calls, usd = calls + c, usd + u
        cap_c += int((env or {}).get("calls") or 0)
        cap_u += float((env or {}).get("usd") or 0.0)
    goal = (d.get("envelopes") or {}).get("_goal") or {}
    if goal.get("calls"):
        cap_c = int(goal["calls"])
    if goal.get("usd"):
        cap_u = float(goal["usd"])
    share = max(calls / cap_c if cap_c else 0.0, usd / cap_u if cap_u else 0.0)
    return {"calls": calls, "usd": round(usd, 3), "calls_limit": cap_c, "usd_limit": round(cap_u, 3), "share": round(min(1.0, share), 3),
            "of": "the goal" if goal else "today's limits"}


# ---- M1.7: one function, as its site page holds it -----------------------------------------------------------------
def _picked(ref, d, fn):
    try:
        import function_templates as T
        tid = T.picked(ref).get(fn.lower()) or (d.get("templates") or {}).get(fn.lower()) or T.default_id(fn.lower())
        return T.get(tid) or T.get(T.default_id(fn.lower())) or {}
    except Exception:  # noqa: BLE001 -- no registry: the page reads without a template
        return {}


def _writes(ref, fn):
    """What a function writes: the acts it may post, and to whom, from Coordination's table."""
    try:
        edges = (R.coordination(ref).get("edges") or {}).get(fn) or {}
    except Exception:  # noqa: BLE001
        edges = {}
    out = []
    for act, dst in sorted(edges.items()):
        to = ", ".join("you" if x == R.OWNER else x for x in dst)
        if fn == "Priority" and act == "propose":
            out.append("Asks %s for less" % to)          # Priority's counter, in the owner's words
        else:
            out.append("%s %s" % (_cap(ACT_WORDS.get(act, act)), to))
    return out


# The bargain in the owner's words (owner_words.py): the one word table every read a screen prints passes through, this
# read's lines (a node's line, its why, its last act and that act's detail, a journey's last move, a step's name) and the
# older cards' reads in website_api alike. Kept here under its old names for the callers that know them.
BARGAIN_WORDS = owner_words.BARGAIN_WORDS
_plain = owner_words.plain


def _settings(fn):
    names = ["Ladder", "Limit"]
    if fn == "Identity":
        names.append("Served from")
    if fn == "Coordination":
        names += ["Who goes first", "Who may post to whom"]
    return names


def _recipe(ref, fn):
    """The function's steps, in order, each run by code, by the AI inside, or by a person, on the rung it has earned."""
    view = R.steps_view(ref, fn) or {}
    out = []
    for s in view.get("steps") or []:
        out.append({"id": s["id"], "name": _plain(s["name"]), "by": RUNG_BY.get(s["rung"], "AI"), "rung": s["rung"],
                    "rung_name": s["rung_name"], "mode": s["mode"], "under": _plain(s.get("under")) or None, "held": s.get("held"),
                    "last": (s.get("last") or {}).get("status")})
    return out, [_plain(h) for h in view.get("hears") or []]


def _journey_rows(ref, fn, events, rows, rs, posts):
    """Each journey on the function's page, with its live status: its last move on the ledger or the record."""
    gates = {g["id"]: g["name"] for g in ((R.engine_def(fn) or {}).get("gates") or [])}
    out = []
    for jid, name, built, actions, extra in PAGES[fn]["journeys"]:
        hits = []
        for e in events:
            if e.get("action") in actions:
                # Root's check that did not hold sent the plan back; every other refusal is a 'said no'
                back = e["action"] == "workflow.blocked" and e.get("state") == "refused"
                hits.append({"action": e["action"], "summary": e.get("summary"), "at": e.get("occurred_at"),
                             "word": "sent back" if back else LIVE.get(str(e.get("state")), str(e.get("state") or ""))})
            elif extra == "answered" and e.get("action") == "ask.answered" and e.get("step") == 1:
                hits.append({"action": e["action"], "summary": e.get("summary"), "at": e.get("occurred_at"), "word": "done"})
        if extra == "owner_words":
            for p in posts:
                if p.get("src") == R.OWNER and "Identity" in (p.get("dst") or []) and p.get("msg_type") == "request":
                    hits.append({"action": "board.request", "summary": R._line(p) or "your words reached Identity", "at": p.get("at"),
                                 "word": "heard"})
        elif extra in ("identity_gates", "priority_gates"):
            for r in rows:
                if r.get("mode") == "gate" and r.get("step") in gates:
                    word = {"admit": "let through", "wait": "waiting", "refuse": "stopped"}.get(str(r.get("answer")), "decided")
                    hits.append({"action": "gate", "summary": "%s: %s" % (gates[r["step"]], word), "at": r.get("ended"), "word": word})
        elif extra == "ladder_moves":
            for s in (R.ladder(ref) or {}).values():
                for h in s.get("history") or []:
                    if h.get("from"):
                        step = (R.step_def(s.get("step") or "")[1] or {}).get("name") or "a step"
                        hits.append({"action": "rung.moved", "summary": "%s: %s to %s" % (step, R.RUNG_NAME.get(h["from"], h["from"]),
                                                                                         R.RUNG_NAME.get(h["to"], h["to"])),
                                     "at": h.get("at"), "word": "moved"})
        elif extra == "coord_picks" and not hits:
            for r in rows:
                if r.get("step") == "coord.pick" and r.get("answer"):
                    hits.append({"action": "coord.pick", "summary": "%s had the next turn" % r["answer"], "at": r.get("ended"), "word": "done"})
        elif extra == "lost":
            for p in posts:
                if p.get("src") == "Coordination" and (p.get("payload") or {}).get("word") == "lost":
                    hits.append({"action": "board.lost", "summary": R._line(p) or "a request was lost at its bound", "at": p.get("at"),
                                 "word": "told Identity"})
        elif extra == "audit_runs" and not hits:
            for r in rs:
                if r.get("engine") == "Audit" and r.get("status") != "running":
                    hits.append({"action": "run", "summary": r.get("what"), "at": r.get("ended") or r.get("started"),
                                 "word": "done" if r.get("status") == "ok" else str(r.get("status"))})
        hits.sort(key=lambda h: W._ts(h.get("at") or ""))
        last = hits[-1] if hits else None
        out.append({"id": jid, "name": name, "built": built,
                    "status": last["word"] if last else NOT_RUN.get(built, "not run yet"),
                    "last": last and {"summary": _short(_plain(last.get("summary"))), "at": last.get("at"), "action": last.get("action")}})
    return out


# Identity's pane (PRD M3.7, screen S5): who the department is, from its one record. Enough to work? is one row per
# point of the marked standard (MK-1), read off the record by code (R._standard_gaps) and off Identity's open question
# on it; done-when as items with level, how and a to-confirm note; each rule with where it came from; the open question
# (S6); and the conflicts Identity closed, each with who split, the ruling and why.
RULING_SAYS = {"run": "it runs", "drop": "dropped", "ask": "asked you"}
SPLIT_BY = {"Adaptation": "Adaptation and Priority did not agree", "Coordination": "the bargain reached its bound"}


def _standard_rows(ref, d, cur, q):
    gaps, asked = set(R._standard_gaps(d)), set((q or {}).get("points") or []) if (q or {}).get("standard") else set()
    confirm = [c for c in d.get("to_be_confirmed") or [] if isinstance(c, dict) and c.get("item")]
    reading = cur.get("state") == "assessing" and int(cur.get("step") or 0) == 1
    rows = []
    for pid, says, points in R.STANDARD_POINTS:
        lacks = [p for p in points if p in gaps]
        if lacks:
            state, note = "not_met", "the record has " + ", ".join(R.STANDARD_SAYS[p] for p in lacks)
        elif asked & set(points):
            state, note = "not_met", "Identity asks you"
        elif pid == "invented" and confirm:
            state, note = "to_confirm", "to confirm with you: " + "; ".join("%s, %s" % (c["item"], c.get("why") or "not given") for c in confirm)
        elif reading:
            state, note = "reading", "being read"
        else:
            # the screen never says refuse: a refuse rule reads never on the pane (22-website.js WB_TAG_SAYS), so the note
            # names the tags the owner reads (found by a verifier 2026-10-23: the met note said refuse)
            state, note = "met", {"goal": "as you said it", "items": "each says how it is checked", "rules": "each says go, ask, never or always",
                                  "owner_budget": "you, and Priority's limits", "invented": "nothing stated that nobody gave"}[pid]
        rows.append({"id": pid, "says": says, "state": state, "note": note})
    return rows


def _identity_part(ref, d, events):
    cur = _cycle_state(ref)
    q = J.open_question(ref)
    why = {c.get("item"): c.get("why") for c in d.get("to_be_confirmed") or [] if isinstance(c, dict)}
    items = [{"id": i.get("id"), "text": i.get("text"), "how": i.get("how"), "level": i.get("level"), "confirm": why.get(i.get("id"))}
             for i in d.get("done_items") or [] if isinstance(i, dict) and i.get("id")]
    rules = [{"tag": r.get("tag"), "line": r.get("line"), "by": "yours" if (r.get("from") or str(r.get("id") or "").startswith("u-")) else "the template",
              "since": r.get("since")} for r in d.get("rules") or [] if isinstance(r, dict) and str(r.get("line") or "").strip()]
    conflicts, raised = [], None
    for e in events:
        if e.get("action") == "conflict.raised":
            raised = e
        elif e.get("action") == "identity.ruled":
            ruling = str(e.get("state") or (e.get("payload") or {}).get("ruling") or "")
            names = (e.get("payload") or {}).get("workflow") or []
            conflicts.append({"at": e.get("occurred_at"), "who": SPLIT_BY.get((raised or {}).get("actor"), "the plan was not settled"),
                              "split": _plain((raised or {}).get("summary")) or None, "plan": " -> ".join(names) or None,
                              "ruling": ruling, "ruled": RULING_SAYS.get(ruling, ruling), "why": _plain(e.get("summary")) or None,
                              "asked_you": ruling == "ask"})
            raised = None
    gaps = R._standard_gaps(d)
    return {"standard": {"met": not gaps and not (q or {}).get("standard"), "missing": gaps, "rows": _standard_rows(ref, d, cur, q)},
            "goal": d.get("goal"), "done": d.get("done"), "done_items": items, "rules": rules,
            "open_question": q and {k: q.get(k) for k in ("id", "text", "why", "missing", "asked", "standard", "points")},
            "conflicts": conflicts[-6:]}


# ---- M4.5: Coordination, from the record: its timetable, why anything waits, who makes and who reads, its ties ------
#: what Coordination's pane reads (PRD M4.5, screen S7), its shape named once: the line and the plan it follows; the
#: timetable, one row per engine of the line (TIMETABLE_ROW); the engines the plan left out; why each waiting engine
#: waits (holds); who makes and who reads each thing (handoffs); the chain against its limit; alarms past a window; and
#: the ties Coordination's AI broke
COORDINATION_FIELDS = ("line", "registered", "timetable", "left_out", "holds", "handoffs", "chain", "alarms", "ties")
#: one engine in the timetable: its slot as Coordination wrote it (on, window_min, since), what starts it in words
#: (starts), where it stands now (state, its word, why it waits, and since when), and its last run (last)
TIMETABLE_ROW = ("engine", "on", "starts", "window_min", "since", "state", "word", "why", "at", "last")
TT_WORDS = {"running": "running", "turn": "its turn", "waits": "waits", "ran": "ran", "stopped": "stopped where it was"}


def _trigger(name):
    """The start Coordination keeps a slot for: the engine's version or timer trigger (engine_runtime.slot_of's)."""
    on = ((R.engine_def(name) or {}).get("start") or {}).get("on") or []
    return next((t for t in on if t.get("kind") in ("version", "timer")), on[0] if on else {})


def _starts(trig):
    """What starts an engine, in words: after a new Brief, after a Build that passed, every 1 h."""
    if trig.get("kind") == "version":
        return ("after a %s that passed" if trig.get("checked") else "after a new %s") % trig.get("of")
    if trig.get("kind") == "timer":
        return "every " + R._period(trig.get("every_s"))
    return "on a post to it"


def _clock(ts):
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _live(ref, name, trig, done, now_s):
    """(live, at, why): whether the engine's own trigger is live (a version it has not run on, a period with no start
    yet), since when, and when it is not, what it waits for, by name: 'Pages v2 is not filed yet'."""
    if trig.get("kind") == "version":
        of, checked = trig.get("of"), bool(trig.get("checked"))
        v = W.latest(ref, of, passed=checked)
        if v and W._slot_id(name, of, v["v"]) not in done:
            return True, v.get("at"), None
        nxt, filed = (v["v"] + 1) if v else 1, W.latest(ref, of)
        if checked and filed and filed["v"] >= nxt:
            return False, None, "%s v%d has not passed its check yet" % (of, filed["v"])
        return False, None, "%s v%d is not filed yet" % (of, nxt)
    if trig.get("kind") == "timer":
        every = max(1.0, float(trig.get("every_s") or 1))
        n = int(now_s // every)
        if "%s@timer.%d" % (name, n) not in done:
            return True, _clock(n * every), None
        return False, None, "its next slot is at %s" % datetime.fromtimestamp((n + 1) * every).strftime("%H:%M")
    return False, None, "it starts on a post to it"


def _peek(ref, d, name):
    """The engine with the turn, asked the way due(peek=True) asks it: (True, None) when it may start now, (False, why)
    when something holds it; no row, no ask and no model call is made. Never raises."""
    try:
        ctx = R._coord_ctx(ref, d)
        ctx["peek"] = True
        got = R.ready(ctx, name, ("version", "timer"))
    except Exception:  # noqa: BLE001 -- the read never fails on Coordination's internals
        return False, "not read"
    if got and got[1]:
        return True, None
    return False, (got[2] if got else None) or "nothing starts it yet"


def _wrote(r):
    w = (r or {}).get("wrote") or {}
    return "%s v%s" % (w["art"], w.get("v")) if w.get("art") else None


def _timetable_rows(ref, d, t, rs, stopped, now_s):
    """One row for each engine of the line, in its order, read the way Coordination picks (engine_runtime.coord_pick):
    one run at a time; the first engine of the line whose trigger is live has the turn, or says what holds it, and the
    ones after it wait their turn; an engine whose trigger is not live waits for what it reads, by name, while the work
    before it is still moving, and has simply run once it is not."""
    done = {r["slot"] for r in rs if r.get("slot") and r.get("status") in ("ok", "failed", "skipped")}
    slots = {r.get("engine"): r for r in t.get("timetable") or [] if isinstance(r, dict)}
    running = [r for r in rs if r.get("status") == "running"]
    out, ahead, moving = [], None, False
    for name in t.get("line") or []:
        slot, trig = slots.get(name) or {}, _trigger(name)
        mine = [r for r in rs if r.get("engine") == name]
        last = next((r for r in reversed(mine) if r.get("slot") and r.get("status") in ("ok", "failed", "skipped")), None)
        run = next((r for r in mine if r.get("status") == "running"), None)
        live, at, why = _live(ref, name, trig, done, now_s)
        # the slot it holds now: the timetable's trigger, at the version it runs on next (the record's 'on' names the
        # version at the time Coordination wrote it); its window and since are the record's
        row = {"engine": name, "on": R.slot_of(ref, name, rs)["on"] if trig else slot.get("on"), "starts": _starts(trig),
               "window_min": int(slot.get("window_min") or (d.get("windows") or {}).get(name) or 30), "since": slot.get("since"),
               "state": None, "word": None, "why": None, "at": None,
               "last": last and {"at": last.get("ended") or last.get("started"), "status": last.get("status"), "wrote": _wrote(last)}}
        if stopped:                                    # a stopped department: every engine stopped where it was
            row.update(state="stopped", at=(run or {}).get("started"))
        elif run:
            row.update(state="running", at=run.get("started"))
        elif live:
            if running:
                row.update(state="waits", why="%s is running" % running[0].get("engine"))
            elif ahead:
                row.update(state="waits", why="its turn comes after %s" % ahead)
            else:
                ok, held = _peek(ref, d, name)
                row.update(state="turn", at=at) if ok else row.update(state="waits", why=_plain(held))
        elif moving or not last:
            row.update(state="waits", why=why)
        else:
            row.update(state="ran", at=row["last"]["at"])
        if live or run:
            ahead = ahead or name
        moving = moving or row["state"] in ("running", "turn", "waits")
        row["word"] = TT_WORDS[row["state"]]
        out.append({k: row[k] for k in TIMETABLE_ROW})
    return out


def _handoffs(ref, d):
    """Who makes each thing and who reads it, from the record (made, M1.2): the latest version, its maker in words (the
    Brief is filed by Identity from the owner's words), and the engines and functions that read it."""
    out = []
    for m in made(ref, d, []):
        by = m.get("by")
        out.append({"art": m["art"], "v": m.get("v"), "by": by,
                    "says": "Identity, from your words" if by == "Owner" else (by or None), "readers": list(m.get("readers") or [])})
    return out


def _chain(ref, rs):
    """The chain the latest Brief started, against its limit: a bar; the numbers stay in the read, for the hover."""
    b = W.latest(ref, "Brief")
    used = sum(1 for r in rs if b and r.get("chain") == "brief.v%d" % b["v"])
    return {"of": "Brief v%d" % b["v"] if b else None, "used": used, "limit": W.CHAIN_LIMIT,
            "share": round(min(1.0, used / float(W.CHAIN_LIMIT or 1)), 3)}


def _ties(ref, rows, today):
    """Each time several functions were ready at once and Coordination's AI said who went first (coord.tie), newest
    first: 'Coordination chose Write first', with its why."""
    out = []
    for r in reversed(rows):
        if r.get("step") != "coord.tie" or r.get("status") != "ok" or not r.get("answer"):
            continue
        why = None
        try:
            why = (W._read(R._out_path(ref, r.get("slot"), "coord.tie", None), {}) or {}).get("why")
        except Exception:  # noqa: BLE001
            pass
        at = r.get("ended") or r.get("started")
        out.append({"pick": r["answer"], "said": "Coordination chose %s first" % r["answer"], "why": _plain(why) or None,
                    "at": at, "today": str(at or "")[:10] == today})
        if len(out) == 6:
            break
    return out


def coordination(ref, d=None, rs=None, ak=None, rows=None):
    """Coordination's own state, read off the record (PRD M4.5): its table's line and timetable, each engine's place in
    it and the exact reason anything waits, the engines the plan left out, who makes and who reads each thing, the
    chain against its limit, alarms past a window, and the ties its AI broke. Reads only."""
    d = d or W.dept(ref) or {}
    rs = W.runs(ref) if rs is None else rs
    ak = W.asks(ref) if ak is None else ak
    rows = _rows(ref) if rows is None else rows
    t = R.coordination(ref)
    stopped = bool(d.get("stopped")) or _cycle_state(ref).get("state") == "stopped"
    tt = _timetable_rows(ref, d, t, rs, stopped, time.time())
    today = datetime.now().astimezone().date().isoformat()
    out = {"line": list(t.get("line") or []), "registered": t.get("registered"), "timetable": tt,
           "left_out": [{"engine": r.get("engine"), "since": r.get("since")} for r in t.get("left_out") or [] if isinstance(r, dict)],
           "holds": [{"engine": r["engine"], "why": r["why"]} for r in tt if r["state"] == "waits" and r["why"]],
           "handoffs": _handoffs(ref, d), "chain": _chain(ref, rs),
           "alarms": [{"engine": a.get("engine"), "text": _plain(a.get("text")), "at": a.get("created")}
                      for a in ak if a.get("kind") == "alarm" and a.get("status") == "pending"],
           "ties": _ties(ref, rows, today)}
    return {k: out[k] for k in COORDINATION_FIELDS}


# ---- M4.7: the engine card, the motor folded in and the five beside it (screen S17) -----------------------------------
#: the engine card's read, its shape named once: where the engine stands (head, from Coordination's timetable), the
#: motor's facts (its slot, whether each slot ran once, its window, today's spend) and one row for each of the five
#: functions (ENGINE_FIVE_ROW: the function, a state that is a dot class, its sentence, since when, and a share for a bar)
ENGINE_CARD_FIELDS = ("engine", "head", "motor", "five")
ENGINE_FIVE_ROW = ("fn", "state", "says", "at", "share")
#: an ask that holds an engine, by the function that holds it: Identity's stamp, Priority's limit, Coordination's alarm
ASK_HOLDER = {"publish": "Identity", "setup": "Identity", "engine": "Identity", "envelope": "Priority", "alarm": "Coordination"}
#: what Identity holding an engine says, by the ask that holds it
ASK_HOLDS = {"publish": "holds it until you stamp the first publish", "setup": "holds it until you stamp the department",
             "engine": "holds it until you stamp the engine your words need"}


def _five_row(fn, state, says, at=None, share=None):
    return {"fn": fn, "state": state, "says": says, "at": at, "share": share}


def engine_card(ref, name):
    """One engine as its card shows it (PRD M4.7, S17): its place in Coordination's timetable, the motor's facts, and
    what each of the five is doing to it now, each a sentence from the record. None for a department not on the engine
    runtime. Reads only."""
    d = W.dept(ref)
    if not d or d.get("runtime") != 2:
        return None
    rs, ak = W.runs(ref), W.asks(ref)
    c = coordination(ref, d, rs, ak)
    row = next((r for r in c["timetable"] if r["engine"] == name), None)
    left = next((r for r in c["left_out"] if r["engine"] == name), None)
    cur, t = _cycle_state(ref), R.coordination(ref)
    stopped = bool(d.get("stopped")) or cur.get("state") == "stopped"
    spend, trig = _spend(ref, d, name), _trigger(name)
    clashes = [x for x in slot_clashes(rs) if str(x.get("slot") or "").startswith(name + "@")]
    if row:
        head = {"state": row["state"], "word": row["word"], "why": row["why"], "at": row["at"], "round": cur.get("round")}
    else:
        head = {"state": "left_out" if left else "quiet", "word": "left out of the plan" if left else "not in the line", "why": None,
                "at": (left or {}).get("since"), "round": cur.get("round")}
    motor = {"slot": (row or {}).get("on") or R.slot_of(ref, name, rs)["on"], "starts": _starts(trig), "once": not clashes,
             "says": "ran once per slot" if not clashes else "a slot ran twice",
             "window_min": int((row or {}).get("window_min") or (d.get("windows") or {}).get(name) or 30), "today": spend["share"]}
    # who holds it, if anyone: an ask that names it, else the reason its row waits
    why = str((row or {}).get("why") or "")
    ask = next((a for a in ak if a.get("status") == "pending" and a.get("engine") == name), None)
    holder = ASK_HOLDER.get((ask or {}).get("kind")) if ask else None
    if not holder and row and row["state"] == "waits":
        holder = "Priority" if "envelope" in why or "limit" in why else ("Identity" if "stamp" in why or "owner" in why else None)
    five = []
    # Identity: the rules and the owner's stamp
    if stopped:
        five.append(_five_row("Identity", "off", "the department is stopped"))
    elif holder == "Identity":
        five.append(_five_row("Identity", "warn", ASK_HOLDS.get((ask or {}).get("kind")) or "holds it until you answer"))
    else:
        five.append(_five_row("Identity", "ok", "lets it start: no rule holds it"))
    # Adaptation: how it came into the department's plan
    plans = [w for w in d.get("workflows") or [] if name in (w.get("engines") or [])]
    if left:
        five.append(_five_row("Adaptation", "off", "its plan left it out"))
    elif name in (t.get("grown") or []):
        five.append(_five_row("Adaptation", "ok", "offered it for your idea, and you stamped it"))
    elif plans:
        five.append(_five_row("Adaptation", "ok", "proposed it in the plan Root registered", plans[-1].get("at")))
    else:
        five.append(_five_row("Adaptation", "off", "it is in no plan yet"))
    # Priority: its limit
    over = spend["share"] >= 1 or holder == "Priority"
    ran_today = any(r.get("engine") == name and str(r.get("started") or "")[:10] == W.now()[:10] for r in rs)
    five.append(_five_row("Priority", "block" if over else "ok",
                          "holds it: today's limit is spent" if over else
                          ("let the run start inside today's limit" if ran_today else "keeps its limit, with room today"), share=spend["share"]))
    # Coordination: its slot and its turn
    st = (row or {}).get("state")
    if left:
        co = _five_row("Coordination", "off", "keeps it out of the line", (left or {}).get("since"))
    elif st == "stopped":
        co = _five_row("Coordination", "off", "stopped it where it was")
    elif st == "running":
        co = _five_row("Coordination", "breath", "gave it the turn", row["at"])
    elif st == "turn":
        co = _five_row("Coordination", "breath", "gives it the turn now")
    elif st == "waits":
        co = _five_row("Coordination", "wait", ("keeps its slot while %s holds it" % holder) if holder else "keeps its slot: " + why)
    elif st == "ran":
        co = _five_row("Coordination", "ok", "gave it its slot; it ran", row["at"])
    else:
        co = _five_row("Coordination", "off", "has no slot for it")
    co["share"] = c["chain"]["share"]
    five.append(co)
    # Audit: the thing the line leads to, read or not yet
    final = (W.artifacts_of(d) or [None])[-1]
    v = W.latest(ref, final) if final else None
    read = v and any(r.get("engine") == "Audit" and r.get("slot") == W._slot_id("Audit", final, v["v"]) and r.get("status") == "ok" for r in rs)
    five.append(_five_row("Audit", "ok", "read %s v%d" % (final, v["v"])) if read else
                _five_row("Audit", "off", "will read the %s it leads to" % final if final else "has nothing to read yet"))
    out = {"engine": name, "head": head, "motor": motor, "five": [{k: r[k] for k in ENGINE_FIVE_ROW} for r in five]}
    return _clean({k: out[k] for k in ENGINE_CARD_FIELDS})


def _j2_part(ref, d, fn, events, ak):
    """What J2 adds to this function's pane, from the record as it stands (later milestones fill more of it)."""
    if fn == "Identity":
        return _identity_part(ref, d, events)
    if fn == "Adaptation":
        prop = next((e for e in reversed(events) if e.get("action") == "proposal.created"), None)
        return {"proposal": prop and {"workflow": (prop.get("payload") or {}).get("workflow") or [],
                                      "source": (prop.get("payload") or {}).get("source"), "at": prop.get("occurred_at")},
                "root_checks": [{"summary": _plain(e.get("summary")), "at": e.get("occurred_at"), "passed": e.get("action") == "workflow.validated"}
                                for e in events if e.get("action") in ("workflow.validated", "workflow.blocked")][-4:],
                "rounds": []}
    if fn == "Priority":
        said = {"proposal.granted": "said yes", "proposal.countered": "asked for less", "proposal.refused": "said no"}
        return {"bargains": [{"said": said[e["action"]], "summary": _plain(e.get("summary")), "at": e.get("occurred_at")}
                             for e in events if e.get("action") in said][-6:],
                "envelopes": [dict(_spend(ref, d, n), engine=n) for n in [x[0] for x in W.engines_of(d)] + list(FUNCS)]}
    if fn == "Coordination":
        return coordination(ref, d, ak=ak)                 # its timetable, holds, hand-offs, chain, alarms and ties (PRD M4.5)
    return {"readings": [{"summary": _plain(e.get("summary")), "at": e.get("occurred_at")} for e in events if e.get("action") == "audit.finding_filed"][-6:],
            "findings": [{"text": a.get("text"), "at": a.get("created")} for a in ak if a.get("kind") == "finding" and a.get("status") == "pending"],
            "spot_checks": []}


def function(ref, fn):
    """One function as its site page holds it: its line, the template's fields, its recipe, its journeys with their live
    status, its version 1 scope, and what J2 adds; with its node from functions(). None for a department not on the
    engine runtime; ValueError for a name that is not one of the five."""
    name = _cap(str(fn or "").lower())
    if name not in FUNCS:
        raise ValueError("no function named %s" % fn)
    d = W.dept(ref)
    if not d or d.get("runtime") != 2:
        return None
    all5 = functions(ref) or {}
    node = next((n for n in all5.get("functions") or [] if n["name"] == name), None)
    cur = _cycle_state(ref)
    events = _events(ref, cur.get("cycle_id")) if cur.get("cycle_id") else []
    rows, rs, posts, ak = _rows(ref), W.runs(ref), R.board(ref), W.asks(ref)
    t = _picked(ref, d, name)
    recipe, hears = _recipe(ref, name)
    e = R.engine_def(name) or {}
    page = PAGES[name]
    spend = _spend(ref, d, name)
    fields = [{"key": "goal", "label": "Goal", "value": _cap(_plain(e.get("description")))},
              {"key": "done", "label": "Done when", "value": None},
              {"key": "hears", "label": "Hears", "value": hears or None},
              {"key": "writes", "label": "Writes", "value": _writes(ref, name) or None},
              {"key": "checks", "label": "Checks", "value": [_plain(c) for c in t.get("checks") or []] or None},
              {"key": "envelope", "label": "Limit", "value": {"share": spend["share"]}},
              {"key": "settings", "label": "Settings", "value": _settings(name)}]
    for f in fields:
        f["placeholder"] = f["value"] in (None, "", [])
    return _clean({"ref": ref, "fn": name.lower(), "name": name, "vsm": page["vsm"], "line": page["line"],
                   "holds": page["holds"], "hands_to": page["hands_to"], "keeps": page["keeps"], "v1": page["v1"],
                   "template": {"id": t.get("id"), "name": t.get("name") or "Default", "use_case": t.get("use_case")},
                   "fields": fields, "recipe": recipe,
                   "journeys": _journey_rows(ref, name, _events(ref), rows, rs, posts),
                   "node": node, "cycle": all5.get("cycle"), "j2": _j2_part(ref, d, name, events, ak)})
