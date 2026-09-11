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
import importlib
import os
import re
import threading
import time
import traceback
import uuid

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

# AND THE TEAM POLLER, FOR THE SAME REASON. A workspace's whole promise is "nobody presses sync",
# and starting it from the Connections tab's own route made that quietly untrue: a teammate who
# worked all morning in Chat and Library heard about nothing anybody else had done, because the one
# screen that starts the poller was never open. It belongs here, in the process the run happens in.
#
# It deliberately does NOT check whether a workspace is configured. With none, the poller sits in
# its backoff doing nothing and picks one up by itself the moment Create or Join finishes. Refusing
# to start without one would mean somebody has to remember to start it afterwards, and that is
# exactly the thing nobody remembers. `start()` is idempotent and thread-safe, so the route below
# keeping its own call is a belt, not a second poller. (2026-09-10.)
try:
    from seo_agent.workspace import sync as _ws_sync
    _ws_sync.start()
except Exception:  # noqa: BLE001 — no workspace, no network, a missing module: the app still boots
    pass

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


@router.delete("/chats/{chat_id}")
def api_delete_chat(chat_id: str):
    """Throw a chat away. The Library keeps every article that was written in it.

    A RUNNING chat is refused rather than killed. A run writes into the folder we would be
    deleting, so pulling it out from under a live thread is how you get half-written state and
    a stack trace nobody can act on. Stop it first, then delete it; the UI does both in order.
    """
    if not _ok_id(chat_id):
        return _bad("bad id")
    if not os.path.isdir(store.chat_dir(chat_id)):
        return _bad("no such chat", 404)
    if _live_status(chat_id) == "running":
        return _bad("That chat is still working. Stop it first, then delete it.", 409)
    if not store.delete_chat(chat_id):
        return _bad("could not delete that chat")
    return {"ok": True, "id": chat_id}


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
    # nobody would ever know it had been skipped. `run_research` reads it to take the angle the
    # asset engine already worked out, and the Library save reads it to tick the idea it came
    # from. The model touches it at no point. The third way in is loop._took_the_offer: accepting
    # the agent's offer in the chat records the same id the same way.
    idea = (body.get("idea") or "").strip()
    if not (idea and re.match(r"^a\d{1,6}$", idea)):
        # THE SAME FACT, TYPED. Somebody who writes "write a1001" has started from that idea just
        # as surely as somebody who pressed its button, so the id counts when the message names
        # one that is really on the sheet and still open. Still provenance: the id is read from
        # what the person wrote, never inferred from what the article turned out to be about.
        idea = _named_open_idea(text)
    if idea and re.match(r"^a\d{1,6}$", idea):
        store.patch_state(chat_id, run_id, idea_id=idea)
    if len(runs) == 0:
        store.set_chat_title(chat_id, text[:60])
    _sync_claude_bin()
    _spawn(chat_id + run_id, _guarded(chat_id, run_id,
                                      lambda: loop.start(chat_id, run_id, text)))
    return {"run_id": run_id, "answered": False, "state": store.get_state(chat_id, run_id)}


def _named_open_idea(text):
    """An idea id the person typed, checked against the sheet. "" when the message names none, or
    names more than one, or names one that is already written: a guess here ticks the wrong row."""
    try:
        from seo_agent.assets import _common as acm
        open_ids = {(r.get("id") or "").lower() for r in acm.ideas() if r.get("status") == "open"}
    except Exception:  # noqa: BLE001 — a sheet we cannot read must never stop a message being sent
        return ""
    found = {m.lower() for m in re.findall(r"\ba\d{1,6}\b", text or "")} & open_ids
    return found.pop() if len(found) == 1 else ""


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


# ---- keeping the catalogue current -----------------------------------------------------------
# THE BUG THIS SHAPE EXISTS FOR (owner, 2026-09-10). This route used to hand refresh_site an emit
# that threw every line away -- `"emit": lambda **kw: None` -- and then block until the whole
# survey came back. refresh_site says a great deal while it works ("Read the sitemaps", "The site
# lists 11,656 pages now", "The site's firewall pushed back, waiting 120s"), and all of it went
# into that no-op. The screen had nothing to draw but one fixed sentence, so a run sitting out six
# minutes of firewall cooldowns looked exactly like a run that had hung, and exactly like a run
# that had finished.
#
# So it is now the same shape as the workspace job above, deliberately: one job in memory, the
# work on a thread, every line the engine says recorded as it arrives, and one GET the screen
# polls on the same cadence. refresh_site IS one of the twelve tools, and the button now reports
# what a tool run reports -- the tool's own label from the registry, and its own substep lines.
#
# NOTHING HERE WRITES A PROGRESS LINE OF ITS OWN. Every word the screen shows was said by the
# engine. A line invented from "he pressed the button" is the bug, not the fix.

_KN_KEY = "knowledge-refresh"          # the worker slot, so two refreshes can never overlap
_KN_MAX_STEPS = 200                    # a long run is bounded; the screen shows the tail anyway
_kn_job = None
_kn_job_lock = threading.Lock()
# A wait the engine announced. It hands the number over as a FIELD (`wait_seconds`, set by
# fetch.py where it sits out a firewall cooldown), so nothing here has to read prose to tell
# "waiting on a slow site" apart from "working".
#
# The regex is the fallback for a line that carries the sentence but not the field — an older
# engine, or a caller that has not been given the field yet. It is deliberately second: reading
# the number out of somebody else's wording was the whole arrangement until 2026-09-10, and it
# was one reworded sentence away from silently turning every cooldown back into something that
# looks like progress, with no test able to catch it because the sentence and the reader live in
# different packages.
_KN_WAIT = re.compile(r"waiting\s+(\d+)\s*s\b", re.I)


def _kn_worker_alive():
    with _lock:
        t = _workers.get(_KN_KEY)
    return bool(t and t.is_alive())


def _kn_start_job(mode):
    global _kn_job
    with _kn_job_lock:
        _kn_job = {"mode": mode, "phase": "running", "tool": "refresh_site",
                   "label": registry.LABELS.get("refresh_site") or "refresh_site",
                   "steps": [], "waiting": None, "result": None, "error": None, "spawned": False,
                   "started_at": time.time(), "updated_at": time.time(), "finished_at": None}
        return dict(_kn_job)


def _kn_say(**kw):
    """Move the job on. Every field the screen draws is set here and nowhere else."""
    with _kn_job_lock:
        if _kn_job is not None:
            _kn_job.update(kw)


def _kn_stop(phase, **kw):
    """Land the job. One door for both endings, so a stopped job can never still be running."""
    now = time.time()
    _kn_say(phase=phase, finished_at=now, updated_at=now, waiting=None, **kw)


def _kn_emit(**kw):
    """One line from the engine, recorded exactly as the engine said it.

    The tools report through sh.reporter, which calls emit(type="substep_finished", label=...,
    note=...). A line with a label is a line for the person; anything else is dropped rather than
    guessed at. Neither label nor note is reworded here or on the screen -- they are already
    written for a person, and a second wording would drift from the first.
    """
    label = str(kw.get("label") or "").strip()
    if not label:
        return
    note = str(kw.get("note") or "").strip()
    at = time.time()
    wait_seconds = kw.get("wait_seconds")
    if wait_seconds is None:
        m = _KN_WAIT.search(note)
        wait_seconds = int(m.group(1)) if m else None
    else:
        try:
            wait_seconds = int(wait_seconds)
        except (TypeError, ValueError):
            wait_seconds = None
    with _kn_job_lock:
        if _kn_job is None or _kn_job.get("phase") != "running":
            return                      # a line arriving after the end never revives the spinner
        steps = _kn_job["steps"]
        steps.append({"label": label[:200], "note": note[:400], "at": at})
        del steps[:-_KN_MAX_STEPS]
        # A wait the engine ANNOUNCED, carried with its own number so the screen can say "waiting"
        # instead of drawing a working step. The next line clears it, because that line is the
        # proof the wait is over.
        _kn_job["waiting"] = ({"seconds": min(3600, wait_seconds), "since": at}
                              if wait_seconds else None)
        _kn_job["updated_at"] = at


def _kn_get_job():
    """The job as it stands, with the one correction the screen cannot make for itself.

    A spinner trusts "phase == running". A worker that died without reaching its own except --
    the interpreter going down, the thread killed -- would leave that true for ever, which is the
    spinner-after-the-work-stopped this whole change is about. So a job still marked running whose
    worker is gone is reported as failed. `spawned` is checked because between starting the job
    and starting its thread there is no worker yet, and that instant is not a crash.
    """
    with _kn_job_lock:
        if _kn_job is None:
            return None
        if _kn_job.get("phase") == "running" and _kn_job.get("spawned") and not _kn_worker_alive():
            _kn_job.update(phase="failed", finished_at=time.time(), waiting=None,
                           error="The refresh stopped without saying why. Nothing was changed.")
        job = dict(_kn_job)
        # the worker appends to `steps` while this is being serialised, so it is copied under
        # the lock rather than handed out live
        job["steps"] = list(job["steps"])
        return job


def _kn_worker(preview, include_unchecked, use_archive):
    """The refresh itself, on a thread.

    ctx carries a REAL emit and the tool's own step id, so sh.reporter parents each substep to the
    tool exactly as it does inside a run: it is the same tool, and only the door differs.

    A REAL refresh also asks for the shared knowledge pack to be rebuilt, which is the owner's
    ruling in WORKSPACE-PLAN section 2: one click updates everybody AND the copy a new joiner
    downloads. He does not wait for the second half -- ws_pack_refresh returns at once and the
    rebuild runs behind him as the quiet line at the foot of the screen. It is fired AFTER the
    refresh has succeeded, because a pack rebuilt from a catalogue that failed is worse than no
    rebuild, and it can never turn a working refresh into an error: it swallows everything,
    including having no workspace at all.
    """
    ctx = {"chat_id": "knowledge", "run_id": "refresh", "step_id": "refresh_site",
           "emit": _kn_emit}
    try:
        from seo_agent.tools import refresh_site
        out = refresh_site.run(ctx, preview=preview, include_unchecked=include_unchecked,
                               use_archive=use_archive)
    except Exception as e:  # noqa: BLE001 -- a crash on a thread must land on the screen
        _kn_stop("failed", error=str(e)[:300] or e.__class__.__name__)
        return
    if not isinstance(out, dict):
        _kn_stop("failed", error="The refresh returned nothing, so nothing was changed.")
        return
    if out.get("error"):
        # A refusal the tool SURVIVED -- every page blocked, catalogue untouched -- comes back as
        # an error beside a summary rather than as a raised exception. It is a failure on the
        # screen, and it asks for no pack rebuild: the catalogue it would rebuild from did not
        # change.
        _kn_stop("failed", error=str(out["error"])[:400], result=out)
        return
    _kn_stop("done", result=out)
    if not preview:
        try:
            ws_pack_refresh("the catalogue was refreshed")
        except Exception:  # noqa: BLE001 -- a working refresh is never turned into a failure
            pass


@router.post("/knowledge/refresh")
def api_knowledge_refresh(body: dict = Body(default={})):
    """Start bringing the catalogue up to date, and return at once.

    With preview=true it reports and changes nothing; without it, it writes. Both go on a thread
    and both report the same way, because the person watching cannot tell which of the two is the
    slow one and should not have to.

    The answer is NOT in this response. GET /knowledge/refresh is what the screen watches, and it
    carries the engine's lines while they arrive and the counts when they land.
    """
    if _kn_worker_alive():
        return _bad("A refresh is already running. Wait for it to finish.", 409)
    preview = bool(body.get("preview"))
    include_unchecked = bool(body.get("include_unchecked"))
    use_archive = bool(body.get("use_archive"))
    _kn_start_job("preview" if preview else "apply")
    if not _spawn(_KN_KEY, lambda: _kn_worker(preview, include_unchecked, use_archive)):
        return _bad("A refresh is already running. Wait for it to finish.", 409)
    _kn_say(spawned=True)
    return {"started": True, "job": _kn_get_job()}


@router.get("/knowledge/refresh")
def api_knowledge_refresh_state():
    """What the refresh is doing right now, in the engine's own words. The one read the card
    polls: the lines so far, whether it is sitting out a wait the site imposed, and, when it is
    over, the counts or the reason."""
    return {"job": _kn_get_job()}


@router.post("/knowledge/refresh/dismiss")
def api_knowledge_refresh_dismiss(body: dict = Body(default={})):
    """Put the card away once the refresh has stopped. A job still RUNNING is refused, because
    "clear this box" must never be able to hide work that is still going."""
    global _kn_job
    job = _kn_get_job()
    if job and job.get("phase") == "running":
        return _bad("That refresh is still running. Let it finish or fail before clearing it.", 409)
    with _kn_job_lock:
        _kn_job = None
    return {"ok": True}


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
        # A FILE A PERSON TYPES IN IS NEVER A 404. The blank form only reaches disk when the
        # brand-pack builder runs, so a pack built before that form existed has no copy of it,
        # and this screen still offers a door to it (the owner, 2026-09-10). brand/_common.read
        # hands back the blank form for exactly those names, so what a person opens is the form
        # they are being asked to fill in rather than an error. Any other missing name is still
        # a 404, which is the truth for it.
        try:
            from seo_agent.brand import _common as bcm
            if bcm.is_input(name):
                return {"name": name, "text": bcm.read(name)}
        except Exception:  # noqa: BLE001 -- the engine may not be installed yet
            pass
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
    # ...and it is also the one brand file that travels on the LIVE pipe. It is small, and a
    # person typed it, so it is a row in `brand_inputs` rather than a wait for the next pack
    # rebuild (design/WORKSPACE-PLAN.md section 3; features.md next door is 13,219 machine-written
    # words and stays in the pack). brand/_common.input_saved does both halves: the stamp above,
    # and the push. It never writes the file (this route already did) and it never raises: a save
    # that reached disk has succeeded, and no workspace, no network, or a workspace a version
    # behind must not turn it into a failed save.
    try:
        from seo_agent.brand import _common as bcm
        if bcm.is_input(name):
            bcm.input_saved(name, data)
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


# ---- the team workspace --------------------------------------------------------------------
# Five people, one Supabase project the company owns (design/WORKSPACE-PLAN.md). One person
# presses Create; everybody else pastes a link. The thinking lives in seo_agent/workspace/ —
# these routes are the panel's half: validate what was typed, put the slow part on a thread,
# and let the screen poll one dict.
#
# WHAT THIS FILE DOES NOT DECIDE. It never decides that a workspace exists. schema.create()
# already runs verify() whichever route it took and hands back {"ok": bool}; this file reads
# that flag and nothing else. A route that inferred success from "the POST came back" is the
# one failure spec section 10 names by hand, and the way to keep it out is to have no code
# here that could.
#
# THE TOKEN. It arrives in one request body, is passed as one argument, and the argument is
# rebound to "" as the call returns. It is never a field on the job the screen polls, never a
# key in connections.json, and never in a message. schema.run_sql puts it in a header and
# builds no error text from headers, so the scrub below is defence in depth rather than the
# only line — but the messages it guards are drawn on a screen, so it stays.

_WS_MODS = ("client", "schema", "link", "pack", "sync")

# The six settings are client.SETTINGS and are the engine's to write. `workspace_name` is the
# panel's own: it is what the tab calls the workspace, and client.save_settings refuses keys it
# does not know, so it goes in beside them rather than through them (see design/HANDOFF-W4.md).
_WS_NAME_KEY = "workspace_name"

_WS_TOKEN = re.compile(r"sbp_[A-Za-z0-9_-]{8,}")

# How long the member list may be reused before it is read again. The screen polls once a
# second while a job is running, and "who is in the team" does not change once a second.
_WS_MEMBERS_TTL = 20.0

_ws_job = None
_ws_job_lock = threading.Lock()
_ws_members = {"at": 0.0, "rows": []}
# The last answer schema.verify() gave, and when. Cached because verify probes ten tables and
# the bucket -- eleven calls -- and the screen polls this route once a second while a job runs.
_ws_checked = {"at": 0.0, "res": None}
# What the quiet line reads off. Set only by the pack progress callback below, so it can only
# ever say what the pack is actually doing.
_ws_pack = {"state": "idle", "note": ""}
_ws_rebuilder_ref = [None]


def _ws():
    """The workspace engine's modules, or None when this build has no seo_agent/workspace/.

    Resolved per call and never at import, so the panel loads, draws and says something useful
    on a checkout where the package is missing or half-landed.
    """
    try:
        workspace = importlib.import_module("seo_agent.workspace")
    except Exception:
        return None
    out = {}
    for n in _WS_MODS:
        m = getattr(workspace, n, None)
        if m is None:
            try:
                m = importlib.import_module("seo_agent.workspace." + n)
            except Exception:
                m = None
        out[n] = m
    return out


def _ws_ready(mods, *names):
    return bool(mods) and all(mods.get(n) is not None for n in names)


def _ws_scrub(msg, *secrets):
    """No secret reaches the screen, whatever an error string happens to carry."""
    s = str(msg or "")
    for v in secrets:
        v = str(v or "")
        if len(v) >= 6:
            s = s.replace(v, "…")
    return _WS_TOKEN.sub("sbp_…", s)[:400]


# ---- what was typed, checked before anything is started -------------------------------------
# The engine refuses a bad key too, and says so well. These run FIRST anyway, because they run
# in the request rather than on the thread: a person who pasted the secret key gets the sentence
# back on the button press instead of watching a spinner start and then fail.

def _ws_check_url(url):
    if not (url or "").strip():
        return "Paste the project URL first."
    if not re.match(r"^https://[a-z0-9]{16,40}\.supabase\.(co|in|net)/?$", (url or "").strip(), re.I):
        return ("That does not look like a Supabase project URL. It reads "
                "https://abcdefghijklmnop.supabase.co and is on the project's settings page, "
                "under Data API.")
    return ""


def _ws_check_key(key):
    """The publishable key, and only that one. Naming the key somebody pasted by mistake is the
    difference between fixing it in ten seconds and giving up."""
    k = (key or "").strip()
    if not k:
        return "Paste the publishable key first."
    if k.startswith("sb_publishable_"):
        return ""
    if k.startswith("sb_secret_"):
        return ("That is the secret key. It gets past every row rule, so Sutra never asks for "
                "it and it must never go in a share link. The one to paste starts with "
                "sb_publishable_ and is on the same Data API page.")
    if k.startswith("eyJ"):
        return ("That is a service role JWT, an admin key. Sutra never asks for one. The key to "
                "paste starts with sb_publishable_ and is on the project's Data API page.")
    if k.startswith("sbp_"):
        return ("That is a personal access token, not a project key. Sutra asks for that one "
                "later, at the moment it creates the tables. The key here starts with "
                "sb_publishable_.")
    return ("That key is not this project's publishable key. The publishable key starts with "
            "sb_publishable_ and is on the project's Data API page.")


def _ws_check_token(token):
    t = (token or "").strip()
    if not t:
        return "Paste the token first."
    if not t.startswith("sbp_"):
        return ("A Supabase personal access token starts with sbp_. You make one at "
                "supabase.com/dashboard/account/tokens.")
    return ""


# ---- the one running job ----------------------------------------------------------------
# In memory, never on disk. A job that did not finish has created nothing that survives a
# restart, and a job state read back after a crash would be exactly the "half-made workspace
# drawn as if it worked" the plan forbids.

def _ws_start_job(kind):
    global _ws_job
    with _ws_job_lock:
        _ws_job = {"kind": kind, "phase": "starting", "step": "", "pct": None,
                   "done_bytes": 0, "total_bytes": 0, "error": None, "paste": None,
                   "link": "", "started_at": time.time(), "finished_at": None}
        return dict(_ws_job)


def _ws_say(**kw):
    """Move the job on. Every field the screen draws is set here and nowhere else."""
    with _ws_job_lock:
        if _ws_job is not None:
            _ws_job.update(kw)


def _ws_get_job():
    with _ws_job_lock:
        return dict(_ws_job) if _ws_job else None


def _ws_fail(what, do):
    _ws_say(phase="failed", error={"what": what, "do": do}, finished_at=time.time())


def _ws_paste_route(res, why=""):
    """THE PASTE ROUTE IS A ROUTE, NOT A FAILURE STATE.

    There may never be a personal access token on a given machine — there is not one on the
    owner's — so pasting the script into Supabase's own SQL Editor is a first-class way to set
    a workspace up, and for many people it will be the only one. schema.create() returns it
    fully formed: the script, the deep link to that project's editor, the reason this route is
    the one on offer, and the next step. This reshapes it for the screen and invents no part
    of it. The screen draws it as a route, with its own heading and its own button.
    """
    _ws_say(phase="paste", step="", pct=None, paste={
        "sql": str((res or {}).get("sql") or ""),
        "editor_url": str((res or {}).get("editor_url") or "https://supabase.com/dashboard"),
        "why": _ws_scrub(why or (res or {}).get("reason") or ""),
        "next": str((res or {}).get("next") or ""),
    })


# ---- credentials -------------------------------------------------------------------------

def _ws_settings(mods):
    client = (mods or {}).get("client")
    if client is None:
        return {}
    try:
        return client.settings()
    except Exception:  # noqa: BLE001
        return {}


def _ws_name():
    return str(store.connections().get(_WS_NAME_KEY) or "")


def _ws_save_name(name):
    c = store.connections()
    if str(name or "").strip():
        c[_WS_NAME_KEY] = str(name).strip()[:80]
    else:
        c.pop(_WS_NAME_KEY, None)
    store.save_connections(c)


def _ws_member_id(mods):
    """This person's id. Made once and then kept, because it is what their writes are stamped
    with: a new one on every join would read as a new person joining every time."""
    s = _ws_settings(mods)
    return str(s.get("member_id") or "").strip() or uuid.uuid4().hex[:16]


def _ws_link(mods, s):
    lk = (mods or {}).get("link")
    if lk is None:
        return ""
    url, key, wid = (s.get("workspace_url") or ""), (s.get("workspace_key") or ""), (s.get("workspace_id") or "")
    if not (url and key and wid):
        return ""
    try:
        return str(lk.make_link(url, key, wid) or "")
    except Exception:  # noqa: BLE001
        return ""


def _ws_face(asked, name=""):
    """The face this person ends up with: what they picked if it is real, otherwise one chosen
    for them. Never raises and never refuses -- an avatar must not be able to block a join.

    A face is validated against the pack rather than taken as free text, so nobody can arrive
    with a flag, a skin tone, or a glyph that renders as a grey box on a teammate's machine.
    """
    try:
        from seo_agent.workspace import faces
    except Exception:  # noqa: BLE001
        return ""
    asked = (asked or "").strip()
    if faces.is_known(asked):
        return asked
    try:
        taken = [str(r.get("emoji") or "") for r in (_ws_members.get("rows") or [])]
        return faces.suggest(taken, name)
    except Exception:  # noqa: BLE001
        return faces.DEFAULT


def _ws_announce(mods, member_id, name, emoji=""):
    """Put this person in the `members` table, so section 3's "who is in it" has something to read.

    THIS ROUTES TO THE ENGINE AND WRITES NOTHING ITSELF. It used to build the row here, which made
    the panel a second writer into Supabase: the engine owns what a member row looks like, and two
    definitions of it in two files drift the first time a column is added. `client.register_member`
    is idempotent on member_id, so a retried create or a rejoin cannot mint a duplicate person.
    (2026-09-10 — the stopgap existed only because nothing in the engine wrote the row at all, and
    "who is in it" would have been permanently empty.)

    Never fatal: a workspace whose member row did not land still works, and failing a whole join
    over a display name would be the tail wagging the dog.
    """
    client = (mods or {}).get("client")
    if client is None or not member_id:
        return ""
    err = ""
    try:
        client.register_member(name, emoji=(emoji or "") or None)
    except Exception as e:  # noqa: BLE001
        # STILL NOT FATAL -- a join must not fail over a display name -- but the caller is told
        # now. It used to swallow this silently, which is how the face picker came to answer
        # "ok" to a write Supabase had rejected (2026-09-11).
        err = _ws_scrub(e) or str(e)
    _ws_members["at"] = 0.0
    return err


def _ws_forget_checks():
    """Anything that changed the workspace makes the cached verify stale."""
    _ws_checked["at"], _ws_checked["res"] = 0.0, None
    _ws_members["at"] = 0.0


def _ws_member_rows(mods):
    """Who is in the team, read at most every _WS_MEMBERS_TTL seconds. The screen polls this
    route once a second while a job runs, and a network call per second to answer a question
    whose answer changes twice a year is not a cost worth paying."""
    client = (mods or {}).get("client")
    if client is None:
        return []
    now = time.time()
    if now - _ws_members["at"] < _WS_MEMBERS_TTL:
        return list(_ws_members["rows"])
    try:
        # A WORKSPACE THAT HAS NOT MIGRATED YET HAS NO `emoji` COLUMN, and PostgREST answers a
        # request for a column it does not have with a 400 -- which would take the whole member
        # list down for everybody still on schema 3, including the owner's own live workspace on
        # the day this shipped. Ask for the face, and fall back to the older shape if it is not
        # there yet. The faces simply do not draw until the migration runs.
        try:
            rows = client.select("members", order="joined_at", limit=50,
                                 columns="member_id,name,emoji,joined_at,last_seen_at") or []
        except Exception:  # noqa: BLE001
            rows = client.select("members", order="joined_at", limit=50,
                                 columns="member_id,name,joined_at,last_seen_at") or []
    except Exception:  # noqa: BLE001
        # Offline, or asleep. Keep showing the last answer rather than telling him the team
        # emptied out because the wifi dropped.
        _ws_members["at"] = now - (_WS_MEMBERS_TTL / 2)
        return list(_ws_members["rows"])
    _ws_members["at"], _ws_members["rows"] = now, list(rows)
    return list(rows)


def _ws_start_poller(mods):
    """Keep the one background poller running whenever a workspace is connected.

    THE PLAN'S "FOREVER AFTER" IS THIS FUNCTION. Section 1 ends "nobody presses sync, nobody
    imports anything", and nothing else in the app starts sync's poller — so without this a
    workspace would be set up perfectly and then never hear about a single change anybody
    else made. sync.start is idempotent, so calling it from every read of this route costs an
    is_alive() check and survives an app restart, which is the case a one-shot call at create
    time would miss.
    """
    sync = (mods or {}).get("sync")
    if sync is None:
        return
    try:
        sync.start()
    except Exception:  # noqa: BLE001
        pass


def _ws_verify(mods, force=False):
    """Is this workspace actually finished? schema.verify()'s dict, unchanged, at most once a
    minute.

    THIS IS WHY IT IS HERE AT ALL. A project can have all ten tables and no knowledge bucket:
    the storage policies do not always attach, and the tables survive when they do not. That
    workspace looks connected -- there is a URL, a key and an id in connections.json -- and
    nobody can ever join it, because the pack has nowhere to live. client.configured() cannot
    see that; it only reads settings, on purpose, because it is asked on every render. So the
    tab asks this as well, and draws "connected" only when this says ok.
    """
    schema = (mods or {}).get("schema")
    if schema is None:
        return None
    now = time.time()
    if not force and _ws_checked["res"] is not None and now - _ws_checked["at"] < 60.0:
        return _ws_checked["res"]
    try:
        res = schema.verify() or {}
    except Exception as e:  # noqa: BLE001
        # Offline, or the project is asleep. That is not "your workspace is broken", so the
        # last real answer stands and the tab says nothing new.
        if _ws_checked["res"] is not None:
            return _ws_checked["res"]
        return {"ok": None, "reason": _ws_scrub(e), "missing": [], "bucket": None}
    _ws_checked["at"], _ws_checked["res"] = now, res
    return res


# ---- the pack, and the quiet line -----------------------------------------------------------
# Section 2's ruling: one click updates everybody AND the joining copy, and he does not wait
# for the pack. pack.Rebuilder is the engine's implementation of exactly that — request()
# returns at once and coalesces a burst into one rebuild — so the panel's whole job is to fire
# it after a refresh and to carry its progress out to the quiet line.

def _ws_pack_progress(stage, done=0, total=0, note=""):
    stage = str(stage or "")
    if stage in ("start", "build", "pack", "verify"):
        _ws_pack["state"] = "building"
    elif stage in ("upload", "publish"):
        _ws_pack["state"] = "uploading"
    elif stage in ("done", "error"):
        _ws_pack["state"] = "idle"
    _ws_pack["note"] = str(note or "")


def _ws_rebuilder(mods):
    if _ws_rebuilder_ref[0] is not None:
        return _ws_rebuilder_ref[0]
    if not _ws_ready(mods, "pack", "client", "sync"):
        return None
    client, pack, sync = mods["client"], mods["pack"], mods["sync"]
    try:
        _ws_rebuilder_ref[0] = pack.Rebuilder(
            client, progress=_ws_pack_progress, cursor=lambda: sync.last_seen_id(client))
    except Exception:  # noqa: BLE001
        return None
    return _ws_rebuilder_ref[0]


def ws_pack_refresh(reason=""):
    """Ask for the shared pack to be rebuilt, and return immediately.

    Called from the catalogue refresh, which is the click section 2 is about. It never raises
    and never blocks: a person with no workspace, or no network, must not have a working
    refresh turned into an error by a feature he has not set up.
    """
    mods = _ws()
    if not mods:
        return False
    try:
        if not mods["client"].configured():
            return False
    except Exception:  # noqa: BLE001
        return False
    rb = _ws_rebuilder(mods)
    if rb is None:
        return False
    try:
        rb.request(reason or "the catalogue was refreshed")
        return True
    except Exception:  # noqa: BLE001
        return False


# ---- create ------------------------------------------------------------------------------

def _ws_create_worker(url, key, name, member_id, member_name, token, confirm=False):
    """Set the workspace up, prove it is there, upload the pack, then hand back the link.

    ONE WORKER, TWO DOORS, ONE VERDICT. `confirm=True` is the paste route's "I've run it"
    button: schema.confirm() verifies and remembers. Otherwise schema.create() runs the script
    if it was given a token and verifies either way. Both come back with a single `ok`, and
    that flag is the only thing this function reads to decide anything.

    `token` is optional and dies with this function: one argument, one call, rebound to "" in
    that call's `finally`, before anything else can raise with it still in scope.
    """
    mods = _ws()
    schema, pack, client, sync = mods["schema"], mods["pack"], mods["client"], mods["sync"]
    try:
        _ws_say(phase="tables",
                step="Checking your project" if confirm else "Setting up your workspace", pct=5)
        try:
            res = (schema.confirm(url, key) if confirm
                   else schema.create(url, key, token=token or None)) or {}
        except Exception as e:  # noqa: BLE001
            # schema could not even turn this into the paste route itself. Offer the route
            # anyway, with the reason: a person must never be stuck.
            _ws_paste_route({"sql": _ws_sql(mods), "editor_url": _ws_editor(mods, url)},
                            _ws_scrub(e, token))
            return
        finally:
            token = ""

        # REMEMBER THE PROJECT BEFORE JUDGING IT, and this is not a tidy-up — it is the fix for a
        # real one (2026-09-10). The owner created his workspace, verify() wrongly called it
        # incomplete, and this function returned here without saving a thing. The tables, the
        # triggers and the bucket were all sitting in his Supabase project, and Sutra had no idea
        # they existed: next time he opened Connections it offered him a blank Create form, as if
        # nothing had ever happened.
        #
        # The URL and the key are HIS INPUT and they are valid whether or not the script finished.
        # Losing them turns "not finished, here is what to do" into "start again from nothing", and
        # it breaks the button that is supposed to rescue him: "I've run it" has to check the same
        # project, and it cannot if nobody wrote down which project that was.
        #
        # So an unfinished setup is now a RESUMABLE state, which is what the screen already draws.
        client.save_settings(workspace_url=url, workspace_key=key)
        _ws_save_name(name)

        # THE ONE FLAG. schema ran verify() itself, whichever door this came through, and
        # verify is the only function allowed to say a workspace is ready. Note what `ok` false
        # covers: no token yet, a script that half-applied, AND a project whose tables are all
        # there but whose knowledge bucket is not — a workspace nobody could ever join. All
        # three are the same state to a person: not finished, and here is what to do.
        if not res.get("ok"):
            _ws_paste_route(res)
            return

        ws_id = str(res.get("workspace_id") or "")
        client.save_settings(member_id=member_id, member_name=member_name)
        if name:
            try:
                client.update("workspace", {"id": ws_id}, {"name": name})
            except Exception:  # noqa: BLE001
                pass          # the local name still shows; a display name is not worth failing on
        _ws_announce(mods, member_id, member_name, _ws_face("", member_name))
        _ws_forget_checks()

        _ws_say(phase="pack", step="Uploading the knowledge pack", pct=45,
                link=_ws_link(mods, _ws_settings(mods)))

        def on_progress(stage, done=0, total=0, note=""):
            _ws_pack_progress(stage, done, total, note)
            base = 45 if str(stage) in ("build", "pack", "start") else 70
            span = 25 if base == 45 else 25
            pct = base + int(span * (float(done) / float(total))) if total else base
            _ws_say(pct=max(45, min(97, pct)), done_bytes=int(done or 0),
                    total_bytes=int(total or 0), step=str(note or "Uploading the knowledge pack"))

        try:
            pack.publish(client, last_seen_id=sync.last_seen_id(client), progress=on_progress)
        except Exception as e:  # noqa: BLE001
            # The workspace EXISTS — verify said so — so this is not a failed create. Calling
            # it one would throw away ten real tables and the saved credentials to tidy a screen.
            _ws_say(phase="done", step="", pct=100, link=_ws_link(mods, _ws_settings(mods)),
                    finished_at=time.time(),
                    error={"what": "The workspace is made and the link works, but the knowledge "
                                   "pack did not finish uploading: " + _ws_scrub(e),
                           "do": "Nothing is lost. Press Check for changes on the Knowledge tab "
                                 "and it uploads again. Until it does, a teammate cannot join."})
            return
        finally:
            _ws_pack["state"] = "idle"

        _ws_say(phase="done", step="", pct=100, link=_ws_link(mods, _ws_settings(mods)),
                finished_at=time.time())
    except Exception as e:  # noqa: BLE001
        _ws_fail("The workspace could not be created: " + _ws_scrub(e, token),
                 "Check the project is awake in the Supabase dashboard, then press Try again.")


def _ws_sql(mods):
    try:
        return mods["schema"].sql()
    except Exception:  # noqa: BLE001
        return ""


def _ws_editor(mods, url):
    try:
        return mods["schema"].editor_url(mods["schema"].project_ref(url))
    except Exception:  # noqa: BLE001
        return "https://supabase.com/dashboard"


def _ws_begin(body, confirm):
    """The shared front half of create and confirm: check what was typed, then put the slow
    part on a thread. Nothing here decides anything about the workspace itself."""
    mods = _ws()
    if not _ws_ready(mods, "schema", "pack", "link", "client", "sync"):
        return _bad("The team workspace is not in this build of Sutra, so nothing was "
                    "attempted. Update Sutra and try again.", 501)

    url = str(body.get("url") or "").strip().rstrip("/")
    key = str(body.get("key") or "").strip()
    name = str(body.get("name") or "").strip()[:80]
    token = str(body.get("token") or "").strip()

    for problem in (_ws_check_url(url), _ws_check_key(key)):
        if problem:
            return _bad(problem)
    # THE TOKEN IS OPTIONAL. There is not one on the owner's machine and there may never be,
    # so a create with no token is not a mistake — it is the paste route, which comes straight
    # back with the script. Only a token that is present and malformed is refused, and it is
    # refused HERE, in the request, so nobody watches a spinner start and then fail.
    if token:
        problem = _ws_check_token(token)
        if problem:
            return _bad(problem)

    s = _ws_settings(mods)
    member_id = _ws_member_id(mods)
    member_name = (str(body.get("member_name") or "").strip()
                   or str(s.get("member_name") or "").strip() or "The owner")[:80]
    _ws_start_job("create")
    if not _spawn("workspace", lambda: _ws_create_worker(url, key, name, member_id,
                                                         member_name, token, confirm)):
        return _bad("A workspace job is already running. Wait for it to finish.", 409)
    return {"started": True}


@router.post("/workspace/create")
def api_workspace_create(body: dict = Body(...)):
    """Start a workspace on a Supabase project the company owns.

    `token` is optional. With one, schema.create runs the script through the management API and
    then verifies. Without one, it verifies anyway and hands back the paste route — which is a
    route, not a refusal, and is how the owner's own first run is expected to go.
    """
    return _ws_begin(body, confirm=False)


@router.post("/workspace/confirm")
def api_workspace_confirm(body: dict = Body(...)):
    """The paste route's "I've run it" button. schema.confirm verifies and remembers.

    A route of its own rather than a flag on create, because the two are different questions:
    create asks "set this up", confirm asks "is it set up now". They share a worker so that
    both are judged by the same verify and can never drift into two definitions of ready.
    """
    return _ws_begin(body, confirm=True)


@router.post("/workspace/update")
def api_workspace_update(body: dict = Body(default={})):
    """Bring an existing workspace up to the schema this Sutra expects.

    A workspace made before a change cannot get a new table from the setup script: every statement
    in it is `create ... if not exists`, and the tables are already there. schema.migrate() applies
    only the steps that workspace has not run, in order, each in its own transaction with its own
    version bump, and stops at the first failure. With no personal access token it comes back as
    the paste route carrying JUST those steps, never the whole create script.

    It is never run automatically: it needs a token or a person pasting into the SQL Editor, and
    both of those are somebody's choice to make.
    """
    mods = _ws()
    if not _ws_ready(mods, "schema", "client"):
        return _bad("The team workspace is not in this build of Sutra, so nothing was "
                    "attempted. Update Sutra and try again.", 501)
    token = str(body.get("token") or "").strip()
    if token:
        problem = _ws_check_token(token)
        if problem:
            return _bad(problem)

    def work():
        try:
            res = mods["schema"].migrate(token=token or None) or {}
        except Exception as e:  # noqa: BLE001
            _ws_fail("The update could not run.", _ws_scrub(e, token))
            return
        if res.get("route") == "paste":
            _ws_paste_route(res, res.get("reason") or "")
            return
        if res.get("ok"):
            _ws_verify(mods, force=True)          # the cached verdict is now out of date
            _ws_say(phase="done", step=str(res.get("reason") or "Workspace updated."),
                    finished_at=time.time())
        else:
            _ws_fail("The update did not finish.", _ws_scrub(res.get("reason") or "", token))

    _ws_start_job("update")
    if not _spawn("workspace", work):
        return _bad("A workspace job is already running. Wait for it to finish.", 409)
    return {"started": True}


# ---- join --------------------------------------------------------------------------------

def _ws_join_worker(url, key, ws_id, name, member_id, emoji=""):
    mods = _ws()
    schema, pack, client, sync = mods["schema"], mods["pack"], mods["client"], mods["sync"]
    try:
        _ws_say(phase="verify", step="Checking the workspace is there", pct=1)
        try:
            v = schema.verify(url, key) or {}
        except Exception as e:  # noqa: BLE001
            _ws_fail("Sutra could not reach that workspace: " + _ws_scrub(e),
                     "Check you are online. A free Supabase project that has been idle for a "
                     "week takes about a minute to wake up, so try again in a minute.")
            return
        if not v.get("ok"):
            # verify() has already written the sentence for a person, and it names the actual
            # thing that is wrong — no tables, some tables, tables it cannot read with this
            # key, or tables with no knowledge bucket behind them. It is passed through
            # UNCHANGED. Rewriting it is how a message ends up blaming the project URL for a
            # storage problem, which is a mistake this feature has already made once.
            _ws_fail(str(v.get("reason") or "That workspace is not finished."),
                     "Nothing on this Mac was touched. Ask whoever set it up to open their "
                     "Connections tab — it will show them the same thing and what to do — "
                     "then send you the link again.")
            return

        client.save_settings(workspace_url=url, workspace_key=key,
                             workspace_id=str(v.get("workspace_id") or ws_id),
                             member_id=member_id, member_name=name)
        _ws_announce(mods, member_id, name, emoji)
        _ws_forget_checks()
        try:
            row = client.one("workspace", columns="name") or {}
            _ws_save_name(row.get("name") or "")
        except Exception:  # noqa: BLE001
            pass

        _ws_say(phase="download", step="Downloading the team's knowledge", pct=1)

        def on_progress(stage, done=0, total=0, note=""):
            pct = int(100 * (float(done) / float(total))) if total else 0
            _ws_say(pct=max(0, min(99, pct)), done_bytes=int(done or 0),
                    total_bytes=int(total or 0),
                    step=str(note or "Downloading the team's knowledge"))

        try:
            got = pack.join(client, progress=on_progress) or {}
        except Exception as e:  # noqa: BLE001
            # Joined but not filled. Say exactly that: the credentials are real, and pressing
            # Try again resumes rather than starting over.
            _ws_fail("You are on the team, but the knowledge did not finish coming down: "
                     + _ws_scrub(e),
                     "Press Try again. Nothing you have on this Mac was touched.")
            return

        # WHERE TO REPLAY FROM. pack.join returns the boundary the pack was built at; saving it
        # as last_seen_id is what makes the next poll pick up exactly the changes the pack does
        # not already contain. Too low replays them twice, too high loses them for good.
        #
        # catch_up() SAVES THAT BOUNDARY AND THEN DRAINS IT IMMEDIATELY, rather than saving it and
        # waiting for the poller's next tick. Downloading 33.6 MB takes long enough that changes
        # land while it runs, so a joiner who is handed the files and nothing else is knowingly
        # stale the second they are told they are done, with nothing on screen saying so. It never
        # raises: a join that fetched the whole pack must not report failure because the poll after
        # it hit a flat network. (2026-09-10.)
        try:
            from seo_agent.workspace import sync as _ws_sync_join
            _ws_sync_join.catch_up(client, replay_from=got.get("replay_from"))
        except Exception:  # noqa: BLE001
            pass
        _ws_say(phase="done", step="", pct=100, finished_at=time.time())
    except Exception as e:  # noqa: BLE001
        _ws_fail("Joining did not finish: " + _ws_scrub(e),
                 "Check you are online and press Try again.")


@router.post("/workspace/join")
def api_workspace_join(body: dict = Body(...)):
    """Paste the link, type a name, press Done. The link carries the project URL, the
    publishable key and the workspace id, and nothing in it can make or drop a table."""
    mods = _ws()
    if not _ws_ready(mods, "schema", "pack", "link", "client", "sync"):
        return _bad("The team workspace is not in this build of Sutra, so nothing was "
                    "attempted. Update Sutra and try again.", 501)

    raw = str(body.get("link") or "").strip()
    name = str(body.get("name") or "").strip()[:80]
    # The face is optional on the wire. A client that does not send one, or sends something not
    # in the pack, gets a face chosen for them rather than a refusal -- an avatar is not worth
    # blocking somebody's join over.
    face = _ws_face(str(body.get("emoji") or ""), name)
    if not raw:
        return _bad("Paste the link your teammate sent you.")
    if not name:
        return _bad("Type the name your team will see beside your work.")
    try:
        url, key, ws_id = mods["link"].read_link(raw)
    except Exception as e:  # noqa: BLE001
        # link.read_link says what is wrong with a link better than a generic sentence can.
        return _bad(_ws_scrub(e) or "That link could not be read. Copy it again from your "
                    "teammate's Connections tab — it is one long line with no spaces in it.")
    url = str(url or "").strip().rstrip("/")
    problem = _ws_check_url(url) or _ws_check_key(str(key or ""))
    if problem:
        return _bad("That link is not a Sutra workspace link. " + problem)
    if not str(ws_id or "").strip():
        return _bad("That link is missing the workspace it points at. Ask for it again.")

    _ws_start_job("join")
    member_id = _ws_member_id(mods)
    if not _spawn("workspace", lambda: _ws_join_worker(url, str(key), str(ws_id), name, member_id, face)):
        return _bad("A workspace job is already running. Wait for it to finish.", 409)
    return {"started": True}


# ---- what is true right now ----------------------------------------------------------------

@router.get("/workspace")
def api_workspace(check: int = 0):
    """The resting state and the running job, in the one read the screen polls.

    `link` is here on purpose. It carries the publishable key, which the plan puts in the link
    by design: it can read and write this workspace's rows, bounded by row rules, and nothing
    else. The two credentials that are NOT here and never will be are the secret key and the
    personal access token.
    """
    mods = _ws()
    job = _ws_get_job()
    blank = {"installed": bool(mods), "configured": False, "verify": None, "workspace": None,
             "me": None, "members": [], "link": "", "sync": None, "job": job}
    if not _ws_ready(mods, "client", "link", "sync"):
        return blank
    try:
        configured = bool(mods["client"].configured())
    except Exception:  # noqa: BLE001
        configured = False
    if not configured:
        return blank
    s = _ws_settings(mods)
    try:
        st = mods["sync"].status() or {}
    except Exception:  # noqa: BLE001
        st = {}
    out = st.get("outbox") or {}
    # `check` is the screen saying "the Connections tab is open, so a network round trip is
    # worth it". Off that tab this route is polled only to keep the quiet line honest, and
    # eleven probes for a footnote would be a poor trade.
    _ws_start_poller(mods)
    checked = _ws_verify(mods) if check else _ws_checked["res"]
    return {
        "installed": True,
        "configured": True,
        "verify": checked,
        "workspace": {"name": _ws_name() or "The team workspace",
                      "url": s.get("workspace_url") or "", "id": s.get("workspace_id") or ""},
        "me": {"member_id": s.get("member_id") or "", "name": s.get("member_name") or "",
               "emoji": s.get("member_emoji") or ""},
        "members": _ws_member_rows(mods),
        "link": _ws_link(mods, s),
        "sync": {"pending": int(out.get("queued") or 0),
                 "pack_state": _ws_pack["state"],
                 "last_seen_at": st.get("updated_at"),
                 # THE SAME NEWS FROM THE OTHER DIRECTION. verify().needs_update is "this
                 # workspace is a version behind"; this one is "somebody has already saved
                 # something that could not be sent because of it". Either is enough to offer
                 # the update; the screen shows it once, not twice.
                 "needs_update": st.get("needs_update") or None,
                 "stuck": st.get("stuck") or None},
        "job": job,
    }


@router.get("/workspace/faces")
def api_workspace_faces():
    """The faces a person may pick, which are still free, and which one to pre-select.

    Served rather than hardcoded in the UI so the pack has ONE definition. A second copy in
    JavaScript is a copy that drifts the first time a face is added.
    """
    try:
        from seo_agent.workspace import faces
    except Exception:  # noqa: BLE001
        return {"faces": [], "names": {}, "free": [], "suggested": ""}
    mods = _ws()
    rows, name = [], ""
    if mods:
        try:
            rows = _ws_member_rows(mods)
            name = (_ws_settings(mods) or {}).get("member_name") or ""
        except Exception:  # noqa: BLE001
            rows = []
    taken = [str(r.get("emoji") or "") for r in rows]
    return {"faces": list(faces.FACES), "names": dict(faces.NAMES),
            "free": faces.free(taken), "suggested": faces.suggest(taken, name)}


@router.post("/workspace/face")
def api_workspace_face(body: dict = Body(...)):
    """Change the face you already have. Separate from join on purpose: picking one at join
    time is a step in a flow, changing it later is a one-click edit, and folding the second
    into the first would mean re-running a join to swap an emoji."""
    mods = _ws()
    if not _ws_ready(mods, "client"):
        return _bad("The team workspace is not in this build of Sutra.", 501)
    try:
        if not mods["client"].configured():
            return _bad("You are not in a workspace yet.")
    except Exception:  # noqa: BLE001
        return _bad("You are not in a workspace yet.")
    asked = str(body.get("emoji") or "").strip()
    try:
        from seo_agent.workspace import faces
    except Exception:  # noqa: BLE001
        return _bad("This build has no face pack.")
    if not faces.is_known(asked):
        return _bad("Pick one of the faces on offer.")
    s = _ws_settings(mods) or {}
    mid = s.get("member_id") or ""
    # A FACE IS PICKED ONCE (owner, 2026-09-11: "once chosen nobody can change it"). Enforced
    # HERE and not only in the UI, because a hidden button is not a rule -- anything that can
    # POST could still swap it. Read the row rather than trusting the local settings copy: the
    # question is what the WORKSPACE has, which is what teammates see.
    try:
        mine = next((m for m in (_ws_member_rows(mods) or [])
                     if str(m.get("member_id") or "") == mid), None)
    except Exception:  # noqa: BLE001
        mine = None
    if mine and str(mine.get("emoji") or "").strip():
        return _bad("You already have a face, and it stays yours. Faces are picked once.")
    err = _ws_announce(mods, mid, s.get("member_name") or "", asked)
    if err:
        # THE COMMON CASE IS A WORKSPACE THAT HAS NOT MIGRATED. members.emoji arrives in schema
        # 4; on an older workspace there is no column to write to and Supabase rejects it. Say
        # that, and say what to do, rather than reporting a save that did not happen.
        if "emoji" in err.lower() or "column" in err.lower() or "PGRST204" in err:
            return _bad("Your workspace has not been updated yet, so there is nowhere to keep a "
                        "face. Open Connections and run the workspace update, then pick again.")
        return _bad("That face could not be saved: " + err)
    return {"ok": True, "emoji": asked, "name": faces.name_of(asked)}


@router.post("/workspace/dismiss")
def api_workspace_dismiss(body: dict = Body(default={})):
    """Forget a job that has stopped, so the section goes back to its resting state.

    A route of its own rather than a flag on one of the other four, because "clear this screen"
    is not "leave the team" and must never be able to become it by a typo. A job still RUNNING
    is refused: throwing away the only record of a worker that is still making tables is how a
    half-made workspace ends up on screen as if nothing had happened.
    """
    global _ws_job
    with _ws_job_lock:
        job = dict(_ws_job) if _ws_job else None
        if job and job.get("phase") in ("starting", "tables", "verify", "pack", "download"):
            return _bad("That job is still running. Let it finish or fail before clearing it.", 409)
        _ws_job = None
    return {"ok": True}


@router.post("/workspace/leave")
def api_workspace_leave(body: dict = Body(default={})):
    """Stop being on the team.

    Local knowledge is untouched: it is this person's own copy, it is what Sutra reads from
    (plan section 6), and deleting it would take their work away rather than a workspace.
    Nothing is dropped in Supabase either — leaving is not ending the team's data.
    """
    global _ws_job
    mods = _ws()
    if _ws_ready(mods, "sync"):
        try:
            mods["sync"].stop()          # stop listening before the credentials go
        except Exception:  # noqa: BLE001
            pass
    if _ws_ready(mods, "client"):
        try:
            mods["client"].forget()
        except Exception:  # noqa: BLE001
            pass
    _ws_save_name("")
    _ws_forget_checks()
    _ws_members["rows"] = []
    _ws_rebuilder_ref[0] = None
    with _ws_job_lock:
        _ws_job = None
    return {"ok": True}


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
    # TWO WRITERS, TWO SHAPES. assets/merge.py writes a LIST of {method, file, state, ideas};
    # assets/import_sheet.py writes a DICT of {method: state}. Normalised here rather than at the
    # two writers, because the list carries the per-method detail the merge's own line needs and
    # the dict is what this screen wants. Found 2026-09-10: the list form raised
    # "AttributeError: 'list' object has no attribute 'items'" and took the whole Asset ideas tab
    # down with it. It had never fired only because this install's sheet was imported.
    raw = m.get("methods") or {}
    states = ({r.get("method"): r.get("state") for r in raw if isinstance(r, dict)}
              if isinstance(raw, list) else raw)
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
    # THE SHEET IS PART OF "AM I SET UP". Without it the opening screen has no way to know that
    # 1,890 ranked ideas exist, so its first starter chip offered six fresh competitor guesses
    # instead of the top idea. The model and the tool both refuse that now; the chip is the same
    # rule on screen, and it needs this fact to draw itself. (2026-09-10.)
    try:
        from seo_agent.tools import build_assets as _ba
        assets = _ba.status()          # {built, total, counts, methods_run, next}
    except Exception:  # noqa: BLE001 — health must answer even when the sheet cannot be read
        assets = {"built": False, "next": None}
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
            "assets": {"built": bool(assets.get("built")),
                       "total": assets.get("total", 0),
                       "open": (assets.get("counts") or {}).get("open", 0),
                       "next": assets.get("next")},
            "chats": len(store.list_chats()),
            "data_dir": store.data_dir()}
