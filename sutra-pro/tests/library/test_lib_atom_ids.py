"""The id helpers of types.py: atom_sid, function_atom_id, overhead_atom_id, function_node_id (S2-models-10,
S4-fnodes-07). One AtomId pattern, two forms, no third scheme."""
import hashlib
import re

import pytest
from pydantic import TypeAdapter, ValidationError

from sutra_app.library.types import (
    ATOM_ID_RE, FUNCTIONS, NODE_ID_RE, AtomId, IdError, atom_sid, function_atom_id, function_node_id,
    overhead_atom_id,
)

RUN = "j2-20261104-101500-a1b2"
ATOM_ID = TypeAdapter(AtomId)


def test_sid_is_the_first_ten_hex_digits_of_sha1_of_run_and_node():
    sid = atom_sid(RUN, "sales.identity")
    assert sid == hashlib.sha1(f"{RUN}:sales.identity".encode()).hexdigest()[:10]
    assert sid == "16dfc77671"                       # a golden: the separator and the length are part of the contract
    assert re.fullmatch(r"[0-9a-f]{10}", sid)


def test_sid_depends_on_both_parts_and_on_their_order():
    base = atom_sid(RUN, "sales.identity")
    assert atom_sid(RUN, "sales.identity") == base                      # deterministic
    assert atom_sid(RUN + "x", "sales.identity") != base
    assert atom_sid(RUN, "sales.audit") != base
    assert atom_sid("sales.identity", RUN) != base                      # not symmetric


@pytest.mark.parametrize("run_id, node_id", [("", "n"), ("r", ""), (None, "n"), ("r", None), (5, "n"), ("r", ["x"])])
def test_sid_refuses_a_missing_or_non_text_part(run_id, node_id):
    with pytest.raises(IdError):
        atom_sid(run_id, node_id)


def test_sid_refuses_text_that_cannot_be_encoded():
    with pytest.raises(IdError):
        atom_sid("run\ud800", "node")


def test_function_atom_id_has_at_least_two_digits():
    sid = "3f9a1c2b7d"
    assert function_atom_id(sid, 1) == "a-3f9a1c2b7d-01"
    assert function_atom_id(sid, 2) == "a-3f9a1c2b7d-02"
    assert function_atom_id(sid, 9) == "a-3f9a1c2b7d-09"
    assert function_atom_id(sid, 10) == "a-3f9a1c2b7d-10"
    assert function_atom_id(sid, 99) == "a-3f9a1c2b7d-99"
    assert function_atom_id(sid, 100) == "a-3f9a1c2b7d-100"
    assert function_atom_id(sid, 999_999) == "a-3f9a1c2b7d-999999"


@pytest.mark.parametrize("n", [0, -1, 1_000_000, True, False, 1.0, "1", None])
def test_function_atom_id_refuses_a_number_the_pattern_cannot_hold(n):
    with pytest.raises(IdError):
        function_atom_id("3f9a1c2b7d", n)


@pytest.mark.parametrize("sid", ["", "A" * 10, "3f9a1c2b7d3f9a1c2", "ab-cd", "ab cd", "ab\n", None, 7])
def test_function_atom_id_refuses_a_bad_sid(sid):
    with pytest.raises(IdError):
        function_atom_id(sid, 1)


def test_function_atom_id_takes_the_longest_legal_sid():
    assert function_atom_id("a" * 16, 1) == "a-" + "a" * 16 + "-01"
    assert function_atom_id("0", 1) == "a-0-01"


def test_results_match_atom_id_pattern_and_the_pydantic_type():
    ids = [function_atom_id(atom_sid(RUN, f"sales.{fn}"), n) for fn in FUNCTIONS for n in (1, 2, 50, 123456)]
    ids += [overhead_atom_id(RUN), overhead_atom_id("req-17")]
    for value in ids:
        assert ATOM_ID_RE.fullmatch(value), value
        assert ATOM_ID.validate_python(value) == value


def test_atom_id_pattern_accepts_both_forms_and_nothing_else():
    for good in ("a-3f9a1c2b7d-01", "W-1.a1", "W-12.a345", "a-x-12", "a-" + "z" * 16 + "-123456"):
        assert ATOM_ID.validate_python(good) == good
    for bad in ("atom-1", "a-3f9a1c2b7d-1", "a-3F9a1c2b7d-01", "a-3f9a1c2b7d-01\n", "a--01", "a-" + "z" * 17 + "-01",
                "a-3f9a1c2b7d-1234567", "W-1", "W-1.b1", "W-.a1", "W-1.a", "W-٣.a1", "W-1.a٣", "a-3f9a1c2b7d-٠١", "W-1.a1\n", "",
                "W-" + "1" * 40 + ".a1"):
        with pytest.raises(ValidationError):
            ATOM_ID.validate_python(bad)


def test_no_collision_in_ten_thousand_sids():
    sids = {atom_sid(f"j2-20261104-1015{r:02d}-{r:04x}", f"dept{d}.{fn}")
            for r in range(100) for d in range(20) for fn in FUNCTIONS}
    assert len(sids) == 100 * 20 * len(FUNCTIONS)


def test_no_collision_in_ten_thousand_function_atom_ids_of_one_run():
    ids = {function_atom_id(atom_sid(RUN, f"dept{d}.{fn}"), n) for d in range(40) for fn in FUNCTIONS for n in range(1, 51)}
    assert len(ids) == 40 * len(FUNCTIONS) * 50


def test_overhead_key_is_function_atom_id_of_the_overhead_sid():
    assert overhead_atom_id("req-17") == function_atom_id(atom_sid("req-17", "overhead"), 1)
    assert overhead_atom_id("req-17") == "a-55bc398936-01"                   # a golden
    assert overhead_atom_id(RUN) == "a-acf5c7d8de-01"


def test_overhead_key_repeats_for_one_owner_and_differs_between_owners():
    assert overhead_atom_id("req-17") == overhead_atom_id("req-17")
    owners = [RUN, "req-17", "req-18", "j2-20261104-101500-a1b3", "req-170"]
    assert len({overhead_atom_id(o) for o in owners}) == len(owners)


def test_overhead_key_cannot_equal_a_function_atom_of_the_same_run():
    own = {function_atom_id(atom_sid(RUN, f"{d}.{fn}"), n) for d in ("sales", "ops", "overhead") for fn in FUNCTIONS
           for n in range(1, 30)}
    assert overhead_atom_id(RUN) not in own


@pytest.mark.parametrize("owner", ["", None, 17, b"req-1"])
def test_overhead_key_needs_an_owner(owner):
    with pytest.raises(IdError):
        overhead_atom_id(owner)


def test_function_node_id_is_dept_dot_function():
    for fn in FUNCTIONS:
        assert function_node_id("sales", fn) == f"sales.{fn}"
    assert function_node_id("web-team_2", "audit") == "web-team_2.audit"


def test_function_node_id_matches_the_node_id_pattern_of_the_graph():
    node = re.compile(r"^[a-z][a-z0-9_-]{1,39}(\.[a-z]+)?$")
    for dept in ("sales", "a1", "x" * 40):
        for fn in FUNCTIONS:
            assert node.fullmatch(function_node_id(dept, fn))


@pytest.mark.parametrize("dept", ["Sales", "a.b", "", "a", "x" * 41, "1sales", "sa les", "sales\n", None, 5])
def test_function_node_id_refuses_a_bad_department(dept):
    with pytest.raises(IdError):
        function_node_id(dept, "audit")


@pytest.mark.parametrize("function", ["root", "Audit", "audit ", "", None, "identity.audit"])
def test_function_node_id_refuses_a_bad_function(function):
    with pytest.raises(IdError):
        function_node_id("sales", function)


def test_node_id_pattern_has_no_dot():
    assert NODE_ID_RE.fullmatch("sales")
    assert not NODE_ID_RE.fullmatch("sales.identity")


def test_id_errors_are_typed_value_errors():
    assert issubclass(IdError, ValueError) and IdError is not ValueError
