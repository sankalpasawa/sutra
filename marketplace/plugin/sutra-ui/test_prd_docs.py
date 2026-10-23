"""test_prd_docs.py -- the PRD's design documents that the build reads (sutra-ui/design).

M6.1's done check is a document, not code: the J2.b proposal (PRD-FIVE-FUNCTIONS-J2B.md) and
its three prototype runs exist and are linked from MK-3 in the decision log. M6.3 to M6.5
build from that file, so this is the law for it: MK-3 links it, the three runs are named and
attached with their plans and costs, every J2B row is marked keep, each worked example's
covers name every done-when item, a plan that may run in a website department keeps Check
(Q12), a shaped engine that a Library engine reads writes in that engine's form, and the
body stays about two pages, with the detail in its appendices.

Reads files only; touches no registry. The runs themselves live in the J2 prototype, outside
this repository: set J2_PROTOTYPE to its checkout to check them too.
"""
import os
import re

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.join(HERE, "design")
PROPOSAL = os.path.join(DESIGN, "PRD-FIVE-FUNCTIONS-J2B.md")
DECISIONS = os.path.join(DESIGN, "PRD-FIVE-FUNCTIONS-DECISIONS.md")
RUNS = ("j2-20261013-165916", "j2-20261014-111512", "j2-20261016-160511")
RUN_FILES = ("report.json", "calls.jsonl", "workflows.json")
BODY_MAX_WORDS = 1250                    # 'a two-page proposal' (PRD M6.1), tables included
ROW = re.compile(r"^J2B-(\d+)\b")
ITEM = re.compile(r"\bD(\d+)\b")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _sections(text, level="## "):
    """Each heading at this level, with the text under it up to the next one."""
    out, head = {}, None
    for line in text.splitlines():
        if line.startswith(level):
            head = line[len(level):].strip()
            out[head] = []
        elif head is not None:
            out[head].append(line)
    return {h: "\n".join(lines) for h, lines in out.items()}


def _section(text, prefix, level="## "):
    found = [body for head, body in _sections(text, level).items() if head.startswith(prefix)]
    assert len(found) == 1, "one section headed %r" % prefix
    return found[0]


def _table(text):
    """The first markdown table in the text, as one dict per row keyed by its header."""
    rows = [line for line in text.splitlines() if line.startswith("|")]
    assert len(rows) >= 3, "a table with a header, a rule and a row"
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head = cells[0]
    return [dict(zip(head, r)) for r in cells[2:]]


def _words(text):
    return len([w for w in text.split() if re.search(r"[A-Za-z0-9]", w)])


@pytest.fixture(scope="module")
def proposal():
    assert os.path.isfile(PROPOSAL), "the M6.1 proposal is in design/"
    return _read(PROPOSAL)


def _examples(text):
    return _sections(_section(text, "Three worked examples"), "### ")


def test_mk3_links_the_proposal_and_names_its_three_runs():
    row = next((line for line in _read(DECISIONS).splitlines() if line.startswith("| MK-3 ")), "")
    assert row, "the decision log has an MK-3 row"
    assert "](PRD-FIVE-FUNCTIONS-J2B.md)" in row, "MK-3 links the proposal"
    for run in RUNS:
        assert run in row, "MK-3 names the run %s" % run


def test_the_three_runs_are_named_and_attached_with_plan_and_cost(proposal):
    head = proposal.split("\n## ", 1)[0]
    attached = {r.get("Run"): r for r in _table(_section(proposal, "Appendix C"))}
    for run in RUNS:
        assert run in head, "the header names the run %s" % run
        row = attached.get(run)
        assert row, "the runs appendix has a row for %s" % run
        assert row.get("Plan (workflow: covers)"), "%s: its plan is attached" % run
        assert "calls" in row.get("Cost", "") and "credits" in row["Cost"], "%s: its cost is attached" % run


def test_the_runs_exist_in_the_prototype():
    root = os.environ.get("J2_PROTOTYPE")
    if not root:
        pytest.skip("J2_PROTOTYPE is not set; the runs live in the J2 prototype's checkout")
    for run in RUNS:
        for name in RUN_FILES:
            assert os.path.isfile(os.path.join(root, "runs", run, name)), "%s has %s" % (run, name)


def test_every_proposal_row_is_marked_keep(proposal):
    rows = [ROW.match(r["Row"]) for r in _table(_section(proposal, "The proposal"))]
    proposed = [int(m.group(1)) for m in rows if m]
    assert proposed == list(range(1, len(proposed) + 1)) and len(proposed) >= 3, "rows J2B-1 to J2B-n, in order"
    marked = {}
    for r in _table(_section(proposal, "Marked")):
        m = ROW.match(r["Row"])
        if m:
            marked[int(m.group(1))] = r["Mark"]
    assert sorted(marked) == proposed, "every proposed row is marked, and only those"
    assert set(marked.values()) == {"keep"}, "the decision log takes every row as keep"


def test_the_rules_keep_a_kinds_required_engines(proposal):
    """Rule 5 and Q12: when Make runs, what it reads and what code checks all name the kind's required engines."""
    rows = {ROW.match(r["Row"]).group(1): r["What the build does"] for r in _table(_section(proposal, "The proposal")) if ROW.match(r["Row"])}
    for n in ("1", "2", "6"):
        assert "required" in rows[n], "J2B-%s names the kind's required engines" % n
    assert "cannot" in rows["1"] and "cannot" in rows["4"], "a required engine that cannot serve the goal is an answer, not a plan"


def test_each_example_covers_every_done_when_item(proposal):
    examples = _examples(proposal)
    assert len(examples) == 3, "three worked examples"
    for head, body in examples.items():
        items_line = next((line for line in body.splitlines() if line.startswith("Items:")), "")
        items = {int(n) for n in ITEM.findall(items_line)}
        assert items == set(range(1, len(items) + 1)) and items, "%s: items D1 to Dn" % head
        engines = _table(body)
        assert 2 <= len(engines) <= 5, "%s: two to five engines" % head
        covered = set()
        for e in engines:
            got = {int(n) for n in ITEM.findall(e["Covers"])}
            assert got, "%s: %s covers something" % (head, e["Engine"])
            covered |= got
            conf = re.search(r"\d(?:\.\d+)?", e["Confidence"])
            assert conf and 0 <= float(conf.group(0)) <= 1, "%s: %s has a confidence from 0 to 1" % (head, e["Engine"])
            assert e["Level"].startswith(("L1", "L2")), "%s: %s has a level" % (head, e["Engine"])
        assert covered == items, "%s: the covers name every item, and only those" % head


def test_a_plan_that_may_run_in_a_website_department_keeps_check(proposal):
    """Q12: Check is the website kind's one required engine; an example that a website department can reach keeps it."""
    for head, body in _examples(proposal).items():
        if "website" not in head.lower():
            continue
        check = [e for e in _table(body) if e["Engine"] == "Check"]
        assert check and check[0]["Level"].startswith("L1"), "%s: Check is taken from the Library and kept" % head


def test_a_shaped_writer_that_a_library_engine_reads_writes_in_its_form(proposal):
    """J2B-3: a level-1 engine reads a Library artifact only in the form it reads (Pages: Check's form)."""
    for head, body in _examples(proposal).items():
        engines = _table(body)
        flow = [(e, [s.strip() for s in e["Reads > writes"].split(">")]) for e in engines]
        read_by_l1 = {rw[0] for e, rw in flow if e["Level"].startswith("L1")}
        for e, (reads, writes) in flow:
            if e["Level"].startswith("L2") and writes in read_by_l1:
                assert "form" in e["Does"], "%s: %s writes %s in the form the Library engine reads" % (head, e["Engine"], writes)


def test_the_body_is_about_two_pages(proposal):
    body = sum(_words(text) for head, text in _sections(proposal).items() if not head.startswith("Appendix"))
    body += _words(proposal.split("\n## ", 1)[0])
    assert body <= BODY_MAX_WORDS, "the body is %d words; the detail belongs in an appendix" % body
    assert any(h.startswith("Appendix") for h in _sections(proposal)), "the detail has an appendix"
