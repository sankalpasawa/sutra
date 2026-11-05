"""The five display words and the Atom log rows (library design section 7; function-nodes.md section 6.2; WP L4,
S4-fnodes-08): one pure function gives the word the card, the Atom log, the chip counts and AtomOut.state all use, and a
verify_failed atom is a STORED abandoned atom with abandon_code verify_failed."""
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from factories_atom import (
    ATOM_ID, abandon, check, close_with, closed, fields, open_transition, opened, refused, results_for, tried, verify_failed_atom,
)
from sutra_app.library.atom import (
    Atom, AtomError, LedgerRow, LedgerVerify, atom_display_state, close_atom, ledger_row,
)
from sutra_app.library.gate import GATE
from sutra_app.library.types import violations_from_validation_error

WORDS = {"open", "verify_failed", "closed", "refused", "abandoned"}


def kinds_of_atom():
    """(name, atom, stored state, display word): every row of the table in function-nodes.md section 6.2."""
    return [
        ("open, attempt 0", opened(), "open", "open"),
        ("open, one failed try", tried(opened(), 1), "open", "open"),
        ("open, three failed tries", tried(opened(), 3), "open", "open"),
        ("closed", closed(), "closed", "closed"),
        ("closed on attempt 2", closed(tries=1), "closed", "closed"),
        ("abandoned, verify_failed", verify_failed_atom(), "abandoned", "verify_failed"),
        ("abandoned, manual", abandon(opened(), "stopped", code="manual").atom, "abandoned", "abandoned"),
        ("abandoned, run_ended", abandon(opened(), "run ended: stopped", code="run_ended").atom, "abandoned", "abandoned"),
        ("abandoned, replaced", abandon(opened(), "replaced by a new turn", code="replaced").atom, "abandoned", "abandoned"),
        ("refused", refused(), "refused", "refused"),
    ]


@pytest.mark.parametrize("name,atom,stored,word", kinds_of_atom(), ids=[k[0] for k in kinds_of_atom()])
def test_display_state_table(name, atom, stored, word):
    assert atom.state == stored and atom_display_state(atom) == word


def test_the_display_words_are_five_and_verify_failed_is_never_a_stored_state():
    shown = {atom_display_state(a) for _, a, _, _ in kinds_of_atom()}
    assert shown == WORDS
    assert {a.state for _, a, _, _ in kinds_of_atom()} == {"open", "closed", "refused", "abandoned"}
    with pytest.raises(ValidationError):
        Atom.model_validate(fields(opened(), state="verify_failed"))


def test_an_open_atom_is_always_open_whatever_its_attempt_or_last_result():
    for tries in range(4):
        assert atom_display_state(tried(opened(), tries)) == "open"
    assert atom_display_state(tried(opened(), 3, exit_code=127)) == "open"


def test_display_state_reads_a_mapping_such_as_an_event_body_and_any_object_with_the_two_fields():
    assert atom_display_state({"state": "abandoned", "abandon_code": "verify_failed"}) == "verify_failed"
    assert atom_display_state({"state": "abandoned", "abandon_code": "manual"}) == "abandoned"
    assert atom_display_state({"state": "open"}) == "open"
    assert atom_display_state(SimpleNamespace(state="abandoned", abandon_code="verify_failed")) == "verify_failed"
    assert atom_display_state(SimpleNamespace(state="refused", abandon_code=None)) == "refused"
    for bad in ({"state": "done"}, {}, SimpleNamespace(state=None)):
        with pytest.raises(AtomError) as caught:
            atom_display_state(bad)
        assert caught.value.code == "bad_state"


def test_an_abandon_code_other_than_verify_failed_never_shows_as_verify_failed():
    for code in ("manual", "run_ended", "replaced"):
        assert atom_display_state({"state": "abandoned", "abandon_code": code}) == "abandoned"
    assert atom_display_state({"state": "closed", "abandon_code": "verify_failed"}) == "closed"      # only an abandoned atom counts


# ---- the ledger row -----------------------------------------------------------------------------------------------------

def test_a_closed_atoms_row_is_the_plugins_row_with_node_and_department():
    atom = closed(check("file-exists"), tries=1, department_id="sales", session_id="3f9a1c2b7d", touches=["site/"], model="sonnet", effort="high")
    row = ledger_row(atom)
    assert row.model_dump(mode="json", exclude_none=True) == {
        "kind": "atom_ledger_row", "schema_version": 1, "atom_id": ATOM_ID, "node_id": "sales.adaptation", "department_id": "sales",
        "session_id": "3f9a1c2b7d", "goal": "Visitors can open the contact form", "status": "closed",
        "verify": {"template": "file-exists", "exit_code": 0}, "attempt": 2, "model": "sonnet", "effort": "high", "touches": ["site/"],
        "relevance": "declared: file-exists on site/index.html", "relevance_source": "default", "ts": 120}


def test_the_row_of_the_closed_atom_in_the_design_example():
    spec_row = {"kind": "atom_ledger_row", "schema_version": 1, "atom_id": "a-3f9a1c2b7d-01", "node_id": "sales.adaptation", "status": "closed",
                "verify": {"template": "file-exists", "exit_code": 0}, "attempt": 2, "touches": ["site/"],
                "relevance": "declared: file-exists on site/index.html", "relevance_source": "default", "ts": 120}
    row = ledger_row(closed(tries=1, touches=["site/"]))
    got = row.model_dump(mode="json", exclude_none=True)
    assert {k: v for k, v in got.items() if k != "goal"} == spec_row


def test_a_closed_row_shows_the_first_check_and_exit_zero():
    atom = closed(check("grep-count", relevance="the heading is there"), check("file-exists"))
    row = ledger_row(atom)
    assert (row.verify.template, row.verify.exit_code, row.relevance, row.relevance_source, row.reason) == \
        ("grep-count", 0, "the heading is there", "declared", None)


def test_a_verify_failed_row_shows_the_last_failing_check_and_a_non_zero_exit():
    a = tried(opened(check("file-exists"), check("grep-count"), check("turn-posted")), 0)
    a = close_with(a, 1, 0, 127).atom                              # file-exists fails, grep-count passes, turn-posted cannot run
    a = abandon(a, "verify failed: turn-posted: missing", code="verify_failed").atom
    row = ledger_row(a)
    assert (row.status, row.verify.template, row.verify.exit_code, row.attempt) == ("verify_failed", "turn-posted", 127, 1)
    assert row.reason == "verify failed: turn-posted: missing" and row.relevance == "declared: turn-posted"


def test_abandon_with_code_verify_failed_gives_a_verify_failed_row_whose_exit_code_is_not_zero():
    row = ledger_row(verify_failed_atom())
    assert row.status == "verify_failed" and row.verify.exit_code != 0 and row.verify.template == "file-exists" and row.attempt == 3
    assert row.reason == "verify failed: file-exists: missing"


def test_a_verify_failed_row_for_an_atom_with_no_failed_try_falls_back_to_exit_one():
    atom = abandon(opened(check("file-exists"), check("turn-posted")), "verify failed: nothing ran", code="verify_failed").atom
    row = ledger_row(atom)
    assert (row.status, row.verify.template, row.verify.exit_code) == ("verify_failed", "turn-posted", 1)


def test_abandoned_and_refused_rows_have_a_reason_and_no_verify():
    gone = ledger_row(abandon(tried(opened(), 1), "run ended: stopped", code="run_ended").atom)
    assert (gone.status, gone.verify, gone.reason, gone.attempt, gone.ts) == ("abandoned", None, "run ended: stopped", 1, 130)
    r = ledger_row(refused())
    assert (r.status, r.verify, r.attempt, r.goal, r.ts) == ("refused", None, 0, "done", 100)
    assert r.reason == "goal is banal ('done'): state the observable outcome" and r.relevance is None and r.relevance_source is None


def test_an_open_atom_has_no_ledger_row():
    with pytest.raises(AtomError) as caught:
        ledger_row(tried(opened(), 2))
    assert caught.value.code == "not_terminal"


def test_the_ledger_status_is_the_display_word_for_every_atom_that_ended():
    for name, atom, _, word in kinds_of_atom():
        if word == "open":
            continue
        row = ledger_row(atom)
        assert row.status == word, name
        assert GATE.check("atom_ledger_row", row).model == row and row.atom_id == atom.id and row.node_id == atom.node_id


def test_the_row_roundtrips_through_the_gate_and_is_canonical():
    row = ledger_row(verify_failed_atom())
    checked = GATE.check("atom_ledger_row", json.loads(row.canonical_json()))
    assert checked.model == row and checked.json == row.canonical_json()


# ---- LedgerRow rules -----------------------------------------------------------------------------------------------------

def base_row(**over):
    return {"atom_id": ATOM_ID, "node_id": "sales.adaptation", "status": "closed", "verify": {"template": "file-exists", "exit_code": 0},
            "attempt": 1, "ts": 5, **over}


@pytest.mark.parametrize("over,word", [
    ({"verify": {"template": "file-exists", "exit_code": 1}}, "exit_code 0"),
    ({"verify": None}, "exit_code 0"),
    ({"status": "verify_failed", "reason": "r"}, "non-zero"),                                          # verify exit 0
    ({"status": "verify_failed", "verify": None, "reason": "r"}, "non-zero"),
    ({"status": "verify_failed", "verify": {"template": "file-exists", "exit_code": 1}}, "has a reason"),
    ({"status": "abandoned", "reason": "r"}, "no verify"),                                              # carries a verify
    ({"status": "abandoned", "verify": None}, "has a reason"),
    ({"status": "refused", "reason": "r"}, "no verify"),
    ({"status": "refused", "verify": None}, "has a reason"),
])
def test_ledger_row_rules_by_status(over, word):
    with pytest.raises(ValidationError) as caught:
        LedgerRow.model_validate(base_row(**over))
    assert any(v.code == "value_error" and word in v.message for v in violations_from_validation_error(caught.value))


@pytest.mark.parametrize("over", [{"status": "open"}, {"attempt": 4}, {"verify": {"template": "lint", "exit_code": 0}}, {"colour": "red"},
                                  {"atom_id": "atom-1"}, {"ts": -1}, {"relevance": ""}])
def test_ledger_row_fields_are_closed(over):
    with pytest.raises(ValidationError):
        LedgerRow.model_validate(base_row(**over))


def test_valid_rows_of_each_status():
    assert LedgerRow.model_validate(base_row()).verify == LedgerVerify(template="file-exists", exit_code=0)
    LedgerRow.model_validate(base_row(status="verify_failed", verify={"template": "turn-posted", "exit_code": 127}, reason="r"))
    LedgerRow.model_validate(base_row(status="abandoned", verify=None, reason="r", touches=["site/"], model="m", effort="e"))
    LedgerRow.model_validate(base_row(status="refused", verify=None, reason="r", attempt=0, goal=""))
    assert LedgerRow.model_validate(base_row()).goal == "" and LedgerRow.FAMILY == "atom_ledger_row"


def test_close_then_row_uses_the_results_of_the_last_attempt():
    a = opened(check("file-exists"))
    a = close_with(a, 1).atom
    done = close_atom(a, results_for(a, 0, ts=129), 130).atom
    row = ledger_row(done)
    assert row.verify.exit_code == 0 and row.attempt == 2 and row.ts == 130
    assert [r.exit_code for r in done.verify.checks[0].results] == [1, 0]          # the first try stays on the atom, not in the log


def test_every_kind_of_refusal_can_be_ledgered():
    """A refused atom keeps the draft as it was, so its checks can hold a blank relevance or no pin: the row copes."""
    for over in ({"checks": [check("file-exists", relevance="")]}, {"checks": [check("named-test").evolve(target_sha256=None)]},
                 {"checks": [check("grep-count", ["x", "a.html"])]}, {"goal": ""}, {"goal": "done"}, {"other_open": ATOM_ID}):
        checks = over.pop("checks", [])
        atom = open_transition(*checks, **over).atom
        row = ledger_row(atom)
        assert row.status == "refused" and row.verify is None and row.reason == atom.refusal.message and row.relevance is None
