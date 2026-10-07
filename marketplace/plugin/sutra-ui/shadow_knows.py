"""What Shadow knows -- the memory and personality Shadow LEARNS (founder,
2026-10-07).

THE FEATURE IN ONE LINE. The system fills these in from working with the
founder, Shadow re-uses them in every later chat, and the founder can edit
them if they want to -- ideally they never have to.

TWO SECTIONS, TWO QUESTIONS (the same split the founder's own two boxes use):

  memory       WHAT IS TRUE. Who the founder is, the people and projects they
               name, current focus, output preferences, vocabulary, tools.
  personality  HOW TO ACT. Autonomy, how hard to verify, when to interrupt,
               how long to persist, how to communicate, what to prioritise.

WHERE ROWS COME FROM, and the one rule that decides whether a row binds:

  said      the founder stated it outright in a Shadow chat ("I'm the CEO",
            "always run the suite first") -> ACTIVE at once.
  asked     learned from the founder's answer to something Shadow ASKED them.
            Active when the founder said it as a standing rule, otherwise a
            pending suggestion. The decider decides which (see
            mission_engine.validate_remember).
  inferred  Shadow's reading of a pattern -> always PENDING, one tap to keep.
  typed     the founder added or edited it on "What Shadow knows" -> ACTIVE.

  What the founder said in so many words binds; what Shadow guessed waits for
  a Keep. A wrong fact costs a wrong sentence, a wrong behaviour costs an
  action nobody asked for, and a guess must not be able to do either alone.

WHAT NEVER GOES IN. One task's details (the MotoGP leak, shadow_session
docstring), one-off instructions, secrets, and stale status. The secret check
is mechanical (_SECRET_RE); the rest is the deciders' instruction plus the
pending gate on anything inferred.

STORAGE. One append-only ledger, `knows`, under the shadow home, folded to
the last row per id (shadow_ledger.read_latest) -- so an edit, a keep and a
forget are each one more row and the history is never rewritten. Same home
resolver, same test guard, same provenance stamps as every other Shadow store.

NOT THE FOUNDER'S OWN TWO BOXES. mission_engine.behaves()/memory() are the
founder's free text and stay exactly as they were; they rank first. This is
the learned half that sits beneath each of them.
"""
import re
import time
import uuid

import shadow_ledger

SECTIONS = ("memory", "personality")

#: THE GROUPS (founder, 2026-10-07: "fixed category of things ... we don't
#: want to give loads of stuff for the user to see"). Fifteen categories
#: became three memory groups and one personality list, after the research
#: pass: Claude files memory under five topics, Mem0 advises three to five
#: because more dilute the sorting, and ChatGPT shows personality as a few
#: switches rather than a list. The switches are SWITCHES below; what is
#: left of personality is "Other rules", for anything no switch covers.
GROUPS = {
    "memory": ("you", "work", "preferences"),
    "personality": ("rules",),
}
GROUP_LABELS = {"you": "About you", "work": "Your work",
                "preferences": "Your preferences", "rules": "Other rules"}

#: The fifteen names rows were filed under before the groups, and the names a
#: decider or a caller may still use. Mapped on READ as well as on write, so
#: lines already on disk land in the right group without being rewritten.
_LEGACY = {
    "identity": "you", "people": "you",
    "projects": "work", "focus": "work", "tools": "work",
    "vocabulary": "preferences",
}

#: Kept for callers that list what a section accepts.
CATEGORIES = GROUPS


def group_of(section, category):
    """The group a row belongs to. Never raises: an unknown name files under
    the section's first group rather than being refused."""
    if section == "personality":
        return "rules"
    category = _LEGACY.get(category, category)
    return category if category in GROUPS["memory"] else "you"

SOURCES = ("said", "asked", "inferred", "typed")
STATUSES = ("active", "pending", "forgotten")

#: Sources that bind at once. Everything else waits for a Keep.
_BINDING_SOURCES = ("said", "typed")

#: One line is one thing remembered, not a paragraph.
TEXT_MAX = 200
EVIDENCE_MAX = 300

#: The ceiling PER GROUP. FULL IS A QUESTION, NEVER A SILENT EVICTION: the
#: founder's oldest facts are not traded for the newest without them knowing,
#: so add() refuses and Shadow asks what to merge or drop. Ten (2026-10-07,
#: was 50 per section): "store fewer, surface them reliably" -- and a group
#: the founder can read at a glance.
MAX_ACTIVE = 10

#: Suggestions nobody has looked at are not allowed to pile up without end.
#: Past this, a new suggestion is refused (it was only a suggestion).
MAX_PENDING = 20

#: Credentials never become memory. Deliberately broad: a false positive costs
#: one line the founder can type differently; a false negative puts a key
#: into every boot context and every worker brief.
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abpr]-[A-Za-z0-9\-]{10,}|\b[A-Fa-f0-9]{32,}\b"
    r"|\b(?:password|passwd|api[ _-]?key|secret|token)\b\s*(?:is\s*)?[:=]\s*\S+)",
    re.I)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Refused(ValueError):
    """add/keep/edit said no, in a sentence Shadow can repeat to the founder."""


def _clean(text):
    return " ".join(str(text or "").split())[:TEXT_MAX]


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def _expires(value):
    value = str(value or "").strip()
    return value if _DATE_RE.match(value) else None


def is_expired(row, today=None):
    """A dated row whose date has passed. It stops binding, and the founder is
    asked whether to drop it -- it is never dropped for them."""
    exp = (row or {}).get("expires")
    return bool(exp) and exp < (today or _today())


def rows():
    """Every row, folded to its latest state. NEVER RAISES: this rides every
    Shadow boot, and a broken ledger must cost the learned lines, never the
    boot."""
    try:
        out = [dict(r) for r in shadow_ledger.read_latest("knows")
               if r.get("section") in SECTIONS]
    except Exception:                       # noqa: BLE001 -- see docstring
        return []
    for r in out:                 # rows filed before the groups land in one
        r["category"] = group_of(r["section"], r.get("category"))
    return out


def _find(rid):
    for r in rows():
        if r.get("id") == rid:
            return r
    return None


def active(section=None, group=None):
    """Rows that bind: active and not past their date."""
    today = _today()
    return [r for r in rows()
            if r.get("status") == "active" and not is_expired(r, today)
            and (section is None or r.get("section") == section)
            and (group is None or r.get("category") == group)]


def _full(group):
    return Refused("%s is full (%d lines). Ask the founder which line to "
                   "merge or forget first." % (GROUP_LABELS[group], MAX_ACTIVE))


def pending(section=None):
    return [r for r in rows()
            if r.get("status") == "pending"
            and (section is None or r.get("section") == section)]


def _same(a, b):
    return a.strip().lower() == b.strip().lower()


def _check_text(text):
    if not text:
        raise Refused("nothing to remember")
    if _SECRET_RE.search(text):
        raise Refused("that looks like a credential, and credentials are "
                      "never remembered")


def _save(row):
    return shadow_ledger.append("knows", row)


def add(section, text, source, category=None, evidence=None,
        mission_id=None, expires=None, binding=None):
    """Remember one line. Returns the stored row.

    `binding` lets a caller that KNOWS the founder stated it as a standing rule
    (the decider, reading the founder's answer) make an `asked` row active.
    It can never make an `inferred` row active: a guess waits for a Keep.

    IDEMPOTENT. The same line again (case and spacing ignored) returns the row
    already there; a binding repeat of a pending suggestion activates it,
    because the founder has now said it outright.
    """
    if section not in SECTIONS:
        raise Refused("section must be memory|personality")
    if source not in SOURCES:
        raise Refused("source must be one of %s" % "|".join(SOURCES))
    text = _clean(text)
    _check_text(text)
    binds = source in _BINDING_SOURCES or (source == "asked" and bool(binding))
    status = "active" if binds else "pending"
    category = group_of(section, category)

    for r in rows():
        if r.get("section") != section:
            continue
        if not _same(r.get("text") or "", text):
            continue
        if r.get("status") == "forgotten":
            # A LINE THE FOUNDER DROPPED STAYS DROPPED. The decider sees the
            # same answer on every later turn of the task, so without this a
            # dismissed suggestion would be proposed again the next turn.
            # Only the founder saying it again (said/typed) brings it back.
            if source in _BINDING_SOURCES:
                continue
            raise Refused("the founder already dropped that")
        if r.get("status") == "pending" and status == "active":
            return _update(r, status="active", source=source)
        return r

    if status == "active" and len(active(section, category)) >= MAX_ACTIVE:
        raise _full(category)
    if status == "pending" and len(pending()) >= MAX_PENDING:
        raise Refused("too many suggestions are already waiting")

    row = {"id": "know-%s" % uuid.uuid4().hex[:12],
           "section": section, "category": category, "text": text,
           "source": source, "status": status,
           "evidence": _clean(evidence)[:EVIDENCE_MAX] or None,
           "mission_id": mission_id or None,
           "expires": _expires(expires)}
    return _save(row)


def _update(row, **changes):
    new = {k: v for k, v in dict(row).items()
           if k not in ("ts", "pid", "build")}
    new.update(changes)
    return _save(new)


def _require(rid):
    row = _find(rid)
    if row is None or row.get("status") == "forgotten":
        raise Refused("nothing to change: that line is not remembered")
    return row


def keep(rid):
    """The founder keeps a suggestion. It binds from the next boot."""
    row = _require(rid)
    if row.get("status") == "active":
        return row
    if len(active(row["section"], row["category"])) >= MAX_ACTIVE:
        raise _full(row["category"])
    return _update(row, status="active")


def forget(rid):
    """Drop a suggestion or forget a remembered line. Kept on the record as
    `forgotten` (append-only), never applied again."""
    return _update(_require(rid), status="forgotten")


def edit(rid, text, category=None):
    """The founder rewrites a line. Their words now, so it binds as typed."""
    row = _require(rid)
    text = _clean(text)
    _check_text(text)
    changes = {"text": text, "source": "typed", "status": "active",
               "expires": row.get("expires")}
    if category:
        changes["category"] = group_of(row["section"], category)
    return _update(row, **changes)


def forget_text(section, text):
    """Forget by the words, for "forget that I said X" in a chat. Returns the
    forgotten row, or None when nothing matched."""
    text = _clean(text)
    for r in rows():
        if r.get("section") == section and r.get("status") != "forgotten" \
                and _same(r.get("text") or "", text):
            return forget(r["id"])
    return None


def listing():
    """What "What Shadow knows" draws: every live row, newest first, per
    section, with `expired` worked out so the page can ask about it."""
    today = _today()
    out = {s: [] for s in SECTIONS}
    for r in rows():
        if r.get("status") == "forgotten":
            continue
        view = {k: r.get(k) for k in ("id", "section", "category", "text",
                                      "source", "status", "evidence",
                                      "mission_id", "expires", "ts")}
        view["expired"] = is_expired(r, today)
        out[r["section"]].append(view)
    for s in SECTIONS:
        out[s].reverse()
    return {**out, "pending": sum(1 for s in SECTIONS for r in out[s]
                                  if r["status"] == "pending"),
            "max_active": MAX_ACTIVE,
            "groups": {s: [{"id": g, "label": GROUP_LABELS[g]}
                           for g in GROUPS[s]] for s in SECTIONS},
            "switches": switch_listing()}


def lines(section):
    """The binding lines of one section, oldest first, as prompt lines.
    NEVER RAISES (rows() does not)."""
    return ["- [%s] %s" % (GROUP_LABELS.get(r.get("category"), "Other"),
                           r.get("text"))
            for r in active(section)]


# ------------------------------------------------------------ switches ----
#: PERSONALITY AS SWITCHES (founder, 2026-10-07; ChatGPT's "base style" +
#: characteristics is the model). Four, each with a default that is what
#: Shadow already does, so an unset switch changes nothing. Two are WIRED to
#: an existing engine setting -- a switch, not a suggestion -- and every one
#: also reaches Shadow's context as one sentence (switch_text).
#:   name: (label, default, [(value, label, sentence for Shadow)])
SWITCHES = {
    "acting": ("Acting on its own", "balanced", [
        ("ask_first", "Ask first",
         "Ask before the first instruction of each task and before any "
         "consequential choice."),
        ("balanced", "Balanced",
         "Decide routine things yourself; ask only on consequential choices."),
        ("just_do_it", "Just do it",
         "Decide everything you reasonably can yourself; ask only when a "
         "floor or a fact only the founder holds requires it.")]),
    "checkins": ("Checking in", "only_stuck", [
        ("only_stuck", "Only when stuck",
         "Speak up only when you need them or the task is finished; no "
         "progress updates."),
        ("milestones", "At milestones",
         "Give a one-line update when a meaningful step is done."),
        ("often", "Often",
         "Keep them posted: a short update on every turn that moved.")]),
    "done": ("Before \"done\"", "key", [
        ("trust", "Trust the worker",
         "Accept the worker's report when the checks pass; do not re-verify "
         "beyond them."),
        ("key", "Check the key things",
         "Verify the checks that matter with real evidence; do not gold-plate."),
        ("prove", "Prove everything",
         "Back every check with a probe or evidence you looked at; never "
         "accept a claim alone.")]),
    "replies": ("Replies", "short", [
        ("short", "Short", "Reply in one or two lines, outcome first."),
        ("normal", "Normal", "Reply in a short paragraph when it helps."),
        ("detailed", "Detailed",
         "Explain what you did and why, with the key details.")]),
}

#: The wired half of "Checking in": value -> nudges per hour (the overlay's
#: unasked interruptions, shadow_presence). "Acting on its own" is wired to
#: mission_engine.confirm_top_tier in set_switch.
_NUDGES = {"only_stuck": 0, "milestones": 3, "often": 6}


def _switch_path():
    import os
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "switches.json")


def switches():
    """{name: value} for the switches the founder has SET. NEVER RAISES."""
    try:
        import json_store
        raw = json_store.read_json(_switch_path(), {}) or {}
    except Exception:                       # noqa: BLE001 -- unset, never fatal
        return {}
    return {k: v for k, v in raw.items()
            if k in SWITCHES and v in [o[0] for o in SWITCHES[k][2]]}


def set_switch(name, value):
    """Set one switch, apply its engine setting, return the stored value."""
    if name not in SWITCHES:
        raise Refused("no such switch: %s" % name)
    if value not in [o[0] for o in SWITCHES[name][2]]:
        raise Refused("%s cannot be %r" % (SWITCHES[name][0], value))
    import json_store
    cur = switches()
    cur[name] = value
    json_store.write_json(_switch_path(), cur)
    if name == "acting":
        import mission_engine
        mission_engine.set_confirm_top_tier(value == "ask_first")
    elif name == "checkins":
        import shadow_presence
        shadow_presence.set_nudges_per_hour(_NUDGES[value])
    return value


def switch_listing():
    """What the page draws: every switch, its options, and where it stands."""
    have = switches()
    out = []
    for name, (label, default, opts) in SWITCHES.items():
        out.append({"name": name, "label": label, "default": default,
                    "value": have.get(name, default), "set": name in have,
                    "options": [{"value": v, "label": l} for v, l, _ in opts]})
    return out


def switch_text():
    """One sentence per switch the founder SET, for Shadow's context; "" when
    none is set, so an unconfigured install's context is unchanged."""
    have = switches()
    out = []
    for name, (label, _default, opts) in SWITCHES.items():
        for v, l, sentence in opts:
            if have.get(name) == v:
                out.append("- %s: %s. %s" % (label, l, sentence))
    return "\n".join(out)
