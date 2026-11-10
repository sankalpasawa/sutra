"""The 30 handlers of J2's server as functions (`views.py`) and the stdlib adapter over them (`j2_server.py`), work package E2,
engine design 4.6, 7.1 and 9 [S3-web-07]. J2 runs in mock mode with its Chrome checks faked (as J2's own `--fast` flow does):
a whole Brew Lab run takes about a tenth of a second, so two real runs (a website and a PRD) are the fixtures.

The golden file `golden/api_shapes.json` was recorded from J2 itself (`scripts/record_api_shapes.py`): per route the status,
the content type and the key paths of a JSON body, in three situations (live, saved, idle). The stdlib adapter is asked the same
questions and must give the same shapes, except for the keys the engine adds on purpose (the allow-list in the recorder)."""
import contextlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
              "j2_check", "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_studio", "j2_template_lib",
              "rehydrate", "views", "j2_server")
GOLD = json.loads((REPO / "tests" / "engine" / "golden" / "api_shapes.json").read_text(encoding="utf-8"))
SITE_ID, PRD_ID = "j2-20261104-100004-7f3a", "j2-20261104-100005-7f3a"
PRD_BRIEF = ("Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: "
             "patients at small clinics and the front-desk staff who manage the line. Problem: patients wait 45 minutes on "
             "average in crowded waiting rooms. Must-have features: join the queue from a phone, live position updates, SMS "
             "alert when 2 patients are ahead, staff dashboard to call the next patient. Constraints: works on low-end "
             "Android phones; no patient health data stored. Success: average in-room wait under 10 minutes; 60% of "
             "patients join remotely within 3 months.")
NAMES = {"index", "vendor", "state", "runs", "call", "preview", "docs", "map", "plan", "library", "library_item", "run_templates",
         "artifacts", "agent", "code", "artifacts_tree", "artifact", "story", "board", "audits", "refs", "shot", "file", "site",
         "say", "playbooks_clear", "lessons_clear", "output", "reset", "runlist", "changes"}         # the last two: patch P13


def load_recorder():
    spec = importlib.util.spec_from_file_location("record_api_shapes", REPO / "scripts" / "record_api_shapes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = load_recorder()


# ---- a fresh import of the vendored J2 and of the views (they read flags and paths when imported) ----------------------
@contextlib.contextmanager
def fresh_engine(base: Path):
    from sutra_app.engine import llm
    package = importlib.import_module(ENGINE)
    saved = {name: (sys.modules.pop(f"{ENGINE}.{name}", None), package.__dict__.pop(name, None)) for name in J2_MODULES}
    with pytest.MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_")):
                mp.delenv(name)
        for key, value in {**rec.SCENARIO_ENV, "J2_RUNS_DIR": base / "runs", "J2_MEMORY_FILE": base / "memory" / "lessons.jsonl",
                           "J2_PLAYBOOK_FILE": base / "memory" / "playbooks.jsonl", "J2_LIBRARY_DIR": base / "library"}.items():
            mp.setenv(key, str(value))
        for name in ("_PORT", "_DEFAULT_PORT", "_BASE_TAG", "_BOUND_ATOM", "MOCK", "PROVIDER", "MODEL"):
            mp.setattr(llm, name, getattr(llm, name))          # put back when the module is done
        llm.configure(mock=True)
        try:
            mods = SimpleNamespace(**{name: importlib.import_module(f"{ENGINE}.{name}") for name in ("j2", "views", "j2_server")})
            rec.fake_chrome(mods.j2.j2_check)
            yield mods
        finally:
            for name, (old, attr) in saved.items():
                sys.modules.pop(f"{ENGINE}.{name}", None)
                package.__dict__.pop(name, None)
                if old is not None:
                    sys.modules[f"{ENGINE}.{name}"] = old
                if attr is not None:
                    package.__dict__[name] = attr


def finish(run, text, timeout=60.0):
    assert run.user_says(text) is True
    deadline = time.time() + timeout
    while run.status != "waiting":
        assert time.time() < deadline, "the run did not stop"
        time.sleep(0.003)


class Server:
    """The stdlib adapter on a free port."""

    def __init__(self, mod):
        self.srv = mod.http.server.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def ask(self, method, path, body=None, raw=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(self.base + path, data, {"Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read()

    def json(self, path):
        return json.loads(self.ask("GET", path)[2])


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    base = tmp_path_factory.mktemp("views")
    shutil.copytree(REPO / "sutra_app" / "engine" / "seed" / "library", base / "library")
    with fresh_engine(base) as mods:
        site = mods.j2.J2Run(run_dir=base / "runs" / SITE_ID)
        finish(site, rec.BREW_LAB)
        assert site.outcome.startswith("Done"), site.outcome
        prd = mods.j2.J2Run(run_dir=base / "runs" / PRD_ID)
        prd.set_output("prd")
        finish(prd, PRD_BRIEF)
        assert prd.outcome.startswith("Done"), prd.outcome
        server = Server(mods.j2_server)
        yield SimpleNamespace(j2=mods.j2, views=mods.views, j2_server=mods.j2_server, base=base, runs_dir=base / "runs", site=site,
                              prd=prd, server=server, memory=mods.views.MemoryPaths(str(base / "memory" / "lessons.jsonl"),
                                                                                    str(base / "memory" / "playbooks.jsonl")))
        server.srv.shutdown()


# ---- helpers -----------------------------------------------------------------------------------------------------------
class FakeCommands:
    """The three POSTs, recorded."""

    def __init__(self, say=True, accept=True, reset=True, output="website"):
        self.results = {"say": say, "accept": accept, "reset": reset}
        self.output, self.calls = output, []

    def say(self, text):
        self.calls.append(("say", text))
        return self.results["say"]

    def set_output(self, out):
        self.calls.append(("set_output", out))
        return self.results["accept"], self.output

    def reset(self):
        self.calls.append(("reset",))
        return self.results["reset"]


def live_ctx(w, run, **kw):
    snap, live = w.views.live_state(run)
    name = os.path.basename(run.dir)
    return w.views.RunCtx("live", name, run.dir, str(w.runs_dir), name, w.memory, snap=snap, extras=live, **kw)


def saved_ctx(w, run_id, folder="runs"):
    d = w.base / folder / run_id
    return w.views.RunCtx("saved", run_id, str(d) if d.is_dir() else None, str(w.base / folder), SITE_ID, w.memory)


def idle_ctx(w, **kw):
    snap = w.views.idle_snapshot(w.views.EngineSettings(), w.memory, "j2-idle")
    return w.views.RunCtx("idle", None, None, str(w.runs_dir), None, w.memory, snap=snap, **kw)


def call(w, view, ctx, **q):
    return w.views.VIEWS[view](ctx, q)


def jbody(reply):
    assert reply.ctype == "application/json", reply
    return json.loads(reply.body)


def text_of(reply):
    return reply.body.decode("utf-8") if isinstance(reply.body, bytes) else reply.body


# ---- the golden file ---------------------------------------------------------------------------------------------------
def test_the_golden_was_recorded_from_j2_at_the_baseline_commit():
    assert GOLD["schema"] == rec.SCHEMA and GOLD["j2_commit"].startswith("33aeeda")
    assert set(GOLD["get"]) == {"live", "saved", "idle"} and len(GOLD["get"]["live"]) == 30 == len(rec.ROUTES)
    assert set(GOLD["post"]) == set(rec.POSTS)


def test_the_golden_has_the_template_copy_keys_of_the_j2_sync():
    keys = GOLD["get"]["live"]
    assert {"decisions[].source", "decisions[].saved"} <= set(keys["run_templates"]["keys"])
    assert {"source", "saved"} <= set(keys["library_item"]["keys"])
    assert GOLD["get"]["idle"]["run_templates"]["keys"] == ["decisions"]


def test_key_paths_collapse_maps_and_skip_opaque_values():
    value = {"a": {"x1": {"k": 1}, "x2": {"k": 2}}, "list": [{"p": 1}, {"q": 2}], "reply": {"free": 1}, "n": []}
    assert rec.key_paths(value, maps={"a"}, opaque={"reply"}) == ["a", "a.*", "a.*.k", "list", "list[].p", "list[].q", "n", "reply"]
    assert rec.key_paths([{"id": 1}]) == ["[].id"]


def shape_problems(w, mode, run, run_q):
    """Ask the adapter every question the recorder asked J2 and list what differs from the golden."""
    srv = w.server
    probe = w.j2_server.RUN
    w.j2_server.RUN = w.site
    try:
        state, tree, lib, arts = (srv.json(p) for p in ("/api/state", "/api/artifacts/tree", "/api/library", "/api/artifacts"))
        decisions = srv.json("/api/run-templates")["decisions"]
    finally:
        w.j2_server.RUN = probe
    paths = rec.paths_for(state, tree, lib, arts, run_q, decisions)
    w.j2_server.RUN = run
    problems = []
    try:
        for name, path in paths.items():
            got, gold = rec.shape(*srv.ask("GET", path)), GOLD["get"][mode][name]
            if (got["status"], got["ctype"]) != (gold["status"], gold["ctype"]):
                problems.append(f"{name}: {got['status']} {got['ctype']} instead of {gold['status']} {gold['ctype']}")
            missing = set(gold.get("keys", ())) - set(got.get("keys", ()))
            extra = set(got.get("keys", ())) - set(gold.get("keys", ())) - rec.ADDITIVE.get(name, set())
            if missing or extra:
                problems.append(f"{name}: missing {sorted(missing)[:6]} extra {sorted(extra)[:6]}")
    finally:
        w.j2_server.RUN = probe
    return problems


def test_every_get_route_of_a_live_run_has_the_shape_j2_gave(w):
    assert shape_problems(w, "live", w.site, "") == []


def test_every_get_route_of_a_saved_run_has_the_shape_j2_gave(w):
    assert shape_problems(w, "saved", w.site, f"run={SITE_ID}") == []


def test_every_get_route_of_an_idle_run_has_the_shape_j2_gave(w):
    assert shape_problems(w, "idle", w.j2.J2Run(), "") == []


def test_every_post_route_has_the_shape_j2_gave(w, monkeypatch, tmp_path):
    monkeypatch.setattr(w.j2, "RUNS_DIR", str(tmp_path / "runs"))        # the run it starts is not one of the module's
    monkeypatch.setattr(w.j2_server, "RUN", w.j2.J2Run())
    monkeypatch.setattr(w.j2, "MEMORY_FILE", str(w.base / "none-l.jsonl"))
    monkeypatch.setattr(w.j2, "PLAYBOOK_FILE", str(w.base / "none-p.jsonl"))
    post = lambda path, body: rec.shape(*w.server.ask("POST", path, body))        # noqa: E731
    got = {"output_prd": post("/api/output", {"type": "prd"}), "say_empty": post("/api/say", {"text": "  "})}
    w.j2_server.RUN.set_output("website")
    got["say"] = post("/api/say", {"text": rec.BREW_LAB})
    deadline = time.time() + 60
    while w.j2_server.RUN.status != "waiting" and time.time() < deadline:
        time.sleep(0.01)
    got.update(output_late=post("/api/output", {"type": "website"}), playbooks_clear=post("/api/playbooks/clear", {}),
               lessons_clear=post("/api/lessons/clear", {}), reset=post("/api/reset", {}))
    assert got == GOLD["post"]


@pytest.mark.skipif(not os.environ.get("SUTRA_J2_CHECKOUT"), reason="set SUTRA_J2_CHECKOUT to a J2 checkout to re-record")
def test_the_recorder_reproduces_the_golden_from_a_j2_checkout():
    assert rec.main(["--source", os.environ["SUTRA_J2_CHECKOUT"], "--check"]) == 0


# ---- the registry ------------------------------------------------------------------------------------------------------
def test_the_views_are_the_thirty_handlers_of_the_design(w):
    v = w.views
    assert set(v.VIEWS) == NAMES and all(callable(f) for f in v.VIEWS.values())
    assert v.VIEWS["site"] is v.site and callable(v.site_saved) and callable(v.site_live)
    assert v.HANDLER_COUNT == 30 == len(v.VIEWS) - len(v.PATCH_VIEWS) - 1 + 2          # "site" has two rows (saved and live), one entry
    assert v.LIVE_VIEWS <= set(v.VIEWS)


# ---- publishing: live_state, read_published, idle_snapshot ------------------------------------------------------------
def test_live_state_builds_the_snapshot_and_the_live_dict_of_a_run(w):
    snap, live = w.views.live_state(w.site)
    assert snap == {**w.site.snapshot(0), "saved": None} and len(snap) == 57 and len(w.site.snapshot(0)) == 56
    assert set(live) == {"schema", "pid", "at", "output", "doc", "out_label", "docset", "stages", "stage_i", "docs", "board",
                         "site_tag", "sites"}
    assert live["schema"] == "engine-live/1" and live["pid"] == os.getpid() and live["sites"] == len(w.site.sites) > 0
    assert (live["output"], live["doc"], live["out_label"]) == ("website", False, "Website")
    json.dumps(snap), json.dumps(live)
    prd = w.views.live_state(w.prd)[1]
    assert (prd["output"], prd["doc"], prd["docset"]) == ("prd", True, ["prd"]) and prd["docs"] and prd["stages"] == ["prd"]


def test_read_published_reads_both_files_and_the_pid(w, tmp_path):
    assert w.views.read_published(tmp_path) is None
    (tmp_path / "snapshot.json").write_text("{torn", encoding="utf-8")
    assert w.views.read_published(tmp_path) is None, "a torn snapshot reads as none"
    (tmp_path / "snapshot.json").write_text('{"status": "running"}', encoding="utf-8")
    pub = w.views.read_published(tmp_path)
    assert (pub.snap, pub.live, pub.alive) == ({"status": "running"}, {}, True), "no live.json: nothing says it is gone"
    (tmp_path / "live.json").write_text(json.dumps({"pid": os.getpid(), "sites": 2}), encoding="utf-8")
    pub = w.views.read_published(tmp_path)
    assert pub.live == {"pid": os.getpid(), "sites": 2} and pub.alive is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    (tmp_path / "live.json").write_text(json.dumps({"pid": child.pid}), encoding="utf-8")
    assert w.views.read_published(tmp_path).alive is False
    (tmp_path / "snapshot.json").write_text("[1]", encoding="utf-8")
    assert w.views.read_published(tmp_path) is None, "a snapshot that is not an object is none"


def test_idle_snapshot_has_the_keys_of_a_fresh_j2_snapshot(w):
    fresh = w.j2.J2Run().snapshot(0)
    idle = w.views.idle_snapshot(w.views.EngineSettings(), w.memory, "j2-idle")
    assert set(idle) == set(fresh) and len(idle) == 56
    assert idle["chat"] == [] and idle["status"] == "idle" and idle["output"] == "website"


def test_idle_snapshot_overlays_the_departments_settings_and_restores_j2s_globals(w, tmp_path, monkeypatch):
    lessons, playbooks = tmp_path / "lessons.jsonl", tmp_path / "playbooks.jsonl"
    lessons.write_text('{"id": "L1"}\nnot json\n{"id": "L2"}\n', encoding="utf-8")
    playbooks.write_text('{"id": "P1"}\n', encoding="utf-8")
    memory = w.views.MemoryPaths(str(lessons), str(playbooks))
    monkeypatch.delenv("STUDIO_MOCK")
    rates, output = w.j2.RATES, w.j2.OUTPUT
    settings = w.views.EngineSettings(output="prd", fixes=1, budget=50, memory=True)
    snap = w.views.idle_snapshot(settings, memory, "j2-idle")
    assert (snap["output"], snap["output_label"], snap["doc"], snap["fixes"], snap["budget"]) == ("prd", "PRD document", True, 1, 50)
    assert snap["memory"] is True and snap["lessons"] == [{"id": "L1"}, {"id": "L2"}] and snap["playbooks"] == [{"id": "P1"}]
    assert snap["rubric"][0][0] == "D-1" and snap["model"] is None and snap["mock"] is False
    assert w.j2.RATES is rates and w.j2.OUTPUT == output, "the throw-away run must not leave its output and rate card behind"
    off = w.views.idle_snapshot(w.views.EngineSettings(memory=False), memory, "j2-idle")
    assert off["memory"] is False and off["lessons"] == [] and off["playbooks"] == []
    monkeypatch.setenv("SUTRA_MOCK", "1")
    assert w.views.idle_snapshot(settings, memory, "j2-idle")["mock"] is True
    assert not list(Path(tempfile_dir()).glob("sutra-idle-*/j2-idle")), "the throw-away run's folder is never made"


def tempfile_dir():
    import tempfile
    return tempfile.gettempdir()


# ---- state -------------------------------------------------------------------------------------------------------------
def test_live_state_returns_the_chat_from_since_and_the_additive_keys(w):
    ctx = live_ctx(w, w.site, dept_id="web")
    full = ctx.snap["chat"]
    r = call(w, "state", ctx, since="2")
    body = jbody(r)
    assert (r.code, r.ctype) == (200, "application/json") and r.cache == "no-store"
    assert body["chat"] == full[2:] and body["total"] == len(full) > 2 and body["saved"] is None
    assert body["host"] == {"pid": os.getpid(), "alive": True} and body["run_id"] == SITE_ID and body["dept_id"] == "web"
    assert jbody(call(w, "state", ctx))["chat"] == full
    assert jbody(call(w, "state", ctx, since="junk"))["chat"] == full, "a since that is no number reads as 0"
    assert jbody(call(w, "state", ctx, since="-4"))["chat"] == full, "and a negative one too"


def test_a_gone_process_with_a_running_snapshot_reads_as_waiting_with_an_error(w):
    ctx = live_ctx(w, w.site)
    ctx.snap = {**ctx.snap, "status": "running", "error": None}
    ctx.alive = False
    body = jbody(call(w, "state", ctx))
    assert body["status"] == "waiting" and body["error"] == "The department process stopped (exit unknown). Try again."
    assert body["host"]["alive"] is False
    ctx.alive = True
    body = jbody(call(w, "state", ctx))
    assert body["status"] == "running" and body["error"] is None
    ctx.alive, ctx.snap = False, {**ctx.snap, "status": "waiting"}
    assert jbody(call(w, "state", ctx))["error"] is None, "a run that is only waiting keeps its state"


def test_saved_state_is_read_from_the_folder_and_a_missing_run_is_404(w):
    body = jbody(call(w, "state", saved_ctx(w, SITE_ID), since="1"))
    assert body["saved"] == SITE_ID and body["status"] == "saved" and body["chat"] and "host" not in body
    assert body == json.loads(json.dumps(w.j2.saved_snapshot_dir(str(w.runs_dir / SITE_ID), SITE_ID, 1)))
    gone = call(w, "state", saved_ctx(w, "j2-20200101-000000"))
    assert gone.code == 404 and json.loads(gone.body) == {"error": "no such run"}


def test_the_idle_state_is_the_idle_snapshot_without_run_keys(w):
    ctx = idle_ctx(w)
    body = jbody(call(w, "state", ctx, since="5"))
    assert body == json.loads(json.dumps({**ctx.snap, "saved": None})) and "host" not in body and body["status"] == "idle"
    assert call(w, "state", w.views.RunCtx("live", None, None, "x", None, w.memory)).code == 404, "live without a snapshot"


# ---- runs, call, preview -----------------------------------------------------------------------------------------------
def test_runs_lists_the_departments_folder_and_names_the_live_run(w):
    body = jbody(call(w, "runs", live_ctx(w, w.site)))
    assert body["live"] == SITE_ID and {r["id"] for r in body["runs"]} == {SITE_ID, PRD_ID}
    row = next(r for r in body["runs"] if r["id"] == SITE_ID)
    assert row["status"] == "done" and row["brief"].startswith("A one-page website for Brew Lab")
    assert [r["id"] for r in body["runs"]] == sorted((SITE_ID, PRD_ID), reverse=True), "newest first"
    ctx = idle_ctx(w)
    assert jbody(call(w, "runs", ctx))["live"] == ""
    ctx.runs_dir = str(w.base / "nothing-here")
    assert jbody(call(w, "runs", ctx)) == {"live": "", "runs": []}, "another department's folder holds other runs"


def test_call_returns_the_full_record_or_404(w):
    for ctx in (live_ctx(w, w.site), saved_ctx(w, SITE_ID)):
        rec1 = jbody(call(w, "call", ctx, id="1"))
        assert rec1["id"] == 1 and rec1["prompt"] and rec1["system"] and {"fn", "reply", "raw", "tokens"} <= set(rec1)
        for bad in ("99999", "x", None):
            r = call(w, "call", ctx, id=bad)
            assert r.code == 404 and json.loads(r.body) == {"error": "no such call"}
    assert call(w, "call", saved_ctx(w, "j2-20200101-000000"), id="1").code == 404
    assert call(w, "call", idle_ctx(w), id="1").code == 404


def first_atom(run, kind):
    return next(a["id"] for w_ in run._all_wfs() for a in w_.get("atoms") or [] if (a.get("agent_output") or {}).get("kind") == kind)


def test_preview_serves_an_atoms_section_from_the_built_page(w):
    atom = next(a for w_ in w.site._all_wfs() for a in w_["atoms"] if (a.get("agent_output") or {}).get("anchor"))
    for ctx in (live_ctx(w, w.site), saved_ctx(w, SITE_ID)):
        body = jbody(call(w, "preview", ctx, atom=atom["id"]))
        assert body["anchor"] == atom["agent_output"]["anchor"] and body["html"] and "<body" in body["html"]
        assert jbody(call(w, "preview", ctx, atom="nope")) == {"anchor": None, "html": None}
    assert jbody(call(w, "preview", idle_ctx(w), atom=atom["id"])) == {"anchor": None, "html": None}


def test_preview_of_a_document_atom_renders_its_section(w):
    atom = first_atom(w.prd, "doc")
    for ctx in (live_ctx(w, w.prd), saved_ctx(w, PRD_ID)):
        body = jbody(call(w, "preview", ctx, atom=atom))
        assert body["anchor"] is None and body["html"] and "<h" in body["html"]


# ---- docs, map, plan ---------------------------------------------------------------------------------------------------
def test_docs_shows_which_documents_were_asked_for(w):
    for ctx in (live_ctx(w, w.prd), saved_ctx(w, PRD_ID)):
        body = jbody(call(w, "docs", ctx))
        assert set(body) == {"prd", "hld", "lld"} and body["prd"]["asked"] is True and body["prd"]["text"].startswith("# QuickQueue")
        assert body["prd"]["workflows"] and body["hld"] == {"asked": False, "text": None, "workflows": []}
    site = jbody(call(w, "docs", live_ctx(w, w.site)))
    assert all(v == {"asked": False, "text": None, "workflows": []} for v in site.values())
    live = live_ctx(w, w.site)
    live.extras = {**live.extras, "docset": ["hld"]}
    assert jbody(call(w, "docs", live))["hld"] == {"asked": True, "text": None, "workflows": []}, "asked but not yet written"
    assert jbody(call(w, "docs", idle_ctx(w)))["prd"]["asked"] is False


def test_map_is_drawn_live_only_while_the_run_runs_or_is_paused(w, monkeypatch):
    seen = []
    monkeypatch.setattr(w.views.j2_map, "build", lambda d, live=None: seen.append(live) or {"schema": "map/1"})
    ctx = live_ctx(w, w.site)
    for status, paused, alive, expect in (("running", None, True, True), ("waiting", {"kind": "info"}, True, True),
                                          ("waiting", None, True, False), ("running", None, False, False), ("idle", None, True, False)):
        ctx.snap, ctx.alive = {**ctx.snap, "status": status, "paused": paused}, alive
        seen.clear()
        call(w, "map", ctx)
        assert (seen[0] is not None) is expect, (status, paused, alive)
    ctx.snap, ctx.alive = {**ctx.snap, "status": "running"}, True
    seen.clear()
    call(w, "map", ctx)
    live = seen[0]
    assert set(live) == {"snapshot", "stages", "stage_words", "board"} and live["stage_words"] == w.j2.J2Run.STAGE_WORDS
    assert live["snapshot"]["status"] == "running" and live["board"] == ctx.extras["board"]
    seen.clear()
    call(w, "map", saved_ctx(w, SITE_ID))
    assert seen == [None], "a saved run is never drawn live"


def test_the_map_of_a_finished_run_is_the_same_live_and_saved(w):
    live = jbody(call(w, "map", live_ctx(w, w.site)))
    assert live == jbody(call(w, "map", saved_ctx(w, SITE_ID))) and live["schema"] == "map/1" and live["nodes"]
    assert jbody(call(w, "map", idle_ctx(w)))["nodes"] == []


def test_plan_reads_the_folder(w):
    body = jbody(call(w, "plan", live_ctx(w, w.site)))
    assert body == w.j2.j2_map.plan_view(str(w.runs_dir / SITE_ID))
    assert jbody(call(w, "plan", idle_ctx(w))) == w.j2.j2_map.plan_view(None)


# ---- the library and the run's own copy of its templates (J2 sync 2026-11-04) -----------------------------------------
def first_decision(w):
    return json.loads((w.runs_dir / SITE_ID / "templates.json").read_text())["decisions"][0]


def item_q(w, d):
    return dict(artifact=d["artifact"], section=w.j2.j2_template_lib.slug(d["section"]), slug=w.j2.j2_template_lib.slug(d["template"]),
                version=f"v{d['version']}")


def test_library_lists_every_template_by_artifact_and_section(w):
    body = jbody(call(w, "library", idle_ctx(w)))
    assert body["schema"] == "template-library/1" and set(body["groups"]) >= {"prd", "hld", "lld", "website"}
    assert body == w.j2.j2_template_lib.library_view()


def test_run_templates_answers_each_decision_with_where_its_template_is_read_from(w):
    for ctx in (live_ctx(w, w.site), saved_ctx(w, SITE_ID)):
        decisions = jbody(call(w, "run_templates", ctx))["decisions"]
        assert decisions and all(d["source"] == "from this run" for d in decisions)
        assert all(d["saved"].startswith("templates/") and d["saved"].endswith(f"@v{d['version']}") for d in decisions)
        assert decisions == w.j2.j2_template_lib.run_templates(str(w.runs_dir / SITE_ID))
    assert jbody(call(w, "run_templates", idle_ctx(w))) == {"decisions": []}


def test_run_templates_falls_back_to_the_library_and_then_to_not_recorded(w, tmp_path):
    copy = tmp_path / "runs" / SITE_ID
    shutil.copytree(w.runs_dir / SITE_ID, copy)
    shutil.rmtree(copy / "templates")
    ghost = {"artifact": "prd", "section": "Goals", "template": "ghost", "version": 7, "kind": "specialised", "saved": None}
    data = json.loads((copy / "templates.json").read_text())
    data["decisions"].append(ghost)
    (copy / "templates.json").write_text(json.dumps(data))
    ctx = saved_ctx(w, SITE_ID, folder="runs")
    ctx.dir = str(copy)
    sources = {(d["template"], d["version"]): d["source"] for d in jbody(call(w, "run_templates", ctx))["decisions"]}
    assert sources[("ghost", 7)] == "not recorded" and set(sources.values()) == {"from library", "not recorded"}
    got = jbody(call(w, "library_item", ctx, artifact="prd", section="goals", slug="ghost", version="v7"))
    assert got["source"] == "not recorded" and got["files"] == {} and got["readable"] is None


def test_library_item_serves_the_runs_own_copy_first_and_then_the_library(w):
    d = next(x for x in json.loads((w.runs_dir / SITE_ID / "templates.json").read_text())["decisions"] if x["kind"] != "generic")
    q = item_q(w, d)
    mine = jbody(call(w, "library_item", live_ctx(w, w.site), **q))
    assert mine["source"] == "from this run" and mine["saved"] == d["saved"] and mine["template"]["name"] == d["template"]
    assert "example" in mine and set(mine["files"]) == {"spec.json", "model.py", "schema.json", "meta.json"}
    assert jbody(call(w, "library_item", saved_ctx(w, SITE_ID), **q))["source"] == "from this run"
    lib = jbody(call(w, "library_item", idle_ctx(w), **q))
    assert lib["source"] == "from library" and "example" not in lib and lib["template"] == mine["template"]


def test_library_item_refuses_what_is_not_a_template_path(w):
    ctx = live_ctx(w, w.site)
    d = first_decision(w)
    good = item_q(w, d)
    for bad in ({"artifact": "nope"}, {"section": "../x"}, {"slug": "A B"}, {"slug": ""}, {"version": "3"}, {"version": "vx"},
                {"version": "v-1"}, {"version": "v1.5"}, {"section": "none"}, {"version": "v999"}):
        r = call(w, "library_item", ctx, **{**good, **bad})
        assert r.code == 404 and json.loads(r.body) == {"error": "no such template"}, bad
    assert call(w, "library_item", ctx, **good).code == 200
    section = w.j2.j2_template_lib.slug(next(iter(w.j2.j2_template_lib.library_view()["groups"]["website"])))
    generic = jbody(call(w, "library_item", idle_ctx(w), artifact="website", section=section, slug="generic", version="v1"))
    assert generic["source"] == "from library" and generic["meta"]["kind"] == "generic"


# ---- artifacts, agent, code, artifact ----------------------------------------------------------------------------------
def test_artifacts_agent_and_code_read_the_run_folder(w):
    d = str(w.runs_dir / SITE_ID)
    ctx = live_ctx(w, w.site)
    assert jbody(call(w, "artifacts", ctx)) == w.j2.j2_artifacts.listing(d)
    assert jbody(call(w, "artifacts", idle_ctx(w))) == w.j2.j2_artifacts.listing(None)
    ag = jbody(call(w, "agent", ctx, who="identity"))
    assert ag["schema"] == "agent/1" and ag["found"] is True and ag["who"] == "identity" and ag["conversations"]
    assert jbody(call(w, "agent", ctx, who="nobody"))["found"] is False
    assert jbody(call(w, "agent", idle_ctx(w), who="identity"))["found"] is False
    row = next(c for c in rec_walk(jbody(call(w, "artifacts_tree", ctx))) if c.get("deck"))
    r = call(w, "code", ctx, deck=row["deck"], section=row.get("section"))
    assert r.code == 200 and r.ctype == "text/plain" and r.body
    miss = call(w, "code", ctx, deck="none")
    assert (miss.code, miss.body, miss.ctype) == (404, "not found", "text/plain")


def rec_walk(tree):
    return list(rec._walk_code(tree))


def test_artifacts_tree_is_drawn_from_the_same_data_as_the_map(w, monkeypatch):
    ctx = live_ctx(w, w.site)
    tree = jbody(call(w, "artifacts_tree", ctx))
    assert tree["schema"] == "artifacts-tree/1" and tree == jbody(call(w, "artifacts_tree", saved_ctx(w, SITE_ID)))
    assert jbody(call(w, "artifacts_tree", idle_ctx(w))) == w.j2.j2_artifacts.tree(None)
    seen, build = [], w.views.j2_map.build
    monkeypatch.setattr(w.views.j2_map, "build", lambda d, live=None: seen.append(live) or build(d, None))
    for status, paused, expect in (("running", None, True), ("waiting", None, False), ("waiting", {"kind": "x"}, True)):
        ctx.snap = {**ctx.snap, "status": status, "paused": paused}
        seen.clear()
        call(w, "artifacts_tree", ctx)
        assert (seen[0] is not None) is expect, (status, paused)


def test_artifact_serves_only_a_listed_file_with_its_type(w, tmp_path):
    ctx = live_ctx(w, w.site)
    page = call(w, "artifact", ctx, name="site/v1.html")
    assert (page.code, page.ctype) == (200, "text/html") and page.body.startswith(b"<!doctype html>") or page.body.lower().startswith(b"<!")
    assert call(w, "artifact", ctx, name="goal.json").ctype == "text/plain"
    for bad in ("../" + SITE_ID + "/goal.json", "/etc/passwd", "task.json", "", None, "site/../goal.json"):
        r = call(w, "artifact", ctx, name=bad)
        assert (r.code, r.body, r.ctype) == (404, "not found", "text/plain"), bad
    docx = call(w, "artifact", live_ctx(w, w.prd), name="prd.docx")
    assert (docx.code, docx.ctype, docx.name) == (200, w.views.DOCX, "prd.docx") and docx.body[:2] == b"PK"
    copy = tmp_path / "runs" / SITE_ID
    shutil.copytree(w.runs_dir / SITE_ID, copy)
    (copy / "site" / "shots").mkdir(parents=True, exist_ok=True)
    (copy / "site" / "shots" / "v1.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    ctx = saved_ctx(w, SITE_ID)
    ctx.dir = str(copy)
    png = call(w, "artifact", ctx, name="site/shots/v1.png")
    assert (png.code, png.ctype, png.body[:4]) == (200, "image/png", b"\x89PNG")


# ---- story, board, audits, refs ----------------------------------------------------------------------------------------
def test_story_and_board_are_live_while_the_run_runs_waits_or_is_paused(w, monkeypatch):
    seen = []
    monkeypatch.setattr(w.views.j2_story, "build", lambda d, live=None: seen.append(live) or {"schema": "story/1"})
    ctx = live_ctx(w, w.site)
    for status, paused, expect in (("running", None, True), ("waiting", None, True), ("waiting", {"kind": "x"}, True),
                                   ("idle", None, False), ("idle", {"kind": "x"}, True)):
        ctx.snap = {**ctx.snap, "status": status, "paused": paused}
        seen.clear()
        call(w, "story", ctx)
        assert (seen[0] is not None) is expect, (status, paused)
    ctx.snap = {**ctx.snap, "status": "running", "paused": None}
    seen.clear()
    call(w, "story", ctx)
    assert set(seen[0]) == {"snapshot", "board"} and seen[0]["board"] == ctx.extras["board"]
    seen.clear()
    call(w, "story", saved_ctx(w, SITE_ID))
    assert seen == [None]


def test_board_is_the_live_board_or_the_saved_file_or_the_empty_board(w):
    live = live_ctx(w, w.site)
    marker = {"schema": "board/1", "entries": [{"id": "Q-9"}]}
    live.extras = {**live.extras, "board": marker}
    for status, expect in (("running", marker), ("waiting", marker)):
        live.snap = {**live.snap, "status": status}
        assert jbody(call(w, "board", live)) == expect
    live.snap = {**live.snap, "status": "idle", "paused": None}
    on_disk = {"schema": "board/1", "entries": [{"id": "Q-1"}]}
    folder = w.base / "board-run"
    folder.mkdir(exist_ok=True)
    (folder / "board.json").write_text(json.dumps(on_disk))
    live.dir = str(folder)
    assert jbody(call(w, "board", live)) == on_disk, "the run is idle: the file"
    saved = saved_ctx(w, SITE_ID)
    saved.dir = str(folder)
    assert jbody(call(w, "board", saved)) == on_disk
    assert jbody(call(w, "board", saved_ctx(w, PRD_ID))) == {"schema": "board/1", "entries": []}
    assert jbody(call(w, "board", idle_ctx(w))) == {"schema": "board/1", "entries": []}


def test_audits_condense_the_stage_records_of_a_document_chain(w, tmp_path):
    d = tmp_path / "runs" / "j2-20261104-100009-aaaa"
    d.mkdir(parents=True)
    audit = {"cycle": 2, "results": [{"id": "D-1", "verdict": "PASS", "pass": True, "evidence": "long"}], "extra_issues": [{"id": "X", "verdict": "bad", "n": 1}],
             "rubric": [{"id": "R-1", "verdict": "ok", "pass": False, "note": "n"}], "conditions": [{"id": "N1", "met": True, "evidence": "e"}]}
    (d / "stage-prd.json").write_text(json.dumps({"stage": "prd", "audits": [audit]}))
    (d / "stage-notes.txt").write_text("not a stage file")
    ctx = saved_ctx(w, d.name)
    ctx.dir = str(d)
    assert jbody(call(w, "audits", ctx)) == [{"stage": "prd", "cycle": 2, "results": [{"id": "D-1", "verdict": "PASS", "pass": True}],
                                              "extra_issues": [{"id": "X", "verdict": "bad"}], "rubric": [{"id": "R-1", "verdict": "ok", "pass": False}],
                                              "conditions": [{"id": "N1", "met": True}]}]
    assert jbody(call(w, "audits", live_ctx(w, w.site))) == []
    assert jbody(call(w, "audits", idle_ctx(w))) == []


def test_refs_name_the_conditions_and_the_rubric_ids(w):
    body = jbody(call(w, "refs", idle_ctx(w)))
    assert {"N1", "N8"} <= set(body["conditions"]) and "R-6" in body["rubric"] and "D-1" in body["rubric"]
    assert all(isinstance(t, str) and t for t in {**body["conditions"], **body["rubric"]}.values())


# ---- shot, file, site --------------------------------------------------------------------------------------------------
def test_shot_serves_a_screenshot_by_number_only(w, tmp_path):
    copy = tmp_path / "runs" / SITE_ID
    (copy / "site" / "shots").mkdir(parents=True)
    (copy / "site" / "shots" / "v3.png").write_bytes(b"\x89PNG-3")
    ctx = saved_ctx(w, SITE_ID)
    ctx.dir = str(copy)
    ok = call(w, "shot", ctx, n="3")
    assert (ok.code, ok.ctype, ok.body) == (200, "image/png", b"\x89PNG-3")
    (copy / "site" / "shots" / "vsub").mkdir()
    (copy / "site" / "shots" / "9.png").write_bytes(b"\x89PNG-9")           # a file the number 9 must not reach by a detour
    for bad in ("4", "..", "3/../3", "sub/../9", "v3", "", None, "²"):
        r = call(w, "shot", ctx, n=bad)
        assert (r.code, r.body, r.ctype) == (404, "not found", "text/plain"), bad
    assert call(w, "shot", idle_ctx(w), n="3").code == 404


def test_file_serves_only_the_documents_the_output_allows(w):
    for ctx in (live_ctx(w, w.prd), saved_ctx(w, PRD_ID)):
        md = call(w, "file", ctx, name="prd.md")
        assert (md.code, md.ctype) == (200, "text/markdown") and md.body.startswith(b"# QuickQueue")
        docx = call(w, "file", ctx, name="prd.docx")
        assert (docx.ctype, docx.name, docx.body[:2]) == (w.views.DOCX, "prd.docx", b"PK")
        for bad in ("goal.json", "../task.json", "prd.txt", "", None, "hld.md"):
            r = call(w, "file", ctx, name=bad)
            assert (r.code, r.body, r.ctype) == (404, "not found", "text/plain"), bad
    for ctx in (live_ctx(w, w.site), saved_ctx(w, SITE_ID), idle_ctx(w)):
        assert call(w, "file", ctx, name="prd.md").code == 404, "a website run has no document to download"


def test_file_also_serves_the_documents_of_a_design_run(w, tmp_path):
    d = tmp_path / "runs" / "j2-20261104-100010-bbbb"
    d.mkdir(parents=True)
    (d / "documents.json").write_text(json.dumps({"hld": {"workflows": []}}))
    (d / "hld.md").write_text("# HLD")
    ctx = saved_ctx(w, d.name)
    ctx.dir = str(d)
    ok = call(w, "file", ctx, name="hld.md")
    assert (ok.code, ok.body) == (200, b"# HLD") and call(w, "file", ctx, name="lld.md").code == 404


def test_the_live_site_serves_a_version_or_the_latest(w):
    ctx = live_ctx(w, w.site)
    n = len(w.site.sites)
    latest = call(w, "site", ctx, key="latest")
    assert (latest.code, latest.ctype) == (200, "text/html") and latest.body == w.site.sites[-1]
    assert call(w, "site", ctx, key="v1").body == w.site.sites[0] and call(w, "site", ctx, key=f"v{n}").body == w.site.sites[-1]
    assert call(w, "site", ctx, key="2").body == w.site.sites[1], "J2 took the v off"
    for bad in ("v0", f"v{n + 1}", "v99", "vx", "", "latest2", "v-1"):
        r = call(w, "site", ctx, key=bad)
        assert (r.code, r.body, r.ctype) == (404, "not found", "text/plain"), bad


def test_a_live_document_is_rendered_from_markdown(w):
    ctx = live_ctx(w, w.prd)
    page = text_of(call(w, "site", ctx, key="latest"))
    assert "<h2>Problem</h2>" in page and "<table>" in page
    assert text_of(call(w, "site", ctx, key="v1")) == w.j2.md_html(w.prd.sites[0], "PRD document")


def test_before_anything_is_built_the_live_site_is_a_stub(w):
    stub = text_of(call(w, "site", idle_ctx(w), key="latest"))
    assert "Your website will appear here" in stub
    ctx = live_ctx(w, w.prd)
    ctx.extras = {**ctx.extras, "sites": 0}
    assert "Your document will appear here" in text_of(call(w, "site", ctx, key="v1"))


def test_a_saved_site_serves_latest_or_a_version_or_a_stub(w):
    ctx = saved_ctx(w, SITE_ID)
    n = len(w.site.sites)
    assert call(w, "site", ctx, key="latest").body == w.site.sites[-1] and call(w, "site", ctx, key="v1").body == w.site.sites[0]
    assert call(w, "site", ctx, key=f"v{n}").body == w.site.sites[-1]
    for missing in ("v99", "junk", "v0"):
        assert "No site in this run" in text_of(call(w, "site", ctx, key=missing)), missing
    assert "No site in this run" in text_of(call(w, "site", saved_ctx(w, "j2-20200101-000000"), key="latest"))
    prd = text_of(call(w, "site", saved_ctx(w, PRD_ID), key="latest"))
    assert "<h2>Requirements</h2>" in prd


# ---- index and vendor ---------------------------------------------------------------------------------------------------
def test_index_and_vendor_need_the_folder_the_adapter_was_given(w, tmp_path):
    ctx = idle_ctx(w)
    for name in ("index", "vendor"):
        r = call(w, name, ctx)
        assert (r.code, r.body, r.ctype) == (404, "not found", "text/plain")
    (tmp_path / "j2_ui.html").write_text("<html>page</html>", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "d3.min.js").write_bytes(b"var d3 = 1;")
    ctx = idle_ctx(w, here=str(tmp_path), vendor=str(tmp_path / "vendor"))
    page, js = call(w, "index", ctx), call(w, "vendor", ctx)
    assert (page.code, page.ctype, page.body) == (200, "text/html", "<html>page</html>")
    assert (js.code, js.ctype, js.body, js.cache) == (200, "text/javascript", b"var d3 = 1;", "max-age=3600")
    empty = idle_ctx(w, here=str(tmp_path / "none"), vendor=str(tmp_path / "none"))
    assert call(w, "index", empty).code == 404 and call(w, "vendor", empty).code == 404


# ---- the POSTs ---------------------------------------------------------------------------------------------------------
def test_say_validates_the_text_and_reports_busy(w):
    cmd = FakeCommands()
    ctx = idle_ctx(w, commands=cmd)
    ok = call(w, "say", ctx, text="  hello team  ")
    assert (ok.code, json.loads(ok.body)) == (200, {"ok": True}) and cmd.calls == [("say", "hello team")]
    for bad in ({}, {"text": ""}, {"text": "   \n"}, {"text": None}, {"text": 5}, {"text": ["x"]}):
        r = call(w, "say", ctx, **bad)
        assert (r.code, json.loads(r.body)) == (400, {"error": "empty"}), bad
    assert len(cmd.calls) == 1, "an empty message never reaches the run"
    busy = call(w, "say", idle_ctx(w, commands=FakeCommands(say=False)), text="hi")
    assert (busy.code, json.loads(busy.body)) == (409, {"ok": False})


def test_output_reports_whether_the_type_was_accepted(w):
    cmd = FakeCommands(output="prd")
    ok = call(w, "output", idle_ctx(w, commands=cmd), type="prd")
    assert (ok.code, json.loads(ok.body)) == (200, {"ok": True, "output": "prd"}) and cmd.calls == [("set_output", "prd")]
    late = call(w, "output", idle_ctx(w, commands=FakeCommands(accept=False, output="website")), type="prd")
    assert (late.code, json.loads(late.body)) == (409, {"ok": False, "output": "website"})


def test_reset_is_refused_with_409_while_a_run_is_going(w):
    cmd = FakeCommands()
    ok = call(w, "reset", idle_ctx(w, commands=cmd))
    assert (ok.code, json.loads(ok.body)) == (200, {"ok": True}) and cmd.calls == [("reset",)]
    busy = call(w, "reset", idle_ctx(w, commands=FakeCommands(reset=False)))
    assert (busy.code, json.loads(busy.body)) == (409, {"ok": False})


def test_a_post_without_a_command_object_is_501_and_nothing_is_done(w):
    ctx = idle_ctx(w)
    for name, body in (("say", {"text": "hi"}), ("output", {"type": "prd"}), ("reset", {})):
        assert call(w, name, ctx, **body).code == 501, name


def test_the_clear_routes_empty_the_departments_memory_files(w, tmp_path):
    memory = w.views.MemoryPaths(str(tmp_path / "l.jsonl"), str(tmp_path / "p.jsonl"))
    ctx = idle_ctx(w)
    ctx.memory = memory
    Path(memory.lessons).write_text('{"id": 1}\n{"id": 2}\n\n{"id": 3}\n')
    Path(memory.playbooks).write_text('{"id": 1}\n')
    assert jbody(call(w, "lessons_clear", ctx)) == {"ok": True, "cleared": 3} and not Path(memory.lessons).exists()
    assert Path(memory.playbooks).exists(), "each route clears its own file"
    assert jbody(call(w, "playbooks_clear", ctx)) == {"ok": True, "cleared": 1} and not Path(memory.playbooks).exists()
    assert jbody(call(w, "lessons_clear", ctx)) == {"ok": True, "cleared": 0}


# ---- the file-based live mode and the stdlib adapter give the same bodies ---------------------------------------------
LIVE_QUERIES = {"state": {"since": "1"}, "runlist": {}, "preview": {}, "docs": {}, "map": {}, "artifacts_tree": {}, "story": {}, "board": {},
                "file": {"name": "prd.md"}, "site": {"key": "latest"}}


def test_the_files_the_host_publishes_give_the_same_bodies_as_the_live_run(w, tmp_path):
    assert set(LIVE_QUERIES) == set(w.views.LIVE_VIEWS)
    for run in (w.site, w.prd):
        snap, live = w.views.live_state(run)
        out = tmp_path / os.path.basename(run.dir)
        out.mkdir()
        (out / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        (out / "live.json").write_text(json.dumps(live), encoding="utf-8")
        pub = w.views.read_published(out)
        mem = live_ctx(w, run)
        files = w.views.RunCtx("live", mem.run_id, run.dir, mem.runs_dir, mem.live_id, w.memory, snap=pub.snap, extras=pub.live,
                               alive=pub.alive)
        for name, q in LIVE_QUERIES.items():
            q = {**q, **({"atom": first_atom(run, "doc")} if name == "preview" and run is w.prd else {})}
            a, b = call(w, name, mem, **q), call(w, name, files, **q)
            assert (a.code, a.ctype, a.body) == (b.code, b.ctype, b.body), (os.path.basename(run.dir), name)


def test_the_stdlib_adapter_answers_from_the_run_it_holds(w, monkeypatch):
    monkeypatch.setattr(w.j2_server, "RUN", w.prd)
    srv = w.server
    state = srv.json("/api/state?since=2")
    assert state["output"] == "prd" and state["chat"] == w.prd.chat[2:] and state["host"]["alive"] is True
    assert srv.ask("GET", "/file/prd.docx")[2][:2] == b"PK"
    status, ctype, body = srv.ask("GET", f"/site/latest?run={PRD_ID}")
    assert status == 200 and ctype.startswith("text/html") and b"<h2>Requirements</h2>" in body
    sv = srv.json(f"/api/state?run={PRD_ID}")
    assert sv["saved"] == PRD_ID and sv["versions"] == len(w.prd.sites)


def test_the_live_runs_id_before_its_folder_exists_is_the_live_run(w, monkeypatch, tmp_path):
    fresh = w.j2.J2Run(run_dir=tmp_path / "runs" / "j2-20261104-100011-cccc")
    monkeypatch.setattr(w.j2_server, "RUN", fresh)
    status, _, body = w.server.ask("GET", "/api/state?run=j2-20261104-100011-cccc")
    assert status == 200 and json.loads(body)["saved"] is None and json.loads(body)["status"] == "idle"
    assert w.server.ask("GET", "/api/state?run=j2-20200101-000000")[0] == 404


def test_the_adapter_routes_a_post_by_its_path_and_not_its_query(w, monkeypatch):
    said = []
    fresh = w.j2.J2Run()
    monkeypatch.setattr(fresh, "user_says", lambda text: said.append(text) or True)
    monkeypatch.setattr(w.j2_server, "RUN", fresh)
    plain = w.server.ask("POST", "/api/say", {"text": "one"})
    queried = w.server.ask("POST", "/api/say?dept=web", {"text": "two"})
    assert plain[0] == queried[0] == 200 and plain[2] == queried[2] == b'{"ok": true}'
    assert said == ["one", "two"]
    assert w.server.ask("POST", "/api/output?dept=web&x=1", {"type": "prd"})[0] == 200
    assert w.server.ask("POST", "/api/nothing?dept=web", {})[0] == 404


def test_the_adapter_turns_a_bad_body_into_400_and_an_unknown_path_into_404(w, monkeypatch):
    monkeypatch.setattr(w.j2_server, "RUN", w.j2.J2Run())
    srv = w.server
    assert srv.ask("POST", "/api/say", raw=b"{broken")[0] == 400
    assert srv.ask("POST", "/api/say", raw=b"[1]")[0] == 400
    assert srv.ask("POST", "/api/say", raw=b"")[0] == 400, "no body is an empty object: no text"
    assert srv.ask("POST", "/api/other", {}) == (404, "application/json; charset=utf-8", b"{}")
    assert srv.ask("GET", "/api/other") == (404, "text/plain; charset=utf-8", b"not found")
    assert srv.ask("GET", "/api/library/website/x") [0] == 404


def test_the_adapter_resets_and_sets_the_output_of_its_run(w, monkeypatch):
    fresh = w.j2.J2Run()
    monkeypatch.setattr(w.j2_server, "RUN", fresh)
    assert json.loads(w.server.ask("POST", "/api/output", {"type": "prd"})[2]) == {"ok": True, "output": "prd"}
    assert fresh.output == "prd"
    fresh.status = "running"
    assert w.server.ask("POST", "/api/reset", {}) == (409, "application/json; charset=utf-8", b'{"ok": false}')
    fresh.status = "waiting"
    assert w.server.ask("POST", "/api/reset", {})[0] == 200 and fresh.output == "website"


def test_the_adapter_serves_the_page_and_d3_only_from_a_given_folder(w, monkeypatch, tmp_path):
    monkeypatch.setattr(w.j2_server, "RUN", w.j2.J2Run())
    monkeypatch.setattr(w.j2_server, "HERE", None)
    monkeypatch.setattr(w.j2_server, "VENDOR", None)
    assert w.server.ask("GET", "/")[0] == 404 and w.server.ask("GET", "/vendor/d3.min.js")[0] == 404
    (tmp_path / "j2_ui.html").write_text("<p>page</p>", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "d3.min.js").write_bytes(b"var d3;")
    monkeypatch.setattr(w.j2_server, "HERE", str(tmp_path))
    monkeypatch.setattr(w.j2_server, "VENDOR", str(tmp_path / "vendor"))
    assert w.server.ask("GET", "/") == (200, "text/html; charset=utf-8", b"<p>page</p>")
    assert w.server.ask("GET", "/index.html")[2] == b"<p>page</p>"
    status, ctype, body = w.server.ask("GET", "/vendor/d3.min.js")
    assert (status, ctype, body) == (200, "text/javascript; charset=utf-8", b"var d3;")


def test_the_adapter_redacts_secrets_in_every_text_body_and_leaves_png_and_docx_alone(w, monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_API_KEY", "sk-secret-value-1234567")
    (tmp_path / ".env").write_text("OTHER=dotenv-secret-9876543\n# comment=skipped-value-1111\n", encoding="utf-8")
    (tmp_path / "j2_ui.html").write_text("<p>sk-secret-value-1234567 and dotenv-secret-9876543</p>", encoding="utf-8")
    monkeypatch.setattr(w.j2_server, "HERE", str(tmp_path))
    monkeypatch.setattr(w.j2_server, "RUN", w.j2.J2Run())
    assert w.server.ask("GET", "/")[2] == b"<p>[redacted] and [redacted]</p>"
    assert w.j2_server.redact("x skipped-value-1111 y") == "x skipped-value-1111 y"
    assert {"sk-secret-value-1234567", "dotenv-secret-9876543"} <= set(w.j2_server.secrets())
    monkeypatch.setattr(w.j2_server, "RUN", w.prd)
    assert w.server.ask("GET", "/file/prd.docx")[2][:2] == b"PK"


def test_the_adapter_answers_500_when_a_handler_breaks_and_stays_up(w, monkeypatch, capsys):
    def broken(ctx, q):
        raise RuntimeError("boom")
    monkeypatch.setitem(w.views.VIEWS, "runs", broken)
    monkeypatch.setattr(w.j2_server, "RUN", w.j2.J2Run())
    assert w.server.ask("GET", "/api/runs") == (500, "application/json; charset=utf-8", b'{"error": "internal"}')
    assert "boom" in capsys.readouterr().err
    assert w.server.ask("GET", "/api/refs")[0] == 200


def test_the_adapter_reads_runs_dir_and_memory_files_per_request(w, monkeypatch, tmp_path):
    other = tmp_path / "other-runs"
    (other / "j2-20261104-100012-dddd").mkdir(parents=True)
    (other / "j2-20261104-100012-dddd" / "chat.jsonl").write_text('{"who": "user", "text": "hello there"}\n')
    monkeypatch.setattr(w.j2, "RUNS_DIR", str(other))
    monkeypatch.setattr(w.j2_server, "RUN", w.j2.J2Run())
    assert [r["id"] for r in w.server.json("/api/runs")["runs"]] == ["j2-20261104-100012-dddd"]
    lessons = tmp_path / "lessons.jsonl"
    lessons.write_text('{"id": 1}\n')
    monkeypatch.setattr(w.j2, "MEMORY_FILE", str(lessons))
    assert json.loads(w.server.ask("POST", "/api/lessons/clear", {})[2]) == {"ok": True, "cleared": 1} and not lessons.exists()


def test_the_route_table_of_the_adapter_names_a_view_for_every_get_path(w):
    route = w.j2_server.route
    assert route("/") == ("index", {}) and route("/index.html") == ("index", {}) and route("/vendor/d3.min.js") == ("vendor", {})
    assert route("/api/library") == ("library", {}) and route("/api/artifacts/tree") == ("artifacts_tree", {})
    assert route("/api/library/prd/goals/acme/v3") == ("library_item", {"artifact": "prd", "section": "goals", "slug": "acme", "version": "v3"})
    assert route("/api/library/prd/goals")[1] == {"artifact": "", "section": "", "slug": "", "version": ""}
    assert route("/shot/4") == ("shot", {"n": "4"}) and route("/file/prd.md") == ("file", {"name": "prd.md"})
    assert route("/site/latest") == ("site", {"key": "latest"}) and route("/nothing") is None
    names = {route(p)[0] for p in ("/api/state", "/api/runs", "/api/call", "/api/preview", "/api/docs", "/api/map", "/api/plan",
                                   "/api/run-templates", "/api/artifacts", "/api/agent", "/api/code", "/api/artifact", "/api/story",
                                   "/api/board", "/api/audits", "/api/refs")}
    assert names == {"state", "runs", "call", "preview", "docs", "map", "plan", "run_templates", "artifacts", "agent", "code",
                     "artifact", "story", "board", "audits", "refs"}


# ---- the adapter never reaches the page code --------------------------------------------------------------------------
def test_the_views_and_the_adapter_do_not_import_the_ui_package():
    code = ("import sys, sutra_app.engine.views, sutra_app.engine.j2_server\n"
            "bad = [m for m in sys.modules if m == 'sutra_app.ui' or m.startswith('sutra_app.ui.')]\n"
            "sys.exit(1 if bad else 0)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO, timeout=120,
                          env={**os.environ, "PYTHONPATH": str(REPO)})
    assert done.returncode == 0, done.stderr[-500:]
    for name in ("views.py", "j2_server.py"):
        source = (REPO / "sutra_app" / "engine" / name).read_text(encoding="utf-8")
        assert "sutra_app.ui" not in source.replace("sutra_app.ui` ", "").split('"""', 2)[-1], name


# ---- patch P13: GET /api/runlist and GET /api/changes (not in J2's repository; shapes in GOLD["patched"]) ------------------
def patched_problems(w, route, ctx, mode):
    reply = w.views.VIEWS[route](ctx, {})
    got, gold = rec.shape(reply.code, reply.ctype, reply.body), GOLD["patched"]["get"][route][mode]
    return [] if got == gold else [f"{route}/{mode}: {got} instead of {gold}"]


def test_the_golden_has_the_two_patched_routes():
    assert set(GOLD["patched"]["get"]) == set(rec.PATCH_ROUTES) == {"runlist", "changes"}
    assert set(GOLD["patched"]["get"]["runlist"]["runs"]["keys"]) == {"live", "runs", "runs[].id", "runs[].title", "runs[].status",
                                                                     "runs[].output", "runs[].when", "runs[].brief"}
    assert {"runlist", "changes"} <= NAMES


def test_the_runlist_of_the_real_runs_lists_both_newest_first(w):
    ctx = saved_ctx(w, SITE_ID)
    body = jbody(call(w, "runlist", ctx))
    ids = [r["id"] for r in body["runs"]]
    assert ids == [PRD_ID, SITE_ID] and body["live"] == SITE_ID          # the saved ctx of this fixture names SITE_ID as its live id
    by = {r["id"]: r for r in body["runs"]}
    assert by[SITE_ID]["status"] == "done" and by[SITE_ID]["output"] == "website" and by[SITE_ID]["when"] == "2026-11-04T10:00:04"
    assert by[PRD_ID]["output"] == "prd" and by[PRD_ID]["brief"].startswith("Write a PRD for QuickQueue")
    assert by[SITE_ID]["brief"] == rec.BREW_LAB[:160]
    assert patched_problems(w, "runlist", ctx, "runs") == []


def test_the_live_run_reads_running_only_while_it_runs_and_its_process_exists(w):
    ctx = live_ctx(w, w.site)
    assert {r["id"]: r["status"] for r in jbody(call(w, "runlist", ctx))["runs"]}[SITE_ID] == "done"
    snap = {**ctx.snap, "status": "running"}
    running = w.views.RunCtx("live", SITE_ID, ctx.dir, ctx.runs_dir, SITE_ID, w.memory, snap=snap, extras=ctx.extras, alive=True)
    assert {r["id"]: r["status"] for r in jbody(call(w, "runlist", running))["runs"]} == {PRD_ID: "done", SITE_ID: "running"}
    gone = w.views.RunCtx("live", SITE_ID, ctx.dir, ctx.runs_dir, SITE_ID, w.memory, snap=snap, extras=ctx.extras, alive=False)
    assert jbody(call(w, "runlist", gone))["runs"][1]["status"] == "done"
    saved = saved_ctx(w, SITE_ID)
    assert jbody(call(w, "runlist", saved))["runs"][1]["status"] == "done"


def test_the_runlist_of_a_department_with_no_runs_is_empty(w, tmp_path):
    ctx = w.views.RunCtx("idle", None, None, str(tmp_path / "none"), None, w.memory, snap=None)
    assert jbody(call(w, "runlist", ctx)) == {"live": "", "runs": []}
    assert patched_problems(w, "runlist", ctx, "empty") == [] and patched_problems(w, "changes", ctx, "empty") == []


def test_the_changes_of_a_run_without_a_change_file_are_empty_and_a_torn_file_reads_as_none(w, tmp_path):
    assert jbody(call(w, "changes", saved_ctx(w, SITE_ID))) == {"changes": []}
    assert jbody(call(w, "changes", idle_ctx(w))) == {"changes": []}
    d = tmp_path / "j2-20261106-120000-dddd"
    d.mkdir()
    ctx = w.views.RunCtx("saved", d.name, str(d), str(tmp_path), None, w.memory)
    for text in ("{not json", '{"a": 1}', "[1, 2]"):
        (d / "change.json").write_text(text)
        assert jbody(call(w, "changes", ctx)) == {"changes": []}
    (d / "change.json").write_text(json.dumps([{"id": "c1", "request": "Add a map", "cycle": 2, "revise": ["a", "b"], "new": ["c"]}, "x"]))
    assert jbody(call(w, "changes", ctx)) == {"changes": [{"id": "c1", "request": "Add a map", "cycle": 2, "revise": 2, "new": 1}]}
    assert patched_problems(w, "changes", ctx, "runs") == []


def test_the_fixture_runs_of_the_recorder_give_titles_statuses_and_skip_what_is_not_a_run(w, tmp_path):
    live = rec.write_patch_fixture(tmp_path / "runs")
    ctx = w.views.RunCtx("saved", rec.PATCH_RUN_DONE, str(tmp_path / "runs" / rec.PATCH_RUN_DONE), str(tmp_path / "runs"), live, w.memory)
    body = jbody(call(w, "runlist", ctx))
    assert [r["id"] for r in body["runs"]] == [rec.PATCH_RUN_STOPPED, rec.PATCH_RUN_DONE]      # newest first; the folder without a chat is skipped
    stopped, done = body["runs"]
    assert (done["title"], done["status"], done["output"]) == ("Brew Lab", "done", "website")
    assert (stopped["title"], stopped["status"], stopped["output"]) == ("A PRD for QuickQueue.", "stopped", "prd")
    assert stopped["brief"] == "Write a PRD for QuickQueue." and stopped["when"] == "2026-11-06T10:15:00"
    assert jbody(call(w, "changes", ctx))["changes"][1] == {"id": "c2", "request": "Warmer colours", "cycle": 3, "revise": 0, "new": 2}


def test_the_stdlib_adapter_serves_the_two_p13_routes(w, monkeypatch):
    monkeypatch.setattr(w.j2_server, "RUN", w.prd)
    body = w.server.json("/api/runlist")
    assert body["live"] == PRD_ID and [r["id"] for r in body["runs"]] == [PRD_ID, SITE_ID]
    assert w.server.json(f"/api/runlist?run={SITE_ID}")["runs"] == body["runs"]
    assert w.server.json("/api/changes") == {"changes": []} and w.server.json(f"/api/changes?run={SITE_ID}") == {"changes": []}
    assert w.server.ask("GET", "/api/changes?run=j2-20260101-000000-zzzz")[0] == 200
