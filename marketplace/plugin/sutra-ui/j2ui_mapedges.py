"""j2ui_mapedges.py -- the Map's steps and edges (map/1), for j2ui_map.

The page draws the work as boxes on a line with the engine that made each one between them. A step is the engine between
two consecutive trunk boxes; the edges say what turned one box into the next (step), what was given to whom (handoff), who
spoke to whom (speaks_to, from the chat) and who asked whom (asks, uses, from the board). Everything here is read from the
Ctx contract (j2ui_common): the boxes j2ui_map made, the chat, the ledger events, the board entries. Nothing is guessed,
written or sent: an edge exists only where the record holds what it says.

A box of the chain is a dict j2ui_map.boxes made: {slug, eng, node, status}; the Charter has slug 'charter' and no engine.
"""
FUNCS = ("identity", "adaptation", "priority", "coordination", "audit")
CHARTER = "work:charter"
AUDIT_READ = "audit.finding_filed"             # the ledger's word that Audit read the live site (a clean reading files one too)


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def slot_steps(engine):
    """The slot steps of an engine that have a latest row: [(step, last)]. A gate or a rule is a decision on the way to a
    start, not a run of work (engine_runtime.steps_view says which)."""
    sv = (engine or {}).get("steps_view") or {}
    return [(s, s["last"]) for s in sv.get("steps") or [] if isinstance(s, dict) and s.get("mode") == "slot" and s.get("last")]


def checks_of(engine):
    """(passed, run) over the slot steps of one engine that have a latest row; passed means the step's check was ok."""
    rows = slot_steps(engine)
    return sum(1 for _, last in rows if last.get("ok") is True), len(rows)


def step_nodes(chain):
    """One engine node between each two consecutive boxes of the chain. Its label is the engine that makes the box it leads
    to; the Charter to Brief step has no engine and is called Make. made_by is None: functions_view says who made a version
    by engine name, and the page keys its personas by function, so the maker of a step is not recorded."""
    out = []
    for a, b in zip(chain, chain[1:]):
        eng, wfs = b["eng"], list(b["node"]["workflows"])
        passed, run = checks_of(eng) if eng else (0, 0)
        out.append({"id": "step:%s>%s" % (a["slug"], b["slug"]), "kind": "engine", "row": "work", "label": eng["name"] if eng else "Make",
                    "status": b["status"], "version": None,
                    "detail": "%s · %d of %d checks passed" % (plural(len(wfs), "workflow"), passed, run) if run else "not recorded",
                    "file": None, "workflows": wfs, "tag": None, "color": None, "lane": b["node"]["lane"], "team": None,
                    "unchecked": [], "made_by": None})
    return out


def step_edges(chain, steps):
    """box -> step -> box; n is the workflows of the box the step leads to, recorded when it has any."""
    out = []
    for a, s, b in zip(chain, steps, chain[1:]):
        n = len(s["workflows"])
        for src, dst in ((a["node"]["id"], s["id"]), (s["id"], b["node"]["id"])):
            out.append({"from": src, "to": dst, "kind": "step", "label": None, "n": n, "basis": "recorded" if n else "declared"})
    return out


def handoffs(chain):
    """A box given to an engine that is not the next one on the line (the engine reads an artifact other than the box before
    its own), then the Charter to the first box. The line a website is born with hands each box to the next, so it has none
    of the first kind; the charter's line is declared by order, not recorded."""
    out, by_name = [], {b["node"]["label"]: b["node"]["id"] for b in chain if b["slug"] != "charter"}
    for i, b in enumerate(chain):
        eng = b["eng"]
        src = by_name.get(eng.get("reads")) if eng and eng.get("wid") else None
        before = chain[i - 1]["node"]["id"] if i else None
        if src and src != before and src != b["node"]["id"]:
            out.append({"from": src, "to": b["node"]["id"], "kind": "handoff", "label": "given to " + eng["wid"], "n": 1, "basis": "recorded"})
    if chain and chain[0]["slug"] == "charter" and len(chain) > 1:
        out.append({"from": CHARTER, "to": chain[1]["node"]["id"], "kind": "handoff", "label": "built from the charter", "n": 1,
                    "basis": "declared"})
    return out


def speaks(chat):
    """speaks_to edges with message counts: the Requester to Identity (their messages), Identity to the Requester (messages
    addressed to them), and function to function (chat who and next). Messages to and from workflow agents (W-k) are not
    drawn."""
    chat = [m for m in chat or [] if isinstance(m, dict)]
    you = sum(1 for m in chat if m.get("who") == "user")
    back = sum(1 for m in chat if m.get("who") == "identity" and m.get("to_user"))
    out, pairs = [], {}
    for a, b, c in (("person:requester", "fn:identity", you), ("fn:identity", "person:requester", back)):
        if c:
            out.append({"from": a, "to": b, "kind": "speaks_to", "label": None, "n": c, "basis": "recorded"})
    for m in chat:
        a, b = m.get("who"), m.get("next")
        if a in FUNCS and b in FUNCS and a != b:
            pairs[(a, b)] = pairs.get((a, b), 0) + 1
    out += [{"from": "fn:" + a, "to": "fn:" + b, "kind": "speaks_to", "label": None, "n": c, "basis": "recorded"}
            for (a, b), c in sorted(pairs.items(), key=lambda x: (FUNCS.index(x[0][0]), FUNCS.index(x[0][1])))]
    return out


def audits(ctx):
    """How many times Audit read, from the ledger of the current cycle."""
    return sum(1 for e in getattr(ctx, "events", None) or [] if isinstance(e, dict) and e.get("action") == AUDIT_READ)


def lines(ctx, has_charter, target):
    """speaks_to edges from a function to a box it acted on, from the record only: Identity wrote the Charter, and once Audit
    has read, Audit audited the box the Preview shows (`target`, its id) as many times as it read."""
    out = []
    if has_charter:
        out.append({"from": "fn:identity", "to": CHARTER, "kind": "speaks_to", "label": "wrote the charter", "n": None, "basis": "recorded"})
    n = audits(ctx)
    if n and target:
        out.append({"from": "fn:audit", "to": target, "kind": "speaks_to", "label": "audits", "n": n, "basis": "recorded"})
    return out


def board_edges(entries, owner):
    """asks and uses lines between two different boxes, from the message board (board/1): an answered question draws a line
    from the asker's box to the answerer's, and one from each reuser's box to the answerer's, labelled with the question's
    id. A function has no box, so a question it asked draws no line; the Board tab lists every entry. `owner` maps a
    workflow (W-k) to its box."""
    out = []
    for e in entries or []:
        src, dst = owner.get(e.get("asked_by")), owner.get(e.get("to"))
        if src and dst and src != dst and e.get("status") == "answered":
            out.append({"from": src, "to": dst, "kind": "asks", "label": e.get("id"), "n": None, "basis": "recorded"})
            for user in e.get("used_by") or []:
                usrc = owner.get(user)
                if usrc and usrc != dst:
                    out.append({"from": usrc, "to": dst, "kind": "uses", "label": e.get("id"), "n": None, "basis": "recorded"})
    return out
