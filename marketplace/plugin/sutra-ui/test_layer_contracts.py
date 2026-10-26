"""The contract every implementation of a layer passes (PRD amendment A1.21), run on every implementation on disk
(layers/<layer>/v<N>.py), and the contract's own cases shown to catch what they are for: a recipe missing a HEARS
handler fails case 2 with that row named, and a ref_to pointing at a delegate fails case 7.
"""
import json
import types

import pytest

import layers
import layers.contract as C
import layer_schema as S

MODULES = C.discover()


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return {"ref": C.fixture_department(tmp_path / "departments")}


def test_every_layer_has_its_version_1_on_disk():
    assert [C.impl_id(m) for m in MODULES] == [S.DEFAULT_PINS[layer] for layer in S.LAYER_NAMES]


@pytest.mark.parametrize("module", MODULES, ids=C.impl_id)
@pytest.mark.parametrize("case", C.cases(), ids=lambda c: "case %d" % c[0])
def test_the_contract(module, case, ctx):
    _, what, fn = case
    assert fn(module, ctx) == [], what


@pytest.mark.parametrize("module", MODULES, ids=C.impl_id)
def test_what_the_contract_reports_and_does_not_gate(module, capsys):
    counts = C.by_reference(module)
    fallback = C.on_the_md_fallback(module)
    assert set(counts) == {"by_reference", "own"}
    assert fallback == ["%s.%s" % (g, p) for g, parts in S.PROMPTS[module.LAYER].items() for p in parts if p not in (module.WORDS.get(g) or {})], \
        "a part is on the .md fallback until its layer holds its words (wave 1)"
    print("%s: %d by reference, %d own; no WORDS yet (read from the .md bundle, or for Root built inline): %s"
          % (C.impl_id(module), counts["by_reference"], counts["own"], ", ".join(fallback) or "none"))


def _fake(tmp_path, layer, recipe, **more):
    (tmp_path / layer).mkdir(parents=True, exist_ok=True)
    (tmp_path / layer / "v1.json").write_text(json.dumps(recipe), encoding="utf-8")
    base = {"__file__": str(tmp_path / layer / "v1.py"), "LAYER": layer, "VERSION": 1, "IMPLEMENTS": 1, "RECIPE": "v1.json",
            "CODE": {}, "PROMPT": {}, "DRAFT": {}, "CHECK": {}, "WORDS": {}, "LAYOUT": {}}
    base.update(more)
    return types.SimpleNamespace(**base)


def test_a_stub_missing_a_hears_handler_fails_case_2_with_that_row_named(tmp_path):
    recipe = layers.recipes()["Priority"]
    recipe["on"] = [h for h in recipe["on"] if h["name"] != "An engine is born"]
    got = C.case_2(_fake(tmp_path, "priority", recipe), {})
    assert got == ["priority/v1: no handler hears inform/born (An engine is born)"]
    recipe["on"].append({"name": "Hear the weather", "when": {"msg_type": "inform", "word": "weather"}, "steps": []})
    assert "priority/v1: the handler Hear the weather (inform/weather) is no HEARS row" in C.case_2(_fake(tmp_path, "priority", recipe), {})


def test_a_ref_to_pointing_at_a_delegate_fails_case_7(tmp_path, monkeypatch):
    import engine_runtime as R
    monkeypatch.setattr(R, "_a_delegate_for_the_test", layers.ref_to("_names"), raising=False)
    fake = _fake(tmp_path, "identity", layers.recipes()["Identity"], CODE={"identity_read": layers.ref_to("_a_delegate_for_the_test")})
    assert C.case_7(fake) == ["identity/v1: code identity_read points at engine_runtime._a_delegate_for_the_test, which is itself a delegate"]
    fine = _fake(tmp_path, "identity", layers.recipes()["Identity"],
                 CODE={"identity_read": layers.ref_to("identity_read"), "identity_doubt": layers.ref_to("identity_read")})
    assert C.case_7(fine) == [] and C.case_3(fine) == []
    gone = _fake(tmp_path, "identity", layers.recipes()["Identity"], CODE={"identity_read": layers.ref_to("no_such_body")})
    assert C.case_7(gone) == ["identity/v1: code identity_read points at engine_runtime.no_such_body, which is not there"]


def test_the_other_cases_catch_what_they_are_for(tmp_path):
    recipe = layers.recipes()["Coordination"]
    bad = _fake(tmp_path, "coordination", recipe, IMPLEMENTS=2)
    assert C.case_1(bad) == ["coordination/v1: IMPLEMENTS 2 is not schema version 1"]
    nameless = json.loads(json.dumps(recipe))
    nameless["steps"][1]["prompt"] = "no_such_prompt"
    nameless["rules"][0]["check"] = "a_check_of_nobodys"
    nameless["steps"][1]["out"] = {"answer": "str"}            # coord.tie no longer says why
    fake = _fake(tmp_path, "coordination", nameless)
    assert C.case_3(fake) == ["coordination/v1, coord.busy: no check named a_check_of_nobodys is provided",
                              "coordination/v1, coord.tie: no prompt named no_such_prompt is provided"]
    assert C.case_4(fake) == ["coordination/v1: the check a_check_of_nobodys is in neither CHECKS[coordination] nor SHARED_CHECKS"]
    assert C.case_8(fake) == ["coordination/v1, coord.tie: it does not return why, which code outside the layer reads"]
    worded = _fake(tmp_path, "coordination", recipe, WORDS={"tie": {"tie": {"task": "Say who goes first {{ready}}"}}})
    assert C.case_5(worded) == ["coordination/v1: tie.tie has WORDS and no LAYOUT",
                                "coordination/v1: tie.tie.task: holds '{{' or '}}', which only the app may write"]
    lying = _fake(tmp_path, "priority", layers.recipes()["Priority"], CHECK={"answer_has_its_price": lambda c, s, i, out: {"ok": True, "notes": []}})
    assert C.case_4(lying) == ['priority/v1: answer_has_its_price accepts the bad sample {"answer": "accept", "why": ""}',
                               'priority/v1: answer_has_its_price accepts the bad sample {"answer": "grant", "why": "x"}']
