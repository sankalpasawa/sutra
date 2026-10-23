"""functions_view.py -- the department's five functions, as one read of the record (PRD M1.1, M1.2).

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
    quiet                  anything else; a department that is stopped or done is quiet throughout, never working

There is no 'asleep' state: the order the five wake in is not ruled (PRD Q9), so only states the record has are shown.
What the record does not hold is named in not_recorded and never guessed (the prototype's "not recorded" list).
"""
import re
import time

import engine_runtime as R
import j2_runtime as J
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
        "running": "The work is running", "pursuing": "Working on what Audit found", "blocked": "Stuck: needs your words",
        "stopped": "Stopped by you", "done": "Goal reached"}
STEPS = ((1, "Enough to work"), (2, "Propose"), (3, "Price"), (4, "Settle"), (5, "Root's review"), (6, "Run"), (7, "Read"),
         (8, "Next or done"))
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


# ---- M1.2: who spoke to whom, who made what and who reads it -------------------------------------------------------
def speaks(ref):
    """Every pair that spoke on the board, src > dst, the owner and Root included: how often, and when last."""
    pairs = {}
    for p in R.board(ref):
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
def _waits_from_threads(ref):
    """The thread rule: the src of an open thread that wrote its latest post waits on the decider (dst[0]); between the
    five only, since a wait on the owner is read from the asks."""
    posts = {}
    for p in R.board(ref):
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
            out[fn] = _short(mine[-1].get("why") or "a step of %s failed its check" % fn)
            continue
        runs_fn = [r for r in rs if r.get("engine") == fn and r.get("status") != "running"]
        if runs_fn and runs_fn[-1].get("status") == "failed":
            out[fn] = _short(runs_fn[-1].get("what") or "%s's last run failed" % fn)
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


def _last_act(fn, rs, posts):
    run = next((r for r in reversed(rs) if r.get("engine") == fn and r.get("status") != "running" and r.get("what")), None)
    post = next((p for p in reversed(posts) if p.get("src") == fn and R._line(p)), None)
    best = None
    if run:
        best = {"what": _short(run.get("what")), "at": run.get("ended") or run.get("started")}
    if post and (not best or W._ts(post.get("at") or "") >= W._ts(best["at"] or "")):
        best = {"what": _short(R._line(post)), "at": post.get("at")}
    return best


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
                    "last": last and {"summary": _short(last.get("summary")), "at": last.get("occurred_at")}})
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
    events = _events(ref, cur.get("cycle_id")) if cur.get("cycle_id") else []
    pending = [a for a in ak if a.get("status") == "pending"]
    running = [r for r in rs if r.get("status") == "running"]
    work_running = [r for r in running if not r.get("system")]
    waits = _waits_from_threads(ref)
    faults = _faults(ref, d, rs, rows, now_s)
    nr = []
    mades = made(ref, d, nr)
    pairs = speaks(ref)
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
        # a run of the function's own
        mine = [r for r in running if r.get("engine") == fn]
        if mine and node["state"] != "working":
            node.update(state="working", line=_short(mine[0].get("what") or "working"))
        # the thread rule
        if node["state"] == "quiet" and fn in waits:
            node.update(state="waiting", waits_on=waits[fn]["on"], line="waits on %s" % waits[fn]["on"])
        # Identity asks: a pending ask, the cycle's open question, a blocked cycle; pursuing waits while a finding is asked
        if fn == "Identity":
            ask = question or finding or (pending[0] if pending else None)
            if state == "blocked":
                node.update(state="waiting_on_you", waits_on="you", line="the plan was not granted; it needs your words")
            elif state == "waiting" or ask:
                node.update(state="waiting_on_you", waits_on="you",
                            line=_short((ask or {}).get("text") or "waits for your answer"))
        if fn in faults:
            node.update(state="fault", why=faults[fn], line=faults[fn])
        # a department that is stopped, or whose goal is reached, is quiet throughout
        if state in ("stopped", "done"):
            node.update(state="quiet", waits_on=None, line="", why=None)
        node["word"] = WORDS[node["state"]]
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
    return _clean({"ref": ref, "name": d.get("name"), "kind": d.get("kind"), "stopped": bool(d.get("stopped")),
                   "functions": nodes, "cycle": cycle, "speaks": pairs, "made": mades,
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
