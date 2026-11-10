#!/usr/bin/env python3
"""Record the shapes of J2's HTTP API into `tests/engine/golden/api_shapes.json` (work package E2, engine design 9).

    scripts/py scripts/record_api_shapes.py --source "$J2SRC" [--commit <sha>] [--out FILE] [--check]
    scripts/py scripts/record_api_shapes.py --patched-only [--out FILE] [--check]       # only the "patched" section (no J2 checkout)

Runs J2's own `j2_server.Handler` from `$J2SRC`, an extraction of this repository's `prototypes/j2` at the pinned sutra commit
(`git archive <sha> prototypes/j2 | tar -x --strip-components=2 -C "$J2SRC"`, docs/design/j2-sync-4.md 2.2): a plain folder, used as it
is, so an edited working tree or a `.pyc` never matters; `--commit` only names the commit and is recorded as `j2_commit`. J2 runs in a
child process, in mock mode with the Chrome checks faked as J2's `--fast` flow does, and with every J2 path under a temp folder
(`J2_RUNS_DIR`, memory, library): nothing is written to the extraction. It drives one Brew Lab run to Done, then asks every GET route
in three situations:

    live    no `?run=`: the run that is held by the server
    saved   `?run=<id>`: the same run read from its folder
    idle    a fresh run, before any message

and the POST routes on a fresh run. Per route it keeps the status, the content type and, for a JSON body, the KEY PATHS (the
names of the keys at every depth, `[]` for a list; a map keyed by ids is written with `*`, and so is `enums`, the enum names of a
template version: they are data, a new seed template adds some, D150), never a value: ids and times change between runs, the shape
does not. `tests/engine/test_engine_views.py` runs the same requests against `views.py` and compares.
`--check` records again and exits 1 when the file differs.

The "patched" section (patch P13) is the one part J2 cannot give: `GET /api/runlist` and `GET /api/changes` exist only in the old Sutra
repository's copy of the prototype, so their shapes are recorded from the engine's own handlers (`views.runlist`, `views.changes`)
over a small fixture of saved runs (`write_patch_fixture`), once for a department with runs and once for an empty one.
The module is also imported by that test for `key_paths`, `ROUTES`
and the scenario constants, so the two sides ask the same questions.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = "025e265c594564f47a2365874cd5a5cc5d0d20a6"       # the sutra commit whose `prototypes/j2` the golden is recorded from (sync 4, D136)
DEFAULT_OUT = REPO / "tests" / "engine" / "golden" / "api_shapes.json"
SCHEMA = "api-shapes/1"

BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
# The flags of the recorded run: mock, J2's own template library, artifact schemas and message board on, so that the routes that
# read those records have something to show; realization off (the unmodified mock cannot pass its cost check, E1 notes).
SCENARIO_ENV = {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_TEMPLATE_LIBRARY": "1",
                "J2_ARTIFACT_SCHEMA": "1", "J2_BOARD": "1", "J2_FORCE_QUESTION": "adaptation"}
# Maps keyed by ids: their keys are written as `*` in a key path. `enums` is the map of a template version's enum names (`FormField.type`,
# `Requirement.priority`, ...): data, which every new seed template extends, so no template can move the golden again (D150).
MAPS = frozenset({"atoms_v1", "agents", "conditions", "rubric", "constellations", "names", "groups", "groups.*", "enums"})
# Free-form agent output: the key is kept, what is inside it is not (it is the model's reply, not part of the API).
OPAQUE = frozenset({"reply", "proposal", "adaptation_final", "priority_final", "metrics"})
# Keys that exist on the engine's side only, on purpose (engine design 4.6): the live state's host, run_id and dept_id, and the
# provider and usd that calls.jsonl records gain (`call_log[]` in the state, the record of /api/call). Everything else is equal.
_CALL_LOG = {"call_log[].provider", "call_log[].usd"}
_LIVE_STATE = {"host", "host.pid", "host.alive", "run_id", "dept_id"}
ADDITIVE = {"state": _CALL_LOG | _LIVE_STATE, "state_since": _CALL_LOG | _LIVE_STATE, "call": {"provider", "usd"}}


def key_paths(value, maps=MAPS, opaque=OPAQUE):
    """The sorted key paths of a JSON value: `a.b`, `a[]`, `a[].c`. The keys of a map (a last name in `maps`, or a whole path
    such as `groups.*`) become `*`; the inside of a key named in `opaque` is not followed."""
    out = set()

    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                name = "*" if (path.split(".")[-1].rstrip("[]") in maps or path in maps) else str(k)
                p = f"{path}.{name}" if path else name
                out.add(p)
                if name not in opaque:
                    walk(x, p)
        elif isinstance(v, list):
            for x in v:
                walk(x, path + "[]")
    walk(value, "")
    return sorted(out)


def shape(status, ctype, body):
    """What is kept of one response."""
    ctype = (ctype or "").split(";")[0].strip()
    out = {"status": status, "ctype": ctype}
    if ctype == "application/json":
        out["keys"] = key_paths(json.loads(body))
    return out


def fake_check(j2_check, html):
    """J2's `--fast` stub: the render check without a browser (static checks, no overflow, no script errors)."""
    st = j2_check.static_checks(html)
    return {"available": True, **st, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0},
            "js_errors": [], "design": {}, "form_results": [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [],
                                                           "errors_during": [], "ok": True} for i in range(st["forms"])]}


def fake_chrome(j2_check):
    j2_check.find_chrome = lambda: None
    j2_check.tap_targets = lambda html, selector, min_px=44: {"available": True, "roots": 1, "checked": 0, "small_count": 0,
                                                              "small": []}
    j2_check.check = lambda html: fake_check(j2_check, html)


# The GET routes: (name, path with {run} where the query starts). `{run}` is "" live and idle, "run=<id>" saved. The routes that
# take an id or a name are filled from the run itself by `ask_routes`.
ROUTES = ("state", "state_since", "runs", "call", "call_missing", "preview", "docs", "map", "plan", "library", "library_item",
          "library_missing", "run_templates", "artifacts", "agent", "code", "code_missing", "artifacts_tree", "artifact",
          "artifact_missing", "story", "board", "audits", "refs", "shot_missing", "file_missing", "site_latest", "site_v1",
          "site_v99", "unknown")
PATCH_ROUTES = {"runlist": "/api/runlist", "changes": "/api/changes"}         # P13: not in J2's repository, recorded from the engine
POSTS = ("output_prd", "say_empty", "say", "output_late", "playbooks_clear", "lessons_clear", "reset")


def slug(text):
    """j2_template_lib.slug."""
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "template"


def paths_for(state, tree, lib, artifacts, run_q, decisions=()):
    """name -> path for every GET route, from a run's state, its artifacts tree, the library view, its artifact list and its
    template decisions (the template of the library_item route is one the run used, so that the run's own copy is shown)."""
    q = lambda extra="": ("?" + "&".join(x for x in (run_q, extra) if x)) if (run_q or extra) else ""       # noqa: E731
    atoms = [a for w in state.get("workflows") or [] for a in w.get("atoms") or []]
    atom = next((a["id"] for a in atoms if (a.get("agent_output") or {}).get("anchor")), atoms[0]["id"] if atoms else "x")
    mine = next(((d["artifact"], slug(d["section"]), slug(d["template"]), d["version"]) for d in decisions
                 if d.get("kind") != "generic"), None)
    tpl = mine or next(((t["artifact"], t["section_slug"], t["slug"], t["versions"][-1]["version"])
                for sections in (lib.get("groups") or {}).values() for slot in sections.values()
                for t in slot.get("templates") or [] if t.get("versions")), None)
    art = next((r["file"] for r in artifacts.get("deliverables", []) if r.get("file")), "site/v1.html")
    code = next(((r["deck"], r.get("section")) for r in _walk_code(tree)), ("x", None))
    return {
        "state": "/api/state" + q(), "state_since": "/api/state" + q("since=3"), "runs": "/api/runs" + q(),
        "call": "/api/call" + q("id=1"), "call_missing": "/api/call" + q("id=99999"),
        "preview": "/api/preview" + q(f"atom={atom}"), "docs": "/api/docs" + q(), "map": "/api/map" + q(), "plan": "/api/plan" + q(),
        "library": "/api/library" + q(),
        "library_item": ("/api/library/%s/%s/%s/v%s" % tpl if tpl else "/api/library/website/x/x/v1") + q(),
        "library_missing": "/api/library/website/none/none/v1" + q(), "run_templates": "/api/run-templates" + q(),
        "artifacts": "/api/artifacts" + q(), "agent": "/api/agent" + q("who=identity"),
        "code": "/api/code" + q(f"deck={code[0]}" + (f"&section={code[1]}" if code[1] else "")),
        "code_missing": "/api/code" + q("deck=none"), "artifacts_tree": "/api/artifacts/tree" + q(),
        "artifact": "/api/artifact" + q(f"name={art}"), "artifact_missing": "/api/artifact" + q("name=nothing.txt"),
        "story": "/api/story" + q(), "board": "/api/board" + q(), "audits": "/api/audits" + q(), "refs": "/api/refs" + q(),
        "shot_missing": "/shot/99" + q(), "file_missing": "/file/goal.json" + q(), "site_latest": "/site/latest" + q(),
        "site_v1": "/site/v1" + q(), "site_v99": "/site/v99" + q(), "unknown": "/api/nothing" + q(),
    }


def _walk_code(tree):
    """Rows of an artifacts-tree/1 that have a `code` reference ({deck, section}), if the tree has any."""
    stack = [tree]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            c = n.get("code")
            if isinstance(c, dict) and c.get("deck"):
                yield c
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)


# ------------------------------------------------------------------------------------------------- the patched routes (P13)
PATCH_RUN_DONE, PATCH_RUN_STOPPED, PATCH_RUN_BARE = "j2-20261105-091500-aaaa", "j2-20261106-101500-bbbb", "j2-20261106-111500-cccc"


def write_patch_fixture(runs_dir):
    """Three saved runs in `runs_dir`: one finished with a goal, a summary and two change requests, one that never finished (only a
    chat and a goal statement) and one whose folder has no chat.jsonl (not a run: the list skips it). Returns the live run's id."""
    runs = Path(runs_dir)

    def put(name, **files):
        folder = runs / name
        folder.mkdir(parents=True, exist_ok=True)
        for file, value in files.items():
            text = "\n".join(json.dumps(row) for row in value) + "\n" if file == "chat.jsonl" else json.dumps(value)
            (folder / file).write_text(text, encoding="utf-8")

    put(PATCH_RUN_DONE, **{"chat.jsonl": [{"meta": True, "output": "website"}, {"who": "user", "text": BREW_LAB}],
                           "goal.json": {"site_name": "Brew Lab", "statement": "A one-page website."},
                           "summary.json": {"status": "done", "output_type": "website", "brief": BREW_LAB},
                           "change.json": [{"id": "c1", "request": "Add a map", "cycle": 2, "revise": ["a"], "new": []},
                                           {"id": "c2", "request": "Warmer colours", "cycle": 3, "revise": [], "new": ["b", "c"]}]})
    put(PATCH_RUN_STOPPED, **{"chat.jsonl": [{"meta": True, "output": "prd"}, {"who": "user", "text": "Write a PRD for QuickQueue."}],
                              "goal.json": {"statement": "A PRD for QuickQueue. It has two users."}})
    put(PATCH_RUN_BARE, **{"goal.json": {}})
    return PATCH_RUN_STOPPED


def patched_shapes():
    """{"get": {route: {mode: shape}}} recorded from the engine's `views.runlist` and `views.changes` over `write_patch_fixture`:
    the department with runs (`runs`) and one with none (`empty`). Imports the engine, so it needs this checkout on the path."""
    sys.path.insert(0, str(REPO))
    from sutra_app.engine import views
    with tempfile.TemporaryDirectory(prefix="j2-shapes-patched-") as work:
        runs = Path(work) / "runs"
        live = write_patch_fixture(runs)
        memory = views.MemoryPaths(str(Path(work) / "lessons"), str(Path(work) / "playbooks"))
        out = {name: {} for name in PATCH_ROUTES}
        for mode, runs_dir, run_id in (("runs", runs, PATCH_RUN_DONE), ("empty", Path(work) / "none", None)):
            ctx = views.RunCtx("saved" if run_id else "idle", run_id, str(runs_dir / run_id) if run_id else None, str(runs_dir),
                               live if run_id else None, memory)
            for name in PATCH_ROUTES:
                reply = views.VIEWS[name](ctx, {})
                out[name][mode] = shape(reply.code, reply.ctype, reply.body)
    return {"fixture": "write_patch_fixture in scripts/record_api_shapes.py", "get": out}


# ---------------------------------------------------------------------------------------------------------------- the child
def child(source, work):
    """Runs inside the subprocess: J2 at `source`, everything it writes under `work`."""
    sys.dont_write_bytecode = True
    os.chdir(work)
    lib = Path(work) / "library"
    if (Path(source) / "library").is_dir():
        shutil.copytree(Path(source) / "library", lib)
    env = {**SCENARIO_ENV, "J2_RUNS_DIR": f"{work}/runs", "J2_MEMORY_FILE": f"{work}/memory/lessons.jsonl",
           "J2_PLAYBOOK_FILE": f"{work}/memory/playbooks.jsonl", "J2_LIBRARY_DIR": str(lib)}
    os.environ.update(env)
    sys.path.insert(0, source)
    import j2
    import j2_check
    import j2_server
    fake_chrome(j2_check)

    def say(run, text):
        assert run.user_says(text)
        end = time.time() + 120
        while run.status != "waiting":
            assert time.time() < end, "the run did not stop"
            time.sleep(0.01)

    run = j2.J2Run()
    say(run, BREW_LAB)
    assert (run.outcome or "").startswith("Done"), run.outcome
    srv = j2_server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), j2_server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def ask(method, path, body=None):
        req = urllib.request.Request(base + path, None if body is None else json.dumps(body).encode(),
                                     {"Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read()

    def get_json(path):
        return json.loads(ask("GET", path)[2])

    out = {"schema": SCHEMA, "j2_commit": os.environ.get("J2_COMMIT", ""), "scenario_env": SCENARIO_ENV, "maps": sorted(MAPS), "opaque": sorted(OPAQUE),
           "get": {}, "post": {}}
    try:
        j2_server.RUN = run
        name = os.path.basename(run.dir)
        state = get_json("/api/state")
        tree, lib_view, arts = get_json("/api/artifacts/tree"), get_json("/api/library"), get_json("/api/artifacts")
        decisions = get_json("/api/run-templates")["decisions"]
        for mode, run_q in (("live", ""), ("saved", f"run={name}")):
            paths = paths_for(state, tree, lib_view, arts, run_q, decisions)
            out["get"][mode] = {n: shape(*ask("GET", p)) for n, p in paths.items()}
        j2_server.RUN = j2.J2Run()          # idle: a fresh run before any message
        out["get"]["idle"] = {n: shape(*ask("GET", p)) for n, p in paths_for(state, tree, lib_view, arts, "", decisions).items()}
        j2_server.RUN = j2.J2Run()          # the POSTs, in an order a page would use
        post = lambda path, body: shape(*ask("POST", path, body))       # noqa: E731
        out["post"]["output_prd"] = post("/api/output", {"type": "prd"})
        out["post"]["say_empty"] = post("/api/say", {"text": "  "})
        j2_server.RUN.set_output("website")
        out["post"]["say"] = post("/api/say", {"text": BREW_LAB})
        end = time.time() + 120
        while j2_server.RUN.status != "waiting" and time.time() < end:
            time.sleep(0.01)
        out["post"]["output_late"] = post("/api/output", {"type": "website"})
        out["post"]["playbooks_clear"] = post("/api/playbooks/clear", {})
        out["post"]["lessons_clear"] = post("/api/lessons/clear", {})
        out["post"]["reset"] = post("/api/reset", {})
    finally:
        srv.shutdown()
    print(json.dumps(out, indent=1, sort_keys=True))


# ---------------------------------------------------------------------------------------------------------------- the parent
def checkout_of(source, commit):
    """(folder to run J2 from, temp folder to remove or None, commit text). `source` is an extraction of `prototypes/j2` (see the
    module docstring), used as it is; `commit` is only the name recorded as `j2_commit`. Anything else stops here with the recipe."""
    source = Path(source).resolve()
    if not (source / "j2.py").is_file():
        raise SystemExit(f"--source {source} holds no j2.py: it must be an extraction of prototypes/j2, "
                         "`git archive <sha> prototypes/j2 | tar -x --strip-components=2 -C <empty folder>`")
    return source, None, commit


def record(source, commit=BASELINE):
    folder, tmp, full = checkout_of(source, commit)
    work = Path(tempfile.mkdtemp(prefix="j2-shapes-work-"))
    try:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "J2_COMMIT": full}
        for name in list(env):
            if name.startswith(("J2_", "STUDIO_")) and name != "J2_COMMIT":
                del env[name]
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(folder), str(work)],
                             capture_output=True, text=True, env=env, timeout=600)
        if res.returncode:
            raise SystemExit(f"the J2 child failed:\n{res.stderr[-3000:]}")
        return json.loads(res.stdout)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default=os.environ.get("SUTRA_J2_CHECKOUT"),
                    help="an extraction of this repository's prototypes/j2: git archive <sha> prototypes/j2 | tar -x --strip-components=2 -C "
                         "<empty folder> (default: $SUTRA_J2_CHECKOUT, which names such a folder)")
    ap.add_argument("--commit", default=BASELINE, help="the sutra commit the extraction was made from, recorded as j2_commit "
                                                       "(default: the pin of the last sync)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true", help="record again and exit 1 when the file differs")
    ap.add_argument("--patched-only", action="store_true", help="only the patched section (P13), in the existing file; no J2 checkout")
    ap.add_argument("--child", nargs=2, metavar=("SOURCE", "WORK"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.child:
        return child(*a.child)
    out = Path(a.out)
    if a.patched_only:
        data = json.loads(out.read_text(encoding="utf-8"))
        data["patched"] = patched_shapes()
    else:
        if not a.source:
            ap.error("--source (or SUTRA_J2_CHECKOUT) is required")
        data = record(a.source, a.commit)
        data["patched"] = patched_shapes()
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if a.check:
        same = out.is_file() and out.read_text(encoding="utf-8") == text
        print("api shapes: " + ("up to date" if same else "DIFFERENT from " + str(out)))
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(data['get']['live'])} routes x 3 modes, {len(data['post'])} POSTs, {len(data['patched']['get'])} patched routes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
