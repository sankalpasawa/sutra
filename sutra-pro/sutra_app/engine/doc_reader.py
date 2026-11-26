"""The document reader (D455): one renderer for every Markdown file a run shows in Files (PRD, HLD, LLD, an operating design, any
other `.md`).

The Markdown the builders write is the source of truth. The reader never adds content: no run id, run time, run status, scan coverage,
receipt or verification result is put into a document. The only facts from outside the file are the document's own revision metadata
(`meta`: its version and the time that version was written, its label, and the Word file the run exported beside it), and only when the
run records them. Downloads are the existing ones: the Markdown file and that Word file, both from `/api/artifact`.

    blocks(md)                         the document as blocks (headings, paragraphs, lists, tables, code, diagrams, callouts)
    reader_html(md, title, meta, ...)  the Files pane's page: compact header, Preview and Markdown, On this page, Download
    diagram_svg(source)                a ```mermaid flowchart or state diagram drawn as SVG; None when it is not one this draws

What is drawn from the Markdown, and how:
    # Title                           the header's title (the first heading, when it is a level-1 heading)
    ## Section / ### Sub              sections; each is an On this page entry (### nested)
    - **R1**: text, 1. **G2** text    a list whose every item starts with a bold id: ruled rows with the id in a gutter, linkable (#R1)
    ... Accepted when ... Checked by  a list of requirements (every item has "Accepted when"): a table, stacked on a narrow pane
    | a | b |                         a ruled table; a long one (8 rows or more) is striped and compact; a first-column id is linkable
    Assumption: / Tradeoff: / Note:   a line that starts with one of these labels: a labelled aside, its words unchanged
    > [!NOTE] / > **Note:**          a callout; any other quote is a quote
    ```mermaid                        a diagram drawn beside its text, its source one click away; ```digest-example, an example labelled
                                      "Example digest · no live data"; any other fence, code
    R1, G2, C10 in the text           a link to where the document defines that id; ids it does not define stay text
"""
import base64
import datetime
import html
import os
import re
from functools import lru_cache

__all__ = ["blocks", "reader_html", "diagram_svg", "title_of", "meta_line", "defined_ids", "inline", "EXAMPLE_LABEL"]

EXAMPLE_LABEL = "Example digest · no live data"
EXAMPLE_LANGS = ("digest-example",)
DIAGRAM_LANGS = ("mermaid",)
LONG_TABLE = 8                      # rows from which a table is striped and compact (Dense Ops)
NOTE_LABELS = ("Assumption", "Tradeoff", "Note")
CALLOUT_KINDS = {"note": "Note", "tip": "Tip", "important": "Important", "warning": "Warning", "caution": "Caution"}

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w.+-]*)[^`]*$")
LIST = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
HR = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
NOTE = re.compile(r"^(" + "|".join(NOTE_LABELS) + r"):\s*(.*)$")
ID = r"[A-Z]{1,3}-?\d{1,3}"
ID_LEAD = re.compile(r"^\*\*(" + ID + r")\b\s*([^*]*?)\*\*\s*:?\s*(.*)$")
ID_WORD = re.compile(r"(?<![\w#-])(" + ID + r")(?![\w-])")
GH_CALLOUT = re.compile(r"^\[!(\w+)\]\s*(.*)$", re.I)
BOLD_CALLOUT = re.compile(r"^\*\*(" + "|".join(CALLOUT_KINDS.values()) + r"):?\*\*:?\s*(.*)$", re.I)


# ------------------------------------------------------------------------------------------------------------------ blocks
def blocks(md):
    """The document as a list of blocks (dicts with "t"): h(level, text), p(lines), list(ordered, items[{lines, children}]),
    table(head, align, rows), code(lang, text), quote(lines), hr. Nothing is dropped: every non-blank line lands in one block."""
    lines = str(md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return _blocks(lines)


def _blocks(lines):
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if m := FENCE.match(ln):
            mark, lang, body, i = m[2], m[3].lower(), [], i + 1
            while i < n and not (lines[i].strip().startswith(mark[0] * len(mark)) and not lines[i].strip().strip(mark[0])):
                body.append(lines[i])
                i += 1
            i += 1                                                   # the closing fence (or the end of the file)
            out.append({"t": "code", "lang": lang, "text": "\n".join(body)})
            continue
        if m := HEADING.match(ln):
            out.append({"t": "h", "level": len(m[1]), "text": m[2].strip()})
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            out.append(_table(rows))
            continue
        if HR.match(ln):
            out.append({"t": "hr"})
            i += 1
            continue
        if QUOTE.match(ln):
            body = []
            while i < n and (m := QUOTE.match(lines[i])):
                body.append(m[1])
                i += 1
            out.append({"t": "quote", "lines": body})
            continue
        if LIST.match(ln):
            j = i
            while j < n:
                cur = lines[j]
                if not cur.strip():                                  # a blank line: the list goes on only if an item or indented text follows
                    k = j + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and (LIST.match(lines[k]) and _indent(lines[k]) >= _indent(ln) or _indent(lines[k]) > _indent(ln)):
                        j = k
                        continue
                    break
                if j > i and _starts_block(cur) and not LIST.match(cur):
                    break
                j += 1
            out.append(_list(lines[i:j]))
            i = j
            continue
        para = []
        while i < n and lines[i].strip() and not (para and _starts_block(lines[i])):
            para.append(lines[i].strip())
            i += 1
        out.append({"t": "p", "lines": para})
    return out


def _indent(ln):
    return len(ln) - len(ln.lstrip(" \t").replace("\t", "    "))


def _starts_block(ln):
    s = ln.strip()
    return bool(HEADING.match(ln) or FENCE.match(ln) or s.startswith("|") or QUOTE.match(ln) or LIST.match(ln) or HR.match(ln))


def _list(lines):
    """One list (with nested lists) from its lines; the first line is an item."""
    first = LIST.match(lines[0])
    base = len(first[1].replace("\t", "    "))
    ordered = first[2][0].isdigit()
    start = int(first[2][:-1]) if ordered else 1
    items, cur, child = [], None, []

    def close():
        if cur is not None:
            if child:
                cur["children"].extend(_blocks(_dedent(child)))
                child.clear()
            items.append(cur)
    for ln in lines:
        m = LIST.match(ln)
        if m and len(m[1].replace("\t", "    ")) <= base:
            close()
            cur = {"lines": [m[3].strip()], "children": []}
        elif not ln.strip():
            if child:
                child.append("")
        elif child or (_indent(ln) > base and LIST.match(ln)) or (_indent(ln) > base and _starts_block(ln)):
            child.append(ln)
        else:
            cur["lines"].append(ln.strip())                          # an indented or lazy continuation line of the item
    close()
    return {"t": "list", "ordered": ordered, "start": start, "items": items}


def _dedent(lines):
    pad = min((_indent(x) for x in lines if x.strip()), default=0)
    return [x[pad:] if len(x) >= pad else x.strip() for x in lines]


def _cells(row):
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def _table(rows):
    head = _cells(rows[0])
    body, align = rows[1:], [""] * len(head)
    if body and TABLE_SEP.match(body[0]):
        align = ["center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else "" for c in _cells(body[0])]
        body = body[1:]
    width = max([len(head)] + [len(_cells(r)) for r in body])
    pad = lambda r: r + [""] * (width - len(r))                       # noqa: E731
    return {"t": "table", "head": pad(head), "align": pad(align)[:width], "rows": [pad(_cells(r)) for r in body]}


# ------------------------------------------------------------------------------------------------------------- the model
def title_of(md, fallback="Document"):
    """The document's title: its first heading when that is a level-1 heading, else `fallback`."""
    first = next((b for b in blocks(md) if b["t"] == "h"), None)
    return _plain(first["text"]) if first and first["level"] == 1 else str(fallback or "Document")


def _plain(t):
    return re.sub(r"`([^`]*)`", r"\1", re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*", lambda m: m[1] or m[2], str(t))).strip()


def defined_ids(bl):
    """The ids the document defines: a list item that starts with a bold id, or a table row whose first cell is an id."""
    out = []

    def walk(bs):
        for b in bs:
            if b["t"] == "list":
                for it in b["items"]:
                    if m := ID_LEAD.match(it["lines"][0]):
                        out.append(m[1])
                    walk(it["children"])
            elif b["t"] == "table":
                out.extend(r[0] for r in b["rows"] if r and re.fullmatch(ID, r[0].strip("* ")))
    walk(bl)
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def meta_line(meta):
    """The header's revision line, from the document's own revision metadata only: "Version 3 · 26 Nov 2026, 22:59". "" without it."""
    meta = meta or {}
    v, when = meta.get("version"), meta.get("time")
    parts = []
    if isinstance(v, int) and not isinstance(v, bool) and v >= 1:
        parts.append(f"Version {v}")
    if parts and isinstance(when, str) and when:
        try:
            t = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
            parts.append(f"{t.day} {t:%b %Y}, {t:%H:%M}")
        except ValueError:
            pass
    return " · ".join(parts)


def _slugger():
    used = {}

    def slug(text):
        s = re.sub(r"[^a-z0-9]+", "-", _plain(text).lower()).strip("-") or "section"
        used[s] = used.get(s, 0) + 1
        return s if used[s] == 1 else f"{s}-{used[s]}"
    return slug


def _requirement(text):
    """A requirement item's parts when it has "Accepted when": (requirement, accepted, checked, serves); else None."""
    m = re.match(r"^(.*?)\s+Accepted when\s+(.*)$", text)
    if not m:
        return None
    req, rest = m[1], m[2]
    chk = serves = ""
    if s := re.search(r"\s+Serves\s+([^.]*?)\.?\s*$", rest):
        serves, rest = s[1], rest[:s.start()]
    if c := re.search(r"\s+Checked by\s+(.*?)\.?\s*$", rest):
        chk, rest = c[1], rest[:c.start()]
    return req, rest, chk, serves


# ------------------------------------------------------------------------------------------------------------- inline html
def inline(t, ids=frozenset()):
    """One line of Markdown as HTML: `code`, **bold**, *italic*, [links](https://...) and links to the ids the document defines."""
    keep = []

    def hold(x):
        keep.append(x)
        return f"\x00{len(keep) - 1}\x00"
    t = str(t or "")
    t = re.sub(r"(`+)(.+?)\1", lambda m: hold(f"<code>{html.escape(m[2])}</code>"), t)
    t = re.sub(r"\[([^\]]+)\]\(((?:https?://|mailto:)[^)\s]+)\)",
               lambda m: hold(f'<a href="{html.escape(m[2])}" target="_blank" rel="noopener noreferrer">{html.escape(m[1])}</a>'), t)
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    if ids:
        t = ID_WORD.sub(lambda m: f'<a class="ref" href="#{m[1]}">{m[1]}</a>' if m[1] in ids else m[1], t)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m[1])], t)


def _lines_html(lines, ids, tag="p", cls=""):
    """Lines of one paragraph or list item: plain lines run together; a line that starts with Assumption:, Tradeoff: or Note: is its own
    labelled aside (its words as written)."""
    out, run = [], []

    def flush():
        if run:
            out.append(f"<{tag}{cls}>{inline(' '.join(run), ids)}</{tag}>" if tag else inline(" ".join(run), ids))
            run.clear()
    for ln in lines:
        if m := NOTE.match(ln):
            flush()
            out.append(f'<p class="lab lab-{m[1].lower()}"><b>{m[1]}:</b> {inline(m[2], ids)}</p>')
        else:
            run.append(ln)
    flush()
    return "".join(out)


# ------------------------------------------------------------------------------------------------------------- the body
def _body(bl, ids, title_used, slug, toc, pics=None):
    parts, open_sec, sec = [], False, ""
    pics = dict(pics or {})

    def close():      # a picture drawn from the text goes at the end of the section it belongs to (D457)
        if sec in pics:
            parts.append(pics.pop(sec))
    for k, b in enumerate(bl):
        t = b["t"]
        if t == "h":
            if k == title_used:
                continue
            lvl, text = b["level"], b["text"]
            if lvl <= 2:
                close()
                sec = _plain(text)
                if open_sec:
                    parts.append("</section>")
                sid = slug(text)
                toc.append((2, sid, _plain(text)))
                parts.append(f'<section class="sec" id="{sid}"><h2>{inline(text, ids)}</h2>' if lvl == 2
                             else f'<section class="sec" id="{sid}"><h2 class="h1x">{inline(text, ids)}</h2>')
                open_sec = True
            else:
                sid = slug(text)
                if lvl == 3:
                    toc.append((3, sid, _plain(text)))
                parts.append(f'<h{lvl} id="{sid}">{inline(text, ids)}</h{lvl}>')
        elif t == "p":
            fail = sec == FLOWS_SECTION and re.match(r"If\b[^:]{3,}:", b["lines"][0])
            parts.append(_lines_html(b["lines"], ids, cls=' class="failpath"' if fail else ""))
        elif t == "list":
            parts.append(_flow_html(b, ids) if sec == FLOWS_SECTION and b["ordered"] and not _has_diagram(bl, sec)
                         else _list_html(b, ids, slug, toc))
        elif t == "table":
            parts.append(_table_html(b, ids))
        elif t == "code":
            parts.append(_code_html(b))
        elif t == "quote":
            parts.append(_quote_html(b, ids, slug, toc))
        elif t == "hr":
            parts.append("<hr>")
    close()
    if open_sec:
        parts.append("</section>")
    return "".join(parts)


# ------------------------------------------------------------------------------------------------------------- pictures from the text
# D457 (carries P36 of the PRD template change): what the reader draws from a document's own words where the document has no diagram
# of its own. A numbered list under "Key flows" is a chain of steps, an "If ...:" line under it the failure path; a document with
# "Users" and "Dependencies" gets a context picture at the end of "Approach" (the people, the product, what it depends on); a design
# with "Components" (ids C1, C2, ...) and "Data flow" lines that say "X to Y" gets its architecture at the end of "Data flow".
# Nothing is drawn that the text does not say; the Markdown, and so its download and the Word file, are unchanged.
FLOWS_SECTION, PEOPLE_SECTION, NEEDS_SECTION, PICTURE_AFTER = "Key flows", "Users", "Dependencies", "Approach"
COMPONENTS_SECTION, DATAFLOW_SECTION = "Components", "Data flow"
PICTURE_MAX = 6
COMP_ID = re.compile(r"^C\d{1,3}$")


def _sections(bl):
    """{h2 heading: [its blocks]}."""
    out, cur = {}, None
    for b in bl:
        if b["t"] == "h" and b["level"] <= 2:
            cur = _plain(b["text"])
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(b)
    return out


def _has_diagram(bl, sec):
    return any(b["t"] == "code" and b["lang"] in DIAGRAM_LANGS for b in _sections(bl).get(sec, []))


def _bold_lead(text):
    m = re.match(r"\*\*(.+?)\*\*", str(text).strip())
    return _plain(m[1]).strip(" :.") if m else ""


def _flow_html(b, ids):
    """The numbered steps of Key flows as a chain, each step's words as written."""
    steps = [f'<li><span class="fn">{n}</span><div>{_lines_html(it["lines"], ids, tag="")}</div></li>'
             for n, it in enumerate(b["items"], b["start"])]
    return f'<ol class="flowchain" start="{b["start"]}" aria-label="{FLOWS_SECTION}, as steps">{"".join(steps)}</ol>'


def _context_html(bl, title):
    """People, the product and what it depends on, from Users and Dependencies; "" without both."""
    secs = _sections(bl)
    people, needs = [], []
    for b in secs.get(PEOPLE_SECTION, []):
        if b["t"] == "p":
            people += [x for x in [_bold_lead(b["lines"][0])] if x]
        elif b["t"] == "list":
            people += [x for x in (_bold_lead(it["lines"][0]) for it in b["items"]) if x]
        elif b["t"] == "table":
            people += [_plain(r[0]) for r in b["rows"] if r and r[0].strip()]
    for b in secs.get(NEEDS_SECTION, []):
        if b["t"] == "table":
            needs += [_plain(r[0]) for r in b["rows"] if r and r[0].strip()]
        elif b["t"] == "list":
            needs += [x for x in (_bold_lead(it["lines"][0]) for it in b["items"]) if x]
    if not (title and people and needs):
        return ""

    def side(label, xs):
        more = f'<span class="more">+{len(xs) - PICTURE_MAX} more</span>' if len(xs) > PICTURE_MAX else ""
        return (f'<div class="side"><span class="lbl">{label}</span>'
                + "".join(f'<span class="node">{html.escape(x[:80])}</span>' for x in xs[:PICTURE_MAX]) + more + "</div>")
    t = html.escape(title)
    return (f'<figure class="context" aria-label="Context: who uses {t} and what it depends on">'
            f'{side("People", people)}<span class="arr" aria-hidden="true">&#8644;</span><div class="core">{t}</div>'
            f'<span class="arr" aria-hidden="true">&#8644;</span>{side("Depends on", needs)}'
            f'<figcaption>Drawn from {PEOPLE_SECTION} and {NEEDS_SECTION}.</figcaption></figure>')


ARCH_END = r"(?:C\d{1,3}(?:/C\d{1,3})*|[A-Z][\w.-]*(?: [A-Z][\w.-]*)?)"
ARCH_CHAIN = re.compile(rf"({ARCH_END})(?:\s*\([^)]*\))?((?:\s+to\s+{ARCH_END}(?:\s*\([^)]*\))?)+)")
ARCH_HOP = re.compile(rf"\s+to\s+({ARCH_END})")


def _architecture_html(bl):
    """The components and the data flow between them, from Components (C1, C2, ...) and Data flow ("C3 to C4", "Gmail to C3",
    "C8 to C9/C10 to Slack"); "" when fewer than two flows are found."""
    secs = _sections(bl)
    comps = {}
    for b in secs.get(COMPONENTS_SECTION, []):
        if b["t"] == "list":
            for it in b["items"]:
                if (m := ID_LEAD.match(it["lines"][0])) and COMP_ID.match(m[1]):
                    comps[m[1]] = _plain(m[2] or re.split(r"\s*[(:]", m[3], maxsplit=1)[0]).strip(" .")[:40]
        elif b["t"] == "table":
            for r in b["rows"]:
                if r and COMP_ID.match(r[0].strip("* ")):
                    comps[r[0].strip("* ")] = _plain(r[1] if len(r) > 1 else "")[:40]
    edges, seen = [], set()
    for b in secs.get(DATAFLOW_SECTION, []):
        if b["t"] != "list":
            continue
        for it in b["items"]:
            head = _plain(" ".join(it["lines"])).split(":")[0]
            for m in ARCH_CHAIN.finditer(head):
                hops = [m[1]] + ARCH_HOP.findall(m[2])
                for a, c in zip(hops, hops[1:]):
                    for x in a.split("/"):
                        for y in c.split("/"):
                            if x != y and (x, y) not in seen and (COMP_ID.match(x) or COMP_ID.match(y)):
                                seen.add((x, y))
                                edges.append((x, y, "", False))
    if len(edges) < 2 or not comps:
        return ""
    order = list(dict.fromkeys(n for e in edges for n in e[:2]))
    nodes = {n: {"label": f"{n} {comps[n]}".strip() if n in comps else n, "shape": "box" if COMP_ID.match(n) else "ext"} for n in order}
    alt = "Architecture: " + "; ".join(f"{nodes[a]['label']} to {nodes[c]['label']}" for a, c, *_ in edges)
    svg = draw_graph(nodes, order, edges, horiz=False, alt=alt[:600], cls="arch")
    return (f'<figure class="diagram arch">{svg}<figcaption>Architecture, drawn from {COMPONENTS_SECTION} and {DATAFLOW_SECTION}. '
            "Dashed boxes are outside the product.</figcaption></figure>")


def _pictures(bl, title):
    """{section: the picture that ends it}, for the sections that have no diagram of their own."""
    out = {}
    if (ctx := _context_html(bl, title)) and not _has_diagram(bl, PICTURE_AFTER):
        out[PICTURE_AFTER] = ctx
    if (arch := _architecture_html(bl)) and not _has_diagram(bl, DATAFLOW_SECTION):
        out[DATAFLOW_SECTION] = arch
    return out


def _list_html(b, ids, slug, toc):
    items = b["items"]
    led = [ID_LEAD.match(it["lines"][0]) for it in items]
    if len(items) >= 2 and all(led):
        reqs = [_requirement(" ".join([m[3]] + it["lines"][1:])) for m, it in zip(led, items)]
        if all(reqs) and not any(it["children"] for it in items):
            return _ledger_html(led, reqs, ids)
        rows = []
        for m, it in zip(led, items):
            rid, rest_bold, text = m[1], m[2], m[3]
            head = f"<b>{inline(rest_bold, ids)}</b>{':' if text else ''} " if rest_bold else ""
            body = head + _lines_html([text] + it["lines"][1:], ids, tag="") if text or rest_bold else _lines_html(it["lines"][1:], ids, tag="")
            kids = _body(it["children"], ids, -1, slug, toc) if it["children"] else ""
            rows.append(f'<li id="{rid}"><a class="rid" href="#{rid}">{rid}</a><div class="ibody">{body}{kids}</div></li>')
        return f'<ol class="ids" role="list">{"".join(rows)}</ol>'
    tag = "ol" if b["ordered"] else "ul"
    start = f' start="{b["start"]}"' if b["ordered"] and b["start"] != 1 else ""
    lis = []
    for it in items:
        first, rest = it["lines"][0], it["lines"][1:]
        body = _lines_html([first] + rest, ids, tag="") if not NOTE.match(first) else _lines_html([first] + rest, ids)
        kids = _body(it["children"], ids, -1, slug, toc) if it["children"] else ""
        lis.append(f"<li>{body}{kids}</li>")
    return f"<{tag}{start}>{''.join(lis)}</{tag}>"


NOT_STATED = '<span class="none">Not stated</span>'


def _ledger_html(led, reqs, ids):
    rows = []
    for m, (req, acc, chk, serves) in zip(led, reqs):
        rid = m[1]
        lead = f"<b>{inline(m[2], ids)}</b> " if m[2] else ""
        srv = f'<span class="serves">Serves {inline(serves, ids)}</span>' if serves else ""
        rows.append(f'<tr id="{rid}"><td class="id" data-label="Id"><a class="rid" href="#{rid}">{rid}</a></td>'
                    f'<td data-label="Requirement">{lead}{inline(req, ids)}{srv}</td>'
                    f'<td data-label="Accepted when">{inline(acc, ids)}</td>'
                    f'<td class="method" data-label="Checked by">{inline(chk, ids) if chk else NOT_STATED}</td></tr>')
    long = " long" if len(rows) >= LONG_TABLE else ""
    return ('<div class="tw"><table class="lg req stack' + long + '"><thead><tr><th class="id">Id</th><th>Requirement</th>'
            '<th>Accepted when</th><th>Checked by</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def _table_html(b, ids):
    head, rows, align = b["head"], b["rows"], b["align"]
    st = lambda i: f' style="text-align:{align[i]}"' if i < len(align) and align[i] else ""      # noqa: E731
    th = "".join(f"<th{st(i)}>{inline(c, ids)}</th>" for i, c in enumerate(head))
    trs = []
    for r in rows:
        first = r[0].strip("* ") if r else ""
        rid = f' id="{first}"' if re.fullmatch(ID, first) else ""
        tds = []
        for i, c in enumerate(r):
            lab = html.escape(_plain(head[i]) if i < len(head) else "", quote=True)
            if i == 0 and rid:
                tds.append(f'<td class="id" data-label="{lab}"{st(i)}><a class="rid" href="#{first}">{html.escape(first)}</a></td>')
            else:
                tds.append(f'<td data-label="{lab}"{st(i)}>{inline(c, ids)}</td>')
        trs.append(f"<tr{rid}>{''.join(tds)}</tr>")
    cls = "lg" + (" long" if len(rows) >= LONG_TABLE else "") + (" stack" if len(head) >= 4 else "")
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def _code_html(b):
    lang, text = b["lang"], b["text"]
    src = html.escape(text)
    if lang in EXAMPLE_LANGS:
        return (f'<figure class="example"><figcaption><b>{EXAMPLE_LABEL}</b></figcaption>'
                f'<pre class="exbody">{src}</pre></figure>')
    if lang in DIAGRAM_LANGS:
        svg = diagram_svg(text)
        if svg:
            more = f'<details class="dsrc"><summary>Diagram source</summary><pre><code>{src}</code></pre></details>'
            return f'<figure class="diagram">{svg}{more}</figure>'
        return (f'<figure class="code"><figcaption>Diagram source ({html.escape(lang)}): not a kind this reader draws</figcaption>'
                f'<pre><code>{src}</code></pre></figure>')
    cap = f"<figcaption>{html.escape(lang)}</figcaption>" if lang else ""
    return f'<figure class="code">{cap}<pre><code>{src}</code></pre></figure>'


def _quote_html(b, ids, slug, toc):
    lines = list(b["lines"])
    first = lines[0].strip() if lines else ""
    kind = label = None
    if m := GH_CALLOUT.match(first):
        kind = m[1].lower()
        label = CALLOUT_KINDS.get(kind, m[1].capitalize())
        lines[0] = m[2]
    elif m := BOLD_CALLOUT.match(first):
        label = m[1].capitalize()
        kind = label.lower()
        lines[0] = m[2]
    inner = _body(_blocks(lines), ids, -1, slug, toc)
    if kind:
        return f'<aside class="callout callout-{html.escape(kind)}"><b class="clab">{html.escape(label)}</b>{inner}</aside>'
    return f"<blockquote>{inner}</blockquote>"


# ------------------------------------------------------------------------------------------------------------- diagrams
NODE = re.compile(r"^([A-Za-z_][\w-]*)\s*(?:\[\[(.+?)\]\]|\[\((.+?)\)\]|\(\((.+?)\)\)|\[(.+?)\]|\((.+?)\)|\{(.+?)\}|>(.+?)\])?")
ARROW = re.compile(r"^\s*(?:(-->|---|-\.->|-\.-|==>|===|--x|--o)\s*(?:\|([^|]*)\|)?|--\s+([^-][^>]*?)\s+-->|==\s+(.+?)\s+==>)\s*")


def _parse_flow(lines):
    nodes, edges, order = {}, [], []

    def node(tok):
        m = NODE.match(tok)
        if not m:
            return None, tok
        nid = m[1]
        label = next((g for g in m.groups()[1:] if g is not None), None)
        shape = "round" if m[3] or m[4] or m[6] else "diamond" if m[7] else "box"
        if nid not in nodes:
            nodes[nid] = {"label": nid, "shape": "box"}
            order.append(nid)
        if label is not None:
            nodes[nid] = {"label": label.strip().strip('"'), "shape": shape}
        return nid, tok[m.end():]
    for ln in lines:
        s = ln.strip().rstrip(";")
        if not s or s.startswith("%%") or re.match(r"^(classDef|class|style|linkStyle|click|subgraph|end)\b", s):
            continue
        cur, rest = node(s)
        if cur is None:
            return None
        while rest.strip():
            m = ARROW.match(rest)
            if not m:
                if rest.strip().startswith("&"):
                    return None
                break
            label = (m[2] or m[3] or m[4] or "").strip().strip('"')
            dashed = bool(m[1] and "." in m[1])
            nxt, rest = node(rest[m.end():])
            if nxt is None:
                return None
            edges.append((cur, nxt, label, dashed))
            cur = nxt
    return (nodes, order, edges) if nodes else None


def _parse_state(lines):
    nodes, edges, order = {}, [], []

    def node(name):
        name = name.strip()
        if name == "[*]":
            return None
        if name not in nodes:
            nodes[name] = {"label": name, "shape": "round"}
            order.append(name)
        return name
    starts, ends = [], []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("%%") or s in ("}",) or s.startswith(("note ", "direction ")):
            continue
        if m := re.match(r'^state\s+"(.+?)"\s+as\s+(\w+)', s):
            node(m[2])
            nodes[m[2]]["label"] = m[1]
            continue
        if m := re.match(r"^(\[\*\]|[\w-]+)\s*-->\s*(\[\*\]|[\w-]+)\s*(?::\s*(.*))?$", s):
            a, b2 = node(m[1]), node(m[2])
            if a is None and b2 is not None:
                starts.append(b2)
            elif b2 is None and a is not None:
                ends.append(a)
            elif a and b2:
                edges.append((a, b2, (m[3] or "").strip(), False))
            continue
        if m := re.match(r"^([\w-]+)\s*:\s*(.+)$", s):
            node(m[1])
            nodes[m[1]]["label"] = m[2].strip()
            continue
        return None
    if starts:
        nodes["__start"] = {"label": "", "shape": "start"}
        order.insert(0, "__start")
        edges[:0] = [("__start", x, "", False) for x in starts]
    if ends:
        nodes["__end"] = {"label": "", "shape": "end"}
        order.append("__end")
        edges += [(x, "__end", "", False) for x in ends]
    return (nodes, order, edges) if nodes else None


def _wrap(text, width=22):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def diagram_svg(source):
    """A ```mermaid flowchart (graph/flowchart TD, TB, LR, RL, BT) or stateDiagram drawn as SVG with readable labels; None when the
    source is another kind of diagram or does not parse. The SVG takes its colours from the page (currentColor and CSS classes)."""
    lines = [x for x in str(source or "").split("\n")]
    head = next((x.strip() for x in lines if x.strip() and not x.strip().startswith("%%")), "")
    body = lines[lines.index(next(x for x in lines if x.strip() == head)) + 1:] if head else []
    if m := re.match(r"^(?:graph|flowchart)(?:\s+(TD|TB|LR|RL|BT))?\s*;?$", head, re.I):
        g, horiz = _parse_flow(body), (m[1] or "TD").upper() in ("LR", "RL")
    elif re.match(r"^stateDiagram(?:-v2)?\s*$", head):
        g, horiz = _parse_state(body), any(re.match(r"^\s*direction\s+LR", x) for x in body)
    else:
        return None
    if not g:
        return None
    return draw_graph(*g, horiz)


def draw_graph(nodes, order, edges, horiz=False, alt="", cls=""):
    """The SVG of a graph: `nodes` {id: {"label", "shape": box|round|diamond|start|end|ext}}, `order` the ids in reading order, `edges`
    [(from, to, label, dashed)]. Layered left to right (`horiz`) or top to bottom; labels wrap and keep off nodes and other labels."""
    # layers: longest path from the sources, with edges that close a cycle drawn back
    idx = {n: i for i, n in enumerate(order)}
    fwd = [(a, b) for a, b, *_ in edges if idx[a] < idx[b] or (idx[a] != idx[b] and not _reaches(edges, b, a))]
    layer = {n: 0 for n in order}
    for _ in range(len(order)):
        changed = False
        for a, b in fwd:
            if layer[b] < layer[a] + 1:
                layer[b] = layer[a] + 1
                changed = True
        if not changed:
            break
    rows = {}
    for n in order:
        rows.setdefault(layer[n], []).append(n)
    # sizes
    size = {}
    for n, v in nodes.items():
        if v["shape"] in ("start", "end"):
            size[n] = (18, 18, [])
            continue
        lab = _wrap(v["label"], 14 if horiz else 22)
        w = max(len(x) for x in lab) * 7.4 + 28
        h = len(lab) * 17 + 18
        if v["shape"] == "diamond":
            w, h = w + 26, h + 18
        size[n] = (max(w, 64), h, lab)
    longest = max((min(len(e[2]), 18) for e in edges if e[2]), default=0) * 6.7
    gap_main = (56 + min(longest, 120)) if horiz else (64 + (56 if longest else 0))
    gap_cross = 28 + (min(longest, 120) if longest else 0)      # room for the labels of edges that leave a node side by side
    pos, along = {}, 16
    for li in sorted(rows):
        ns = rows[li]
        depth = max((size[n][0] if horiz else size[n][1]) for n in ns)
        across = 16
        for n in ns:
            w, h, _ = size[n]
            if horiz:
                pos[n] = (along + (depth - w) / 2, across)
                across += h + gap_cross
            else:
                pos[n] = (across, along + (depth - h) / 2)
                across += w + gap_cross
        along += depth + gap_main
    # centre each layer across the widest one
    extent = {}
    for li, ns in rows.items():
        last = ns[-1]
        extent[li] = (pos[last][1] + size[last][1]) if horiz else (pos[last][0] + size[last][0])
    widest = max(extent.values())
    for li, ns in rows.items():
        shift = (widest - extent[li]) / 2
        for n in ns:
            x, y = pos[n]
            pos[n] = (x, y + shift) if horiz else (x + shift, y)
    centre = lambda n: (pos[n][0] + size[n][0] / 2, pos[n][1] + size[n][1] / 2)      # noqa: E731
    pairs = {(a, b) for a, b, *_ in edges}
    lines, labels = [], []
    boxes = [(pos[n][0] - 4, pos[n][1] - 4, pos[n][0] + size[n][0] + 4, pos[n][1] + size[n][1] + 4) for n in nodes]      # labels keep off nodes
    xs = [pos[n][0] for n in nodes] + [pos[n][0] + size[n][0] for n in nodes]
    ys = [pos[n][1] for n in nodes] + [pos[n][1] + size[n][1] for n in nodes]
    for a, b, label, dashed in edges:
        if a == b:
            continue
        (x1, y1), (x2, y2) = centre(a), centre(b)
        back = layer[b] <= layer[a]
        bend = 36 if (b, a) in pairs else 46 if back else 0       # a pair of opposite edges bends apart; a lone edge back bends wide
        dx, dy = x2 - x1, y2 - y1
        ln = (dx * dx + dy * dy) ** 0.5 or 1
        cx, cy = (x1 + x2) / 2 - dy / ln * bend, (y1 + y2) / 2 + dx / ln * bend
        p1 = _border(pos[a], size[a], (cx, cy) if bend else (x2, y2))
        p2 = _border(pos[b], size[b], (cx, cy) if bend else (x1, y1))
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        if bend:
            lines.append(f'<path class="dge" d="M{p1[0]:.1f} {p1[1]:.1f} Q{cx:.1f} {cy:.1f} {p2[0]:.1f} {p2[1]:.1f}" fill="none"{dash} marker-end="url(#dga)"/>')
            lx, ly = (p1[0] + 2 * cx + p2[0]) / 4, (p1[1] + 2 * cy + p2[1]) / 4
        else:
            lines.append(f'<line class="dge" x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}"{dash} marker-end="url(#dga)"/>')
            lx, ly = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        xs.append(lx)
        ys.append(ly)
        if not label:
            continue
        lab = _wrap(label, 18)
        bw, bh = max(len(x) for x in lab) * 6.7 + 8, len(lab) * 15 + 2
        qx, qy = (cx, cy) if bend else ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        at = lambda t: ((1 - t) ** 2 * p1[0] + 2 * t * (1 - t) * qx + t * t * p2[0], (1 - t) ** 2 * p1[1] + 2 * t * (1 - t) * qy + t * t * p2[1])      # noqa: E731
        nx, ny = -dy / ln, dx / ln
        free = lambda x, y: not any(x - bw / 2 < o[2] and o[0] < x + bw / 2 and y - bh / 2 < o[3] and o[1] < y + bh / 2 for o in boxes)      # noqa: E731
        # on the edge first (its middle, then nearer either end), then just beside it: a label stays with its own line
        cands = [at(t) for t in (0.5, 0.38, 0.62, 0.28, 0.72)]
        cands += [(x + k * nx * (bw / 2 + 6), y + k * ny * (bh / 2 + 6)) for x, y in cands[:3] for k in (1, -1)]
        lx, ly = next(((x, y) for x, y in cands if free(x, y)), cands[0])
        boxes.append((lx - bw / 2, ly - bh / 2, lx + bw / 2, ly + bh / 2))
        xs += [lx - bw / 2, lx + bw / 2]
        ys += [ly - bh / 2, ly + bh / 2]
        top = ly - (len(lab) - 1) * 7.5 + 4
        labels += [f'<text class="dgl" x="{lx:.1f}" y="{top + i * 15:.1f}" text-anchor="middle">{html.escape(t)}</text>' for i, t in enumerate(lab)]
    x0, y0 = min(xs) - 12, min(ys) - 12
    W, H = max(xs) + 12 - x0, max(ys) + 12 - y0
    out = [f'<svg class="dg{(" " + cls) if cls else ""}" viewBox="{x0:.0f} {y0:.0f} {W:.0f} {H:.0f}" width="{W:.0f}" style="min-width:{min(W, max(W * 0.85, 320)):.0f}px"'
           f' role="img" aria-label="{html.escape(alt or _diagram_alt(nodes, edges))}"'
           ' xmlns="http://www.w3.org/2000/svg"><defs><marker id="dga" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"'
           ' orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="dgah"/></marker></defs>'] + lines
    for n, v in nodes.items():
        x, y = pos[n]
        w, h, lab = size[n]
        if v["shape"] == "start":
            out.append(f'<circle class="dgs" cx="{x + 9:.1f}" cy="{y + 9:.1f}" r="8"/>')
            continue
        if v["shape"] == "end":
            out.append(f'<circle class="dgn" cx="{x + 9:.1f}" cy="{y + 9:.1f}" r="8"/><circle class="dgs" cx="{x + 9:.1f}" cy="{y + 9:.1f}" r="4.5"/>')
            continue
        if v["shape"] == "diamond":
            out.append(f'<path class="dgn" d="M{x + w / 2:.1f} {y:.1f}L{x + w:.1f} {y + h / 2:.1f}L{x + w / 2:.1f} {y + h:.1f}L{x:.1f} {y + h / 2:.1f}Z"/>')
        else:
            rx = 14 if v["shape"] == "round" else 6
            out.append(f'<rect class="dgn{" dgx" if v["shape"] == "ext" else ""}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}"/>')
        ty = y + h / 2 - (len(lab) - 1) * 8.5 + 4.5
        for i, t in enumerate(lab):
            out.append(f'<text class="dgt" x="{x + w / 2:.1f}" y="{ty + i * 17:.1f}" text-anchor="middle">{html.escape(t)}</text>')
    return "".join(out + labels) + "</svg>"


def _reaches(edges, a, b, seen=None):
    seen = seen or set()
    if a == b:
        return True
    seen.add(a)
    return any(_reaches(edges, y, b, seen) for x, y, *_ in edges if x == a and y not in seen)


def _border(p, s, toward):
    """The point where the line from the node's centre toward `toward` leaves its box."""
    x, y = p
    w, h = s[0], s[1]
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    t = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
    return cx + dx * t, cy + dy * t


def _diagram_alt(nodes, edges):
    name = lambda n: nodes[n]["label"] or ("start" if n == "__start" else "end")      # noqa: E731
    return "; ".join(f"{name(a)} to {name(b)}" + (f" ({lab})" if lab else "") for a, b, lab, _ in edges)[:600]


# ------------------------------------------------------------------------------------------------------------- the pages
@lru_cache(maxsize=1)
def _font_css():
    """The studio's two type faces, inline: the reader is a sandboxed page (an opaque origin) that cannot load the app's font files."""
    here = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "static", "vendor", "fonts")
    out = []
    for fam, f in (("Bricolage Grotesque", "bricolage-grotesque.woff2"), ("Figtree", "figtree.woff2")):
        try:
            with open(os.path.join(here, f), "rb") as fh:
                data = base64.b64encode(fh.read()).decode()
            out.append(f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{data}) format('woff2');font-weight:300 800;font-display:swap}}")
        except OSError:
            pass
    return "".join(out)


TOKENS = """
:root{--bg:#f3f1ec;--paper:#ffffff;--paper2:#faf9f6;--zebra:#f7f5f0;--ink:#1f2421;--muted:#5f645e;--line:#e2ded5;--line2:#d0cabe;
--accent:#3d5a80;--accentsoft:#e8eef6;--ask:#a0580f;--asksoft:#fbeedf;--codebg:#f4f2ed;--shadow:rgb(31 36 33 / .10);color-scheme:light;
--f-d:'Bricolage Grotesque','Segoe UI',Arial,sans-serif;--f-b:'Figtree','Segoe UI',system-ui,Arial,sans-serif;--f-m:ui-monospace,'Cascadia Mono',Consolas,Menlo,monospace}
:root[data-theme=dark]{--bg:#1a1c1b;--paper:#232624;--paper2:#2a2d2b;--zebra:#272a28;--ink:#ecebe6;--muted:#a5a8a1;--line:#343734;--line2:#464a45;
--accent:#9db8de;--accentsoft:#243040;--ask:#eba25a;--asksoft:#33261a;--codebg:#1d1f1e;--shadow:rgb(0 0 0 / .4);color-scheme:dark}
@media (prefers-color-scheme:dark){:root:not([data-theme]){--bg:#1a1c1b;--paper:#232624;--paper2:#2a2d2b;--zebra:#272a28;--ink:#ecebe6;--muted:#a5a8a1;
--line:#343734;--line2:#464a45;--accent:#9db8de;--accentsoft:#243040;--ask:#eba25a;--asksoft:#33261a;--codebg:#1d1f1e;--shadow:rgb(0 0 0 / .4);color-scheme:dark}}
"""

DOC_CSS = """
*{box-sizing:border-box}[hidden]{display:none!important}
html{scroll-padding-top:var(--barh,56px)}
body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.65 var(--f-b);-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.doc{min-width:0;max-width:740px;width:100%}
.dhead{margin:0 0 22px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.dhead h1{font:700 30px/1.15 var(--f-d);letter-spacing:-.01em;margin:0}
.dhead .meta{font:12.5px/1.5 var(--f-m);color:var(--muted);margin:8px 0 0}
.sec{scroll-margin-top:calc(var(--barh,56px) + 8px)}
h2{font:700 21px/1.25 var(--f-d);margin:34px 0 10px;padding-top:4px}
.sec:first-of-type h2{margin-top:6px}
h2.h1x{font-size:24px}
h3{font:650 16.5px/1.3 var(--f-d);margin:24px 0 8px}
h4,h5,h6{font:650 15px/1.35 var(--f-b);margin:18px 0 6px}
h3,h4,h5,h6,[id]{scroll-margin-top:calc(var(--barh,56px) + 8px)}
p{margin:0 0 12px}
ul,ol{margin:0 0 14px;padding-left:22px}
li{margin:3px 0}
li>ul,li>ol{margin:4px 0 6px}
code{font:13px/1.5 var(--f-m);background:var(--codebg);border:1px solid var(--line);border-radius:4px;padding:0 4px}
hr{border:0;border-top:1px solid var(--line);margin:24px 0}
.lab{border-left:2px solid var(--line2);padding:1px 0 1px 12px;color:var(--muted);font-size:14.5px;margin:-4px 0 12px}
.lab b{color:var(--ink);font-weight:650}
li .lab{margin:4px 0 2px}
.lab-assumption{border-left-color:var(--ask)}
ol.ids{list-style:none;padding:0;margin:0 0 16px;border-top:1px solid var(--line)}
ol.ids>li{display:grid;grid-template-columns:48px minmax(0,1fr);gap:0 12px;padding:8px 0;margin:0;border-bottom:1px solid var(--line)}
.rid{font:600 12.5px/1.9 var(--f-m);color:var(--accent);text-decoration:none;white-space:nowrap}
.rid:hover,a.ref:hover{text-decoration:underline}
a.ref{font-family:var(--f-m);font-size:.88em;text-decoration:none;border-bottom:1px dotted currentColor}
.ibody>ul,.ibody>ol{margin-top:4px}
:target,tr:target td{background:var(--accentsoft)!important;transition:background .6s}
.tw{overflow-x:auto;margin:0 0 18px;border-top:2px solid var(--ink)}
table.lg{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5;color:var(--ink)}
table.lg th{font:650 12px/1.4 var(--f-b);text-transform:uppercase;letter-spacing:.04em;color:var(--muted);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:bottom}
table.lg td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
table.lg td.id,table.lg th.id{width:1%;white-space:nowrap}
table.long{font-size:13.5px}
table.long td{padding:5px 10px}
table.long tbody tr:nth-child(even) td{background:var(--zebra)}
table.req td:nth-child(2){width:46%}
table.req th:last-child{white-space:nowrap}
table.req td.method{font-family:var(--f-m);font-size:12.5px;white-space:nowrap}
.serves{display:block;font:12px/1.5 var(--f-m);color:var(--muted);margin-top:3px}
.serves a.ref{font-size:1em}
.none{color:var(--muted)}
figure{margin:0 0 18px}
figure.code figcaption,figure.example figcaption{font:600 11.5px/1.4 var(--f-m);color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 6px}
pre{margin:0;overflow-x:auto}
figure.code pre{background:var(--codebg);border:1px solid var(--line);border-radius:8px;padding:12px 14px}
figure.code pre code,details.dsrc pre code{border:0;background:none;padding:0;font-size:13px}
figure.example{border:1px dashed var(--line2);border-radius:10px;padding:12px 14px;background:var(--paper2)}
figure.example figcaption b{color:var(--ink)}
pre.exbody{font:13.5px/1.6 var(--f-b);white-space:pre-wrap;overflow-wrap:anywhere}
figure.diagram{border:1px solid var(--line);border-radius:10px;padding:14px;background:var(--paper);overflow-x:auto}
svg.dg{display:block;max-width:100%;height:auto;margin:0 auto;color:var(--ink);font:13px var(--f-b)}
svg.dg .dgn{fill:var(--paper2);stroke:var(--ink);stroke-width:1.4}
svg.dg .dgs{fill:var(--ink)}
svg.dg .dge{stroke:var(--muted);stroke-width:1.5}
svg.dg .dgah{fill:var(--muted)}
svg.dg .dgt{fill:var(--ink);font-size:13px;font-weight:550}
svg.dg .dgl{fill:var(--ink);font-size:12px;paint-order:stroke;stroke:var(--paper);stroke-width:5px;stroke-linejoin:round}
svg.dg .dgx{fill:none;stroke-dasharray:5 4}
figure figcaption{font:12.5px/1.5 var(--f-b);color:var(--muted);margin-top:8px}
ol.flowchain{list-style:none;padding:0;margin:4px 0 16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px 26px}
ol.flowchain>li{position:relative;display:flex;gap:10px;margin:0;border:1px solid var(--line2);border-radius:10px;padding:10px 12px;background:var(--paper);font-size:14px;line-height:1.5}
ol.flowchain>li .fn{flex:none;font:700 12px/1.6 var(--f-m);color:var(--accent)}
ol.flowchain>li:not(:last-child)::after{content:"";position:absolute;right:-18px;top:50%;width:9px;height:9px;border:solid var(--muted);border-width:2px 2px 0 0;transform:translateY(-50%) rotate(45deg)}
p.failpath{border:1px solid var(--line2);border-left:4px solid var(--ask);border-radius:8px;padding:8px 12px;background:var(--asksoft)}
figure.context{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(110px,170px) auto minmax(0,1fr);align-items:center;gap:12px;border:1px solid var(--line);border-radius:10px;padding:14px;background:var(--paper)}
figure.context .side{display:flex;flex-direction:column;gap:6px;min-width:0}
figure.context .lbl{font:650 11px/1.4 var(--f-b);text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
figure.context .node{border:1px solid var(--line2);border-radius:8px;padding:6px 10px;background:var(--paper2);font-size:14px}
figure.context .more{font-size:12.5px;color:var(--muted)}
figure.context .core{text-align:center;font:700 15px/1.3 var(--f-d);background:var(--ink);color:var(--paper);border-radius:10px;padding:16px 12px}
figure.context .arr{flex:none;font-size:20px;color:var(--muted)}
figure.context figcaption{grid-column:1/-1}
details.dsrc{margin-top:10px;font-size:13px}
details.dsrc summary{cursor:pointer;color:var(--muted)}
details.dsrc pre{background:var(--codebg);border-radius:6px;padding:10px 12px;margin-top:6px}
aside.callout{border:1px solid var(--line2);border-left:4px solid var(--accent);border-radius:8px;padding:10px 14px;margin:0 0 16px;background:var(--paper2)}
aside.callout-warning,aside.callout-caution,aside.callout-important{border-left-color:var(--ask)}
aside.callout .clab{display:block;font:650 12px/1.4 var(--f-b);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:4px}
aside.callout>*:last-child,blockquote>*:last-child{margin-bottom:0}
blockquote{margin:0 0 16px;padding:2px 0 2px 14px;border-left:3px solid var(--line2);color:var(--muted)}
"""

READER_CSS = """
.bar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:8px;padding:8px 16px;background:var(--paper);border-bottom:1px solid var(--line)}
.bar .name{font:600 13px/1.3 var(--f-b);color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden;flex:none}
.seg button{font:600 13px/1 var(--f-b);color:var(--muted);background:none;border:0;padding:8px 12px;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.bar details{position:relative;flex:none}
.bar summary{list-style:none;cursor:pointer;font:600 13px/1 var(--f-b);color:var(--ink);border:1px solid var(--line2);border-radius:8px;padding:8px 12px;background:var(--paper);white-space:nowrap}
.bar summary::-webkit-details-marker{display:none}
.bar summary::after{content:"";display:inline-block;width:6px;height:6px;border:solid currentColor;border-width:0 1.5px 1.5px 0;transform:translateY(-3px) rotate(45deg);margin-left:8px}
.dli{vertical-align:-2px;margin-right:6px}
.menu{position:absolute;right:0;top:calc(100% + 6px);min-width:220px;background:var(--paper);border:1px solid var(--line2);border-radius:10px;box-shadow:0 10px 28px var(--shadow);padding:6px;z-index:6}
.menu a,.menu button{display:block;width:100%;text-align:left;font:14px/1.4 var(--f-b);color:var(--ink);text-decoration:none;padding:8px 10px;border-radius:6px;background:none;border:0;cursor:pointer}
.menu a:hover,.menu a:focus-visible{background:var(--paper2)}
.menu a small{display:block;color:var(--muted);font-size:12px}
.menu.toc{left:0;right:auto;max-height:min(70vh,520px);overflow:auto;width:min(86vw,340px)}
.menu.toc a{padding:6px 10px}.menu.toc a.l3{padding-left:24px;font-size:13.5px;color:var(--muted)}
.note{font:12.5px/1.4 var(--f-b);color:var(--muted);padding:6px 10px}
.wrap{display:grid;grid-template-columns:minmax(0,1fr);gap:28px;padding:22px 18px 72px;max-width:1080px;margin:0 auto}
.rail{display:none}
.rail p{font:650 11.5px/1.4 var(--f-b);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 0 8px}
.rail a{display:block;font:13.5px/1.35 var(--f-b);color:var(--muted);text-decoration:none;padding:4px 0 4px 10px;border-left:2px solid transparent}
.rail a.l3{padding-left:22px;font-size:13px}
.rail a:hover{color:var(--ink)}
.rail a[aria-current=true]{color:var(--ink);border-left-color:var(--accent);font-weight:600}
.wrap.srcwrap{grid-template-columns:minmax(0,1fr)!important}
.src{font:13px/1.6 var(--f-m);background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:14px 0;white-space:pre-wrap;overflow-wrap:anywhere;counter-reset:ln;max-width:900px;margin:0 auto;width:100%}
.src span{display:block;padding:0 16px 0 58px;text-indent:-42px;min-height:1.6em}
.src span::before{counter-increment:ln;content:counter(ln);display:inline-block;width:32px;margin-right:10px;text-align:right;color:var(--muted);opacity:.7;text-indent:0;user-select:none}
html:not(.js) .bar{display:none}
html.inframe .bar .name{visibility:hidden}
html.js:not(.themed) body{visibility:hidden}
@media (min-width:860px){
 .wrap{grid-template-columns:minmax(0,740px) 190px;justify-content:center;gap:36px;padding:28px 24px 80px}
 .rail{display:block;position:sticky;top:calc(var(--barh,56px) + 20px);align-self:start;max-height:calc(100vh - var(--barh,56px) - 40px);overflow:auto}
 .tocdd{display:none}
}
@media (max-width:560px){
 body{font-size:15px}
 .dhead h1{font-size:25px}
 .bar{padding:8px 12px;gap:6px;flex-wrap:wrap}
 .bar .name{display:none}
 .dlt{display:none}
 .dli{margin-right:0}
 .seg button{padding:8px 10px}
 .tocdd{order:-1;flex:1}
 .tocdd summary{width:100%}
 .wrap{padding:16px 14px 64px}
 .tw{overflow:visible}
 table.stack,table.stack tbody,table.stack tr,table.stack td{display:block;width:auto!important}
 table.stack thead{display:none}
 table.stack tr{padding:10px 0;border-bottom:1px solid var(--line)}
 table.stack td{border:0;padding:2px 0;white-space:normal!important;background:none!important}
 table.stack td::before{content:attr(data-label);display:block;font:650 11px/1.5 var(--f-b);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-top:6px}
 table.stack td.id::before{display:none}
 table.stack tbody tr:nth-child(even){background:none}
 ol.ids>li{grid-template-columns:40px minmax(0,1fr);gap:0 8px}
 ol.flowchain{grid-template-columns:1fr;gap:18px}
 ol.flowchain>li:not(:last-child)::after{right:auto;left:22px;top:auto;bottom:-14px;transform:rotate(135deg)}
 figure.context{grid-template-columns:1fr;align-items:stretch}
 figure.context .arr{transform:rotate(90deg);align-self:center}
}
"""

READER_JS = r"""
(function(){
"use strict";
var de=document.documentElement,body=document.body,bar=document.getElementById("bar");
de.classList.add("js");
var inFrame=window.parent&&window.parent!==window;
if(inFrame)de.classList.add("inframe");
function send(m){ if(!inFrame)return; m.sutraDoc=1; try{window.parent.postMessage(m,"*");}catch(e){} }
function theme(t){ if(t==="dark"||t==="light")de.dataset.theme=t; de.classList.add("themed"); }
setTimeout(function(){de.classList.add("themed");},inFrame?350:0);
function barh(){ if(bar)de.style.setProperty("--barh",bar.offsetHeight+"px"); }
barh(); window.addEventListener("resize",barh);
var name=body.getAttribute("data-name")||"";
var mode="preview",doc=document.getElementById("view"),src=document.getElementById("srcwrap");
function setMode(m,tell){ mode=m==="source"?"source":"preview"; doc.hidden=mode!=="preview"; src.hidden=mode!=="source";
  document.querySelectorAll("[data-mode]").forEach(function(b){b.setAttribute("aria-pressed",String(b.getAttribute("data-mode")===mode));});
  var dd=document.getElementById("tocdd"); if(dd)dd.hidden=mode!=="preview";
  if(tell)send({type:"mode",mode:mode,name:name}); }
document.querySelectorAll("[data-mode]").forEach(function(b){b.addEventListener("click",function(){setMode(b.getAttribute("data-mode"),true);});});
function fileHref(f){ var q=new URLSearchParams(location.search),o=new URLSearchParams(); ["dept","run"].forEach(function(k){ if(q.get(k))o.set(k,q.get(k)); }); o.set("name",f); return "/api/artifact?"+o.toString(); }
document.querySelectorAll("a[data-file]").forEach(function(a){ var f=a.getAttribute("data-file"); a.href=fileHref(f); a.setAttribute("download",f.split("/").pop());
  a.addEventListener("click",function(e){ var dl=document.getElementById("dl"); if(dl)dl.open=false;
    if(inFrame){ e.preventDefault(); send({type:"download",href:fileHref(f),file:f.split("/").pop()}); } });
});
document.addEventListener("click",function(e){ document.querySelectorAll(".bar details[open]").forEach(function(d){ if(!d.contains(e.target))d.open=false; }); });
document.addEventListener("keydown",function(e){ if(e.key==="Escape")document.querySelectorAll(".bar details[open]").forEach(function(d){d.open=false;}); });
function jump(id){ var el=document.getElementById(id); if(!el)return;
  if(mode!=="preview")setMode("preview",true);
  var dd=document.getElementById("tocdd"); if(dd)dd.open=false;
  requestAnimationFrame(function(){ barh(); var y=el.getBoundingClientRect().top+window.pageYOffset-(bar?bar.offsetHeight:0)-10;
    window.scrollTo({top:Math.max(0,y),behavior:"auto"}); try{history.replaceState(null,"","#"+id);}catch(e){}
    document.querySelectorAll(".tgt").forEach(function(x){x.classList.remove("tgt");}); });
}
document.addEventListener("click",function(e){ var a=e.target.closest&&e.target.closest('a[href^="#"]'); if(!a)return;
  var id=decodeURIComponent(a.getAttribute("href").slice(1)); if(!id||!document.getElementById(id))return; e.preventDefault(); jump(id); });
var links=[].slice.call(document.querySelectorAll(".rail a[href^='#']")),secs=links.map(function(a){return document.getElementById(a.getAttribute("href").slice(1));});
function spy(){ var top=(bar?bar.offsetHeight:0)+24,cur=-1; secs.forEach(function(s,i){ if(s&&s.getBoundingClientRect().top<=top)cur=i; });
  links.forEach(function(a,i){ a.setAttribute("aria-current",String(i===cur)); }); }
window.addEventListener("scroll",spy,{passive:true}); spy();
window.addEventListener("message",function(e){ if(e.source!==window.parent)return; var m=e.data||{}; if(!m||m.sutraDoc!==1)return;
  if(m.type==="theme")theme(m.theme);
  if(m.type==="mode"&&(m.mode==="preview"||m.mode==="source"))setMode(m.mode,false);
});
if(!inFrame){ theme(""); }
send({type:"ready",name:name});
})();
"""


def _body_and_toc(md, title):
    bl = blocks(md)
    ids = frozenset(defined_ids(bl))
    first = next((i for i, b in enumerate(bl) if b["t"] == "h"), -1)
    used = first if first >= 0 and bl[first]["level"] == 1 else -1
    toc = []
    shown_title = _plain(bl[used]["text"]) if used >= 0 else str(title or "Document")
    body = _body(bl, ids, used, _slugger(), toc, _pictures(bl, shown_title))
    shown = _plain(bl[used]["text"]) if used >= 0 else str(title or "Document")
    return shown, body, toc


def _head(title, meta):
    line = meta_line(meta)
    return (f'<header class="dhead"><h1>{html.escape(title)}</h1>'
            + (f'<p class="meta">{html.escape(line)}</p>' if line else "") + "</header>")


def reader_html(md, title="Document", meta=None, name="", chrome=True):
    """The Files pane's page for one Markdown file. `name` is the file's name in the run (the Download menu exports it; no name, no
    Download). `chrome=False` is the bare document (a section preview): no bar, no rail, no script."""
    shown, body, toc = _body_and_toc(md, title)
    head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>{html.escape(shown)}</title><style>{_font_css()}{TOKENS}{DOC_CSS}')
    if not chrome:
        return (head + ".doc{margin:0 auto;padding:20px 18px}</style></head><body><main class=\"doc\">" + body + "</main></body></html>")
    rail = "".join(f'<a class="l{lv}" href="#{sid}">{html.escape(text)}</a>' for lv, sid, text in toc)
    dd = (f'<details class="tocdd" id="tocdd"><summary>On this page</summary><nav class="menu toc" aria-label="On this page">{rail}</nav></details>'
          if toc else "")
    word = str((meta or {}).get("word") or "")
    files = ([(name, "Markdown (.md)", "The original file")] if name else []) + ([(word, "Word (.docx)", "Exported when the run finished")] if word else [])
    dl = ('<details class="dl" id="dl"><summary aria-label="Download"><svg class="dli" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg><span class="dlt">Download</span></summary><div class="menu" role="menu">'
          + "".join(f'<a role="menuitem" data-file="{html.escape(f, quote=True)}" href="#">{lab}<small>{sub}</small></a>' for f, lab, sub in files)
          + "</div></details>") if files else ""
    src = "".join(f"<span>{html.escape(x)}</span>" for x in str(md or "").replace("\r\n", "\n").split("\n"))
    return (head + READER_CSS + "</style></head>"
            f'<body data-name="{html.escape(name, quote=True)}">'
            f'<div class="bar" id="bar"><span class="name">{html.escape(name or shown)}</span>'
            '<div class="seg" role="group" aria-label="View"><button type="button" data-mode="preview" aria-pressed="true">Preview</button>'
            '<button type="button" data-mode="source" aria-pressed="false">Markdown</button></div>'
            f"{dd}{dl}</div>"
            '<div class="wrap" id="view"><main class="doc" id="doc">' + _head(shown, meta) + body + "</main>"
            + (f'<nav class="rail" aria-label="On this page"><p>On this page</p>{rail}</nav>' if toc else "") + "</div>"
            f'<div class="wrap srcwrap" id="srcwrap" hidden><pre class="src" id="src" aria-label="Markdown source">{src}</pre></div>'
            f"<script>{READER_JS}</script></body></html>")
