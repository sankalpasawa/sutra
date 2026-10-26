"""test_j2ui_artifacts.py -- the J2 page's Artifacts tab from a department's record (j2ui_artifacts.py; UIPORT j2ui-views M1).

Named claims:
  M1a  one row per artifact of the line that has a version, in line order, with the prototype's 17 keys (the row key set
       equals the captured prototype row when test_fixtures/j2ui/captured exists, else the list copied from
       j2_artifacts.listing); `open` within the prototype's OPEN values; `color` within the page's tokens
  M1b  the previewable artifact (Build) and the Live site are the deliverables, Brief, Site plan and Pages are records;
       no version, no row; the Pages record (JSON kept under an .html name) opens as text, not as a page
  M1c  the file of a row is `<slug>/v<N>/<primary>` of the latest version; the primary file is index.html, else the first
       .md, else the first file by name; the writing engine, what it reads and its sha256 are on the row
  M1d  served() serves only the file a row names, at most 2,000,000 bytes, html with its css inlined and text/plain for the
       rest; traversal, an unlisted file of a listed version and an oversize file are None; a stored <script> is returned
       unchanged (the header, not the body, makes it inert)
  M1e  nothing here writes, raises or leaks: the listing is the same twice and a broken record gives the empty shape

This file also holds the stand-in the four views are tested against until j2ui-core's Ctx is merged (make_ctx: the
contract's attributes, filled from a seeded department by public reads only), and the prototype loader the contract tests
share (proto_consts, proto_board, proto_show: git objects at the pinned commit, never the prototype's working tree; a test
that needs it skips with a printed reason when the repo or the commit is missing). test_j2ui_map.py, test_j2ui_board.py
and test_j2ui_site.py import them from here.
"""
import ast
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
REF = "dref-ju0001"
FUNCS = ("Identity", "Adaptation", "Priority", "Coordination", "Audit")
PIN = "f9ceba15192bbd6f62047cb7288d0f291b2fbc4f"
PROTO = Path(os.environ.get("J2_PROTOTYPE") or Path.home() / "Desktop" / "development" / "J2_Prototype")

#: the row keys of j2_artifacts.listing at the pin, copied (the captured prototype row is preferred when it exists)
ROW_KEYS = ["name", "type", "kind", "form", "file", "deliverable", "workflows", "depends_on", "version", "sha256", "time",
            "label", "tag", "color", "open", "depends_on_labels", "saved"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ---- the prototype, through git objects at the pin ------------------------------------------------------------------
def proto_show(name):
    """The text of one prototype file at the pinned commit, or None (printed) when the repo or the commit is missing."""
    try:
        from test_fixtures.j2ui import proto           # j2ui-core's loader, once it is merged
        return proto.show(name)
    except Exception:  # noqa: BLE001 -- not merged yet, or the prototype is missing: the local reader below
        pass
    try:
        out = subprocess.run(["git", "-C", str(PROTO), "show", "%s:%s" % (PIN, name)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        out = None
    if not out or out.returncode != 0:
        print("j2ui views: the prototype at %s is not here (set J2_PROTOTYPE), so %s is not compared" % (PIN[:7], name))
        return None
    return out.stdout


def proto_consts(name, const):
    """A module-level constant of a prototype file, read with ast (the files import code the tests must not run)."""
    src = proto_show(name)
    if src is None:
        return None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == const for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def proto_board():
    """The prototype's j2_board module, executed from its source (it imports only json, os and re), or None."""
    src = proto_show("j2_board.py")
    if src is None:
        return None
    ns = {"__name__": "j2_board_proto"}
    exec(compile(src, "j2_board.py", "exec"), ns)       # noqa: S102 -- a pure module of the pinned prototype
    return SimpleNamespace(**ns)


def proto_listing_keys():
    """The artifact row keys: the captured prototype row when it exists, else the copied list."""
    cap = HERE / "test_fixtures" / "j2ui" / "captured"
    if cap.is_dir():
        for p in sorted(cap.glob("*artifacts*.json")):
            rows = json.loads(p.read_text(encoding="utf-8"))
            rows = (rows.get("deliverables") or []) + (rows.get("records") or []) if isinstance(rows, dict) else rows
            if rows:
                return list(rows[0])
    return list(ROW_KEYS)


#: the 56 keys of api/state with their empty defaults (the page's poll() reads every one), for the page's own render
STATE = {"chat": [], "total": 0, "status": "idle", "thinking": None, "step": 0, "steps": {}, "goal": None, "stamped": False,
         "workflows": [], "budget": 0, "spent": 0, "conflicts": [], "audits": [], "versions": 0, "cycle": 0, "calls": 0, "error": None,
         "done": False, "atoms_v1": {}, "turn": None, "cycle_turns": 0, "max_turns": 30, "paused": None, "outcome": None, "style": None,
         "rubric": [], "playbooks": [], "playbooks_used": [], "playbook_saved": None, "mock": False, "model": "not recorded", "fixes": 1,
         "force_audit_fail": None, "test_lessons": False, "force_question": None, "has_board": False, "placeholders": [], "report": None,
         "sections": [], "write_lock": None, "agents": {}, "lanes": [], "call_log": [], "workable": None, "memory": False, "lessons": [],
         "lessons_used": [], "lessons_saved": [], "output": "website", "output_label": "Website", "doc": False, "conditions": None,
         "files": [], "docset": [], "docset_files": [], "saved": None}


def page_render(map_=None, artifacts=None, board=None, state=None):
    """The page's own renderMap, renderArtifacts and renderBoard over the adapter's output, run in node with the prototype's
    j2_ui_render.js and j2_ui.html at the pin: {'map': html, 'artifacts': html, 'board': html}. j2ui-shell's copies are
    used when they exist, else the git objects of the pin; None (printed) when node or the page is not here."""
    if not shutil.which("node"):
        print("j2ui views: node is not here, so the page's own render is not run")
        return None
    page = HERE / "j2ui_assets" / "j2_ui.html"
    harness = HERE / "test_fixtures" / "j2ui" / "j2_ui_render.js"
    html = page.read_text(encoding="utf-8") if page.is_file() else proto_show("j2_ui.html")
    js = harness.read_text(encoding="utf-8") if harness.is_file() else proto_show("j2_ui_render.js")
    if html is None or js is None:
        return None
    html = re.sub(r"""(["'`])/(api|site|file|shot)/""", r"\1\2/", html)        # the page as j2ui-shell serves it (S1)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "j2_ui.html").write_text(html, encoding="utf-8")
        (tmp / "j2_ui_render.js").write_text(js, encoding="utf-8")
        (tmp / "state.json").write_text(json.dumps(dict(STATE, **(state or {}))), encoding="utf-8")
        (tmp / "d.json").write_text(json.dumps({"map": map_ or {}, "artifacts": artifacts or {}, "board": board or []}), encoding="utf-8")
        out = subprocess.run(["node", str(tmp / "j2_ui_render.js"), str(tmp / "j2_ui.html"), str(tmp / "state.json"), "", str(tmp / "d.json")],
                             capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def plain_text(html):
    """The words of a rendered pane: tags and style blocks taken out."""
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", " ", html or "", flags=re.S)).split())


# ---- a department in a temp home --------------------------------------------------------------------------------------
@pytest.fixture
def mods(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    for var, sub in (("SUTRA_UI_PROPOSALS", "proposals"), ("SUTRA_UI_ROUTINES", "routines"), ("SUTRA_UI_RUNS", "runs")):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(var, str(tmp_path / sub))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import website_dept as W
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as F
    for m in (W, R, J, F):
        importlib.reload(m)
    W.create(REF, "City Care Hospital Website", None, kind="website")
    return W, R, J, F


def ago(s):
    return (datetime.now(timezone.utc) - timedelta(seconds=s)).astimezone().isoformat(timespec="seconds")


def set_cycle(W, state, step, **more):
    row = {"cycle_id": "cycle-test", "step": step, "journey": "J2", "state": state, "open_ask": None, "workflow": [],
           "repairs": 0, "updated_at": W.now()}
    row.update(more)
    W._write(W.ddir(REF) / "j2-state.json", row)


def put_ask(W, kind="publish", **more):
    row = {"id": more.pop("id", "a-" + kind), "kind": kind, "engine": more.pop("engine", "Publish"),
           "text": more.pop("text", "Publish: go live for the first time"), "status": "pending", "created": W.now()}
    row.update(more)
    W._put_ask(REF, row)
    return row


def put_run(W, engine, status="ok", what="Write a page", system=False, **more):
    row = {"id": more.pop("id", "r-" + engine.lower() + status), "engine": engine, "system": system,
           "slot": more.pop("slot", "%s@x.v1" % engine), "status": status, "started": more.pop("started", W.now()),
           "ended": None if status == "running" else more.pop("ended", W.now()), "what": what, "wrote": more.pop("wrote", None),
           "chain": None, "spend": more.pop("spend", {"calls": 0, "usd": 0.0}), "retries": 0}
    row.update(more)
    W._put_run(REF, row)
    return row


def put_post(W, R, src, dst, act, word, thread="x-t1", state="working"):
    """A thread on the board whose latest post is src's, as engine_runtime.post writes them."""
    n = len(R.board(REF)) + 1
    R._append(REF, "board.jsonl", {"n": n, "src": src, "dst": [dst], "msg_type": act, "thread": thread, "hop": 1, "about": None,
                                   "payload": {"word": word}, "ack_id": None, "by": None, "at": W.now()})
    ths = [t for t in R.threads(REF) if t["id"] != thread]
    ths.append({"id": thread, "opened_by": src, "with": [dst], "topic": word, "protocol": "propose" if act == "propose" else "inform",
                "decider": dst, "bounds": dict(R.BOUNDS), "default": "cancel", "state": state, "hops": 1, "spent": 0.0,
                "age_s": 0.0, "opened": W.now(), "closed": None, "outcome": None})
    R._save_threads(REF, ths)


def put_step(R, W, engine, step, ok=True, notes=None, status="ok", mode="slot", **more):
    """One step row, as the runtime appends them (steps.jsonl)."""
    row = {"engine": engine, "step": step, "mode": mode, "rung": "C2", "check": {"ok": ok, "notes": notes or []}, "answer": None,
           "usd": 0.0, "calls": 0, "ms": 5, "status": status, "started": W.now(), "ended": W.now()}
    row.update(more)
    R._append(REF, "steps.jsonl", row)
    return row


SITE_HTML = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Home</title>'
             '<link rel="stylesheet" href="style.css"></head><body><main><h1>City Care</h1>'
             '<a href="about.html">About</a></main></body></html>')
ABOUT_HTML = ('<!doctype html><html><head><meta charset="utf-8"><link href="style.css" rel="stylesheet"></head>'
              '<body><main><h1>About</h1></main></body></html>')
SEED = {
    "Brief": lambda n: {"brief.md": "A website for City Care Hospital. v%d" % n},
    "Site plan": lambda n: {"site-plan.json": json.dumps({"site_name": "City Care", "pages": [{"slug": "index", "title": "Home"}], "v": n})},
    "Pages": lambda n: {"index.html": json.dumps({"title": "Home", "body_html": "<h1>City Care v%d</h1>" % n}),
                        "_plan.json": json.dumps({"pages": [{"slug": "index"}]})},
    "Build": lambda n: {"index.html": SITE_HTML.replace("City Care", "City Care v%d" % n), "style.css": "body{color:#123}",
                        "about.html": ABOUT_HTML},
    "Live site": lambda n: {"index.html": SITE_HTML.replace("City Care", "City Care v%d" % n), "style.css": "body{color:#123}",
                            "about.html": ABOUT_HTML},
}


def add_ver(W, art, files=None, ok=True, notes=None, run=None, at=None):
    """A version of an artifact, written the way the department writes them (versions product), with the check as given:
    website_dept.add_version would fold the Library's own check in, and a test of the views wants the check it names."""
    import versions as VERS
    n = len(W.versions(REF, art)) + 1
    files = SEED[art](n) if files is None else files
    return VERS.add(W._abase(REF, art), files, [], run, {"ok": ok, "notes": notes if notes is not None else ["ok" if ok else "failed"]},
                    at or W.now())


def seed_line(W, upto=5, ok=True):
    """The first `upto` artifacts of the line each with one version (Brief ... Live site)."""
    for art in W.artifacts_of(W.dept(REF))[:upto]:
        add_ver(W, art, ok=ok)


# ---- the Ctx contract's stand-in (j2ui_common.get_ctx, built by j2ui-core) --------------------------------------------
def map_engines(W, R, F, ref):
    """(engines, planned) as website_dept.map_view gives them. map_view raises KeyError('engine') while Identity's question is
    open (website_dept.status reads a['engine'] of every pending ask and a j2_identity ask has none; found 2026-10-26 on
    main 827fe38f, reported to the integrator), so the same parts are read here one by one, as j2ui-core's get_ctx must."""
    d, rs, ak = W.dept(ref), W.runs(ref), W.asks(ref)
    engines = [x for x in (W.engine_view(ref, e[0]) for e in W.engines_of(d)) if x]
    table = R.coordination(ref)
    line = set(table.get("line") or [])
    left = {r.get("engine") for r in table.get("left_out") or [] if isinstance(r, dict)}
    slots = {r.get("engine"): r for r in table.get("timetable") or [] if isinstance(r, dict)}
    for e in engines:
        e.pop("runs", None)
        last = next((r for r in reversed(rs) if r["engine"] == e["name"]), None)
        e["last"] = last and {"status": last["status"], "at": last["started"], "what": last.get("what"), "words": last.get("words")}
        if any(a.get("engine") == e["name"] and a["status"] == "pending" for a in ak):
            e["state"] = "Waits"
        e["in_line"] = e["name"] in line
        if e["name"] in left and e["state"] not in ("Running", "Missing"):
            e["state"] = "Left out"
        e["timetable"] = slots.get(e["name"])
    return engines, not F.no_plan(ref, d, table)


def make_ctx(mods_, ref=REF, chat=None, paused=None):
    """The Ctx contract's attributes for a department, from public reads only. `chat` is the message list the test wants the
    views to see (the chat builder is j2ui-core's); `paused` forces the ask the state's paused shows."""
    W, R, J, F = mods_
    d = W.dept(ref)
    fv = F.functions(ref)
    cur = J._state(ref) or {}
    mv_engines, planned = map_engines(W, R, F, ref)
    mv = {"engines": mv_engines, "planned": planned}
    runs, asks = W.runs(ref), W.asks(ref)
    line = [e for e in mv["engines"] if e["in_line"]] if mv["planned"] else []
    left = [e for e in mv["engines"] if not e["in_line"]]
    wid = {e["name"]: "W-%d" % (i + 1) for i, e in enumerate(line + left)}
    engines = []
    for i, e in enumerate(mv["engines"]):
        engines.append({"k": i + 1, "wid": wid.get(e["name"]), "name": e["name"], "reads": e.get("reads"), "writes": e.get("writes"),
                        "runs_as": e.get("runs_as"), "in_line": e["in_line"], "state": e["state"], "env": e.get("envelope"),
                        "window_min": e.get("window_min"), "last": e.get("last"), "timetable": e.get("timetable"),
                        "steps_view": R.steps_view(ref, e["name"]), "runs": [r for r in runs if r["engine"] == e["name"]]})
    arts = [{"name": a, "slug": W.slug(a), "versions": W.versions(ref, a), "latest": (W.versions(ref, a) or [None])[-1]}
            for a in W.artifacts_of(d)]
    pend = [a for a in asks if a.get("status") == "pending"]
    q = J.open_question(ref)
    ctx = SimpleNamespace(
        ref=ref, kind=d["kind"], d=d, root_ref=d.get("root"), doc=False, stopped=bool(d.get("stopped")), fv=fv, cur=cur,
        state=(fv or {}).get("cycle", {}).get("state") or cur.get("state") or "not_started", runs=runs, asks=asks,
        posts=R.board(ref), root_posts=[], steps=R.step_rows(ref), events=[e for e in J.events(ref) if cur.get("cycle_id") and e.get("cycle_id") == cur["cycle_id"]],
        engines=engines, planned=mv["planned"], arts=arts, chat=list(chat or []), msg_of={}, ask_msg={}, ask_opts={},
        paused_ask=paused if paused is not None else (dict(q, kind="j2_identity") if q else (pend[0] if pend else None)),
        reasons=[], memo={})
    names = {"Owner": "user"}
    names.update({f: f.lower() for f in FUNCS})
    names.update({e["name"]: e["wid"] for e in engines if e["wid"]})
    ctx.wid = lambda name: wid.get(name)
    ctx.who = lambda src: names.get(src)
    ctx.fn_id = lambda name: "fn:" + str(name).lower() if name in FUNCS else None
    ctx.dest = lambda name: names.get(name)
    ctx.step_at = lambda iso: None
    return ctx


def msg(i, who, text, **more):
    """A chat message in the prototype's shape (id is its 1-based position)."""
    m = {"id": i, "t": "10:00:%02d" % (i % 60), "who": who, "text": text, "step": None}
    if who == "identity" and more.get("next", "user") == "user":         # to_user is Identity's alone, on a message to the owner
        m["to_user"] = True
    m.update(more)
    return m


@pytest.fixture
def ctx5(mods):
    """A department with all five artifacts filed and the Live site published."""
    seed_line(mods[0])
    return make_ctx(mods)


# ---- M1a: the rows ------------------------------------------------------------------------------------------------------
def test_m1a_one_row_per_artifact_with_a_version_in_line_order(mods):
    import j2ui_artifacts as A
    W = mods[0]
    for art in ("Brief", "Site plan", "Build"):
        add_ver(W, art)
    got = A.listing(make_ctx(mods))
    names = [r["name"] for r in got["deliverables"] + got["records"]]
    assert sorted(names) == ["Brief", "Build", "Site plan"]
    assert [r["name"] for r in got["records"]] == ["Brief", "Site plan"]       # line order
    assert [r["name"] for r in got["deliverables"]] == ["Build"]


def test_m1a_no_version_no_row(mods):
    import j2ui_artifacts as A
    assert A.listing(make_ctx(mods)) == {"deliverables": [], "records": []}


def test_m1a_row_keys_are_the_prototypes_seventeen(ctx5):
    import j2ui_artifacts as A
    got = A.listing(ctx5)
    rows = got["deliverables"] + got["records"]
    assert len(rows) == 5
    want = proto_listing_keys()
    assert len(want) == 17
    for r in rows:
        assert list(r) == want
        assert list(r) == list(A.ROW_KEYS)


def test_m1a_open_color_and_form_stay_in_the_pages_vocabulary(ctx5):
    import j2ui_artifacts as A
    got = A.listing(ctx5)
    opens = proto_consts("j2_artifacts.py", "OPEN")
    allowed_open = set((opens or A.OPEN).values())
    for r in got["deliverables"] + got["records"]:
        assert r["open"] in allowed_open and r["open"] in ("text", "preview")        # this adapter makes no image rows
        assert r["color"] in {"--prd", "--hld", "--lld", "--site", "--other"}
        assert r["form"] in ("page", "doc", "data")
        assert r["open"] == A.OPEN[r["form"]]
        assert r["saved"] is True and r["label"] == r["name"]
        assert isinstance(r["time"], str) and re.fullmatch(r"[0-9a-f]{64}", r["sha256"])
    if opens:
        assert A.OPEN == opens


# ---- M1b: the split -------------------------------------------------------------------------------------------------------
def test_m1b_build_and_live_site_are_the_deliverables(ctx5):
    import j2ui_artifacts as A
    got = A.listing(ctx5)
    assert [r["name"] for r in got["deliverables"]] == ["Build", "Live site"]
    assert [r["name"] for r in got["records"]] == ["Brief", "Site plan", "Pages"]
    assert all(r["kind"] == "type" and r["deliverable"] is True for r in got["deliverables"])
    assert all(r["kind"] == "record" and r["deliverable"] is False for r in got["records"])
    assert [r["tag"] for r in got["deliverables"]] == ["Site", "Site"]
    assert [r["color"] for r in got["deliverables"]] == ["--site", "--site"]
    assert {r["tag"] for r in got["records"]} == {"Other"}


def test_m1b_before_publish_only_build_is_a_deliverable(mods):
    import j2ui_artifacts as A
    seed_line(mods[0], upto=4)
    got = A.listing(make_ctx(mods))
    assert [r["name"] for r in got["deliverables"]] == ["Build"]
    assert len(got["records"]) == 3


def test_m1b_without_a_build_the_last_artifact_is_previewable(mods):
    import j2ui_artifacts as A
    ctx = make_ctx(mods)
    assert A.previewable(ctx) == "Build"
    ctx.arts = [a for a in ctx.arts if a["name"] != "Build"]
    assert A.previewable(ctx) == "Live site"
    ctx.arts = []
    assert A.previewable(ctx) == ""


def test_m1b_the_pages_record_opens_as_text(ctx5):
    import j2ui_artifacts as A
    pages = next(r for r in A.listing(ctx5)["records"] if r["name"] == "Pages")
    assert pages["file"] == "pages/v1/index.html"
    assert (pages["form"], pages["open"], pages["tag"]) == ("data", "text", "Other")
    data, mime = A.served(ctx5, pages["file"])
    assert mime == "text/plain" and json.loads(data)["title"] == "Home"


# ---- M1c: the file and the rest of the row -----------------------------------------------------------------------------
def test_m1c_file_is_slug_version_primary_of_the_latest_version(ctx5, mods):
    import j2ui_artifacts as A
    W = mods[0]
    add_ver(W, "Build")                      # a second version: the row follows the latest
    got = A.listing(make_ctx(mods))
    build = next(r for r in got["deliverables"] if r["name"] == "Build")
    assert build["file"] == "build/v2/index.html" and build["version"] == 2
    site_plan = next(r for r in got["records"] if r["name"] == "Site plan")
    assert site_plan["file"] == "site-plan/v1/site-plan.json" and site_plan["type"] == "site-plan"
    assert next(r for r in got["records"] if r["name"] == "Brief")["file"] == "brief/v1/brief.md"


def test_m1c_primary_is_index_then_first_md_then_first_name():
    import j2ui_artifacts as A
    assert A.primary({"b.html": "x", "index.html": "x", "a.md": "x"}) == "index.html"
    assert A.primary({"z.json": "x", "b.md": "x", "a.md": "x"}) == "a.md"
    assert A.primary({"z.json": "x", "m.css": "x"}) == "m.css"
    assert A.primary({}) == ""


def test_m1c_forms():
    import j2ui_artifacts as A
    assert A.form_of("index.html", "<!doctype html>") == "page"
    assert A.form_of("brief.md", "x") == "doc" and A.form_of("notes.txt", "x") == "doc"
    assert A.form_of("plan.json", "{}") == "data"
    assert A.form_of("index.html", '{"title": "x"}') == "data"          # data kept under an .html name


def test_m1c_writer_reader_and_sha(ctx5, mods):
    import j2ui_artifacts as A
    W = mods[0]
    got = A.listing(ctx5)
    by = {r["name"]: r for r in got["deliverables"] + got["records"]}
    assert by["Brief"]["workflows"] == [] and by["Brief"]["depends_on"] == [] and by["Brief"]["depends_on_labels"] == []
    assert by["Site plan"]["workflows"] == ["W-1"] and by["Site plan"]["depends_on"] == ["brief"]
    assert by["Site plan"]["depends_on_labels"] == ["Brief"]
    assert by["Pages"]["workflows"] == ["W-2"] and by["Pages"]["depends_on"] == ["site-plan"]
    assert by["Build"]["workflows"] == ["W-3"] and by["Build"]["depends_on_labels"] == ["Pages"]
    assert by["Live site"]["workflows"] == ["W-4"] and by["Live site"]["depends_on_labels"] == ["Build"]
    want = hashlib.sha256(W.read_files(REF, "Brief", 1)["brief.md"].encode("utf-8")).hexdigest()
    assert by["Brief"]["sha256"] == want
    assert by["Brief"]["time"] == W.versions(REF, "Brief")[-1]["at"]


def test_m1c_dependency_on_an_artifact_with_no_version_is_left_out(mods):
    import j2ui_artifacts as A
    add_ver(mods[0], "Site plan")                       # the Brief it reads was never filed
    row = A.listing(make_ctx(mods))["records"][0]
    assert row["name"] == "Site plan" and row["depends_on"] == [] and row["depends_on_labels"] == []


def test_m1c_an_engine_the_plan_left_out_still_names_its_workflow(mods):
    import j2ui_artifacts as A
    seed_line(mods[0], upto=3)
    ctx = make_ctx(mods)
    for e in ctx.engines:
        if e["name"] == "Write":
            e["wid"], e["in_line"] = "W-4", False
    pages = next(r for r in A.listing(ctx)["records"] if r["name"] == "Pages")
    assert pages["workflows"] == ["W-4"]


def test_m1c_tag_of():
    import j2ui_artifacts as A
    assert A.tag_of("Build", "index.html") == ("Site", "--site")
    assert A.tag_of("Live site", "index.html") == ("Site", "--site")
    assert A.tag_of("Live site", "notes.md") == ("Other", "--other")
    assert A.tag_of("Brief", "brief.md") == ("Other", "--other")
    assert A.tag_of("Pages", "index.html") == ("Other", "--other")
    assert A.tag_of("Pages", "index.html", "Pages") == ("Site", "--site")       # the previewable artifact of another line


# ---- M1d: what may be served ------------------------------------------------------------------------------------------------
def test_m1d_a_listed_file_is_served_and_the_html_has_its_css_inlined(ctx5):
    import j2ui_artifacts as A
    data, mime = A.served(ctx5, "build/v1/index.html")
    html = data.decode("utf-8")
    assert mime == "text/html"
    assert "<style>body{color:#123}</style>" in html and "<link" not in html
    data, mime = A.served(ctx5, "brief/v1/brief.md")
    assert mime == "text/plain" and data.decode("utf-8").startswith("A website for City Care Hospital")
    data, mime = A.served(ctx5, "site-plan/v1/site-plan.json")
    assert mime == "text/plain" and json.loads(data)["site_name"] == "City Care"


@pytest.mark.parametrize("name", ["../dept.json", "/etc/passwd", "build/v1/../../dept.json", "build\\v1\\index.html", "%2e%2e/x",
                                  "build/v1/about.html", "build/v1/style.css", "build/v2/index.html", "build/v1/", "build", "",
                                  "build/v1/index.html\x00", "brief/v1/../v1/brief.md", ".", "..", "dept.json", "asks.json",
                                  "//etc/passwd", "build/v1/index.html/../../../dept.json"])
def test_m1d_anything_not_listed_is_none(ctx5, name):
    import j2ui_artifacts as A
    assert A.served(ctx5, name) is None


def test_m1d_not_a_string_is_none(ctx5):
    import j2ui_artifacts as A
    for bad in (None, 7, ["build/v1/index.html"], {"a": 1}, b"build/v1/index.html"):
        assert A.served(ctx5, bad) is None


def test_m1d_an_oversize_file_is_none(mods):
    import j2ui_artifacts as A
    W = mods[0]
    add_ver(W, "Brief", {"brief.md": "x" * (A.MAX_BYTES + 1)})
    add_ver(W, "Site plan", {"site-plan.json": "y" * A.MAX_BYTES})
    ctx = make_ctx(mods)
    assert A.served(ctx, "brief/v1/brief.md") is None
    data, mime = A.served(ctx, "site-plan/v1/site-plan.json")
    assert len(data) == A.MAX_BYTES and mime == "text/plain"


def test_m1d_a_stored_script_is_returned_unchanged(mods):
    import j2ui_artifacts as A
    page = '<!doctype html><html><body><script>alert(1)</script><p>hi</p></body></html>'
    add_ver(mods[0], "Build", {"index.html": page, "style.css": "p{}"})
    data, mime = A.served(make_ctx(mods), "build/v1/index.html")
    assert data.decode("utf-8") == page and mime == "text/html"


def test_m1d_inline_css_either_attribute_order_and_when_absent():
    import j2ui_artifacts as A
    files = {"index.html": '<head><link href="style.css" rel="stylesheet"></head>', "a.html": "<head><link rel='stylesheet' href='style.css'/></head>",
             "b.html": "<head><title>x</title></head>", "c.html": '<head><link rel="icon" href="style.css"></head>',
             "d.html": '<head><link rel="stylesheet" href="other.css"></head>', "style.css": "a{}"}
    assert A.inline_css(files, "index.html") == "<head><style>a{}</style></head>"
    assert A.inline_css(files, "a.html") == "<head><style>a{}</style></head>"
    for n in ("b.html", "c.html", "d.html"):
        assert A.inline_css(files, n) == files[n]                          # the document is left alone
    assert A.inline_css({"index.html": "<link rel=stylesheet href=style.css>"}, "index.html") == "<link rel=stylesheet href=style.css>"
    assert A.inline_css(files, "missing.html") == ""


def test_m1d_the_css_cannot_close_its_own_tag():
    import j2ui_artifacts as A
    out = A.inline_css({"index.html": '<link rel="stylesheet" href="style.css">', "style.css": "a{}</style><script>x</script>"}, "index.html")
    assert out.count("</style>") == 1 and "<\\/style><script>" in out


# ---- M1e: reads only, never raises ----------------------------------------------------------------------------------------
def test_m1e_the_listing_is_the_same_twice_and_writes_nothing(ctx5, mods):
    import j2ui_artifacts as A
    W = mods[0]
    before = sorted((str(p.relative_to(W.ddir(REF))), p.stat().st_mtime_ns) for p in W.ddir(REF).rglob("*") if p.is_file())
    a = json.dumps(A.listing(ctx5), sort_keys=True)
    ctx2 = make_ctx(mods)
    assert json.dumps(A.listing(ctx2), sort_keys=True) == a
    assert A.listing(ctx5) is A.listing(ctx5)                              # memoised on ctx.memo
    after = sorted((str(p.relative_to(W.ddir(REF))), p.stat().st_mtime_ns) for p in W.ddir(REF).rglob("*") if p.is_file())
    assert before == after


def test_m1e_a_broken_record_gives_the_empty_shape_and_a_reason(ctx5):
    import j2ui_artifacts as A
    ctx5.arts = [{"name": "Build", "slug": "build", "versions": [{"v": "x"}]}]
    ctx5.engines = None
    ctx5.memo = {}
    ctx5.ref = None                                                          # read_files on no department
    got = A.listing(ctx5)
    assert got == {"deliverables": [], "records": []} and ctx5.reasons
    assert A.served(ctx5, "build/vx/index.html") is None


def test_m1e_a_bare_stand_in_without_memo_or_reasons_does_not_raise(mods):
    import j2ui_artifacts as A
    seed_line(mods[0], upto=2)
    ctx = make_ctx(mods)
    bare = SimpleNamespace(ref=ctx.ref, arts=ctx.arts, engines=ctx.engines)
    assert len(A.listing(bare)["records"]) == 2
    assert A.served(bare, "brief/v1/brief.md")[1] == "text/plain"


def test_m1e_nothing_leaks(ctx5):
    import j2ui_artifacts as A
    blob = json.dumps(A.listing(ctx5))
    assert not re.search(r"(?:~|\b[A-Za-z]:)?(?:/[\w.@-]+){3,}", blob.replace("build/v1/index.html", ""))
    assert not re.search(r"GRANT|COUNTER|REFUSE|accept-proposal|reject-proposal", blob)
    assert "private" not in blob


def test_m1e_real_ctx_when_core_is_merged(mods):
    """j2ui-core's get_ctx feeds the same listing as the stand-in (skipped until j2ui_common exists)."""
    C = pytest.importorskip("j2ui_common", reason="j2ui-core is not merged yet")
    import j2ui_artifacts as A
    seed_line(mods[0])
    C.reset_caches()
    a = A.listing(C.get_ctx(REF))
    b = A.listing(make_ctx(mods))
    assert [r["file"] for r in a["deliverables"] + a["records"]] == [r["file"] for r in b["deliverables"] + b["records"]]
