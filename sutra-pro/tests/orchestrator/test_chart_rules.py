"""ChartRules (ORCH-5): reuse-first, busy, bad_assignment, classify and the digest, plus a sample of the library's codes through
`ChartStore.check` (the library does the chart arithmetic; this file proves ours is added to it, all violations at once)."""
import pytest
from factories_org import add_op, dept_op, div_op, make_chart, merge_op, move_op, new_node, rename_op, split_op
from orchestrator.test_chart_store import Env

from sutra_app.orchestrator.chart_rules import JACCARD_REUSE, classify, reuse_violations


@pytest.fixture
def built(db, settings, clock, events):
    return Env(db, settings, clock, events).build()


def task(env, n: int, dept: str, status: str = "running", *, scope: str | None = None, title: str | None = None, created: int | None = None) -> str:
    task_id = f"tsk_{n:012x}"
    env.sql("INSERT INTO tasks(id, dept_id, scope_node_id, title, user_text, status, run_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            task_id, dept, scope, title or f"Task {n}", "u", status, f"j2-20261104-1000{n:02d}-aaaa" if status in ("starting", "running", "waiting_user") else None,
            created if created is not None else n)
    return task_id


def codes(found) -> list[tuple[str, str]]:
    return [(v.path, v.code) for v in found]


# ---- classify -------------------------------------------------------------------------------------------------------------------

def test_only_a_rearrange_with_a_merge_or_a_split_needs_the_owner(built):
    kinds = {
        "reuse": built.change(reuses=["web"]),
        "add": built.change(dept_op("$s", "Support")),
        "move": built.change(move_op("menu", "sales")),
        "rename": built.change(rename_op("menu", name="Dishes")),
        "merge": built.change(merge_op("quotes", "leads")),
        "split": built.change(split_op("leads", [new_node("$p", "division", "Warm", "sales")])),
        "add+merge": built.change(div_op("$n", "Extra", "sales"), merge_op("quotes", "leads")),
    }
    assert {k: built.chart.classify(c) for k, c in kinds.items()} == {
        "reuse": "auto", "add": "auto", "move": "auto", "rename": "auto", "merge": "approve", "split": "approve", "add+merge": "approve"}
    assert classify(kinds["merge"].model) == "approve"


# ---- reuse first ----------------------------------------------------------------------------------------------------------------

def test_an_added_node_with_the_name_of_a_live_node_of_its_kind_is_refused_naming_it(built):
    found = built.chart.check(built.change(div_op("$x", "menus", "sales")))
    assert codes(found) == [("ops.0.node.name", "reuse_candidate")]
    assert "Menu" in found[0].message and "(menu)" in found[0].message and "reuse it" in found[0].message


def test_the_same_name_with_other_case_or_plural_counts_as_the_same(built):
    assert ("ops.0.node.name", "reuse_candidate") in codes(built.chart.check(built.change(dept_op("$x", "WEB"))))          # next to the library's duplicate_name
    assert codes(built.chart.check(built.change(dept_op("$x", "Sale")))) == [("ops.0.node.name", "reuse_candidate")]


def test_a_new_node_whose_name_and_purpose_overlap_at_least_half_is_refused(built):
    built.apply(rename_op("web", purpose="Websites and landing pages for shops"))
    found = built.chart.check(built.change(add_op("$x", "department", "Landing pages", "root", "Websites for shops")))
    assert codes(found) == [("ops.0.node.name", "reuse_candidate")]
    assert JACCARD_REUSE == 0.5


def test_an_overlap_of_exactly_one_half_is_already_a_reuse_and_a_third_is_not(built):
    built.apply(div_op("$r", "Roast cafe menu board", "web"))
    assert codes(built.chart.check(built.change(div_op("$x", "Roast cafe", "sales")))) == [("ops.0.node.name", "reuse_candidate")]       # 2 of 4 words
    assert built.chart.check(built.change(div_op("$x", "Roast bar", "sales"))) == []                                                       # 1 of 5 words


def test_a_new_node_below_the_overlap_or_of_another_kind_is_allowed(built):
    assert built.chart.check(built.change(dept_op("$x", "Support"))) == []
    assert built.chart.check(built.change(div_op("$x", "Web", "sales"))) == []                  # a division named like a department: other kind
    assert built.chart.check(built.change(add_op("$x", "department", "Billing", "root", "Invoices and refunds"))) == []


def test_the_reuse_check_looks_at_every_added_node_and_reports_each(built):
    found = built.chart.check(built.change(dept_op("$a", "Sales"), dept_op("$b", "Support"), div_op("$c", "Leads", "web")))
    assert [c for c in codes(found) if c[1] == "reuse_candidate"] == [("ops.0.node.name", "reuse_candidate"), ("ops.2.node.name", "reuse_candidate")]
    assert reuse_violations(built.head(), []) == []


# ---- busy -----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["blocked", "queued", "starting", "running", "waiting_user"])
def test_a_division_with_an_unfinished_task_cannot_move(built, status):
    task(built, 1, "web", status, scope="menu", title="Menu board")
    found = built.chart.check(built.change(move_op("menu", "sales")))
    assert codes(found) == [("ops.0.node", "busy")] and found[0].message == "Menu is busy with Menu board"


def test_a_finished_task_or_a_task_without_a_scope_does_not_make_a_division_busy(built):
    task(built, 1, "web", "done", scope="menu")
    task(built, 2, "web", "running")
    task(built, 3, "web", "crashed", scope="menu")
    assert built.chart.check(built.change(move_op("menu", "sales"))) == []


def test_a_merge_source_and_a_split_node_can_be_busy_and_a_merge_target_is_not(built):
    task(built, 1, "sales", "running", scope="leads", title="Hot leads")
    assert codes(built.chart.check(built.change(merge_op("quotes", "leads")))) == [("ops.0.sources.0", "busy")]
    assert codes(built.chart.check(built.change(merge_op("leads", "quotes")))) == []
    assert codes(built.chart.check(built.change(split_op("leads", [new_node("$p", "division", "Warm", "sales")])))) == [("ops.0.node", "busy")]


def test_a_task_scoped_below_the_division_makes_the_whole_subtree_busy(built):
    built.apply(div_op("$deep", "Deep", "leads"))
    task(built, 1, "sales", "running", scope="deep", title="Deep dive")
    found = built.chart.check(built.change(move_op("leads", "web")))
    assert codes(found) == [("ops.0.node", "busy")] and found[0].message == "Leads (Deep) is busy with Deep dive"


def test_a_rename_is_never_busy(built):
    task(built, 1, "web", "running", scope="menu")
    assert built.chart.check(built.change(rename_op("menu", name="Dishes"))) == []


# ---- the library's codes come through check, all at once, next to ours ----------------------------------------------------------

def test_check_reports_the_library_violations_and_ours_together_in_order(built):
    task(built, 1, "web", "running", scope="menu")
    change = built.change(dept_op("$x", "Sales"), move_op("menu", "ghost"), rename_op("nobody", name="X"), move_op("sales", "web"))
    found = built.chart.check(change)
    got = codes(found)
    assert ("ops.1.to_parent", "unknown_node") in got and ("ops.2.node", "unknown_node") in got and ("ops.3.node", "move_not_division") in got
    assert got[-2:] == [("ops.0.node.name", "reuse_candidate"), ("ops.1.node", "busy")] and len(got) == len(set(got))


def test_a_stale_base_is_the_only_violation_because_the_other_rules_would_judge_the_wrong_chart(built):
    change = built.change(dept_op("$x", "Sales"), base=1)
    assert [(v.path, v.code) for v in built.chart.check(change)] == [("", "stale_base")]


def test_a_few_more_library_codes_reach_the_caller_unchanged(built):
    cases = {
        "bad_parent_kind": div_op("$x", "Thing", "root"),
        "not_a_child": split_op("leads", [new_node("$q", "division", "Warm", "sales")], moves=[("menu", "$q")]),
        "merge_not_division": merge_op("leads", "web"),
        "bad_merge": merge_op("leads", "leads"),
        "split_not_division": split_op("web", [new_node("$p", "division", "Part", "web")]),
    }
    for expected, op in cases.items():
        assert expected in [v.code for v in built.chart.check(built.change(op))], expected


def test_a_change_without_violations_checks_clean(built):
    assert built.chart.check(built.change(reuses=["web"])) == []
    change = built.change(dept_op("$x", "Support"))
    assert built.chart.check(change, chart=built.head()) == []
    other = make_chart({"web": {}})                      # a chart given on purpose is the one judged (here the change is based on another revision)
    assert [v.code for v in built.chart.check(change, chart=other)] == ["stale_base"]


# ---- stage C ---------------------------------------------------------------------------------------------------------------------

def draft(dept: str, scope: str | None = None, follows: str | None = None) -> dict:
    return {"dept": dept, "scope": scope, "follows": follows}


def test_an_assignment_to_a_live_team_with_a_division_scope_and_its_own_task_is_good(built):
    mine = task(built, 1, "web", "done")
    assert built.chart.check_assignments([draft("web"), draft("web", "menu"), draft("web", "menu", mine)]) == []


def test_a_department_that_is_not_live_is_bad_unless_the_change_adds_it(built):
    found = built.chart.check_assignments([draft("support"), draft("leads")])
    assert codes(found) == [("assignments.0.dept", "bad_assignment"), ("assignments.1.dept", "bad_assignment")]      # a division is no department
    assert built.chart.check_assignments([draft("support")], added=["support"]) == []


def test_a_scope_must_be_a_division_under_that_department(built):
    found = built.chart.check_assignments([draft("web", "leads"), draft("web", "web"), draft("web", "ghost")])
    assert codes(found) == [("assignments.0.scope", "bad_assignment"), ("assignments.1.scope", "bad_assignment"), ("assignments.2.scope", "bad_assignment")]


def test_follows_must_be_a_task_of_that_department(built):
    other = task(built, 1, "sales", "done")
    found = built.chart.check_assignments([draft("web", follows=other), draft("web", follows="tsk_00000000ffff")])
    assert codes(found) == [("assignments.0.follows", "bad_assignment"), ("assignments.1.follows", "bad_assignment")]


def test_drafts_may_be_objects_with_attributes(built):
    class Draft:
        dept, scope, follows = "nope", None, None

    assert codes(built.chart.check_assignments([Draft()])) == [("assignments.0.dept", "bad_assignment")]


def test_the_assignment_check_can_use_the_chart_after_stage_b(built):
    after = built.chart.preview(built.change(dept_op("$s", "Support"), div_op("$t", "Tier one", "$s")))
    chart = make_chart({"support": {"tier-one": {}}})
    assert built.chart.check_assignments([draft("support", "tier-one")], chart) == []
    assert after.added == ["support", "tier-one"]


# ---- digest ----------------------------------------------------------------------------------------------------------------------

def test_the_digest_has_one_line_per_department_and_one_indented_line_per_division(built):
    built.apply(rename_op("sales", purpose="Selling things"))
    text = built.chart.digest("anything")
    assert text.splitlines() == [
        "Org chart revision 4. Root id: root.",
        "sales | Sales | Selling things | live: - | last: -",
        "  leads | Leads | ",
        "  quotes | Quotes | ",
        "web | Web |  | live: - | last: -",
        "  menu | Menu | "]


def test_the_digest_shows_the_live_and_the_last_task_of_a_department(built):
    task(built, 1, "web", "done", title="Old site", created=1)
    task(built, 2, "web", "running", title="New site", created=2)
    task(built, 3, "sales", "crashed", title="Quote tool", created=3)
    lines = built.chart.digest("x").splitlines()
    assert "web | Web |  | live: New site | last: New site (running) tsk_000000000002" in lines
    assert "sales | Sales |  | live: - | last: Quote tool (crashed) tsk_000000000003" in lines


def test_the_digest_cuts_long_purposes(built):
    built.apply(rename_op("web", purpose="w" * 200), rename_op("menu", purpose="m" * 200))
    lines = {line.strip().split(" | ")[0]: line for line in built.chart.digest("x").splitlines()[1:]}
    assert "w" * 120 in lines["web"] and "w" * 121 not in lines["web"]
    assert "m" * 80 in lines["menu"] and "m" * 81 not in lines["menu"]


def test_a_digest_over_the_limit_is_cut_at_a_line_and_says_so(built):
    text = built.chart.digest("x", max_chars=120)
    assert len(text) <= 120 and text.splitlines()[-1].startswith("(+") and text.splitlines()[-1].endswith("more not shown)")
    assert text.startswith("Org chart revision 3.")
    assert "\n".join(built.chart.digest("x").splitlines()[:2]) in text
    with pytest.raises(ValueError):
        built.chart.digest("x", max_chars=10)


def test_over_forty_departments_keep_the_best_matches_and_every_busy_one(built):
    ops = [dept_op(f"$d{i}", f"Team{i:02d} {'coffee' if i == 41 else 'misc'}") for i in range(1, 46)]
    for start in range(0, 45, 8):
        built.apply(*ops[start:start + 8])
    task(built, 1, "team40-misc", "running", title="Busy one")
    text = built.chart.digest("coffee roasting", max_chars=20_000)
    kept = [line.split(" | ")[0] for line in text.splitlines() if "|" in line and not line.startswith(" ")]
    assert len(kept) == 25 + 1                                           # the best 25 plus the one busy team outside them
    assert kept[:3] == ["sales", "web", "team01-misc"] and "team41-coffee" in kept and "team40-misc" in kept
    assert "team45-misc" not in kept
    assert text.splitlines()[-1] == f"(+{47 - len(kept)} more teams not shown)"


def test_forty_one_departments_are_cut_to_the_best_twenty_five(built):
    ops = [dept_op(f"$d{i}", f"Team{i:02d} Thing") for i in range(1, 40)]
    for start in range(0, 39, 8):
        built.apply(*ops[start:start + 8])
    text = built.chart.digest("x", max_chars=50_000)
    assert len([line for line in text.splitlines() if "|" in line and not line.startswith(" ")]) == 25
    assert text.splitlines()[-1] == "(+16 more teams not shown)"


def test_a_forty_department_chart_is_not_cut_by_the_team_rule(built):
    ops = [dept_op(f"$d{i}", f"Team{i:02d} Thing") for i in range(1, 39)]
    for start in range(0, 38, 8):
        built.apply(*ops[start:start + 8])
    assert len(built.head().nodes) - 1 - 3 == 40            # 40 departments (sales, web and 38 more) and 3 divisions
    text = built.chart.digest("x", max_chars=50_000)
    assert "more teams not shown" not in text and "team38-thing" in text
