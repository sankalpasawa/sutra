"""test_j2ui_say.py -- the owner's words, routed to the writers that already exist (j2ui_say.py; UI port step C4).

Named claims:
  C4-1  'Option k' on an options ask chooses the k-th option the owner was SHOWN, even when the live list has changed since (Stop
        dropped on a stopped department); an option no longer offered is 409 UNKNOWN_OPTION; no such option is 400
  C4-2  'Option 1' / 'Option 2' on a stamp ask stamp and say no; 'Option 3' is 400; '1. Option 2' with one ask is an answer and
        '2. Option 1' is words; with nothing waiting a bare answer ('Option 1', '2', '1. Option 2') is refused 409 NO_PENDING_ASK and
        writes nothing (a double click or a click in the poll gap), while free words are still a request; a repeat of the answer just
        given, inside the rebuild floor, never answers the next ask (409 ALREADY_HANDLED)
  C4-3  words go where the Chat sends them: Identity's open question takes j2_runtime.answer; an options ask that offers the words
        option takes them; anything else is owner_ask on Root about this department (a department with no Root takes them itself);
        end to end on a Root and a department the next state shows exactly one more user message
  C4-4  blank words raise Empty; the writers' refusals are mapped (AskError, J2Error, ValueError) to the status and body the page's
        server would give; nothing is ever refused because work is running
  C4-5  reset, output and clear answer 409 and leave every file of the department byte-identical
"""
import hashlib
import os

import pytest

from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403

import j2ui_common as C
import j2ui_say as SAY
import j2ui_state as S


class Spies:
    """Record the calls the writers get, answering as the real ones would not need to (they are tested elsewhere)."""

    def __init__(self, m, monkeypatch, **replies):
        self.calls = []
        for obj, name in ((m.W, "choose_option"), (m.W, "decide_ask"), (m.W, "owner_ask"), (m.J, "answer")):
            monkeypatch.setattr(obj, name, self._spy(name, replies.get(name)))

    def _spy(self, name, reply):
        def spy(*a, **k):
            self.calls.append((name, a, k))
            if isinstance(reply, BaseException):
                raise reply
            return reply
        return spy

    def names(self):
        return [c[0] for c in self.calls]


def dir_hash(m):
    h = hashlib.sha256()
    for root, dirs, files in os.walk(m.home):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            h.update(p.encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


def blocked_with_stop_first(m):
    """An options ask whose Stop comes first, so that dropping it shifts every number after it."""
    opts = [m.W.option("stop", "Stop here", "the department stops where it is"), m.W.option("words", "Change the plan in my words", "afresh"),
            m.W.option("leave:D2", "Leave D2 out", "D2 is dropped")]
    a = m.W.options_ask("blocked", "The plan could not be set up.", opts, title="The plan could not be set up.", why="x", thread="x-blocked")
    m.W._put_ask(REF, a)
    card_post(m, a, objective=a["text"])
    return a


# ---- C4-1: options asks ------------------------------------------------------------------------------------------------------
def test_c41_option_k_is_the_kth_option_shown_even_when_the_live_list_changed(mods, monkeypatch):
    a = blocked_with_stop_first(mods)
    d = mods.W.dept(REF)
    d["stopped"] = True
    mods.W.save_dept(REF, d)
    C.touch(REF)
    assert C.get_ctx(REF).ask_opts[next(iter(C.get_ctx(REF).ask_opts))] == ["words", "leave:D2"], "shown with Stop dropped"
    d["stopped"] = False
    mods.W.save_dept(REF, d)
    assert [o["id"] for o in mods.W.offered(mods.W.dept(REF), mods.W.asks(REF)[0])] == ["stop", "words", "leave:D2"], "live: Stop is first again"
    spies = Spies(mods, monkeypatch)
    assert SAY.say(REF, "Option 2") == {"ok": True}
    assert spies.calls == [("choose_option", (REF, a["id"], "leave:D2"), {})], "the second shown, not the second live"


def test_c41_an_option_no_longer_offered_is_unknown_and_no_such_option_is_400(mods):
    a = mods.W.options_ask("blocked", "Stuck.", [mods.W.option("words", "In my words", "x"), mods.W.option("stop", "Stop here", "x")], title="Stuck.",
                           thread="x-blocked")
    mods.W._put_ask(REF, a)
    card_post(mods, a, objective=a["text"])
    C.touch(REF)
    C.get_ctx(REF)                                             # the page was given both options
    d = mods.W.dept(REF)
    d["stopped"] = True
    mods.W.save_dept(REF, d)
    with pytest.raises(SAY.SayError) as e:
        SAY.say(REF, "Option 2")
    assert (e.value.status, e.value.body) == (409, {"code": "UNKNOWN_OPTION"})
    assert SAY.say_http(REF, "Option 7") == (400, {"error": "no such option"}) and SAY.say_http(REF, "Option 0") == (400, {"error": "no such option"})
    assert mods.W.asks(REF)[0]["status"] == "pending", "nothing was chosen"


def test_c41_choosing_for_real_applies_the_choice_and_the_words_option_needs_words(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    assert SAY.say_http(REF, "Option 1") == (400, {"code": "EMPTY_ANSWER"}), "the words option needs the owner's words"
    assert SAY.say_http(REF, "Option 2")[0] == 200
    assert mods.W.asks(REF)[0]["status"] == "chosen" and mods.W.asks(REF)[0]["chosen"]["id"] == "leave:D2"
    # nothing waits now, so a later 'Option 3' answers nothing: it is refused, not sent on as the owner's request; the answered ask stays answered
    before = dir_hash(mods)
    assert SAY.say_http(REF, "Option 3") == (409, {"code": "NO_PENDING_ASK"}) and mods.W.asks(REF)[0]["chosen"]["id"] == "leave:D2"
    assert dir_hash(mods) == before, "and nothing was written"


def test_c41_the_words_option_takes_typed_words(mods, monkeypatch):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "Make it three pages")
    assert spies.calls == [("choose_option", (REF, a["id"], "words", "Make it three pages"), {})]


# ---- C4-2: stamp asks --------------------------------------------------------------------------------------------------------
def test_c42_a_stamp_is_option_1_and_no_is_option_2(mods, monkeypatch):
    stamp_ask(mods, "publish")
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "Option 1")
    SAY.say(REF, "option 2")
    SAY.say(REF, " 2 ")
    assert [(c[0], c[1][1:]) for c in spies.calls] == [("decide_ask", ("a-publish", True)), ("decide_ask", ("a-publish", False)),
                                                        ("decide_ask", ("a-publish", False))]
    assert SAY.say_http(REF, "Option 3") == (400, {"error": "no such option"}) and len(spies.calls) == 3


def test_c42_a_numbered_answer_is_an_answer_only_for_the_first_question(mods, monkeypatch):
    root = with_root(mods)
    stamp_ask(mods, "publish")
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "1. Option 2")
    assert spies.names() == ["decide_ask"] and spies.calls[0][1][2] is False
    SAY.say(REF, "2. Option 1")
    SAY.say(REF, "Option 1; Option 2")
    SAY.say(REF, "Option one")
    assert spies.names() == ["decide_ask", "owner_ask", "owner_ask", "owner_ask"], "words, not answers"
    assert spies.calls[1][1] == (root, "2. Option 1") and spies.calls[1][2] == {"about": REF}


def test_c42_parse_answer():
    for text, k in (("Option 2", 2), ("option2", 2), ("2", 2), ("1. Option 3", 3), ("1) 2", 2), ("Option 1.", 1), (" 1 : option 2 ", 2)):
        assert SAY.parse_answer(text) == k, text
    for text in ("2. Option 1", "Option 1; Option 2", "1. Option 1; 2. Option 2", "yes", "Option", "Option 1 please", "3 pages", ""):
        assert SAY.parse_answer(text) is None, text


# ---- C4-2b: an answer with nothing to answer ------------------------------------------------------------------------------------
BARE = ("Option 1", "Option 3", "option 2", "2", " 1 ", "1. Option 2", "2. Option 1", "1) 2", "Option 1.", "1. Option 1; 2. Option 2", "Option 1;")


@pytest.mark.parametrize("text", BARE)
def test_c42_a_bare_answer_with_nothing_waiting_is_refused_and_writes_nothing(mods, monkeypatch, text):
    """The page sends 'Option k' at once on a click, so a double click or a click inside the poll gap arrives after the ask was
    stamped; it must not become the owner's request."""
    with_root(mods)
    spies = Spies(mods, monkeypatch)
    before = dir_hash(mods)
    assert SAY.say_http(REF, text) == (409, {"code": "NO_PENDING_ASK"})
    with pytest.raises(SAY.SayError) as e:
        SAY.say(REF, text)
    assert (e.value.status, e.value.body) == (409, {"code": "NO_PENDING_ASK"})
    assert spies.calls == [] and dir_hash(mods) == before


def test_c42_free_words_with_nothing_waiting_are_still_a_request(mods, monkeypatch):
    root = with_root(mods)
    spies = Spies(mods, monkeypatch)
    for text in ("Add a page about pricing", "3 pages please", "Option one", "Option 1 please", "2 pages", "1. Option 1 and 2. Option 2", "Make it 2 columns"):
        assert SAY.say_http(REF, text) == (200, {"ok": True}), text
    assert spies.names() == ["owner_ask"] * 7 and spies.calls[0][1] == (root, "Add a page about pricing") and spies.calls[0][2] == {"about": REF}


def test_c42_a_number_is_an_answer_to_identitys_open_question_even_when_nothing_else_waits(mods, monkeypatch):
    """Identity's free-text question takes everything as words: '5' is the owner's answer to 'how many pages', not a stale click."""
    q = mods.W.j2_identity_ask("How many pages?", "cycle-test", "words", "")
    mods.W._put_ask(REF, q)
    cycle(mods, "waiting", 1, open_ask=q["id"])
    spies = Spies(mods, monkeypatch)
    assert SAY.say_http(REF, "5") == (200, {"ok": True}) and SAY.say_http(REF, "Option 2") == (200, {"ok": True})
    assert [(c[0], c[1][1]) for c in spies.calls] == [("answer", "5"), ("answer", "Option 2")]


def test_c42_a_double_click_on_stamp_stamps_once_and_the_second_click_changes_nothing(mods, born, tick):
    ref = born()
    before = S.build_state(C.get_ctx(ref))
    assert before["paused"] and before["paused"]["kind"] == "approval", "the first publish waits for a stamp"
    assert SAY.say_http(ref, "Option 1") == (200, {"ok": True})
    after_first = S.build_state(C.get_ctx(ref))
    assert SAY.say_http(ref, "Option 1") == (409, {"code": "NO_PENDING_ASK"}), "the stamp landed: nothing is waiting for a second one"
    after_second = S.build_state(C.get_ctx(ref))
    assert [(m["id"], m["who"], m["text"]) for m in after_second["chat"]] == [(m["id"], m["who"], m["text"]) for m in after_first["chat"]]
    assert [m["text"] for m in after_second["chat"] if m["who"] == "user"].count("Option 1") == 1, "one stamp, one bubble"
    assert after_second["total"] == after_first["total"] > before["total"]
    assert [a["status"] for a in mods.W.asks(ref) if a["kind"] == "publish"].count("stamped") == 1


def resolving(m, monkeypatch):
    """decide_ask that settles the ask in the record the way the real one does, and says what it was asked."""
    calls = []

    def decide(ref, aid, yes):
        calls.append((aid, yes))
        a = next(x for x in m.W.asks(ref) if x["id"] == aid)
        m.W._put_ask(ref, dict(a, status="stamped" if yes else "refused", decided=m.W.now()))
    monkeypatch.setattr(m.W, "decide_ask", decide)
    return calls


def test_c42_a_repeat_of_the_answer_just_given_never_answers_the_next_ask(mods, monkeypatch):
    """A double click, or a click in the poll gap, arrives after the first ask is stamped and the next one has appeared: the protocol
    carries no message id, so the repeat would answer the new ask. It is dropped (ALREADY_HANDLED) inside the rebuild floor."""
    now = [1_000_000.0]
    monkeypatch.setattr(C, "_now", lambda: now[0])
    stamp_ask(mods, "publish")
    stamp_ask(mods, "rule", tid="x-rule")
    calls = resolving(mods, monkeypatch)
    assert SAY.say_http(REF, "Option 1") == (200, {"ok": True}) and calls == [("a-publish", True)]
    now[0] += C.MIN_REBUILD_S / 2
    assert SAY.say_http(REF, "option 1") == (409, {"code": "ALREADY_HANDLED"}) and calls == [("a-publish", True)], "the new ask is not answered"
    assert [a["id"] for a in mods.W.asks(REF) if a["status"] == "pending"] == ["a-rule"]
    assert SAY.say_http(REF, "Option 2") == (200, {"ok": True}) and calls[-1] == ("a-rule", False), "another answer is the owner's own"
    now[0] += 5 * C.MIN_REBUILD_S
    stamp_ask(mods, "envelope", tid="x-env")
    assert SAY.say_http(REF, "Option 2") == (200, {"ok": True}) and calls[-1] == ("a-envelope", False), "and so is the same answer a moment later"


def test_c42_the_same_answer_to_the_same_ask_is_not_a_repeat(mods, monkeypatch):
    """Only an answer that would land on ANOTHER ask is dropped: while the ask is still there, an answer is the owner's."""
    now = [1_000_000.0]
    monkeypatch.setattr(C, "_now", lambda: now[0])
    stamp_ask(mods, "publish")
    spies = Spies(mods, monkeypatch)
    assert SAY.say_http(REF, "Option 2") == (200, {"ok": True}) and SAY.say_http(REF, "Option 2") == (200, {"ok": True})
    assert spies.names() == ["decide_ask", "decide_ask"]


# ---- C4-3: words ---------------------------------------------------------------------------------------------------------------
def test_c43_words_with_identitys_question_open_answer_it(mods, monkeypatch):
    q = mods.W.j2_identity_ask("What is the site for?", "cycle-test", "words", "Your words name nothing yet.")
    mods.W._put_ask(REF, q)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    cycle(mods, "waiting", 1, open_ask=q["id"])
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "A site for a florist in Jaipur")
    SAY.say(REF, "Option 1")                                   # Identity's question takes everything as words
    assert [(c[0], c[1]) for c in spies.calls] == [("answer", (REF, "A site for a florist in Jaipur", q["id"])), ("answer", (REF, "Option 1", q["id"]))]


def test_c43_identitys_question_is_answered_for_real_by_the_ledgers_own_writer(mods):
    """No spies: the department lives its J2 cycle, Identity asks, the owner's words close the ask and say so in the chat."""
    W, J, R = mods.W, mods.J, mods.R
    d = W.dept(REF)
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(REF, d)
    J.begin(REF)
    cur = J.asked(REF, "What evidence will prove this site is done?", ["done-when"], "Identity's standard is not met yet: done-when", standard=False)
    R.post(REF, "Identity", R.OWNER, "inform", {"word": "question", "done": "What evidence will prove this site is done?", "card": cur["open_ask"]})
    C.touch(REF)
    s = S.build_state(C.get_ctx(REF))
    assert s["paused"]["kind"] == "info" and s["status"] == "waiting" and s["paused"]["msg"] == 1 and s["chat"][0]["act"] == "ASK_REQUESTER"
    assert SAY.say(REF, "Every page has the phone number on it") == {"ok": True}
    ask_row = W.asks(REF)[0]
    assert ask_row["status"] == "stamped" and ask_row["answered"] == "Every page has the phone number on it"
    after = S.build_state(C.get_ctx(REF))
    assert after["paused"] is None and [m["text"] for m in after["chat"] if m["who"] == "user"] == ["Every page has the phone number on it"]
    assert after["chat"][0]["id"] == 1 and after["chat"][1]["who"] == "user", "the answer follows its question"
    assert SAY.say_http(REF, "And the opening hours")[0] == 200, "nothing is open now: new words are a request, never a refusal"


def test_c43_words_with_a_publish_ask_pending_go_to_roots_front_door(mods, monkeypatch):
    root = with_root(mods)
    stamp_ask(mods, "publish")
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "  Make the   headline bigger  ")
    assert spies.calls == [("owner_ask", (root, "Make the headline bigger"), {"about": REF})]


def test_c43_a_department_with_no_root_takes_the_words_itself(mods, monkeypatch):
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "Add a page for visiting hours")
    assert spies.calls == [("owner_ask", (REF, "Add a page for visiting hours"), {})]


def test_c43_end_to_end_the_next_state_shows_exactly_one_more_user_message(mods, born, tick):
    ref = born()
    W = mods.W
    before = S.build_state(C.get_ctx(ref))
    users = [m for m in before["chat"] if m["who"] == "user"]
    assert before["paused"] and before["paused"]["kind"] == "approval", "the first publish waits for a stamp"
    assert SAY.say(ref, "Add a page about our pricing plans") == {"ok": True}
    now = S.build_state(C.get_ctx(ref))
    mine = [m for m in now["chat"] if m["who"] == "user"]
    assert [m["text"] for m in mine] == [m["text"] for m in users] + ["Add a page about our pricing plans"], "at once, before the motor ran"
    assert now["total"] > before["total"] and [m["id"] for m in now["chat"][:before["total"]]] == [m["id"] for m in before["chat"]]
    W.run_until_idle(born.root, limit=300)
    W.run_until_idle(ref, limit=300)
    later = S.build_state(C.get_ctx(ref))
    assert [m["text"] for m in later["chat"] if m["who"] == "user"] == [m["text"] for m in mine], "and still one"
    # and a stamp, from the page's button
    assert later["paused"] and SAY.say(ref, "Option 1") == {"ok": True}
    W.run_until_idle(ref, limit=300)
    assert [a["status"] for a in W.asks(ref) if a["kind"] == "publish"].count("stamped") == 1
    final = S.build_state(C.get_ctx(ref))
    assert [m["text"] for m in final["chat"] if m["who"] == "user"][-1] == "Option 1"


# ---- C4-4: refusals ---------------------------------------------------------------------------------------------------------------
def test_c44_blank_words_are_empty(mods):
    for blank in ("", "   ", None, "\n\t"):
        with pytest.raises(SAY.Empty) as e:
            SAY.say(REF, blank)
        assert (e.value.status, e.value.body) == (400, {"error": "empty"})
    assert SAY.say_http(REF, " ") == (400, {"error": "empty"})


def test_c44_the_writers_refusals_are_mapped(mods, monkeypatch):
    q = mods.W.j2_identity_ask("What is the site for?", "cycle-test", "words", "")
    mods.W._put_ask(REF, q)
    cycle(mods, "waiting", 1, open_ask=q["id"])
    for err, want in ((mods.J.J2Error("NO_OPEN_QUESTION"), (409, {"code": "NO_OPEN_QUESTION"})),
                      (mods.J.J2Error("ALREADY_HANDLED"), (409, {"code": "ALREADY_HANDLED"})),
                      (mods.J.J2Error("NO_DEPARTMENT"), (404, {"code": "NO_DEPARTMENT"})),
                      (mods.J.J2Error("EMPTY_ANSWER"), (400, {"code": "EMPTY_ANSWER"})),
                      (mods.J.J2Error("INVALID_EVENT: step: missing"), (409, {"code": "INVALID_EVENT"})),
                      (ValueError("say what the website is for"), (400, {"error": "say what the website is for"}))):
        Spies(mods, monkeypatch, answer=err)
        assert SAY.say_http(REF, "words") == want, err
    stamp_ask(mods, "publish")
    cycle(mods, "running", 6)
    for err, want in ((mods.W.AskError("ALREADY_HANDLED"), (409, {"code": "ALREADY_HANDLED"})), (mods.W.AskError("EMPTY_ANSWER"), (400, {"code": "EMPTY_ANSWER"})),
                      (ValueError("that ask is already stamped"), (400, {"error": "that ask is already stamped"}))):
        Spies(mods, monkeypatch, decide_ask=err)
        assert SAY.say_http(REF, "Option 1") == want, err


def test_c44_nothing_is_refused_because_work_runs(mods, monkeypatch):
    cycle(mods, "running", 6)
    run(mods, "Write")
    stamp_ask(mods, "publish")
    spies = Spies(mods, monkeypatch)
    assert SAY.say_http(REF, "Option 1") == (200, {"ok": True}) and SAY.say_http(REF, "More photos please") == (200, {"ok": True})
    assert spies.names() == ["decide_ask", "owner_ask"]


def test_c44_a_long_text_is_cut_and_a_say_makes_the_next_read_fresh(mods, monkeypatch):
    spies = Spies(mods, monkeypatch)
    SAY.say(REF, "w " * 3000)
    assert len(spies.calls[0][1][1]) == SAY.TEXT_CHARS
    first = C.get_ctx(REF)
    assert C.get_ctx(REF) is first
    SAY.say(REF, "again")
    assert C.get_ctx(REF) is not first, "touch lifts the wait: the owner's own words show at once"


# ---- C4-5: the three that mean nothing ------------------------------------------------------------------------------------------------
def test_c45_reset_output_and_clear_change_nothing(mods):
    stamp_ask(mods, "publish")
    cycle(mods, "running", 6)
    C.get_ctx(REF)
    before = dir_hash(mods)
    assert SAY.reset(REF) == (409, {"ok": False})
    assert SAY.output(REF, {"type": "prd"}) == (409, {"ok": False, "output": "website"})
    assert SAY.clear(REF, "lessons") == (409, {"ok": False, "cleared": 0}) and SAY.clear(REF, "playbooks") == (409, {"ok": False, "cleared": 0})
    assert dir_hash(mods) == before
