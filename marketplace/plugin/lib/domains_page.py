#!/usr/bin/env python3
"""domains_page.py — fleet-wide generator for a company's public Domains page.

The web surface of the core:domains module (ADR-028). One page per company:
left index rail, two levels of depth, one-line description AND charter per
domain, dotted child blocks — rendered in THAT company's design system.

Terminology (founder 2026-07-30): internally these are DOMAINS, always; the
page may display "Departments" as a user-facing synonym via --label.

Design system: carried by the D0 (root) domain's `design` field:
    {"bg":..,"card":..,"ink":..,"muted":..,"line":..,"accent":..,"accent_bg":..,
     "font":.., "source": "<where these tokens came from>"}
Detection order (the skill documents this): D0.design -> detect from the
company's own site CSS -> neutral fallback (and SAY it's the fallback).

Usage:  python3 domains_page.py OUT.html [--label Departments] [--title "..."]
Reads the registry at $SUTRA_NATIVE_HOME (default ~/.sutra-native/user-kit).
Third-party names: any domain with `public_names_withheld` true on the parent
hides child names on the public page.
"""
import sys, os, html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import placement_engine as E  # noqa: E402

NEUTRAL = {"bg": "#fafaf9", "card": "#ffffff", "ink": "#1c1917", "muted": "#78716c",
           "line": "#e7e5e4", "accent": "#1d4ed8", "accent_bg": "#eff4ff",
           "font": "-apple-system,'Segoe UI',Roboto,sans-serif", "source": "neutral fallback"}


def build(out_path, label="Domains", title=None):
    domains = E.load_domains()
    if not domains:
        raise SystemExit("registry empty — run a scan or seed the org tree first")
    kids, root = {}, None
    for r, d in domains.items():
        p = d.get("parent_ref")
        if p is None:
            root = r
        kids.setdefault(p, []).append(r)
    for v in kids.values():
        v.sort(key=lambda r: domains[r].get("ts_minted_ms", 0))
    rootd = domains[root]
    T = dict(NEUTRAL)
    T.update(rootd.get("design") or {})

    def esc(s): return html.escape(s or "")

    def charter_line(ref):
        # a domain hosts MANY charters — render every one (founder 2026-07-30)
        chs = sorted(E.charters_for(ref), key=lambda x: x["id"])
        return "".join('<p class="charter"><span>Charter</span> %s — %s</p>'
                       % (esc(c.get("title", "")), esc(c.get("purpose", "")))
                       for c in chs)

    def org_diagram(parent_name, child_names):
        if not child_names:
            return ""
        boxes = "".join('<div class="tnode">%s</div>' % esc(n) for n in child_names)
        return ('<div class="tree"><div class="tnode troot">%s</div>'
                '<div class="tdown"></div><div class="tkids">%s</div></div>'
                % (esc(parent_name), boxes))

    tops = kids.get(root, [])
    rail, sections = [], []

    def dpath_idx(idx):                       # [1,2] -> "D1.2" / anchor "d1-2"
        return "D" + ".".join(str(x) for x in idx), "d" + "-".join(str(x) for x in idx)

    def nav_entry(ref, idx, depth):
        d = domains[ref]
        ch = [] if d.get("public_names_withheld") else kids.get(ref, [])
        label_i, anchor = dpath_idx(idx)
        if ch:
            inner = "".join(nav_entry(c, idx + [j], depth + 1)
                            for j, c in enumerate(ch, 1))
            return ('<details class="navgrp"%s><summary><span class="chip">%s</span>'
                    '<a href="#%s">%s</a><span class="navcount">%d</span></summary>'
                    '<div class="navkids">%s</div></details>'
                    % (" open" if depth < 2 else "", label_i, anchor, esc(d["name"]),
                       len(ch), inner))
        return ('<a class="sub" href="#%s"><span class="chip">%s</span>%s</a>'
                % (anchor, label_i, esc(d["name"])))

    def node_block(ref, idx, depth):
        """One domain as a dotted block: chip, name, desc, charters — and if it
        has children, its OWN cascading diagram + child blocks inside, at any
        depth (founder 2026-07-30: the entire structure is cascading)."""
        d = domains[ref]
        ch = [] if d.get("public_names_withheld") else kids.get(ref, [])
        label_i, anchor = dpath_idx(idx)
        body = ('<span class="chip">%s</span><b>%s</b><p>%s</p>%s'
                % (label_i, esc(d["name"]), esc(d.get("description", "")), charter_line(ref)))
        if d.get("public_names_withheld") and kids.get(ref):
            body += ('<p class="withheld">%d entries — names withheld on the public page</p>'
                     % len(kids.get(ref, [])))
        if ch:
            inner = "".join(node_block(c, idx + [j], depth + 1)
                            for j, c in enumerate(ch, 1))
            body += ('<details class="cascade"%s><summary>%d sub-domains</summary>'
                     '%s<div class="grid">%s</div></details>'
                     % (" open" if depth < 2 else "",
                        len(ch), org_diagram(d["name"], [domains[c]["name"] for c in ch]),
                        inner))
        return '<div class="info" id="%s">%s</div>' % (anchor, body)

    for i, t in enumerate(tops, 1):
        d = domains[t]
        ch = [] if d.get("public_names_withheld") else kids.get(t, [])
        label_i, anchor = dpath_idx([i])
        rail.append(nav_entry(t, [i], 1))
        if d.get("public_names_withheld"):
            blocks = ('<div class="info withheld">%d entries — names withheld on the public page</div>'
                      % len(kids.get(t, [])))
        elif ch:
            blocks = "".join(node_block(c, [i, j], 2) for j, c in enumerate(ch, 1))
        else:
            blocks = '<div class="info empty">no sub-%s yet</div>' % label.lower()
        diag = "" if d.get("public_names_withheld") else org_diagram(
            d["name"], [domains[c]["name"] for c in ch])
        sections.append(
            '<section id="%s" class="dept"><header><span class="chip big">%s</span>'
            '<div><h2>%s</h2><p class="desc">%s</p>%s</div><span class="count">%d</span>'
            '</header>%s<div class="grid">%s</div></section>'
            % (anchor, label_i, esc(d["name"]), esc(d.get("description", "")),
               charter_line(t), len(kids.get(t, [])), diag, blocks))

    rootdiag = org_diagram(rootd["name"], [domains[t]["name"] for t in tops])
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<style>
:root{--bg:%(bg)s;--card:%(card)s;--ink:%(ink)s;--mut:%(muted)s;--line:%(line)s;--acc:%(accent)s;--accbg:%(accent_bg)s}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.55 %(font)s}
.layout{max-width:1100px;margin:0 auto;padding:40px 20px;display:grid;grid-template-columns:220px 1fr;gap:34px}
nav{position:sticky;top:24px;align-self:start;font-size:.92rem}
nav a{display:flex;align-items:center;gap:8px;color:var(--ink);text-decoration:none;padding:7px 8px;border-radius:8px}
nav a:hover{background:var(--accbg)}
.chip{font:600 .72rem/1 ui-monospace,Menlo,monospace;color:var(--ink);background:var(--accbg);border:1px solid var(--acc);border-radius:6px;padding:3px 7px;flex:none}
.chip.big{font-size:.85rem;padding:6px 10px}
h1{font-size:1.65rem;letter-spacing:-.01em}
.rootdesc{color:var(--mut);margin:6px 0 30px;max-width:60ch}
.dept{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:22px;scroll-margin-top:20px}
.dept:target{border-color:var(--acc)}
.dept header{display:flex;gap:14px;align-items:flex-start;margin-bottom:14px}
.dept h2{font-size:1.12rem}
.desc{color:var(--mut);font-size:.92rem;margin-top:2px;max-width:58ch}
.charter{font-size:.8rem;color:var(--mut);margin-top:6px;max-width:58ch}
.charter span{font:600 .68rem/1 ui-monospace,monospace;color:var(--acc);border:1px dotted var(--acc);border-radius:5px;padding:2px 6px;margin-right:6px}
.count{margin-left:auto;font:600 .75rem/1 ui-monospace,monospace;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.info{border:1.5px dashed var(--line);border-radius:10px;padding:12px 14px}
.info b{display:inline-block;margin-left:8px;font-size:.95rem}
.info p{color:var(--mut);font-size:.85rem;margin-top:6px}
.info.withheld,.info.empty{color:var(--mut);font-style:italic}
.cascade{margin-top:10px;border-top:1px dotted var(--line);padding-top:8px}
.cascade summary{cursor:pointer;font-size:.78rem;color:var(--acc);list-style:none}
.cascade summary::before{content:"\25B8 ";font-size:.7rem}
.cascade[open] summary::before{content:"\25BE "}
.cascade .grid{margin-top:10px;grid-template-columns:1fr}
.navgrp summary a{color:var(--ink);text-decoration:none;flex:1}
.navgrp summary a:hover{color:var(--acc)}
.navcount{font:600 .68rem/1 ui-monospace,monospace;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:1px 7px}
.navkids{margin:2px 0 6px 14px}
.navkids .navgrp summary{padding:5px 6px;font-size:.88rem}
footer{color:var(--mut);font-size:.8rem;margin-top:8px}
.navgrp summary{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:8px;cursor:pointer;list-style:none}
.navgrp summary::before{content:"\25B8";font-size:.7rem;color:var(--mut)}
.navgrp[open] summary::before{content:"\25BE"}
.navgrp summary:hover{background:var(--accbg)}
.navkids{margin-left:14px;border-left:2px solid var(--line);padding-left:8px}
.navkids a.sub{font-size:.85rem;padding:5px 6px}
.tree{margin:6px 0 18px;text-align:center}
.tnode{display:inline-block;background:var(--card);border:1.5px solid var(--acc);border-radius:8px;padding:6px 14px;font-size:.85rem;font-weight:600}
.tnode.troot{background:var(--accbg)}
.tdown{width:2px;height:14px;background:var(--line);margin:0 auto}
.tkids{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;position:relative;padding-top:14px}
.tkids::before{content:"";position:absolute;top:0;left:12%%;right:12%%;height:2px;background:var(--line)}
.tkids .tnode{position:relative;border-width:1px;border-color:var(--line);font-weight:500}
.tkids .tnode::before{content:"";position:absolute;top:-14px;left:50%%;width:2px;height:14px;background:var(--line)}
#q{width:100%%;margin-bottom:10px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;font-size:.9rem}
#q:focus{outline:2px solid var(--acc)}
.hidden{display:none !important}
mark{background:var(--accbg);color:inherit;border-radius:3px}
@media(max-width:760px){.layout{grid-template-columns:1fr}nav{position:static;display:flex;flex-wrap:wrap;gap:4px}}
</style></head><body><div class="layout">
<nav><input id="q" type="search" placeholder="Search domains..." autocomplete="off">%(rail)s</nav>
<main>
<h1>%(root)s</h1>
<p class="rootdesc">%(rootdesc)s</p>
%(rootdiag)s
%(sections)s
<footer>%(n)d %(label_l)s · two levels of depth · generated from the live placement registry (ADR-028) · design tokens: %(src)s</footer>
</main>
<script>
(function(){var q=document.getElementById('q');if(!q)return;
q.addEventListener('input',function(){var v=q.value.trim().toLowerCase();
document.querySelectorAll('section.dept').forEach(function(sec){
 var any=false;
 sec.querySelectorAll('.info').forEach(function(b){
  var hit=!v||b.textContent.toLowerCase().indexOf(v)>=0;
  b.classList.toggle('hidden',!hit);if(hit)any=true;});
 var selfHit=!v||sec.querySelector('header').textContent.toLowerCase().indexOf(v)>=0;
 sec.classList.toggle('hidden',!(any||selfHit));
 if(v)sec.querySelectorAll('details.cascade').forEach(function(d){d.open=true;});});
document.querySelectorAll('nav a.sub, nav details.navgrp').forEach(function(n){
 var hit=!v||n.textContent.toLowerCase().indexOf(v)>=0;
 n.classList.toggle('hidden',!hit);});});})();
</script>
</div></body></html>
""" % dict(title=esc(title or "%s · %s" % (rootd["name"], label)), rail="".join(rail),
           root=esc(rootd["name"]), rootdesc=esc(rootd.get("description", "")),
           rootdiag=rootdiag,
           sections="".join(sections), n=len(domains), label_l=label.lower(),
           src=esc(T.get("source", "")), **{k: T[k] for k in
           ("bg", "card", "ink", "muted", "line", "accent", "accent_bg", "font")})

    open(out_path, "w").write(page)
    return out_path, len(domains)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    label = "Departments" if "--label" not in " ".join(sys.argv) else \
        sys.argv[sys.argv.index("--label") + 1]
    out = args[0] if args else "domains.html"
    p, n = build(out, label=label)
    print("wrote %s (%d domains)" % (p, n))
