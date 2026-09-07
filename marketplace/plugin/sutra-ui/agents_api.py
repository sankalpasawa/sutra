"""agents_api.py -- the SEO Writer's routes, mounted at /api/agents/seo.

Thin on purpose. Every handler does one of two things: read a file the engine already
wrote, or kick the engine's loop on a background thread and return. No business logic
lives here, because anything clever in an HTTP handler is logic that cannot be tested
without a server running. The engine is the `seo_agent` package beside this file; it
imports nothing from sutra-ui, so it keeps working if this panel is not there.

Two things are sutra-ui's to decide, and they are decided here:

  * which `claude` binary the agent drives -- the one providers.py resolved for the chat,
    so the agent bills the same subscription and follows the same PATH repair;
  * where the agent's data lives -- ~/.sutra-ui/agents/seo, beside the panel's own
    settings, never inside the read-only bundle.

Origin and panel-token checks are the app-level middleware's job (app.py:_origin_guard),
so a POST here is already known to come from this panel or from a local, origin-less
client.
"""
import os
import re
import threading
import traceback

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

import providers
from seo_agent import llm, loop, registry, store

router = APIRouter(prefix="/api/agents/seo", tags=["agents"])

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _bad(msg, code=400):
    return JSONResponse({"detail": msg}, status_code=code)


def _ok_id(*ids):
    return all(isinstance(i, str) and _ID.match(i) and ".." not in i for i in ids)


# ---- the claude binary -------------------------------------------------------------------

def _sync_claude_bin():
    """Hand the agent the same `claude` the chat drives. providers.py owns detection
    (login-shell PATH, settings override, env override); this only carries the answer."""
    try:
        path = providers.provider_bin("claude")
    except Exception:
        path = None
    if path:
        os.environ["SEO_AGENT_CLAUDE_BIN"] = path
    return path


_sync_claude_bin()


# ---- one worker per run --------------------------------------------------------------------

_workers = {}
_lock = threading.Lock()


def _spawn(key, fn):
    """Start fn on a daemon thread unless the same run already has a live worker."""
    with _lock:
        t = _workers.get(key)
        if t and t.is_alive():
            return False
        th = threading.Thread(target=fn, daemon=True, name="seo-agent:" + key)
        _workers[key] = th
        th.start()
        return True


def _guarded(chat_id, run_id, fn):
    """A crash inside the loop lands in the run's own log, never silently in a thread."""
    def wrapped():
        try:
            fn()
        except Exception as e:  # noqa: BLE001 -- the whole point is to catch everything
            store.emit(chat_id, run_id, "step_failed", label="Run",
                       reason=str(e)[:400], detail=traceback.format_exc()[-1500:],
                       recovering=False)
            store.patch_state(chat_id, run_id, status="failed", error=str(e)[:400])
    return wrapped


def _live_status(chat_id):
    runs = store.list_runs(chat_id)
    for r in reversed(runs):
        if r.get("status") in ("running", "waiting"):
            return r["status"]
    return None


# ---- chats -----------------------------------------------------------------------------------

@router.get("/chats")
def api_chats():
    out = []
    for c in store.list_chats():
        c = dict(c)
        c["live"] = _live_status(c["id"])
        out.append(c)
    return out


@router.post("/chats")
def api_new_chat(body: dict = Body(default={})):
    title = (body.get("title") or "New chat").strip()[:80]
    cid = store.new_chat(title or "New chat")
    return {"id": cid, "title": title, "live": None}


@router.get("/chats/{chat_id}")
def api_chat(chat_id: str):
    if not _ok_id(chat_id):
        return _bad("bad id")
    meta = store.read_json(os.path.join(store.chat_dir(chat_id), "chat.json"))
    if not meta:
        return _bad("no such chat", 404)
    return {"chat": meta, "messages": store.get_messages(chat_id), "runs": store.list_runs(chat_id)}


@router.post("/chats/{chat_id}/send")
def api_send(chat_id: str, body: dict = Body(...)):
    """A message. If a run is waiting on the user, this IS the answer; if one is running,
    say so instead of starting a second; otherwise it starts a new run."""
    if not _ok_id(chat_id):
        return _bad("bad id")
    text = (body.get("text") or "").strip()
    if not text:
        return _bad("empty")
    if not store.read_json(os.path.join(store.chat_dir(chat_id), "chat.json")):
        return _bad("no such chat", 404)

    runs = store.list_runs(chat_id)
    live = [r for r in runs if r.get("status") in ("running", "waiting")]
    if live:
        run = live[-1]
        run_id = run["run_id"]
        if run["status"] == "running":
            return _bad("The agent is still working. Stop it first, or wait.", 409)
        w = run.get("waiting_on") or {}
        if w.get("kind") == "approval":
            answer = {"approved": False, "note": text}
        elif w.get("kind") == "artifact":
            answer = {"approved": False, "changes": text}
        else:
            answer = {"text": text}
        _sync_claude_bin()
        _spawn(chat_id + run_id, _guarded(chat_id, run_id,
                                          lambda: loop.resume(chat_id, run_id, answer)))
        return {"run_id": run_id, "answered": True, "state": store.get_state(chat_id, run_id)}

    run_id = store.new_run(chat_id, text[:60])
    store.patch_state(chat_id, run_id, request=text)
    if len(runs) == 0:
        store.set_chat_title(chat_id, text[:60])
    _sync_claude_bin()
    _spawn(chat_id + run_id, _guarded(chat_id, run_id,
                                      lambda: loop.start(chat_id, run_id, text)))
    return {"run_id": run_id, "answered": False, "state": store.get_state(chat_id, run_id)}


# ---- runs ------------------------------------------------------------------------------------

@router.get("/runs/{chat_id}/{run_id}")
def api_run(chat_id: str, run_id: str):
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    s = store.get_state(chat_id, run_id)
    return s or _bad("no such run", 404)


@router.get("/runs/{chat_id}/{run_id}/events")
def api_events(chat_id: str, run_id: str, since: int = 0):
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    since = max(0, int(since or 0))
    evs = store.get_events(chat_id, run_id, since)
    return {"events": evs, "next": since + len(evs), "state": store.get_state(chat_id, run_id)}


@router.get("/runs/{chat_id}/{run_id}/trail")
def api_trail(chat_id: str, run_id: str):
    """The research evidence trail: every step's own working file, named in plain English.

    The port of the original's numbered proof/ folder. Without this the only way to check a
    research run was to read raw JSON off disk.
    """
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    try:
        from seo_agent.research import render
        return {"rows": render.trail(chat_id, run_id, store)}
    except Exception as e:  # noqa: BLE001
        return {"rows": [], "error": str(e)[:200]}


@router.get("/runs/{chat_id}/{run_id}/work/{name}")
def api_work_file(chat_id: str, run_id: str, name: str):
    """One working file from the trail. Read only, and only files the trail itself names, so a
    path can never be used to reach outside the run."""
    if not _ok_id(chat_id, run_id) or not _NAME.match(name or ""):
        return _bad("bad name")
    from seo_agent.research import render
    if name not in {f for f, _l, _n in render.TRAIL}:
        return _bad("not a trail file", 404)
    data = store.load_artifact(chat_id, run_id, "_work/" + name)
    if data is None:
        return _bad("not found", 404)
    label = next((l for f, l, _n in render.TRAIL if f == name), name)
    return {"name": name, "label": label,
            "data": data if isinstance(data, (dict, list)) else {"text": data}}


@router.get("/runs/{chat_id}/{run_id}/artifact/{name}")
def api_artifact(chat_id: str, run_id: str, name: str):
    if not _ok_id(chat_id, run_id) or not _NAME.match(name or ""):
        return _bad("bad name")
    if name == "brand":
        return _brand_pack()
    data = store.load_artifact(chat_id, run_id, name)
    if data is None:
        return _bad("not found", 404)
    return data if isinstance(data, (dict, list)) else {"text": data}


def _brand_pack():
    """The brand pack as the screen shows it: one row per file, with review flags."""
    try:
        from seo_agent.brand import pack
        out = pack.summary()
        # the company record is built by the crawler, not a brand builder, so the pack does not
        # list it; the screen shows it as a file all the same
        if not any(f.get("name") == "company.json" for f in out.get("files", [])):
            rec = store.knowledge("brand/company.json")
            out.setdefault("files", []).insert(0, {"name": "company.json", "exists": bool(rec),
                                                   "words": len(__import__("json").dumps(rec or {}).split()),
                                                   "flags": 0 if (rec or {}).get("brand_oneliner") else 1})
        return out
    except Exception:  # noqa: BLE001 -- the builder may not be installed yet; list what is on disk
        files = []
        for name in store.list_knowledge("brand"):
            base = name.split("/", 1)[1]
            text = store.knowledge(name)
            body = text if isinstance(text, str) else __import__("json").dumps(text)
            files.append({"name": base, "exists": True, "words": len(body.split()),
                          "flags": body.count("\u26a0")})
        return {"files": files, "needs_review": []}


@router.post("/runs/{chat_id}/{run_id}/artifact/{name}")
def api_save_artifact(chat_id: str, run_id: str, name: str, body: dict = Body(...)):
    """The user edited an artifact by hand (reordered the blueprint, say). Save exactly what
    they sent, run the checks for that kind, and log it. The next step reads the file, so
    the agent continues from THEIR version with no special code."""
    if not _ok_id(chat_id, run_id) or not _NAME.match(name or ""):
        return _bad("bad name")
    if store.load_artifact(chat_id, run_id, name) is None:
        return _bad("not found", 404)
    data = body.get("data")
    if data is None:
        return _bad("nothing to save")
    store.save_artifact(chat_id, run_id, name, data)
    checks = None
    if name.startswith("blueprint") and isinstance(data, dict):
        from seo_agent.checks import run_checks
        checks = run_checks("blueprint", data, ctx={"chat_id": chat_id, "run_id": run_id})
    store.emit(chat_id, run_id, "edited", artifact=name, block="*", instruction="edited by hand")
    return {"ok": True, "checks": checks}


@router.post("/runs/{chat_id}/{run_id}/answer")
def api_answer(chat_id: str, run_id: str, body: dict = Body(...)):
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    state = store.get_state(chat_id, run_id)
    if not state:
        return _bad("no such run", 404)
    if state.get("status") != "waiting":
        return _bad("This run is not waiting for an answer.", 409)
    answer = body.get("answer", {})
    if not isinstance(answer, dict):
        answer = {"text": str(answer)}
    _sync_claude_bin()
    _spawn(chat_id + run_id, _guarded(chat_id, run_id,
                                      lambda: loop.resume(chat_id, run_id, answer)))
    return {"state": store.get_state(chat_id, run_id)}


@router.post("/runs/{chat_id}/{run_id}/stop")
def api_stop(chat_id: str, run_id: str):
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    if not store.get_state(chat_id, run_id):
        return _bad("no such run", 404)
    return {"state": loop.stop(chat_id, run_id)}


@router.post("/runs/{chat_id}/{run_id}/edit")
def api_edit(chat_id: str, run_id: str, body: dict = Body(...)):
    """Targeted edit: rewrite one block, prove nothing else moved, then check."""
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    import json as _json
    from seo_agent.checks import run_checks
    from seo_agent.editing.edit_block import edit_block
    from seo_agent.editing.make_diff import make_diff

    name = body.get("artifact", "")
    block_id = body.get("block_id", "")
    instruction = (body.get("instruction") or "").strip()
    if not _NAME.match(name or "") or not instruction:
        return _bad("artifact and instruction are needed")
    old = store.load_artifact(chat_id, run_id, name)
    if old is None:
        return _bad("no such artifact", 404)
    _sync_claude_bin()
    try:
        res = edit_block(old, block_id, instruction,
                         context={"chat_id": chat_id, "run_id": run_id})
    except Exception as e:  # noqa: BLE001 -- BlockDrift, ValueError, NoKey all read the same to the user
        return _bad(str(e)[:400])
    new = res["new"]
    store.save_artifact(chat_id, run_id, name, new)
    kind = "blueprint" if name.startswith("blueprint") else "draft"
    checks = run_checks(kind, new, previous=old, ctx={"chat_id": chat_id, "run_id": run_id})
    old_text = old if isinstance(old, str) else _json.dumps(old, indent=2, sort_keys=True)
    new_text = new if isinstance(new, str) else _json.dumps(new, indent=2, sort_keys=True)
    store.emit(chat_id, run_id, "edited", artifact=name, block=block_id, instruction=instruction)
    return {"ok": True, "checks": checks, "diff": make_diff(old_text, new_text),
            "changed_blocks": res.get("changed_blocks", [])}


@router.post("/runs/{chat_id}/{run_id}/publish")
def api_publish(chat_id: str, run_id: str, body: dict = Body(default={})):
    """'Publish' means: save to the Library. Nothing leaves this machine."""
    if not _ok_id(chat_id, run_id):
        return _bad("bad id")
    saved = loop.save_to_library(chat_id, run_id, title=body.get("title"))
    if not saved:
        return _bad("There is no draft to save yet.", 404)
    return {"ok": True, "item_id": saved["item_id"], "title": saved["title"]}


# ---- knowledge / memory / connections / tools ----------------------------------------------

@router.get("/knowledge")
def api_knowledge():
    """Everything the Knowledge screen shows, light. Page bodies and the embedding map have
    their own routes because a 10,000-page site does not fit in one reply."""
    idx = store.knowledge("site_index.json") or {}
    pages = idx.get("pages") if isinstance(idx, dict) else (idx if isinstance(idx, list) else [])
    pages = pages or []
    light = dict(idx) if isinstance(idx, dict) else {}
    light.pop("pages", None)
    types = {}
    for p in pages:
        types[p.get("type") or "page"] = types.get(p.get("type") or "page", 0) + 1
    light.update({"page_count": len(pages), "types": types,
                  "ranking_pages": sum(1 for p in pages if p.get("top_keyword")),
                  "ok_pages": sum(1 for p in pages if (p.get("body_status") or "ok") == "ok")})
    try:
        from seo_agent.tools import _index
        page_index = _index.status()
    except Exception:  # noqa: BLE001
        page_index = {"built": False}
    return {"site_index": light,
            "report": store.knowledge("catalogue-report.json"),
            "top_pages": (store.knowledge("top-pages.json") or [])[:25],
            "page_index": page_index,
            "brand": _brand_pack(),
            "company": store.knowledge("brand/company.json") or {},
            "brand_voice": store.knowledge("brand_voice.json"),
            "competitors": store.knowledge("competitors.json")}


@router.get("/knowledge/pages")
def api_knowledge_pages(offset: int = 0, limit: int = 50, q: str = "", type: str = ""):
    """A page of the catalogue: searchable by title or url, filterable by type, sorted by
    traffic then title. Light rows only."""
    idx = store.knowledge("site_index.json") or {}
    pages = idx.get("pages") if isinstance(idx, dict) else (idx if isinstance(idx, list) else [])
    pages = pages or []
    ql = (q or "").strip().lower()
    if ql:
        pages = [p for p in pages if ql in (p.get("title") or "").lower() or ql in (p.get("url") or "").lower()
                 or ql in (p.get("top_keyword") or "").lower()]
    if type:
        pages = [p for p in pages if (p.get("type") or "page") == type]
    # Traffic first, then the fullest pages. Found live 2026-09-04: with no traffic pulled, every
    # page sorted equal and the 31 pages whose text failed came out on top, so a catalogue that is
    # 99.7% clean opened on a screen of red. A page that could not be read is never the first row.
    pages.sort(key=lambda p: (-(p.get("traffic_clean") or p.get("traffic") or 0),
                              0 if (p.get("body_status") or "") == "ok" else 1,
                              -(p.get("word_count") or 0),
                              (p.get("title") or p.get("url") or "").lower()))
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    rows = []
    for p in pages[offset:offset + limit]:
        rows.append({k: p.get(k) for k in ("url", "type", "title", "word_count", "body_status",
                                             "traffic", "traffic_clean", "top_keyword", "intent",
                                             "position", "modified", "source")})
    return {"total": len(pages), "offset": offset, "rows": rows}


@router.get("/knowledge/page")
def api_knowledge_page(url: str = ""):
    """One page's saved text, for the reader in the panel."""
    from seo_agent.tools import _shared as sh
    u = (url or "").strip().rstrip("/")
    if not u:
        return _bad("url is needed")
    body = sh.page_bodies().get(u)
    if body is None:
        return _bad("no saved text for that page", 404)
    idx = store.knowledge("site_index.json") or {}
    row = next((p for p in (idx.get("pages") or []) if (p.get("url") or "").rstrip("/") == u), {})
    return {"url": u, "title": row.get("title") or "", "text": body, "row": row}


@router.get("/knowledge/embedding-map")
def api_embedding_map():
    """Every page as a point: a two-dimensional view of the page index."""
    try:
        from seo_agent.tools import _index
    except Exception as e:  # noqa: BLE001
        return _bad("page index unavailable: %s" % str(e)[:120], 404)
    idx = store.knowledge("site_index.json") or {}
    types = {(p.get("url") or ""): (p.get("type") or "page") for p in (idx.get("pages") or [])}
    traffic = {(p.get("url") or ""): (p.get("traffic_clean") or p.get("traffic") or 0)
               for p in (idx.get("pages") or [])}
    m = _index.embedding_map(types=types, traffic=traffic)
    if not m:
        return _bad("The page index has not been built yet.", 404)
    return m


_BRAND_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.(md|json)$")


@router.get("/knowledge/brand/{name}")
def api_brand_file(name: str):
    if not _BRAND_FILE.match(name or ""):
        return _bad("bad name")
    v = store.knowledge("brand/" + name)
    if v is None:
        return _bad("not found", 404)
    return v if isinstance(v, (dict, list)) else {"name": name, "text": v}


@router.post("/knowledge/brand/{name}")
def api_save_brand_file(name: str, body: dict = Body(...)):
    """The user edited a brand file (confirmed the flagged rows, fixed a persona). Their text
    is the truth from then on; the builders never overwrite a file that exists."""
    if not _BRAND_FILE.match(name or ""):
        return _bad("bad name")
    if name.endswith(".json"):
        data = body.get("data")
        if not isinstance(data, (dict, list)):
            return _bad("json data is needed")
    else:
        data = body.get("text")
        if not isinstance(data, str):
            return _bad("text is needed")
    store.save_knowledge("brand/" + name, data)
    return {"ok": True}


@router.post("/knowledge")
def api_save_knowledge(body: dict = Body(...)):
    for key in ("competitors",):
        if key in body and body[key] is not None:
            store.save_knowledge(key + ".json", body[key])
    if isinstance(body.get("company"), dict):
        rec = store.knowledge("brand/company.json") or {}
        for k in ("brand", "domain", "brand_oneliner", "niche_definition", "location_name",
                  "language_code", "about", "wordpress_url"):
            if k in body["company"]:
                rec[k] = str(body["company"][k] or "").strip()[:600]
        store.save_knowledge("brand/company.json", rec)
    return {"ok": True}


@router.get("/memory")
def api_memory():
    rows = store.memory_rules(active_only=False)
    return {"rules": rows, "active": sum(1 for r in rows if r.get("active", True))}


@router.post("/memory")
def api_add_memory(body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        return _bad("empty")
    return store.add_memory(text, body.get("kind", "rule"), source="user")


@router.post("/memory/{mem_id}/toggle")
def api_toggle_memory(mem_id: str, body: dict = Body(default={})):
    if not _ok_id(mem_id):
        return _bad("bad id")
    store.set_memory_active(mem_id, bool(body.get("active", True)))
    return {"ok": True}


_CONN_KEYS = ("dataforseo_login", "dataforseo_password", "voyage_key")


@router.get("/connections")
def api_connections():
    """Never the secrets themselves. Only whether each one is set. DataForSEO and Voyage;
    the model is the `claude` CLI on the user's subscription, never an API key."""
    c = store.connections()
    return {k: bool((c.get(k) or "").strip()) for k in _CONN_KEYS}


@router.post("/connections")
def api_save_connections(body: dict = Body(...)):
    c = store.connections()
    for k in _CONN_KEYS:
        if k in body:
            v = (body.get(k) or "").strip()
            if v:
                c[k] = v[:400]
            else:
                c.pop(k, None)
    # An API key pasted here would route the model through the API and bill per token,
    # which this panel refuses everywhere else too. Drop any that were ever saved.
    for k in ("anthropic_key", "openai_key"):
        c.pop(k, None)
    store.save_connections(c)
    return {"ok": True}


@router.get("/tools")
def api_tools():
    return registry.for_screen()


# ---- library -----------------------------------------------------------------------------------

@router.get("/library")
def api_library():
    return store.library_list()


@router.get("/library/{item_id}")
def api_library_item(item_id: str):
    if not _ok_id(item_id):
        return _bad("bad id")
    it = store.library_get(item_id)
    return it or _bad("not found", 404)


@router.post("/library/{item_id}/status")
def api_library_status(item_id: str, body: dict = Body(...)):
    if not _ok_id(item_id):
        return _bad("bad id")
    status = body.get("status") if body.get("status") in ("draft", "ready", "published") else "draft"
    return store.library_set_status(item_id, status) or _bad("not found", 404)


@router.post("/library/{item_id}/delete")
def api_library_delete(item_id: str):
    if not _ok_id(item_id):
        return _bad("bad id")
    return {"ok": store.library_delete(item_id)}


# ---- health ------------------------------------------------------------------------------------

@router.get("/health")
def api_health():
    _sync_claude_bin()
    c = store.connections()
    try:
        from seo_agent.tools import _index
        page_index = _index.status()
    except Exception:  # noqa: BLE001
        page_index = {"built": False}
    idx = store.knowledge("site_index.json") or {}
    brand = _brand_pack()
    return {"ok": True,
            "model_provider": llm.provider(),
            "claude_bin": os.environ.get("SEO_AGENT_CLAUDE_BIN") or None,
            "dataforseo": bool((c.get("dataforseo_login") or "").strip()
                               and (c.get("dataforseo_password") or "").strip()),
            "voyage": bool((c.get("voyage_key") or "").strip()),
            "site_indexed": bool(idx.get("pages")) if isinstance(idx, dict) else False,
            "page_index": page_index,
            "brand_ready": bool(next((f for f in brand.get("files", [])
                                      if f.get("name") == "writer-brief.md" and f.get("exists")), None)),
            "chats": len(store.list_chats()),
            "data_dir": store.data_dir()}
