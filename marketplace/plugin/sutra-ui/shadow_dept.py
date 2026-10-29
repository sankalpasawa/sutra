"""shadow_dept.py -- a task is given a department to use, or one is made for it, by an agent and a covering of code
(PRD amendment A5, A5.3).

One decision for each task, taken when the task is about to start (app._delegate_spawn) or earlier on request. The question is
put to the task's Shadow chat, which has no tools and answers in text; `parse_choice` validates the answer as `dept.choice`.
Code then covers it (`cover`, DR-1 to DR-8, in order): the agent chooses, the covering decides what stands. The app does every
write: `apply` makes the department through founding.spawn, and `record` stores the validated `dept.decision` on the task and
in the ledger.

LINK-ONLY. A decision to use a department is recorded and linked; the department is not messaged and the worker runs as it did.
Shadow never starts a department the owner stopped. A create is held for the owner's yes when an `ask` rule on Root says so
(DR-7); nothing is made and no ask is raised. The owner says yes with confirmed=true on the department route.

Nothing here names a kind of department: the Library's kinds and their use cases are data."""
import asyncio
import inspect
import json
import re
import time

import dept_read
import layer_schema as S
import shadow_dept_prompt as PROMPT
import shadow_ledger
import website_dept as W

#: injectable, so a test stubs the model: {"fn": f}, f(text) -> the reply (text), sync or async. None means the task's own chat.
CHOOSER = {"fn": None}
TIMEOUT_S = 45
SETTING = "shadow.dept_root"
RATE_MAX = 3                         # DR-6: creates under one Root in the window
RATE_WINDOW_S = 10 * 60
DUPLICATE_AT = 0.6                   # DR-4: token overlap of name and goal
RULE_TAGS = ("always", "refuse", "ask")
RULES_SHOWN = 10
S_MID = r"m-[0-9a-f]{12}"           # a task id


# ---- which Root, and the facts ----------------------------------------------------------------------------------
def roots():
    return [d for d in W.list_depts() if d.get("kind") == "root" and d.get("ref")]


def pick_root():
    """The Root the task is given a department under: the only one; with several, the shadow setting `dept_root`, else the one
    whose departments were active last. None when there is none (DR-1)."""
    rs = roots()
    if not rs:
        return None
    if len(rs) == 1:
        return rs[0]["ref"]
    try:
        import providers
        want = providers._raw_settings().get(SETTING)
    except Exception:  # noqa: BLE001 -- a settings file that cannot be read is no preference
        want = None
    if want in {r["ref"] for r in rs}:
        return want

    return max(rs, key=lambda r: dept_read.newest(r["ref"]))["ref"]


def task_words(mission):
    """The task as words: its objective and what it must be done by."""
    checks = [str(c.get("check") or "") for c in (mission or {}).get("done_when") or [] if isinstance(c, dict)]
    return " ".join(w for w in [str((mission or {}).get("objective") or "")] + checks if w).strip()


def owner_rules(root_ref):
    try:
        import engine_runtime
        rules = engine_runtime._effective_rules(root_ref, W.dept(root_ref) or {})
    except Exception:  # noqa: BLE001 -- the rules are context for the model, never a reason to fail the task
        return []
    return [{"tag": r["tag"], "line": str(r.get("line") or "")[:200]} for r in rules
            if isinstance(r, dict) and r.get("tag") in RULE_TAGS and r.get("line")][:RULES_SHOWN]


def recent_creates(rows, now=None):
    """DR-6: the departments under the Root born inside the window, from the `created` stamps in their dept.json."""
    now = time.time() if now is None else now
    return sum(1 for r in rows if r.get("created") and 0 <= now - (W._ts(r["created"]) or 0) <= RATE_WINDOW_S)


# ---- the choice: text in, a validated dept.choice out ---------------------------------------------------------------
def parse_choice(text):
    """The first JSON object in the reply, validated as dept.choice; None when there is none or it does not fit (the covering
    reads None as DR-8). A fault is a row on the interface's list, never a raise: a bad answer never blocks the task."""
    raw = str(text or "")
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    body = fence.group(1) if fence else raw[raw.find("{"):raw.rfind("}") + 1] if "{" in raw else ""
    try:
        obj = json.loads(body)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("done_items") is None:
        obj.pop("done_items", None)
    if S.report("dept.choice", S.validate("dept.choice", obj), never_refuse=True):
        return None
    return obj


def _fallback(words, cands, why):
    """No agent answer: use a candidate only when its name is in the task's words, else nothing. Never blocks the task."""
    low = words.lower()
    for c in sorted(cands, key=lambda c: -len(c["name"])):
        if c["name"].strip() and c["name"].lower() in low:
            return {"action": "use", "ref": c["ref"], "reason": ("%s; the task names %s" % (why, c["name"]))[:400],
                    "confidence": "low"}
    return {"action": "none", "reason": why[:400], "confidence": "low"}


async def _ask(text, mission):
    """The agent's reply, or None (offline, timed out, or the chat could not answer)."""
    fn = CHOOSER["fn"]
    if fn is None:
        try:
            import shadow_task_chat
            chat = shadow_task_chat.get((mission or {}).get("id"))
        except Exception:  # noqa: BLE001
            chat = None
        if chat is None or not chat.alive:
            return None
        fn = chat.dept_choice
    try:
        reply = fn(text)
        if inspect.isawaitable(reply):
            reply = await asyncio.wait_for(reply, TIMEOUT_S)
        return reply if isinstance(reply, str) else None
    except Exception:  # noqa: BLE001 -- a timeout or a dead chat is the offline fallback
        return None


# ---- the covering -------------------------------------------------------------------------------------------------
def _over(overrides, rule, note):
    overrides.append({"rule": rule, "note": note[:200] or rule})


def cover(choice, ctx):
    """DR-1 to DR-8, in order, over a validated choice. `ctx`: root_ref, org (bool), children {ref: row}, kinds, birth_ask,
    recent (creates in the window), fallback (None, 'offline' or 'bad_output'). Returns final_action, final_ref, overrides,
    held, held_reason. Each override is shown with the decision."""
    act, ref = choice["action"], choice.get("ref")
    kind, name, goal = choice.get("kind"), choice.get("name"), choice.get("goal")
    over, held, why = [], False, None
    kids = ctx["children"]
    if not ctx.get("root_ref") or not ctx.get("org"):                                              # DR-1
        _over(over, "no_org", "there is no organisation to give the task a department")
        return {"final_action": "none", "final_ref": None, "overrides": over, "held": False, "held_reason": None}
    if act == "use" and ref not in kids:                                                           # DR-2
        _over(over, "not_a_child", "the department chosen is not one of this organisation's")
        act, ref = ("create", None) if kind and name and goal else ("none", None)
    if act == "create" and (kind not in ctx["kinds"] or kind == "root" or not str(name or "").strip()
                            or not str(goal or "").strip()):                                       # DR-3
        _over(over, "bad_kind", "a new department needs a kind from the Library, a name and a goal")
        act = "none"
    if act == "create":                                                                            # DR-4
        for r in kids.values():
            if not r["stopped"] and (r["name"].strip().lower() == name.strip().lower()
                                     or dept_read.jaccard(r["name"] + " " + r["goal"], name + " " + goal) >= DUPLICATE_AT):
                _over(over, "duplicate", "%s already does this" % r["name"])
                act, ref = "use", r["ref"]
                break
    if act == "use":                                                                               # DR-5
        r = kids[ref]
        if r["stopped"]:
            held, why = True, "stopped"
            _over(over, "stopped", "%s is Off; Shadow does not start it" % r["name"])
        elif r["state"] == "blocked":
            held, why = True, "blocked"
            _over(over, "blocked", "%s is blocked on a question" % r["name"])
    if act == "create" and ctx.get("recent", 0) >= RATE_MAX:                                       # DR-6
        _over(over, "rate", "enough departments were made in the last ten minutes")
        act = "none"
    if act == "create" and ctx.get("birth_ask"):                                                   # DR-7
        held, why = True, "founder_rule"
        _over(over, "founder_rule", "a rule asks the owner before a new department")
    if ctx.get("fallback") == "bad_output":                                                        # DR-8
        _over(over, "bad_output", "the answer was not a valid choice")
    elif ctx.get("fallback") == "offline":
        _over(over, "offline", "no agent answered")
    return {"final_action": act, "final_ref": ref if act == "use" else None, "overrides": over[:6], "held": held,
            "held_reason": why}


# ---- decide -------------------------------------------------------------------------------------------------------
async def decide(mission=None, words=None, root_ref=None, confirmed=False, prior=None):
    """The decision for a task (or for bare words): the agent's choice and the covering over it. Nothing is written.
    `confirmed` is the owner's yes to a held create, and `prior` is the held decision it answers: its choice stands."""
    words = " ".join(str(words if words is not None else task_words(mission)).split())[:4000]
    root = root_ref or pick_root()
    rd = W.dept(root) if root else None
    rows = dept_read.rows(root) if rd else []
    cands = dept_read.candidates(root, words, 8) if rd else []
    kinds = {}
    if rd:
        import engine_runtime
        kinds = engine_runtime.library_kinds()
    ctx = {"root_ref": root if rd else None, "org": bool(rd and rd.get("org")), "children": {r["ref"]: r for r in rows},
           "kinds": kinds, "recent": recent_creates(rows), "fallback": None,
           "birth_ask": False}
    by = "agent"
    if prior and confirmed:
        choice, by = prior["choice"], prior["decided_by"]
    else:
        if rd:
            import engine_runtime
            ctx["birth_ask"] = bool(engine_runtime.birth_ask_applies(root)) and not confirmed
        text = PROMPT.render({"words": words, "candidates": cands, "kinds": kinds, "rules": owner_rules(root) if rd else []})
        reply = await _ask(text, mission) if rd else None
        choice = parse_choice(reply) if reply else None
        if choice is None:
            ctx["fallback"] = "bad_output" if reply else "offline"
            by = "code" if reply else "stub"
            choice = _fallback(words, cands, "the answer was not a valid choice" if reply else "no agent answered")
    out = cover(choice, ctx)
    mid = (mission or {}).get("id")
    return dict(choice=choice, decided_by=by, mode="link", considered=[c["ref"] for c in cands], candidates_seen=len(rows),
                root_ref=ctx["root_ref"], result_ref=None, operation_id=None,
                mission_id=mid if isinstance(mid, str) and re.fullmatch(S_MID, mid) else None, at=W.now(),
                prompt_version=PROMPT.VERSION, **out)



# ---- apply and record ---------------------------------------------------------------------------------------------
def _notify(decision, text):
    """A feed item the owner can read (information, not a question): the decision touched something that stands in its way."""
    try:
        import shadow_feed
        key = "dept:%s:%s:%s" % (decision.get("mission_id") or decision["at"], decision["final_action"],
                                 decision.get("final_ref") or decision["choice"].get("name") or "")
        item = {"item_id": "dept-%x" % (hash(key) & 0xffffffff), "producer": "shadow", "kind": "info", "title": text[:200],
                "deep_link": "sutra://shadow/mission/%s" % decision["mission_id"] if decision.get("mission_id")
                else "sutra://shadow/departments", "dedupe_key": key, "state": "new"}
        if decision.get("mission_id"):
            item["mission_id"] = decision["mission_id"]
        ref = decision.get("final_ref") or decision.get("result_ref")
        if ref:
            item["department"] = ref
        shadow_feed.emit(item)
    except Exception:  # noqa: BLE001 -- the note is a courtesy
        pass


def _name_of(ref):
    return str((W.dept(ref) or {}).get("name") or ref)


def apply(decision, words=None):
    """Do what the decision says. A create makes the department through founding.spawn (idempotent for a Root and a name); a
    use or none writes nothing; a held decision writes nothing and says so in the feed. Returns the decision, updated."""
    d = dict(decision)
    choice = d["choice"]
    if d["held"]:
        if d["held_reason"] == "founder_rule":
            _notify(d, "A new department, %s, waits for your yes" % choice.get("name"))
        else:
            _notify(d, "%s is %s. Use it anyway, or create another?" % (_name_of(d["final_ref"]),
                                                                      "Off" if d["held_reason"] == "stopped" else "blocked"))
        return d
    if d["final_action"] != "create":
        return d
    S.check("dept.decision", d)                                    # before spawn writes dept.json
    import founding
    root = d["root_ref"]
    mid = d.get("mission_id")
    context = {"id": mid or d["at"], "messages": [{"actor": "user", "text": words or choice["goal"]}]}
    try:
        made = founding.spawn(root, choice["name"], choice["kind"], choice["goal"],
                              owner=(W.dept(root) or {}).get("owner") or "the owner", goal_context=context,
                              done_items=choice.get("done_items"))
    except ValueError as exc:
        d.update(final_action="none", final_ref=None)
        d["overrides"] = (d["overrides"] + [{"rule": "duplicate", "note": str(exc)[:200] or "duplicate"}])[:6]
        return d
    if made.get("existing"):
        d.update(final_action="use", final_ref=made["ref"])
        d["overrides"] = (d["overrides"] + [{"rule": "duplicate", "note": "%s already does this" % _name_of(made["ref"])}])[:6]
        return d
    d.update(result_ref=made["ref"], final_ref=made["ref"], operation_id=str(made.get("operation_id") or "")[:80] or None)
    try:
        rec = W.dept(made["ref"])
        trimmed = dict(d, choice={k: v for k, v in choice.items() if k != "goal"})
        rec["founding"] = dict(rec.get("founding") or {}, decision=trimmed)
        W.save_dept(made["ref"], rec)
    except Exception:  # noqa: BLE001 -- the department exists; its note of how it came to be may fail
        pass
    return d


def record(decision):
    """Store the validated decision on the task (department_decision, department_ref) and as one ledger row. A decision with
    no task is validated and returned. Raises S.SchemaFault in refuse mode, before anything is written."""
    S.check("dept.decision", decision, ref=None)
    mid = decision.get("mission_id")
    if mid:
        import mission_engine
        store = mission_engine.MissionStore()
        m = store.load(mid)
        if m is not None:
            m["department_decision"] = decision
            m["department_ref"] = decision.get("result_ref") or decision.get("final_ref")
            store.save(m)
    try:
        shadow_ledger.append("actions", {"mission_id": mid, "kind": "department", "final_action": decision["final_action"],
                                         "final_ref": decision.get("final_ref"), "reason": decision["choice"]["reason"][:300],
                                         "held": decision["held"]})
    except Exception:  # noqa: BLE001 -- the ledger row is a record, never a reason to fail
        pass
    return decision


async def decide_and_apply(mission=None, words=None, root_ref=None, apply_it=True, confirmed=False):
    """The one entry: decide, apply, record. A task has one decision; asking again returns it, unless it is held for the owner
    and `confirmed` carries the yes. With `apply_it` false the decision is only previewed. Without a task, nothing is stored."""
    prior = (mission or {}).get("department_decision")
    if prior and not (confirmed and prior.get("held") and prior.get("held_reason") == "founder_rule"):
        return prior
    d = await decide(mission, words=words, root_ref=root_ref, confirmed=confirmed, prior=prior)
    if not apply_it:                                   # a preview: what would be done, validated, and nothing written
        return S.check("dept.decision", d)
    return record(apply(d, words=words))
