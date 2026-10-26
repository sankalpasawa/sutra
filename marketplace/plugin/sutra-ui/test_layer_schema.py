"""The interface schema layer itself (PRD amendment A1): its types and validator, its modes, its tables against the code
they are bound to, its rulings, its public functions, and the JSON Schema files generated from it.

A test here that meets a fault on purpose does so inside S.expect_refused(); any other fault fails the test through
the conftest fixture, which is the rule every test of the app now keeps (A1.20).
"""
import json

import pytest

import layer_schema as S


ENVELOPE = S.obj({"calls": S.integer(0), "usd": S.number(0)}, required=("calls", "usd"))


@pytest.fixture
def envelope(monkeypatch):
    """A definition of the test's own, so the modes are tested apart from the tables."""
    monkeypatch.setitem(S.DEFS, "test.envelope", ENVELOPE)
    monkeypatch.setitem(S.DEFS, "test.flag", S.boolean())
    return "test.envelope"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A records home of the test's own, as test_j2's fixture makes one, with no model."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import website_dept as W
    return W


def _f(schema, value):
    return S.faults(schema, value)


# ---- S1: one test per keyword ----------------------------------------------------------------------------------------
def test_s1_type_and_a_bool_is_not_a_whole_number():
    assert _f(S.integer(), 3) == [] and _f(S.integer(), 3.0) == []
    assert _f(S.integer(), True) == ["$: is not a whole number"]
    assert _f(S.number(), True) == ["$: is not a number"] and _f(S.number(), 2.5) == []
    assert _f(S.boolean(), 0) == ["$: is not true or false"]
    assert _f(S.text(10), 5) == ["$: is not a string"]
    assert _f({"type": "null"}, None) == [] and _f(S.items(S.text(3)), "x") == ["$: is not a list"]
    assert _f(S.obj({}), []) == ["$: is not an object"]


def test_s1_enum_and_const():
    assert _f(S.enum("a", "b"), "a") == [] and _f(S.enum("a", "b"), "c") == ["$: is not one of a, b"]
    assert _f(S.enum(1, 2), True) != [], "True is not 1"
    assert _f(S.const("Adaptation"), "Adaptation") == [] and _f(S.const("Adaptation"), "Root") == ["$: is not Adaptation"]
    assert _f(S.const(False), 0) != []


def test_s1_min_length_and_max_length():
    assert _f(S.text(5, 2), "a") == ["$: shorter than 2"]
    assert _f(S.text(5), "abcdef") == ["$: longer than 5"]
    assert _f(S.text(5, 1), "abc") == []


def test_s1_pattern_is_searched():
    assert _f(S.word(S.ITEM_RE, 3), "D2") == [] and _f(S.word(S.ITEM_RE, 3), "D0") == ["$: does not match %s" % S.ITEM_RE]
    assert _f({"type": "string", "pattern": "b"}, "abc") == [], "re.search, not a full match"


def test_s1_minimum_and_maximum():
    assert _f(S.integer(0, 1440), -1) == ["$: below 0"]
    assert _f(S.integer(0, 1440), 1441) == ["$: above 1440"]
    assert _f(S.number(0, 1), 0.5) == []


def test_s1_items_min_items_max_items_and_unique_items():
    sch = S.items(S.text(3), 2, 1, unique=True)
    assert _f(sch, ["a"]) == []
    assert _f(sch, []) == ["$: fewer than 1 items"]
    assert _f(sch, ["a", "b", "c"]) == ["$: more than 2 items"]
    assert _f(sch, ["a", "a"]) == ["$: holds an item twice"]
    assert _f(sch, ["a", "abcd"]) == ["$[1]: longer than 3"]


def test_s1_properties_required_and_additional_properties():
    closed = S.obj({"id": S.text(4, 1), "n": S.integer()}, required=("id",), open=False)
    assert _f(closed, {"id": "a1", "n": 2}) == []
    assert _f(closed, {"n": 2}) == ["$.id: is missing"]
    assert _f(closed, {"id": "a1", "colour": "red"}) == ["$.colour: is not a field here"]
    assert _f(closed, {"id": "a1", "n": "2"}) == ["$.n: is not a whole number"]
    assert _f(S.obj({"id": S.text(4)}), {"id": "x", "colour": "red"}) == [], "open: an unknown key passes"
    typed = S.map_of(S.integer(0, 1440))
    assert _f(typed, {"Plan": 15}) == [] and _f(typed, {"Plan": "15"}) == ["$.Plan: is not a whole number"]


def test_s1_property_names_pattern():
    sch = S.map_of(S.items(S.text(40)), keys=S.ITEM_RE)
    assert _f(sch, {"D1": ["Publish"]}) == []
    assert _f(sch, {"X1": []}) == ["$.X1: the key does not match %s" % S.ITEM_RE]


def test_s1_any_of_and_nullable():
    sch = S.nullable(S.text(3))
    assert _f(sch, None) == [] and _f(sch, "ab") == []
    got = _f(sch, "abcd")
    assert len(got) == 1 and got[0].startswith("$: fits none of its shapes")


def test_s1_ref_into_defs(monkeypatch):
    monkeypatch.setitem(S.DEFS, "name", S.word(S.NAME_RE, 40))
    assert _f(S.ref("name"), "Site plan") == []
    assert _f(S.ref("nowhere"), "x") == ["$: no definition named nowhere"]
    assert _f(S.items(S.ref("name")), ["Plan", "/etc/x"])[0].startswith("$[1]: does not match")


def test_s1_unknown_keywords_are_ignored():
    assert _f({"type": "string", "x-owner": "identity", "format": "email", "description": "x"}, "anything") == []


def test_s1_x_say_refuses_control_characters_but_keeps_newline_and_tab():
    assert _f(S.say(40), "two\nlines\tand a tab") == []
    assert _f(S.say(40), "a bell \x07") == ["$: holds a control character"]


def test_s1_field_refuses_markers_return_only_and_a_newline_when_not_multiline_while_text_takes_them():
    one = S.field(200)
    assert _f(one, "Judge one request from the owner.") == []
    assert any("'{{' or '}}'" in f for f in _f(one, "fill {{goal}} here"))
    assert any("'{{' or '}}'" in f for f in _f(one, "a stray }} brace"))
    assert any("Return ONLY" in f for f in _f(one, "Return ONLY a JSON object: {}"))
    assert _f(one, "two\nlines") == ["$: holds a line break"]
    assert _f(S.field(200, multiline=True), "two\nlines") == []
    assert _f(one, "a tab\tis fine") == [] and _f(one, "a bell \x07") == ["$: holds a control character"]
    assert _f(S.field(200), "") == ["$: shorter than 1"]
    assert _f(S.text(200), 'pasted {"a": {"b": 1}} and a template }}') == [], "text() has no content rule"


# ---- S1: the modes -----------------------------------------------------------------------------------------------------
def test_s1_warn_mode_a_fault_is_a_row_and_a_count_and_nothing_raises(home, envelope):
    W = home
    W.create("t-warn", "Acme", None)
    runs = len(W.runs("t-warn"))
    before = S.REFUSED["count"]
    with S.expect_refused(envelope) as met:
        assert S.check(envelope, {"calls": -1, "usd": 1.0}, ref="t-warn", owner="priority") == {"calls": -1, "usd": 1.0}
        assert S.REFUSED["count"] == before + 1, "REFUSED grows in warn mode"
    assert met == ["$.calls: below 0"]
    rows = W.runs("t-warn")[runs:]
    assert len(rows) == 1 and rows[0]["engine"] == "Priority" and rows[0]["system"]
    assert rows[0]["what"].startswith("kept a record that does not fit the interface: test.envelope: $.calls: below 0")
    assert S.REFUSED["count"] == before, "expect_refused takes what it met off REFUSED"


def test_s1_refuse_mode_raises_after_the_row_and_except_value_error_does_not_catch_it(home, envelope, monkeypatch):
    W = home
    W.create("t-refuse", "Acme", None)
    monkeypatch.setattr(S, "MODE", "refuse")
    runs = len(W.runs("t-refuse"))
    with S.expect_refused() as met:
        with pytest.raises(S.SchemaFault) as got:
            try:
                S.check(envelope, {"calls": 1}, ref="t-refuse", owner="priority")
            except ValueError:                                   # pragma: no cover -- the point: it is not one
                pytest.fail("SchemaFault was caught as a ValueError")
    assert not isinstance(got.value, ValueError)
    assert got.value.name == envelope and got.value.faults == ["$.usd: is missing"]
    assert str(got.value) == "test.envelope: $.usd: is missing"
    assert met == ["$.usd: is missing"]
    rows = W.runs("t-refuse")[runs:]
    assert len(rows) == 1 and rows[0]["what"].startswith("refused a write that does not fit the interface: test.envelope")
    # never-refuse: the owner's Stop lands in refuse mode too, and its fault is a row only
    with S.expect_refused():
        assert S.check("test.flag", "yes", ref="t-refuse", never_refuse=True) == "yes"


def test_s1_refused_never_raises_and_a_ref_with_no_department_writes_no_row(home):
    W = home
    with S.expect_refused() as met:
        S.refused("no-such-dept", "envelope", ["$.calls: below 0"])
        S.refused(None, "envelope", ["$.usd: is missing"])
    assert met == ["$.calls: below 0", "$.usd: is missing"]
    assert not (W.home() / "no-such-dept").exists(), "a fault never makes a department folder"


def test_s1_mode_is_a_code_constant_never_an_environment_variable():
    src = (S.HERE / "layer_schema.py").read_text(encoding="utf-8")
    assert S.MODE == "warn" and S.OWNERSHIP_MODE == "warn"
    assert "os.environ" not in src and "getenv" not in src
