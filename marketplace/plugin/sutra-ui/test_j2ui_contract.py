"""test_j2ui_contract.py -- the adapter, as the page meets it: the whole app, every cycle state, the prototype's shapes
(UI port, package j2ui-verify, step T3).

Every claim here goes through the full app (TestClient on app.py, loopback host) against a department seeded by
test_fixtures/j2ui/seed.py, and takes the prototype's own answers (test_fixtures/j2ui/captured) and constants (the pinned
j2_map.py, j2_artifacts.py, j2_board.py) as the shape truth. The module tests of the five j2ui packages prove each builder; this
proves what the page is given.

Named claims:
  T3-1  every cycle state of test_j2ui_state.STATE_TABLE (imported, not restated), and the departments the contract adds, answer
        every route: api/state has exactly the 56 keys and carries each key the page reads, and says what its row says (status,
        thinking, step, paused, outcome, done, stamped); atoms_v1 is run_views of the workflows by the vendored schema and the
        prototype's validator finds no atom missing; api/map has the captured map's keys, statuses, node and edge kinds, the
        pinned legend, and the golden invariants; api/board, api/artifacts, api/docs, api/audits, api/refs, api/preview and
        api/call have the prototype's shapes
  T3-2  nothing the adapter says anywhere has GRANT, COUNTER or REFUSE, an act id, a path of this machine or a private key; only
        Identity's messages are for the owner; ids are the places in the list
  T3-3  the page is never blanked: each state's real answers, fed through poll_harness.js on the copy of the page, are ok
  T3-4  the P1 cases: after the owner's follow-up through Root there is one more user message and none is the Validator's; two
        publish asks pending at once are two ask messages, paused names one and there is no third; `Option 1` on an options ask
        chooses it; `Option 2` is the second option the owner was shown even after Stop came back into the list; a stamp is `Option 1`
  T3-5  the honesty cases: a clean reading is one line, with no per-item PASS, no `Workable (checked by code)` and workable None; every
        condition names who recorded it; and, as a strict expected failure (E1, open), none is Root's check of the plan
  T3-6  scope: a department of kind default, a Root, a department of the first build and an unknown ref are 404 on every route
  T3-7  the guard stands: a write with an Origin and without the panel token is 403; with the token it passes; api/artifact refuses
        a path that leaves its folder; a built site, a file and a screenshot carry the SAFE headers

Run: ./run-tests.sh test_j2ui_contract.py"""
import json
import re

import pytest
from fastapi.testclient import TestClient

import app as app_module
from test_fixtures.j2ui import harness as H
from test_fixtures.j2ui import proto
from test_fixtures.j2ui import seed as SEED
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403  (blocked, card_post and the other record helpers)
from test_j2ui_state import STATE_TABLE

import engine_runtime as R
import j2_runtime as J
import j2ui_atoms as A
import j2ui_common as C
import website_api

UI = H.HERE.parents[1]
COPY = UI / "j2ui_assets" / "j2_ui.html"
CAPTURE = "j2-20261014-111512"
GET_ROUTES = ("api/state?since=0", "api/runs", "api/map", "api/board", "api/artifacts", "api/docs", "api/audits", "api/refs",
              "api/preview?atom=W-1.a1", "api/call?id=1", "api/artifact?name=brief/v1/brief.md", "site/latest", "site/latest/index.html",
              "file/prd.md", "shot/1")
POST_ROUTES = ("api/say", "api/reset", "api/output", "api/playbooks/clear", "api/lessons/clear")
#: the words the owner never reads (SCREEN WORD RULES): the bargain's old names GRANT, COUNTER and REFUSE, "order" and "orders" (the old
#: noun for what a function says to another, so the word is not used in any sense), and every act id that
#: has a hyphen in it (accept-proposal, reject-proposal, not-understood), from the runtime's own list of acts, not a copy of it
BANNED = re.compile(r"GRANT|COUNTER|REFUSE|\borders?\b|" + "|".join(re.escape(a) for a in R.ACTS if "-" in a), re.I)
#: an act id printed as an id: a string that is nothing else, in the form `act: cancel`, or in capitals anywhere (FAILURE). The one-word ids
#: are English as well (the prototype's own step is called "J2.b Propose"), so a word in a sentence is not one
RAW_ACT = re.compile(r"^\s*(?:%s)\s*$|\b(?:act|word|msg_type)\s*[:=]\s*(?:%s)\b|\b(?:%s)\b" % (
    "|".join(R.ACTS), "|".join(R.ACTS), "|".join(a.upper().replace("-", "[-_]") for a in R.ACTS)))
WHO = {"user", "validator", "identity", "adaptation", "priority", "coordination", "audit"}
JSON_ROUTES = ("api/state?since=0", "api/runs", "api/map", "api/board", "api/artifacts", "api/docs", "api/audits", "api/refs", "api/preview?atom=W-1.a1")
EXTRA_STATES = ("two_publish_asks", "running_line", "with_board", "pursuing_line", "filed", "question", "ready", "root_follow_up", "start", "build_filed")
TABLE = [pytest.param(row, id=row[0]) for row in STATE_TABLE]


@pytest.fixture(scope="module")
def client():
    return TestClient(app_module.app, base_url="http://127.0.0.1")


@pytest.fixture
def plant(tmp_path, monkeypatch):
    """plant(state) -> (ref, m): a department in that state on fresh homes (the seed boots them)."""
    n = [0]

    def make(state, **kw):
        n[0] += 1
        return SEED.seed(tmp_path / ("homes%d" % n[0]), state, env=monkeypatch, **kw)
    return make


def url(ref, path=""):
    return "/j2ui/%s/%s" % (ref, path)


def strings(obj, keys=False):
    """Every string in a JSON value (and, with keys, every key too)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if keys:
                yield k
            yield from strings(v, keys)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v, keys)
    elif isinstance(obj, str):
        yield obj


def all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_keys(v)


def read_all(client, ref):
    """Every JSON route of the page, as the page reads them: {name: body}. Each answers 200 and is JSON, no-store."""
    out = {}
    for path in JSON_ROUTES:
        r = client.get(url(ref, path))
        assert r.status_code == 200, (path, r.status_code, r.text[:120])
        assert r.headers["content-type"].startswith("application/json") and r.headers["cache-control"] == "no-store", path
        out[path.split("?")[0][4:]] = r.json()
    r = client.get(url(ref, "api/call?id=1"))
    assert r.status_code == 404 and r.json() == {"error": "no such call"}
    return out


def files_of(home):
    """Every file under the records home: {path relative to it: the hash of its bytes}."""
    import hashlib
    import os
    out = {}
    for root, dirs, files in os.walk(home):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, home)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def snapshot(home):
    """The records home as one value, to compare before and after: what 'a read writes nothing' says."""
    return sorted(files_of(home).items())


def changed(before, home):
    """The files of the records home that differ from a files_of() taken earlier (the message of a failed claim)."""
    after = files_of(home)
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


# ---- the shapes of the prototype -------------------------------------------------------------------------------------
def captured_keys():
    """The key lists of the prototype's own map: per node kind, the edge, the top level and the status."""
    mp = H.captured(CAPTURE, "map")
    nodes = {}
    for n in mp["nodes"]:
        nodes.setdefault(n["kind"], list(n))
    return {"top": list(mp), "nodes": nodes, "edge": list(mp["edges"][0]), "status": list(mp["status"])}


def check_map(mp, s, engines):
    cap = captured_keys()
    statuses = proto.consts("j2_map.py", "STATUSES")
    node_kinds = [k for k in proto.consts("j2_map.py", "NODE_KINDS") if k != "know"]
    edge_kinds = proto.consts("j2_map.py", "EDGE_KINDS")
    assert list(mp) == cap["top"] and mp["schema"] == "map/1" and list(mp["status"]) == cap["status"]
    assert mp["legend"] == proto.consts("j2_map.py", "LEGEND") == C.LEGEND
    nodes, edges = mp["nodes"], mp["edges"]
    ids = [n["id"] for n in nodes]
    assert len(set(ids)) == len(ids), "an id is one node"
    for n in nodes:
        assert n["kind"] in node_kinds and n["status"] in statuses, n["id"]
        assert list(n) == cap["nodes"][n["kind"]], (n["id"], "the node keys of the prototype's own map")
    for e in edges:
        assert e["kind"] in edge_kinds and e["from"] in ids and e["to"] in ids and list(e) == cap["edge"], e
    # golden invariants: the person first, the five functions in order, the trunk in the registered line's order
    assert ids[0] == "person:requester" and ids[1:6] == ["fn:identity", "fn:adaptation", "fn:priority", "fn:coordination", "fn:audit"]
    steps = [n for n in nodes if n["kind"] == "engine" and n.get("lane") == "trunk" and not n["id"].startswith("step:charter>")]
    line = [w["name"] for w in s["workflows"]]
    assert [n["label"] for n in steps] == [e for e in engines if e in line or not line], \
        "the trunk's steps are the department's engines in the registered line's order (the Charter's own step apart)"
    if line:
        assert [n["workflows"] for n in steps] == [[w["id"]] for w in s["workflows"]]
    # every workflow of the state is on exactly one box, or named where the map says it does not know
    boxes = [n for n in nodes if n["kind"] == "work"]
    said = " ".join(mp["not_recorded"])
    for w in s["workflows"]:
        on = [n["id"] for n in boxes if w["id"] in n["workflows"]]
        assert len(on) == 1 or w["id"] in said or w["name"] in said, (w["id"], on)
    # waiting on you only with an open question; a finished department never says running
    asked = bool(s["paused"]) or any(m.get("pause") for m in s["chat"] if m["who"] == "identity" and m.get("act") == "ASK_REQUESTER")
    if not asked:
        assert not [n["id"] for n in nodes if n["status"] == "waiting_on_you"], "nobody asked, so nobody waits on you"
        assert mp["status"]["state_status"] != "waiting_on_you"
    if str(s["outcome"] or "").startswith("Done"):
        assert not [n["id"] for n in nodes if n["status"] == "running"] and mp["status"]["state_status"] != "running"


def check_artifacts(ar):
    row_keys = list(H.captured(CAPTURE, "artifacts")["deliverables"][0])
    opens = set(proto.consts("j2_artifacts.py", "OPEN").values())
    assert list(ar) == ["deliverables", "records"]
    for r in ar["deliverables"] + ar["records"]:
        assert list(r) == row_keys, r["name"]
        assert r["open"] in opens, (r["name"], r["open"])
        assert isinstance(r["file"], str) and r["file"] and r["deliverable"] in (True, False)
    assert all(r["deliverable"] for r in ar["deliverables"]) and not any(r["deliverable"] for r in ar["records"])


def check_board(bd):
    assert list(bd) == ["schema", "entries"] and bd["schema"] == "board/1"
    want = list(proto.load("j2_board").new_entry("Q-1", "W-1", None, "W-2", "x", "q", 1, 1))
    for e in bd["entries"]:
        assert list(e) == want, e


def check_state(s, row=None):
    assert list(s) == list(C.STATE_KEYS) and len(s) == 56
    assert s["total"] == len(s["chat"]) or s["total"] >= len(s["chat"])
    assert s["error"] is None and s["saved"] is None and s["write_lock"] is None and s["memory"] is False
    assert s["outcome"] in (None, "Done", "Done with open items"), "never Stopped, Crashed or Paused"
    assert s["output"] == "website" and s["doc"] is False and s["files"] == [] and s["docset"] == []
    if row:
        name, _setup, status, thinking, step, pause, outcome, done, stamped = row
        got = (s["status"], s["thinking"], s["step"], (s["paused"] or {}).get("kind"), s["outcome"], s["done"], s["stamped"])
        assert got == (status, thinking, step, pause, outcome, done, stamped), name
    p = s["paused"]
    if p:
        assert set(p) == {"kind", "questions", "msg", "label", "choices"} and s["chat"][p["msg"] - 1]["act"] == "ASK_REQUESTER"
        assert s["status"] != "running", "the composer and the option buttons stay live when something waits on the owner"
    for i, m in enumerate(s["chat"], 1):
        assert m["id"] == i and m["who"] in WHO and isinstance(m["text"], str), m
        assert ("to_user" not in m) or (m["to_user"] is True and m["who"] == "identity"), "only Identity speaks to the owner: " + m["who"]
        if m["who"] != "identity":                          # rule 1: nobody else is addressed to the owner, whatever the key that says it
            assert "user" not in (m.get("next"), m.get("audience")), "only Identity speaks to the owner (next or audience): %s %r" % (m["who"], m)
    wf = s["workflows"]
    views, warns = A.schema().run_views(wf)
    assert s["atoms_v1"] == {v["id"]: v for v in views}, "atoms_v1 is the prototype's own run_views"
    assert not [w for w in warns if "which is not an atom" in w or "missing" in w], warns
    assert not [w for w in A.schema().validate_views(list(s["atoms_v1"].values())) if "missing" in w]


def check_words(bodies):
    """Nothing the adapter says has a banned word, an act id, a path of this machine or a private key."""
    for name, body in bodies.items():
        for text in strings(body):
            assert not BANNED.search(text), (name, text[:120])
            assert not RAW_ACT.search(text), (name, "an act id as it is on the board: " + text[:120])
            assert not C.ABS_PATH.search(text), (name, text[:120])
        assert not {str(k).lower() for k in all_keys(body)} & J.PRIVATE_KEYS, name
    assert not [m for m in bodies["state"]["chat"] if re.search(r"\b(?:accept|reject|propose|inform|request)\b-?\w*:", m["text"])]


def check_page(ref, bodies, client):
    """The page, polled on the copy against the adapter's real answers, draws without a fault and with no undefined, NaN or null."""
    bundle = {"state": bodies["state"], "map": bodies["map"], "board": bodies["board"], "artifacts": bodies["artifacts"], "docs": bodies["docs"],
              "audits": bodies["audits"], "refs": bodies["refs"], "runs": bodies["runs"], "preview": bodies["preview"]}
    got = H.run_harness(COPY, bundle)
    assert got["ok"], got["errors"]
    return got


def everything(client, ref, m, row=None):
    before = files_of(m.home)                                 # hard rule 4(g): the records are hashed BEFORE the first read of the department
    bodies = read_all(client, ref)
    assert changed(before, m.home) == [], "the first read wrote"
    m.C.touch(ref)
    read_all(client, ref)                                     # and a second that rebuilds the read at once
    assert changed(before, m.home) == [], "the second read wrote"
    check_state(bodies["state"], row)
    check_map(bodies["map"], bodies["state"], [e[0] for e in m.W.engines_of(m.W.dept(ref))])
    assert not m.C.get_ctx(ref).reasons, "the read of the department failed in no part: " + str(m.C.get_ctx(ref).reasons)
    check_artifacts(bodies["artifacts"])
    check_board(bodies["board"])
    assert list(bodies["docs"]) == ["prd", "hld", "lld"] and all(v == {"asked": False, "text": None, "workflows": []} for v in bodies["docs"].values())
    assert bodies["audits"] == [] and bodies["preview"] == {"anchor": None, "html": None}
    assert bodies["runs"] == {"live": bodies["runs"]["live"], "runs": []}
    assert set(bodies["refs"]) == {"conditions", "rubric"} and bodies["refs"]["rubric"] == {}
    check_words(bodies)
    check_page(ref, bodies, client)
    return bodies


# ---- T3-1 to T3-3: every state ---------------------------------------------------------------------------------------------
def test_t31_every_key_the_page_reads_is_a_key_of_the_state():
    html = COPY.read_text(encoding="utf-8")
    tokens = set(re.findall(r"\b(?:s|CTX|state)\.(\w+)", html))
    not_state = {"id", "detail", "allChat"}
    assert tokens - not_state <= set(C.STATE_KEYS), sorted(tokens - not_state - set(C.STATE_KEYS))
    assert {"chat", "total", "status", "paused", "outcome", "versions", "thinking", "has_board", "workflows", "atoms_v1"} <= tokens


@pytest.mark.parametrize("row", TABLE)
def test_t31_each_cycle_state_answers_every_route_and_says_what_its_row_says(client, plant, row):
    ref, m = plant(row[0])
    bodies = everything(client, ref, m, row)
    assert bodies["state"]["status"] == row[2]


@pytest.mark.parametrize("name", EXTRA_STATES)
def test_t31_the_departments_the_contract_adds_answer_every_route(client, plant, name):
    ref, m = plant(name)
    bodies = everything(client, ref, m)
    s = bodies["state"]
    if name in ("running_line", "with_board", "pursuing_line", "filed", "question", "ready", "root_follow_up"):
        assert [w["id"] for w in s["workflows"]] == ["W-1", "W-2", "W-3", "W-4"] and len(s["atoms_v1"]) == 11, "a registered line has its atoms"
        assert len(s["lanes"]) == 10, "lanes for the five functions, the validator and the four builders"
    if name in ("pursuing_line", "filed", "question", "ready", "root_follow_up"):
        assert bodies["artifacts"]["deliverables"], "something is built, and the Artifacts tab lists it"
    if name == "with_board":
        assert s["has_board"] is True and len(bodies["board"]["entries"]) == 2
        assert {e["status"] for e in bodies["board"]["entries"]} == {"answered", "open"}
        assert {"asks", "uses"} <= {e["kind"] for e in bodies["map"]["edges"]}, "the board's questions are drawn on the Map"
    else:
        assert s["has_board"] is False and bodies["board"]["entries"] == []
    if name == "ready":
        assert s["outcome"] == "Done" and s["done"] is True and s["paused"] is None
    if name == "start":
        assert s["status"] == "idle" and s["chat"] == [] and s["total"] == 0


#: every state of the cycle table and every extra department is read, and hashed before the first read, by everything() above; these are the
#: ones it does not read (with the routes it does not either: the built site, a file, a screenshot, one artifact)
READ_STATES = ("filed", "build_filed", "two_publish_asks", "hostile", "building")
READS = GET_ROUTES


def read_everything(client, ref):
    """Every GET of the page's routes, answered or not: how many answered 200 or 302."""
    got = 0
    for path in READS:
        got += client.get(url(ref, path), follow_redirects=False).status_code in (200, 302)
    return got


def test_t31_the_map_is_the_same_twice_and_a_read_writes_nothing(client, plant):
    ref, m = plant("filed")
    before = snapshot(m.home)                                 # before the FIRST read: a read that writes is caught on the first one
    first = read_all(client, ref)
    assert snapshot(m.home) == before, "the first read wrote"
    again = read_all(client, ref)
    assert snapshot(m.home) == before, "reading writes nothing"
    assert again["map"] == first["map"] and again["artifacts"] == first["artifacts"] and again["state"]["chat"] == first["state"]["chat"]


@pytest.mark.parametrize("name", READ_STATES)
def test_t31_every_get_of_the_page_writes_nothing_on_the_first_read_and_the_next(client, plant, name):
    """Hard rule 4(g): reads write nothing. The records home is hashed BEFORE the first GET (the first is the one that builds the read of
    the department: the Map, the status, what is due next), then after every route the page calls, and again after a second pass made to
    rebuild at once. build_filed is the line stepped to the instant after Build is filed and before anything has asked the owner to
    publish: the window in which a read once filed the ask."""
    ref, m = plant(name)
    before = files_of(m.home)
    assert read_everything(client, ref) > 5
    assert changed(before, m.home) == [], "the first read of %s wrote" % name
    m.C.touch(ref)
    read_everything(client, ref)
    assert changed(before, m.home) == [], "the second read of %s wrote" % name


def test_t31_a_read_writes_nothing_at_any_slot_of_a_run_nor_after_the_stamp(client, tmp_path, monkeypatch):
    """The motor leaves a window after every slot (Build filed and Publish not yet asked, an engine due and not yet started...). The
    line is run one slot at a time from the words to the owner's stamp and on to the end, and after every slot the department is read
    from a fresh read (touch) and compared with the records before it."""
    m = SEED.boot(tmp_path / "homes", monkeypatch)
    seen = {"slots": 0, "reads": 0}

    def read_between():
        ref = next((d["ref"] for d in m.W.list_depts() if d.get("parent") == m.root), None)
        if ref is None:
            return
        m.C.touch(ref)
        before = files_of(m.home)
        seen["reads"] += read_everything(client, ref) > 0
        assert changed(before, m.home) == [], "a read after slot %d (%s) wrote" % (seen["slots"], ref)

    for who, ref in SEED.stepped(m, org="Walk Learning"):
        seen["slots"] += 1
        read_between()
    ref = m.ref
    pending = [a for a in m.W.asks(ref) if a.get("status") == "pending" and a.get("kind") == "publish"]
    assert pending, "the line ran to its first question"
    for a in pending:
        m.W.decide_ask(ref, a["id"], True)
    read_between()
    while m.W.run_until_idle(ref, limit=1):
        seen["slots"] += 1
        read_between()
    assert seen["slots"] >= 10 and seen["reads"] >= seen["slots"] - 2, seen


def read_to_rest(client, m, ref, what, limit=60):
    """The department run one slot at a time until nothing is due, and read, from a fresh read, in the window before the first slot and
    after every slot: the records home is hashed before each round of reads and must be what it was after it. Returns the slots run."""
    def read():
        m.C.touch(ref)
        before = files_of(m.home)
        assert read_everything(client, ref) > 5
        assert changed(before, m.home) == [], "a read %s wrote" % what
    read()
    slots = 0
    while m.W.run_until_idle(ref, limit=1):
        slots += 1
        assert slots < limit, "the line never rests"
        read()
    read()                                                    # and once more at rest, after the last tick has filed whatever it files
    return slots


@pytest.mark.parametrize("how", ["decide_ask", "api_say"])
def test_t31_a_read_writes_nothing_at_any_slot_after_the_owner_said_no_to_the_publish_question(client, plant, how):
    """Hard rule 4(g) on the refused branch of the publish gate (found by a verifier 2026-10-27: the page's next poll after the owner's
    no filed the skipped run). The line is taken to the question, the owner says no (the writer, or POST api/say 'Option 2', which
    is what the page sends), and the department is run a slot at a time with the whole page read between the slots."""
    ref, m = plant("question")
    pending = [a for a in m.W.asks(ref) if a["kind"] == "publish" and a["status"] == "pending"]
    assert len(pending) == 1, "the line ran to its question"
    if how == "decide_ask":
        m.W.decide_ask(ref, pending[0]["id"], False)
    else:
        r = client.post(url(ref, "api/say"), json={"text": "Option 2"})
        assert (r.status_code, r.json()) == (200, {"ok": True})
    assert [a["status"] for a in m.W.asks(ref) if a["kind"] == "publish"] == ["refused"]
    skipped = lambda: [r for r in m.W.runs(ref) if r.get("status") == "skipped" and r.get("what") == "refused by the owner"]  # noqa: E731
    assert skipped() == [], "the window: the owner said no and no tick has run"
    slots = read_to_rest(client, m, ref, "after the owner said no (%s)" % how)
    assert slots >= 1 and len(skipped()) == 1, "the tick filed the skipped run, once (%d slots)" % slots
    assert m.W.versions(ref, "Live site") == [], "refused by the owner: never published"


def test_t31_a_read_writes_nothing_at_any_slot_while_an_engine_is_held_at_its_limit(client, plant):
    """Hard rule 4(g) on Priority's gate (the module's own body since M5.4 files the card): Publish has no budget left, the owner stamps
    the publish question from the page, and the department is run a slot at a time with the whole page read between the slots. The
    card that says Publish is out of its envelope is the tick's, once."""
    ref, m = plant("question")
    m.W.set_envelope(ref, "Publish", calls=0)
    r = client.post(url(ref, "api/say"), json={"text": "Option 1"})
    assert (r.status_code, r.json()) == (200, {"ok": True})
    held = lambda: [a for a in m.W.asks(ref) if a["kind"] == "envelope"]  # noqa: E731
    assert held() == [], "the window: the owner stamped and no tick has run"
    slots = read_to_rest(client, m, ref, "while Publish is held at its limit")
    assert slots >= 1 and [(a["engine"], a["status"]) for a in held()] == [("Publish", "pending")], "the tick filed the card, once"
    s = client.get(url(ref, "api/state?since=0")).json()
    assert s["paused"] and "out of today's envelope" in json.dumps(s["paused"]), "and the page asks the owner"


def test_t32_every_act_between_functions_is_worded_for_the_owner_and_no_id_is_printed(client, plant):
    ref, m = plant("running")
    for i, act in enumerate(m.R.ACTS):
        thread(m, "Priority", "Adaptation", act, "line", tid="x-a%d" % i, words="the plan (%d)" % i)
        thread(m, "Audit", "Coordination", act, "finding", tid="x-b%d" % i, words="a page (%d)" % i)
    bodies = read_all(client, ref)
    texts = [x["text"] for x in bodies["state"]["chat"]]
    assert len(texts) == 2 * len(m.R.ACTS)
    for text in texts:
        assert not re.search(r"\b(?:accept-proposal|reject-proposal|not-understood)\b|\b[A-Z]{4,}\b", text), text
    assert "Said no to the plan: the plan (5)" in texts and "Asked Adaptation for less: the plan (3)" in texts
    check_words(bodies)
    check_page(ref, bodies, client)


def test_t32_a_path_of_this_machine_is_shortened_a_relative_path_and_a_date_are_not(client, plant):
    ref, m = plant("running")
    ask(m, "step", id="a-step", engine="Write", text="Write the page at /Users/me/work/site/index.html by hand; see build/v1/index.html on 5/6/2026",
        created=m.W.now())
    thread(m, "Priority", "Adaptation", "inform", "line", tid="x-r", words="no", reasoning="private thought", secret="s3cret", token="t0ken")
    text = json.dumps(client.get(url(ref, "api/state?since=0")).json())
    assert "at index.html by hand" in text and "build/v1/index.html on 5/6/2026" in text and "/Users" not in text
    assert "private thought" not in text and "s3cret" not in text and "t0ken" not in text


def test_t32_a_state_that_lost_a_key_is_caught_by_the_checks_themselves(client, plant, monkeypatch):
    import j2ui_state as S
    ref, m = plant("filed")
    whole = S.build_state

    def lacking(ctx, since=0):
        out = whole(ctx, since)
        del out["atoms_v1"]
        return out
    monkeypatch.setattr(S, "build_state", lacking)
    m.C.touch(ref)
    m.C.get_ctx(ref).memo.clear()
    with pytest.raises(AssertionError):
        everything(client, ref, m)


@pytest.mark.parametrize("name", ["pursuing_line", "ready"])
def test_t32_the_guards_of_rule_1_and_the_words_catch_what_they_guard(client, plant, name):
    """A guard that cannot fail guards nothing: real bodies of every JSON route are mutated one way at a time, and the checks must refuse."""
    import copy
    ref, m = plant(name)
    bodies = read_all(client, ref)
    check_state(bodies["state"])
    check_words(bodies)                                       # the real answers pass
    n_chat = len(bodies["state"]["chat"])
    others = [i for i, x in enumerate(bodies["state"]["chat"]) if x["who"] != "identity"]
    assert others and n_chat, "a department with messages from the functions to mutate"

    def mutated(fn):
        out = copy.deepcopy(bodies)
        fn(out)
        return out

    def set_key(key, value):
        return lambda b: b["state"]["chat"][others[0]].__setitem__(key, value)
    for label, fn in (("to_user on a function that is not Identity", set_key("to_user", True)),
                      ("next 'user' on one", set_key("next", "user")),
                      ("audience 'user' on one", set_key("audience", "user"))):
        with pytest.raises(AssertionError):
            check_state(mutated(fn)["state"])
        print("caught:", label)
    texts = list(R.ACTS) + ["FAILURE", "CANCEL", "act: cancel", "Said orders to Priority", "an order", "GRANT", "COUNTER", "REFUSE",
                            "/Users/someone/work/site/index.html", "C:\\Users\\someone\\site"]
    for text in texts:
        for route, where in (("state", lambda b, t: b["state"]["chat"][0].__setitem__("text", t)),
                             ("map", lambda b, t: b["map"]["not_recorded"].append(t)),
                             ("artifacts", lambda b, t: b["artifacts"]["deliverables"][0].__setitem__("form", t))):
            if route == "artifacts" and not bodies["artifacts"]["deliverables"]:
                continue
            with pytest.raises(AssertionError):
                check_words(mutated(lambda b: where(b, text)))
    for key in sorted(J.PRIVATE_KEYS)[:3]:
        with pytest.raises(AssertionError):
            check_words(mutated(lambda b: b["state"].__setitem__(key, "x")))
    for fine in ("Said no to the plan: the plan", "Asked Adaptation for less: the plan", "J2.b Propose", "an orderly line", "a reorder", "the request they made",
                 "the line's steps in sequence"):
        check_words(mutated(lambda b: b["state"]["chat"][0].__setitem__("text", fine)))


# ---- T3-4: the P1 cases ---------------------------------------------------------------------------------------------------
def test_t34_after_the_owner_follows_up_through_root_there_is_one_more_user_message_and_none_is_the_validators(client, plant):
    ref, m = plant("root_follow_up")
    chat = client.get(url(ref, "api/state?since=0")).json()["chat"]
    users = [x["text"] for x in chat if x["who"] == "user"]
    assert users == [SEED.WEBSITE, "Add a page about our pricing plans"], users
    assert not [x for x in chat if x["who"] == "validator" and ("pricing" in x["text"] or x["text"] == SEED.WEBSITE)]
    assert [x["who"] for x in chat if "pricing plans" in x["text"]] == ["user"], "the words Root hands on are not said again"
    first, again = [x["id"] for x in chat if x["who"] == "user"]
    assert first < again
    before = len(chat)
    r = client.post(url(ref, "api/say"), json={"text": "Make the logo bigger"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    m.W.run_until_idle(m.root, limit=300)
    m.W.run_until_idle(ref, limit=300)
    chat = client.get(url(ref, "api/state?since=0")).json()["chat"]
    assert [x["text"] for x in chat if x["who"] == "user"] == [SEED.WEBSITE, "Add a page about our pricing plans", "Make the logo bigger"]
    assert len(chat) > before and not [x for x in chat if x["who"] == "validator" and "logo" in x["text"]]


def test_t34_two_publish_asks_at_once_are_two_messages_and_paused_names_one(client, plant):
    ref, m = plant("two_publish_asks")
    assert [a["slot"] for a in m.W.asks(ref)] == ["Publish@build.v1", "Publish@build.v2"], "the asks are the ones the runtime files, one for each slot"
    for poll in (1, 2, 3):                                     # a poll, then two more that each rebuild the read at once (past C.MIN_REBUILD_S):
        if poll > 1:                                           # a write made by the first read would show as a third ask in the second
            m.C.touch(ref)
        s = client.get(url(ref, "api/state?since=0")).json()
        asks = [x for x in s["chat"] if x.get("act") == "ASK_REQUESTER"]
        assert len(asks) == 2 and len(s["chat"]) == 2 + len([x for x in s["chat"] if x.get("act") != "ASK_REQUESTER"]), \
            "no virtual third message (poll %d)" % poll
        assert asks[0]["id"] != asks[1]["id"] and s["paused"]["msg"] in (asks[0]["id"], asks[1]["id"])
        assert [x["text"].split("\n")[0] for x in asks] == ["@Requester Publish: go live, version 1", "@Requester Publish: go live, version 2"]
        assert s["paused"]["label"].endswith("(1 more waiting)"), s["paused"]["label"]
        assert [q["options"] for q in s["paused"]["questions"]] == [["Stamp", "Say no"]]
    assert len([a for a in m.W.asks(ref) if a["kind"] == "publish"]) == 2, "the reads filed no ask of their own"


def options_ask(m, first="leave:D2", ref=REF):
    """An options ask the way the runtime files one, with the option the runtime recommends first."""
    opts = {"words": m.W.option("words", "Change the plan in my words", "Adaptation shapes it afresh"),
            "leave:D2": m.W.option("leave:D2", "Leave D2 out", "D2 is dropped from done-when"),
            "stop": m.W.option("stop", "Stop here", "the department stops where it is")}
    order = [first] + [k for k in opts if k != first]
    a = m.W.options_ask("blocked", "The plan could not be set up: Check has no reader.", [opts[k] for k in order],
                        title="The plan could not be set up.", who="Root, setting up the engines", why="Check has no reader", thread="x-blocked",
                        cycle_id="cycle-test")
    m.W._put_ask(ref, a)
    card_post(m, a, ref=ref, objective=a["text"])
    return a


def test_t34_option_1_on_an_options_ask_chooses_it(client, plant):
    ref, m = plant("blocked")
    for a in m.W.asks(ref):                                   # the table's own card is replaced by one whose first option is a choice
        m.W._put_ask(ref, dict(a, status="replaced"))
    a = options_ask(m, first="leave:D2")
    s = client.get(url(ref, "api/state?since=0")).json()
    assert s["paused"]["kind"] == "limit" and s["paused"]["questions"][0]["options"][0].startswith("Leave D2 out")
    r = client.post(url(ref, "api/say"), json={"text": "Option 1"})
    assert (r.status_code, r.json()) == (200, {"ok": True})
    row = next(x for x in m.W.asks(ref) if x["id"] == a["id"])
    assert row["status"] == "chosen" and row["chosen"]["id"] == "leave:D2"


def test_t34_option_2_is_the_second_option_the_owner_was_shown_even_when_stop_came_back_into_the_list(client, plant):
    ref, m = plant("not_started")
    a = options_ask(m, first="stop", ref=ref)
    d = m.W.dept(ref)
    d["stopped"] = True                                        # the owner is shown the list without Stop
    m.W.save_dept(ref, d)
    shown = client.get(url(ref, "api/state?since=0")).json()
    assert [o.split(" (")[0] for o in shown["paused"]["questions"][0]["options"]] == ["Change the plan in my words", "Leave D2 out"]
    d["stopped"] = False                                       # and Stop is back in the live list, first
    m.W.save_dept(ref, d)
    assert [o["id"] for o in m.W.offered(m.W.dept(ref), m.W.asks(ref)[0])] == ["stop", "words", "leave:D2"]
    r = client.post(url(ref, "api/say"), json={"text": "Option 2"})
    assert r.status_code == 200, r.text
    row = next(x for x in m.W.asks(ref) if x["id"] == a["id"])
    assert row["status"] == "chosen" and row["chosen"]["id"] == "leave:D2", "the second shown, not the second live (which is the words option)"


def test_t34_a_stamp_is_option_1_and_what_identity_answers_comes_after_it(client, plant):
    ref, m = plant("question")
    s = client.get(url(ref, "api/state?since=0")).json()
    ask = next(x for x in s["chat"] if x.get("act") == "ASK_REQUESTER")
    assert "Option 1: Stamp" in ask["text"] and "Option 2: Say no" in ask["text"] and s["paused"]["msg"] == ask["id"]
    r = client.post(url(ref, "api/say"), json={"text": "Option 1"})
    assert (r.status_code, r.json()) == (200, {"ok": True})
    m.W.run_until_idle(ref, limit=300)
    s = client.get(url(ref, "api/state?since=0")).json()
    stamps = [x for x in s["chat"] if x["who"] == "user" and x["text"] == "Option 1"]
    live = next(x for x in s["chat"] if "is live" in x["text"])
    assert len(stamps) == 1 and ask["id"] < stamps[0]["id"] < live["id"]
    assert [a["status"] for a in m.W.asks(ref) if a["kind"] == "publish"] == ["stamped"]
    assert s["paused"] is None


def test_t34_option_3_on_a_two_option_ask_is_400_and_blank_words_are_400(client, plant):
    ref, m = plant("question")
    assert client.post(url(ref, "api/say"), json={"text": "Option 3"}).json() == {"error": "no such option"}
    assert client.post(url(ref, "api/say"), json={"text": "   "}).status_code == 400
    assert [a["status"] for a in m.W.asks(ref) if a["kind"] == "publish"] == ["pending"], "nothing was stamped"


def test_t34_the_three_posts_that_mean_nothing_leave_the_department_as_it_was(client, plant):
    ref, m = plant("filed")
    before = snapshot(m.home)
    assert client.post(url(ref, "api/reset")).status_code == 409
    assert client.post(url(ref, "api/output"), json={"type": "prd"}).status_code == 409
    assert client.post(url(ref, "api/playbooks/clear")).status_code == 409 and client.post(url(ref, "api/lessons/clear")).status_code == 409
    assert snapshot(m.home) == before


# ---- T3-5: honesty --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["filed", "ready"])
def test_t35_a_clean_reading_is_one_line_with_no_per_item_pass_and_no_workable_claim(client, plant, name):
    ref, m = plant(name)
    bodies = read_all(client, ref)
    s = bodies["state"]
    assert s["workable"] is None
    assert len(s["audits"]) == 1
    a = s["audits"][0]
    assert a["all_pass"] is True and a["results"] == [] and a["extra_issues"] == [] and a["rubric"] == [] and "found nothing to put right" in a["read"]
    text = json.dumps(s)
    assert "Workable (checked by code)" not in text and '"verdict": "PASS"' not in text and "NEEDS_REVISION" not in text
    got = H.run_harness(COPY, {k: bodies[k] for k in ("state", "map", "board", "artifacts", "docs", "audits", "refs", "runs", "preview")})
    pane = got["panes"]["pane-audit"]
    assert got["ok"] and pane
    seen = H.visible(pane)
    assert "Workable (checked by code)" not in seen and "Not workable yet" not in seen
    assert not re.search(r">\s*PASS\s*<", pane) and "PASS" not in seen, "no cell says a check passed that nobody made"
    assert "Audit read" in seen and "found nothing to put right" in seen
    assert s["conditions"] and all(c["evidence"].startswith(("Check engine", "Root's check")) for c in s["conditions"]), \
        "every condition says who recorded the check: the Check engine, or Root's check of the plan"


E1 = ("E1 of design/PRD-FIVE-FUNCTIONS-J2UI.md section 7, open: j2ui_audit._standards lists the standards Root's check ran on the PLAN (R-1 on) "
      "among the conditions the Audit tab heads 'Necessary conditions (checked by code, site v1)', so a check of the plan reads as a result "
      "for the site (D-HONEST: no invented result; a check is never a score). Ends when j2ui-work drops them from the conditions, or the "
      "owner rules that they belong there and the design record says so as a decision; then this marker is removed")


@pytest.mark.parametrize("name", ["filed", pytest.param("ready", marks=pytest.mark.xfail(strict=True, reason=E1)),
                                  pytest.param("question", marks=pytest.mark.xfail(strict=True, reason=E1))])
def test_t35_every_condition_is_the_check_engines_recorded_check_and_none_is_roots_check_of_the_plan(client, plant, name):
    """Mapping rule 14 of the plan: conditions are the Check engine's notes named as such. The claim above names a recorder for each
    (the Check engine, or Root's check); this is the plan's own, strict: a department whose plan Root checked (the real flow) lists its
    standards R-1 on as well, under the heading of the site's version. Strict expected failure until E1 is settled."""
    ref, m = plant(name)
    s = client.get(url(ref, "api/state?since=0")).json()
    assert s["conditions"], "the Check engine recorded a check"
    assert all(c["evidence"].startswith("Check engine") for c in s["conditions"]), [(c["id"], c["evidence"][:40]) for c in s["conditions"]][:4]


# ---- T3-6: scope ----------------------------------------------------------------------------------------------------------
def test_t36_a_default_department_a_root_the_first_build_and_a_stranger_are_404_on_every_route(client, plant, monkeypatch):
    ref, m = plant("default_kind")
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    m.W.create("dref-old1", "The first build", "x", kind="website")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME")
    for who in (ref, SEED.ROOT, "dref-old1", "dref-nobody", "%2E%2E"):
        for path in GET_ROUTES + ("", "j2host.js"):
            r = client.get(url(who, path))
            assert r.status_code == 404, (who, path, r.status_code)
            if r.headers["content-type"].startswith("application/json"):
                assert r.json() == {"error": "no such department"}, (who, path)
        for path in POST_ROUTES:
            r = client.post(url(who, path), json={"text": "hello"})
            assert r.status_code == 404 and r.json() == {"error": "no such department"}, (who, path)
    for odd in ("a%2Fb", "dref-nobody%00", "x" * 200):                  # a ref that is not even a ref never reaches a department
        assert client.get(url(odd, "api/state?since=0")).status_code == 404, odd


# ---- T3-7: the guard, the traversal, the headers ---------------------------------------------------------------------------
def test_t37_a_write_with_an_origin_and_no_panel_token_is_403_and_with_it_the_guard_lets_it_pass(client, plant):
    ref, m = plant("question")
    origin = {"Origin": "http://127.0.0.1:8330"}
    for path in POST_ROUTES:
        r = client.post(url(ref, path), json={"text": "Option 2"}, headers=origin)
        assert r.status_code == 403, path
    assert [a["status"] for a in m.W.asks(ref) if a["kind"] == "publish"] == ["pending"], "the guard stopped it before anything was said"
    token = client.get("/api/panel-token").json()["token"]
    assert client.post(url(ref, "api/say"), json={"text": "Option 2"}, headers=dict(origin, **{"X-Sutra-Panel": token})).status_code == 200
    assert client.post(url(ref, "api/say"), json={"text": "x"}, headers={"Origin": "http://evil.example", "X-Sutra-Panel": token}).status_code == 403


def test_t37_api_artifact_serves_only_a_file_it_lists_and_refuses_a_path_that_leaves_its_folder(client, plant):
    ref, m = plant("filed")
    listing = client.get(url(ref, "api/artifacts")).json()
    files = [r["file"] for r in listing["deliverables"] + listing["records"]]
    assert files
    for f in files:
        r = client.get(url(ref, "api/artifact"), params={"name": f})
        assert r.status_code == 200 and r.headers["content-type"].split(";")[0] in ("text/html", "text/plain", "text/markdown"), f
        for k, v in website_api.SAFE.items():
            assert r.headers[k.lower()] == v, (f, k)
    for bad in ("../../../../etc/passwd", "..%2F..%2Fdept.json", "/etc/passwd", "brief/../../../dept.json", "brief\\..\\dept.json", "dept.json", "",
                "j2-state.json", "../" + files[0], "brief/v1/../../v1/brief.md", "C:/Windows/win.ini", "brief/v1/brief.md\x00.png"):
        r = client.get(url(ref, "api/artifact"), params={"name": bad})
        assert r.status_code == 404 and r.text == "not found", (bad, r.status_code)
        assert "root" not in r.text.lower() or r.text == "not found"
    assert client.get(url(ref, "api/artifact")).status_code == 404


def test_t37_a_site_a_file_and_a_shot_carry_the_safe_headers_and_stay_inside_their_version(client, plant):
    ref, m = plant("filed")
    for path in ("site/latest", "site/v1", "site/1"):
        r = client.get(url(ref, path), follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith("/index.html"), path
        for k, v in website_api.SAFE.items():
            assert r.headers[k.lower()] == v, (path, k)
    home = client.get(url(ref, "site/v1/index.html"))
    assert home.status_code == 200 and "City Care Hospital" in home.text and "<style" in home.text, "css inlined"
    assert client.get(url(ref, "site/v1/about.html")).status_code == 200
    for path in ("site/v9/index.html", "site/v1/nothing.html", "site/v1/%2e%2e/%2e%2e/dept.json", "site/v1/..%2f..%2fdept.json", "file/prd.md", "shot/1"):
        r = client.get(url(ref, path))
        assert r.status_code == 404 and r.text == "not found", (path, r.status_code)
        for k, v in website_api.SAFE.items():
            assert r.headers[k.lower()] == v, (path, k)
    for path in ("file/..%2Fdept.json", "file/%2e%2e%2fdept.json", "shot/..%2Fdept", "shot/%2e%2e"):       # not even a route: still nothing of the record
        r = client.get(url(ref, path))
        assert r.status_code == 404 and "City Care" not in r.text and "cycle" not in r.text, path
    for k, v in website_api.SAFE.items():
        assert home.headers[k.lower()] == v
    ref2, m2 = plant("start")
    nothing = client.get(url(ref2, "site/latest"))
    assert nothing.status_code == 200 and "Your website will appear here once it's built." in nothing.text


def test_t31_the_map_keeps_its_steps_and_their_names_while_identity_asks_a_question(client, plant):
    """Identity's open question names no engine; website_dept.status once read one from every pending ask, so map_view raised and the
    Map lost its steps (found by this package on main cbb61740, mended by j2ui-views' fix 78170ba7). Pinned so it stays mended."""
    ref, m = plant("waiting")
    c = m.C.get_ctx(ref)
    assert c.reasons == [] and len(c.engines) == 4
    mp = client.get(url(ref, "api/map")).json()
    assert [n["label"] for n in mp["nodes"] if n["kind"] == "engine" and not n["id"].startswith("step:charter>")] == ["Plan", "Write", "Check", "Publish"]
