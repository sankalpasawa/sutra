"""The workspace capability (work package WP3, engine design 2.2, D127): which model calls of the engine may look at the owner's working
folder, and which may change it. The capability is a table; these tests read it through a recording port, as the router does."""
import json
from types import SimpleNamespace

import pytest

from sutra_app.engine import capabilities, llm
from sutra_app.engine.capabilities import Capability, EngineContext, OutputSpec, SPECS, register
from sutra_app.engine.capabilities.workspace import WORKSPACE_PURPOSES, WorkspaceCapability, team_workspace_for, workspace_for
from sutra_app.engine.host.publisher import HostHooks
from sutra_app.engine.port import CallTag, CompletionResult
from sutra_app.engine.spec import EngineSettings

from test_engine_host import BREW_LAB, QUIET, Running, brew_dir, events, j2, make_port_of   # noqa: F401  (fixtures and helpers)

FIVE = ("identity", "adaptation", "priority", "coordination", "audit")


class EditSpec(Capability):
    """An output whose builders may change files, as the project output will be."""
    name = "edits"

    def outputs(self):
        return {"editing": OutputSpec(label="Editing", noun="e", workspace="edit")}


@pytest.fixture
def edit_output():
    register(SimpleNamespace(OUTPUTS={}), [EditSpec()])
    yield "editing"
    SPECS.pop("editing", None)


def ctx(**settings) -> EngineContext:
    return EngineContext(task=SimpleNamespace(), settings=EngineSettings(**settings), paths=SimpleNamespace(), data_dir=None)


# ---- the table -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("function", FIVE)
@pytest.mark.parametrize("purpose", WORKSPACE_PURPOSES)
def test_the_five_functions_read_the_folder_for_their_own_work(function, purpose):
    assert workspace_for(function, purpose, "website") == "read"


@pytest.mark.parametrize("purpose", ["summary", "template", "review", "change", "chat_plan", "chat"])
@pytest.mark.parametrize("function", FIVE + ("W-3", "reviewer", "summariser", ""))
def test_helper_calls_get_no_folder(function, purpose):
    assert workspace_for(function, purpose, "website") == "none"


def test_builders_read_on_every_output_that_does_not_say_edit(edit_output):
    for output in ("website", "prd", "hld", "lld", None, "unknown"):
        assert workspace_for("W-1", "agent_turn", output) == "read"


def test_a_builder_of_an_output_that_says_edit_may_edit_and_audit_still_only_reads(edit_output):
    assert workspace_for("W-2", "agent_turn", edit_output) == "edit"
    assert workspace_for("W-2", "judge", edit_output) == "edit"
    for fn in FIVE:
        assert workspace_for(fn, "agent_turn", edit_output) == "read", fn      # only builders change files
    assert workspace_for("audit", "agent_turn", edit_output) == "read"


def test_an_agent_that_is_not_one_of_the_engines_gets_no_folder():
    assert workspace_for("team:marketing", "agent_turn", "website") == "none"
    assert workspace_for("W-x", "agent_turn", "website") == "none"
    assert workspace_for("w-3", "agent_turn", "website") == "none"


def test_the_capability_reads_the_calls_own_stage_before_the_runs_output(edit_output):
    cap, c = WorkspaceCapability(), ctx()
    assert cap.tag(CallTag(function="W-1", stage=edit_output), c) == {"workspace": "edit", "team_workspace": "edit"}
    assert cap.tag(CallTag(function="W-1", stage="prd"), c) == {"workspace": "read"}
    c.selection = capabilities.Selection(edit_output, "owner", "x")
    assert cap.tag(CallTag(function="W-1"), c) == {"workspace": "edit", "team_workspace": "edit"}          # no stage on the tag: the run's output


# ---- what the TEAM may do (D135): every agent of a run whose builders change files is told so, not only the builders ----------------------
@pytest.mark.parametrize("function", FIVE + ("W-1", "W-7"))
def test_every_agent_of_an_output_that_edits_carries_what_the_team_may_do(edit_output, function):
    tag = WorkspaceCapability().tag(CallTag(function=function, stage=edit_output), ctx())
    assert tag["team_workspace"] == "edit"
    assert tag["workspace"] == ("edit" if function.startswith("W-") else "read")             # the agent's own reach is unchanged


@pytest.mark.parametrize("output", ["website", "prd", "hld", "lld", None, "unknown"])
def test_an_output_whose_builders_only_read_says_nothing_about_a_team(edit_output, output):
    for function in FIVE + ("W-1",):
        assert "team_workspace" not in WorkspaceCapability().tag(CallTag(function=function, stage=output), ctx())


def test_a_helper_call_of_an_editing_output_carries_neither(edit_output):
    assert WorkspaceCapability().tag(CallTag(function="reviewer", purpose="review", stage=edit_output), ctx()) == {}


def test_team_workspace_for_is_a_table_of_the_outputs_specs(edit_output):
    assert team_workspace_for(edit_output) == "edit"
    assert [team_workspace_for(o) for o in ("website", "prd", None, "")] == ["none"] * 4


def test_a_helper_call_adds_nothing_to_its_tag():
    assert WorkspaceCapability().tag(CallTag(function="reviewer", purpose="review"), ctx()) == {}


def test_workspace_off_gives_every_call_none(edit_output):
    cap = WorkspaceCapability()
    for tag in (CallTag(function="identity"), CallTag(function="W-1", stage=edit_output), CallTag(function="audit", purpose="judge")):
        assert cap.tag(tag, ctx(workspace="off")) == {}
        assert cap.tag(tag, ctx()) != {}


def test_the_capability_reads_no_file_and_needs_no_folder():
    # a table: the same answer whatever is (not) on disk, so a tag built offline equals one built with a folder set
    assert WorkspaceCapability().tag(CallTag(function="identity"), ctx()) == {"workspace": "read"}


# ---- through the host, with a recording port --------------------------------------------------------------------------
class TaggingPort(llm.ScriptedPort):
    """J2's mock mode that keeps the tag of every request."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.tags = []

    def complete(self, req, on_progress=None):
        self.tags.append(req.tag)
        return super().complete(req, on_progress)


def run_brew(run_dir, **kw):
    seen = {}

    def make(*, sink, mock, task, paths):
        seen["port"] = TaggingPort(usage_sink=sink)
        return seen["port"]
    assert Running(run_dir, "--mock", make_port=make).wait() == 0
    return seen["port"].tags


def test_a_website_run_reads_with_every_agent_and_never_edits_and_helpers_get_none(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings={**QUIET, "J2_REALIZATION": "1"})
    tags = run_brew(run_dir)
    assert len(tags) > 10
    by_function = {}
    for tag in tags:
        by_function.setdefault(tag.function, set()).add((tag.purpose, tag.workspace))
    for tag in tags:
        assert tag.workspace != "edit", tag
        want = "read" if tag.purpose in WORKSPACE_PURPOSES and (tag.function in FIVE or tag.function.startswith("W-")) else "none"
        assert tag.workspace == want, tag
    assert {t.function for t in tags if t.workspace == "read"} >= set(FIVE)
    assert any(t.function.startswith("W-") and t.workspace == "read" for t in tags), "builders read"
    assert {"plan", "judge"} <= {t.purpose for t in tags if t.workspace == "read"}


PRD_BRIEF = ("Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: patients at small "
             "clinics and the front-desk staff who manage the line. Problem: patients wait 45 minutes on average in crowded waiting "
             "rooms. Must-have features: join the queue from a phone, live position updates, SMS alert when 2 patients are ahead, staff "
             "dashboard to call the next patient. Constraints: works on low-end Android phones; no patient health data stored. Success: "
             "average in-room wait under 10 minutes; 60% of patients join remotely within 3 months.")


def test_a_prd_run_reads_too(j2, make_run_dir):
    run_dir = make_run_dir(user_text=PRD_BRIEF, settings={**QUIET, "J2_OUTPUT": "prd"})
    tags = run_brew(run_dir)
    assert {t.workspace for t in tags if t.function in FIVE and t.purpose == "agent_turn"} == {"read"}
    assert all(t.workspace != "edit" for t in tags)


def test_workspace_off_in_the_global_settings_gives_every_call_none(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"workspace": "off"}))
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    tags = run_brew(run_dir)
    assert tags and {t.workspace for t in tags} == {"none"}
    assert json.loads((run_dir / "settings.json").read_text())["workspace"] == "off"


def test_workspace_off_in_the_teams_own_settings_wins_over_the_global_one(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"workspace": "auto"}))
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    dept = data_dir / "departments" / "web"
    (dept / "engine.json").write_text(json.dumps({"workspace": "off"}))
    assert {t.workspace for t in run_brew(run_dir)} == {"none"}


def test_the_registry_is_installed_before_the_first_call_and_the_run_has_a_context(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    running = Running(run_dir, "--mock")
    assert running.wait() == 0
    assert running.host.context.run is running.host.run and running.host.context.output == "website"


def test_the_prompts_are_not_changed_by_the_capability(j2, make_run_dir):
    """The folder text is added by the router below J2's prompt; a capability's addendum is empty for every agent of the four outputs."""
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    systems = []

    class Port(llm.ScriptedPort):
        def complete(self, req, on_progress=None):
            systems.append(req.system)
            return super().complete(req, on_progress)
    assert Running(run_dir, "--mock", make_port=make_port_of(Port)).wait() == 0
    assert systems and not [s for s in systems if "Working folder" in s or "## Project work" in s]


# ---- the addendum ------------------------------------------------------------------------------------------------------
def test_host_hooks_append_every_capabilitys_addendum_after_the_inner_text(monkeypatch):
    class Says(Capability):
        name = "says"

        def addendum(self, fn, c):
            return f"\n\n## Says\n{fn} in {c.output}"
    monkeypatch.setattr(capabilities, "CAPABILITIES", (Says(),))
    inner = SimpleNamespace(system_addendum=lambda fn: "\n\n## Node context\nnote")
    hooks = HostHooks(inner, publisher=None, context=ctx())
    assert hooks.system_addendum("audit") == "\n\n## Node context\nnote\n\n## Says\naudit in website"


def test_host_hooks_without_a_context_return_the_inner_text_only():
    inner = SimpleNamespace(system_addendum=lambda fn: "inner")
    assert HostHooks(inner, publisher=None).system_addendum("audit") == "inner"
