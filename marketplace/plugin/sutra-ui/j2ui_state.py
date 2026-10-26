"""j2ui_state.py -- `api/state`: the 56 keys the J2 page polls, drawn from one read of the department (UI port, step C3).

The page polls this every 700 ms and a missing key blanks it, so every key is always there. j2ui-core fills the keys the
record answers (the chat, status, the one ask the owner is asked, the goal, the budget, the version count); j2ui_work fills
its thirteen (workflows, atoms, lanes, conflicts, audits...), each empty when it fails. What Sutra does not have is the
prototype's own empty form: memory is off, there is no report, no model name is recorded.

The rules the page's composer and strip depend on:
    status    'waiting' whenever something waits on the owner, even while an engine runs (the page disables the composer and
              every option button while status is 'running', so a pending stamp could not be answered); 'running' while a
              function works or an engine runs and nothing waits on the owner; 'idle' before any cycle, post or chat
    paused    one ask at a time: Identity's open question, then asks that offer options, then asks that take a stamp, oldest first
    outcome   'Done' or 'Done with open items' only; never 'Stopped' or 'Crashed' (the page turns those into a failure card)
"""
import os

import functions_view as F
import j2_runtime as J
import owner_words
import website_dept as W
import j2ui_chat as CH
import j2ui_common as C

TAGS = {"refuse": "never"}                 # a rule's tag as the screen says it (22-website.js WB_TAG_SAYS)
MORE = " (%d more waiting)"
LABEL_CHARS = 120


# ---- the one ask the owner is asked --------------------------------------------------------------------------------------
def _created(a):
    return str(a.get("created"))


def pick_paused(c):
    """The ask the state's `paused` shows, or None: {ask, kind (the pause kind), msg (the id of its question message), form
    ('words', 'options' or 'stamp'), question, options (the labels shown), label, more}. Identity's open question first, then
    the asks that offer options, then the asks that take a stamp, each oldest first."""
    pending = [a for a in c.asks if a.get("status") == "pending" and a.get("id")]
    open_id = c.cur.get("open_ask") if J.enabled() else None
    first = [a for a in pending if a["id"] == open_id and a.get("kind") == "j2_identity"]
    rest = sorted((a for a in pending if a.get("options")), key=_created) + \
        sorted((a for a in pending if not a.get("options") and a.get("kind") != "j2_identity"), key=_created)
    order = first + rest
    if not order:
        return None
    a = order[0]
    form = CH.form_of(a)
    msg = c.ask_msg.get(a["id"])
    ids = c.ask_opts.get(msg) if msg else None
    if form == "options":
        by_id = {o.get("id"): o for o in a.get("options") or []}
        shown = [by_id[i] for i in (ids if ids is not None else [o.get("id") for o in W.offered(c.d, a)]) if i in by_id]
        labels = [CH._label(o) for o in shown]
    else:
        labels = list(CH.STAMP_LABELS) if form == "stamp" else []
    text = a.get("why") or a.get("title") or CH._flat(a.get("text"))[:LABEL_CHARS]
    label = CH._flat(owner_words.plain(text)) + (MORE % (len(order) - 1) if len(order) > 1 else "")
    return {"ask": a, "kind": CH.pause_of(a), "msg": msg, "form": form, "label": label, "more": len(order) - 1,
            "question": CH._line(owner_words.kept(a.get("text") or "", a.get("words"))), "options": labels}


def paused_of(c):
    p = c.paused_ask
    if not p:
        return None
    return {"kind": p["kind"], "questions": [{"question": p["question"], "options": list(p["options"])}], "msg": p["msg"],
            "label": p["label"], "choices": None}


# ---- the rest of the state ------------------------------------------------------------------------------------------------
def _steps():
    return {str(n): "%s %s" % (J.JOURNEY[n], name) for n, name in F.STEPS}


def _goal(c):
    d = c.d
    items = W.items_of(d)
    rules = ["%s: %s" % (TAGS.get(r.get("tag"), r.get("tag")), r.get("line") or r.get("text") or "") for r in d.get("rules") or []
             if isinstance(r, dict)]
    return {"statement": d.get("goal") or "", "site_name": d.get("name") or "", "audience": "", "standards": [], "rules": rules,
            "done_when": [i.get("text") for i in items], "charter_items": [i.get("text") for i in items],
            "to_be_confirmed": [{"criterion": i.get("text"), "fact": i.get("confirm")} for i in items if i.get("confirm")],
            "confirmed_facts": [], "dropped_by_requester": []}


def _has_goal(c):
    return bool(c.d) and (bool(c.arts and c.arts[0]["versions"]) or bool(W.requests(c.ref)))


def _previewable(c):
    return next((a for a in c.arts if a["name"] == "Build"), c.arts[-1] if c.arts else None)


def _outcome(c):
    if c.state != "done":
        return None
    open_items = any(i.get("confirm") for i in W.items_of(c.d)) or any(a.get("kind") == "finding" and a.get("status") == "pending" for a in c.asks)
    return "Done with open items" if open_items else "Done"


def _working(c):
    """The function that works now (lower case), else the running engine's W-k, else None."""
    for n in (c.fv or {}).get("functions") or []:
        if n.get("state") == "working":
            return n.get("fn")
    return next((e["wid"] for e in c.engines if e.get("state") == "Running" and e.get("wid")), None)


def _status(c, paused, working):
    if not c.cur.get("cycle_id") and not c.posts and not c.chat:
        return "idle"
    if paused:
        return "waiting"
    return "running" if working or any(e.get("state") == "Running" for e in c.engines) else "waiting"


def _own(c):
    paused = paused_of(c)
    working = _working(c)
    budget = (c.fv or {}).get("budget") or {}
    build = _previewable(c)
    state = C.EMPTY_STATE()
    try:
        step = int(c.cur.get("step") or ((c.fv or {}).get("cycle") or {}).get("step") or 0)
    except (TypeError, ValueError):
        step = 0
    state.update({
        "chat": list(c.chat), "total": len(c.chat), "status": _status(c, paused, working), "thinking": working, "turn": working,
        "step": step, "steps": _steps(), "goal": _goal(c) if _has_goal(c) else None,
        "stamped": any(e.get("action") == "identity.assessed" for e in c.events), "budget": int(budget.get("calls_limit") or 0),
        "spent": int(budget.get("calls") or 0), "versions": len(build["versions"]) if build else 0,
        "cycle": int(c.cur.get("round") or (1 if c.cur.get("cycle_id") else 0)),
        "calls": sum(int((r.get("spend") or {}).get("calls") or 0) for r in c.runs), "done": c.state == "done",
        "paused": paused, "outcome": _outcome(c), "mock": os.environ.get("SUTRA_WEBSITE_OFFLINE") == "1"})
    return state


def _lazy(name, fn, c, default):
    """A builder of another module of the adapter, imported when it is needed: when the module (or the builder) is not there,
    or fails, `default`."""
    try:
        build = getattr(__import__(name), fn, None)
        return default if build is None else build(c)
    except ImportError:
        return default
    except Exception as exc:  # noqa: BLE001 -- a builder never takes the state down with it
        c.reasons.append("%s: %s" % (name, type(exc).__name__))
        return default


def is_live_run(c, run):
    """A run the page may name: none, the live cycle's id, or the department's ref. Sutra keeps one live cycle per department."""
    return not run or run in (c.cur.get("cycle_id"), c.ref)


def runs(c):
    """api/runs: the live run and no saved ones (a cycle id listed here would be set by the page as ?run= and load nothing)."""
    return {"live": c.cur.get("cycle_id") or c.ref, "runs": []}


def build_state(c, since=0, run=None):
    """The 56 keys of api/state. `since` is a place in the chat list (chat[since:], total the whole length), clamped at 0;
    `run` is the router's to validate (is_live_run). The state is built once per read of the department; only the slice of the
    chat differs per call."""
    try:
        since = max(0, int(since or 0))
    except (TypeError, ValueError):
        since = 0
    base = c.memo.get("state")
    if base is None:
        base = _own(c)
        board = _lazy("j2ui_board", "build", c, None)
        base["has_board"] = bool(isinstance(board, dict) and board.get("entries"))
        work = _lazy("j2ui_work", "build", c, None)
        if isinstance(work, dict):
            base.update({k: work[k] for k in C.WORK_KEYS if k in work})
        c.memo["state"] = base
    out = dict(base)
    out["chat"] = base["chat"][since:]
    return out
