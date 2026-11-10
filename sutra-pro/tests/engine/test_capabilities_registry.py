"""The capability registry (work package WP3, engine design 2.1, D126): the engine keeps gaining abilities and every one of them is
inherited by every output and every agent call. A capability adds; it never replaces. The registry is how the host, the API and the
tests learn what the engine can do."""
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import capabilities, llm
from sutra_app.engine.api import mount
from sutra_app.engine.api.settings import CAPABILITIES_SCHEMA, capabilities_view
from sutra_app.engine.capabilities import (CAPABILITIES, Capability, CapabilityConflict, EngineContext, OutputSpec, SPECS, addenda,
                                           describe, documents, install, register)
from sutra_app.engine.port import CallTag, CompletionResult
from sutra_app.engine.spec import EngineSettings


def ctx(**settings) -> EngineContext:
    return EngineContext(task=SimpleNamespace(), settings=EngineSettings(**settings), paths=SimpleNamespace(), data_dir=None)


def spec(label="Thing", **kw) -> OutputSpec:
    return OutputSpec(label=label, noun="thing", sections=("One",), conditions="x.json", rubric=(("T-1", "t"),), rates="rates_prd",
                      check_types=("heading-present",), builder="b", file="thing.md", done="Done", **kw)


class Adds(Capability):
    def __init__(self, name="adds", outputs=None):
        self.name, self._outputs = name, outputs or {}

    def outputs(self):
        return self._outputs


class FakeJ2:
    def __init__(self, **outs):
        self.OUTPUTS = dict(outs)


class RecordingPort:
    def __init__(self):
        self.tags, self.progress = [], []

    def describe(self):
        return SimpleNamespace(provider="x", model="y", mock=False)

    def complete(self, req, on_progress=None):
        self.tags.append(req.tag)
        if on_progress is not None:
            on_progress({"chars": 2, "text": "hi"})
        return CompletionResult(text="ok")


@pytest.fixture
def port(llm_reset):
    p = RecordingPort()
    llm_reset.configure(p, mock=False, base_tag=CallTag(run_id="j2-x", dept_id="web", task_id="t1"))
    return p


# ---- the registry ----------------------------------------------------------------------------------------------------
def test_the_registry_is_a_fixed_tuple_in_a_fixed_order_with_the_workspace_first():
    assert isinstance(CAPABILITIES, tuple) and CAPABILITIES[0].name == "workspace"
    names = [c.name for c in CAPABILITIES]
    assert len(set(names)) == len(names) and all(names)


def test_register_adds_an_output_and_remembers_its_spec():
    j2 = FakeJ2(website={"label": "Website"})
    register(j2, [Adds("a", {"thing": spec()})])
    assert j2.OUTPUTS["thing"]["label"] == "Thing" and j2.OUTPUTS["thing"]["capability"] == "a"
    assert j2.OUTPUTS["thing"]["workspace"] == "read" and j2.OUTPUTS["thing"]["single"] is False
    assert SPECS["thing"].label == "Thing"
    SPECS.pop("thing")


def test_register_is_idempotent():
    j2, caps = FakeJ2(), [Adds("a", {"thing": spec()})]
    register(j2, caps)
    first = j2.OUTPUTS["thing"]
    register(j2, caps)
    assert j2.OUTPUTS["thing"] is first and list(j2.OUTPUTS) == ["thing"]
    SPECS.pop("thing", None)


def test_an_output_that_the_engine_already_has_is_a_conflict():
    j2 = FakeJ2(website={"label": "Website"})
    with pytest.raises(CapabilityConflict, match="website"):
        register(j2, [Adds("a", {"website": spec()})])
    assert j2.OUTPUTS == {"website": {"label": "Website"}}


def test_an_output_that_another_capability_added_is_a_conflict_and_nothing_is_added():
    j2 = FakeJ2()
    register(j2, [Adds("a", {"thing": spec("A")})])
    before = dict(j2.OUTPUTS)
    with pytest.raises(CapabilityConflict, match="thing"):
        register(j2, [Adds("b", {"other": spec("O"), "thing": spec("B")})])
    assert j2.OUTPUTS == before and "other" not in j2.OUTPUTS            # all or nothing
    SPECS.pop("thing", None)


def test_two_capabilities_naming_the_same_output_in_one_registration_conflict():
    with pytest.raises(CapabilityConflict, match="both"):
        register(FakeJ2(), [Adds("a", {"t": spec()}), Adds("b", {"t": spec()})])


def test_the_real_registry_registers_into_the_real_j2_and_never_touches_the_four_outputs():
    from sutra_app.engine import j2
    before = {k: dict(v) for k, v in j2.OUTPUTS.items() if k in ("website", "prd", "hld", "lld")}
    register(j2)
    register(j2)
    assert {k: dict(j2.OUTPUTS[k]) for k in before} == before


def test_an_output_spec_says_what_it_can_do_and_refuses_a_bad_workspace():
    assert spec().workspace == "read" and spec(workspace="edit").to_j2()["workspace"] == "edit"
    assert spec(single=True).to_j2()["single"] is True
    with pytest.raises(ValueError):
        spec(workspace="write")


# ---- hooks reach every output and every agent call ------------------------------------------------------------------
@pytest.mark.parametrize("stage", ["website", "prd", "hld", "lld", None])
def test_the_workspace_hook_runs_for_every_output(port, stage):
    install(ctx())
    llm.ask("s", "u", None, tag=CallTag(function="identity", stage=stage))
    assert port.tags[-1].workspace == "read"


def test_without_the_hooks_a_call_is_untouched(port):
    llm.ask("s", "u", None, tag=CallTag(function="identity"))
    assert port.tags[-1].workspace == "none"


def test_a_tag_hook_only_fills_fields_that_are_still_empty(port, llm_reset):
    llm.TAG_HOOKS.append(lambda tag: {"function": "audit", "purpose": "plan", "workspace": "edit", "step": 4})
    llm.ask("s", "u", None, tag=CallTag(function="identity", purpose="summary"))
    got = port.tags[-1]
    assert (got.function, got.purpose) == ("identity", "summary")      # set by the caller: kept
    assert (got.workspace, got.step) == ("edit", 4)                    # empty: filled


def test_a_second_capability_cannot_override_the_first(port):
    llm.TAG_HOOKS.append(lambda tag: {"workspace": "read"})
    llm.TAG_HOOKS.append(lambda tag: {"workspace": "edit"})
    llm.ask("s", "u", None, tag=CallTag(function="identity"))
    assert port.tags[-1].workspace == "read"


def test_a_field_the_tag_does_not_have_and_a_value_it_refuses_are_ignored(port, capsys):
    llm.TAG_HOOKS.append(lambda tag: {"nonsense": 1})
    llm.TAG_HOOKS.append(lambda tag: {"workspace": "everything"})
    llm.ask("s", "u", None, tag=CallTag(function="identity"))
    assert port.tags[-1].workspace == "none"
    assert "tag hook" in capsys.readouterr().err


def test_a_hook_that_raises_never_stops_the_call(port, capsys):
    def boom(tag):
        raise RuntimeError("broken capability")
    llm.TAG_HOOKS.append(boom)
    assert llm.ask("s", "u", None, tag=CallTag(function="identity")) == "ok"
    assert "broken capability" in capsys.readouterr().err


def test_progress_hooks_see_each_event_of_a_call_and_the_callers_own_callback_still_runs(port):
    seen, own = [], []
    llm.PROGRESS_HOOKS.append(lambda tag, event: seen.append((tag.function, event["text"])))
    llm.ask("s", "u", None, tag=CallTag(function="audit"), on_progress=own.append)
    assert seen == [("audit", "hi")] and own == [{"chars": 2, "text": "hi"}]


def test_without_a_progress_hook_the_port_is_asked_for_no_progress_at_all(port):
    llm.ask("s", "u", None, tag=CallTag(function="audit"))
    assert port.progress == [] and llm.PROGRESS_HOOKS == []


def test_a_progress_hook_that_raises_does_not_stop_the_call_or_the_other_hooks(port, capsys):
    seen = []

    def boom(tag, event):
        raise RuntimeError("bad sink")
    llm.PROGRESS_HOOKS[:] = [boom, lambda tag, event: seen.append(event)]
    assert llm.ask("s", "u", None, tag=CallTag(function="audit")) == "ok" and len(seen) == 1
    assert "bad sink" in capsys.readouterr().err


def test_install_twice_replaces_its_hooks_instead_of_adding_to_them(port):
    install(ctx())
    install(ctx(workspace="off"))
    assert len([h for h in llm.TAG_HOOKS if hasattr(h, "capability")]) == 1
    llm.ask("s", "u", None, tag=CallTag(function="identity"))
    assert port.tags[-1].workspace == "none"                           # the second context won


def test_install_keeps_hooks_that_are_not_a_capabilitys(port):
    mine = lambda tag: {}      # noqa: E731
    llm.TAG_HOOKS.append(mine)
    install(ctx())
    assert mine in llm.TAG_HOOKS


def test_a_capability_that_only_tags_adds_no_progress_hook_and_one_that_watches_adds_one():
    class Watches(Capability):
        name = "watches"

        def progress(self, tag, event):
            pass
    tags, progress = capabilities.capability_hooks(ctx(), [Adds("a"), Watches()])
    assert tags == [] and [h.capability for h in progress] == ["watches"]


def test_install_calls_every_capability_once_before_the_hooks_exist(llm_reset):
    order = []

    class Probe(Capability):
        name = "probe"

        def install(self, c):
            order.append(("install", len(llm.TAG_HOOKS)))
    install(ctx(), [Probe()])
    assert order == [("install", 0)]


# ---- addenda, description and the API --------------------------------------------------------------------------------
def test_addenda_joins_every_capabilitys_text_in_order_and_survives_a_broken_one(capsys):
    class Says(Capability):
        def __init__(self, name, text):
            self.name, self.text = name, text

        def addendum(self, fn, c):
            if self.text is None:
                raise RuntimeError("no text")
            return f"[{self.name}:{fn}]"
    got = addenda("audit", ctx(), [Says("a", "x"), Says("b", None), Says("c", "z")])
    assert got == "[a:audit][c:audit]" and "no text" in capsys.readouterr().err


def test_describe_lists_name_outputs_and_settings():
    rows = describe([Adds("a", {"thing": spec(workspace="edit", single=True)})])
    assert rows == [{"name": "a", "outputs": [{"name": "thing", "label": "Thing", "workspace": "edit", "single": True}], "settings": []}]
    assert describe()[0] == {"name": "workspace", "outputs": [],
                             "settings": [{"field": "workspace", "values": ["auto", "off"], "default": "auto"}]}


# ---- the Artifacts row of an output's report (J2 sync 4, D146) -------------------------------------------------------
def report_run(tmp_path, text="# Thing\n\nWhat was done.\n", name="thing.md", folder="j2-20261104-100004-7f3a"):
    """A run folder (`folder` under `tmp_path`) holding the report `name`, or none when `text` is None."""
    run = tmp_path / folder
    run.mkdir()
    if text is not None:
        (run / name).write_text(text, encoding="utf-8")
    return run


def test_a_capability_with_an_output_that_has_a_report_file_gets_its_document_row_with_no_code_of_its_own(tmp_path):
    cap = Adds("a", {"thing": spec()})
    assert type(cap).documents is Capability.documents, "the hook is inherited: the capability adds only its output"
    rows = cap.documents("thing", report_run(tmp_path))
    assert len(rows) == 1
    row = rows[0]
    assert (row["id"], row["kind"], row["name"], row["file"], row["doc_file"]) == ("thing", "document", "Thing thing", "thing.md", "thing.md")
    assert (row["maker"], row["made_in"], row["sections"], row["nodes"], row["docs"], row["ok"]) == (None, [], {}, [], [], True)
    assert row["versions"] == [{"workflow": None, "cycle": None, "purpose": "", "label": "current"}]
    assert row["views"] == {"summary": True, "agent": {"format": "text", "file": "thing.md", "schema": None, "model": None, "valid": None},
                            "human": {"format": "markdown", "file": "thing.md"}}, "the three tabs are J2's own views() of the row"


def test_the_row_is_in_the_shape_of_j2s_own_document_rows(tmp_path):
    from sutra_app.engine import j2_artifacts
    theirs = j2_artifacts.groups(str(report_run(tmp_path, name="prd.md", folder="j2-prd")))["groups"][3]
    assert theirs["id"] == "documents" and [r["id"] for r in theirs["rows"]] == ["prd"]
    mine = Adds("a", {"thing": spec()}).documents("thing", report_run(tmp_path))[0]
    assert set(mine) == set(theirs["rows"][0]), "the same keys as a row of J2's own Documents group"
    for key in ("kind", "maker", "made_in", "sections", "nodes", "docs"):
        assert type(mine[key]) is type(theirs["rows"][0][key]), key


def test_an_output_that_is_not_this_capabilitys_gets_no_row_even_when_the_file_is_there(tmp_path):
    run = report_run(tmp_path)
    cap = Adds("a", {"thing": spec()})
    for output in ("website", "prd", "hld", "lld", "other", "", None):
        assert cap.documents(output, run) == [], output
    assert Adds("empty").documents("thing", run) == [], "a capability with no output has no report"


def test_no_file_no_run_or_an_empty_file_is_no_row_or_a_row_that_is_not_ok(tmp_path):
    cap = Adds("a", {"thing": spec()})
    assert cap.documents("thing", report_run(tmp_path, text=None)) == [], "the run has not written the report yet"
    assert cap.documents("thing", None) == [] and cap.documents("thing", str(tmp_path / "nowhere")) == []
    empty = cap.documents("thing", report_run(tmp_path, text="", folder="j2-empty"))
    assert len(empty) == 1 and empty[0]["ok"] is False, "an empty report is listed, and not marked ok"
    assert Adds("b", {"nofile": OutputSpec(label="N", noun="n", file=None)}).documents("nofile", tmp_path) == []


def test_an_output_given_as_a_plain_dict_has_its_row_too(tmp_path):
    plain = {"label": "Plain", "noun": "note", "file": "plain.md"}
    rows = Adds("a", {"plain": plain}).documents("plain", report_run(tmp_path, name="plain.md"))
    assert [(r["id"], r["name"], r["file"]) for r in rows] == [("plain", "Plain note", "plain.md")]


def test_the_registry_concatenates_every_capabilitys_rows_in_order_and_a_broken_one_adds_nothing(tmp_path, capsys):
    run = report_run(tmp_path)

    class Broken(Capability):
        name = "broken"

        def documents(self, output, run_dir):
            raise RuntimeError("no rows today")

    class Odd(Capability):
        name = "odd"

        def documents(self, output, run_dir):
            return {"not": "a list"}

    class Two(Capability):
        name = "two"

        def documents(self, output, run_dir):
            return [{"id": "two-a"}, {"id": "two-b"}]
    got = documents("thing", run, [Adds("a", {"thing": spec()}), Broken(), Odd(), Two()])
    assert [r["id"] for r in got] == ["thing", "two-a", "two-b"]
    assert "no rows today" in capsys.readouterr().err
    assert documents("thing", run, []) == [] and documents("thing", run, [Adds("none")]) == []


def test_the_real_registry_gives_a_row_for_the_project_report_and_none_for_j2s_own_outputs(tmp_path):
    from sutra_app.engine import j2
    capabilities.register(j2)
    assert all(type(c).documents is Capability.documents for c in CAPABILITIES), "no capability overrides the hook (project.py is not edited)"
    run = report_run(tmp_path, text="## Findings\n\nSomething.\n", name="project.md")
    rows = documents("project", run)
    assert [(r["id"], r["name"], r["file"]) for r in rows] == [("project", "Project work report", "project.md")]
    assert rows[0]["views"]["human"] == {"format": "markdown", "file": "project.md"}
    for own in ("website", "prd", "hld", "lld", "", None):
        assert documents(own, run) == [], own


def test_asking_for_rows_imports_j2_only_when_a_row_is_built_and_the_package_still_imports_none():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(sys.modules["sutra_app.engine.capabilities.base"]))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [n for n in top if "j2" in ast.dump(n)], "base.py imports no J2 module at the top"


def test_the_context_names_the_concrete_output(llm_reset):
    c = ctx()
    assert c.output == "website"
    c.selection = capabilities.Selection("prd", "owner", "you chose it")
    assert c.output == "prd"
    c.run = SimpleNamespace(output="hld")
    assert c.output == "hld"


@pytest.fixture
def api(fake_services):
    fake_services.add_department("web")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, fake_services)
    return TestClient(app, raise_server_exceptions=False)


def test_get_engine_capabilities_lists_what_the_engine_can_do(api):
    got = api.get("/api/engine/capabilities")
    assert got.status_code == 200
    body = got.json()
    assert body["schema"] == CAPABILITIES_SCHEMA == "engine-capabilities/1"
    assert body == json.loads(json.dumps(capabilities_view()))
    assert [c["name"] for c in body["capabilities"]] == [c.name for c in CAPABILITIES]
    assert {"website", "prd", "hld", "lld"} <= set(body["outputs"])
    assert all(isinstance(c["outputs"], list) and isinstance(c["settings"], list) for c in body["capabilities"])


def test_the_module_imports_no_j2_module_so_importing_it_reads_no_environment():
    code = ("import sys\nimport sutra_app.engine.capabilities\n"
            "print(sorted(m for m in sys.modules if m.startswith('sutra_app.engine.j2')))")
    import subprocess
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                          env={"PYTHONPATH": ":".join(sys.path), "PATH": ""})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"
