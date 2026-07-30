#!/usr/bin/env python3
"""generate-departments.py — regenerate departments.html from the live registry.

Standardized renderer for the core:departments module's WEB surface (the CLI
surface lives in the skill). Two levels of depth, left index rail, one-line
description per department, dotted info blocks for children. Run from the
asawa-holding root:

    python3 sutra/website/generate-departments.py

Design rules applied (dataviz skill, 2026-07-30): hierarchy via typography and
spacing; text wears ink tokens; ONE accent used sparingly (index chips, links);
recessive structure lines; light/dark from the same tokens. Third-party client
names are withheld on the public page.
"""
import sys, os, html

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "marketplace", "plugin", "lib"))
import placement_engine as E  # noqa: E402

WITHHOLD_CHILDREN_OF = {"Client Projects (T3)"}

domains = E.load_domains()
kids, root = {}, None
for r, d in domains.items():
    p = d.get("parent_ref")
    if p is None:
        root = r
    kids.setdefault(p, []).append(r)
for v in kids.values():
    v.sort(key=lambda r: domains[r].get("ts_minted_ms", 0))

def esc(s): return html.escape(s or "")

tops = kids.get(root, [])
rail, sections = [], []
for i, t in enumerate(tops, 1):
    d = domains[t]
    ch = kids.get(t, [])
    anchor = "d%d" % i
    rail.append('<a href="#%s"><span class="chip">D%d</span>%s</a>'
                % (anchor, i, esc(d["name"])))
    if d["name"] in WITHHOLD_CHILDREN_OF:
        blocks = ('<div class="info withheld">%d client projects — names withheld '
                  'on the public page</div>' % len(ch))
    elif ch:
        blocks = "".join(
            '<div class="info"><span class="chip">D%d.%d</span>'
            '<b>%s</b><p>%s</p></div>'
            % (i, j, esc(domains[c]["name"]),
               esc(domains[c].get("description", "")))
            for j, c in enumerate(ch, 1))
    else:
        blocks = '<div class="info empty">no sub-departments yet</div>'
    sections.append(
        '<section id="%s" class="dept"><header><span class="chip big">D%d</span>'
        '<div><h2>%s</h2><p class="desc">%s</p></div>'
        '<span class="count">%d</span></header><div class="grid">%s</div></section>'
        % (anchor, i, esc(d["name"]), esc(d.get("description", "")), len(ch), blocks))

rootd = domains[root]
page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sutra · Company Departments</title>
<style>
:root{--bg:#fafaf9;--card:#fff;--ink:#1c1917;--mut:#78716c;--line:#e7e5e4;--acc:#1d4ed8;--accbg:#eff4ff}
@media(prefers-color-scheme:dark){:root{--bg:#101010;--card:#1a1a1a;--ink:#f5f5f4;--mut:#a8a29e;--line:#2c2a28;--acc:#8ab0ff;--accbg:#1b2540}}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif}
.layout{max-width:1100px;margin:0 auto;padding:40px 20px;display:grid;grid-template-columns:220px 1fr;gap:34px}
nav{position:sticky;top:24px;align-self:start;font-size:.92rem}
nav a{display:flex;align-items:center;gap:8px;color:var(--ink);text-decoration:none;padding:7px 8px;border-radius:8px}
nav a:hover{background:var(--accbg)}
.chip{font:600 .72rem/1 ui-monospace,Menlo,monospace;color:var(--acc);background:var(--accbg);border-radius:6px;padding:3px 7px;flex:none}
.chip.big{font-size:.85rem;padding:6px 10px}
h1{font-size:1.65rem;letter-spacing:-.01em}
.rootdesc{color:var(--mut);margin:6px 0 30px;max-width:60ch}
.dept{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:22px;scroll-margin-top:20px}
.dept:target{border-color:var(--acc)}
.dept header{display:flex;gap:14px;align-items:flex-start;margin-bottom:14px}
.dept h2{font-size:1.12rem}
.desc{color:var(--mut);font-size:.92rem;margin-top:2px;max-width:58ch}
.count{margin-left:auto;font:600 .75rem/1 ui-monospace,monospace;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.info{border:1.5px dashed var(--line);border-radius:10px;padding:12px 14px}
.info b{display:inline-block;margin-left:8px;font-size:.95rem}
.info p{color:var(--mut);font-size:.85rem;margin-top:6px}
.info.withheld,.info.empty{color:var(--mut);font-style:italic}
footer{grid-column:1/-1;color:var(--mut);font-size:.8rem;margin-top:8px}
@media(max-width:760px){.layout{grid-template-columns:1fr}nav{position:static;display:flex;flex-wrap:wrap;gap:4px}}
</style></head><body><div class="layout">
<nav>%s</nav>
<main>
<h1>%s</h1>
<p class="rootdesc">%s</p>
%s
<footer>%d departments · two levels of depth · generated from the live placement registry (ADR-028) · MECE: every area has exactly one home</footer>
</main>
</div></body></html>
""" % ("".join(rail), esc(rootd["name"]), esc(rootd.get("description", "")),
       "".join(sections), len(domains))

out = os.path.join(HERE, "departments.html")
open(out, "w").write(page)
print("wrote %s (%d bytes, %d departments)" % (out, os.path.getsize(out), len(domains)))
