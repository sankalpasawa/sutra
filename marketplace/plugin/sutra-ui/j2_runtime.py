"""J2: the department's life, on its record.

J1 ends with the department made. J2 is the five functions working toward the identity's goal (the department page,
section J2): Identity finds the identity good enough, Adaptation proposes the workflows, Priority grants, refuses or
counters, Identity closes a conflict, Root checks and registers, Coordination orders and the workflows run, Audit reads
the result, and the loop goes on until done-when holds.

The functions do that work on the department's one board, in engine_runtime. This module is the lifecycle's own record
and its covering: one cycle per department, the step it stands on, and an append-only ledger of what happened. The
ledger is written where the thing happens (a post on the board, a run row, a filed version), by the hooks below, so it
cannot say something the department did not do.
"""
import copy
import hashlib
import json
import os
import uuid

import engine_runtime as R
import layer_schema as S
import record
import website_dept as W


SCHEMA_VERSION = "j2.event.v1"
ACTORS = {"Root", "Identity", "Adaptation", "Priority", "Coordination", "Audit", "User"}
PRIVATE_KEYS = {"private_reasoning", "reasoning", "chain_of_thought", "scratchpad", "secret", "token", "password"}
JOURNEY = {1: "J2.a", 2: "J2.b", 3: "J2.c", 4: "J2.d", 5: "J2.e", 6: "J2.f", 7: "J2.g", 8: "J2.h"}
REPAIRS = 2                     # how often Root's check may send a workflow back before Identity tells the owner (J2.4)
LEDGER, INDEX, OLD_LEDGER = "j2-events.jsonl", "j2-index.json", "j2-events.json"
MARK = 256                      # the index keeps where every 256th event starts, so a page is read from near its cursor


class J2Error(ValueError):
    """A stable J2 boundary error."""


def enabled():
    """On unless switched off: a department born while it is off runs as it did before J2, and is never held."""
    return os.environ.get("J2_FLOW_V1", "1").strip().lower() not in ("0", "false", "off")


def _path(ref, name):
    return W.ddir(ref) / name


# ---- the ledger: a journal, one event a line, and its index beside it (M0.2) ---------------------------------------
# The ledger was one JSON document, read whole and written whole on every event, and the screen counted it by reading
# it whole every 2.5 s. Now an event is one line appended under the department's lock, and j2-index.json carries what
# an append needs to know without reading the journal: the idempotency keys seen (as digests), each cycle's last
# event, the count, how many bytes it has read, and where every MARK-th event starts. A row's seq is its place in the
# journal, so the index's marks are a row's address.
_IDX = {}                       # each journal's index, as this process last read it: {path: (inode, index)}


def _digest(key):
    return hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:16]


def _convert(ref):
    """A ledger written before M0.2 is one JSON document. It becomes the journal once, row for row and in its order,
    and the document is kept beside it as j2-events.json.bak."""
    old = _path(ref, OLD_LEDGER)
    if not old.exists():
        return
    with W._lock(ref):
        if not old.exists():
            return
        new = _path(ref, LEDGER)
        if not new.exists():
            tmp = _path(ref, LEDGER + ".tmp")
            if tmp.exists():
                tmp.unlink()
            for row in W._read(old, []):
                if isinstance(row, dict):
                    record.append(tmp, row)
            tmp.touch()
            os.replace(tmp, new)                            # whole or not at all: a conversion cut short starts again
        os.replace(old, _path(ref, OLD_LEDGER + ".bak"))
        _IDX.pop(str(new), None)
        if _path(ref, INDEX).exists():
            _path(ref, INDEX).unlink()


def _blank():
    return {"keys": {}, "last_event_by_cycle": {}, "count": 0, "bytes": 0, "marks": []}


def _scan(p, idx):
    """Read the journal from the byte the index last read to its end. A last line with no newline is one being written
    or one torn by a closed app: it is left unread."""
    with open(p, "rb") as f:
        f.seek(int(idx["bytes"]))
        data = f.read()
    pos = int(idx["bytes"])
    pieces = data.split(b"\n")
    pieces.pop()                                            # b"" after the last newline, or the unfinished line
    for raw in pieces:
        at, pos = pos, pos + len(raw) + 1
        try:
            row = json.loads(raw.decode("utf-8")) if raw.strip() else None
        except Exception:  # noqa: BLE001 -- a torn line is skipped, as record.lines skips it
            row = None
        if not isinstance(row, dict):
            continue
        idx["count"] += 1
        if (idx["count"] - 1) % MARK == 0:
            idx["marks"].append(at)
        if row.get("idempotency_key"):
            idx["keys"][_digest(row["idempotency_key"])] = idx["count"]
        if row.get("cycle_id") and row.get("event_id"):
            idx["last_event_by_cycle"][row["cycle_id"]] = row["event_id"]
    idx["bytes"] = pos


def _index(ref):
    """The index, current with the journal: this process's copy when the journal has not grown since; else
    j2-index.json, read forward from the byte it last read (an app closed between the line and the index); else built
    from the journal. Called under the department's lock."""
    _convert(ref)
    p = _path(ref, LEDGER)
    try:
        st = p.stat()
        ino, size = st.st_ino, st.st_size
    except FileNotFoundError:
        ino, size = None, 0
    held = _IDX.get(str(p))
    idx = held[1] if held and held[0] == ino else None
    if idx is None:
        idx = W._read(_path(ref, INDEX), None)
    if not isinstance(idx, dict) or not all(k in idx for k in _blank()) or int(idx.get("bytes") or 0) > size:
        idx = _blank()
    if int(idx["bytes"]) < size:
        _scan(p, idx)
    _IDX[str(p)] = (ino, idx)
    return idx


def _rows_from(ref, start, first_seq):
    """The journal's rows from byte `start`, each with its seq (a row written before seq existed takes its place)."""
    out = []
    try:
        with open(_path(ref, LEDGER), "rb") as f:
            f.seek(start)
            data = f.read()
    except FileNotFoundError:
        return out
    pieces = data.split(b"\n")
    pieces.pop()
    n = first_seq
    for raw in pieces:
        try:
            row = json.loads(raw.decode("utf-8")) if raw.strip() else None
        except Exception:  # noqa: BLE001
            row = None
        if isinstance(row, dict):
            out.append((int(row.get("seq") or n), row))
            n += 1
    return out


def _at_seq(ref, idx, seq):
    k = (int(seq) - 1) // MARK
    if k >= len(idx["marks"]):
        return None
    return next((row for s, row in _rows_from(ref, idx["marks"][k], k * MARK + 1) if s == int(seq)), None)


def events(ref):
    """The whole ledger, oldest first."""
    _convert(ref)
    return record.lines(_path(ref, LEDGER))


def _after(ref, after_seq):
    after = max(0, int(after_seq or 0))
    with W._lock(ref):
        marks = list(_index(ref)["marks"])
    if not marks:
        return []
    k = min(after // MARK, len(marks) - 1)
    return [(s, row) for s, row in _rows_from(ref, marks[k], k * MARK + 1) if s > after]


def events_after(ref, after_seq=0):
    """The ledger after a cursor, read from the index's nearest mark rather than from the top."""
    return [row for _, row in _after(ref, after_seq)]


def event_count(ref):
    with W._lock(ref):
        return int(_index(ref)["count"])


def _state(ref):
    return W._read(_path(ref, "j2-state.json"), None)


def _save_state(ref, row):
    with W._lock(ref):
        W._write(_path(ref, "j2-state.json"), row)
    return row


def _set(ref, **more):
    """Move the cycle: the step it stands on, and the plain word for its state."""
    with W._lock(ref):
        state = _state(ref)
        if not state:
            return None
        state.update(more)
        if "step" in more:
            state["journey"] = JOURNEY.get(more["step"], state.get("journey"))
        state["updated_at"] = W.now()
        W._write(_path(ref, "j2-state.json"), state)
        return state


def _clean(value):
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if str(k).lower() not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def append_event(ref, event):
    """Append one valid event, once, before the next actor is woken."""
    row = _clean(copy.deepcopy(event or {}))
    if row.get("department_ref") != ref:
        raise J2Error("DEPARTMENT_MISMATCH")
    required = ("idempotency_key", "cycle_id", "step", "journey", "actor", "recipient", "action", "state", "summary")
    missing = [key for key in required if row.get(key) in (None, "")]
    if missing:
        raise J2Error("INVALID_EVENT: " + ", ".join(missing))
    with W._lock(ref):
        # once, from the index: the journal itself is not read to append to it (M0.2)
        idx = _index(ref)
        digest = _digest(row["idempotency_key"])
        if digest in idx["keys"]:
            previous = _at_seq(ref, idx, idx["keys"][digest])
            if previous and previous.get("idempotency_key") == row["idempotency_key"]:
                return previous
        row.setdefault("schema_version", SCHEMA_VERSION)
        row.setdefault("event_id", "evt-" + uuid.uuid4().hex[:12])
        row.setdefault("identity_revision", int((W.dept(ref) or {}).get("identity_revision") or 1))
        row.setdefault("occurred_at", W.now())
        row.setdefault("visibility", ["agent_activity"])
        row.setdefault("evidence_refs", [])
        row.setdefault("correlation_id", row["cycle_id"])
        row.setdefault("causation_id", idx["last_event_by_cycle"].get(row["cycle_id"]))
        row["seq"] = idx["count"] + 1                   # the ledger's own order: clocks tick in seconds, events do not
        p = _path(ref, LEDGER)
        size = p.stat().st_size if p.exists() else 0
        if size > idx["bytes"]:
            with open(p, "ab") as f:                    # a line torn by a closed app is ended, so this one is a line of its own
                f.write(b"\n")
            size += 1
        record.append(p, row)
        idx["count"] += 1
        if (idx["count"] - 1) % MARK == 0:
            idx["marks"].append(size)
        idx["keys"][digest] = row["seq"]
        idx["last_event_by_cycle"][row["cycle_id"]] = row["event_id"]
        st = p.stat()
        idx["bytes"] = st.st_size
        _IDX[str(p)] = (st.st_ino, idx)
        record.write(_path(ref, INDEX), idx, indent=None)
        state = _state(ref)
        if isinstance(state, dict):
            state["event_count"] = idx["count"]         # the screen's poll reads the count here, not off the ledger
            W._write(_path(ref, "j2-state.json"), state)
    return row


def note(ref, step, actor, recipient, action, state, summary, key, payload=None, **more):
    """One event of the running cycle, or nothing when the department has no cycle (born before J2, or J2 off)."""
    cur = _state(ref)
    if not cur or not cur.get("cycle_id"):
        return None
    row = {"idempotency_key": "%s/%s/%s/%s" % (ref, cur["cycle_id"], step, key), "department_ref": ref,
           "cycle_id": cur["cycle_id"], "step": step, "journey": JOURNEY.get(step, "J2"), "actor": actor,
           "recipient": recipient, "action": action, "state": state, "summary": str(summary)[:400], "payload": payload or {}}
    row.update({k: v for k, v in more.items() if v is not None})
    return append_event(ref, row)


def _ready(dept):
    return any(isinstance(e, dict) and e.get("kind") == "j2_ready" for e in dept.get("events") or [])


# ---- the cycle ---------------------------------------------------------------------------------------------------
def active(ref):
    """The department lives its J2 cycle: the flag is on, a cycle exists, and nobody stopped it."""
    cur = _state(ref) if enabled() else None
    return bool(cur and cur.get("cycle_id") and cur.get("state") not in ("stopped", "done"))


def holding(ref):
    """A workflow runs only once Root has registered it (step 5). A department with no cycle is never held."""
    cur = _state(ref) if enabled() else None
    if not cur or not cur.get("cycle_id") or cur.get("state") == "done":
        return None
    if cur.get("state") == "stopped":
        return "the department's J2 cycle is stopped"
    if int(cur.get("step") or 1) < 6:
        return "waits for the workflow to be granted and registered"
    return None


def done(ref):
    return ((_state(ref) or {}).get("state") == "done") if enabled() else False


# Identity's standard is one standard, its own (PRD M3.3, MK-1): engine_runtime reads it (R._standard_gaps, its
# identity.enough step and that step's draft) and decides each question; this module records the question asked and
# what the owner said to it, and never decides one nor says one to the owner (rule 14; found by a verifier 2026-10-23:
# a presence check of its own here asked a question the marked standard does not hold, and posted it). The question on
# words that name nothing to build from is Identity's take step's, recorded by questioned().
QUESTION = {"words": "What is the %s for, and about whom or what?"}
THIN = "Your words name nothing to build from yet."


def _move(ref, state, **more):
    """Move the cycle's state, except that a cycle the owner stopped stays stopped: the move waits in `was`, and Start
    goes on from it (an answer given to a stopped department is used on Start)."""
    cur = _state(ref) or {}
    if cur.get("state") == "stopped":
        return _set(ref, was=state, **more)
    return _set(ref, state=state, **more)


def _ask_gap(ref, dept, cur):
    """Where the cycle starts, and after the owner answers a question Identity's code asked: Identity reads its standard
    on the record by code and asks the next point unmet (R.identity_asks, which records it through asked()). Returns the
    cycle when a question is open now, None when the standard is met."""
    return R.identity_asks(ref)


def reopened(ref):
    """From blocked, the plan is shaped afresh (M3.5): the cycle goes back to step 2 with Root's repairs at nought. A
    stopped cycle stays stopped and goes on from there on Start."""
    with W._lock(ref):
        cur = _state(ref)
        if not cur or not cur.get("cycle_id"):
            return None
        note(ref, int(cur.get("step") or 5), "User", "Identity", "cycle.reopened", "running", "The plan is shaped afresh from the owner's words.",
             "reopened-" + uuid.uuid4().hex[:6])
        return _move(ref, "adapting", step=2, repairs=0)


def begin(ref):
    """Start the department's cycle, once. Called when J1 hands over (D1: J2 is the department's own life, and nobody
    presses a button for it), and by Start for a department born before that. A stopped cycle starts again."""
    with W._lock(ref):
        dept = W.dept(ref)
        cur = _state(ref)
        if cur and cur.get("state") != "stopped":
            return cur
        if cur:
            return resume(ref)
        cur = _save_state(ref, {"cycle_id": "cycle-" + uuid.uuid4().hex[:10], "step": 1, "journey": "J2.a",
                                "state": "assessing", "open_ask": None, "workflow": [], "repairs": 0, "updated_at": W.now()})
        return _ask_gap(ref, dept, cur) or cur


def start(ref):
    """The Start button's boundary: valid only after J1's hand-over, and the same answer however often it is pressed."""
    if not enabled():
        raise J2Error("J2_FLOW_DISABLED")
    dept = W.dept(ref)
    if not dept:
        raise J2Error("NO_DEPARTMENT")
    if not _ready(dept):
        raise J2Error("J2_NOT_READY")
    return begin(ref)


def answer(ref, text, ask_id=None, at=None, go_on=True):
    """The owner's words for Identity's open question: written to the identity, and the standard is read again (J2.1:
    one question at a time, until it is met). `at` is where the owner said them in the chat ({board, n}), when they came
    that way; the card keeps them under it, and the chat does not say them again. `go_on` hands the words to Identity's
    step once the standard is met and the department's first words are filed, so Identity says so and starts step 2;
    Identity's own step, which goes on itself, passes False. Returns the cycle's state, and for a question Identity's
    code asked, what the answer put on the record (`taken`) or the defaults 'just do it' used (`defaults`)."""
    text = " ".join(str(text or "").split())[:2000]
    if not text:
        raise J2Error("EMPTY_ANSWER")
    with W._lock(ref):
        dept = W.dept(ref)
        if not dept:
            raise J2Error("NO_DEPARTMENT")
        cur = _state(ref)
        aid = (cur or {}).get("open_ask")
        ask = next((a for a in W.asks(ref) if a["id"] == aid and a.get("kind") == "j2_identity"), None)
        if not cur or not ask or (ask_id and ask_id != aid):
            raise J2Error("NO_OPEN_QUESTION")
        if ask["status"] != "pending":
            raise J2Error("ALREADY_HANDLED")
        missing = ask.get("missing")
        if missing == "words":
            # the first words named nothing to build from (M0.5): the answer is the owner's words to Identity, on the board,
            # and Identity reads them as the first words, against the same standard; the identity itself is not edited here
            _took(ref, ask, text)
            _, row = R.request(ref, text)
            if row:
                # the words on the board carry the answer, and the card keeps it: the chat leaves that post to the card
                # (found by a verifier 2026-10-23: the answer stood under the card and again as a turn of its own)
                ask["words_at"] = {"board": ref, "n": row["n"]}
                W._put_ask(ref, ask)
            return _state(ref)
        hurry = bool(R.JUST_DO_IT.fullmatch(text))
        filed = bool(W.versions(ref, W.artifacts_of(dept)[0]))
        if ask.get("standard") or (missing == "rules" and not hurry) or (hurry and filed and go_on):
            # Identity's standard was not met (M3.3): the answer is the owner's words to Identity, which reads them against
            # the standard again and asks again or starts. A rule given as an answer keeps its tag (M3.4): Identity reads
            # it, restates its tag and scope, and the owner stamps it. 'Just do it' to a question Identity's code asked
            # goes the same way once the first words are filed: Identity's step fills the defaults, names them and starts
            # (found by a verifier 2026-10-26: the answer box filled them and said nothing). Nothing is written here
            _took(ref, ask, text)
            _, row = R.request(ref, text, answers=ask["id"])
            if row:
                ask["words_at"] = {"board": ref, "n": row["n"]}      # the card keeps the answer; the chat leaves the post to it
                W._put_ask(ref, ask)
            return _state(ref)
        # Identity's code asked this (where the cycle started, or after an answer or a stamp), on a point it reads on
        # the record: Identity's code takes the answer onto the record, through the record's own writers (done-when is
        # its items, M3.1; the owner and the budget too, so the same question never comes back, M3.3), or fills the
        # point from the kind's defaults on 'just do it'; the revision moves the Org screen's copy
        said = {"defaults": R._standard_defaults(ref, list(ask.get("points") or []) or [missing])} if hurry else \
            {"taken": R._standard_fill(ref, missing, text)}
        ask.update({"status": "stamped", "decided": W.now(), "by": "the owner", "answered": text})
        if at:
            ask["words_at"] = at
        W._put_ask(ref, ask)
        note(ref, 1, "User", "Identity", "ask.answered", "complete", "The owner answered: %s" % text[:200], "answer-" + aid,
             {"missing": missing})
        cur = _move(ref, "assessing", open_ask=None)
        nxt = _ask_gap(ref, W.dept(ref), cur)
        if nxt:
            return nxt
        if go_on and filed:
            # the standard is met and the first words are filed: Identity's step goes on from here, as for an answer said
            # in the chat (it reads the standard again, says so and starts step 2); the cycle never stands at 'Reading your
            # words' with nothing to read (found 2026-10-26 through the answer box)
            R.request(ref, text, answers=aid)
        return dict(cur, **said)


def _took(ref, ask, text, by="the owner", at=None):
    """Close Identity's question with the owner's words: the ask is answered once, and the ledger says so once,
    whichever way the words came (the answer box, or the chat; `at` is where they were said there)."""
    ask.update({"status": "stamped", "decided": W.now(), "by": by, "answered": text})
    if at:
        ask["words_at"] = at
    W._put_ask(ref, ask)
    note(ref, 1, "User", "Identity", "ask.answered", "complete", "The owner answered: %s" % text[:200], "answer-" + ask["id"],
         {"missing": ask.get("missing")})
    return _move(ref, "assessing", open_ask=None)


def open_question(ref):
    """Identity's open question to the owner, as every screen shows it: {id, text, why, missing, asked, standard,
    points}, or None. A question on Identity's standard (M3.3) says so, with the points it asks about, and takes
    'just do it'. A stopped department keeps its question; the answer is used on Start."""
    cur = _state(ref) if enabled() else None
    if not cur or not cur.get("open_ask"):
        return None
    ask = next((a for a in W.asks(ref) if a["id"] == cur["open_ask"] and a.get("kind") == "j2_identity" and a["status"] == "pending"), None)
    if not ask:
        return None
    return {"id": ask["id"], "text": ask.get("text"), "why": ask.get("why"), "missing": ask.get("missing"), "asked": ask.get("created"),
            "standard": bool(ask.get("standard")), "points": list(ask.get("points") or [])}


def standard_question(ref):
    """Identity's open question on its standard, as the ask holds it, or None (M3.3)."""
    cur = _state(ref) if enabled() else None
    if not cur or not cur.get("open_ask"):
        return None
    return next((a for a in W.asks(ref) if a["id"] == cur["open_ask"] and a.get("kind") == "j2_identity" and a.get("standard")
                 and a["status"] == "pending"), None)


def asked(ref, question, missing, why, key=None, standard=True):
    """Identity's standard is not met (J2.a, PRD M3.3): the one question Identity decided is recorded here, a real ask that
    takes words, in the chat or through /j2/answer, and nothing starts until the standard is met or the owner says 'just
    do it'. `standard` is True when Identity's reading in a step asked it (that reading reads the answer again), False
    when Identity's code asked it on the record (R.identity_asks). One open question at a time, with no cap on how many
    are asked in turn."""
    # the question and its why reach the card in plain words, as every card's do (R.plain_card, PRD M3.6)
    said = R.plain_card(ref, {"text": str(question), "why": str(why or "")}, "question")
    question, why = said["text"], said["why"]
    with W._lock(ref):
        cur = _state(ref)
        if not cur or not cur.get("cycle_id"):
            return None
        ask = next((a for a in W.asks(ref) if a["id"] == cur.get("open_ask") and a.get("kind") == "j2_identity"
                    and a["status"] == "pending" and bool(a.get("standard")) == bool(standard)), None)
        if ask is None:
            ask = W._put_ask(ref, W.j2_identity_ask(question, cur["cycle_id"], (missing or ["goal"])[0], why, missing, standard))
        note(ref, 1, "Identity", "User", "identity.questioned", "waiting", str(question), "identity-question-" + str(key or ask["id"]),
             {"missing": list(missing or []), "why": str(why or ""), "standard": bool(standard)})
        return _move(ref, "waiting", step=1, open_ask=ask["id"])


def took(ref, aid, words, at=None):
    """Close Identity's question `aid` with the owner's words, said in the chat (M3.3); `at` is the owner's post that said
    them ({board, n}), which the card keeps. Returns the ask, closed now or before; None for no such question of Identity's."""
    with W._lock(ref):
        ask = next((a for a in W.asks(ref) if a["id"] == aid and a.get("kind") == "j2_identity"), None)
        if ask and ask["status"] == "pending":
            _took(ref, ask, " ".join(str(words or "").split())[:2000], at=at)
        return ask


def answered_question(ref):
    """The last of Identity's questions the owner answered in this cycle, kept under its card: {id, text, answer, at}."""
    cur = _state(ref) if enabled() else None
    if not cur or not cur.get("cycle_id"):
        return None
    done = [a for a in W.asks(ref) if a.get("kind") == "j2_identity" and a.get("cycle_id") == cur["cycle_id"]
            and a["status"] == "stamped" and a.get("answered")]
    if not done:
        return None
    a = done[-1]
    return {"id": a["id"], "text": a.get("text"), "answer": a.get("answered"), "at": a.get("decided")}


def took_words(ref, words, at=None):
    """The owner's words reached Identity in the chat while its question on thin words is open: they answer it (M0.5).
    `at` is the owner's post that said them ({board, n}), which the card keeps. Returns True when they did."""
    with W._lock(ref):
        cur = _state(ref)
        ask = next((a for a in W.asks(ref) if cur and a["id"] == cur.get("open_ask") and a.get("kind") == "j2_identity"
                    and a.get("missing") == "words" and a["status"] == "pending"), None)
        if not ask:
            return False
        _took(ref, ask, " ".join(str(words or "").split())[:2000], at=at)
        return True


def waiting_on_owner(ref):
    cur = _state(ref) if enabled() else None
    return bool(cur and cur.get("state") == "waiting" and cur.get("open_ask")
                and any(a["id"] == cur["open_ask"] and a.get("kind") == "j2_identity" and a["status"] == "pending" for a in W.asks(ref)))


def status(ref):
    dept = W.dept(ref)
    if not dept:
        raise J2Error("NO_DEPARTMENT")
    state = _state(ref) or {"cycle_id": None, "step": None, "journey": None,
                            "state": "not_started" if _ready(dept) else "not_ready", "updated_at": None}
    count = state.get("event_count")
    return dict(state, department_ref=ref, enabled=enabled(), event_count=int(count) if count is not None else event_count(ref),
                done_when=dept.get("done"), goal_reached=state.get("state") == "done",
                open_question=open_question(ref), answered_question=answered_question(ref))


def stop(ref):
    """The owner's Stop: no new admissions, the department is off, and the record says who did it. A department that
    never started is stopped without a cycle of work being run first."""
    with W._lock(ref):
        dept = W.dept(ref)
        if not dept:
            raise J2Error("NO_DEPARTMENT")
        cur = _state(ref)
        if cur and cur.get("state") == "stopped":
            return cur
        if not cur:
            cur = _save_state(ref, {"cycle_id": "cycle-" + uuid.uuid4().hex[:10], "step": 1, "journey": "J2.a",
                                    "state": "assessing", "open_ask": None, "workflow": [], "repairs": 0, "updated_at": W.now()})
        note(ref, int(cur.get("step") or 1), "User", "Identity", "cycle.stopped", "stopped", "The owner stopped the department.",
             "cycle-stopped-" + uuid.uuid4().hex[:6])
        cur = _set(ref, state="stopped", was=cur.get("state"))
    W.set_stopped(ref, True)
    return _state(ref)


def resume(ref):
    """Start again after a Stop: the cycle goes on from the step it stood on."""
    with W._lock(ref):
        cur = _state(ref)
        if not cur or cur.get("state") != "stopped":
            return cur
        back = cur.get("was") if cur.get("was") not in (None, "stopped") else ("running" if int(cur.get("step") or 1) >= 6 else "assessing")
        note(ref, int(cur.get("step") or 1), "User", "Identity", "cycle.resumed", back, "The owner started the department again.",
             "cycle-resumed-" + uuid.uuid4().hex[:6])
        cur = _set(ref, state=back, was=None)
    if (W.dept(ref) or {}).get("stopped"):
        W.set_stopped(ref, False)
    return _state(ref)


# ---- the hooks: the ledger is written where the thing happens ------------------------------------------------------
def on_post(ref, row):
    """A post on the department's board that is a move of the lifecycle becomes its event. A stopped cycle records only
    the owner's own answer to an ask, given while it is stopped and used on Start (S10: the card can still be answered).
    Never raises."""
    try:
        src, dst, act = row.get("src"), list(row.get("dst") or []), row.get("msg_type")
        if not active(ref) and not (src == R.OWNER and act in ("accept-proposal", "reject-proposal") and enabled()
                                    and (_state(ref) or {}).get("state") == "stopped"):
            return
        pl = row.get("payload") or {}
        word, key = pl.get("word"), "post-%s" % row.get("n")
        names = [e.get("name") for e in pl.get("engines") or [] if isinstance(e, dict)]
        if word == "line":
            if src == "Identity" and dst == ["Adaptation"] and act == "request":
                note(ref, 2, "Identity", "Adaptation", "proposal.requested", "running",
                     "Reshape the workflow: Root's check refused it." if pl.get("faults") else "Propose what the department does next.",
                     key, {"faults": pl.get("faults") or []})
                _set(ref, step=2, state="adapting")
            elif src == "Adaptation" and dst == ["Priority"] and act == "propose":
                note(ref, 2, "Adaptation", "Priority", "proposal.created", "pending",
                     "Proposed the workflow %s (%s)." % (" -> ".join(names), "from the Library" if pl.get("source") == "library" else "shaped for this goal"),
                     key, {"source": pl.get("source"), "workflow": names, "hop": row.get("hop")}, proposal_ref=row.get("thread"))
                _set(ref, step=3, state="bargaining")
            elif src == "Priority" and act == "accept-proposal":
                note(ref, 3, "Priority", "Adaptation", "proposal.granted", "granted", str(pl.get("why") or "Granted within the envelope."),
                     key, {"hop": row.get("hop")}, proposal_ref=row.get("thread"))
            elif src == "Priority" and act == "reject-proposal":
                note(ref, 3, "Priority", "Adaptation", "proposal.refused", "refused", str(pl.get("why") or "Refused."),
                     key, {"hop": row.get("hop")}, proposal_ref=row.get("thread"), reason_codes=["envelope"])
            elif src == "Priority" and act == "propose":
                note(ref, 3, "Priority", "Adaptation", "proposal.countered", "waiting", str(pl.get("why") or "Countered."),
                     key, {"keep": pl.get("keep") or [], "hop": row.get("hop")}, proposal_ref=row.get("thread"), reason_codes=["envelope"])
        elif word == "conflict" and dst == ["Identity"]:
            note(ref, 4, src, "Identity", "conflict.raised", "waiting", str(pl.get("why") or "The bargain did not close."),
                 key, {"workflow": names, "bound": pl.get("bound")}, proposal_ref=pl.get("for"))
            _set(ref, step=4, state="closing")
        elif word == "finding" and src == "Audit":
            art = _deliverable(ref, pl.get("artifact"))
            note(ref, 7, "Audit", "Identity", "audit.finding_filed", "recorded", str(pl.get("claim") or "A finding."),
                 key, {"severity": pl.get("severity"), "findings": len(pl.get("findings") or [])},
                 evidence_refs=[{"artifact": art, "version": pl.get("about_version")}] if art else [])
            _set(ref, step=8, state="pursuing")
        elif src == "Identity" and R.OWNER in dst and act == "request":
            note(ref, int((_state(ref) or {}).get("step") or 1), "Identity", "User", "ask.created", "waiting",
                 str(pl.get("objective") or pl.get("word") or "An ask.")[:300], key, {"word": word})
        elif src == R.OWNER and act in ("accept-proposal", "reject-proposal"):
            said = ("chose: %s" % pl["chose"]) if pl.get("chose") else ("stamped it" if act == "accept-proposal" else "refused it")
            note(ref, int((_state(ref) or {}).get("step") or 1), "User", "Identity", "ask.answered", "complete",
                 "The owner %s." % said, key, dict({"word": word}, **({"option": pl["option"]} if pl.get("option") else {})))
    except Exception:  # noqa: BLE001 -- the ledger never fails the post it records
        return


def on_run(ref, row, when):
    """A workflow's run: its slot, its start, how it ended. Never raises."""
    try:
        if not active(ref) or row.get("system"):
            return
        eng, rid = row.get("engine"), row.get("id")
        if when == "started":
            note(ref, 6, "Coordination", eng, "slot.assigned", "assigned", "%s has the next turn." % eng, "slot-%s" % rid,
                 {"slot": row.get("slot")}, run_ref=rid, workflow_ref=eng)
            note(ref, 6, eng, "Coordination", "run.started", "running", "%s started." % eng, "run-started-%s" % rid,
                 {"slot": row.get("slot")}, run_ref=rid, workflow_ref=eng)
            return
        status_ = row.get("status")
        spend = row.get("spend") or {}
        env = {"calls_used": spend.get("calls"), "money_used": spend.get("usd")}
        if status_ == "ok":
            wrote = row.get("wrote") or {}
            if wrote.get("art"):
                note(ref, 6, eng, "Coordination", "artifact.filed", "filed", "%s v%s filed." % (wrote["art"], wrote.get("v")),
                     "filed-%s" % rid, {}, run_ref=rid, workflow_ref=eng,
                     evidence_refs=[{"artifact": wrote["art"], "version": wrote.get("v")}])
            note(ref, 6, eng, "Coordination", "run.completed", "complete", str(row.get("what") or "%s finished." % eng),
                 "run-ended-%s" % rid, {}, run_ref=rid, workflow_ref=eng, envelope=env)
        elif status_ == "failed":
            note(ref, 6, eng, "Coordination", "run.failed", "failed", str(row.get("what") or "%s failed." % eng),
                 "run-ended-%s" % rid, {}, run_ref=rid, workflow_ref=eng, envelope=env, reason_codes=["check.failed"])
        elif status_ in ("waiting", "asked"):
            note(ref, 6, eng, "Coordination", "workflow.blocked", "waiting", str(row.get("what") or "%s waits." % eng),
                 "run-ended-%s" % rid, {"on": "the model" if status_ == "waiting" else "the owner"}, run_ref=rid, workflow_ref=eng)
    except Exception:  # noqa: BLE001 -- the ledger never fails the run it records
        return


def on_held(ref, engine, slot, why):
    """Priority held a workflow at its envelope (J2.5). Never raises."""
    try:
        if active(ref):
            note(ref, 6, "Priority", engine, "envelope.held", "held", str(why or "%s is past its envelope." % engine),
                 "held-%s" % slot, {"slot": slot}, workflow_ref=engine, reason_codes=["envelope"])
    except Exception:  # noqa: BLE001
        return


def on_table(ref, table, grown=None):
    """Coordination wrote its table after a registered plan, or grew its line by an engine the owner stamped (PRD M4.1).
    Never raises."""
    try:
        if not active(ref):
            return
        line = list((table or {}).get("line") or [])
        v = (table or {}).get("registered")
        # the slots it wrote, in words: one for each engine of the line (PRD M4.3)
        slots = [{"engine": r.get("engine"), "on": r.get("on")} for r in (table or {}).get("timetable") or [] if isinstance(r, dict)]
        if grown:
            note(ref, 6, "Coordination", "Identity", "timetable.written", "complete", "Coordination added %s to the line." % grown,
                 "table-grow-%s-%s" % (grown, uuid.uuid4().hex[:6]), {"line": line, "grown": grown, "timetable": slots})
        else:
            note(ref, 5, "Coordination", "Root", "timetable.written", "complete", "Coordination set its line to the plan: %s."
                 % " -> ".join(line), "table-v%s" % v, {"line": line, "version": v, "timetable": slots}, workflow_ref="workflow/%s" % v)
    except Exception:  # noqa: BLE001 -- the ledger never fails the table it records
        return


def on_granted(ref, engine, envelope, kept, version=None):
    """Priority gave a new engine its limit, or let it keep the one it holds (PRD M4.1). Never raises."""
    try:
        if active(ref):
            env = dict(envelope or {})
            note(ref, 5 if version else 6, "Priority", engine, "envelope.granted", "granted",
                 ("%s keeps the limit it holds." if kept else "Priority gave %s its limit.") % engine,
                 "granted-%s-%s" % (engine, ("v%s" % version) if version else uuid.uuid4().hex[:6]),
                 {"engine": engine, "calls": env.get("calls"), "usd": env.get("usd"), "kept": bool(kept)},
                 workflow_ref=("workflow/%s" % version) if version else None)
    except Exception:  # noqa: BLE001
        return


def registered(ref, engines, source, by="Root", checks=None, plan=None, fit=None):
    """Root's check passed: the workflow is on the department's record, and the work may run (step 5 to step 6). The
    validated event lists the checks that ran, each with whether it held and why (M0.7). The registration keeps them too
    (A1.14): the rows, which done-when items the engines cover, the deliverable (the last engine's output), the engines
    the plan left out (what Coordination's table will hold once it writes after this record), and what each engine does
    differently for this goal when the plan says. `plan` is the engines as the granted line carried them (dicts, with
    their covers); without it the names stand for the plan."""
    names = [e if isinstance(e, str) else e.get("name") for e in engines]
    import layer_schema as S
    with W._lock(ref):
        dept = W.dept(ref)
        versions = list(dept.get("workflows") or [])
        version = len(versions) + 1
        reg = {"version": version, "engines": names, "source": source, "registered": W.now(), "by": by}
        if checks is not None:
            reg["checks"] = [dict(c) for c in checks]
        reg["covers"] = S.as_workflow([e for e in plan if isinstance(e, dict)] if plan else names, source, dept)["covers"]
        if fit:
            reg["fit"] = {str(k): str(v)[:300] for k, v in fit.items() if k in names and v}
        grown = set((R.coordination(ref).get("grown") or []))
        reg["left_out"] = [n for n in dept.get("engines") or [] if n not in names and n not in grown]
        versions.append(reg)
        reg["deliverable"] = S.deliverable(dict(dept, workflows=versions))
        dept["workflows"] = versions                 # the department's own record: nothing here is written to the Library
        W.save_dept(ref, dept, by="root")
    key = "workflow-v%d" % version
    note(ref, 5, "Root", "Adaptation", "workflow.validated", "complete", "The workflow meets Sutra's standards.", key + "-validated",
         {"workflow": names, "checks": list(checks or [])}, workflow_ref="workflow/%d" % version)
    note(ref, 5, "Root", "Coordination", "workflow.registered", "complete", "Registered %s on the department's record, version %d."
         % (" -> ".join(names), version), key + "-registered", {"workflow": names, "source": source, "version": version},
         workflow_ref="workflow/%d" % version)
    return _set(ref, step=6, state="running", workflow=names, repairs=0)


def refused(ref, engines, faults, checks=None):
    """Root's check failed (J2.4): nothing is registered; the reasons go back, with the checks that ran (none, when the
    line failed Adaptation's own check before it reached Root). Returns how often that has now happened."""
    names = [e if isinstance(e, str) else e.get("name") for e in engines]
    cur = _state(ref) or {}
    n = int(cur.get("repairs") or 0) + 1
    # each refusal is its own event: the count starts again when the plan is shaped afresh (reopened), so the count alone
    # would name an earlier refusal of the same cycle and the append would return that row instead (found by a verifier
    # 2026-10-23: after new words reopened a blocked plan, Root's three refusals never reached the ledger)
    key = "workflow-refused-%d-%s" % (n, uuid.uuid4().hex[:6])
    if names:
        note(ref, 5, "Root", "Adaptation", "workflow.blocked", "refused", "Root's check refused the workflow: %s." % "; ".join(faults)[:300],
             key, {"workflow": names, "faults": list(faults), "checks": list(checks or [])}, reason_codes=["standards"])
    else:
        note(ref, 2, "Adaptation", "Identity", "workflow.blocked", "refused", "The shaped line did not pass its check: %s." % "; ".join(faults)[:300],
             key, {"workflow": [], "faults": list(faults), "checks": list(checks or [])}, reason_codes=["check.failed"])
    _set(ref, step=5, state="reshaping", repairs=n)
    return n


def ruled(ref, ruling, why, engines):
    names = [e if isinstance(e, str) else e.get("name") for e in engines or []]
    note(ref, 4, "Identity", "Adaptation" if ruling != "ask" else "User", "identity.ruled", ruling, str(why or ruling)[:300],
         "ruled-" + uuid.uuid4().hex[:6], {"ruling": ruling, "workflow": names})
    if ruling == "drop":
        _set(ref, step=4, state="blocked")
    elif ruling == "ask":
        _set(ref, step=4, state="waiting")


def assessed(ref, dept, key="first"):
    note(ref, 1, "Identity", "Adaptation", "identity.assessed", "complete", "The identity is good enough to start on.",
         "identity-assessed-" + str(key), {"sufficient": True, "done_when": dept.get("done"), "rules": len(dept.get("rules") or [])})


def questioned(ref, question, key):
    """The first words name nothing to build from (J2.1): Identity's question is a real ask, answerable in the chat or
    through /j2/answer, and nothing starts until it is answered (M0.5). One open ask, however often it is asked."""
    with W._lock(ref):
        cur = _state(ref)
        if not cur or not cur.get("cycle_id"):
            return None
        d = W.dept(ref) or {}
        text = QUESTION["words"] % ("site" if d.get("kind") == "website" else "department")
        ask = next((a for a in W.asks(ref) if a.get("kind") == "j2_identity" and a.get("missing") == "words"
                    and a["status"] == "pending" and a.get("cycle_id") == cur["cycle_id"]), None)
        if ask is None:
            ask = W._put_ask(ref, W.j2_identity_ask(text, cur["cycle_id"], "words", question or THIN))
        note(ref, 1, "Identity", "User", "identity.questioned", "waiting", text, "identity-question-" + str(key),
             {"missing": ["words"], "why": str(question or THIN)})
        return _move(ref, "waiting", step=1, open_ask=ask["id"])


def _deliverable(ref, artifact=None):
    """What Audit reads and the ledger cites: the artifact the event names, else the department's deliverable, the last
    output of its registered plan (PRD M8.1: the interface's to say); None when it has none."""
    return artifact or S.deliverable(W.dept(ref))


def not_read(ref, version, why, artifact=None):
    """Audit's judge did not read the version (not sampled, or no model to read it): nothing is found and nothing is
    cleared. The ledger says so, and the cycle stays at step 7 until a version is read (M0.3). Never raises."""
    try:
        if not active(ref):
            return
        why = str(why or "it was not read").rstrip(".")
        art = _deliverable(ref, artifact)
        note(ref, 7, "Audit", "Identity", "audit.not_read", "not_read", "Audit did not read %s v%s: %s." % (art or "what the plan delivers", version, why),
             "audit-not-read-v%s" % version, {"why_not_read": why}, evidence_refs=[{"artifact": art, "version": version}] if art else [])
        _set(ref, step=7, state="unread")
    except Exception:  # noqa: BLE001 -- the ledger never fails the run it records
        return


def _read_clean(ref, version, art):
    """The ledger's line for a version Audit read and found nothing to put right in (step 7): written once for the version,
    by whichever of audited and reached comes first, so it always stands before the goal it led to."""
    note(ref, 7, "Audit", "Identity", "audit.finding_filed", "recorded",
         "Audit read %s v%s and found nothing to put right." % (art or "what the plan delivers", version),
         "audit-clean-v%s" % version, {"severity": "none", "findings": 0}, evidence_refs=[{"artifact": art, "version": version}] if art else [])


def audited(ref, version, findings, artifact=None, reading=None):
    """Audit read what went out, and the ledger records that (step 7): a version read item by item, every item met, none to
    confirm and no high finding open, with nothing to put right, is one event that says so. 'Found nothing' is no reading: a
    version nobody read, or one that read no item, records nothing here. Whether the goal is reached is not decided here, nor
    written: this module records and projects and never rules (rule 14). Identity's covering decides it from the reading
    (identity_done, PRD M8.4) and records it through reached(). Returns False, since nothing is reached by recording."""
    r = reading or {}
    if not active(ref) or not (r.get("read") and r.get("met") and not r.get("not_met") and not r.get("to_confirm") and not r.get("high")):
        return False
    if not findings:
        # with findings, Audit's own post to Identity is the event; "found nothing" is said only when that is true
        # (found live 2026-10-08: twelve findings filed, and the next line of the ledger said nothing was found)
        _read_clean(ref, version, _deliverable(ref, artifact))
    return False


def reached(ref, version, artifact=None, reading=None, findings=0):
    """Identity says the goal is reached (identity_done, PRD M8.4), and the ledger records it: one goal.reached event, citing
    the reading it rests on and the version it read, and the cycle is done. The decision is Identity's, made from the reading
    and held to done_is_read before this is called; this records it, once. A version that was read clean has its line first.
    Returns True when it was recorded now, False when the cycle is not in step to be done or it was recorded already."""
    if not active(ref):
        return False
    dept = W.dept(ref) or {}
    art = _deliverable(ref, artifact)
    if not findings:
        _read_clean(ref, version, art)
    ev = [dict({"artifact": art, "version": version}, **({"reading": reading} if reading else {}))] if art else ([{"reading": reading}] if reading else [])
    note(ref, 8, "Identity", "User", "goal.reached", "done", "Done-when holds: %s." % str(dept.get("done") or "").rstrip("."),
         "goal-reached-v%s" % version, {"done_when": dept.get("done"), "reading": reading}, evidence_refs=ev)
    _set(ref, step=8, state="done")
    return True


# ---- what the screen reads ----------------------------------------------------------------------------------------
def _board_action(row):
    msg = row.get("msg_type")
    word = str((row.get("payload") or {}).get("word") or "")
    if msg == "propose":
        return "proposal.created"
    if msg == "accept-proposal":
        return "proposal.accepted"
    if msg in ("reject-proposal", "refuse"):
        return "proposal.refused"
    if msg == "request" and "owner" in [str(x).lower() for x in row.get("dst") or []]:
        return "ask.created"
    if word == "finding":
        return "audit.finding_filed"
    return "board." + str(msg or "message")


def activity(ref, after_seq=0, after_board=0):
    """Safe chronological activity derived from canonical J2 events and the real board: after the two cursors, the
    ledger's seq and the board's n, each read in its own order, so no row is shown twice or never."""
    rows = []
    after_board = max(0, int(after_board or 0))
    for seq, event in _after(ref, after_seq):
        rows.append({
            "id": event["event_id"], "at": event.get("occurred_at"), "actor": event["actor"],
            "recipient": event["recipient"], "action": event["action"], "state": event["state"],
            "summary": event["summary"], "step": event.get("step"), "journey": event.get("journey"),
            "evidence_refs": event.get("evidence_refs") or [], "payload": _clean(event.get("payload") or {}),
            "seq": seq,
        })
    for row in R.board(ref):
        if after_board and int(row.get("n") or 0) <= after_board:
            continue
        payload = _clean(row.get("payload") or {})
        summary = str(payload.get("why") or payload.get("done") or payload.get("objective") or payload.get("word") or row.get("msg_type") or "Message")
        rows.append({
            "id": "board-%s" % row.get("n"), "at": row.get("at"), "actor": row.get("src"),
            "recipient": ", ".join(str(x) for x in row.get("dst") or []), "action": _board_action(row),
            "state": "recorded", "summary": summary, "step": None, "journey": None,
            "evidence_refs": [], "payload": payload, "seq": int(row.get("n") or 0),
        })
    # by the second, then each source in its own order: two rows of one second keep the order they were written in
    rows.sort(key=lambda item: (str(item.get("at") or ""), 0 if str(item.get("id")).startswith("board-") else 1, item.get("seq") or 0))
    return rows


def activity_page(ref, after_seq=0, after_board=0):
    """One page of the activity, and the two cursors to read the next one from."""
    after_seq, after_board = max(0, int(after_seq or 0)), max(0, int(after_board or 0))
    rows = activity(ref, after_seq, after_board)
    seqs = [r["seq"] for r in rows if not str(r["id"]).startswith("board-")]
    ns = [r["seq"] for r in rows if str(r["id"]).startswith("board-")]
    return {"events": rows, "after_seq": max([after_seq] + seqs), "after_board": max([after_board] + ns)}
