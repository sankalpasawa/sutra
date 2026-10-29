"""j2ui_map.py -- the J2 page's Map (schema map/1), drawn from the department's own record.

The page (the J2 prototype's j2_ui.html, copied whole) draws /api/map as a metro line: You, the five functions, then the
work in order (the Charter, each artifact of the line with its version and status, and the step between two of them).
This module is that object for a department of kind website, from the Ctx contract (j2ui_common, built by j2ui-core).
The shape is the prototype's j2_map.py at its pin (f9ceba1) and its docs/map-schema.md; the data is Sutra's:

  the Requester          the owner: "You", waiting on you while an ask is open
  the five functions     functions_view's nodes (state -> status), with the calls and seconds of their runs
  the Charter            Identity's goal, once the department has one
  a work box             one artifact of the line: Brief, Site plan, Pages, Build, Live site; its version, its status
                         from the artifact's latest version, the writing engine's latest run and the asks
  a branch box           the artifact of an engine the registered plan left out: hollow, after the trunk
  a step                 the engine between two boxes (j2ui_mapedges); the Charter to Brief step has no engine: Make

Nothing is invented. What Sutra does not record (the version of the Charter, which function worked on a box, tokens, the
workflows of the Brief) is listed in not_recorded and the page says "not recorded". build() writes nothing, makes no model
call and never raises: a wrong shape blanks the page, so a failure returns the empty map with its reason.
"""
from datetime import datetime

import j2ui_artifacts as A
import j2ui_board as B
import j2ui_mapedges as E
import website_dept as W
from j2ui_mapedges import checks_of, plural as _plural

try:                                    # the page's legend, once j2ui-core is merged; the pinned copy below until then
    import j2ui_common as C
except Exception:  # noqa: BLE001 -- j2ui-core may not be here yet
    C = None

SCHEMA = "map/1"
NODE_KINDS = ("person", "function", "engine", "work", "know")          # this adapter draws person, function, engine and work
EDGE_KINDS = ("handoff", "step", "speaks_to", "draws_on", "asks", "uses")
STATUSES = ("filed", "done_unchecked", "running", "waiting", "waiting_on_you", "fault", "left_open", "not_made", "idle")
FUNCS = ("identity", "adaptation", "priority", "coordination", "audit")
NAMES = {"identity": "Identity", "adaptation": "Adaptation", "priority": "Priority", "coordination": "Coordination", "audit": "Audit"}
FN_TAB = {"identity": "charter", "adaptation": "workflows", "priority": "conflicts", "coordination": "timeline", "audit": "audit"}   # the tab that shows each function's work
FN_STATUS = {"working": "running", "waiting": "waiting", "waiting_on_you": "waiting_on_you", "fault": "fault", "quiet": "idle"}
LEGEND_PIN = [
    {"key": "function", "label": "function", "drawn": True},
    {"key": "engine", "label": "engine", "drawn": True},
    {"key": "work", "label": "work with its version", "drawn": True},
    {"key": "filed", "label": "filed and checked", "drawn": True},
    {"key": "done_unchecked", "label": "done · checks did not pass", "drawn": True},
    {"key": "running", "label": "running now", "drawn": True},
    {"key": "left_open", "label": "left open", "drawn": True},
    {"key": "waiting_on_you", "label": "waiting on you", "drawn": True},
    {"key": "fault", "label": "fault", "drawn": True},
    {"key": "not_made", "label": "not made", "drawn": True},
    {"key": "handoff", "label": "hand-off", "drawn": True},
    {"key": "speaks_to", "label": "speaks to", "drawn": True},
    {"key": "asks", "label": "asks (board)", "drawn": True},
    {"key": "uses", "label": "uses (board)", "drawn": True},
]
LEGEND = list(getattr(C, "LEGEND", None) or LEGEND_PIN)
CHARTER = "work:charter"


def _list(ctx, name):
    v = getattr(ctx, name, None)
    return v if isinstance(v, list) else []


def _reason(ctx, why):
    rs = getattr(ctx, "reasons", None)
    if isinstance(rs, list) and why not in rs:
        rs.append(why)


def empty(why="nothing to draw yet", ref=None):
    """The map with nothing on it: what the page reads without a blank screen (the prototype's own empty map)."""
    return {"schema": SCHEMA, "run": ref, "live": False,
            "status": {"state": "not started", "state_status": "idle", "checks": {"passed": 0, "run": 0}},
            "nodes": [], "edges": [], "legend": [dict(r) for r in LEGEND], "built_from": [], "not_recorded": [why]}


def closed(ctx):
    """The department has ended its work: the goal is reached or it is stopped. A finished department never says running."""
    return bool(getattr(ctx, "stopped", False)) or getattr(ctx, "state", None) in ("done", "stopped")


def has_goal(ctx):
    """The department has a goal to draw as the Charter: its first artifact has a version, or a request was made (the
    same test as website_dept.map_view's has_goal, from public reads)."""
    got = getattr(ctx, "has_goal", None)
    if isinstance(got, bool):
        return got
    arts = _list(ctx, "arts")
    if arts and arts[0].get("versions"):
        return True
    try:
        return bool(W.requests(ctx.ref))
    except Exception:  # noqa: BLE001 -- the Charter is left off, and the map says why
        return False


def runs_of(ctx, name):
    """The runs of one engine or function, oldest first."""
    return [r for r in _list(ctx, "runs") if isinstance(r, dict) and r.get("engine") == name]


def _secs(row):
    try:
        return max(0.0, (datetime.fromisoformat(row["ended"]) - datetime.fromisoformat(row["started"])).total_seconds())
    except (KeyError, TypeError, ValueError):
        return 0.0


# ---- the person and the five functions ---------------------------------------------------------------------------------------
def person(ctx):
    mine = [m for m in _list(ctx, "chat") if m.get("who") == "user"]
    chat = bool(_list(ctx, "chat"))
    return {"id": "person:requester", "kind": "person", "row": "people", "label": "You",
            "status": "waiting_on_you" if getattr(ctx, "paused_ask", None) else "idle", "version": None, "tag": None, "color": "--user",
            "file": None, "detail": _plural(len(mine), "message") + " from you" if chat else "not recorded", "workflows": []}


def functions(ctx, nr):
    """The five function nodes from functions_view: state to status, `waiting_on_you` only while an ask is open (the same
    source as the page's paused), calls and seconds from the function's own runs. Tokens are not recorded."""
    fv = getattr(ctx, "fv", None) or {}
    nodes = {n.get("fn"): n for n in fv.get("functions") or [] if isinstance(n, dict)}
    asked = bool(getattr(ctx, "paused_ask", None))
    out = []
    for fn in FUNCS:
        src = nodes.get(fn) or {}
        status = FN_STATUS.get(src.get("state"), "idle")
        if status == "waiting_on_you" and not asked:
            status = "idle"
        mine = runs_of(ctx, NAMES[fn])
        said = [m for m in _list(ctx, "chat") if m.get("who") == fn]
        last = B.protocol_words(str(said[-1].get("text") or ""))[:140] if said else ""      # what a function wrote may carry a protocol token
        line = B.protocol_words(str(src.get("line") or ""))[:140]
        if C is not None:                                  # the owner's words in the line (Identity waiting on a rule) stay theirs
            line = C.keep_said(src.get("line"), line)
        wait = src.get("waits_on")
        out.append({"id": "fn:" + fn, "kind": "function", "row": "functions", "label": NAMES[fn], "status": status, "version": None,
                    "tag": None, "color": "--" + fn, "file": None, "workflows": [], "tab": FN_TAB[fn],
                    "wait_on": "you" if status == "waiting_on_you" else (wait if status == "waiting" and wait else None),
                    "calls": sum(int((r.get("spend") or {}).get("calls") or 0) for r in mine),
                    "seconds": round(sum(_secs(r) for r in mine), 1), "tokens": {"input": 0, "output": 0},
                    "detail": line if status != "idle" and line else ("last seen: " + last if last else "no message recorded")})
        if not said:
            nr.append("what %s did (chat)" % NAMES[fn])
    return out


# ---- the work row ---------------------------------------------------------------------------------------------------------------
def box_status(ctx, ver, eng, is_closed):
    """A box's status from its artifact's latest version, the writing engine's latest run and the asks. A failed run is a
    fault; a run in progress is running (never in a finished department); a version whose check passed is filed, one whose
    check did not is done_unchecked (amber: done, checks did not pass); no version is waiting on you while an ask names the
    engine, left open once the department is closed, else not made. The Brief has no engine: filed once it has a version."""
    runs = (eng or {}).get("runs")
    runs = runs if isinstance(runs, list) else (runs_of(ctx, eng["name"]) if eng else [])
    last = runs[-1].get("status") if runs and isinstance(runs[-1], dict) else None
    if last == "failed":
        return "fault"
    if eng and (last == "running" or eng.get("state") == "Running"):
        return "left_open" if is_closed else "running"
    if ver is not None:
        return "filed" if eng is None or (ver.get("check") or {}).get("ok") is True else "done_unchecked"
    if eng and any(a.get("status") == "pending" and a.get("engine") == eng["name"] for a in _list(ctx, "asks") if isinstance(a, dict)):
        return "waiting_on_you"
    return "left_open" if is_closed else "not_made"


def charter():
    return {"id": CHARTER, "kind": "work", "row": "work", "label": "Charter", "tag": "Charter", "color": "--charter", "status": "filed",
            "version": None, "detail": "the plan every workflow reads", "file": None, "workflows": [], "lane": "trunk"}


def boxes(ctx):
    """One dict per artifact of the line, trunk boxes in line order, then the branch boxes of the engines the plan left out.
    Each carries its node (`node`), the artifact, the writing engine and its latest version, for the step nodes and edges."""
    arts = [a for a in _list(ctx, "arts") if isinstance(a, dict) and a.get("name")]
    engines = [e for e in _list(ctx, "engines") if isinstance(e, dict)]
    prev, listing, is_closed = A.previewable(ctx), A.listing(ctx), closed(ctx)
    rows = {r["name"]: r for r in listing["deliverables"] + listing["records"]}
    trunk, branch = [], []
    for a in arts:
        writers = [e for e in engines if e.get("writes") == a["name"]]
        eng = next((e for e in writers if e.get("in_line", True)), None)
        vs = [v for v in a.get("versions") or [] if isinstance(v, dict) and v.get("v") is not None]
        ver = vs[-1] if vs else None
        out = trunk
        if writers and eng is None:                       # every engine that writes it was left out of the plan
            out, ver, eng = branch, None, writers[0]
        row = rows.get(a["name"])
        slug = a.get("slug") or W.slug(a["name"])
        run = checks_of(eng)[1] if eng else 0
        # the listing's own tag when the artifact has a file; before that a website's Preview artifact and Live site are pages
        # (a website reads as before); any other kind's artifact with no version yet is Other, never a Site (A5.1.2)
        tag, color = (row["tag"], row["color"]) if row else A.tag_of(a["name"], "index.html" if ver or getattr(ctx, "kind", "website") == "website" else None, prev)
        if out is branch:
            status, detail, version, file = "not_made", "left out of the plan", None, None
            tag, color = "Other", "--other"
        else:
            status = box_status(ctx, ver, eng, is_closed)
            detail = _plural(run, "step") + " checked" if run else "no steps recorded"
            version, file = (ver["v"] if ver else None), (row or {}).get("file")
        node = {"id": "work:" + slug, "kind": "work", "row": "work", "label": a["name"], "tag": tag, "color": color, "status": status,
                "version": version, "detail": detail, "file": file,
                "workflows": [e["wid"] for e in writers if e.get("wid") and (out is branch or e.get("in_line", True))], "lane": "branch" if out is branch else "trunk"}
        out.append({"art": a, "slug": slug, "eng": eng, "ver": ver, "node": node, "status": status})
    return trunk, branch


def outcome(ctx):
    """Done, or Done with open items: a done-when item that still rests on a fact nobody gave, or a finding still asked
    (the same rule as the state's outcome); None while the department is not done."""
    if getattr(ctx, "state", None) != "done":
        return None
    items = W.items_of(ctx.d) if isinstance(getattr(ctx, "d", None), dict) else []
    open_ask = any(isinstance(a, dict) and a.get("kind") == "finding" and a.get("status") == "pending" for a in _list(ctx, "asks"))
    return "Done with open items" if open_ask or any(i.get("confirm") for i in items) else "Done"


def status_line(ctx, fns):
    """(state, state_status) for the pill at the top: who is running now, or how it stands."""
    if getattr(ctx, "paused_ask", None):
        return "Waiting on you", "waiting_on_you"
    work = [n for n in fns if n["status"] == "running"]
    if work:
        return "%s running" % work[0]["label"], "running"
    if getattr(ctx, "state", None) == "done":
        return outcome(ctx), "idle"
    if getattr(ctx, "stopped", False) or getattr(ctx, "state", None) == "stopped":
        return "Stopped", "idle"
    if any(isinstance(e, dict) and e.get("state") == "Running" for e in _list(ctx, "engines")):
        return "Running", "running"
    return ("Waiting", "waiting") if (getattr(ctx, "cur", None) or {}).get("cycle_id") else ("Idle", "idle")


def _build(ctx):
    nr = ["version of Charter"]
    chat = _list(ctx, "chat")
    if not chat:
        nr.append("chat (messages from the Requester)")
    fns = functions(ctx, nr)
    trunk, branch = boxes(ctx)
    goal = has_goal(ctx)
    if not goal:
        nr.append("the goal (none is recorded yet, so no plan is drawn)")
    chain = ([{"slug": "charter", "eng": None, "node": charter(), "status": "filed"}] if goal else []) + trunk
    steps = E.step_nodes(chain)
    work = []
    for i, b in enumerate(chain):
        work += ([steps[i - 1]] if i else []) + [b["node"]]
    work += [b["node"] for b in branch]
    placed = {w for b in trunk + branch for w in b["node"]["workflows"]}
    wids = [e["wid"] for e in _list(ctx, "engines") if isinstance(e, dict) and e.get("wid")]
    first = (trunk[0]["art"]["name"] if trunk else "the first artifact")
    nr += ["workflows of " + first] + ["workflows of " + b["node"]["label"] for b, s in zip(chain[1:], steps) if not s["workflows"]]
    lost = [w for w in wids if w not in placed]
    if lost:
        nr.append("workflows not placed on the map: " + ", ".join(lost))
    prev = A.previewable(ctx)
    target = next((b["node"]["id"] for b in trunk if b["art"]["name"] == prev), None)
    audited = bool(E.audits(ctx) and target)
    for b in trunk:
        n = b["node"]
        if n["version"] is None:
            nr.append("version of " + n["label"])
        elif audited and n["id"] == target:
            nr.append("which other function worked on %s (only Audit is recorded)" % n["label"])
        else:
            nr.append("which function worked on %s: not recorded" % n["label"])
    owner = {w: b["node"]["id"] for b in trunk + branch for w in b["node"]["workflows"]}
    entries = B.build(ctx).get("entries") or []                      # none until W3-BOARD files questions.json: no asks or uses lines
    edges = (E.step_edges(chain, steps) + E.handoffs(chain) + E.speaks(chat) + E.lines(ctx, goal, target) + E.board_edges(entries, owner))
    nr += ["tokens per function (Sutra records calls and cost, not tokens)", "messages to and from workflow agents (W-n) are not drawn",
           "what the work draws on (Knows row, later version)"]
    passed = run = 0
    for e in _list(ctx, "engines"):
        p, r = checks_of(e)
        passed, run = passed + p, run + r
    state, state_status = status_line(ctx, fns)
    return {"schema": SCHEMA, "run": (getattr(ctx, "cur", None) or {}).get("cycle_id") or ctx.ref,
            "live": any((n.get("state") == "working") for n in (getattr(ctx, "fv", None) or {}).get("functions") or []) or bool(getattr(ctx, "paused_ask", None)),
            "status": {"state": state, "state_status": state_status, "checks": {"passed": passed, "run": run}},
            "nodes": [person(ctx)] + fns + work, "edges": edges, "legend": [dict(r) for r in LEGEND], "built_from": ["department record"],
            "not_recorded": list(dict.fromkeys(nr))}


def build(ctx):
    """The map/1 object for the department, memoised on ctx.memo; the empty map with its reason when anything fails."""
    memo = getattr(ctx, "memo", None)
    memo = memo if isinstance(memo, dict) else {}
    if "map" not in memo:
        try:
            memo["map"] = _build(ctx)
        except Exception as exc:  # noqa: BLE001 -- a wrong shape blanks the page: the empty map, and why
            _reason(ctx, "the map could not be drawn: %s" % exc)
            memo["map"] = empty("the map could not be drawn (%s)" % exc, getattr(ctx, "ref", None))
    return memo["map"]
