"""The document reader (D455): sutra_app/engine/doc_reader.py renders the authored Markdown, adds nothing from the run, and draws the
navigation, the ledger rows, the diagrams and the example block. Offline: the fixture is tests/fixtures/doc_reader/fixture_prd.md."""
import html
import re
from pathlib import Path

from sutra_app.engine import doc_reader as r

FIX = (Path(__file__).resolve().parents[1] / "fixtures" / "doc_reader" / "fixture_prd.md").read_text(encoding="utf-8")


def page(md=FIX, **kw):
    return r.reader_html(md, kw.pop("title", "fixture_prd.md"), kw.pop("meta", None), **kw)


def text_of(h):
    body = re.sub(r"<script>.*?</script>|<style>.*?</style>|<svg.*?</svg>|<pre class=\"src\".*?</pre>", " ", h, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)))


def test_every_authored_word_is_in_the_preview_and_nothing_from_the_run():
    shown = re.sub(r"\s+", " ", text_of(page()))
    for w in ("Threads go quiet", "Find the threads that still need an answer", "judging \"substantive\" costs a model call",
              "every 2 hours during working hours", "Pulse reads the whole thread before deciding.", "must",
              "each classified thread records the messages read.", "test_run", "one@example.com", "m8@example.com"):
        assert w in shown, w
    for injected in ("j2-", "Live preview", "mailboxes scanned", "Pass", "Fail", "receipt"):
        assert injected not in shown, injected


def test_the_markdown_view_is_the_whole_original_file():
    h = page()
    src = re.search(r'<pre class="src" id="src"[^>]*>(.*?)</pre>', h, re.S)[1]
    lines = [html.unescape(x) for x in re.findall(r"<span>(.*?)</span>", src, re.S)]
    assert "\n".join(lines) == FIX


def test_the_header_shows_the_document_revision_only_when_recorded():
    h = page(meta={"version": 3, "time": "2026-11-26T22:59:10"})
    assert '<p class="meta">Version 3 · 26 Nov 2026, 22:59</p>' in h
    assert '<p class="meta">' not in page(meta={}) and '<p class="meta">' not in page(meta={"time": "2026-11-26T22:59:10"})
    assert "<h1>Fixture — Reader PRD</h1>" in h, "the first # heading is the title"
    assert "<h1>agent_hld.md</h1>" in r.reader_html("## Purpose\n\ntext", "agent_hld.md"), "no # heading: the name it was given"


def test_sections_ids_and_navigation():
    h = page()
    assert '<section class="sec" id="problem"><h2>Problem</h2>' in h and '<h3 id="key-flow">' in h
    rail = re.search(r'<nav class="rail"[^>]*>(.*?)</nav>', h, re.S)[1]
    assert re.findall(r'href="#([\w-]+)"', rail) == ["problem", "goals", "approach", "key-flow", "requirements", "nested-lists", "mailboxes"]
    assert 'id="tocdd"' in h, "the narrow pane's On this page dropdown"
    assert '<li id="G1"><a class="rid" href="#G1">G1</a>' in h, "an id list: linkable ids"
    assert '<a class="ref" href="#R2">R2</a>' in h and '<a class="ref" href="#G1">G1</a>' in h, "references link to the definition"
    assert '<tr id="X1">' in h, "a table's first-column id is linkable"
    assert "<a class=\"ref\" href=\"#Q9\">" not in r.reader_html("- **G1**: see Q9\n- **G2**: x", "d"), "an id the document does not define stays text"


def test_requirements_become_a_ledger_that_stacks():
    h = page()
    table = re.search(r'<table class="lg req stack">(.*?)</table>', h, re.S)[1]
    assert re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", table) == ["Id", "Requirement", "Priority", "Accepted when", "Checked by"]
    row = re.search(r'<tr id="R1">(.*?)</tr>', table, re.S)[1]
    assert 'data-label="Accepted when">each classified thread records the messages read.</td>' in row
    assert 'data-label="Checked by">test_run</td>' in row and 'Serves <a class="ref" href="#G1">G1</a>' in row
    assert "table.stack td::before{content:attr(data-label)" in h, "at 390 px each requirement stacks with its acceptance"


def test_long_tables_are_striped_and_compact():
    assert re.search(r'<table class="lg long">', page()), "8 rows or more"
    assert 'class="lg long' not in r.reader_html("| a | b |\n|---|---|\n| 1 | 2 |", "d")


def test_asides_callouts_example_and_code():
    h = page()
    assert '<p class="lab lab-tradeoff"><b>Tradeoff:</b> judging "substantive" costs a model call.</p>' in h
    assert '<aside class="callout callout-note"><b class="clab">Note</b>' in h
    assert f"<figcaption><b>{r.EXAMPLE_LABEL}</b></figcaption>" in h and "Example digest · no live data" == r.EXAMPLE_LABEL
    assert '<figure class="code"><figcaption>python</figcaption>' in h
    assert "digest-example" not in text_of(r.reader_html("## A\n\nNo example here.", "d")), "no example unless the file has one"


def test_diagrams_are_drawn_where_written_with_their_source():
    h = page()
    approach = h[h.index('id="approach"'):h.index('id="requirements"')]
    assert approach.count('<svg class="dg"') == 2, "the state diagram and the flow, inside the section that writes them"
    assert approach.index("Open or resolved") < approach.index('<svg class="dg"') < approach.index("How often to check mail")
    assert approach.count("<summary>Diagram source</summary>") == 2
    svg = r.diagram_svg("flowchart LR\n  A[Scan] --> B{Ok?}\n  B -->|yes| C[Send]\n  B -.->|no| D[Hold]")
    assert svg and ">Scan<" in svg and ">yes<" in svg and 'stroke-dasharray' in svg and 'aria-label="Scan to Ok?' in svg
    state = r.diagram_svg("stateDiagram-v2\n  [*] --> Open\n  Open --> Closed : closed with a reason\n  Closed --> [*]")
    assert state and ">Open<" in state and ">closed with a<" in state and 'class="dgs"' in state
    assert r.diagram_svg("sequenceDiagram\n  A->>B: hi") is None
    other = r.reader_html("```mermaid\nsequenceDiagram\n  A->>B: hi\n```", "d")
    assert "not a kind this reader draws" in other and "A-&gt;&gt;B: hi" in other


def test_no_markup_from_the_file_runs():
    h = r.reader_html('## A\n\n<script>alert(1)</script> [x](javascript:alert(1)) <img src=x onerror=alert(1)>\n\n| <b>c</b> |\n|---|\n| d |', "d")
    body = h[h.index("<main"):h.index("</main>")]
    assert "<script>" not in body and "<img" not in body and 'href="javascript' not in body and "&lt;script&gt;" in body


def test_lists_keep_nesting_and_continuation_lines():
    h = page()
    nested = h[h.index('id="nested-lists"'):h.index('id="mailboxes"')]
    assert re.search(r"<li>Pilot mailboxes:<ul><li>one@example.com</li><li>two@example.com</li></ul></li>", nested)
    assert '<p class="lab lab-assumption"><b>Assumption:</b> the lead is confirmed before delivery.</p>' in nested


def test_a_section_preview_has_no_bar_and_no_script():
    h = r.reader_html("## A\n\ntext", "Section", chrome=False)
    assert "<script>" not in h and 'id="bar"' not in h and "<h2>A</h2>" in h


def test_downloads_are_the_existing_files():
    h = page(name="fixture_prd.md", meta={"word": "fixture_prd.docx"})
    assert 'data-file="fixture_prd.md"' in h and 'data-file="fixture_prd.docx"' in h and "/api/artifact?" in h
    assert 'data-file="fixture_prd.docx"' not in page(name="fixture_prd.md"), "no Word file in the run: no Word item"
    assert 'id="dl"' not in page(), "no file name (a live site page): no Download menu"


PICS = (Path(__file__).resolve().parents[1] / "fixtures" / "doc_reader" / "fixture_pictures.md").read_text(encoding="utf-8")


def section_html(h, sid, nxt):
    return h[h.index(f'id="{sid}"'):h.index(f'id="{nxt}"')]


def test_key_flows_are_a_chain_of_their_own_steps_and_the_if_line_is_the_failure_path():
    h = r.reader_html(PICS, "d")
    flows = section_html(h, "key-flows", "dependencies")
    assert '<ol class="flowchain" start="1"' in flows and flows.count("<li>") == 3
    assert "The desk reads the new mail since the last run." in flows, "each step's words as written"
    assert '<p class="failpath">If the inbox cannot be read: the summary says so' in flows


def test_the_context_picture_ends_approach_from_users_and_dependencies():
    h = r.reader_html(PICS, "d")
    approach = section_html(h, "approach", "key-flows")
    ctx = re.search(r'<figure class="context".*?</figure>', approach, re.S)[0]
    assert re.findall(r'<span class="node">(.*?)</span>', ctx) == ["Team lead", "Support agent", "Inbox access", "Chat account"]
    assert '<div class="core">Fixture — Picture Desk</div>' in ctx and "Drawn from Users and Dependencies." in ctx
    assert "figure class=\"context\"" not in r.reader_html("# T\n\n## Users\n\n**A** b.\n\n## Approach\n\nx", "d"), "no Dependencies: no picture"


def test_the_architecture_ends_data_flow_from_components_and_its_x_to_y_lines():
    h = r.reader_html(PICS, "d")
    flow = h[h.index('id="data-flow"'):]
    arch = re.search(r'<figure class="diagram arch">.*?</figure>', flow, re.S)[0]
    for label in (">C1 Mail reader<", ">C2 Sorter<", ">C3 Summary writer<", ">Mail<", ">Chat<"):
        assert label in arch, label
    assert 'aria-label="Architecture: Mail to C1 Mail reader; C1 Mail reader to C2 Sorter; C2 Sorter to C3 Summary writer; C3 Summary writer to Chat"' in arch
    assert arch.count('class="dgn dgx"') == 2, "outside systems are dashed"
    assert "Architecture, drawn from Components and Data flow." in arch


def test_an_authored_diagram_wins_and_the_markdown_is_unchanged():
    authored = PICS.replace("## Data flow\n", "## Data flow\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    h = r.reader_html(authored, "d")
    assert "diagram arch" not in h and h.count('<svg class="dg"') == 1
    src = re.search(r'<pre class="src" id="src"[^>]*>(.*?)</pre>', r.reader_html(PICS, "d"), re.S)[1]
    assert "\n".join(html.unescape(x) for x in re.findall(r"<span>(.*?)</span>", src, re.S)) == PICS


def test_a_data_flow_written_as_steps_is_drawn_too():
    """The Inbox Triage HLD of 27 Nov 2026 wrote its data flow as one paragraph of steps, not as "X to Y" lines."""
    md = PICS.split("## Data flow")[0] + ("## Data flow\n\nDaily run: C1 reads new mail from the shared inbox; C2 sorts each message; "
                                          "C3 sends the summary to the team lead only.\n\nMarks: the lead marks an item; C3 writes the mark to C1.\n")
    arch = re.search(r'<figure class="diagram arch">.*?</figure>', r.reader_html(md, "d"), re.S)[0]
    assert ('aria-label="Architecture: Shared inbox to C1 Mail reader; C1 Mail reader to C2 Sorter; C2 Sorter to C3 Summary writer; '
            'C3 Summary writer to Team lead; C3 Summary writer to C1 Mail reader"') in arch
    assert arch.count('class="dgn dgx"') == 2


SHAPES = """# Fixture — Shapes

<!-- W-1:start -->
## Requirements

1. **Requirements1 (R1)**: The desk reads new mail (must). Accepted when a test run reads it. Checked by test_run. Serves G1, G2.
2. **Requirements2 (R2)**: The desk sorts mail (should). Accepted when, with a labelled set, every message gets one class. Checked by code. Serves G2.

## Actions and authority

| Id | Action | Access | Approval |
|---|---|---|---|
| A1 | Read mail | read | autonomous |
| A2 | Send summary | write | with_confirmation |

## Steps

1. **S1** Read (code): read new mail. Implements R1.
2. **S2** Sort (model): sort each message. Implements R2.

## Components

- **C1** Reader (tool): reads mail. Covers R1. In S1. Performs A1.
- **C2** Sorter (model): sorts mail. Covers R1, R2. In S2.
- Assumption: the inbox is a shared one.

## Safety

- Reads untrusted input: yes. Mail is written by outsiders.
- Reads private data: yes. The inbox holds addresses.
- Acts outside its folder: no. It only reads.
<!-- W-1:end -->
"""


def test_lists_that_are_tables_or_flows_take_that_shape_and_keep_their_words():
    h = r.reader_html(SHAPES, "d")
    preview = h[:h.index('id="srcwrap"')]
    assert "&lt;!--" not in preview and "W-1:start" in h[h.index('id="srcwrap"'):], "a comment line: hidden in Preview, kept in Markdown"
    req = re.search(r'<table class="lg req stack">.*?</table>', h, re.S)[0]
    assert '<tr id="R1">' in req and '<span class="pri pri-must">must</span>' in req and '<span class="pri pri-should">should</span>' in req
    assert 'data-label="Accepted when">with a labelled set, every message gets one class.</td>' in req
    matrix = re.search(r'<figure class="matrix">.*?</figure>', h, re.S)[0]
    assert matrix.count("&#9679;") == 3 and "Which goal each requirement serves" in matrix
    assert '<span class="pill pill-ok">read</span>' in h and '<span class="pill pill-ask">with_confirmation</span>' in h
    steps = re.search(r'<ol class="stepflow".*?</ol>', h, re.S)[0]
    assert '<li id="S1">' in steps and '<b>Read</b> <span class="kind">code</span>' in steps and "read new mail. Implements <a class=\"ref\" href=\"#R1\">R1</a>." in steps
    comp = h[h.index('id="components"'):h.index('id="safety"')]
    heads = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", re.search(r"<thead>(.*?)</thead>", comp, re.S)[1])
    assert heads == ["Id", "Name", "Kind", "Description", "Covers", "In", "Performs"]
    assert 'data-label="Covers"><a class="ref" href="#R1">R1</a>, <a class="ref" href="#R2">R2</a></td>' in comp and 'title="not given">' in comp, "C2 performs nothing: a dash"
    assert '<p class="lab lab-assumption"><b>Assumption:</b> the inbox is a shared one.</p>' in comp
    safety = h[h.index('id="safety"'):]
    assert re.findall(r"<th>(.*?)</th>", safety)[:3] == ["Question", "Answer", "Detail"]
    assert safety.count('class="yn yn-yes"') == 2 and safety.count('class="yn yn-no"') == 1 and "Mail is written by outsiders." in safety
