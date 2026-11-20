"""Grants (MAN-2, guardrails 3 and 4; D266 to D269): the role table, the tiers and the intersection, as pure functions. A grant is never wider than the owner's access, tier 6 can not be
held, the planner cannot add a tier, and more restrictions never add one (checked over every combination, not a sample)."""
import itertools
import json
import random
from types import SimpleNamespace

import pytest

from sutra_app.orchestrator import grants
from sutra_app.orchestrator.grants import (
    COMMAND_LEVELS, FOLDER_LEVELS, GRANTABLE_TIERS, OWNER_ACCESS, ROLE_TABLE, ROLES, TOOL_PROFILES, Grant, GrantError, StepRequest, intersect, normalize_scope,
    output_level_of, resolve, scope_width, scopes_overlap,
)
from sutra_app.orchestrator.models import NodeCaps

OUTPUTS = (None, "read", "edit")
WANTS = [frozenset(c) for n in range(7) for c in itertools.combinations(range(1, 7), n)]          # every subset of tiers 1 to 6
APPROVALS = [frozenset(), frozenset({4}), frozenset({5}), frozenset({4, 5, 6})]


def tiers(role, owner, output=None, **step):
    return intersect(role, StepRequest(**step), output, owner).tiers


def combos():
    return itertools.product(ROLES, OUTPUTS, OWNER_ACCESS, TOOL_PROFILES, WANTS, APPROVALS)


# ---- the table, case by case -------------------------------------------------------------------------------------------------------

def test_a_worker_whose_output_only_reads_has_tiers_0_and_1_whatever_the_plan_says():
    ask_everything = {"wants": frozenset({1, 2, 3, 4, 5, 6}), "tool_profile": "sutra+github", "scope": ("site/",)}
    for owner in ("read", "edit"):
        grant = intersect("worker", StepRequest(**ask_everything), "read", owner, approved={4, 5, 6})
        assert grant.tiers[:2] == (0, 1) and not grant.writer and grant.commands == "none" and grant.scope == ()
        assert 2 not in grant.tiers and 3 not in grant.tiers
    assert tiers("worker", "read", "read") == (0, 1)
    assert tiers("worker", "edit", "read") == (0, 1)
    assert tiers("worker", "edit", None) == (0, 1)                                   # no spec at all: read, as workspace_for answers


def test_a_worker_with_an_editing_output_and_an_owner_who_allowed_changes_writes_and_runs_the_builder_tools():
    grant = intersect("worker", StepRequest(scope=("site/pricing/",)), "edit", "edit")
    assert grant.tiers == (0, 1, 2, 3) and grant.folder == "edit" and grant.commands == "git_reads" and grant.tool_profile == "none" and grant.run_tools == "engine"
    assert grant.scope == ("site/pricing/",) and grant.scope_width == "one" and not grant.writes_alone


def test_a_worker_that_writes_without_a_declared_scope_holds_the_whole_folder_and_runs_alone():
    grant = intersect("worker", StepRequest(), "edit", "edit")
    assert grant.writer and grant.scope == () and grant.scope_width == "whole" and grant.writes_alone


def test_a_reviewer_never_writes_and_reads_git_only_when_the_output_edits_and_the_owner_allowed_changes():
    for output, owner in itertools.product(OUTPUTS, OWNER_ACCESS):
        grant = intersect("reviewer", StepRequest(scope=("a/",), wants=frozenset({2})), output, owner, approved={4})
        assert 2 not in grant.tiers and grant.folder != "edit" and grant.scope == () and 4 not in grant.tiers
    assert intersect("reviewer", None, "edit", "edit").tiers == (0, 1, 3)
    assert intersect("reviewer", None, "edit", "edit").folder == "inspect" and intersect("reviewer", None, "edit", "edit").commands == "git_reads"
    assert intersect("reviewer", None, "edit", "read").tiers == (0, 1) and intersect("reviewer", None, "edit", "read").folder == "read"      # read only means no command at all
    assert intersect("reviewer", None, "read", "edit").tiers == (0, 1)
    assert intersect("reviewer", None, "edit", "none").tiers == (0,)


def test_the_planner_thinks_and_sees_plan_data_only():
    for output, owner in itertools.product(OUTPUTS, OWNER_ACCESS):
        grant = intersect("planner", StepRequest(wants=frozenset({1, 2, 3, 4, 5, 6}), scope=("a/",), tool_profile="sutra+github"), output, owner, approved={4})
        assert grant.tiers == (0, 1) and grant.folder == "none" and grant.tool_profile == "none" and grant.commands == "none" and grant.scope == ()


def test_the_planner_cannot_add_a_tier_by_asking():
    plain = {owner: intersect("planner", None, "edit", owner) for owner in OWNER_ACCESS}
    for owner, wants, profile in itertools.product(OWNER_ACCESS, WANTS, TOOL_PROFILES):
        assert intersect("planner", StepRequest(wants=wants, tool_profile=profile), "edit", owner, approved={4, 5, 6}).tiers == plain[owner].tiers == (0, 1)


def test_tier_4_is_only_given_to_a_worker_with_an_approval_for_any_folder_access():
    ask = StepRequest(wants=frozenset({4}))
    assert 4 not in intersect("worker", ask, "edit", "edit").tiers                                           # no approval
    given = intersect("worker", ask, "edit", "edit", approved={4})
    assert given.tiers == (0, 1, 2, 3, 4) and given.tool_profile == "github"                                 # the github part only: no app-database read comes with it
    assert 4 not in intersect("worker", StepRequest(), "edit", "edit", approved={4}).tiers                   # approved but never asked for
    for owner in ("read", "none"):                                                                           # the folder access does not matter for the network (D298)
        assert 4 in intersect("worker", ask, "edit", owner, approved={4}).tiers
        assert 4 not in intersect("worker", ask, "edit", owner).tiers
    assert intersect("worker", ask, "read", "read", approved={4}).tiers == (0, 1, 4)                         # a read-only owner: the folder to read, and the network
    assert intersect("worker", ask, "edit", "none", approved={4}).tiers == (0, 4)                            # no folder at all: tiers 0 and 4 only
    for role in ("reviewer", "planner"):
        assert 4 not in intersect(role, ask, "edit", "edit", approved={4}).tiers                             # a reviewer and the planner never reach the network
        assert "never reaches the network" in resolve(role, ask, "edit", "edit", approved={4}).denied[0].why


def test_a_tier_4_grant_holds_github_only_and_sutra_only_if_the_step_asked_for_it_separately():
    assert intersect("worker", StepRequest(wants=frozenset({4})), "read", "none", approved={4}).tool_profile == "github"
    assert intersect("worker", StepRequest(tool_profile="github"), "read", "none", approved={4}).tool_profile == "github"
    both = intersect("worker", StepRequest(tool_profile="sutra+github"), "read", "none", approved={4})
    assert both.tool_profile == "sutra+github" and both.tiers == (0, 1, 4)
    sutra_only = intersect("worker", StepRequest(tool_profile="sutra+github"), "read", "none")                # asked for both, approved for neither: the sutra part needs no approval
    assert sutra_only.tool_profile == "sutra" and sutra_only.tiers == (0, 1)
    assert resolve("worker", StepRequest(tool_profile="sutra+github"), "read", "none").asks[0].tier == 4
    assert intersect("worker", StepRequest(tool_profile="sutra"), "read", "none", approved={4}).tool_profile == "sutra"     # an approval for tier 4 changes nothing when it was not asked for
    assert intersect("reviewer", StepRequest(tool_profile="sutra+github"), "read", "read", approved={4}).tool_profile == "sutra"


def test_what_a_step_asks_for_and_cannot_have_is_listed_with_a_reason_and_what_the_owner_could_allow_is_asked():
    refused = resolve("worker", StepRequest(wants=frozenset({4, 5, 6})), "edit", "edit")
    assert [ask.tier for ask in refused.asks] == [4] and [denial.tier for denial in refused.denied] == [5, 6]
    assert all(denial.why for denial in refused.denied) and refused.asks[0].why
    read_only = resolve("worker", StepRequest(wants=frozenset({2, 3, 4})), "edit", "read")
    assert [denial.tier for denial in read_only.denied] == [2, 3] and [ask.tier for ask in read_only.asks] == [4]      # the network is still the owner's to allow
    no_edit_output = resolve("worker", StepRequest(wants=frozenset({2})), "read", "edit")
    assert "only reads" in no_edit_output.denied[0].why
    assert resolve("reviewer", StepRequest(wants=frozenset({2})), "edit", "edit").denied[0].why == "A reviewer never changes files"


def test_the_tool_profile_follows_what_was_asked_and_the_role_and_never_gives_github_without_tier_4():
    assert intersect("worker", StepRequest(tool_profile="sutra"), "read", "none").tiers == (0, 1)              # app data is tier 1 even with no folder
    assert intersect("worker", StepRequest(tool_profile="sutra"), "read", "none").tool_profile == "sutra"
    assert intersect("worker", StepRequest(tool_profile="sutra+github"), "edit", "edit").tool_profile == "sutra"     # asked, not approved: only the app tools
    assert intersect("worker", StepRequest(tool_profile="sutra+github"), "edit", "edit", approved={4}).tool_profile == "sutra+github"
    assert intersect("worker", StepRequest(tool_profile="github"), "edit", "edit").tool_profile == "none"
    assert intersect("reviewer", StepRequest(tool_profile="sutra+github"), "read", "read").tool_profile == "sutra"
    assert intersect("worker", StepRequest(), "edit", "edit").tool_profile == "none"                           # deny by default: nothing is on unless asked
    assert intersect("worker", StepRequest(wants=frozenset({4})), "read", "read", approved={4}).tool_profile == "github"
    assert intersect("planner", StepRequest(tool_profile="sutra"), "read", "read").tool_profile == "none"


def test_a_worker_with_no_working_folder_and_no_tools_can_only_think():
    assert intersect("worker", None, "edit", "none").tiers == (0,) and intersect("worker", None, "edit", "none").folder == "none"


# ---- the rules over every combination ---------------------------------------------------------------------------------------------

def rank(order, value):
    return order.index(value)


def test_a_grant_is_never_wider_than_the_owners_access_and_never_holds_tier_5_or_6():
    count = 0
    for role, output, owner, profile, wants, approved in combos():
        grant = intersect(role, StepRequest(wants=wants, tool_profile=profile, scope=("a/", "b/")), output, owner, approved=approved)
        count += 1
        assert set(grant.tiers) <= set(GRANTABLE_TIERS) and 5 not in grant.tiers and 6 not in grant.tiers
        assert set(grant.tiers) <= ROLE_TABLE[role].tiers
        assert rank(FOLDER_LEVELS, grant.folder) <= rank(FOLDER_LEVELS, ROLE_TABLE[role].folder)
        assert rank(COMMAND_LEVELS, grant.commands) <= rank(COMMAND_LEVELS, ROLE_TABLE[role].commands)
        assert rank(TOOL_PROFILES, grant.tool_profile) <= rank(TOOL_PROFILES, ROLE_TABLE[role].profile)
        if role == "planner":
            continue                                                                    # the planner has no folder: the owner's access does not apply to it
        if owner == "none":
            assert grant.folder == "none" and grant.commands == "none" and not set(grant.tiers) & {2, 3}
        if owner == "read":
            assert max(set(grant.tiers) - {4}) <= 1 and grant.folder in ("none", "read") and grant.commands == "none" and not grant.writer         # the folder part only (D298)
        if grant.writer:
            assert role == "worker" and owner == "edit" and (output_level_of(output) == "edit") and 2 in grant.tiers
        if 4 in grant.tiers:
            assert role == "worker" and 4 in approved and (4 in wants or "github" in profile)                    # any folder access: the approval is the control
    assert count == len(ROLES) * len(OUTPUTS) * len(OWNER_ACCESS) * len(TOOL_PROFILES) * len(WANTS) * len(APPROVALS)


def weaker_variants(role, output, owner, profile, wants, approved):
    """Every way of making ONE of the four inputs more restrictive (and the plan's own request smaller)."""
    for lower in OWNER_ACCESS[:OWNER_ACCESS.index(owner)]:
        yield role, output, lower, profile, wants, approved
    if output_level_of(output) == "edit":
        yield role, "read", owner, profile, wants, approved
    if approved:
        yield role, output, owner, profile, wants, frozenset()
    if wants:
        yield role, output, owner, profile, frozenset(), approved
    if profile != "none":
        yield role, output, owner, "none", wants, approved


def test_more_restrictions_never_add_a_tier():
    for combo in combos():
        role, output, owner, profile, wants, approved = combo
        full = intersect(role, StepRequest(wants=wants, tool_profile=profile), output, owner, approved=approved)
        for r, o, ow, pr, w, a in weaker_variants(*combo):
            less = intersect(r, StepRequest(wants=w, tool_profile=pr), o, ow, approved=a)
            assert set(less.tiers) <= set(full.tiers), (combo, (o, ow, pr, w, a))
            assert rank(FOLDER_LEVELS, less.folder) <= rank(FOLDER_LEVELS, full.folder)
            assert rank(COMMAND_LEVELS, less.commands) <= rank(COMMAND_LEVELS, full.commands)
            assert rank(TOOL_PROFILES, less.tool_profile) <= rank(TOOL_PROFILES, full.tool_profile)


def test_what_a_step_asks_for_adds_nothing_but_tier_4_with_an_approval():
    for role, output, owner, profile, wants, approved in combos():
        asked = intersect(role, StepRequest(wants=wants, tool_profile=profile), output, owner, approved=approved)
        plain = intersect(role, StepRequest(tool_profile=profile), output, owner)
        assert set(asked.tiers) - set(plain.tiers) <= {4}
        if asked.tiers != plain.tiers:
            assert 4 in approved and role == "worker"
        assert set(asked.tool_profile.split("+")) - {"github"} <= set(plain.tool_profile.split("+"))               # asking for the network never adds the app-database read


def test_the_same_inputs_give_the_same_grant_whatever_the_order_of_asking():
    rng = random.Random(7)
    for _ in range(200):
        role, output, owner, profile, wants, approved = rng.choice(list(combos()))
        a = intersect(role, StepRequest(wants=wants, tool_profile=profile), output, owner, approved=approved)
        b = intersect(role, StepRequest(wants=frozenset(sorted(wants, reverse=True)), tool_profile=profile), output, owner, approved=sorted(approved, reverse=True))
        assert a == b


# ---- a grant can not be built wider than the table --------------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"role": "worker", "tiers": (0, 1, 6)}, {"role": "worker", "tiers": (0, 1, 5)}, {"role": "worker", "tiers": (0, 1, 7)}, {"role": "worker", "tiers": (1,)},
    {"role": "worker", "tiers": (0, 2, 1)}, {"role": "worker", "tiers": (0, 1, 1)}, {"role": "reviewer", "tiers": (0, 1, 2), "folder": "edit"},
    {"role": "reviewer", "tiers": (0, 1, 4), "tool_profile": "sutra+github"}, {"role": "planner", "tiers": (0, 1, 3)}, {"role": "planner", "tiers": (0, 1), "folder": "read"},
    {"role": "worker", "tiers": (0, 1, 2), "folder": "read"}, {"role": "worker", "tiers": (0, 1), "folder": "edit"}, {"role": "worker", "tiers": (0, 1, 3), "folder": "read"},
    {"role": "worker", "tiers": (0, 1), "folder": "read", "scope": ("a/",)}, {"role": "worker", "tiers": (0, 1, 4), "folder": "read", "tool_profile": "sutra"},
    {"role": "worker", "tiers": (0,), "folder": "read"}, {"role": "worker", "tiers": (0, 1)}, {"role": "owner", "tiers": (0,)}, {"role": "worker", "tiers": (0, True)},
    {"role": "worker", "tiers": (0, 1), "folder": "edit-all"}, {"role": "worker", "tiers": (0, 1, 2, 3), "folder": "edit", "commands": "shell"},
    {"role": "worker", "tiers": (0, 1, 2, 3), "folder": "edit", "commands": "sandboxed_builder"}, {"role": "reviewer", "tiers": (0, 1), "folder": "read", "run_tools": "engine"},
    {"role": "planner", "tiers": (0, 1), "run_tools": "engine"}, {"role": "worker", "tiers": (0, 1), "folder": "read", "run_tools": "everything"},
])
def test_a_grant_that_is_wider_than_the_role_table_or_not_consistent_cannot_be_built(kwargs):
    with pytest.raises(GrantError):
        Grant(**kwargs)


def test_tier_6_cannot_be_in_a_grant_by_any_route():
    for route in (lambda: Grant(role="worker", tiers=(0, 1, 6), folder="read"), lambda: Grant.from_json({"role": "worker", "tiers": [0, 1, 6], "folder": "read"}),
                  lambda: Grant.from_json({"role": "worker", "tiers": [0, 6]})):
        with pytest.raises(GrantError, match="tier 6"):
            route()
    assert 6 not in GRANTABLE_TIERS and 5 not in GRANTABLE_TIERS


def test_a_grant_is_frozen_and_for_node_makes_a_new_one_with_ids():
    grant = intersect("worker", StepRequest(scope=("a/",)), "edit", "edit")
    with pytest.raises(Exception):
        grant.tiers = (0, 1, 2, 3, 4)
    with pytest.raises(Exception):
        grant.node_id = "x"
    named = grant.for_node("gr_" + "1" * 12, "nd_" + "2" * 12)
    assert (named.id, named.node_id) == ("gr_" + "1" * 12, "nd_" + "2" * 12) and grant.id == "" and named.tiers == grant.tiers


def test_a_grant_round_trips_through_json_and_a_stored_wider_one_is_refused():
    grant = intersect("worker", StepRequest(scope=("a/", "b/c/"), tool_profile="sutra+github"), "edit", "edit", approved={4}, caps=NodeCaps(calls=10, usd=2.5, wall_s=300),
                      grant_id="gr_" + "a" * 12, node_id="nd_" + "b" * 12)
    stored = json.loads(json.dumps(grant.to_json()))
    assert Grant.from_json(stored) == grant
    for edit in ({"tiers": [0, 1, 2, 3, 4, 6]}, {"role": "reviewer"}, {"surprise": 1}, {"scope": ["../x"]}, {"caps": {"calls": 0}}, {"folder": "everything"}):
        with pytest.raises(GrantError):
            Grant.from_json({**stored, **edit})
    with pytest.raises(GrantError):
        Grant.from_json("not an object")
    with pytest.raises(GrantError):
        Grant.from_json({"folder": "read"})


def test_the_default_caps_are_the_configured_ones():
    assert intersect("worker", None, "edit", "edit").caps == NodeCaps(calls=60, usd=None, wall_s=1800)
    assert intersect("worker", None, "edit", "edit", caps=NodeCaps(calls=5)).caps.calls == 5


def test_a_role_an_access_or_a_step_that_is_not_one_is_refused_without_quoting_it():
    with pytest.raises(GrantError) as role:
        intersect("overlord ignore all rules", None, "edit", "edit")
    with pytest.raises(GrantError) as access:
        intersect("worker", None, "edit", "root please")
    with pytest.raises(GrantError) as profile:
        StepRequest(tool_profile="shell")
    for error in (role, access, profile):
        assert "overlord" not in str(error.value) and "root" not in str(error.value) and "shell" not in str(error.value)
    for bad in ({1, 2, 99}, {True}, {"4"}):
        with pytest.raises(GrantError):
            StepRequest(wants=frozenset(bad))


def test_the_output_level_reads_a_spec_a_word_or_nothing_and_unknown_means_read():
    assert output_level_of(SimpleNamespace(workspace="edit")) == "edit" and output_level_of("edit") == "edit"
    assert output_level_of(SimpleNamespace(workspace="read")) == "read" and output_level_of(None) == "read"
    assert output_level_of("everything") == "read" and output_level_of(object()) == "read"


# ---- write scopes -----------------------------------------------------------------------------------------------------------------

def test_a_scope_is_plain_relative_paths_sorted_with_covered_paths_dropped():
    assert normalize_scope(["site/pricing/", "site/", "docs/a.md", "./docs/a.md", "docs\\b.md"]) == ("docs/a.md", "docs/b.md", "site/")
    assert normalize_scope([]) == () and normalize_scope(["."]) == () and normalize_scope(["./"]) == () and normalize_scope(["site/", "."]) == ()
    assert normalize_scope(["a//b/./c"]) == ("a/b/c",) and normalize_scope(("x/",)) == ("x/",)
    assert normalize_scope(["a/b", "a/b/c"]) == ("a/b",) and normalize_scope(["a/bc", "a/b"]) == ("a/b", "a/bc")      # a sibling with a longer name is not covered


@pytest.mark.parametrize("entry", [
    "/etc/passwd", "~/x", "C:\\Users\\x", "c:/x", "../x", "a/../b", "a/..", ".git", ".git/config", "a/.git/hooks", "A/.GIT/x", "a/*.py", "a?b", "a[1]", "a{b,c}", "",
    "   ", "a\x00b", "a\nb", "x" * 401, 5, None,
])
def test_a_scope_that_leaves_the_folder_or_touches_git_or_is_not_plain_is_refused(entry):
    with pytest.raises(GrantError):
        normalize_scope(["fine/", entry])


def test_a_scope_has_at_most_50_paths():
    assert len(normalize_scope([f"d{i}/" for i in range(50)])) == 50
    with pytest.raises(GrantError):
        normalize_scope([f"d{i}/" for i in range(51)])


def test_scopes_overlap_when_one_covers_the_other_and_the_whole_folder_overlaps_everything():
    assert scopes_overlap(("site/",), ("site/pricing/",)) and scopes_overlap(("site/pricing",), ("site/",)) and scopes_overlap(("a/", "b/"), ("c/", "b/x"))
    assert not scopes_overlap(("site/",), ("docs/",)) and not scopes_overlap(("a/b",), ("a/bc",)) and not scopes_overlap(("a/", "b/"), ("c/", "d/"))
    assert scopes_overlap((), ("a/",)) and scopes_overlap(("a/",), ()) and scopes_overlap((), ())


def test_scope_width_names_none_one_and_several():
    assert (scope_width(()), scope_width(("a/",)), scope_width(("a/", "b/"))) == ("whole", "one", "wide")
    assert intersect("reviewer", None, "edit", "edit").scope_width == "none" and intersect("worker", StepRequest(scope=("a/", "b/")), "edit", "edit").scope_width == "wide"


def test_a_scope_on_a_step_that_cannot_write_is_checked_and_then_dropped():
    assert intersect("worker", StepRequest(scope=("a/",)), "read", "edit").scope == ()
    with pytest.raises(GrantError):
        intersect("worker", StepRequest(scope=("../outside",)), "read", "edit")           # a bad path is a bad plan even where it would not be used


def test_the_module_lists_what_it_exports():
    assert set(grants.__all__) >= {"intersect", "resolve", "Grant", "ROLE_TABLE", "normalize_scope"}


# ---- J2's builder tools are described, not a tier (D299) ----------------------------------------------------------------------------

def test_a_worker_whose_output_only_reads_has_tiers_0_and_1_and_still_has_the_engines_builder_tools():
    for owner in OWNER_ACCESS:
        grant = intersect("worker", StepRequest(), "read", owner)
        assert grant.run_tools == "engine" and grant.commands == "none" and (grant.tiers == (0, 1) if owner != "none" else grant.tiers == (0,))
    edit = intersect("worker", StepRequest(), "edit", "edit")
    assert edit.tiers == (0, 1, 2, 3) and edit.run_tools == "engine" and edit.commands == "git_reads"


def test_run_tools_are_not_capped_by_the_owners_access_or_the_output_and_are_none_for_the_planner_and_the_reviewer():
    for role, output, owner in itertools.product(ROLES, OUTPUTS, OWNER_ACCESS):
        grant = intersect(role, StepRequest(), output, owner)
        assert grant.run_tools == ("engine" if role == "worker" else "none")
    assert COMMAND_LEVELS == ("none", "git_reads") and grants.RUN_TOOLS == ("none", "engine")


def test_run_tools_are_in_the_json_and_in_the_audit_line_and_a_stored_grant_without_them_reads_as_none():
    grant = intersect("worker", StepRequest(scope=("a/",)), "edit", "edit", grant_id="gr_" + "a" * 12, node_id="nd_" + "b" * 12)
    stored = grant.to_json()
    assert stored["run_tools"] == "engine" and Grant.from_json(stored) == grant
    line = grant.describe()
    assert "run_tools engine" in line and "commands git_reads" in line and "tiers 0,1,2,3" in line and len(line) <= 200
    assert "run_tools none" in intersect("reviewer", None, "edit", "edit").describe()
    old = {k: v for k, v in stored.items() if k != "run_tools"}
    assert Grant.from_json(old).run_tools == "none"
    for bad in ("shell", "", "ENGINE", None):
        with pytest.raises(GrantError):
            Grant.from_json({**stored, "run_tools": bad})
    with pytest.raises(GrantError):
        Grant.from_json({**{**stored, "role": "reviewer", "tiers": [0, 1, 3], "folder": "inspect", "scope": []}, "run_tools": "engine"})


def test_a_grant_never_names_the_old_builder_command_level():
    with open(grants.__file__, encoding="utf-8") as handle:
        assert "sandboxed_builder" not in handle.read()
