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
              "every 2 hours during working hours", "Pulse reads the whole thread before deciding (must).",
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
    assert re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", table) == ["Id", "Requirement", "Accepted when", "Checked by"]
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
