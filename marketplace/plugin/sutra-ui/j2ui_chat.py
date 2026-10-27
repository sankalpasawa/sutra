"""j2ui_chat.py -- the chat the J2 page reads: one arrival-ordered list of messages, each with an id that never moves.

The page asks `api/state?since=N` and gets `chat[N:]`, so a message's id is its place in the list and the list only
grows. Four sources feed it, merged by (second, place in the ledger, board, number); none of them is invented here:

    the owner's side     engine_runtime.chat_view(ref), the one reader that already merges Root's board (where every word
                         after the first arrives) with the department's own: the owner's words, the owner's stamps, and
                         what Identity told the owner. The department's own board alone would lose every follow-up.
    the function posts   the department's own board, the posts that are not for the owner: a function's act, in the owner's
                         words ('Said yes to the plan: ...'), a W-k engine's likewise
    the asks             every ask is one message from Identity that carries the question and its numbered options (the
                         page builds its buttons from that text alone), linked to the post that said it
    the validator        only the ledger's workflow.validated / registered / blocked written by Root: Root's check is an event,
                         not a post (the same action by an engine that waits, or by Adaptation's own pre-check, is not Root's)

Order. A record is stamped to the second and the runtime writes a dozen in one, so within a second the clock says nothing;
the ledger's own seq does. Every message has a place (second, anchor, board, number): the anchor is where the ledger stood
at that moment. A ledger event's anchor is its seq; a post that has an event (j2_runtime.on_post files one under its key
'/post-<n>') takes that event's seq; a post with none (Identity's word that the plan is set, which no event records) is
something that was said about what had just happened, so it takes the place just before the next post that has one, after the
events between them (the plan is set after Root's check passed it and registered it), and at the end of the ledger when no
later post has one. Root's board has no ledger of its own: a turn of its that has a twin on the department's board takes the
twin's place, any other keeps the start of its second (Root's board is read first).

The adapter speaks as no function: it never posts, and the only voice that reaches the owner is Identity's (`to_user`).
Post numbers restart at 1 on every board, so a key carries its board: ('r', n) Root's, ('b', n) the department's,
('a', ask) an ask no post says, ('x', ask) the owner's answer to an ask, ('e', seq) a ledger event.
"""
import re
import threading

import engine_runtime as R
import functions_view as F
import owner_words
import website_dept as W
import j2ui_common as C

#: how the page marks a pause (j2.py PAUSES): by the kind of the ask that waits; every other kind (publish, rule, request,
#: rung, engine, line, step, instructions...) is an approval
PAUSE = {"j2_identity": "info", "blocked": "limit", "envelope": "limit", "model": "limit", "alarm": "limit",
         "conflict": "conflict", "finding": "audit"}
APPROVAL = "approval"
STAMP_OPTS = ("approve", "refuse")         # a stamp ask offers two answers, in this order
STAMP_LABELS = ("Stamp", "Say no")
VALIDATOR = {"workflow.validated": None, "workflow.registered": True, "workflow.blocked": False}
CHECKER = "Root"                           # who writes the validator's events: j2_runtime also writes workflow.blocked for an engine that
                                           # waits (actor the engine) and for Adaptation's own check of the shaped line (actor Adaptation)
RANK = {"r": 0, "b": 1, "e": 2}            # Root's board, then the department's, then the ledger, within one place of the ledger
LATE = 10 ** 9


def pause_of(a):
    return PAUSE.get((a or {}).get("kind"), APPROVAL)


def form_of(a):
    """How an ask is answered: 'words' (Identity's question), 'options' (the ask offers its own) or 'stamp'."""
    return "words" if a.get("kind") == "j2_identity" else "options" if a.get("options") else "stamp"


# ---- the registry: ids that never move ------------------------------------------------------------------------------
class _Registry:
    """In memory, per (home, ref): the keys in order of arrival (a key never moves, a message is never dropped), the message
    last built for each, the key each ask's question took, and the options each ask showed when it was first built (the page
    keeps the message it was given, so 'Option 2' means the second button it showed, whatever the live list says now)."""

    def __init__(self):
        self.lock = threading.RLock()
        self.keys, self.index, self.last, self.ask_key, self.frozen = [], {}, {}, {}, {}


_REG = {}
_GUARD = threading.Lock()


def reset():
    with _GUARD:
        _REG.clear()


def _registry(ref):
    with _GUARD:
        return _REG.setdefault(C._key(ref), _Registry())


# ---- text ---------------------------------------------------------------------------------------------------------------
def _flat(s):
    return " ".join(str(s if s is not None else "").split())


def _line(s):
    """One line of an ask: one line whatever the words hold, and never a numbered question (the page reads a line that
    starts '1. ' as one), so words quoted in an ask cannot forge an option. A Said line stays a Said."""
    line = re.sub(r"^(\d+)\.", r"\1)", _flat(s))
    return C.Said(line) if isinstance(s, C.Said) else line


def _label(o):
    cost = _flat(owner_words.plain(o.get("cost")))
    return _flat(owner_words.plain(o.get("label"))) + (" (%s)" % cost if cost else "")


def carries_words(a):
    """The ask's text ends with the owner's own words (an outside-the-site ask: the lead, then the words)."""
    w, t = a.get("words"), a.get("text")
    return isinstance(w, str) and bool(w) and isinstance(t, str) and t.endswith(w)


def ask_text(a, shown):
    """The ask as the page parses it: '@Requester <lead>', the question, and one '   Option k: <label>' line for each option
    offered (`shown`: option dicts, in the order the owner saw them). Identity's question has none; a stamp ask has Stamp
    and Say no. When the question ends with the owner's own words they reach the page as they were said (a Said line:
    the lead and the rest of the ask, the machine's, have passed the path rule here, the words never do)."""
    question = _line(C.said(a.get("text") or "", a.get("words")))
    form = form_of(a)
    if form == "words":
        why = _line(C.shorten(owner_words.plain(a.get("why"))))
        text = "@Requester " + (why + "\n" if why else "") + question
    else:
        lead = _line(C.shorten(owner_words.plain(a.get("title")))) if form == "options" else ""
        labels = [C.shorten(_label(o)) for o in shown] if form == "options" else list(STAMP_LABELS)
        text = "@Requester " + (lead + "\n" if lead else "") + question + "".join("\n   Option %d: %s" % (i + 1, s) for i, s in enumerate(labels))
    return C.Said(text) if carries_words(a) else text


def message(at, who, text, step, **more):
    """A message without its id: {t, who, text, step} and only the optional fields the record supports, in the prototype's
    order (to_user, act, pause, next, audience, register)."""
    m = {"t": C.hhmmss(at), "who": who, "text": text if isinstance(text, C.Said) else str(text if text is not None else ""),
         "step": step if isinstance(step, int) else None}
    for k in ("to_user", "act", "pause", "next", "audience", "register"):
        if more.get(k) is not None:
            m[k] = more[k]
    return m


def _entry(key, at, rank, n, msg, opts=None, sort=None):
    """One message to place: `sort` is (second, anchor in the ledger, board rank, number), see rd.place."""
    return {"key": key, "sort": sort or (C.epoch(at), 0, rank, n if isinstance(n, int) else 0), "msg": msg, "opts": opts}


def _to_owner(p):
    return p.get("src") == "Identity" and R.OWNER in (p.get("dst") or []) and p.get("msg_type") == "request"


# ---- what one build reads -----------------------------------------------------------------------------------------------
def seq_of_event(e):
    """The ledger's own position of an event (0 for a row from before the ledger numbered its events)."""
    return e["seq"] if isinstance(e.get("seq"), int) else 0


class _Read:
    """The owner-facing turns, the raw posts by board and number, and the step each post of the department's was made in."""

    def __init__(self, c):
        self.c = c
        try:
            cv = owner_words.chat(R.chat_view(c.ref)) or {}
        except Exception as exc:  # noqa: BLE001 -- the owner's side is one read; when it fails the rest is still built, and says why
            cv = {}
            c.reasons.append("chat view: %s" % type(exc).__name__)
        self.turns = [dict(t, _key=("b" if t.get("own") or not c.root_ref else "r", t["n"])) for t in cv.get("turns") or []
                      if isinstance(t, dict) and t.get("n") is not None]
        self.raw = {("b", p.get("n")): p for p in c.posts}
        self.raw.update({("r", p.get("n")): p for p in c.root_posts})
        # the department's posts that tie to an ask: the card that names it, Identity's request relayed to Root, the owner's answer
        self.card_of, self.relayed, self.answer_of = {}, {}, {}
        for p in c.posts:
            pl = p.get("payload") or {}
            if pl.get("card"):
                self.card_of.setdefault(pl["card"], ("b", p.get("n")))
            if pl.get("via") == "Root" and _to_owner(p):
                self.relayed.setdefault(p.get("thread"), []).append(p)
            if p.get("src") == R.OWNER and pl.get("ask"):
                self.answer_of[pl["ask"]] = p
        self.twin = self._twins(c)
        self.step_of, seq_of = {}, {}
        for e in c.events:
            m = re.search(r"/post-(\d+)$", str(e.get("idempotency_key") or ""))
            if m:
                self.step_of[int(m.group(1))] = e.get("step")
                seq_of.setdefault(int(m.group(1)), seq_of_event(e))
        self.last_seq = max([seq_of_event(e) for e in c.events] or [0])
        self.anchor = self._anchors(c, seq_of)
        self.newest = self.last_seq + 0.75                     # an answer that left no post is the newest thing of its second

    def _twins(self, c):
        """Identity's words to the owner that reached Root's board are posted twice: on the department's board, marked via Root, and
        on Root's board about the department (the turn the chat shows). Records are stamped to the second, so within one second the
        department's own order is the only true one: a turn of Root's takes the place of its twin, so that what Identity says of
        the owner's stamp comes after the stamp, not before it because Root's board is read first."""
        queues = {}
        for p in c.posts:
            pl = p.get("payload") or {}
            if pl.get("via") == "Root" and p.get("src") == "Identity" and R.OWNER in (p.get("dst") or []):
                queues.setdefault((p.get("msg_type"), pl.get("word"), R._line(p)), []).append(p)
        twin = {}
        for t in self.turns:
            if t["_key"][0] != "r" or t.get("src") != "Identity":
                continue
            raw = self.raw.get(t["_key"]) or {}
            q = queues.get((raw.get("msg_type"), (raw.get("payload") or {}).get("word"), R._line(raw)))
            if q:
                twin[t["_key"]] = q.pop(0)
        return twin

    def _anchors(self, c, seq_of):
        """Post number -> where the ledger stood when the department's board took it: its event's seq for a post that has an
        event, else just before the next post that has one (after the events between them), else the end of the ledger."""
        out, nxt = {}, self.last_seq + 0.5
        for p in sorted(c.posts, key=lambda p: p.get("n") or 0, reverse=True):
            n = p.get("n")
            if n in seq_of:
                out[n], nxt = seq_of[n], seq_of[n] - 0.5
            else:
                out[n] = nxt
        return out

    def place(self, key, at, rank, n):
        """Where a message is placed among the others: by the second, then by where the ledger stood, then board, then number;
        a turn of Root's that has its twin on the department's board takes the twin's place."""
        p = self.twin.get(key)
        if p:
            return (C.epoch(p.get("at")), self.anchor.get(p.get("n"), 0), 1, p.get("n"))
        return (C.epoch(at), self.anchor.get(key[1], 0) if key[0] == "b" else 0, rank, n if isinstance(n, int) else 0)

    def place_of(self, p, rank=1):
        """The place of a post of either board (the board it is on is known by identity)."""
        key = ("b" if self.raw.get(("b", p.get("n"))) is p else "r", p.get("n"))
        return self.place(key, p.get("at"), rank, p.get("n"))

    def step(self, key, at):
        return self.step_of[key[1]] if key[0] == "b" and key[1] in self.step_of else self.c.step_at(at)


# ---- the asks -----------------------------------------------------------------------------------------------------------
def _key_of(rd, a, claimed):
    """The key an ask's question message takes: the post that says it, else a message of its own. In order: a card post on
    the department's board (Identity's question, a blocked plan: the chat leaves these posts to their card); an Identity >
    Owner request turn in the ask's thread (by its word when several share the thread); that thread's post as Root relayed
    it to the front door; else ('a', ask)."""
    thread, kind = a.get("thread"), a.get("kind")
    if a["id"] in rd.card_of:
        return rd.card_of[a["id"]]
    if not thread:
        return ("a", a["id"])
    turns = [t for t in rd.turns if t.get("thread") == thread and _to_owner(t) and t["_key"] not in claimed]
    if len(turns) > 1:
        turns = [t for t in turns if t.get("word") == kind]
    if turns:
        return turns[0]["_key"]
    own = rd.relayed.get(thread, [])
    if len(own) > 1:
        own = [p for p in own if (p.get("payload") or {}).get("word") == kind]
    for p in own:
        twin = next((t for t in rd.turns if t["_key"][0] == "r" and t["_key"] not in claimed and _to_owner(t)
                     and t.get("word") == (p.get("payload") or {}).get("word") and R._line(rd.raw[t["_key"]]) == R._line(p)), None)
        if twin:
            return twin["_key"]
    return ("a", a["id"])


def _shown(c, reg, a):
    """The options the owner was shown for an ask: the live ones the first time, the same ones every time after."""
    form = form_of(a)
    if form == "words":
        return [], None
    live = [o.get("id") for o in W.offered(c.d, a)] if form == "options" else list(STAMP_OPTS)
    with reg.lock:
        ids = reg.frozen.setdefault(a["id"], live)
    by_id = {o.get("id"): o for o in a.get("options") or []}
    return [by_id[i] for i in ids if i in by_id], ids


def _ask_entries(c, rd, reg, claimed):
    out = []
    for a in sorted((x for x in c.asks if x.get("status") != "replaced" and x.get("id")), key=lambda x: str(x.get("created"))):
        fresh = _key_of(rd, a, claimed)
        key = reg.ask_key.setdefault(a["id"], fresh)
        claimed.update((key, fresh))                 # the post that says it now is not said again, whatever message took the ask first
        shown, ids = _shown(c, reg, a)
        at = (rd.raw.get(key) or {}).get("at") or a.get("created")
        msg = message(at, "identity", ask_text(a, shown), rd.step(key, at), to_user=True, act="ASK_REQUESTER", pause=pause_of(a), next="user")
        n = key[1] if key[0] in RANK else 0
        out.append(_entry(key, at, RANK.get(key[0], 1), n, msg, ids, sort=rd.place(key, at, RANK.get(key[0], 1), n)))
        out += _answer_entries(c, rd, reg, claimed, a, ids)
    return out


def _answer_entries(c, rd, reg, claimed, a, ids):
    """The owner's answer to an ask: a choice on an options ask (its post is hidden behind the card), Identity's question
    answered in words, a stamp that left no post. A turn of the owner's own that says the same answer stands for it, and an
    answer is never said twice: when the message for it was already given (the choice is written before the post that applies
    it), that message keeps the answer and the turn is folded into it."""
    status, ch = a.get("status"), a.get("chosen")
    key, said = ("x", a["id"]), None
    posted = rd.answer_of.get(a["id"])
    if status == "chosen" and isinstance(ch, dict):
        if ch.get("id") == W.WORDS_OPTION:
            text = said = _flat(ch.get("words"))
        else:
            order = ids if ids and ch.get("id") in ids else [o.get("id") for o in a.get("options") or []]
            text = "Option %d" % (order.index(ch.get("id")) + 1) if ch.get("id") in order else _flat(ch.get("label"))
        when = ch.get("at") or a.get("decided")
    elif status == "stamped" and a.get("kind") == "j2_identity" and a.get("answered"):
        text = said = _flat(a["answered"])
        at = a.get("words_at") if isinstance(a.get("words_at"), dict) else {}
        posted = rd.raw.get(("b" if at.get("board") == c.ref else "r", at.get("n"))) or posted
        when = a.get("decided")
    elif status in ("stamped", "refused") and form_of(a) == "stamp":
        text, when = "Option 1" if status == "stamped" else "Option 2", a.get("decided")
    else:
        return []
    twins = [t["_key"] for t in rd.turns if t["_key"] not in claimed and t.get("src") == R.OWNER and
             (_flat(t.get("line")) == said if said else t.get("msg_type") in ("accept-proposal", "reject-proposal")
              and (rd.raw.get(t["_key"]) or {}).get("payload", {}).get("ask") == a["id"])]
    if twins and key not in reg.index:
        return []                                                # a turn of the owner's own says it, and is the message
    claimed.update(twins)
    at = (posted or {}).get("at") or when
    sort = rd.place_of(posted) if posted else (C.epoch(at), rd.newest, 1, LATE)
    return [_entry(key, at, 1, (posted or {}).get("n") or LATE, message(at, "user", text, c.step_at(at), next="identity"), sort=sort)]


# ---- the other sources --------------------------------------------------------------------------------------------------
def _turn_entries(rd, claimed):
    out = []
    for t in rd.turns:
        key, at = t["_key"], t.get("at")
        if key in claimed:
            continue
        line, step = _flat(t.get("line")), rd.step(t["_key"], at)
        if t.get("src") == R.OWNER:
            text = {"accept-proposal": "Option 1", "reject-proposal": "Option 2"}.get(t.get("msg_type")) or line
            msg = message(at, "user", text, step, next="identity") if text else None
        elif t.get("src") == "Identity" and R.OWNER in (t.get("dst") or []) and line:
            msg = message(at, "identity", "@Requester " + line, step, to_user=True, next="user")
        else:
            msg = None                                           # only the owner and Identity speak in the owner's chat
        if msg:
            # the words Root handed at the department's birth are the owner's own, said before anything that answers them
            out.append(_entry(key, at, -1 if t.get("birth") else RANK[key[0]], key[1], msg,
                              sort=rd.place(key, at, RANK[key[0]], key[1]) if not t.get("birth") else (C.epoch(at), -1, -1, key[1])))
    return out


def _post_entries(c, rd):
    """The department's own posts that are not for the owner, as the act their author did, in the owner's words."""
    out = []
    for p in c.posts:
        dst = p.get("dst") or []
        who = c.who(p.get("src"))
        if p.get("src") in (R.OWNER, "Root") or R.OWNER in dst or not who:
            continue
        nxt = c.dest(dst[0]) if dst else None
        said = F._said(p)
        key = ("b", p.get("n"))
        text = F._cap(F._did(p)) + (": " + F._short(said) if said else "")
        out.append(_entry(key, p.get("at"), 1, key[1], message(p.get("at"), who, text, rd.step(key, p.get("at")), next=nxt, audience=nxt),
                          sort=rd.place(key, p.get("at"), 1, key[1])))
    return out


def _event_entries(c):
    """Root's check, from the ledger only: it validated the plan, registered it, or sent it back. Only Root's own events: the
    page prints a red 'rejected' tag on a refusal, so an engine that waits for the model is not the validator refusing the plan."""
    out = []
    for e in c.events:
        if e.get("action") not in VALIDATOR or e.get("actor") != CHECKER:
            continue
        rcp = str(e.get("recipient") or "").lower()
        nxt = rcp if rcp in [f.lower() for f in C.FUNCS] else "adaptation"
        key = ("e", e.get("seq") or e.get("event_id"))
        msg = message(e.get("occurred_at"), "validator", owner_words.plain(e.get("summary")), e.get("step"), next=nxt,
                      register=VALIDATOR[e["action"]])
        out.append(_entry(key, e.get("occurred_at"), RANK["e"], e.get("seq"), msg,
                          sort=(C.epoch(e.get("occurred_at")), seq_of_event(e), RANK["e"], seq_of_event(e))))
    return out


# ---- the list ------------------------------------------------------------------------------------------------------------
def build(c):
    """(messages, msg_of, ask_msg, ask_opts) for the department: the page's chat list; `msg_of` {key: id}; `ask_msg` {ask id:
    id of its question message}; `ask_opts` {id of a question message: the option ids as the owner was shown them}."""
    reg = _registry(c.ref)
    with reg.lock:
        rd, claimed = _Read(c), set()
        asks = _ask_entries(c, rd, reg, claimed)
        entries = _turn_entries(rd, claimed) + _post_entries(c, rd) + _event_entries(c) + asks
        for e in sorted((e for e in entries if e["key"] not in reg.index), key=lambda e: (e["sort"], repr(e["key"]))):
            reg.index[e["key"]] = len(reg.keys)
            reg.keys.append(e["key"])
        for e in entries:
            reg.last[e["key"]] = e["msg"]
        messages = [dict(id=i + 1, **reg.last[k]) for i, k in enumerate(reg.keys)]
        msg_of = {k: i + 1 for i, k in enumerate(reg.keys)}
        ask_msg = {aid: msg_of[k] for aid, k in reg.ask_key.items() if k in msg_of}
        ask_opts = {ask_msg[aid]: list(ids) for aid, ids in reg.frozen.items() if aid in ask_msg}
    return messages, msg_of, ask_msg, ask_opts
