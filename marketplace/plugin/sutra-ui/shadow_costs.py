"""What Shadow's work costs, and the founder's monthly budget for it
(founder, 2026-10-08, from Paperclip: "dollar cost per task and a monthly
budget: a warning at 80%, an automatic pause at 100%").

WHERE THE NUMBER COMES FROM. Every Claude turn ends with a `result` event
carrying `total_cost_usd`, and session_runtime already passes it on in its
`done` frame. Measured 2026-10-08 on one persistent stream-json process: the
figure is CUMULATIVE for the process (0.0027 -> 0.0051 -> 0.0065 over three
turns), so a turn's cost is the new total minus the last one this process
reported. A resumed chat is a new process and starts from zero again -- a
total LOWER than the last one is that, and counts in full.

WHAT IS COUNTED. The worker (shadow_runner's observer), the task's own Shadow
chat (shadow_task_chat) and the Now chat (shadow_session). A turn that ends
in an error sends no `done` frame and is not counted -- the figure is a floor,
and the screen says "about".

WHY ITS OWN FILE, not a ledger kind. Shadow's sessions can append any ledger
kind through sutra_mcp; a spend figure Shadow could write to is not a budget.
costs.jsonl sits in the shadow home and only this module writes it.

THE BUDGET lives in the task-limits store beside running_at_once. None or 0
means no budget, which is the default: nothing is stopped unless the founder
sets one.
"""
import json
import os
import threading
import time

import shadow_ledger

#: The warning line, as a fraction of the budget.
WARN_AT = 0.8

_LOCK = threading.Lock()
#: (session id, process key) -> the last cumulative total that process
#: reported. A process key is id(runtime): one chat can be several processes
#: over its life (a resume), and each counts from zero.
_LAST = {}
#: mission ids by worker session, so the observer can name the task.
_CACHE = {"path": None, "size": -1, "rows": []}


def _path():
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "costs.jsonl")


def _month(ts=None):
    return time.strftime("%Y-%m", time.gmtime(ts))


def record(session_id, mission_id, total_usd, kind, proc_key=None):
    """Count one turn from the process's cumulative total. Returns the delta
    recorded (0.0 when nothing new). NEVER RAISES: a cost that cannot be
    written costs the figure, never the turn."""
    try:
        total = float(total_usd)
    except (TypeError, ValueError):
        return 0.0
    if total <= 0:
        return 0.0
    key = (session_id or "", proc_key)
    with _LOCK:
        last = _LAST.get(key, 0.0)
        delta = total - last if total >= last else total
        _LAST[key] = total
    if delta <= 0:
        return 0.0
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "month": _month(), "mission_id": mission_id or None,
           "session_id": session_id or None, "kind": kind,
           "usd": round(delta, 6)}
    try:
        with _LOCK:
            with open(_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
    except Exception:                    # noqa: BLE001 -- see docstring
        return 0.0
    return delta


def _rows():
    """Every row, re-read only when the file grew."""
    p = _path()
    try:
        size = os.path.getsize(p)
    except OSError:
        return []
    if _CACHE["path"] == p and _CACHE["size"] == size:
        return _CACHE["rows"]
    rows = []
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    rows.append(r)
    except OSError:
        return []
    _CACHE.update(path=p, size=size, rows=rows)
    return rows


def by_mission():
    """{mission id: usd} across all time."""
    out = {}
    for r in _rows():
        mid = r.get("mission_id")
        if mid:
            out[mid] = out.get(mid, 0.0) + float(r.get("usd") or 0)
    return out


def month_spent(month=None):
    month = month or _month()
    return sum(float(r.get("usd") or 0) for r in _rows()
               if r.get("month") == month)


# ------------------------------------------------------------- budget ---
def budget():
    """The monthly budget in dollars, or None when there is none."""
    try:
        import mission_engine
        raw = mission_engine._read_limits().get("monthly_budget_usd")
        v = float(raw)
    except Exception:                    # noqa: BLE001 -- no budget
        return None
    return v if v > 0 else None


def set_budget(value):
    """Store the budget; 0 or empty clears it. Returns what was stored."""
    if value in (None, ""):
        v = 0.0
    else:
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError("the budget is an amount in dollars")
        if v < 0:
            raise ValueError("the budget can't be negative")
        if v > 100000:
            raise ValueError("the budget can be up to $100,000")
    import json_store
    import mission_engine
    cur = mission_engine._read_limits()
    cur["monthly_budget_usd"] = round(v, 2) or None
    json_store.write_json(mission_engine.limits_path(), cur)
    return budget()


def status():
    """What the screen shows: spent this month, the budget, and where that
    leaves it -- none | ok | warn | over."""
    spent = month_spent()
    b = budget()
    if b is None:
        level = "none"
    elif spent >= b:
        level = "over"
    elif spent >= b * WARN_AT:
        level = "warn"
    else:
        level = "ok"
    return {"month": _month(), "spent_usd": round(spent, 4),
            "budget_usd": b, "level": level,
            "pct": (round(100 * spent / b) if b else None)}


def spent_up():
    """Has this month's budget been used up? Never raises."""
    try:
        return status()["level"] == "over"
    except Exception:                    # noqa: BLE001
        return False


def spent_up_reason():
    s = status()
    return ("This month's Shadow spending limit ($%.2f) is used up. Raise "
            "it in Shadow's settings, then try again." % (s["budget_usd"] or 0))


# -------------------------------------------------------------- hooks ---
def _mission_for_worker(session_id):
    """(found, mission id) for a worker session: the task whose worker it is.
    A chat Shadow did not make (target_mode "existing", the founder's own) is
    found but not counted -- that spend is the founder's chat, not Shadow's."""
    if not session_id:
        return False, None
    try:
        import mission_engine
        for m in mission_engine.MissionStore().list():
            if m.get("target_session") == session_id:
                return True, (m["id"] if m.get("target_mode") == "new"
                              else False)
    except Exception:                    # noqa: BLE001
        pass
    return False, None


def hook(rt, kind, mission_id=None):
    """Set on a Shadow runtime: session_runtime calls it with each result's
    cumulative total. `kind` is worker | shadow | now. A worker names its
    task by its session; the others are told their task up front."""
    def on_cost(total_usd, session_id):
        mid = mission_id
        if kind == "worker":
            found, mid = _mission_for_worker(session_id)
            if found and mid is False:
                return
        record(session_id, mid, total_usd, kind, proc_key=id(rt))
    return on_cost


def attach(rt, kind, mission_id=None):
    """hook() set on rt, quietly: a test fake without the attribute, or one
    that refuses it, simply goes uncounted."""
    try:
        rt.on_cost = hook(rt, kind, mission_id)
    except Exception:                    # noqa: BLE001
        pass
    return rt
