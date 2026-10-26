"""test_j2ui_chat.py -- the chat list the J2 page reads (j2ui_chat.py; UI port step C2).

Named claims:
  C2-1  the owner's side comes from chat_view, so after owner_ask(root, text, about=dept) there is exactly one `user` message with
        that text and none attributed to the validator; the first words and the follow-up are both `user` messages, in time order;
        the words Root hands on are not said again; Root's post 8 and the department's post 8 are two messages
  C2-2  the validator speaks only for the ledger's workflow.validated / registered / blocked events, and carries `register` as said
  C2-3  a function's post to another reads as the act in the owner's words (Said yes to the plan: ...), never the bare payload,
        GRANT, COUNTER, REFUSE or an act id
  C2-4  every kind of ask is one message from Identity (who identity, to_user, act ASK_REQUESTER, the right pause) whose text the
        page's own parseAsk reads: linked by card (Identity's question, a blocked plan), by thread (the rest, two publish asks at
        once are two messages), or a message of its own (an ask no post says); no plain duplicate of a post an ask stands for
  C2-5  the owner's answers: a stamp reads Option 1 / Option 2, a choice on an options ask Option k of the options shown, Identity's
        question answered reads the words; an answer is never said twice
  C2-6  the options an ask showed are the ones 'Option k' means, whatever the live list says later (Stop dropped on a stopped one)
  C2-7  ids never move: a later post with an older time takes the next id; two builds with no change are equal; eight threads
        building at once make no duplicate or reordered id; a replaced ask's message stays
  C2-8  words quoted in an ask cannot forge an option or a numbered question; to_user is true only for Identity
"""
import json
import re
import subprocess
import threading

import pytest

from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403

import j2ui_chat as CH
import j2ui_common as C

PAUSES = {"publish": "approval", "envelope": "limit", "rule": "approval", "finding": "audit", "conflict": "conflict", "line": "approval",
          "engine": "approval", "instructions": "approval", "rung": "approval", "alarm": "limit", "model": "limit", "request": "approval",
          "done_items": "approval", "step": "approval"}


def parse_ask(text):
    """The page's parseAsk (j2_ui.html), its two regexes and its one unnumbered-question rule."""
    qs, say = [], []
    for line in text.split("\n"):
        m = re.match(r"^(\d+)\. (.*)$", line)
        if m:
            qs.append({"q": m.group(2), "opts": []})
            continue
        m = re.match(r"^\s+Option \d+: (.*?)(?: \[adds \d+ (?:units|work credits)[^\]]*\])?$", line)
        if m and qs:
            qs[-1]["opts"].append(m.group(1))
            continue
        if re.match(r"^\s+Option \d+: ", line) and not qs:
            q = say.pop() if say and not re.match(r"^-|^Still not right|^Some parts|^I couldn't tell", say[-1]) else ""
            qs.append({"q": q, "opts": [re.sub(r"^\s+Option \d+: ", "", line)]})
            continue
        if not qs:
            say.append(line)
    return {"say": "\n".join(say), "qs": qs}


def chat(m, ref=REF):
    C.touch(ref)
    return C.get_ctx(ref)


def users(c):
    return [x for x in c.chat if x["who"] == "user"]


def asks_of(c):
    return [x for x in c.chat if x.get("act") == "ASK_REQUESTER"]


def test_c20_the_helpers_of_functions_view_that_the_chat_reuses_exist():
    """The acts and their words come from functions_view, so the chat, the Timeline and Conflicts agree; a package that renames
    them breaks the chat, and this says so first."""
    import functions_view as F
    for name in ("_did", "_said", "_short", "_cap"):
        assert callable(getattr(F, name, None)), name
    assert F._cap("said yes to the plan") == "Said yes to the plan" and F._short("x" * 300).endswith("…") and len(F._short("x" * 300)) == 140


# ---- C2-1: the owner's side ------------------------------------------------------------------------------------------
def test_c21_a_follow_up_through_root_is_one_user_message_and_no_validator(mods, born, tick):
    ref = born()
    W = mods.W
    W.owner_ask(born.root, "Add a page about our pricing plans", about=ref)
    W.run_until_idle(born.root, limit=300)
    W.run_until_idle(ref, limit=300)
    C.reset_caches()
    c = C.get_ctx(ref)
    texts = [x["text"] for x in users(c)]
    assert texts == [WEBSITE, "Add a page about our pricing plans"], texts
    assert [x["who"] for x in c.chat if "pricing plans" in x["text"]] == ["user"], "the words Root hands on are not said again"
    assert not [x for x in c.chat if x["who"] == "validator" and ("pricing" in x["text"] or x["text"] == WEBSITE)]
    assert {x["who"] for x in c.chat} <= {"user", "identity", "adaptation", "priority", "coordination", "audit", "validator"}
    # time order: the first words, then the follow-up
    first, again = users(c)
    assert first["id"] < again["id"]
    # post numbers restart on every board: Root's post 8 and the department's post 8 are two messages
    root_n, dept_n = {p["n"] for p in c.root_posts}, {p["n"] for p in c.posts}
    both = sorted(root_n & dept_n)
    assert both, "both boards have posts of the same number"
    n = both[-1]
    assert c.msg_of.get(("r", n)) and c.msg_of.get(("b", n)) and c.msg_of[("r", n)] != c.msg_of[("b", n)]


def test_c21_what_identity_says_of_a_stamp_comes_after_the_stamp_even_within_one_second(mods, born):
    """Records are stamped to the second and Publish is code: the stamp and 'Live site v1 is live' share a second. The reply is on Root's
    board (read first) and has its twin on the department's, after the stamp, and that is the place it takes."""
    ref = born()
    W = mods.W
    a = next(x for x in W.asks(ref) if x["kind"] == "publish" and x["status"] == "pending")
    W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    C.reset_caches()
    c = C.get_ctx(ref)
    live = next(x for x in c.chat if "is live" in x["text"])
    stamp = [x for x in users(c) if x["text"] == "Option 1"]
    assert len(stamp) == 1 and stamp[0]["id"] < live["id"], [(x["id"], x["who"], x["text"][:30]) for x in c.chat[-4:]]
    ask_msg = c.ask_msg[a["id"]]
    assert ask_msg < stamp[0]["id"], "and the question comes before its answer"


def test_c21_ids_are_places_in_the_list_and_never_change(mods, born, tick):
    ref = born()
    c1 = chat(mods, ref)
    assert [x["id"] for x in c1.chat] == list(range(1, len(c1.chat) + 1))
    before = {x["id"]: (x["who"], x["text"]) for x in c1.chat}
    mods.W.owner_ask(born.root, "Make the logo bigger", about=ref)
    mods.W.run_until_idle(born.root, limit=300)
    mods.W.run_until_idle(ref, limit=300)
    c2 = chat(mods, ref)
    assert len(c2.chat) > len(c1.chat)
    assert {x["id"]: (x["who"], x["text"]) for x in c2.chat if x["id"] in before} == before
    assert c2.chat[-1]["id"] == len(c2.chat)


# ---- C2-2 and C2-3: the validator, and the functions' acts ---------------------------------------------------------------
def test_c22_the_validator_speaks_only_for_the_ledger(mods):
    cycle(mods, "running", 5)
    event(mods, "workflow.validated", summary="The workflow meets Sutra's standards.")
    event(mods, "workflow.registered", recipient="Coordination", summary="Registered Plan -> Write on the department's record, version 1.")
    event(mods, "workflow.blocked", summary="Root's check refused the workflow: Plan has no reader.", key="b1")
    event(mods, "proposal.granted", actor="Priority", step=3, summary="fits today")
    post(mods, "Root", "Adaptation", "refuse", {"word": "line", "why": "a post from Root is not the validator"})
    c = chat(mods)
    v = [x for x in c.chat if x["who"] == "validator"]
    assert [(x["register"] if "register" in x else None, x["next"]) for x in v] == [(None, "adaptation"), (True, "coordination"), (False, "adaptation")]
    assert "refused" not in v[2]["text"] and "sent the plan back" in v[2]["text"], "in the owner's words"
    assert all(x["step"] == 5 for x in v) and not [x for x in c.chat if x["who"] == "validator" and "Root" in x["text"] and "post from Root" in x["text"]]
    assert len(c.chat) == 3, "the Root post and the Priority event are not messages of the validator, nor of anyone"


def test_c23_a_function_to_function_message_is_the_act_in_the_owners_words(mods):
    thread(mods, "Identity", "Adaptation", "request", "line", tid="x-a", words="Make a site for a florist")
    thread(mods, "Adaptation", "Priority", "propose", "line", tid="x-a", words="Make a site for a florist")
    thread(mods, "Priority", "Adaptation", "accept-proposal", "line", tid="x-a", why="fits today: about 3 calls")
    thread(mods, "Priority", "Adaptation", "propose", "line", tid="x-b", why="the room is smaller")
    thread(mods, "Priority", "Adaptation", "reject-proposal", "line", tid="x-c", why="no room at all")
    got = [(x["who"], x["text"], x.get("next"), x.get("audience")) for x in chat(mods).chat]
    assert got[0] == ("identity", "Asked Adaptation for the plan: Make a site for a florist", "adaptation", "adaptation")
    assert got[1] == ("adaptation", "Proposed the plan to Priority: Make a site for a florist", "priority", "priority")
    assert got[2] == ("priority", "Said yes to the plan: fits today: about 3 calls", "adaptation", "adaptation")
    assert got[3][1].startswith("Asked Adaptation for less: the room is smaller")
    assert got[4][1].startswith("Said no to the plan: no room at all")
    text = json.dumps(got)
    for bad in ("GRANT", "COUNTER", "REFUSE", "accept-proposal", "reject-proposal", "grant", "counter"):
        assert bad not in text, bad
    assert all("to_user" not in x for x in chat(mods).chat), "a function's post is not for the owner"


def test_c23_an_engines_post_is_said_by_its_w_k(mods):
    post(mods, "Plan", "Check", "inform", {"word": "plan", "done": "six pages"})
    c = chat(mods)
    assert [(x["who"], x["next"]) for x in c.chat] == [("W-1", "W-3")] and c.chat[0]["audience"] == "W-3"


# ---- C2-4: every kind of ask ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", sorted(k for k in PAUSES if k != "step"))
def test_c24_a_thread_linked_ask_is_one_message_the_page_can_parse(mods, kind):
    a = stamp_ask(mods, kind, text="%s: the question to put" % kind.title())
    c = chat(mods)
    got = asks_of(c)
    assert len(got) == 1 and len(c.chat) == 1, "the post that says the ask is the ask: no plain duplicate bubble, no virtual message"
    m = got[0]
    assert (m["who"], m["to_user"], m["act"], m["pause"], m["next"]) == ("identity", True, "ASK_REQUESTER", PAUSES[kind], "user")
    p = parse_ask(m["text"])
    assert len(p["qs"]) == 1 and p["qs"][0]["opts"] == ["Stamp", "Say no"] and p["qs"][0]["q"].endswith("the question to put")
    assert m["text"].startswith("@Requester ") and "\n   Option 1: Stamp\n   Option 2: Say no" in m["text"]
    assert c.ask_msg == {a["id"]: m["id"]} and c.ask_opts == {m["id"]: ["approve", "refuse"]}
    assert c.msg_of[("b", 1)] == m["id"]


def test_c24_two_publish_asks_at_once_are_two_messages(mods):
    for i in (1, 2):
        ask(mods, "publish", id="a-pub%d" % i, thread="x-pub%d" % i, text="Publish: go live, version %d" % i)
        thread(mods, "Identity", "Owner", "request", "publish", tid="x-pub%d" % i, objective="say whether the site may go live",
               about={"art": "Build", "v": i})
    c = chat(mods)
    got = asks_of(c)
    assert len(got) == 2 and len(c.chat) == 2 and got[0]["id"] != got[1]["id"]
    assert [x["text"].split("\n")[0] for x in got] == ["@Requester Publish: go live, version 1", "@Requester Publish: go live, version 2"]
    assert c.ask_msg == {"a-pub1": got[0]["id"], "a-pub2": got[1]["id"]}


def test_c24_an_ask_no_post_says_is_a_message_of_its_own(mods):
    a = ask(mods, "step", id="a-step", engine="Write", text="Write the pricing page by hand", created=mods.W.now())
    c = chat(mods)
    m = asks_of(c)[0]
    assert len(c.chat) == 1 and c.msg_of == {("a", "a-step"): m["id"]} and m["pause"] == "approval"
    assert parse_ask(m["text"])["qs"][0]["q"].endswith("Write the pricing page by hand")
    assert a["id"] in c.ask_msg


def test_c24_identitys_question_is_a_card_and_takes_words(mods):
    q = mods.W.j2_identity_ask("What is the site for, and about whom?", "cycle-test", "words", "Your words name nothing to build from yet.")
    mods.W._put_ask(REF, q)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    c = chat(mods)
    m = asks_of(c)[0]
    assert len(c.chat) == 1 and m["pause"] == "info" and c.msg_of == {("b", 1): m["id"]}
    assert m["text"] == "@Requester Your words name nothing to build from yet.\nWhat is the site for, and about whom?"
    assert parse_ask(m["text"])["qs"] == [] and c.ask_opts == {}, "no option lines: the owner types"
    # without a why, one line
    q2 = mods.W.j2_identity_ask("What evidence proves it is done?", "cycle-test", "done-when", "")
    mods.W._put_ask(REF, q2)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q2["text"], "card": q2["id"]}, thread="x-q2")
    assert asks_of(chat(mods))[1]["text"] == "@Requester What evidence proves it is done?"


def test_c24_a_blocked_plan_is_a_card_with_its_options(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"], done=a["text"])
    c = chat(mods)
    m = asks_of(c)[0]
    assert len(c.chat) == 1 and m["pause"] == "limit" and c.msg_of == {("b", 1): m["id"]}
    p = parse_ask(m["text"])
    assert p["say"] == "@Requester The plan could not be set up." and len(p["qs"]) == 1
    assert p["qs"][0]["q"] == "The plan could not be set up: Check has no reader."
    assert p["qs"][0]["opts"] == ["Change the plan in my words (Adaptation shapes it afresh)", "Leave D2 out (D2 is dropped from done-when)",
                                  "Stop here (the department stops where it is)"]
    assert c.ask_opts == {m["id"]: ["words", "leave:D2", "stop"]}


def test_c24_a_stopped_department_is_shown_no_stop_option(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    d = mods.W.dept(REF)
    d["stopped"] = True
    mods.W.save_dept(REF, d)
    c = chat(mods)
    assert c.ask_opts[asks_of(c)[0]["id"]] == ["words", "leave:D2"] and "Stop here" not in asks_of(c)[0]["text"]


# ---- C2-5: the owner's answers --------------------------------------------------------------------------------------------
def test_c25_a_stamp_reads_option_1_or_2(mods):
    stamp_ask(mods, "publish")
    stamp_ask(mods, "rule", tid="x-rule")
    post(mods, "Owner", "Identity", "accept-proposal", {"word": "publish", "ask": "a-publish"}, thread="x-publish")
    post(mods, "Owner", "Identity", "reject-proposal", {"word": "rule", "ask": "a-rule"}, thread="x-rule")
    c = chat(mods)
    assert [x["text"] for x in users(c)] == ["Option 1", "Option 2"] and len(asks_of(c)) == 2 and len(c.chat) == 4
    # an ask decided with no post (no thread) still shows the owner's answer
    ask(mods, "step", id="a-hand", engine="Write", text="Write it by hand")
    a = mods.W.asks(REF)[-1]
    mods.W.decide_ask(REF, a["id"], True)
    assert [x["text"] for x in users(chat(mods))][-1] == "Option 1"


def test_c25_a_choice_on_an_options_ask_reads_the_option_number(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    mods.W.choose_option(REF, a["id"], "leave:D2")
    c = chat(mods)
    assert [x["text"] for x in users(c)] == ["Option 2"] and c.msg_of[("x", a["id"])] == c.chat[-1]["id"]
    assert len(c.chat) == 2 and c.chat[0]["act"] == "ASK_REQUESTER"


def test_c25_the_words_option_is_the_owners_words_once(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    mods.W.choose_option(REF, a["id"], "words", "Make it three pages")
    c = chat(mods)
    assert [x["text"] for x in users(c)] == ["Make it three pages"], "the words option reads the words, not Option 1"
    # and when the words also stand as a turn of the owner's own, they are not said twice
    post(mods, "Owner", "Identity", "request", {"word": "request", "words": "Make it three pages", "answers": a["id"]}, thread="x-w")
    assert [x["text"] for x in users(chat(mods))] == ["Make it three pages"]


def test_c25_identitys_question_answered_reads_the_words(mods):
    q = mods.W.j2_identity_ask("What evidence proves it is done?", "cycle-test", "done-when", "")
    mods.W._put_ask(REF, q)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    q.update(status="stamped", decided=mods.W.now(), by="the owner", answered="Every page has a phone number on it")
    mods.W._put_ask(REF, q)
    c = chat(mods)
    assert [x["who"] for x in c.chat] == ["identity", "user"] and c.chat[1]["text"] == "Every page has a phone number on it"
    assert c.chat[0]["id"] == c.ask_msg[q["id"]]


# ---- C2-6: the options an ask showed -----------------------------------------------------------------------------------------
def test_c26_the_first_options_shown_are_the_ones_option_k_means(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    first = asks_of(chat(mods))[0]
    d = mods.W.dept(REF)
    d["stopped"] = True
    mods.W.save_dept(REF, d)
    c = chat(mods)
    now = asks_of(c)[0]
    assert now["id"] == first["id"] and now["text"] == first["text"], "the message the page was given does not change under it"
    assert c.ask_opts[now["id"]] == ["words", "leave:D2", "stop"], "Option 3 still means Stop; the writer will say it is no longer offered"
    assert [o["id"] for o in mods.W.offered(mods.W.dept(REF), mods.W.asks(REF)[0])] == ["words", "leave:D2"]


# ---- C2-7: ids that never move -------------------------------------------------------------------------------------------------
def test_c27_a_post_with_an_older_time_takes_the_next_id(mods, tick):
    post(mods, "Identity", "Adaptation", "request", {"word": "line", "words": "first"}, thread="x-1")
    post(mods, "Identity", "Adaptation", "request", {"word": "line", "words": "second"}, thread="x-1")
    c1 = chat(mods)
    ids = {x["text"]: x["id"] for x in c1.chat}
    row = post(mods, "Adaptation", "Priority", "propose", {"word": "line", "words": "late"}, thread="x-1")
    # the same post, written again with a time before the others, as a clock that stepped back would
    rows = mods.R.board(REF)
    rows[-1]["at"] = "2000-01-01T00:00:00+00:00"
    p = mods.W.ddir(REF) / "board.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    c2 = chat(mods)
    assert {x["text"]: x["id"] for x in c2.chat if x["text"] in ids} == ids
    assert c2.chat[-1]["text"].endswith("late") and c2.chat[-1]["id"] == 3 and row


def test_c27_two_builds_with_no_change_are_equal(mods):
    stamp_ask(mods, "publish")
    thread(mods, "Identity", "Adaptation", "request", "line", tid="x-a", words="go")
    a, b = chat(mods).chat, chat(mods).chat
    assert a == b and a is not b


def test_c27_eight_threads_building_at_once_make_no_duplicate_or_reordered_id(mods):
    stamp_ask(mods, "publish")
    for i in range(20):
        thread(mods, "Identity", "Adaptation", "request", "line", tid="x-%d" % i, words="w%d" % i)
    C.get_ctx(REF)
    outs, errs = [], []

    def build():
        try:
            c = C.get_ctx(REF)
            outs.append(CH.build(c))
        except Exception as exc:  # noqa: BLE001
            errs.append(exc)
    ts = [threading.Thread(target=build) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(outs) == 8
    first = outs[0][0]
    assert all(o[0] == first for o in outs) and [x["id"] for x in first] == list(range(1, len(first) + 1))
    assert len({x["id"] for x in first}) == len(first) == 21


def test_c27_a_replaced_asks_message_stays_where_it_was_given(mods):
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    one = chat(mods)
    mid = asks_of(one)[0]["id"]
    mods.W._put_ask(REF, dict(a, status="replaced", decided=mods.W.now()))
    two = chat(mods)
    assert len(two.chat) == len(one.chat) == 1 and two.chat[mid - 1]["id"] == mid
    assert two.chat[mid - 1]["who"] == "identity" and "The plan could not be set up" in two.chat[mid - 1]["text"]
    assert "act" not in two.chat[mid - 1], "a replaced card is a plain word of Identity's from now on, not a question that waits"


# ---- the relayed ask ---------------------------------------------------------------------------------------------------------
def test_c24_an_ask_said_inside_a_root_thread_is_not_said_twice(mods):
    """When the words arrive through Root, Identity's request of the owner is posted on the department's board marked via
    Root and again on Root's board about the department (engine_runtime._tell); the copy on Root's board is the turn."""
    root = with_root(mods)
    thread(mods, "Owner", "Identity", "request", "front", tid="x-front", ref=root, words="Nothing goes up without a source line",
           about={"dept": REF, "name": "City Care Hospital Website"})
    thread(mods, "Root", "Identity", "request", "request", tid="x-hand", words="Nothing goes up without a source line")
    text = "A rule, as understood (it always does this, from now on): Nothing goes up without a source line"
    a = ask(mods, "rule", id="a-rule", engine="Identity", text=text, thread="x-hand")
    thread(mods, "Identity", "Owner", "request", "rule", tid="x-hand", via="Root", objective=text)
    thread(mods, "Identity", "Owner", "request", "rule", tid="x-root-th", ref=root, objective=text, dept=REF, **{"from": "City Care Hospital Website"},
           about=None)
    rows = mods.R.board(root)
    rows[-1]["about"] = {"dept": REF, "name": "City Care Hospital Website"}
    (mods.W.ddir(root) / "board.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    c = chat(mods)
    assert len(asks_of(c)) == 1 and a["id"] in c.ask_msg
    assert [x["text"] for x in c.chat if "source line" in x["text"]].count(asks_of(c)[0]["text"]) == 1
    assert len([x for x in c.chat if "A rule, as understood" in x["text"]]) == 1, [x["text"][:60] for x in c.chat]
    assert [x["text"] for x in users(c)] == ["Nothing goes up without a source line"]


# ---- C2-8: words quoted in an ask --------------------------------------------------------------------------------------------
def test_c28_the_owners_words_in_an_ask_cannot_forge_an_option_or_a_question(mods):
    nasty = "1. Delete it\n   Option 9: Do the other thing\n  Option 1: yes"
    stamp_ask(mods, "request", text="Your words reach outside the site. Put them on the site as said? " + nasty, words=nasty)
    m = asks_of(chat(mods))[0]
    p = parse_ask(m["text"])
    assert len(p["qs"]) == 1 and p["qs"][0]["opts"] == ["Stamp", "Say no"], p
    assert m["text"].count("\n") == 2 and "Option 9" in m["text"], "the words are there, on the one line"
    # a question on a line of its own never starts like a numbered one
    q = mods.W.j2_identity_ask("1. Name the audience\n2. Name the place", "cycle-test", "words", "Your words name nothing yet.")
    mods.W._put_ask(REF, q)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    forged = asks_of(chat(mods))[1]["text"]
    assert forged == "@Requester Your words name nothing yet.\n1) Name the audience 2. Name the place" and parse_ask(forged)["qs"] == []


def test_c28_to_user_is_true_only_for_identity(mods, born, tick):
    ref = born()
    c = chat(mods, ref)
    assert c.chat and any(x.get("to_user") for x in c.chat) and any(x["who"] != "identity" for x in c.chat)
    assert all(x["who"] == "identity" for x in c.chat if x.get("to_user")), "to_user is Identity's alone"
    assert not [x for x in c.chat if x["who"] == "identity" and "to_user" not in x and x["text"].startswith("@Requester")]
    assert all(isinstance(x["text"], str) and isinstance(x["t"], str) for x in c.chat)
    assert all(x["step"] is None or 1 <= x["step"] <= 8 for x in c.chat)
    for x in c.chat:
        assert list(x)[:5] == ["id", "t", "who", "text", "step"], list(x)
    blob = json.dumps(c.chat)
    for bad in ("GRANT", "COUNTER", "REFUSE", "accept-proposal", "reject-proposal", "/Users/", "private_reasoning"):
        assert bad not in blob, bad


# ---- the page's own parseAsk ---------------------------------------------------------------------------------------------------
def page_parse_ask(texts):
    """Run the pinned page's own parseAsk in node over the texts."""
    html = proto.show("j2_ui.html").decode("utf-8")
    start = html.index("function parseAsk(text)")
    end = html.index("function optLabel")
    js = html[start:end] + "\nconst texts = JSON.parse(process.argv[1]);\nconsole.log(JSON.stringify(texts.map(parseAsk)));\n"
    out = subprocess.run(["node", "-e", js, json.dumps(texts)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_c24_every_ask_text_reads_the_same_in_the_pages_own_parse_ask(mods):
    if proto.skip_reason():
        pytest.skip(proto.skip_reason())
    for kind in PAUSES:
        if kind != "step":
            stamp_ask(mods, kind, tid="x-" + kind, text="%s: the question to put" % kind.title())
    a = blocked(mods)
    card_post(mods, a, objective=a["text"])
    q = mods.W.j2_identity_ask("What is the site for?", "cycle-test", "words", "Your words name nothing yet.")
    mods.W._put_ask(REF, q)
    post(mods, "Identity", "Owner", "inform", {"word": "question", "done": q["text"], "card": q["id"]}, thread="x-q")
    texts = [x["text"] for x in asks_of(chat(mods))]
    assert len(texts) == len(PAUSES) - 1 + 2
    for text, js in zip(texts, page_parse_ask(texts)):
        mine = parse_ask(text)
        assert js == {"say": mine["say"], "qs": mine["qs"]}, text
