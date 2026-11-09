"""The 30 handlers of J2's server as plain functions (work package E2, engine design 4.6 and 7.1).

    VIEWS[name](ctx: RunCtx, query_or_body: dict) -> Reply

One implementation, two thin adapters: `sutra_app.engine.api` (FastAPI, E4) and `j2_server.py` (the stdlib server of the legacy
tests). A handler never touches a socket, a header or the process: it answers from a `RunCtx`, which says which run the request
is about and where its state comes from:

    live    no `?run=`: the department's current run. `ctx.snap` is `snapshot.json` (what `/api/state` returns, with the whole
            chat), `ctx.extras` is `live.json`, `ctx.dir` is the run folder, `ctx.alive` says whether the process still runs.
    saved   `?run=<id>`: the run folder only, read-only, also while it is running (J2's rule). `ctx.dir` is None when the folder is
            missing: J2's empty shapes follow.
    idle    the department has no run yet or the page was cleared: `ctx.snap` is `idle_snapshot(...)`, `ctx.dir` is None.

The query parameters of J2's routes arrive in the dict (`since`, `id`, `atom`, `who`, `deck`, `section`, `name`); the parts of a
path arrive in it too: `artifact`, `section`, `slug`, `version` ("v3") for `library_item`, `n` for `shot`, `name` for `file`, `key`
for `site`. The three commands (say, output, reset) are done by `ctx.commands` (the orchestrator through `api/`, the in-process run
in the stdlib adapter); the handler keeps J2's validation and J2's body shapes. Bodies are text (or bytes for PNG, DOCX, the page
and the d3 file) and are redacted by the adapter, never here.

`live_state(run)` is the other direction: what the host publishes (`snapshot.json`, `live.json`) built from a `J2Run`.
"""
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple, Union

from . import j2, j2_agent, j2_artifacts, j2_map, j2_story, j2_template_lib, llm
from . import capabilities
from .paths import pid_alive
from .spec import EngineSettings

capabilities.register(j2)        # D126: the API process, the stdlib adapter and the tests see the same outputs as the run process

__all__ = ["Reply", "MemoryPaths", "Commands", "RunCtx", "Published", "VIEWS", "HANDLER_COUNT", "DOCX", "PROCESS_GONE",
           "EMPTY_LIVE", "LIVE_VIEWS", "PATCH_VIEWS", "live_state", "read_published", "idle_snapshot", "effective_snapshot"]

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PROCESS_GONE = "The department process stopped (exit unknown). Try again."      # engine design 4.6
SNAPSHOT_FILE, LIVE_FILE = "snapshot.json", "live.json"
PNG = "image/png"
HANDLER_COUNT = 30        # the rows 1 to 30 of engine design 7.1 ("site" has two rows, saved and live, and one entry in VIEWS)
PATCH_VIEWS = ("runlist", "changes")      # P13: two read-only routes J2's own repository does not have (docs/design/j2-sync-3.md)


@dataclass(frozen=True)
class Reply:
    code: int = 200
    body: Union[str, bytes] = ""
    ctype: str = "application/json"
    name: Optional[str] = None            # the file name of a .docx download
    cache: str = "no-store"


@dataclass
class MemoryPaths:
    lessons: str
    playbooks: str


class Commands(Protocol):
    """What the three POSTs do to the run. The handler validates; this object acts."""

    def say(self, text: str) -> bool: ...                      # False: the run is busy (409)
    def set_output(self, out: Any) -> Tuple[bool, str]: ...    # (accepted, the output type now)
    def reset(self) -> bool: ...                               # False: a run is going on, nothing was touched (409)


@dataclass
class RunCtx:
    mode: str                                     # "live" | "saved" | "idle"
    run_id: Optional[str]
    dir: Optional[str]
    runs_dir: str                                 # this department's folder of runs (the list of /api/runs)
    live_id: Optional[str]                        # the live run's id, "" when there is none
    memory: MemoryPaths
    snap: Optional[dict] = None                   # live and idle: the published snapshot
    extras: Optional[dict] = None                 # live: live.json
    alive: bool = True                            # live: the run's process exists
    dept_id: Optional[str] = None                 # E2 addition: only for the additive `dept_id` key of the live state
    commands: Optional[Commands] = None           # E2 addition: the three POSTs
    here: Optional[str] = None                    # E2 addition: the folder of j2_ui.html, stdlib adapter only
    vendor: Optional[str] = None                  # E2 addition: the folder of d3.min.js, stdlib adapter only


@dataclass(frozen=True)
class Published:
    snap: dict
    live: dict
    alive: bool


EMPTY_LIVE = {"schema": "engine-live/1", "pid": None, "at": "", "output": "website", "doc": False, "out_label": "Website",
              "docset": [], "stages": [], "stage_i": 0, "docs": {}, "board": {"schema": "board/1", "entries": []},
              "site_tag": "", "sites": 0}


# ------------------------------------------------------------------------------------------------------------- publishing
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def live_state(run) -> Tuple[dict, dict]:
    """(snapshot, live) of a `J2Run`: what the host writes as `snapshot.json` and `live.json`, and what the stdlib adapter
    reads per request."""
    snap = {**run.snapshot(0), "saved": None}
    live = {"schema": "engine-live/1", "pid": os.getpid(), "at": _now(), "output": run.output, "doc": bool(run.doc),
            "out_label": run.out["label"], "docset": list(run.docset), "stages": list(run.stages), "stage_i": run.stage_i,
            "docs": run.docs, "board": run.board, "site_tag": run.site_tag, "sites": len(run.sites)}
    return snap, live


def _load_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_published(run_dir) -> Optional[Published]:
    """The published state of a run folder; None when there is no (readable) `snapshot.json`. A missing or torn `live.json`
    reads as {}. `alive` is whether the pid in `live.json` exists; with no pid it is True (nothing says it is gone)."""
    d = os.fspath(run_dir)
    snap = _load_json(os.path.join(d, SNAPSHOT_FILE))
    if snap is None:
        return None
    live = _load_json(os.path.join(d, LIVE_FILE)) or {}
    pid = live.get("pid")
    return Published(snap, live, pid_alive(pid) if isinstance(pid, int) and not isinstance(pid, bool) else True)


_IDLE_LOCK = threading.Lock()


def _rows(path: str) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip().startswith("{")]
    except (OSError, ValueError):
        return []


def idle_snapshot(settings: EngineSettings, memory: MemoryPaths, run_id: str) -> dict:
    """What `/api/state` answers while the department has no run (the 56 keys of `J2Run.snapshot`; `state` adds `saved`): the
    snapshot of a throw-away `J2Run` (its folder does not exist and is never made), with the department's settings laid over it. J2 reads its flags into module globals when a run
    is built, so the throw-away runs under a lock and the two it changes (`RATES`, `OUTPUT`) are put back."""
    missing = os.path.join(tempfile.gettempdir(), f"sutra-idle-{os.getpid()}", str(run_id))
    with _IDLE_LOCK:
        rates, output = j2.RATES, j2.OUTPUT
        try:
            snap = j2.J2Run(run_dir=missing, run_id=str(run_id)).snapshot(0)
        finally:
            j2.RATES, j2.OUTPUT = rates, output
    mock = llm.env_mock()
    out = j2.output_type(settings.output)
    memory_on = bool(settings.memory)
    snap.update({"fixes": int(settings.fixes), "mock": mock, "model": None, "budget": settings.budget, "memory": memory_on,
                 "lessons": _rows(memory.lessons) if memory_on else [], "playbooks": _rows(memory.playbooks) if memory_on else [],
                 **j2.output_info(out, missing, [], [])})
    return snap


# ------------------------------------------------------------------------------------------------------------------ helpers
def _json(obj: Any, code: int = 200) -> Reply:
    return Reply(code, json.dumps(obj, ensure_ascii=False))


def _text(body: str, code: int = 200, ctype: str = "text/plain") -> Reply:
    return Reply(code, body, ctype)


def _not_found() -> Reply:
    return _text("not found", 404)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dir(ctx: RunCtx) -> Optional[str]:
    """The run folder when it exists (J2's `d if d and os.path.isdir(d) else None`)."""
    return ctx.dir if ctx.dir and os.path.isdir(ctx.dir) else None


def _saved(ctx: RunCtx) -> bool:
    return ctx.mode == "saved"


def _live_dict(ctx: RunCtx) -> dict:
    return {**EMPTY_LIVE, **(ctx.extras or {})}


def effective_snapshot(ctx: RunCtx) -> dict:
    """The published snapshot with the process-gone rule: when the process is gone and the snapshot still says running, the
    run is waiting and has an error (engine design 4.6)."""
    snap = ctx.snap or {}
    if not ctx.alive and snap.get("status") == "running":
        return {**snap, "status": "waiting", "error": PROCESS_GONE}
    return snap


def _running_or_paused(snap: dict) -> bool:
    return snap.get("status") == "running" or bool(snap.get("paused"))


def _live_map_input(ctx: RunCtx) -> Optional[dict]:
    """The `live` argument of `j2_map.build` and `j2_artifacts.tree`: only while the run is running or paused."""
    if _saved(ctx):
        return None
    snap = effective_snapshot(ctx)
    if not _running_or_paused(snap):
        return None
    return {"snapshot": snap, "stages": list(_live_dict(ctx)["stages"]), "stage_words": j2.J2Run.STAGE_WORDS,
            "board": _live_dict(ctx)["board"]}


def _site_path(ctx: RunCtx, version: int) -> Optional[str]:
    """The file of version `version` of the live run's page: `site/v<n>.html`, or `site/<tag>v<n>.md` for a document."""
    d = _dir(ctx)
    if not d:
        return None
    live = _live_dict(ctx)
    return os.path.join(d, "site", f"{live['site_tag']}v{version}.md" if live["doc"] else f"v{version}.html")


def _read_text(path: Optional[str]) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, TypeError):
        return ""


def _live_page(ctx: RunCtx, version: Optional[int] = None) -> str:
    """The text of the live run's page version (default: the latest), "" when there is none."""
    n = _live_dict(ctx)["sites"]
    return _read_text(_site_path(ctx, version or n)) if n else ""


# ---------------------------------------------------------------------------------------------------------- rows 1 and 2
def index(ctx: RunCtx, q: dict) -> Reply:
    """Row 1: J2's own page, only when the adapter was given the folder (`SUTRA_J2_CHECKOUT`)."""
    if not ctx.here:
        return _not_found()
    try:
        with open(os.path.join(ctx.here, "j2_ui.html"), encoding="utf-8") as f:
            return Reply(200, f.read(), "text/html")
    except OSError:
        return _not_found()


def vendor(ctx: RunCtx, q: dict) -> Reply:
    """Row 2: the d3 file the Map's Tree view needs."""
    if not ctx.vendor:
        return _not_found()
    try:
        with open(os.path.join(ctx.vendor, "d3.min.js"), "rb") as f:
            return Reply(200, f.read(), "text/javascript", cache="max-age=3600")
    except OSError:
        return _not_found()


# ---------------------------------------------------------------------------------------------------------- rows 3 to 9
def state(ctx: RunCtx, q: dict) -> Reply:
    since = max(0, _int(q.get("since"), 0))
    if _saved(ctx):
        d = _dir(ctx)
        snap = j2.saved_snapshot_dir(d, ctx.run_id, since) if d else None
    elif ctx.snap is None:
        snap = None
    else:
        base = effective_snapshot(ctx)
        snap = {**base, "saved": None, "chat": (base.get("chat") or [])[since:]}
        if ctx.mode == "live":              # additive keys (engine design 4.6): the process, the run and the department
            snap.update(host={"pid": _live_dict(ctx)["pid"], "alive": ctx.alive}, run_id=ctx.run_id, dept_id=ctx.dept_id)
    return _json(snap) if snap else _json({"error": "no such run"}, 404)


def runs(ctx: RunCtx, q: dict) -> Reply:
    return _json({"live": ctx.live_id or "", "runs": j2.list_runs(runs_dir=ctx.runs_dir)})


def runlist(ctx: RunCtx, q: dict) -> Reply:
    """P13: Run settings' list of this department's saved runs, newest first (`j2.run_list`). The live run reads `running`
    only while its process is alive and its snapshot says so; `?run=` is not used: the list is about the department."""
    running = ctx.mode == "live" and ctx.alive and (ctx.snap or {}).get("status") == "running"
    return _json(j2.run_list(ctx.runs_dir, ctx.live_id or "", bool(running)))


def changes(ctx: RunCtx, q: dict) -> Reply:
    """P13: the build journey's stops, one per change request of the run's `change.json` (`j2.run_changes`); none: an empty list."""
    return _json(j2.run_changes(_dir(ctx)))


def call(ctx: RunCtx, q: dict) -> Reply:
    rec = j2.call_record(_dir(ctx), _int(q.get("id"), 0))
    return _json(rec) if rec else _json({"error": "no such call"}, 404)


def preview(ctx: RunCtx, q: dict) -> Reply:
    """An atom's section by its anchor id, from the built page, for the atom card's frame."""
    d = _dir(ctx)
    live = not _saved(ctx)
    wfs = (ctx.snap or {}).get("workflows") or [] if live else (j2._read(d, "workflows.json", []) if d else [])
    at = next((a for w in wfs for a in w.get("atoms") or [] if a["id"] == q.get("atom")), None)
    ao = (at or {}).get("agent_output") or {}
    if ao.get("kind") == "doc":          # a document atom: its section as the page renders markdown
        body = j2.atom_section_body(d, wfs, q.get("atom")) if d else None
        return _json({"anchor": None, "html": j2.md_html(body, "Section") if body else None})
    anchor = ao.get("anchor")
    if live:
        page = _live_page(ctx)
    else:
        page = _read_text(os.path.join(d, "site", "index.html")) if d else ""
    return _json({"anchor": anchor, "html": j2.preview_doc(page, anchor) if anchor else None})


def docs(ctx: RunCtx, q: dict) -> Reply:
    """The Documents tab: prd.md, hld.md, lld.md of a run, read-only, only those names."""
    d = _dir(ctx)
    live = _live_dict(ctx)
    made = (j2._read(d, "documents.json", {}) if d else {}) if _saved(ctx) else live["docs"]
    out = {}
    for k in ("prd", "hld", "lld"):
        try:
            with open(os.path.join(d, f"{k}.md"), encoding="utf-8") as f:
                text = f.read()
        except (OSError, TypeError):
            text = None
        out[k] = {"asked": text is not None or k in made or (not _saved(ctx) and k in live["docset"]), "text": text,
                  "workflows": (made.get(k) or {}).get("workflows", [])}
    return _json(out)


def map(ctx: RunCtx, q: dict) -> Reply:       # noqa: A001 - the row's name
    """The Map tab: the run's work in order (map/1); a running run is drawn from its live state."""
    return _json(j2_map.build(_dir(ctx), _live_map_input(ctx)))


def plan(ctx: RunCtx, q: dict) -> Reply:
    return _json(j2_map.plan_view(_dir(ctx)))


# --------------------------------------------------------------------------------------------------------- rows 10 to 12
def library(ctx: RunCtx, q: dict) -> Reply:
    return _json(j2_template_lib.library_view())


def library_item(ctx: RunCtx, q: dict) -> Reply:
    """One template version: `artifact`, `section`, `slug` and `version` ("v3") of /api/library/<a>/<s>/<slug>/v<N>. A run that
    used it serves its own copy first (J2 sync 2026-11-04): the view passes the run folder."""
    artifact, section, slug, version = (str(q.get(k) or "") for k in ("artifact", "section", "slug", "version"))
    ok = (artifact in j2_template_lib.ARTIFACTS and all(re.fullmatch(r"[a-z0-9-]+", x) for x in (section, slug))
          and re.fullmatch(r"v[0-9]+", version))
    d = _dir(ctx)
    got = j2_template_lib.template_view(artifact, section, slug, int(version[1:]), run_dir=d) if ok else None
    if got and d:      # an example filled from this run's data, when the run used it
        got["example"] = j2_template_lib.run_example(d, got["template"], slug)
    return _json(got) if got else _json({"error": "no such template"}, 404)


def run_templates(ctx: RunCtx, q: dict) -> Reply:
    """This run's routing decisions, each with where its template is read from; none recorded: an empty list."""
    d = _dir(ctx)
    return _json({"decisions": j2_template_lib.run_templates(d) if d else []})


# --------------------------------------------------------------------------------------------------------- rows 13 to 17
def artifacts(ctx: RunCtx, q: dict) -> Reply:
    return _json(j2_artifacts.listing(_dir(ctx)))


def agent(ctx: RunCtx, q: dict) -> Reply:
    return _json(j2_agent.view(_dir(ctx), q.get("who")))


def code(ctx: RunCtx, q: dict) -> Reply:
    txt = j2_artifacts.code_text(_dir(ctx), q.get("deck"), q.get("section"))
    return _text(txt) if txt is not None else _not_found()


def artifacts_tree(ctx: RunCtx, q: dict) -> Reply:
    d = _dir(ctx)
    return _json(j2_artifacts.tree(d, j2_map.build(d, _live_map_input(ctx))) if d else j2_artifacts.tree(None))


def artifact(ctx: RunCtx, q: dict) -> Reply:
    """One file the run's artifact list names, read-only; nothing else is served."""
    p = j2_artifacts.served(_dir(ctx), q.get("name"))
    if not p:
        return _not_found()
    ext = os.path.splitext(p)[1]
    with open(p, "rb") as f:
        data = f.read()
    if ext == ".png":
        return Reply(200, data, PNG)
    if ext == ".docx":
        return Reply(200, data, DOCX, os.path.basename(p))
    return Reply(200, data, "text/html" if ext == ".html" else "text/plain")


# --------------------------------------------------------------------------------------------------------- rows 18 to 21
def story(ctx: RunCtx, q: dict) -> Reply:
    """The Board story view (story/1), live or saved."""
    live = None
    if not _saved(ctx):
        snap = effective_snapshot(ctx)
        if snap.get("status") in ("running", "waiting") or snap.get("paused"):
            live = {"snapshot": snap, "board": _live_dict(ctx)["board"]}
    return _json(j2_story.build(_dir(ctx), live))


def board(ctx: RunCtx, q: dict) -> Reply:
    """The Board tab (board/1): the live board while the run runs or waits, else board.json."""
    if not _saved(ctx):
        snap = effective_snapshot(ctx)
        if snap.get("status") in ("running", "waiting") or snap.get("paused"):
            return _json(_live_dict(ctx)["board"])
    d = _dir(ctx)
    out = j2._read(d, "board.json", {}) if d else {}
    return _json(out or {"schema": "board/1", "entries": []})


def audits(ctx: RunCtx, q: dict) -> Reply:
    """Earlier stages' audits, condensed to ids and results, for a revise atom's Fixes line."""
    d = _dir(ctx)
    pick = lambda rows, *keys: [{k: r.get(k) for k in keys if k in r} for r in rows or []]      # noqa: E731
    out = [{"stage": st.get("stage"), "cycle": a.get("cycle"), "results": pick(a.get("results"), "id", "verdict", "pass"),
            "extra_issues": pick(a.get("extra_issues"), "id", "verdict"), "rubric": pick(a.get("rubric"), "id", "verdict", "pass"),
            "conditions": pick(a.get("conditions"), "id", "met")}
           for f in sorted(os.listdir(d) if d else []) if re.fullmatch(r"stage-\w+\.json", f)
           for st in [j2._read(d, f, {}) or {}] for a in st.get("audits") or []]
    return _json(out)


def refs(ctx: RunCtx, q: dict) -> Reply:
    """Ids the cards name, with their text: conditions/*.json and every output type's rubric."""
    conds = {}
    for n in ("website", "prd", "hld", "lld"):
        conds.update({c["id"]: c["text"] for c in j2.load_conditions(f"{n}.json")})
    rub = {i: t for o in j2.OUTPUTS.values() for i, t in o.get("rubric") or ()}
    return _json({"conditions": conds, "rubric": rub})


# --------------------------------------------------------------------------------------------------------- rows 22 to 25
def shot(ctx: RunCtx, q: dict) -> Reply:
    """The screenshot Audit looked at for site vN."""
    d, n = _dir(ctx), str(q.get("n") or "")
    path = os.path.join(d or "", "site", "shots", f"v{n}.png")
    if not (d and re.fullmatch(r"[0-9]+", n) and os.path.exists(path)):
        return _not_found()
    with open(path, "rb") as f:
        return Reply(200, f.read(), PNG)


def file(ctx: RunCtx, q: dict) -> Reply:
    """A document run's prd.md or prd.docx, to download; only the names the output allows."""
    d, name = _dir(ctx), str(q.get("name") or "")
    out = j2.saved_output(d) if _saved(ctx) else _live_dict(ctx)["output"]
    o = j2.OUTPUTS.get(out) or j2.OUTPUTS["website"]
    allowed = [o["file"], o["file"][:-3] + ".docx"] if o.get("file") else []
    allowed += [f for k in j2._read(d or "", "documents.json", {}) for f in (f"{k}.md", f"{k}.docx")]   # design documents
    path = os.path.join(d or "", name)
    if name not in allowed or not os.path.exists(path):
        return _not_found()
    with open(path, "rb") as f:
        data = f.read()
    return Reply(200, data, DOCX, name) if name.endswith(".docx") else Reply(200, data, "text/markdown")


def site_saved(ctx: RunCtx, q: dict) -> Reply:
    """Row 24: a saved run's page (`latest` or `vN`), or the "No site in this run" stub."""
    d, key = _dir(ctx), str(q.get("key") or "")
    site = os.path.join(d or "", "site")
    num = lambda f: int(f[1:].split(".")[0])         # noqa: E731
    vs = sorted((f for f in os.listdir(site) if re.fullmatch(r"v[0-9]+\.(?:html|md)", f)), key=num) \
        if d and os.path.isdir(site) else []
    name = vs[-1] if key == "latest" and vs else next((f for f in vs if f.split(".")[0] == key), None)
    if not name:
        return Reply(200, "<p style='font:14px system-ui;color:#667;padding:24px'>No site in this run.</p>", "text/html")
    text = _read_text(os.path.join(site, name))
    return Reply(200, j2.md_html(text) if name.endswith(".md") else text, "text/html")


def site_live(ctx: RunCtx, q: dict) -> Reply:
    """Row 25: the live page (markdown rendered for documents) or the "will appear" stub; 404 out of range."""
    live = _live_dict(ctx)
    n = live["sites"]
    if not n:
        return Reply(200, "<p style='font:15px system-ui;color:#667;padding:24px'>Your "
                          f"{'document' if live['doc'] else 'website'} will appear here once it's built.</p>", "text/html")
    key = str(q.get("key") or "")
    i = n if key == "latest" else _int(key.lstrip("v") or 0, 0)         # J2: int(key.lstrip("v") or 0)
    if not 1 <= i <= n:
        return _not_found()
    text = _live_page(ctx, i)
    return Reply(200, j2.md_html(text, live["out_label"]) if live["doc"] else text, "text/html")


def site(ctx: RunCtx, q: dict) -> Reply:
    return site_saved(ctx, q) if _saved(ctx) else site_live(ctx, q)


# --------------------------------------------------------------------------------------------------------- rows 26 to 30
def _no_commands() -> Reply:
    return _json({"error": "this adapter has no command object"}, 501)


def say(ctx: RunCtx, body: dict) -> Reply:
    text = body.get("text")
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        return _json({"error": "empty"}, 400)
    if ctx.commands is None:
        return _no_commands()
    ok = bool(ctx.commands.say(text))
    return _json({"ok": ok}, 200 if ok else 409)


def playbooks_clear(ctx: RunCtx, body: dict) -> Reply:
    return _json({"ok": True, "cleared": j2.clear_playbooks(ctx.memory.playbooks)})


def lessons_clear(ctx: RunCtx, body: dict) -> Reply:
    return _json({"ok": True, "cleared": j2.clear_lessons(ctx.memory.lessons)})


def output(ctx: RunCtx, body: dict) -> Reply:
    """The start page's output type, before the first message."""
    if ctx.commands is None:
        return _no_commands()
    ok, out = ctx.commands.set_output(body.get("type"))
    return _json({"ok": bool(ok), "output": out}, 200 if ok else 409)


def reset(ctx: RunCtx, body: dict) -> Reply:
    if ctx.commands is None:
        return _no_commands()
    ok = bool(ctx.commands.reset())
    return _json({"ok": ok}, 200 if ok else 409)


VIEWS: Dict[str, Callable[[RunCtx, dict], Reply]] = {fn.__name__: fn for fn in (
    index, vendor, state, runs, call, preview, docs, map, plan, library, library_item, run_templates, artifacts, agent, code,
    artifacts_tree, artifact, story, board, audits, refs, shot, file, site, say, playbooks_clear, lessons_clear, output, reset,
    runlist, changes)}

# What a request needs from the live run (the stdlib adapter builds `live_state` only for these; the others read the folder).
LIVE_VIEWS = frozenset({"state", "runlist", "preview", "docs", "map", "artifacts_tree", "story", "board", "file", "site"})
