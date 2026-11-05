"""atom/1, J2's view of an atom (library design section 7; WP L4): `atom_view` equals J2's own `j2_schema.atom_view` on cases
built once from J2's stored atoms (tests/library/fixtures/atom/view_cases.json, made by build_view_cases.py from J2's saved
runs), the status rules, the run-level ports (link_views, run_views, validate_views) and `ledger_row_from_view`.

Known differences from J2, each tested below: an explicit `count: 1` on an expected item is the default and is not echoed;
a check that could not run is exit 127 here and counts as a failed try (library design risk 11); J2's `how` for a deed
atom is `{agent}` only, while the library always writes kind, agent and steps."""
import json

import pytest
from pydantic import ValidationError

from factories_atom import ATOM_ID, atom_from_j2, check, closed, load_view_cases, opened, refused, tried, verify_failed_atom, work
from sutra_app.library.atom import (
    Atom, AtomEdge, AtomError, AtomView, ExpectedItem, LedgerRow, OutputItem, abandon_atom, atom_kind, atom_view, dedupe_edges,
    dependency_edges, ledger_row_from_view, link_views, run_views, validate_atom, validate_views,
)
from sutra_app.library.gate import GATE

J2_KEYS = ["schema", "id", "workflow", "name", "owner", "status", "attempt", "goal", "how", "constraints", "context", "defined_output",
           "verification", "output", "depends_on", "used_by", "notes", "details"]
CASES = load_view_cases()
PAGE = OutputItem(verb="make", name="Hero section", form="page", ref="site/index.html#hero")
FILE = OutputItem(verb="make", name="site/index.html", form="page", ref="site/index.html")


def with_output(atom, *items):
    return atom.evolve(produced=list(items))


def wf(status, name="Plan"):
    return {"name": name, "status": status}


# ---- parity with J2 -----------------------------------------------------------------------------------------------------

def test_the_cases_cover_real_atoms_and_the_cases_built_from_them():
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names)) == 12
    assert {"website_section_closed", "document_section_closed", "behaviour_steps_closed", "send_deed_closed"} <= set(names)
    assert {c["view"]["status"] for c in CASES} == {"open", "closed", "verify_failed", "abandoned"}
    assert all(set(c["view"]) >= set(J2_KEYS) for c in CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_atom_view_equals_j2s_atom_view(case):
    view = case["view"]
    atom = atom_from_j2(case["j2_atom"], produced=view["output"], details=view["details"])
    mine = atom_view(atom, case["workflow"], case["edges"], case["ended"],
                     stale=case["j2_atom"].get("board_stale"), rechecked=case["j2_atom"].get("board_rechecked"))
    assert mine.wire() == view
    assert GATE.check("atom_view", view).model == mine


def test_the_view_has_exactly_the_keys_of_atom_1_and_stale_rechecked_only_when_set():
    wire = atom_view(opened(id="W-1.a1")).wire()
    assert list(wire) == J2_KEYS and wire["schema"] == "atom/1"
    marked = atom_view(opened(id="W-1.a1"), stale="Q-3", rechecked="Q-4").wire()
    assert (marked["stale"], marked["rechecked"]) == ("Q-3", "Q-4") and list(marked)[:18] == J2_KEYS


def test_a_view_is_a_gated_payload_that_reads_back_by_its_json_key_schema():
    view = atom_view(closed(id="W-2.a1", workflow_id="W-2"), wf("done"))
    checked = GATE.check("atom_view", json.loads(view.canonical_json()))
    assert checked.model == view and checked.family == "atom_view" and '"schema":"atom/1"' in checked.json
    for bad in ({"schema": "atom/2"}, {"status": "refused"}, {"colour": "red"}, {"attempt": 4}):
        with pytest.raises(ValidationError):
            AtomView.model_validate({**view.wire(), **bad})


def test_j2s_explicit_count_of_one_is_the_default_and_is_not_echoed():
    atom = opened(id="W-1.a1", expected=[ExpectedItem(text="a", kind="element", target="#a", count=1),
                                         ExpectedItem(text="b", kind="element", target="#b", count=4, met=True)])
    assert atom_view(atom).defined_output == [{"text": "a", "kind": "element", "target": "#a"},
                                              {"text": "b", "kind": "element", "target": "#b", "count": 4, "met": True}]


# ---- status --------------------------------------------------------------------------------------------------------------

def j2_status_table():
    """j2_flow_test.py's own table: (J2 status, workflow status, run ended, attempts) -> atom/1 status. A library atom
    stands for each J2 status: passed -> closed, escalated -> verify_failed, failed -> an open atom with failed tries,
    no status -> an open atom nobody checked."""
    def lib(status, attempts):
        return {"passed": closed, "escalated": verify_failed_atom, None: opened}.get(status, lambda: tried(opened(), attempts))()
    rows = [("passed", "done", False, 1, "closed"), ("escalated", "done", False, 1, "verify_failed"),
            ("failed", "failed", False, 1, "verify_failed"), ("failed", "done", False, 1, "verify_failed"),
            ("failed", "running", False, 3, "verify_failed"), ("failed", "running", False, 1, "open"),
            (None, "registered", False, 1, "open"), (None, "held", False, 1, "open"), (None, "running", False, 1, "open"),
            (None, "held", True, 1, "abandoned"), (None, "registered", True, 1, "abandoned"), (None, "unfunded", False, 1, "abandoned"),
            (None, "done", True, 1, "open")]
    return [(lib(s, a), ws, ended, want, f"{s}/{ws}/{'ended' if ended else 'live'}/{a}") for s, ws, ended, a, want in rows]


@pytest.mark.parametrize("atom,ws,ended,want,name", j2_status_table(), ids=[r[4] for r in j2_status_table()])
def test_status_matches_j2s_table(atom, ws, ended, want, name):
    assert atom_view(atom, wf(ws), ended=ended).status == want


def test_a_check_that_could_not_run_is_a_failed_try_here_where_j2_leaves_it_open():
    """Library design risk 11: 'could not run' is exit 127 and consumes an attempt, so the view may say verify_failed
    earlier than J2 (which says open for these two rows of its table)."""
    a = tried(opened(), 1, exit_code=127)
    assert atom_view(a, wf("done")).status == "verify_failed"
    assert atom_view(a, wf("held"), ended=True).status == "verify_failed"
    assert atom_view(a, wf("running")).status == "open"


def test_mapping_of_stored_state_to_view_status():
    assert atom_view(closed()).status == "closed"
    assert atom_view(abandon_atom(opened(), "stopped", 130).atom).status == "abandoned"
    assert atom_view(abandon_atom(opened(), "run ended", 130, code="run_ended").atom).status == "abandoned"
    assert atom_view(verify_failed_atom()).status == "verify_failed"            # abandoned with abandon_code verify_failed
    assert atom_view(opened()).status == "open"


def test_open_atoms_without_a_workflow_are_final_only_at_attempt_three_with_a_failing_last_result():
    assert atom_view(tried(opened(), 1)).status == "open"           # the library table: only attempt 3 is final here
    assert atom_view(tried(opened(), 2)).status == "open"
    assert atom_view(tried(opened(), 3)).status == "verify_failed"
    assert atom_view(tried(opened(), 3), wf("running")).status == "verify_failed"
    assert atom_view(tried(opened(), 1), wf("failed")).status == "verify_failed"
    ok_then_pass = closed(tries=2)
    assert atom_view(ok_then_pass, wf("failed")).status == "closed"


def test_a_refused_atom_shows_as_abandoned_with_the_refusal_in_details():
    view = atom_view(refused())
    assert view.status == "abandoned" and view.attempt is None
    assert view.details == {"refusal": {"code": "goal_banal", "message": "goal is banal ('done'): state the observable outcome"}}
    assert atom_view(refused(goal="")).goal is None
    assert "refused" not in {atom_view(a).status for a in (refused(), closed(), opened())}


# ---- the fields ----------------------------------------------------------------------------------------------------------

def test_verification_has_one_row_per_result_of_every_attempt_oldest_first():
    a = tried(opened(check("file-exists", text="Index exists"), check("grep-count", text="Heading found")), 2)
    a = with_output(a, FILE)
    rows = atom_view(a).verification
    assert [(r.method, r.evidence, r.met) for r in rows] == [
        ("file-exists: Index exists", "missing", False), ("grep-count: Heading found", "missing", False)] * 2
    assert len(rows) == 4 and atom_view(opened()).verification == [] and all(r.applies_to == "site/index.html" for r in rows)


@pytest.mark.parametrize("template,kind", [
    ("file-exists", "exists"), ("element-count", "exists"), ("grep-count", "exists"), ("heading-present", "exists"),
    ("section-not-empty", "exists"), ("facts-present", "meets the defined output"), ("lld-slice", "meets the defined output"),
    ("named-test", "valid"), ("tap-targets", "valid"), ("ids-unique", "valid"), ("turn-posted", "valid"), ("reply-valid", "valid"),
    ("behavior-steps", "receipt"), ("deed-send", "receipt"),
])
def test_the_kind_of_check_follows_the_template(template, kind):
    args = {"grep-count": ["a", "b.html", "1"], "named-test": ["t.sh"], "reply-valid": ["priority", "price"], "file-exists": ["a.html"]}.get(template, [])
    row = atom_view(tried(opened(check(template, args)), 1)).verification[0]
    assert row.check == kind


def test_applies_to_is_cut_to_its_bound():
    long = check("facts-present", ["x" * 500] * 8, text="Eight long facts")
    row = atom_view(tried(opened(long), 1)).verification[0]
    assert len(row.applies_to) == 4000 and row.applies_to.endswith("…")


def test_a_deed_check_names_its_own_text_and_gives_the_receipt_id_as_evidence():
    a = tried(opened(check("behavior-steps", ["click #go"], text="Total updates"), id="W-9.a1"), 1)
    row = atom_view(a).verification[0]
    assert (row.check, row.applies_to, row.evidence, row.method) == ("receipt", "Total updates", "W-9.a1:1", "behavior-steps: Total updates")


def test_a_make_check_applies_to_the_page_section_else_the_first_make_else_its_arguments():
    one = tried(opened(check("element-count", ["#hero", "#nav"], text="Two parts")), 1)
    assert atom_view(one).verification[0].applies_to == "#hero, #nav"                      # no output: the targets
    assert atom_view(with_output(one, FILE)).verification[0].applies_to == "site/index.html"
    assert atom_view(with_output(one, FILE, PAGE)).verification[0].applies_to == "Hero section"      # the section with a "#" wins
    deed = OutputItem(verb="do", name="Click", form="behaviour", ref="W-1.a1:1")
    assert atom_view(with_output(one, deed)).verification[0].applies_to == "#hero, #nav"
    assert atom_view(tried(opened(check("turn-posted")), 1)).verification[0].applies_to is None


def test_name_workflow_owner_attempt_and_goal():
    a = opened(id="W-3.a1", workflow_id="W-3")
    v = atom_view(a, wf("running", "Menu section"))
    assert (v.name, v.workflow, v.owner, v.attempt, v.goal) == ("Menu section", "W-3", "Builder", None, "Visitors can open the contact form")
    assert atom_view(with_output(opened(id="W-4.a1"), PAGE)).name == "Hero section" and atom_view(opened(id="W-4.a1")).name == "W-4.a1"
    assert atom_view(opened(id="W-4.a1")).workflow == "W-4" and atom_view(opened()).workflow == ATOM_ID
    assert atom_view(tried(opened(), 2)).attempt == 2
    assert atom_view(opened(id="W-5.a1", workflow_id="W-9")).workflow == "W-9"


def test_how_constraints_context_notes_and_details_pass_through():
    a = opened(constraints=[{"text": "Keep the nav"}], context=["charter item 1"], work=work("llm", agent="W-1 Builder", steps="Make it"))
    a = a.evolve(notes="This adds a contact form.", details={"selectors": ["#contact"], "section": "W-1"})
    v = atom_view(a)
    assert v.how.model_dump() == {"kind": "AI", "agent": "W-1 Builder", "steps": "Make it"} and v.owner == "W-1 Builder"
    assert (v.constraints, v.context, v.notes, v.details) == (["Keep the nav"], ["charter item 1"], "This adds a contact form.",
                                                              {"selectors": ["#contact"], "section": "W-1"})
    assert atom_view(opened(kind="bash")).how.kind == "code" and atom_view(opened(work=work("bash", agent=None))).owner is None


def test_edges_are_the_atoms_own_dependencies_plus_the_given_ones_without_repeats():
    own = AtomEdge(atom="W-2.a1", why="it builds the page")
    a = opened(id="W-1.a1", depends_on=[own])
    v = atom_view(a, edges=[{"atom": "W-3.a1", "why": "LLD slice hero"}, own, {"atom": "W-3.a1", "why": "LLD slice hero"}])
    assert [(e.atom, e.why) for e in v.depends_on] == [("W-2.a1", "it builds the page"), ("W-3.a1", "LLD slice hero")]
    assert v.used_by == [] and atom_view(a, edges=()).depends_on == [own]
    assert dedupe_edges([own, own, {"atom": "W-2.a1", "why": "another reason"}]) == [own, AtomEdge(atom="W-2.a1", why="another reason")]


# ---- the run-level ports -------------------------------------------------------------------------------------------------

def workflow(n, atoms, status="done", **over):
    return {"id": f"W-{n}", "proposal_id": f"p{n}", "name": f"Plan {n}", "status": status, "dependencies": [], "atoms": atoms, **over}


def build_run():
    a1 = with_output(closed(id="W-1.a1", workflow_id="W-1"), PAGE)
    a2 = with_output(closed(id="W-2.a1", workflow_id="W-2"), FILE)
    a3 = closed(id="W-3.a1", workflow_id="W-3")
    return [workflow(1, [a1]), workflow(2, [a2], dependencies=["p1"]), workflow(3, [a3], dependencies=["p1", "p2"])]


def test_dependency_edges_come_from_declared_dependencies():
    wfs = build_run()
    assert [(e.atom, e.why) for e in dependency_edges(wfs[1], wfs)] == [("W-1.a1", "its workflow depends on Plan 1")]
    assert [e.atom for e in dependency_edges(wfs[2], wfs)] == ["W-1.a1", "W-2.a1"]
    assert dependency_edges(wfs[0], wfs) == [] and dependency_edges({"dependencies": ["nope"]}, wfs) == []


def test_run_views_link_used_by_as_the_inverse_of_depends_on():
    views, warnings = run_views(build_run())
    by = {v.id: v for v in views}
    assert [e.atom for e in by["W-3.a1"].depends_on] == ["W-1.a1", "W-2.a1"] and by["W-1.a1"].depends_on == []
    assert sorted(e.atom for e in by["W-1.a1"].used_by) == ["W-2.a1", "W-3.a1"] and [e.atom for e in by["W-2.a1"].used_by] == ["W-3.a1"]
    pairs = {(v.id, e.atom) for v in views for e in v.depends_on}
    assert pairs == {(e.atom, v.id) for v in views for e in v.used_by} and warnings == []
    assert [v.name for v in views] == ["Plan 1", "Plan 2", "Plan 3"]


def test_what_a_builders_prompt_held_beats_the_declared_dependencies():
    wfs = build_run()
    given = {"W-2": {"edges": [{"atom": "W-1.a1", "why": "its section was listed in this prompt"}], "whole": False},
             "W-3": {"edges": [], "whole": False}}
    by = {v.id: v for v in run_views(wfs, given)[0]}
    assert [e.why for e in by["W-2.a1"].depends_on] == ["its section was listed in this prompt"] and by["W-3.a1"].depends_on == []
    whole = {"W-3": {"edges": [], "whole": True}}
    assert [e.atom for e in {v.id: v for v in run_views(wfs, whole)[0]}["W-3.a1"].depends_on] == ["W-1.a1", "W-2.a1"]


def test_an_atom_is_never_its_own_dependency_and_the_run_view_gets_the_run_flags():
    wfs = [workflow(1, [opened(id="W-1.a1", workflow_id="W-1")], status="held")]
    given = {"W-1": {"edges": [{"atom": "W-1.a1", "why": "itself"}], "whole": False}}
    views, _ = run_views(wfs, given, ended=True)
    assert views[0].depends_on == [] and views[0].status == "abandoned"


def test_warnings_for_dangling_edges_cycles_unused_outputs_and_mixed_atoms():
    done = lambda i: closed(id=f"W-{i}.a1", workflow_id=f"W-{i}")
    v1, v2, v3 = (atom_view(done(i), wf("done")) for i in (1, 2, 3))
    dangling = v1.evolve(depends_on=[AtomEdge(atom="W-9.a1", why="x")])
    assert validate_views([dangling]) == ["W-1.a1: depends on W-9.a1, which is not an atom of this run"]
    assert validate_atom(dangling) == [] and validate_atom(dangling, {"W-1.a1"}) == validate_views([dangling])
    a = v1.evolve(depends_on=[AtomEdge(atom="W-2.a1", why="x")])
    b = v2.evolve(depends_on=[AtomEdge(atom="W-3.a1", why="x")])
    c = v3.evolve(depends_on=[AtomEdge(atom="W-1.a1", why="x")])
    assert validate_views([a, b, c]) == ["cycle: W-1.a1 -> W-2.a1 -> W-3.a1 -> W-1.a1"]
    unused = v1.evolve(output=[OutputItem(verb="make", name="n", form="code", ref="x.py")])
    assert validate_views([unused]) == ["W-1.a1: its output is never used and is not a final output"]
    final = v1.evolve(output=[PAGE])
    assert validate_views([final]) == []
    mixed = v1.evolve(output=[PAGE, OutputItem(verb="do", name="Click", form="behaviour", ref="W-1.a1:1")])
    assert validate_views([mixed]) == ["info: W-1.a1 is a mixed atom (1 make, 1 do)"]


def test_atom_kind_is_derived_from_the_output_verbs():
    do = OutputItem(verb="do", name="Click", form="behaviour", ref="W-1.a1:1")
    assert atom_kind(atom_view(opened())) == "make"                                  # no output counts as make (J2)
    assert atom_kind(atom_view(with_output(opened(), PAGE))) == "make"
    assert atom_kind(atom_view(with_output(opened(), do))) == "do"
    assert atom_kind(atom_view(with_output(opened(), PAGE, do))) == "mixed"


def test_link_views_returns_new_views_and_ignores_edges_to_atoms_outside_the_run():
    a = atom_view(closed(id="W-1.a1", workflow_id="W-1"))
    b = atom_view(closed(id="W-2.a1", workflow_id="W-2"), edges=[{"atom": "W-1.a1", "why": "x"}, {"atom": "W-7.a1", "why": "gone"}])
    linked = link_views([a, b])
    assert a.used_by == [] and [e.atom for e in linked[0].used_by] == ["W-2.a1"] and linked[1].used_by == []
    assert link_views([linked[0], linked[1]]) == linked                                     # idempotent: used_by is rebuilt, not added to


# ---- ledger_row_from_view ------------------------------------------------------------------------------------------------

def view_of(name):
    return AtomView.model_validate(next(c["view"] for c in CASES if c["name"] == name))


@pytest.mark.parametrize("name,status,exit_code,reason", [
    ("website_section_closed", "closed", 0, None),
    ("failed_try_workflow_failed", "verify_failed", 1, "Visitors now see your full menu with all seven items and their prices in rupees, in a warm coffee-shop look."),
    ("never_funded", "abandoned", None, "abandoned: the run ended before this atom was built"),
])
def test_each_terminal_j2_status_gives_a_valid_ledger_row(name, status, exit_code, reason):
    view = view_of(name)
    row = ledger_row_from_view(view, "s-0123456789", "sales", now=555)
    assert isinstance(row, LedgerRow) and row.status == status == view.status
    assert (row.atom_id, row.node_id, row.department_id, row.goal, row.ts) == (view.id, "s-0123456789", "sales", view.goal, 555)
    assert (row.verify.exit_code if row.verify else None) == exit_code and row.reason == reason
    assert (row.model, row.effort, row.touches, row.relevance, row.session_id) == (None, None, [], None, None)
    assert GATE.check("atom_ledger_row", row).model == row


def test_the_template_is_the_check_type_before_the_colon_of_the_first_method():
    view = view_of("website_section_closed")
    first = view.verification[0].method
    row = ledger_row_from_view(view, "s-0123456789", None)
    assert row.verify.template == first.split(":")[0] and row.department_id is None and row.ts == 0
    doc = ledger_row_from_view(view_of("document_section_closed"), "s-0123456789", None)
    assert doc.verify.template == "heading-present"


def test_attempt_is_the_views_or_zero():
    assert ledger_row_from_view(view_of("website_section_closed"), "s-0123456789", None).attempt == 1
    assert ledger_row_from_view(view_of("never_funded"), "s-0123456789", None).attempt == 0


def test_the_reason_comes_from_details_then_the_refusal_then_the_notes():
    base = view_of("never_funded")
    assert ledger_row_from_view(base.evolve(details={"reason": "unfunded by Priority"}, notes="n"), "n1", None).reason == "unfunded by Priority"
    refusal = {"refusal": {"code": "goal_banal", "message": "goal is banal"}}
    assert ledger_row_from_view(base.evolve(details=refusal, notes="n"), "n1", None).reason == "goal is banal"
    assert ledger_row_from_view(base.evolve(details={}, notes="Never built."), "n1", None).reason == "Never built."
    assert ledger_row_from_view(base.evolve(details={"reason": "  "}, notes=""), "n1", None).reason.startswith("abandoned")
    assert ledger_row_from_view(view_of("website_section_closed"), "n1", None).reason is None


def test_a_verify_failed_row_without_words_of_its_own_gives_the_first_unmet_evidence():
    failed = view_of("failed_try_workflow_failed").evolve(details={}, notes="")
    row = ledger_row_from_view(failed, "n1", None)
    assert row.reason == "verify failed: '#hero' found 0 time(s) in index.html, expected 1" and row.verify.exit_code == 1
    bare = failed.evolve(verification=[failed.verification[0].evolve(met=True)])
    assert ledger_row_from_view(bare, "n1", None).reason == "verify failed"


def test_a_view_that_is_still_open_has_no_row_and_one_without_checks_cannot_give_a_closed_row():
    with pytest.raises(AtomError) as caught:
        ledger_row_from_view(view_of("never_checked_open"), "s-0123456789", None)
    assert caught.value.code == "not_terminal"
    with pytest.raises(ValidationError):
        ledger_row_from_view(view_of("website_section_closed").evolve(verification=[]), "s-0123456789", None)


def test_the_atoms_own_ledger_row_and_the_views_agree_on_the_status():
    for atom in (closed(id="W-1.a1"), verify_failed_atom(id="W-2.a1")):
        view = atom_view(atom)
        assert ledger_row_from_view(view, atom.node_id, None).status == view.status
    assert Atom.FAMILY == "atom"
