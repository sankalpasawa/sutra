"""Precedence for standing instructions (PLAN-100 S88).

Order (highest wins): floors > session > project > d_ledger > taste >
history. Floors are not instructions at all -- they live in code
(shadow_egress.floor_check) and NOTHING in this ranking can reach above
them; replay_context() states that in the header it builds, and the test
pins that a floor survives any confirmed instruction that contradicts it.
Unconfirmed rows are INERT: they never enter the replay context.
"""
_RANK = {"floor": 0, "session": 1, "project": 2, "d_ledger": 3,
         "taste": 4, "history": 5}


def rank_key(row):
    return (_RANK.get(row.get("precedence"), 9), row.get("ts") or "")


def row_scope(row):
    """Legacy rows carry no scope: they are GLOBAL (grandfather rule).
    Scope is orthogonal to precedence and never enters _RANK."""
    return (row or {}).get("scope") or "global"


def replay_context(rows, scope="global", scope_id=None):
    """Confirmed rows only, precedence-ordered, floors restated first.
    scope="global" (default) returns the rules that apply everywhere;
    scope="chat" with a scope_id returns ONLY that chat's rules, so a
    per-chat rule can never color an unrelated reply."""
    confirmed = [r for r in rows or []
                 if r.get("confirmed") and not r.get("revoked_at")
                 and row_scope(r) == scope
                 and (scope != "chat" or r.get("scope_id") == scope_id)]
    confirmed.sort(key=rank_key)
    lines = ["FLOORS (not overridable by anything below): destructive git "
             "ops, external client repos, irreversible external sends -- "
             "confirm-first, always."]
    for r in confirmed:
        lines.append("[%s] %s" % (r.get("precedence"), r.get("text", "")))
    return "\n".join(lines)
