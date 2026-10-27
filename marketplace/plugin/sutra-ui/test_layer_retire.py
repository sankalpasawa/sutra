"""Retiring the .md files and the dead copies (PRD M2.10, amendment A1; package W3-PROOF, step X1).

X1  function-prompts/ and its reader are deleted, so the layers' words are the only words an agent is sent, and the bodies engine_runtime
    still held after a layer's version took them over are deleted with their registry entries.

      a  grep finds no 'function-prompts' in code; the folder, the runtime's reader of it and the prompt compiler's are gone; a default
         version that does not load refuses the definitions load and names the parts nothing else can serve; the prompt snapshot
         (test_function_prompts.py M2.1a) is what the words render
      b  every name the legacy registries (engine_runtime.CODE, PROMPT, DRAFT, CHECK) hold is reached: by a version's table by
         reference (ref_to), or because no layer holds a body of that name (a work engine's); no entry is a copy of a body a version
         holds of its own, and no version's table points at a delegate (contract cases 3 and 7 on every version)

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import ast
import os
import re
from pathlib import Path

import pytest

import layers
import layers.contract as C
import layers.prompts as P
import layer_schema as S

HERE = Path(__file__).resolve().parent
#: folders that are not the app's code: the environment, vendored and generated trees, the design documents (which keep the history
#: of what was retired), the fixtures and the generated schemas
SKIP_DIRS = {".venv", "node_modules", "mock", "design", "test_fixtures", "schemas", "__pycache__", ".git", "electron", "apps-frameworks",
             "seo_agent", "evals"}
CODE_SUFFIXES = {".py", ".js", ".sh", ".json", ".html", ".css", ".md", ".yml", ".yaml", ".toml", ".cfg", ".txt"}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import engine_runtime as R
    R._DEFS.clear()
    yield R
    R._DEFS.clear()


def layer_schema_parts(layer):
    """[(group, parts)] of a layer's prompts, as the interface lists them."""
    return [(group, list(parts)) for group, parts in S.PROMPTS[layer].items()]


# ---- X1a · the .md bundle ---------------------------------------------------------------------------------------------------
def _code_files():
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if Path(name).suffix in CODE_SUFFIXES and not name.startswith("test_") and name != "conftest.py":
                yield Path(root) / name


def test_x1_grep_finds_no_function_prompts_in_code():
    """The code, the scripts, the screens and the docs of the app name no folder of .md prompt files (a test names the snapshot's
    file, whose name keeps the history, and the design documents keep the history of what was retired)."""
    seen = list(_code_files())
    assert len(seen) > 100, "the walk reached the app's files"
    assert [str(p.relative_to(HERE)) for p in seen if "function-prompts" in p.read_text(encoding="utf-8", errors="replace")] == []


def test_x1_the_folder_and_the_readers_of_it_are_gone(runtime):
    assert not (HERE / "function-prompts").exists()
    for gone in ("PROMPTS_DIR", "_parts", "_instruction", "instruction_faults", "bundle_faults"):
        assert not hasattr(runtime, gone), "engine_runtime.%s read the bundle" % gone
    for gone in ("parts_of", "instruction", "file_parts", "md_part", "instruction_faults", "bundle_faults", "extract", "split",
                 "returns_span", "inputs_of", "literal", "main", "held", "from_the_bundle", "PART", "RETURNS"):
        assert not hasattr(P, gone), "layers.prompts.%s read the bundle" % gone
    assert not hasattr(C, "on_the_md_fallback"), "and the contract does not name a fallback that is not there"
    # what stays is the owner's note of an earlier whole-file change (M2.2): the one .md path
    assert all(hasattr(P, name) for name in ("own", "own_files", "kept_as_notes", "kept_note"))


def test_x1_every_part_of_the_interface_is_served_by_the_default_versions_words(runtime):
    """Nothing else can serve an agent a part: each of the 63 parts the five functions' prompts hold (29 the files held, 34 added
    after them) has its words and its layout in the version a department is born with."""
    parts = [(layer, group, part) for layer in S.FUNCTION_LAYERS for group, ps in S.PROMPTS[layer].items() for part in ps]
    assert len(parts) == 63
    for layer, group, part in parts:
        module = layers.load(S.DEFAULT_PINS[layer])
        assert part in module.WORDS[group] and part in module.LAYOUT[group], (layer, group, part)
        assert P._module(None, layer, group, part) is module
    assert P.faults() == runtime.prompt_faults() == [] and runtime.validate(runtime.defs()) == []


def test_x1_a_default_version_that_does_not_load_refuses_the_definitions_load_and_names_what_nothing_else_serves(runtime, monkeypatch):
    """The .md files and the copies in engine_runtime used to serve a layer that did not load; nothing does now, so the load is
    refused, in words, and no function runs on words or bodies that are not there."""
    real = layers.load
    monkeypatch.setattr(layers, "load", lambda impl_id: None if str(impl_id).startswith("adaptation/") else real(impl_id))
    runtime._DEFS.clear()
    with pytest.raises(ValueError, match=r"the engine definitions are refused: Adaptation, adapt\.source: no function named adapt_source ships with the app"):
        runtime.defs()
    faults = runtime.prompt_faults()
    assert "Adaptation's goal instructions, does: the version holds no words for it" in faults, "and the words nothing else holds"
    parts = [(g, p) for g, ps in layer_schema_parts("adaptation") for p in ps]
    assert len([f for f in faults if f.startswith("Adaptation's")]) == len(faults) == len(parts) == 15, "each of Adaptation's parts, and no other layer's"
    monkeypatch.undo()
    runtime._DEFS.clear()
    assert runtime.validate(runtime.defs()) == [], "and with the version there the load is whole"


def test_x1_a_pinned_version_that_does_not_load_runs_the_default_versions_words_with_one_row(runtime):
    """W3-PINS' rule is unchanged by the retirement: a pin that cannot run runs the layer's default (layers.pins), and the words it
    is sent are the default version's."""
    assert layers.cannot_run("identity/v9") == "it does not load"
    d = {"kind": "website", "layers": {"identity": "identity/v9"}}
    assert layers.pins("dref-x", d)["identity"] == "identity/v1"
    assert P._module("dref-x", "identity", "take", "gate") is layers.load("identity/v1")


# ---- X1b · the dead copies ---------------------------------------------------------------------------------------------------
KINDS = ("code", "prompt", "draft", "check")
#: the registries cleared of dead copies (the check below asks of each)
CLEARED = KINDS


def _tables():
    """{kind: (the legacy registry, [every discovered version's table of that kind])} -- the versions under layers/ in order."""
    import engine_runtime as R
    mods = [layers.load(i) for ids in layers.available().values() for i in ids]
    return {k: (getattr(R, k.upper()), [getattr(m, k.upper(), None) or {} for m in mods]) for k in KINDS}


def _lineage_fixture_versions():
    """The fixture child under test_fixtures/layers_lineage/ (A2), which extends a version and so may reach the same bodies."""
    return sorted((HERE / "test_fixtures" / "layers_lineage").rglob("v*.py"))


def test_x1_the_legacy_registries_hold_no_copy_of_a_body_a_version_holds_of_its_own(runtime):
    """A name in engine_runtime's CODE, PROMPT, DRAFT or CHECK is there because a version reaches it by reference (ref_to) or because
    no version holds a body of that name (a work engine's). One a version holds as its own body, and none reaches by reference, is
    a dead copy: nothing can run it."""
    dead = {}
    for kind, (registry, tables) in _tables().items():
        own = {n for t in tables for n, fn in t.items() if not hasattr(fn, "legacy")}
        reached = {n for t in tables for n, fn in t.items() if hasattr(fn, "legacy")}
        dead[kind] = sorted(n for n in registry if n in own and n not in reached)
    assert {kind: dead[kind] for kind in CLEARED} == {kind: [] for kind in CLEARED}, dead


def test_x1_no_version_reaches_a_body_that_is_not_there_or_is_a_delegate(runtime):
    """Contract cases 3 and 7 on every version on disk: every name a recipe uses is provided, and no ref_to points at nothing or
    at a delegate (so no delegate loops back to the version that points at it)."""
    for module in C.discover():
        assert C.case_3(module) == [] and C.case_7(module) == [], C.impl_id(module)
    fixtures = _lineage_fixture_versions()
    assert fixtures, "the fixture child is there"
    for path in fixtures:
        # the fixture child only extends a version (inherit): it points at no body of engine_runtime's by reference of its own
        calls = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", getattr(n.func, "attr", None)) == "ref_to"]
        assert calls == [], str(path)


def test_x1_the_registries_shrank_by_the_copies_and_the_by_reference_counts_did_not_change(runtime):
    """What the retirement removed from the legacy registries (69 + 25 + 25 + 46 = 165 entries before, 128 after) and what it left: the
    live bodies are still reached by reference, so the layers' counts are as they were."""
    sizes = {k: len(getattr(runtime, k.upper())) for k in KINDS}
    assert sizes == {"code": 48, "prompt": 21, "draft": 21, "check": 38}, sizes                    # 69, 25, 25 and 46 before: 37 entries fewer
    counts = {C.impl_id(m): C.by_reference(m) for m in C.discover()}
    assert counts["root/v1"] == {"by_reference": 14, "own": 0} and counts["coordination/v1"] == {"by_reference": 19, "own": 2}
    assert counts["audit/v1"] == {"by_reference": 9, "own": 6}


def test_x1_a_body_a_version_wraps_stays_where_it_is_and_the_copies_it_replaced_are_gone(runtime):
    """audit/v1 and identity/v1 run the body engine_runtime holds under their own wrapper (R.audit_pick, R.identity_read ...): those
    are live and stay, with no registry entry of their own; the bodies a version copied whole (priority, the line's handlers, the
    mechanical check) are deleted."""
    for name in ("audit_pick", "audit_file", "identity_read", "identity_file", "identity_apply", "identity_drop", "identity_finding", "hear"):
        assert callable(getattr(runtime, name)), name
    for name in ("audit_pick", "audit_file", "identity_read", "identity_file", "identity_apply", "identity_drop", "identity_finding"):
        assert name not in runtime.CODE, name
    for name in ("priority_envelope", "priority_grant", "priority_read", "priority_post", "audit_mechanical", "adapt_line_offer", "adapt_source",
                 "adapt_line_refused", "adapt_line_counter", "identity_closed", "_round_inert"):
        assert not hasattr(runtime, name) and name not in runtime.CODE, name
    for name in ("adapt_hearnext", "adapt_round", "adapt_round_granted", "adapt_round_refused"):
        assert name not in runtime.CODE, name


def test_x1_the_prompt_builders_a_version_took_over_are_gone_and_the_ones_it_references_stay(runtime):
    for name in ("p_adapt_line", "d_adapt_line", "p_priority_bargain", "d_priority_bargain", "p_adapt_fit", "d_adapt_fit", "p_adapt_next", "d_adapt_next"):
        assert not hasattr(runtime, name), name
    for name in ("adapt_line", "priority_bargain", "adapt_fit", "adapt_next"):
        assert name not in runtime.PROMPT, name
    for name in ("adapt_line_draft", "priority_bargain_draft", "adapt_fit_draft", "adapt_next_draft"):
        assert name not in runtime.DRAFT, name
    # every soft step of a function still finds its prompt and its draft: in its version, or in the registry for a name that is by reference
    for engine in ("Identity", "Adaptation", "Priority", "Coordination", "Audit"):
        for step in runtime.all_steps(engine):
            for kind in ("prompt", "draft"):
                if step.get(kind):
                    assert callable(layers.resolve(None, engine, kind, step[kind], getattr(runtime, kind.upper()))), (engine, step["id"], kind)


def test_x1_the_checks_a_version_took_over_are_gone_and_the_ones_it_wraps_or_references_stay(runtime):
    for name in ("c_line_is_engines", "c_answer_has_its_price", "c_done_is_read", "c_question_is_bounded", "c_spot_check_reads_only", "c_line_is_fitted",
                 "c_round_is_new", "_fit_line"):
        assert not hasattr(runtime, name), name
    for name in ("line_is_engines", "answer_has_its_price", "has_a_verdict", "done_is_read", "question_is_bounded", "spot_check_reads_only",
                 "line_is_fitted", "round_is_new"):
        assert name not in runtime.CHECK, name
    assert callable(runtime.c_has_a_verdict), "audit/v1 wraps the body engine_runtime holds, and gives it no entry of its own"
    # every check a function's step names is found: in its version, or in the registry for a name that is by reference
    for engine in ("Identity", "Adaptation", "Priority", "Coordination", "Audit", "Setup"):
        for step in runtime.all_steps(engine):
            assert callable(layers.resolve(None, engine, "check", step["check"], runtime.CHECK)), (engine, step["id"], step["check"])
            if step.get("code"):
                assert callable(layers.resolve(None, engine, "code", step["code"], runtime.CODE)), (engine, step["id"], step["code"])
