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
from seo_agent.prompts import store as prompt_store

router = APIRouter(prefix="/api/agents/seo", tags=["agents"])

# THE OWNER'S OWN PROMPTS, TURNED ON FOR THIS PROCESS. A prompt he edited on the Prompts tab lives
# under the data dir, and `install()` teaches the engine's two prompt doors to prefer it. It is done
# here, at import, because this is the process a run actually happens in: `_spawn` below puts the
# loop on a background THREAD, not in a subprocess, so patching once covers every run this app
# serves. Nothing outside this app is touched, which is the ruling: "it only changes the Sutra app".
prompt_store.install()

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
    # The chip on the Asset ideas tab carries the idea's id as DATA, not as words in the message.
    # It is written into the run's state here, before loop.start, so the model never has to read
    # an id out of prose and decide to look it up. That is a step that can quietly not happen, and
    # nobody would ever know it had been skipped. Research reads it to get the angle; the Library
    # save reads it to tick the idea. The model touches it at no point.
    idea = (body.get("idea") or "").strip()
    if idea and re.match(r"^a\d{1,6}$", idea):
        store.patch_state(chat_id, run_id, idea_id=idea)
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
    """Which brand files exist and how long each is. Nothing else.

    It used to carry a flag count per file, and the count of drafted rows became a list of chores
    on the owner's own screen (2026-09-09). The flags still live in the documents, where the
    quality gates read them; they are no longer counted at anybody. Two callers need this: /health,
    to answer "is the pack built", and the brand checkpoint's artifact.
    """
    try:
        from seo_agent.brand import pack
        out = pack.summary()
        # the company record is built by the crawler, not a brand builder, so the pack does not
        # list it; the screen shows it as a file all the same
        if not any(f.get("name") == "company.json" for f in out.get("files", [])):
            rec = store.knowledge("brand/company.json")
            out.setdefault("files", []).insert(0, {"name": "company.json", "exists": bool(rec),
                                                   "words": len(__import__("json").dumps(rec or {}).split())})
        return out
    except Exception:  # noqa: BLE001 -- the builder may not be installed yet; list what is on disk
        files = []
        for name in store.list_knowledge("brand"):
            base = name.split("/", 1)[1]
            text = store.knowledge(name)
            body = text if isinstance(text, str) else __import__("json").dumps(text)
            files.append({"name": base, "exists": True, "words": len(body.split())})
        return {"files": files}


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

def _type_names(types):
    """{type: what a person calls it}, for the types this catalogue actually holds.

    The names were decided once, by the builder that classified the types, and saved beside the
    roles in brand/type-roles.json. Nothing is named a second time here.
    """
    try:
        from seo_agent.brand import type_roles
        return type_roles.display_names(sorted(types))
    except Exception:  # noqa: BLE001 -- an unbuilt pack is a screen with slugs on it, not a 500
        return {}


def _primary_language():
    return ((store.knowledge("brand/company.json") or {}).get("language_code") or "en")[:2].lower()


def _page_language(page, primary):
    """Which language a catalogue row is in. Decided HERE and nowhere else, because two places
    decide it — the tally on the Knowledge screen and the filter behind the page list — and if
    they disagreed the screen would say "English 9,858" and then show 9,889 rows. An untagged row
    is the site's own language: 31 of the owner's 12,318 pages have no `lang`, and they are
    English pages, not pages in no language.
    """
    return (page.get("lang") or "").strip().lower()[:2] or primary


def _languages(pages):
    """({code: how many pages}, {code: the language's name}), summing to the whole catalogue.

    The list exists to show what the site was TRANSLATED into. The owner's site carries about
    2,400 translated pages across thirteen languages, and Swedish mixed into his English is the
    confusion the language filter was added to end.
    """
    from seo_agent.foundation import urls as U
    primary, out = _primary_language(), {}
    for p in pages:
        code = _page_language(p, primary)
        if code:
            out[code] = out.get(code, 0) + 1
    return out, {c: U.language_name(c) for c in out}


def _brand_knowledge():
    """The brand half of the Knowledge screen: the one page a writer reads, what it was built
    from, and how long the call-to-action list is.

    Deliberately NOT the old file-by-file pack with its review flags. A person opening this wants
    to read the brief and see the chain behind it, not to be handed a list of chores.
    """
    try:
        from seo_agent.brand import cta, pack
        from seo_agent.tools import _shared as sh
        return {"brand": sh.company()["brand"],
                "brief": pack.brief(),
                "built_from": pack.built_from(),
                # Files a PERSON fills in, kept apart from the ones a builder wrote. Same row
                # shape as built_from and extras, so the screen renders it the same way.
                "inputs": pack.inputs(),
                "extras": pack.extras(),
                "cta": {"count": cta.count()}}
    except Exception:  # noqa: BLE001 -- the engine may not be installed yet; show an empty pack
        return {"brand": "", "brief": {"exists": False, "words": 0, "text": ""},
                "built_from": [], "inputs": [], "extras": [], "cta": {"count": 0}}


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
    langs, lang_names = _languages(pages)
    light.update({"page_count": len(pages), "types": types, "type_names": _type_names(types),
                  "languages": langs, "language_names": lang_names,
                  "ranking_pages": sum(1 for p in pages if p.get("top_keyword")),
                  # Whether a traffic pull ever happened. The screen needs to tell "nobody ranks"
                  # apart from "we have not connected search traffic yet", and printing 0 for the
                  # second one reads as the first.
                  "has_traffic": any(p.get("top_keyword") for p in pages),
                  "ok_pages": sum(1 for p in pages if (p.get("body_status") or "ok") == "ok")})
    try:
        from seo_agent.tools import _index
        page_index = _index.status()
    except Exception:  # noqa: BLE001
        page_index = {"built": False}
    company = store.knowledge("brand/company.json") or {}
    # The screen opens the page list filtered to the company's own language, so this field has to
    # be there even on a record written before the field existed.
    company.setdefault("language_code", "en")
    return {"site_index": light,
            "report": store.knowledge("catalogue-report.json"),
            "top_pages": (store.knowledge("top-pages.json") or [])[:25],
            "page_index": page_index,
            "brand": _brand_knowledge(),
            "company": company,
            "brand_voice": store.knowledge("brand_voice.json"),
            "competitors": store.knowledge("competitors.json")}


@router.get("/knowledge/cta")
def api_cta():
    """The pages an article's close is allowed to link to."""
    from seo_agent.brand import cta
    from seo_agent.foundation import urls as U
    from seo_agent.tools import _shared as sh
    return {"rows": cta.rows(), "domain": U.bare_host(sh.company().get("domain"))}


@router.post("/knowledge/cta")
def api_save_cta(body: dict = Body(...)):
    """The whole list, in the order the person wants it. Every row saved here is theirs from then
    on, and the features builder re-emits them above its own rows rather than over them.

    A url the catalogue has never seen is accepted and comes back with an empty title: the page may
    have been published since the last crawl, and making him re-crawl to add a link he knows is
    live would be the tool arguing with him. A url on somebody else's domain is refused, because
    the close links to his own product or to nothing.
    """
    from seo_agent.brand import cta
    from seo_agent.foundation import urls as U
    from seo_agent.tools import _shared as sh
    rows = body.get("rows")
    if not isinstance(rows, list):
        return _bad("send the whole list as \"rows\", in the order you want it")
    co = sh.company()
    wanted, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            return _bad("every row needs a url and a note")
        url = str(r.get("url") or "").strip()
        why = cta.check(url, co.get("domain"))
        if why:
            return _bad(why)
        key = url.rstrip("/").lower()
        if key in seen:              # the same page twice is one row, not an error
            continue
        seen.add(key)
        wanted.append({"url": url, "note": str(r.get("note") or "").strip()[:300]})
    return {"rows": cta.save(co["brand"], wanted), "domain": U.bare_host(co.get("domain"))}


@router.post("/knowledge/refresh")
def api_knowledge_refresh(body: dict = Body(default={})):
    """Bring the catalogue up to date. With preview=true it reports and changes nothing."""
    ctx = {"chat_id": "knowledge", "run_id": "refresh", "emit": lambda **kw: None}
    try:
        from seo_agent.tools import refresh_site
        return refresh_site.run(ctx, preview=bool(body.get("preview")),
                                include_unchecked=bool(body.get("include_unchecked")),
                                use_archive=bool(body.get("use_archive")))
    except Exception as e:  # noqa: BLE001
        return _bad(str(e)[:300], 500)


@router.get("/knowledge/changes")
def api_knowledge_changes():
    """The last refresh's change summary, as markdown."""
    return {"text": store.knowledge("catalogue-changes.md") or ""}


@router.post("/knowledge/traffic")
def api_knowledge_traffic(body: dict = Body(...)):
    """Import a traffic export the person already has. Takes a path on this Mac, or the CSV text."""
    from seo_agent.foundation import traffic_import
    text = body.get("text")
    source = "pasted text"
    if not text:
        path = os.path.expanduser((body.get("path") or "").strip())
        if not path:
            return _bad("give me a file path or the text of the file")
        if not os.path.exists(path):
            return _bad("there is no file at %s" % path, 404)
        try:
            with open(path, encoding="utf-8-sig") as f:
                text = f.read()
        except Exception as e:  # noqa: BLE001
            return _bad("that file could not be read: %s" % str(e)[:160])
        source = os.path.basename(path)
    out = traffic_import.apply(text, source=source)
    return out if out.get("ok") else _bad(out.get("error", "nothing was imported"))


@router.get("/knowledge/pages")
def api_knowledge_pages(offset: int = 0, limit: int = 5, q: str = "", type: str = "", lang: str = ""):
    """A page of the catalogue: searchable by title or url, filterable by type and by language,
    sorted by traffic then title. Light rows only.

    `limit` defaults to five. It used to be twenty-five, which on a 12,318-page site filled the
    screen with rows nobody had asked to see; the list is a sample with a search box, not a table
    of contents. `lang` is two letters, and a row with no lang counts as the company's own
    language, because that is what an untagged page is.
    """
    idx = store.knowledge("site_index.json") or {}
    pages = idx.get("pages") if isinstance(idx, dict) else (idx if isinstance(idx, list) else [])
    pages = pages or []
    ql = (q or "").strip().lower()
    if ql:
        pages = [p for p in pages if ql in (p.get("title") or "").lower() or ql in (p.get("url") or "").lower()
                 or ql in (p.get("top_keyword") or "").lower()]
    if type:
        pages = [p for p in pages if (p.get("type") or "page") == type]
    if lang:
        want, primary = lang.strip().lower()[:2], _primary_language()
        pages = [p for p in pages if _page_language(p, primary) == want]
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
                                             "position", "modified", "source", "lang")})
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
    # PRICING.MD IS THE ONE BRAND FILE A SAVE HAS TO PROPAGATE. It carries facts the crawler can
    # never reach -- prices a site draws with JavaScript -- and features.md, the file the writer
    # reads for product claims, is filled FROM it. MARKING is all that happens here: the rebuild
    # reuses the cached crawl and still costs two model calls, which a save must not sit and wait
    # for. features.pricing_saved() writes one stamp file and returns whether a rebuild is due; it
    # touches nothing else and calls no model (verified against the function, 2026-09-09).
    # The chain is ONE hop by the owner's decision: pricing.md -> features.md, and no further.
    # Without this the feature still works -- the fingerprint makes the next brand-pack run
    # rebuild -- so a failure here is not a failed save, and the save still stands.
    if name == "pricing.md":
        try:
            from seo_agent.brand import features
            features.pricing_saved()
        except Exception:  # noqa: BLE001 -- the engine may not be installed
            pass
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


# ---- prompts -------------------------------------------------------------------------------------
# The owner's own writing rules, editable without a developer. Four routes and no logic: which
# prompts exist, one prompt's text, save, reset. Everything they need to decide lives in
# seo_agent/prompts/store.py, including the flow drawn across the top of the tab.
#
# The name of a prompt travels as a QUERY parameter, not a path segment, because a name carries
# slashes ("write/formats/listicle") — the same names the engine already loads prompts by. It is
# never joined onto a path here: the store resolves it through its own allow-list.


@router.get("/prompts")
def api_prompts():
    return prompt_store.listing()


@router.get("/prompts/one")
def api_prompt(name: str = ""):
    try:
        return prompt_store.one(name)
    except prompt_store.PromptError as e:
        return _bad(str(e), 404)


@router.post("/prompts/save")
def api_save_prompt(body: dict = Body(...)):
    """His version of one prompt. Saved under the data dir, and read by the very next article.

    A save that has lost a {{TOKEN}} the shipped version had is refused, with the missing ones
    named. That break would otherwise surface in the middle of a paid run, as a model reading a
    prompt with a hole in it, and nothing on screen would ever have said why.
    """
    try:
        return prompt_store.save(body.get("name"), body.get("text"))
    except prompt_store.PromptError as e:
        return _bad(str(e))


@router.post("/prompts/reset")
def api_reset_prompt(body: dict = Body(...)):
    """Back to what shipped. It deletes his copy; the original was never written over."""
    try:
        return prompt_store.reset(body.get("name"))
    except prompt_store.PromptError as e:
        return _bad(str(e), 404)


# ---- library -----------------------------------------------------------------------------------

# WHICH SHAPE EACH ARTICLE WAS WRITTEN TO, for the Library's Format column. Read from the run that
# made it, never stored a second time on the row: the format is decided once, at the route step, and
# `write-report.json` records it. Cached per run because the Library screen polls this route while a
# run is going, and a routed archetype never changes afterwards. Only a real answer is cached, so a
# row still being written is looked at again on the next poll and fills in when the report lands.
_FORMAT_CACHE = {}


def _run_format(chat_id, run_id):
    """The routed archetype for one run, or "" when it has not got that far."""
    if not chat_id or not run_id:
        return ""
    key = (chat_id, run_id)
    if key in _FORMAT_CACHE:
        return _FORMAT_CACHE[key]
    rep = store.load_artifact(chat_id, run_id, "write-report.json") or {}
    arch = str(rep.get("archetype") or "").strip() if isinstance(rep, dict) else ""
    if arch:
        _FORMAT_CACHE[key] = arch
    return arch


@router.get("/library")
def api_library():
    rows = store.library_list()
    for r in rows:
        # The row's OWN meta first, the run second. loop.save_to_library writes the archetype onto
        # the row now, and that is the durable answer: a run folder can be deleted and its article
        # kept, and a finished article should still be able to say what shape it was written to.
        # Reading the run is the fallback for rows written before that landed. (2026-09-09.)
        arch = (r.get("format_archetype") or "").strip() or _run_format(r.get("chat_id"), r.get("run_id"))
        r["format"] = arch
        # the plain name comes from the prompt store, the same place the Prompts tab gets it, so
        # the two screens can never call the same shape by two different names
        r["format_label"] = prompt_store.format_title(arch) if arch else ""
    return rows


@router.get("/library/{item_id}")
def api_library_item(item_id: str):
    if not _ok_id(item_id):
        return _bad("bad id")
    it = store.library_get(item_id)
    return it or _bad("not found", 404)


@router.get("/library/{item_id}/artifact/{name}")
def api_library_artifact(item_id: str, name: str):
    """One milestone's file, straight out of the run that made it.

    This is what makes the live Library worth having: the owner asked to be able to open any
    half-finished piece of a run without the agent stopping to show it to him (2026-09-09). The
    row on screen carries a strip of milestones; this route is what a click on one of them reads.

    Nothing is copied to serve it. The row knows its chat and its run, and the file is read from
    that run's artifacts folder, so what the panel shows is the run's own file and cannot drift
    from it. `name` is the milestone key the strip carries ("plan"), or the file it stands for.
    """
    if not _ok_id(item_id):
        return _bad("bad id")
    if not _NAME.match(name or ""):
        return _bad("bad name")
    row = store.library_artifact(item_id, name)
    return row or _bad("that part of this article has not been written yet", 404)


@router.post("/library/{item_id}/save")
def api_library_save_edit(item_id: str, body: dict = Body(...)):
    """Save an edited article back over itself. The person's version is the truth from then on.

    A saved article is a document, not a transcript: fixing a sentence should not need a live
    run. Title and body only; status has its own route and the rest is provenance.
    """
    if not _ok_id(item_id):
        return _bad("bad id")
    it = store.library_get(item_id)
    if not it:
        return _bad("not found", 404)
    draft = body.get("draft")
    if not isinstance(draft, str) or not draft.strip():
        return _bad("an empty article is not a save")
    title = (body.get("title") or it.get("title") or "").strip()[:160]
    return store.library_update(item_id, draft, title) or _bad("could not save", 500)


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


# ---- asset ideas ---------------------------------------------------------------------------------

def _plain_methods(line):
    """Any method slug left in a sentence becomes what a person calls it. The builders name
    themselves after the original's folders, which is right in a path and wrong on screen."""
    from seo_agent.assets import _common as acm
    for slug, name in sorted(acm.METHOD_NAMES.items(), key=lambda kv: -len(kv[0])):
        line = line.replace(slug, name)
    return line


def _assets_payload():
    from seo_agent.assets import _common as acm
    rows = acm.ideas()
    nxt = acm.next_open(rows)
    # Which methods contributed comes from the merge's own record, not from counting the `method`
    # field on the rows. Counting rows cannot tell a method that RAN AND FOUND NOTHING from one
    # that never ran at all, and those are different facts a person needs: one means the method is
    # working and this site has nothing there, the other means it is blocked. The merge writes all
    # three states, with a ready-made sentence. (Raised by the merge builder, 2026-09-09.)
    m = acm.read("_work/merge/methods.json") or {}
    states = m.get("methods") or {}
    ran = sorted([k for k, v in states.items() if v == "ran"]) or \
        sorted({x for r in rows for x in (r.get("method") or [])})
    return {
        "built": bool(rows),
        "total": len(rows),
        "counts": acm.counts(rows),
        "methods_run": ran,
        "methods": states,
        "methods_line": _plain_methods(m.get("line") or ""),
        "methods_blocked": sorted([k for k, v in states.items() if v != "ran"]),
        "next": ({"id": nxt["id"], "title": nxt.get("title", ""), "angle": nxt.get("angle", ""),
                  "format": nxt.get("format", ""), "method": nxt.get("method") or [],
                  "linkability": nxt.get("linkability") or {}} if nxt else None),
        "rows": [{k: r.get(k) for k in
                  ("id", "title", "angle", "format", "method", "brand_fit", "linkability",
                   "beatability", "effort", "rank", "status", "reuse", "built")} for r in rows],
    }


@router.get("/assets")
def api_assets():
    return _assets_payload()


@router.get("/assets/{idea_id}")
def api_asset(idea_id: str):
    from seo_agent.assets import _common as acm
    if not re.match(r"^a\d{1,6}$", idea_id or ""):
        return _bad("bad id")
    row = acm.by_id(idea_id)
    return row or _bad("not found", 404)


@router.post("/assets/{idea_id}/status")
def api_asset_status(idea_id: str, body: dict = Body(...)):
    """Drop an idea, or put a dropped one back. The only status a person sets by hand.

    `done` is deliberately NOT settable here. An idea is ticked from provenance, when a run that
    started from it reaches the Library, and nowhere else. Letting the screen set it would put a
    second source of truth next to the first, and they would disagree the first time somebody
    clicked the wrong row.
    """
    from seo_agent.assets import _common as acm
    if not re.match(r"^a\d{1,6}$", idea_id or ""):
        return _bad("bad id")
    want = (body.get("status") or "").strip()
    if want not in ("open", "dropped"):
        return _bad("An idea can be set to open or dropped. Done is set by writing the article.")
    rows = acm.ideas()
    row = acm.by_id(idea_id, rows)
    if not row:
        return _bad("not found", 404)
    if row.get("status") == "done":
        return _bad("That one is written. It is in the Library.")
    row["status"] = want
    acm.save_ideas(rows)
    return _assets_payload()


# ---- health ------------------------------------------------------------------------------------

def _dfs_credit():
    """Whether an article run can actually measure anything, for the screen to say so up front.

    Three rules, and each one exists because getting it wrong is worse than not showing it:

    * The floor comes from `run_research.MIN_CREDITS`, never a literal. The screen and the guard
      that refuses the run must agree, and two copies of a number always drift.
    * `enough` is True when the balance is UNKNOWN, matching the guard's fail-open. The owner's
      connection drops constantly; a screen that reads "blocked" on every network blip is worse
      than one that says nothing.
    * Cached through `loop._cached_balance`, 300 seconds. Reading a balance is itself an API call
      and /health is polled, so an uncached read here would be its own bug.
    """
    try:
        from seo_agent.tools import _shared as _sh, dfs as _dfs, run_research as _rr
        mode = _sh.dfs_mode(_dfs)
        if mode != "live":
            return {"mode": mode, "balance": None, "floor": _rr.MIN_CREDITS, "enough": mode == "demo"}
        bal = loop._cached_balance(_dfs)
        return {"mode": mode, "balance": bal, "floor": _rr.MIN_CREDITS,
                "enough": bal is None or bal >= _rr.MIN_CREDITS}
    except Exception:   # noqa: BLE001 — health must answer even when this cannot
        return {"mode": "unknown", "balance": None, "floor": None, "enough": True}


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
            "dataforseo_credit": _dfs_credit(),
            "voyage": bool((c.get("voyage_key") or "").strip()),
            "site_indexed": bool(idx.get("pages")) if isinstance(idx, dict) else False,
            "page_index": page_index,
            "brand_ready": bool(next((f for f in brand.get("files", [])
                                      if f.get("name") == "writer-brief.md" and f.get("exists")), None)),
            "chats": len(store.list_chats()),
            "data_dir": store.data_dir()}
