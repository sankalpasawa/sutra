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
                                           describe, install, register)
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
