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


def test_x1_a_default_version_that_does_not_load_refuses_the_definitions_load_and_names_its_parts(runtime, monkeypatch):
    """The .md files used to serve a layer that did not load; nothing does now, so the load is refused, in words, and no function
    runs on words that are not there."""
    real = layers.load
    monkeypatch.setattr(layers, "load", lambda impl_id: None if str(impl_id).startswith("adaptation/") else real(impl_id))
    runtime._DEFS.clear()
    with pytest.raises(ValueError, match=r"the engine definitions are refused: Adaptation's goal instructions, does: the version holds no words for it"):
        runtime.defs()
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
