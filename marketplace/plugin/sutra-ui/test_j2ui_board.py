"""test_j2ui_board.py -- the J2 page's Board tab, board/1, from questions.json (j2ui_board.py; UIPORT j2ui-views M5).

Named claims:
  M5a  no questions.json (or an empty, torn or odd one) is the empty board, and the tab stays hidden: entries [] and nothing
       raised; a file in wave 3's shape gives one page entry per row
  M5b  each entry has every key of the prototype's j2_board.new_entry, in its order; statuses are within STATUSES and roles
       within ROLES; an entry with another status, or no id, is dropped
  M5c  engine names are written as their workflow (W-k) in asked_by, to, answered_by, atom and used_by; a function is its
       lower-case id; asked_by_role is function for the five and builder for the rest; answered_from says where an answer
       came from, or is None
  M5d  the page's own renderBoard draws the entries (node, the pinned page); the Map draws asks and uses lines between the
       boxes of the engines that asked and answered
Shares the department fixtures and the Ctx stand-in of test_j2ui_artifacts.py.
"""
import json
import re

import pytest

from test_j2ui_artifacts import (REF, make_ctx, mods, page_render, plain_text, proto_board, proto_consts, seed_line)  # noqa: F401 -- mods is a fixture

#: the keys of j2_board.new_entry at the pin, copied (proto_board compares them when the prototype is here)
ENTRY_KEYS = ["id", "asked_by", "atom", "to", "about", "question", "answer", "answered_by", "status", "artifact_update", "used_by",
              "cycle", "attempt", "asked_by_role", "answered_from"]


def put_questions(W, rows, wrap=True):
    W._write(W.ddir(REF) / "questions.json", {"schema": "board/1", "entries": rows} if wrap else rows)


def q(i="Q-1", **more):
    """One coordination.question as W3-BOARD files it."""
    row = {"schema": "board/1", "id": i, "asked_by": "Write", "to": "Plan", "about": "the page list", "question": "Which pages does the site have?",
           "answer": None, "answered_by": None, "status": "open", "artifact_update": None, "used_by": [], "cycle": "cycle-test",
           "slot": "Write@site-plan.v1", "attempt": 1, "run": None}
    row.update(more)
    return row


@pytest.fixture
def line(mods):
    from test_j2ui_map import register
    seed_line(mods[0])
    register(mods[0], mods[1])
    return mods


# ---- M5a: absent, empty, odd ---------------------------------------------------------------------------------------------------------------
def test_m5a_no_file_is_the_empty_board(mods):
    import j2ui_board as B
    ctx = make_ctx(mods)
    assert B.build(ctx) == {"schema": "board/1", "entries": []}
    assert B.build(ctx) is B.build(ctx) and ctx.reasons == []


def test_m5a_an_empty_file_is_the_empty_board(mods):
    import j2ui_board as B
    put_questions(mods[0], [])
    assert B.build(make_ctx(mods)) == {"schema": "board/1", "entries": []}
    put_questions(mods[0], {"schema": "board/1", "entries": None}, wrap=False)
    assert B.build(make_ctx(mods))["entries"] == []


@pytest.mark.parametrize("raw", ["{not json", "[1, 2", "", "null", "7", '"text"', '{"entries": "x"}', '{"entries": {"a": 1}}', "[null, 3, \"x\", []]"])
def test_m5a_a_torn_or_odd_file_does_not_raise(mods, raw):
    import j2ui_board as B
    (mods[0].ddir(REF) / "questions.json").write_text(raw, encoding="utf-8")
    got = B.build(make_ctx(mods))
    assert got == {"schema": "board/1", "entries": []}
    json.dumps(got)


def test_m5a_a_list_file_is_read_as_the_entries(mods):
    import j2ui_board as B
    put_questions(mods[0], [q("Q-1"), q("Q-2")], wrap=False)
    assert [e["id"] for e in B.build(make_ctx(mods))["entries"]] == ["Q-1", "Q-2"]


# ---- M5b: the keys -----------------------------------------------------------------------------------------------------------------------
def test_m5b_an_entry_has_every_key_of_new_entry_in_its_order(mods):
    import j2ui_board as B
    put_questions(mods[0], [q()])
    e = B.build(make_ctx(mods))["entries"][0]
    assert list(e) == ENTRY_KEYS == list(B.KEYS)
    board = proto_board()
    if board is not None:
        assert list(e) == list(board.new_entry("Q-1", "W-1", "W-1.a1", "W-2", "x", "y?", "c", 1))
        assert board.SCHEMA == B.SCHEMA and tuple(board.STATUSES) == B.STATUSES and tuple(board.ROLES) == B.ROLES
    assert B.STATUSES == tuple(proto_consts("j2_board.py", "STATUSES") or B.STATUSES)


def test_m5b_statuses_and_roles_stay_inside_the_prototypes(mods):
    import j2ui_board as B
    statuses = ("open", "answered", "unanswered", "refused")
    put_questions(mods[0], [q("Q-%d" % (i + 1), status=s, asked_by=a) for i, (s, a) in enumerate(zip(statuses * 2, ["Write"] * 4 + ["Audit"] * 4))])
    entries = B.build(make_ctx(mods))["entries"]
    assert len(entries) == 8
    assert {e["status"] for e in entries} == set(statuses) <= set(proto_consts("j2_board.py", "STATUSES") or statuses)
    assert {e["asked_by_role"] for e in entries} == set(proto_consts("j2_board.py", "ROLES") or ("function", "builder"))


def test_m5b_an_entry_with_another_status_or_no_id_is_dropped(mods):
    import j2ui_board as B
    put_questions(mods[0], [q("Q-1", status="pending"), q("Q-2", status=None), q("", status="open"), {"status": "open"}, 5, q("Q-3")])
    ctx = make_ctx(mods)
    assert [e["id"] for e in B.build(ctx)["entries"]] == ["Q-3"]
    assert any("5 entries" in r or "entries the board does not show" in r for r in ctx.reasons)


def test_m5b_odd_values_are_read_as_the_prototype_reads_them(mods):
    import j2ui_board as B
    put_questions(mods[0], [q(attempt="x", used_by=None, cycle=5, about=None, artifact_update={}), q("Q-2", attempt=3, used_by=["Check", 4, ""])])
    one, two = B.build(make_ctx(mods))["entries"]
    assert (one["attempt"], one["used_by"], one["cycle"], one["about"], one["artifact_update"]) == (1, [], None, "", None)
    assert (two["attempt"], two["used_by"]) == (3, ["W-3"])


# ---- M5c: names and where an answer came from ------------------------------------------------------------------------------------------------
def test_m5c_engine_names_are_written_as_their_workflow(line):
    import j2ui_board as B
    put_questions(line[0], [q(asked_by="Write", to="Plan", answered_by="Plan", status="answered", answer="Home, About, Contact",
                              used_by=["Check", "Publish"], atom="Write")])
    e = B.build(make_ctx(line))["entries"][0]
    assert (e["asked_by"], e["to"], e["answered_by"], e["atom"], e["used_by"]) == ("W-2", "W-1", "W-1", "W-2", ["W-3", "W-4"])
    assert "Plan" not in json.dumps(e) and "Write" not in json.dumps(e)


def test_m5c_a_function_is_its_lower_case_id_and_the_role_is_function(line):
    import j2ui_board as B
    put_questions(line[0], [q(asked_by="Audit", to="Write", status="answered", answer="Yes", answered_by="Identity")])
    e = B.build(make_ctx(line))["entries"][0]
    assert (e["asked_by"], e["to"], e["answered_by"], e["asked_by_role"]) == ("audit", "W-2", "identity", "function")
    assert e["answered_from"] == {"function": "identity"}


def test_m5c_a_builder_asks_and_the_role_is_builder(line):
    import j2ui_board as B
    put_questions(line[0], [q()])
    e = B.build(make_ctx(line))["entries"][0]
    assert (e["asked_by_role"], e["status"], e["answer"], e["answered_by"], e["answered_from"]) == ("builder", "open", None, None, None)


def test_m5c_answered_from_names_the_workflow_and_the_version_it_filed(line):
    import j2ui_board as B
    put_questions(line[0], [q("Q-1", status="answered", answer="Home and About", answered_by="Plan", artifact_update={"art": "Site plan", "v": 2}),
                            q("Q-2", status="answered", answer="x", answered_by="Plan"),
                            q("Q-3", status="refused", answered_by="Plan"),
                            q("Q-4", status="answered", answer="y", answered_by="Root"),
                            q("Q-5", status="answered", answer="z", answered_by="Plan", answered_from={"workflow": "Plan", "version": 4})])
    got = {e["id"]: e["answered_from"] for e in B.build(make_ctx(line))["entries"]}
    assert got == {"Q-1": {"workflow": "W-1", "version": 2}, "Q-2": {"workflow": "W-1", "version": None}, "Q-3": None, "Q-4": None,
                   "Q-5": {"workflow": "W-1", "version": 4}}


def test_m5c_artifact_update_is_kept_and_the_words_are_the_owners(line):
    import j2ui_board as B
    put_questions(line[0], [q(question="Priority did not grant the line; Which pages?", status="answered", answer="refused: none",
                              answered_by="Plan", artifact_update={"art": "Site plan", "v": 2})])
    e = B.build(make_ctx(line))["entries"][0]
    assert e["artifact_update"] == {"art": "Site plan", "v": 2}
    assert (e["question"], e["answer"]) == ("Priority did not say yes to the line; Which pages?", "said no: none")


def test_m5c_no_secret_and_no_path_leaves(line):
    import j2ui_board as B
    put_questions(line[0], [q(question="Where is /Users/someone/secret/file.txt?", status="open")])
    blob = json.dumps(B.build(make_ctx(line)))
    assert "private" not in blob and "GRANT" not in blob and "COUNTER" not in blob and "REFUSE" not in blob


# ---- M5d: the page and the Map -------------------------------------------------------------------------------------------------------------------
def test_m5d_the_pages_own_renderBoard_draws_the_entries(line):
    import j2ui_board as B
    put_questions(line[0], [q("Q-1", status="answered", answer="Home and About", answered_by="Plan", artifact_update={"art": "Site plan", "v": 2},
                              used_by=["Check"]), q("Q-2", asked_by="Audit", to="Write", question="Is there a phone number?")])
    board = B.build(make_ctx(line))
    out = page_render(board=board["entries"])
    if out is None:
        pytest.skip("the pinned page or node is not here")
    words = plain_text(out["board"])
    assert not re.search(r"\bundefined\b|\bNaN\b|\bnull\b", words)
    for want in ("Q-1", "Q-2", "W-2", "W-1", "answered", "open", "Home and About", "Is there a phone number?", "W-3", "yes"):
        assert want in words, want
    assert "Plan (function)" not in words and "No questions asked yet" not in words
    assert "No questions asked yet" in plain_text(page_render(board=[])["board"])


def test_m5d_the_map_draws_asks_and_uses_between_boxes(line):
    import j2ui_map as M
    put_questions(line[0], [q("Q-1", status="answered", answer="Home and About", answered_by="Plan", used_by=["Check", "Plan"]),
                            q("Q-2", asked_by="Audit", to="Write", status="answered", answer="x"),          # a function asked: no box
                            q("Q-3", asked_by="Write", to="Plan", status="open")])                         # not answered yet
    m = M.build(make_ctx(line))
    edges = [(e["kind"], e["from"], e["to"], e["label"]) for e in m["edges"] if e["kind"] in ("asks", "uses")]
    assert edges == [("asks", "work:pages", "work:site-plan", "Q-1"), ("uses", "work:build", "work:site-plan", "Q-1")]
    every = {n["id"] for n in m["nodes"]}
    assert all(e["from"] in every and e["to"] in every for e in m["edges"])


def test_m5d_no_board_no_such_edges(line):
    import j2ui_map as M
    assert not [e for e in M.build(make_ctx(line))["edges"] if e["kind"] in ("asks", "uses")]
