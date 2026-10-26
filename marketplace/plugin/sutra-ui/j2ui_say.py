"""j2ui_say.py -- `api/say`: the owner's words, routed to the writers that already exist (UI port, step C4).

The page has one box. A click on an option sends 'Option 2'; a typed answer or a new request sends the words. Nothing here
writes a record: every word reaches the department through the writer the Chat already uses, so the owner's act is the
record's own and the adapter speaks as nobody.

    'Option k' (or '1. Option k') with an ask waiting   k is read against the options the owner was shown (the page keeps the
                                                        message it was given, whatever the live list says now): an options
                                                        ask takes website_dept.choose_option, a stamp ask decide_ask
    words, Identity's question open                     j2_runtime.answer
    words, an options ask that offers 'words'           choose_option(..., 'words', text)
    any other words                                     website_dept.owner_ask on Root, the front door, about this department
                                                        (a department with no Root takes them itself): exactly the Chat's path

It is never refused because work runs: the owner may speak at any time. The three other POSTs of the prototype's page (a new
run, the output type, clearing memory) have no meaning for a long-lived department; each answers 409 and changes nothing.
"""
import re

import j2_runtime as J
import website_dept as W
import j2ui_common as C

#: an answer: '[N.] [Option] k', the question number defaulting to 1 (the page joins several as '1. Option 2; 2. Option 1')
ANSWER = re.compile(r"^\s*(?:(\d+)\s*[.:)]\s*)?(?:option\s*)?(\d+)\s*[.:)]?\s*$", re.I)
CODES = {"NO_DEPARTMENT": 404, "EMPTY_ANSWER": 400}          # a J2Error's code is the text before its first colon; any other is 409
TEXT_CHARS = 2000


class SayError(Exception):
    """A refusal, as the page's server says it: the status and the JSON body."""

    def __init__(self, status, body):
        super().__init__("%s %s" % (status, body))
        self.status, self.body = status, body


class Empty(SayError):
    def __init__(self):
        super().__init__(400, {"error": "empty"})


def parse_answer(text):
    """k when the whole text is one answer to the first question ('Option 2', '2', '1. Option 2'), else None. Several
    segments, or an answer to another question, are words."""
    parts = [p for p in str(text).split(";") if p.strip()]
    if len(parts) != 1:
        return None
    m = ANSWER.match(parts[0])
    if not m or int(m.group(1) or 1) != 1:
        return None
    return int(m.group(2))


def _answer(c, p, k):
    """'Option k' for the ask the page shows: k is a place in the options the owner was shown."""
    ask = p["ask"]
    ids = c.ask_opts.get(p["msg"]) or ([o.get("id") for o in W.offered(c.d, ask)] if p["form"] == "options" else list(("approve", "refuse")))
    if not 1 <= k <= len(ids):
        raise SayError(400, {"error": "no such option"})
    if p["form"] == "options":
        W.choose_option(c.ref, ask["id"], ids[k - 1])         # an option no longer offered is AskError UNKNOWN_OPTION: 409
    else:
        W.decide_ask(c.ref, ask["id"], ids[k - 1] == "approve")


def _words(c, p, text):
    open_q = J.open_question(c.ref)
    if open_q:
        J.answer(c.ref, text, open_q["id"])
    elif p and p["form"] == "options" and W.WORDS_OPTION in (c.ask_opts.get(p["msg"]) or [o.get("id") for o in W.offered(c.d, p["ask"])]):
        W.choose_option(c.ref, p["ask"]["id"], W.WORDS_OPTION, text)
    elif c.root_ref:
        W.owner_ask(c.root_ref, text, about=c.ref)             # the front door, as the Chat sends them
    else:
        W.owner_ask(c.ref, text)


def say(ref, text):
    """The owner's words or option for the department: {'ok': True}. Empty words raise Empty; a refusal raises SayError."""
    text = " ".join(str(text or "").split())[:TEXT_CHARS]
    if not text:
        raise Empty()
    C.touch(ref)
    c = C.get_ctx(ref)
    p = c.paused_ask
    try:
        k = parse_answer(text) if p else None
        if k is not None and p["form"] != "words":
            _answer(c, p, k)
        else:
            _words(c, p, text)
    except SayError:
        raise
    except W.AskError as exc:
        raise SayError(400 if exc.code == "EMPTY_ANSWER" else 409, {"code": exc.code}) from exc
    except J.J2Error as exc:
        code = str(exc).split(":", 1)[0]
        raise SayError(CODES.get(code, 409), {"code": code}) from exc
    except ValueError as exc:
        raise SayError(400, {"error": str(exc)}) from exc
    finally:
        C.touch(ref)                                          # the owner's own words show at once
    return {"ok": True}


def say_http(ref, text):
    """say as (status, body): what the route answers."""
    try:
        return 200, say(ref, text)
    except SayError as exc:
        return exc.status, exc.body


def reset(ref):
    """A new run: a department is long-lived and has one live cycle, so there is nothing to start over. The page reloads."""
    return 409, {"ok": False}


def output(ref, body):
    """The output type: a department is a website team."""
    return 409, {"ok": False, "output": "website"}


def clear(ref, kind):
    """Clear memory or playbooks: memory is off, so the page never shows these buttons. Nothing is cleared."""
    return 409, {"ok": False, "cleared": 0}
