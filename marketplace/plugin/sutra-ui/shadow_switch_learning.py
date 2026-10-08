"""Switch suggestions from what the founder does (founder, 2026-10-08:
"build rule 2").

THE RULE. A personality switch changes three ways: the founder sets it on
"What Shadow knows", the founder says it in a chat (shadow_remember sets it at
once), or -- this module -- Shadow notices a PATTERN in what the founder does
and SUGGESTS a change. A pattern never changes a switch by itself: the founder
answers Yes or No on a card.

WHAT COUNTS AS A PATTERN. The same signal in THREE DIFFERENT tasks or chats
within the last 30 days, all after the founder last answered a suggestion for
that switch. One odd task can never move a default.

THE SIGNALS, every one already recorded somewhere; nothing new is tracked:

  acting  -> just_do_it  an approval of a held instruction, sent unchanged
                         (ledger `actions`, kind "approval")
  acting  -> ask_first   a held instruction withdrawn or changed
                         (mission `withdrawn`), or a running task stopped by
                         the founder's Stop (ledger `missions`, "founder stop")
  done    -> prove       a FINISHED task the founder reopened (mission
                         `reopened`, from "done")
  replies -> short       the founder saying "too long", "shorter", "tl;dr" ...
  replies -> normal      the founder asking "explain", "more detail" ...
  checkins -> milestones the founder asking "what's happening", "any update"

  (No signal moves checkins toward "only when stuck": dismissing a nudge is
  not recorded anywhere, so that direction stays the founder's own click.)

THE GUARDRAILS.
  * Suggest only; Yes sets the switch through shadow_knows.set_switch.
  * One open suggestion per switch; after Yes the switch rests 7 days, after
    No it rests 30 -- and only signals AFTER the answer count again.
  * Both directions are suggestions, toward Ask first as much as away from it.
  * A suggestion for the value the switch already has is never shown.

NEVER RAISES on the read path: it rides the settings and home reads.
"""
import calendar
import os
import re
import time

import shadow_ledger

WINDOW_DAYS = 30
THRESHOLD = 3
REST_AFTER_YES_DAYS = 7
REST_AFTER_NO_DAYS = 30

_SHORT_RE = re.compile(
    r"\b(too long|shorter|be brief|more concise|tl;?dr|keep it short|"
    r"less text|wall of text|too wordy)\b", re.I)
_NORMAL_RE = re.compile(
    r"\b(explain|more detail|in detail|elaborate|tell me more|why did you)\b",
    re.I)
_STATUS_RE = re.compile(
    r"\b(what'?s happening|what is happening|any update|status\?|"
    r"how'?s it going|where are we|what'?s the status)\b", re.I)

#: (switch, target) -> the sentence the card gives as the reason.
WHY = {
    ("acting", "just_do_it"):
        "You approved %d held instructions without changing them.",
    ("acting", "ask_first"):
        "You withdrew, changed or stopped my work %d times.",
    ("done", "prove"):
        "You reopened %d tasks I had marked done.",
    ("replies", "short"):
        "You asked for shorter replies %d times.",
    ("replies", "normal"):
        "You asked me to explain more %d times.",
    ("checkins", "milestones"):
        "You asked me for an update %d times.",
}


def _ts(value):
    """ISO 'YYYY-MM-DDTHH:MM:SSZ' -> epoch seconds, or None."""
    try:
        return calendar.timegm(time.strptime(str(value)[:19],
                                             "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _answers_path():
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "switch_suggestions.json")


def answers():
    """{switch: {"answer", "at", "until", "to"}}. NEVER RAISES."""
    try:
        import json_store
        got = json_store.read_json(_answers_path(), {}) or {}
        return got if isinstance(got, dict) else {}
    except Exception:                        # noqa: BLE001 -- none, not fatal
        return {}


def _signals(now):
    """[(switch, target, unit, epoch)] -- every signal in the window. A
    `unit` is the task or chat it happened in; THRESHOLD counts units."""
    since = now - WINDOW_DAYS * 86400
    out = []

    def add(sw, target, unit, when):
        t = _ts(when)
        if unit and t is not None and t >= since:
            out.append((sw, target, str(unit), t))

    def text_signals(text, unit, when):
        text = str(text or "")
        if _SHORT_RE.search(text):
            add("replies", "short", unit, when)
        elif _NORMAL_RE.search(text):
            add("replies", "normal", unit, when)
        if _STATUS_RE.search(text):
            add("checkins", "milestones", unit, when)

    try:
        for r in shadow_ledger.read("actions", 2000):
            if r.get("kind") == "approval":
                add("acting", "just_do_it", r.get("mission_id"), r.get("ts"))
    except Exception:                        # noqa: BLE001
        pass
    try:
        for r in shadow_ledger.read("missions", 2000):
            if r.get("state") == "stopped" \
                    and str(r.get("note") or "").startswith("founder stop"):
                add("acting", "ask_first", r.get("mission_id"), r.get("ts"))
    except Exception:                        # noqa: BLE001
        pass
    try:
        import mission_engine
        for m in mission_engine.MissionStore().list():
            mid = m.get("id")
            for w in m.get("withdrawn") or []:
                if isinstance(w, dict) and w.get("why") in ("withdraw",
                                                            "change"):
                    add("acting", "ask_first", mid, w.get("at"))
            for leg in m.get("reopened") or []:
                if isinstance(leg, dict) and leg.get("from") == "done":
                    add("done", "prove", mid, leg.get("at"))
            for s in m.get("founder_says") or []:
                if isinstance(s, dict) and s.get("via") != "reopen":
                    text_signals(s.get("text"), mid, s.get("at"))
    except Exception:                        # noqa: BLE001
        pass
    try:
        import shadow_conversations
        for c in shadow_conversations.list_all():
            for msg in c.get("messages") or []:
                if isinstance(msg, dict) and msg.get("who") == "founder":
                    text_signals(msg.get("text"), c.get("id"), msg.get("ts"))
    except Exception:                        # noqa: BLE001
        pass
    return out


def suggestions(now=None):
    """The open suggestions, at most one per switch. NEVER RAISES."""
    try:
        import shadow_knows
        now = now or time.time()
        current = shadow_knows.effective()
        answered = answers()
        units = {}
        for sw, target, unit, t in _signals(now):
            a = answered.get(sw) or {}
            if (_ts(a.get("until")) or 0) > now:
                continue                     # resting after an answer
            if t <= (_ts(a.get("at")) or 0):
                continue                     # counted before the answer
            units.setdefault((sw, target), set()).add(unit)
        out = []
        for (sw, target), seen in sorted(units.items(),
                                         key=lambda kv: -len(kv[1])):
            if len(seen) < THRESHOLD or current.get(sw) == target:
                continue
            if any(s["name"] == sw for s in out):
                continue                     # one open suggestion per switch
            label, _default, opts = shadow_knows.SWITCHES[sw]
            labels = {v: l for v, l, _ in opts}
            out.append({"name": sw, "label": label,
                        "from": current.get(sw),
                        "from_label": labels.get(current.get(sw)),
                        "to": target, "to_label": labels[target],
                        "why": WHY[(sw, target)] % len(seen),
                        "count": len(seen)})
        return out
    except Exception:                        # noqa: BLE001 -- see docstring
        return []


def answer(name, reply, now=None):
    """The founder's Yes or No. Yes sets the switch; either rests it."""
    import json_store
    import shadow_knows
    now = now or time.time()
    open_ = {s["name"]: s for s in suggestions(now)}
    if name not in open_:
        raise shadow_knows.Refused("there is no open suggestion for %s"
                                   % name)
    if reply not in ("yes", "no"):
        raise shadow_knows.Refused("answer yes or no")
    target = open_[name]["to"]
    if reply == "yes":
        shadow_knows.set_switch(name, target)
    rest = REST_AFTER_YES_DAYS if reply == "yes" else REST_AFTER_NO_DAYS
    cur = answers()
    cur[name] = {"answer": reply, "to": target, "at": _iso(now),
                 "until": _iso(now + rest * 86400)}
    json_store.write_json(_answers_path(), cur)
    return cur[name]
