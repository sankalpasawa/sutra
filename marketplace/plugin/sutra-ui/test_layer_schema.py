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


# ---- S3: the tables, against the code they are bound to -------------------------------------------------------------
import ast  # noqa: E402

import engine_runtime as R  # noqa: E402
import functions_view as FV  # noqa: E402
import j2_runtime as J  # noqa: E402
import website_dept as W  # noqa: E402


def _steps(e):
    return list(e.get("gates") or []) + list(e.get("rules") or []) + list(e.get("steps") or []) + \
        [s for h in e.get("on") or [] for s in h.get("steps") or []]


def _function_engines():
    return {name: R.defs()["engines"][name] for name in S.ENGINE_LAYER if name in R.defs()["engines"]}


def test_s3_edges_are_engine_defs_edges_in_their_order():
    assert S.edges() == R.defs()["edges"]


def test_s3_every_handler_of_the_five_is_a_hears_row_and_every_row_has_its_handler():
    for name, e in _function_engines().items():
        if name == "Setup":
            continue
        layer = S.ENGINE_LAYER[name]
        rows = {(r["act"], r["word"]): r for r in S.hears(layer)}
        handlers = {(h["when"]["msg_type"], h["when"].get("word", S.ANY)): h["name"] for h in e.get("on") or []}
        assert set(handlers) == set(rows), "%s: %s" % (name, set(handlers) ^ set(rows))
        for pair, handler in handlers.items():
            assert rows[pair]["handler"] == handler
            assert rows[pair]["payload"] in S.DEFS and rows[pair]["via"] in ("board", "call")
            assert set(rows[pair]["from"]) <= set(S.ACTORS)


# the sites: every post() and _tell() call of engine_runtime and j2_runtime, with what it sends
def _consts(node, fn):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        a, b = _consts(node.body, fn), _consts(node.orelse, fn)
        return a | b if a is not None and b is not None else None
    if (isinstance(node, ast.Name) and node.id == "OWNER") or (isinstance(node, ast.Attribute) and node.attr == "OWNER"):
        return {"Owner"}
    if isinstance(node, ast.Name) and fn is not None:
        vals = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == node.id for t in n.targets)]
        got = set()
        for v in vals:
            c = _consts(v, None)
            if c is None:
                return None
            got |= c
        return got or None
    return None


def _payload(node, fn):
    if isinstance(node, ast.Dict):
        return node
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "dict" and node.args and isinstance(node.args[0], ast.Dict):
        return node.args[0]
    if isinstance(node, ast.Name) and fn is not None:
        vals = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == node.id for t in n.targets)]
        if len(vals) == 1:
            return _payload(vals[0], None)
    return None


def _word(node, fn):
    d = _payload(node, fn) if node is not None else None
    if d is None:
        return S.ANY
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and k.value == "word":
            got = _consts(v, fn)
            return got if got is not None else S.ANY
    return S.ANY


def _post_sites(module):
    tree = ast.parse((S.HERE / (module + ".py")).read_text(encoding="utf-8"))
    out = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) and getattr(f.value, "id", None) == "R" else None)
            if name not in ("post", "_tell") or (name == "post" and fn.name == "_tell") or len(node.args) < 4:
                continue                      # _tell's own post is the wrapper: its callers are the sites
            a = node.args
            if name == "post":
                src, act, pl = _consts(a[1], fn), _consts(a[3], fn), a[4] if len(a) > 4 else None
            else:
                src, act, pl = {"Identity"}, _consts(a[3], fn), a[4] if len(a) > 4 else None
            out.append({"where": "%s:%d %s" % (module, node.lineno, fn.name), "src": src, "act": act, "word": _word(pl, fn)})
    return out


def test_s3_every_post_site_is_a_sends_row():
    sites = _post_sites("engine_runtime") + _post_sites("j2_runtime")
    assert len(sites) > 60, "the scan finds the sites"
    for site in sites:
        assert site["act"], "%s: its act is a literal" % site["where"]
        for src in site["src"] or ():         # a sender named by a variable is read below
            for act in site["act"]:
                rows = [r for r in S.SENDS[src] if r["act"] == act]
                assert rows, "%s: %s sends no %s" % (site["where"], src, act)
                if site["word"] == S.ANY:
                    assert any(r["words"] == S.ANY for r in rows), "%s: a word that is not a literal needs an (any) row" % site["where"]
                else:
                    for w in site["word"]:
                        assert any(r["words"] == S.ANY or w in r["words"] for r in rows), \
                            "%s: %s %s %r is not in SENDS" % (site["where"], src, act, w)
    named = [s for s in sites if s["src"] is None]
    assert named, "the scan reads the sites whose sender is a variable (_line_conflict's)"
    for site in named:                        # each act word a variable sender posts is some actor's row
        for act in site["act"]:
            for w in ([] if site["word"] == S.ANY else site["word"]):
                assert any(r["act"] == act and (r["words"] == S.ANY or w in r["words"]) for a in S.SENDS for r in S.SENDS[a]), site


def test_s3_every_sends_row_names_known_acts_actors_and_payloads():
    assert set(S.SENDS) == set(S.ACTORS)
    for actor, rows in S.SENDS.items():
        for r in rows:
            assert r["act"] in S.ACTS and set(r["to"]) <= set(S.ACTORS) and r["payload"] in S.DEFS
            assert r["words"] == S.ANY or (isinstance(r["words"], tuple) and r["words"])


_COORDINATIONS_OWN = ("coord.edge", "coord.bounds", "coord.alarm", "coord.verdict")


def test_s3_every_cross_layer_ask_rule_is_a_calls_row():
    tree = ast.parse((S.HERE / "engine_runtime.py").read_text(encoding="utf-8"))
    found = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_ask_rule" and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant):
                found.append((fn.name, node.args[1].value))
    assert found
    calls = {(c["site"], c["what"]): c for c in S.calls()}
    for site, sid in found:
        owner = R.step_def(sid)[0]
        if sid in _COORDINATIONS_OWN:
            assert owner == "Coordination", "Coordination's own rule calls stay inside its layer"
            continue
        assert (site, sid) in calls, "%s asks %s's %s in place, and CALLS does not say so" % (site, owner, sid)
        assert calls[(site, sid)]["to"] == owner
    assert all(c["from"] in S.TITLE.values() and c["to"] in S.TITLE.values() for c in S.calls())


def test_s3_every_soft_steps_out_keys_are_named_in_its_parts_returns():
    readers = {}
    for layer, groups in S.PROMPTS.items():
        for group, parts in groups.items():
            for part, p in parts.items():
                rb = p["read_by"]
                for sid in (rb if isinstance(rb, tuple) else (rb,) if rb else ()):
                    readers.setdefault(sid, []).append(p)
    soft = [s for e in _function_engines().values() for s in _steps(e) if s.get("prompt")]
    assert len(soft) >= 14
    for s in soft:
        assert s["id"] in readers, "%s reads no part" % s["id"]
        for p in readers[s["id"]]:
            for key in s.get("out") or {}:
                assert '"%s"' % key in p["returns"], "%s: %s is not in its part's returns" % (s["id"], key)


def test_s3_prompts_are_the_bundles_parts_and_the_returns_byte_for_byte():
    for fn, files in R.INSTRUCTIONS.items():
        assert list(S.PROMPTS[fn]) == list(files) and list(S.GROUPS[fn]) == list(files)
        for file, parts in files.items():
            text = (R.PROMPTS_DIR / fn / (file + ".md")).read_text(encoding="utf-8")
            lead, got = R._parts(text)
            assert S.GROUPS[fn][file] == lead.split("\n\n")[0]
            if not parts:
                assert list(S.PROMPTS[fn][file]) == ["note"], "a file no step reads is its note (A1.16 rule 7)"
                continue
            assert list(S.PROMPTS[fn][file]) == list(parts)
            for part, slots in parts.items():
                p = S.PROMPTS[fn][file][part]
                assert p["inputs"] == tuple(slots)
                assert p["returns"] is None or p["returns"] in got[part], "%s.%s.%s: returns byte for byte" % (fn, file, part)
                assert p["returns"] is not None or "Return ONLY" not in got[part]
                assert all(d in S.DEFS and d.startswith("field.") for d in p["fields"].values())


def test_s3_roots_returns_are_its_inline_builders_byte_for_byte():
    got = {"setup.read": {"words": "w", "conversation": {"messages": []}, "named": None,
                          "facts": {"kinds": "website", "use_cases": "website: a site", "existing": "none"}}}
    ctx = {"bag": got, "dept": {"name": "Acme Root", "org": {"name": "Acme"}}, "ref": None}
    assert S.PROMPTS["root"]["setup"]["converse"]["returns"] in R.p_setup_converse(ctx, None, None)
    assert S.PROMPTS["root"]["setup"]["shape"]["returns"] in R.p_setup_shape(ctx, None, None)


def test_s3_checks_are_every_check_a_function_step_names():
    for name, e in _function_engines().items():
        layer = S.ENGINE_LAYER[name]
        named = {s["check"] for s in _steps(e)}
        if name == "Setup":
            named |= {s["check"] for s in _steps(R.engine_def("Setup"))}
        assert named <= set(S.CHECKS[layer]) | set(S.SHARED_CHECKS), "%s: %s" % (name, named - set(S.CHECKS[layer]) - set(S.SHARED_CHECKS))
        assert set(S.CHECKS[layer]) <= named
    assert all(c in R.CHECK for layer in S.CHECKS for c in S.CHECKS[layer]) and all(c in R.CHECK for c in S.SHARED_CHECKS)


def test_s3_contract_samples_hold_against_the_bodies_on_main():
    for check, samples in S.CONTRACT_SAMPLES.items():
        for out in samples["good"]:
            assert R.CHECK[check](None, None, None, out)["ok"] is True, (check, out)
        for out in samples["bad"]:
            assert R.CHECK[check](None, None, None, out)["ok"] is False, (check, out)


def test_s3_outputs_are_the_step_outputs_read_outside_the_layer():
    src = (S.HERE / "functions_view.py").read_text(encoding="utf-8") + (S.HERE / "j2_runtime.py").read_text(encoding="utf-8")
    ids = {s["id"] for e in R.defs()["engines"].values() for s in _steps(e)}
    read = {i for i in ids if '"%s"' % i in src or "'%s'" % i in src}
    assert read == set(S.OUTPUTS)


def test_s3_layers_carry_the_function_pages_verbatim():
    for layer in S.FUNCTION_LAYERS:
        page = FV.PAGES[S.TITLE[layer]]
        for k in ("vsm", "line", "holds", "hands_to", "keeps", "v1"):
            assert S.LAYERS[layer][k] == page[k], (layer, k)
    assert set(S.LAYERS) == set(S.LAYER_NAMES) and S.LAYERS["identity"]["view"] == "view.identity"


def test_s3_settings_defaults_are_the_codes():
    assert S.SETTINGS["priority"]["envelope"]["default"] == R.engine_def("Priority")["template"]["envelope"]
    assert S.SETTINGS["coordination"]["order"]["default"] == R.defs()["coordination"]["order"]
    assert all(s["def"] in S.DEFS for layer in S.SETTINGS for s in S.SETTINGS[layer].values())


def test_s3_the_constants_and_field_tuples_equal_the_codes():
    assert S.BOUNDS == R.BOUNDS and S.CHAIN_LIMIT == W.CHAIN_LIMIT and S.REPAIRS == J.REPAIRS
    assert S.OPTIONS_MAX == W.OPTIONS_MAX and S.DONE_ITEMS_MAX == W.DONE_ITEMS_MAX and S.STANDARD == R.STANDARD
    assert S.ACTS == R.ACTS and S.RULE_TAGS == W.RULE_TAGS and (S.DONE_HOW, S.DONE_LEVELS) == (W.DONE_HOW, W.DONE_LEVELS)
    assert S.TABLE_FIELDS == R.TABLE_FIELDS and S.SLOT_FIELDS == R.SLOT_FIELDS and S.LEFT_OUT_FIELDS == R.LEFT_OUT_FIELDS
    assert S.COORDINATION_FIELDS == FV.COORDINATION_FIELDS and S.TIMETABLE_ROW == FV.TIMETABLE_ROW
    assert S.ENGINE_CARD_FIELDS == FV.ENGINE_CARD_FIELDS and S.ENGINE_FIVE_ROW == FV.ENGINE_FIVE_ROW
    assert S.BORN_FIELDS == R.BORN_FIELDS and S.SLOT_STATES == tuple(FV.TT_WORDS)
    assert set(S.DEFS["coordination.table"]["properties"]) == set(S.TABLE_FIELDS) | {"schema_version"}
    assert tuple(S.DEFS["coordination.slot"]["properties"]) == S.SLOT_FIELDS
    assert tuple(S.DEFS["coordination.left_out"]["properties"]) == S.LEFT_OUT_FIELDS
    assert tuple(S.DEFS["view.coordination"]["properties"]) == S.COORDINATION_FIELDS
    assert tuple(S.DEFS["view.coordination"]["properties"]["timetable"]["items"]["properties"]) == S.TIMETABLE_ROW
    assert tuple(S.DEFS["view.engine_card"]["properties"]) == S.ENGINE_CARD_FIELDS
    assert tuple(S.DEFS["view.engine_card"]["properties"]["five"]["items"]["properties"]) == S.ENGINE_FIVE_ROW
    assert tuple(S.DEFS["act.born"]["properties"])[1:] == S.BORN_FIELDS
    assert S.VERDICTS["identity"]["journey"] == R.JOURNEYS
    assert set(S.ASK_KINDS) >= {"blocked", "j2_identity", "done_items", "instructions", "engine", "line"}


# ---- S3: the rulings, kept as interface tests (A1.25) ----------------------------------------------------------------
def test_s3_ruling_only_identity_speaks_to_the_owner():
    for actor, rows in S.SENDS.items():
        if any("Owner" in r["to"] for r in rows):
            assert actor == "Identity", actor


def test_s3_ruling_priority_prices_and_holds_and_never_orders():
    assert {d for r in S.SENDS["Priority"] for d in r["to"]} == {"Adaptation"}
    assert not any("order" in w for r in S.SENDS["Priority"] if r["words"] != S.ANY for w in r["words"])
    for p in (S.HERE / "function-templates" / "priority").glob("*.json"):
        low = p.read_text(encoding="utf-8").lower()
        assert "what runs next" not in low and " order" not in low.replace("in order", ""), p.name


def test_s3_ruling_root_makes_the_department_and_never_an_engine():
    assert not any(r["act"] == "propose" for r in S.SENDS["Root"])
    assert S.DEFS["engine.template"]["properties"]["made_by"]["properties"]["by"] == {"const": "Adaptation"}


def test_s3_ruling_adaptation_proposes_and_never_applies():
    assert not [k for k, (owner, _) in S.DEPARTMENT_KEYS.items() if owner == "adaptation"]
    assert {r["act"] for r in S.SENDS["Adaptation"]} == {"propose", "inform"}


def test_s3_ruling_the_checker_is_never_the_writer():
    assert not [k for k, (owner, _) in S.DEPARTMENT_KEYS.items() if owner == "audit"]
    assert not R.engine_def("Audit").get("writes"), "Audit owns no artifact"
    assert "function's" in dict((s[0], s[1]) for s in S.WORKFLOW_STANDARDS)["names_unique"]


def test_s3_ruling_threads_are_bounded_and_no_engine_is_mandatory_unless_its_kind_says_so():
    assert S.BOUNDS == R.BOUNDS and S.CHAIN_LIMIT == W.CHAIN_LIMIT and S.REPAIRS == J.REPAIRS
    assert "required_kept" in [s[0] for s in S.WORKFLOW_STANDARDS]
    for kind, k in R.defs()["kinds"].items():
        assert R.required_engines({"kind": kind}) == list(k.get("required") or [])


def test_s3_the_tables_name_only_known_definitions_and_layers():
    for layer, kinds in S.RECORDS.items():
        assert layer in S.LAYER_NAMES and all(k["def"] in S.DEFS for k in kinds.values())
    assert all(name in S.DEFS for name in S.VIEWS.values()) and all(name in S.DEFS for name in S.SINK.values())
    assert all(name in S.DEFS for name in S.SINK_JOURNALS.values())
    assert all(o["params"] is None or o["params"] in S.DEFS for o in S.OPTION_KINDS.values())
    assert all(o["layer"] in S.LAYER_NAMES for o in S.OPTION_KINDS.values())
    assert all(set(st) <= set(S.STAGES) and set(src) <= set(S.SOURCES) for _, _, src, st in S.WORKFLOW_STANDARDS)
    assert S.owner_of_key("goal") == "identity" and S.owner_of_key("envelopes") == "priority" and S.owner_of_key("colour") is None


# ---- S4: the public functions ----------------------------------------------------------------------------------------
FIXTURES = S.HERE / "schemas" / "layers" / "fixtures"


def test_s4_migrate_reads_a_v0_department_as_v1_and_never_writes():
    v0 = json.loads((FIXTURES / "department.v0.json").read_text(encoding="utf-8"))
    v1 = json.loads((FIXTURES / "department.v1.json").read_text(encoding="utf-8"))
    kept = json.dumps(v0, sort_keys=True)
    assert S.migrate("department", v0) == v1
    assert json.dumps(v0, sort_keys=True) == kept, "a read returns a copy and changes nothing"
    assert v1["schema_version"] == 1 and v1["layers"] == S.DEFAULT_PINS
    assert v1["done_items"] == [{"id": "D1", "text": v0["done"], "how": "code", "level": "outcome"}]
    assert v1["an_older_key"] == "kept on read", "unknown keys are kept on read"
    assert S.validate("department", {k: v for k, v in v1.items() if k != "an_older_key"}) == []
    assert S.migrate("department", v1) == v1, "a v1 record reads as it is"


def test_s4_migrate_maps_an_older_tables_writer_to_coordination_keeping_its_why():
    t = {"order": ["posts", "line", "functions"], "line": ["Plan"], "by": "Root", "why": "the plan Root registered"}
    got = S.migrate("coordination.table", t)
    assert (got["by"], got["why"], got["schema_version"]) == ("Coordination", "the plan Root registered", 1)
    assert S.migrate("coordination.table", dict(t, by="born"))["by"] == "born"
    assert S.validate("coordination.table", got) == []


def test_s4_as_workflow_gives_the_deliverable_and_default_covers():
    d = {"kind": "website", "done_items": [{"id": "D1", "text": "Every page checked and live", "how": "code", "level": "outcome"},
                                           {"id": "D2", "text": "Pages read well", "how": "model", "level": "target"}]}
    wf = S.as_workflow(["Plan", "Write", "Check", "Publish"], "library", d)
    assert wf["deliverable"] == "Live site" and wf["covers_by"] == "default"
    assert wf["covers"] == {"D1": ["Publish"], "D2": ["Publish"]}
    assert [e["reads"] for e in wf["engines"]] == ["Brief", "Site plan", "Pages", "Build"]
    assert S.validate("workflow", wf) == []
    shaped = S.as_workflow([{"name": "Facts", "does": "finds the facts", "reads": "Brief", "writes": "Facts", "internet": True, "covers": ["D1"]},
                            {"name": "Inventory", "reads": "Facts", "writes": "Inventory", "covers": ["D1", "D2"]}], "shaped", d)
    assert shaped["covers"] == {"D1": ["Facts", "Inventory"], "D2": ["Inventory"]} and shaped["covers_by"] == "adaptation"
    assert shaped["deliverable"] == "Inventory" and S.validate("workflow", shaped) == []


def test_s4_validate_workflow_returns_the_shape_rows_until_roots_standards_are_code():
    wf = S.as_workflow(["Plan", "Write", "Check", "Publish"], "library", {"kind": "website"})
    rows = S.validate_workflow(wf, "registration")
    assert rows[0] == {"check": "workflow_meets_standards", "passed": True, "why": "the workflow fits the workflow schema"}
    assert S.workflow_faults(wf) == []
    bad = S.validate_workflow({"engines": [{"name": "Bad/Name"}], "source": "shaped"})
    assert bad[0]["passed"] is False and S.workflow_faults({"engines": "x"})[0].startswith("workflow_meets_standards: ")
    for r in rows:
        assert S.validate("workflow.check", r) == []


def test_s4_first_input_and_deliverable():
    assert S.first_input("root") == "Request" and S.first_input("website") == "Brief" and S.first_input("organic") == "Brief"
    assert S.deliverable({"kind": "website"}) == "Live site" and S.deliverable({"kind": "default"}) == "Result"
    assert S.deliverable({"kind": "organic"}) is None
    assert S.deliverable({"kind": "website", "workflows": [{"version": 1, "engines": ["Plan", "Write"], "source": "library"}]}) == "Pages"


def test_s4_validate_act_holds_the_edges_the_words_and_the_payload():
    assert S.validate_act("Priority", "Owner", "inform", {"word": "said"}) != [], "only Identity speaks to the owner"
    assert S.validate_act("Owner", "Identity", "request", {"word": "request", "words": 'my {"a": 1} }}'}) == []
    assert S.validate_act("Adaptation", ["Priority"], "propose", {"word": "trial", "step": "write.page"}) == []
    assert S.validate_act("Adaptation", "Priority", "propose", {"word": "grant"})[0].startswith("$.word: Adaptation does not propose")
    assert S.validate_act("Priority", "Adaptation", "propose", {"word": "order the line"}) == ["$.word: Priority prices and holds; it never orders"]
    assert S.validate_act("Audit", "Identity", "inform", {"word": "finding", "severity": "dire"}) == ["$.severity: is not one of high, medium, low"]
    assert S.validate_act("Plan", "Identity", "inform", {"word": "x"}) == ["$: Engine sends no inform"]
    assert S.validate_act("Identity", "Owner", "inform", {"word": "said", "done": "Line 1."}) == [], "an (any) row takes a stored tell"
    assert S.validate_act("Identity", ["Coordination"], "inform", {"word": "born"}) == []
    assert S.validate_act("Identity", "Coordination", "agree", {"word": "verdict", "answer": "maybe"}) == ["$.answer: is not one of admit, wait, refuse"]


def test_s4_check_act_is_a_row_in_warn_mode_and_a_refusal_in_refuse_mode(monkeypatch):
    with S.expect_refused("act") as met:
        assert S.check_act("Priority", "Owner", "inform", {"word": "said"}) == {"word": "said"}
    assert met == ["Priority inform to Owner: $: Priority sends no inform"]
    monkeypatch.setattr(S, "MODE", "refuse")
    with S.expect_refused("act"):
        with pytest.raises(S.SchemaFault):
            S.check_act("Priority", "Owner", "inform", {"word": "said"})


def test_s4_check_department_checks_only_the_changed_keys_and_stamps_the_version(monkeypatch):
    before = {"kind": "website", "ref": "r", "name": "Acme", "colour": "an old key", "windows": {"Plan": "fifteen"}}
    d = dict(before, goal="A live site")
    assert S.check_department(dict(d), before=before)["schema_version"] == 1, "a legacy fault never blocks a later save"
    with S.expect_refused("department") as met:
        S.check_department(dict(d, colour="red"), before=before)
    assert met == ["$.colour: is not a field here"]
    with S.expect_refused("department") as met:
        S.check_department(dict(d, done_items=[{"id": "D2", "text": "x"}], to_be_confirmed=[{"item": "D9"}]), before=before)
    assert met == ["$.done_items: the ids do not run D1 to D1 in order", "$.to_be_confirmed: D9 names no done-when item"]
    with S.expect_refused("department") as met:
        S.check_department(dict(d, kind="spaceship"), before=before)
    assert met == ["$.kind: spaceship is no kind in the definitions"]
    with S.expect_refused("department") as met:
        S.check_department(dict(d, goal="Mine now"), before=before, by="Priority")
    assert met == ["$.goal: is Identity's, and Priority wrote it"], "ownership is a row in warn mode"
    monkeypatch.setattr(S, "MODE", "refuse")
    with S.expect_refused("department") as met:
        S.check_department(dict(d, stopped="yes"), before=before)       # the owner's Stop always lands
    assert met == ["$.stopped: is not true or false"]
    with S.expect_refused("department"):
        with pytest.raises(S.SchemaFault):
            S.check_department(dict(d, colour="red"), before=before)


def test_s4_a_new_workflows_entry_is_a_registration_and_meets_the_write_stage():
    base = {"kind": "website", "ref": "r", "name": "Acme"}
    reg = {"version": 1, "engines": ["Plan", "Write", "Check", "Publish"], "source": "library", "registered": "2026-10-26", "by": "Root"}
    S.check_department(dict(base, workflows=[reg]), before=base)
    with S.expect_refused("department") as met:
        S.check_department(dict(base, workflows=[reg, {"version": 2, "engines": ["Plan"], "source": "copied"}]),
                           before=dict(base, workflows=[reg]))
    assert "$.workflows[1].registered: is missing" in met and "$.workflows[1].source: is not one of library, shaped, fitted, made" in met
    assert not [f for f in met if f.startswith("$.workflows[0]")], "the entry already on the record is not read again"


def test_s4_validate_field_instructions_view_and_record():
    assert S.validate_field("identity", "take", "take", "task", "Judge one request from the owner.") == []
    assert S.validate_field("identity", "take", "take", "task", "Judge {{words}}") != []
    assert S.validate_field("identity", "take", "take", "returns", "x") == ["$: take.take has no field returns the owner may change"]
    assert S.validate_field("identity", "take", "nowhere", "task", "x") == ["$: Identity has no part take.nowhere"]
    assert S.validate_field("identity", "goal", "skills", "items", ["judge a request against the goal"]) == []
    good = {"schema_version": 1, "values": {"identity": {"take": {"take": {"task": {"value": "Judge it.", "at": "2026-10-26", "ask": "a-1"}}}}}}
    assert S.validate_instructions(good) == []
    bad = json.loads(json.dumps(good))
    bad["values"]["identity"]["take"]["take"]["task"]["value"] = "Return ONLY yes"
    assert S.validate_instructions(bad) == ["$.values.identity.take.take.task: holds 'Return ONLY': the answer's shape belongs to the app"]
    assert S.validate_view("identity", {}) != [] and S.validate_view("root", {}) == ["$: root has no view"]
    assert S.validate_record("identity", "rule", {"line": "x"}) == []
    assert S.validate_record("identity", "colour", {}) == ["$: Identity keeps no record named colour"]


def test_s4_describe_is_the_whole_interface_as_json():
    got = S.describe()
    assert json.loads(json.dumps(got)) == got
    for k in ("layers", "records", "department_keys", "hears", "sends", "edges", "calls", "verdicts", "checks", "shared_checks",
              "contract_samples", "outputs", "settings", "groups", "prompts", "option_kinds", "workflow_standards", "views",
              "sink", "sink_journals", "defs"):
        assert got[k], k
    assert got["edges"] == R.defs()["edges"] and got["schema_version"] == S.SCHEMA_VERSION
