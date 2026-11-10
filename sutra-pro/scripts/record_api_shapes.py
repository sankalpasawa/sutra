#!/usr/bin/env python3
"""Record the shapes of J2's HTTP API into `tests/engine/golden/api_shapes.json` (work package E2, engine design 9; J2 sync 4, D150).

    scripts/py scripts/record_api_shapes.py --source <an extraction of prototypes/j2> [--commit <sutra commit>] [--out FILE] [--check]

The one J2 this product follows is the folder `prototypes/j2` of this repository. `--source` (or the variable SUTRA_J2_CHECKOUT) is
a new, empty folder it was extracted into with `git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <folder>`, and
`--commit` is that sutra commit (recorded as `j2_commit`; the default is `BASELINE`). An extraction, never the working tree, so an
edited file or a `.pyc` can never matter.

Runs J2's own `j2_server.Handler` from that folder in a child process, in mock mode with the Chrome checks faked as J2's `--fast`
flow does, and with every J2 path under a temp folder (`J2_RUNS_DIR`, memory, library): nothing is written to the extraction. It
drives one Brew Lab run to Done, then asks every GET route in three situations:

    live    no `?run=`: the run that is held by the server
    saved   `?run=<id>`: the same run read from its folder
    idle    a fresh run, before any message

and the POST routes on a fresh run. Per route it keeps the status, the content type and, for a JSON body, the KEY PATHS (the
names of the keys at every depth, `[]` for a list; a map keyed by ids is written with `*`, and so is `enums`, the enum names of a
template version: they are data, a new seed template adds some, D150), never a value: ids and times change between runs, the shape
does not. Every route of J2's server is recorded the same way, `/api/runlist` and `/api/changes` and the routes added in sync 4
(`/api/plan-map`, `/api/activity`, `/api/catalog`, `/api/artifacts/groups`, `/api/record`, `/doc/<name>`, `/view`, `POST /api/ask` and
`POST /api/settings`) included. `tests/engine/test_engine_views.py` runs the same requests against `views.py` and compares. `--check`
records again and exits 1 when the file differs. The module is also imported by that test (and by two library tests) for `key_paths`,
`ROUTES` and the scenario constants, so the two sides ask the same questions.
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
ROUTES = ("state", "state_since", "runs", "runlist", "changes", "call", "call_missing", "preview", "docs", "map", "plan", "plan_map",
          "library", "library_item", "library_missing", "catalog", "run_templates", "artifacts", "agent", "activity", "code",
          "code_missing", "artifacts_tree", "artifacts_groups", "artifact", "artifact_missing", "story", "board", "audits", "refs",
          "shot_missing", "file_missing", "record_part", "record_art", "record_missing", "doc", "view", "view_missing", "site_latest",
          "site_v1", "site_v99", "unknown")
POSTS = ("output_prd", "say_empty", "say", "ask", "ask_refused", "settings", "settings_read", "output_late", "playbooks_clear",
         "lessons_clear", "reset")


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
    parts = (state.get("studio") or {}).get("parts") or []                  # the Simple view's parts: one record each (/api/record?sec=)
    sec = parts[0]["sec"] if parts else "W-1"
    deliverable = next((r["name"] for r in artifacts.get("deliverables", []) if r.get("name")), "site")
    code = next(((r["deck"], r.get("section")) for r in _walk_code(tree)), ("x", None))
    return {
        "state": "/api/state" + q(), "state_since": "/api/state" + q("since=3"), "runs": "/api/runs" + q(),
        "runlist": "/api/runlist" + q(), "changes": "/api/changes" + q(),
        "call": "/api/call" + q("id=1"), "call_missing": "/api/call" + q("id=99999"),
        "preview": "/api/preview" + q(f"atom={atom}"), "docs": "/api/docs" + q(), "map": "/api/map" + q(), "plan": "/api/plan" + q(),
        "plan_map": "/api/plan-map" + q(), "library": "/api/library" + q(),
        "library_item": ("/api/library/%s/%s/%s/v%s" % tpl if tpl else "/api/library/website/x/x/v1") + q(),
        "library_missing": "/api/library/website/none/none/v1" + q(), "catalog": "/api/catalog" + q(),
        "run_templates": "/api/run-templates" + q(), "artifacts": "/api/artifacts" + q(), "agent": "/api/agent" + q("who=identity"),
        "activity": "/api/activity" + q("who=adaptation"),
        "code": "/api/code" + q(f"deck={code[0]}" + (f"&section={code[1]}" if code[1] else "")),
        "code_missing": "/api/code" + q("deck=none"), "artifacts_tree": "/api/artifacts/tree" + q(),
        "artifacts_groups": "/api/artifacts/groups" + q(),
        "artifact": "/api/artifact" + q(f"name={art}"), "artifact_missing": "/api/artifact" + q("name=nothing.txt"),
        "story": "/api/story" + q(), "board": "/api/board" + q(), "audits": "/api/audits" + q(), "refs": "/api/refs" + q(),
        "shot_missing": "/shot/99" + q(), "file_missing": "/file/goal.json" + q(),
        "record_part": "/api/record" + q(f"sec={sec}"), "record_art": "/api/record" + q(f"art={deliverable}"),
        "record_missing": "/api/record" + q("sec=nothing"), "doc": "/doc/prd" + q(), "view": "/view" + q(f"name={art}"),
        "view_missing": "/view" + q("name=nothing.txt"), "site_latest": "/site/latest" + q(),
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
        out["post"]["ask"] = post("/api/ask", {"who": "adaptation", "q": "Why did you plan the work this way?"})      # mock: from the records
        out["post"]["ask_refused"] = post("/api/ask", {"who": "nobody", "q": "Is anyone there?"})
        out["post"]["settings"] = post("/api/settings", {"decide_for_me": True})                 # the Simple view's Decide for me switch
        out["post"]["settings_read"] = post("/api/settings", {})
        out["post"]["output_late"] = post("/api/output", {"type": "website"})
        out["post"]["playbooks_clear"] = post("/api/playbooks/clear", {})
        out["post"]["lessons_clear"] = post("/api/lessons/clear", {})
        out["post"]["reset"] = post("/api/reset", {})
    finally:
        srv.shutdown()
    print(json.dumps(out, indent=1, sort_keys=True))


# ---------------------------------------------------------------------------------------------------------------- the parent
def extraction_of(source):
    """The folder to run J2 from: the extraction of `prototypes/j2` that `--source` names (it must hold J2's own server)."""
    folder = Path(source).resolve()
    if not (folder / "j2_server.py").is_file():
        raise SystemExit(f"{folder} is not an extraction of prototypes/j2 (no j2_server.py in it): make one with "
                         "`git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <new, empty folder>`")
    return folder


def record(source, commit=BASELINE):
    folder = extraction_of(source)
    work = Path(tempfile.mkdtemp(prefix="j2-shapes-work-"))
    try:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "J2_COMMIT": commit}
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default=os.environ.get("SUTRA_J2_CHECKOUT"),
                    help="an extraction of prototypes/j2 (git archive into a new folder); the variable SUTRA_J2_CHECKOUT names it too")
    ap.add_argument("--commit", default=BASELINE, help="the sutra commit the extraction was made from (recorded as j2_commit)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true", help="record again and exit 1 when the file differs")
    ap.add_argument("--child", nargs=2, metavar=("SOURCE", "WORK"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.child:
        return child(*a.child)
    if not a.source:
        ap.error("--source (or SUTRA_J2_CHECKOUT) is required: an extraction of prototypes/j2")
    out = Path(a.out)
    data = record(a.source, a.commit)
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if a.check:
        same = out.is_file() and out.read_text(encoding="utf-8") == text
        print("api shapes: " + ("up to date" if same else "DIFFERENT from " + str(out)))
        return 0 if same else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(data['get']['live'])} routes x 3 modes, {len(data['post'])} POSTs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
