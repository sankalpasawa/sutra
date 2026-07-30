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
import sys, os, html, json

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


def build_site(out_dir, label="Domains", window=2):
    """Drill-down zoom site (founder 2026-07-30): every domain gets its OWN
    page rooted at itself, ALL pages from one template (consistency layer).
    Exactly window+1 = 3 levels of D per page:
      L1 page domain — h1 + description + charters + diagram of children
      L2 children    — full dotted blocks: description + charters + diagram
      L3 grandkids   — SUMMARY only: whole card clickable, name + one-liner
                       + "open > N inside" (only when N > 0); charters live
                       one click away on the grandchild's own page
    Clicking any domain opens ITS page, which repeats the same template one
    level down. Left nav is sticky + minimal: children visible, grandchild
    groups collapsed unless the page has <= 6 of them (codex fold). Search
    on every page. Filenames are stable refs (survive restructure).
    index.html = the root domain."""
    domains = E.load_domains()
    if not domains:
        raise SystemExit("registry empty — run a scan or seed the org tree first")
    kids, root = {}, None
    for r, d in domains.items():
        p_ = d.get("parent_ref")
        if p_ is None:
            root = r
        kids.setdefault(p_, []).append(r)
    for v in kids.values():
        v.sort(key=lambda r: domains[r].get("ts_minted_ms", 0))
    os.makedirs(out_dir, exist_ok=True)
    T = dict(NEUTRAL)
    T.update(domains[root].get("design") or {})

    # Privacy parity with the flat renderer (codex fold 2026-07-30): a
    # `public_names_withheld` domain hides its children's names, and no page
    # is generated for any hidden descendant — a ref-named page would leak
    # the very names the flag withholds.
    hidden = set()
    def _hide(ref):
        for c in kids.get(ref, []):
            hidden.add(c); _hide(c)
    for r, d in domains.items():
        if d.get("public_names_withheld"):
            _hide(r)

    def esc(s): return html.escape(s or "")
    def fname(ref): return "index.html" if ref == root else ref + ".html"
    def vis_kids(ref):
        return [] if domains[ref].get("public_names_withheld") else kids.get(ref, [])
    def withheld_note(ref):
        n = len(kids.get(ref, []))
        return ('<p class="withheld">%d entries — names withheld on the public page</p>' % n) \
            if domains[ref].get("public_names_withheld") and n else ""

    # ---- charter layer (founder 2026-07-30: past projects ARE charters) ----
    # One owner (domain_ref, the existing invariant) + linked_domain_refs as
    # references, never homes. Render-time defaults keep the pre-existing
    # stub charters valid with zero migration (codex fold).
    all_ch = []
    for fn in os.listdir(E.CHARTERS):
        if not fn.endswith(".json"):
            continue
        try:
            c = json.load(open(os.path.join(E.CHARTERS, fn)))
        except (ValueError, OSError):
            continue
        c.setdefault("kind", "standing")
        c.setdefault("status", "active")
        c.setdefault("linked_domain_refs", [])
        c.setdefault("artifacts", [])
        all_ch.append(c)
    all_ch.sort(key=lambda c: c.get("id", ""))
    owned_by, linked_to = {}, {}
    for c in all_ch:
        owned_by.setdefault(c.get("domain_ref"), []).append(c)
        for lr in c["linked_domain_refs"]:
            linked_to.setdefault(lr, []).append(c)

    def st_tag(c):
        return '<span class="st st-%s">%s</span>' % (c["status"], c["status"])

    # Charter TAGS (founder 2026-07-30: prose pills unreadable). Density
    # heuristic (codex fold): a group shows visible one-liners only when it
    # has <= 3 charters AND their purposes fit a small budget; otherwise
    # compact chips — purpose on hover (desktop, title attr on the CLOSED
    # summary only) and tap-to-expand (native <details>, works on touch).
    def st_dot(c):
        return '<span class="chdot st-%s"><i></i>%s</span>' % (c["status"], c["status"])

    def _art_n(c):
        n = len(c["artifacts"])
        return ('<span class="chart-n">%d</span>' % n) if n else ""

    def _links_of(c):
        return [r for r in c["linked_domain_refs"] if r in domains and r not in hidden]

    def _links_html(c):
        links = _links_of(c)
        if not links:
            return ""
        return ('<span class="chlinks">linked: %s</span>'
                % ", ".join('<a href="%s">%s</a>' % (fname(r), esc(domains[r]["name"]))
                            for r in links))

    def ch_panel(c):
        arts = "".join('<code class="chpath">%s</code>' % esc(a) for a in c["artifacts"][:6])
        more = ('<span class="chart-n">+%d more</span>' % (len(c["artifacts"]) - 6)) \
            if len(c["artifacts"]) > 6 else ""
        return ('<div class="chpanel"><p>%s</p>%s%s%s</div>'
                % (esc(c.get("purpose", "")), _links_html(c), arts, more))

    def ch_card(c):
        """Mini-card mode: chip + visible one-liner (no hover needed)."""
        return ('<div class="chcard">%s<b>%s</b>%s'
                '<p class="chline">%s</p>%s</div>'
                % (st_dot(c), esc(c["title"]), _art_n(c),
                   esc(c.get("purpose", "")), _links_html(c)))

    def ch_compact(c):
        """Dense mode: status + title + artifact count stay scannable
        (codex fold); purpose hovers on the closed summary + opens on tap."""
        return ('<details class="chd"><summary title="%s">%s<b>%s</b>%s</summary>%s</details>'
                % (esc(c.get("purpose", "")), st_dot(c), esc(c["title"]),
                   _art_n(c), ch_panel(c)))

    def ch_group(label_g, chs):
        if not chs:
            return ""
        dense = len(chs) > 3 or sum(len(c.get("purpose", "")) for c in chs) > 320
        body = "".join((ch_compact if dense else ch_card)(c) for c in chs)
        return ('<h3 class="chg">%s</h3><div class="chips%s">%s</div>'
                % (label_g, " dense" if dense else "", body))

    def charter_line(ref):
        """L2 compact form: standing titles as tiny hover chips + project count."""
        chs = owned_by.get(ref, [])
        standing = [c for c in chs if c["kind"] == "standing"]
        proj = [c for c in chs if c["kind"] == "project"]
        out = "".join('<span class="chmini" title="%s">%s</span>'
                      % (esc(c.get("purpose", "")), esc(c["title"])) for c in standing)
        if proj:
            out += ('<a class="chmini chmore" href="%s">%d project%s &rsaquo;</a>'
                    % (fname(ref), len(proj), "s" if len(proj) > 1 else ""))
        return ('<p class="chrow"><span class="chlabel">Charter</span>%s</p>' % out) if out else ""

    def charters_section(ref):
        """L1: ALWAYS present — the word CHARTER on every department page."""
        chs = owned_by.get(ref, [])
        standing = [c for c in chs if c["kind"] == "standing"]
        proj = [c for c in chs if c["kind"] == "project"]
        inbound = [c for c in linked_to.get(ref, [])
                   if c.get("domain_ref") in domains and c.get("domain_ref") not in hidden]
        h = ['<section class="chsec"><h2 class="chh">Charters</h2>']
        h.append(ch_group("Standing", standing))
        h.append(ch_group("Projects", proj))
        if not standing and not proj:
            h.append('<p class="chempty">none yet</p>')
        if inbound:
            linkchips = "".join(
                '<a class="chd chlinkchip" href="%s" title="%s">%s<b>%s</b>'
                '<span class="chowner">owned by %s</span></a>'
                % (fname(c["domain_ref"]), esc(c.get("purpose", "")), st_dot(c),
                   esc(c["title"]), esc(domains[c["domain_ref"]]["name"]))
                for c in inbound)
            h.append('<h3 class="chg">Linked</h3>'
                     '<div class="chips dense">%s</div>' % linkchips)
        h.append('</section>')
        return "".join(h)

    def child_of(page_ref, ref):
        """Roll a deep ref UP to the direct child of page_ref it sits under."""
        cur, seen = ref, set()
        while cur in domains and cur not in seen:
            seen.add(cur)
            par = domains[cur].get("parent_ref")
            if par == page_ref:
                return cur
            cur = par
        return None

    def lane_chart(page_ref, tops):
        """Horizontal figure (founder 2026-07-30): rows = charters that touch
        >= 2 of THIS page's direct children after roll-up; never descends
        into sub-departments. Codex P1 folds: refs are set-deduped per child
        column (owner wins a shared column); a charter owned by the page
        itself renders with linked columns only."""
        tset = set(tops)
        if len(tops) < 2:
            return ""
        rows = []
        for c in all_ch:
            owner = c.get("domain_ref")
            cols = {}
            for r in set([owner] + c["linked_domain_refs"]):
                if r == page_ref or r not in domains:
                    continue
                col = child_of(page_ref, r)
                if col not in tset:
                    continue
                role = "O" if r == owner else "L"
                if cols.get(col) != "O":
                    cols[col] = role
            if len(cols) < 2:
                continue
            cells = []
            for t in tops:
                m = cols.get(t)
                if m == "O":
                    cells.append('<td class="lo" aria-label="Owner: %s">O</td>' % esc(c["title"]))
                elif m == "L":
                    cells.append('<td class="ll" aria-label="Linked: %s">L</td>' % esc(c["title"]))
                else:
                    cells.append('<td class="ln"></td>')
            touched = ", ".join(domains[t]["name"] for t in tops if t in cols)
            rows.append('<tr title="%s touches: %s"><th scope="row">%s%s</th>%s</tr>'
                        % (esc(c["title"]), esc(touched), esc(c["title"]), st_tag(c),
                           "".join(cells)))
        if not rows:
            return ""
        head = "".join('<th scope="col">%s</th>' % esc(domains[t]["name"]) for t in tops)
        return ('<section class="lanes"><h2 class="chh">Cross-cutting charters</h2>'
                '<p class="lanenote">O owner &middot; L linked</p>'
                '<div class="lanewrap"><table class="lanetab">'
                '<thead><tr><th scope="col"></th>%s</tr></thead><tbody>%s</tbody></table>'
                '</div></section>' % (head, "".join(rows)))

    def org_diagram(page_ref, ref):
        """Diagram at ANY cascading level. Child boxes are clickable: they
        anchor to the child's block on THIS page, or open its page when the
        child has its own subtree beyond the window."""
        ch = vis_kids(ref)
        if not ch:
            return ""
        boxes = "".join('<a class="tnode" href="#%s">%s</a>'
                        % (anchor_of[c], esc(domains[c]["name"])) for c in ch)
        return ('<div class="tree"><div class="tnode troot">%s</div>'
                '<div class="tdown"></div><div class="tkids">%s</div></div>'
                % (esc(domains[ref]["name"]), boxes))

    def dpath_idx(idx):
        return "D" + ".".join(str(x) for x in idx), "d" + "-".join(str(x) for x in idx)

    def crumb(ref):
        chain, cur, seen = [], ref, set()
        while cur and cur in domains and cur not in seen:
            seen.add(cur); chain.append(cur); cur = domains[cur].get("parent_ref")
        chain.reverse()
        return " &rsaquo; ".join(
            ('<a href="%s">%s</a>' % (fname(c), esc(domains[c]["name"])))
            if c != ref else "<b>%s</b>" % esc(domains[c]["name"])
            for c in chain)

    def page_for(page_ref):
        pd = domains[page_ref]
        tops = vis_kids(page_ref)

        # per-page anchor table for this page's window
        anchor_of.clear()
        def assign(ref, idx, depth):
            anchor_of[ref] = dpath_idx(idx)[1]
            if depth < window:
                for j, c in enumerate(vis_kids(ref), 1):
                    assign(c, idx + [j], depth + 1)
                return
            for c in vis_kids(ref):              # beyond window: anchor at parent
                anchor_of[c] = dpath_idx(idx)[1]
        for i, t in enumerate(tops, 1):
            assign(t, [i], 1)

        # Minimal nav (codex fold): grandchild groups collapsed by default,
        # auto-expanded only when the whole page has few of them.
        n_grandkids = sum(len(vis_kids(c)) for c in tops)
        nav_open = " open" if n_grandkids <= 6 else ""

        def nav_entry(ref, idx, depth):
            d = domains[ref]
            ch = vis_kids(ref)
            label_i, anchor = dpath_idx(idx)
            if ch and depth < window:
                inner = "".join(nav_entry(c, idx + [j], depth + 1)
                                for j, c in enumerate(ch, 1))
                return ('<details class="navgrp"%s><summary><span class="chip">%s</span>'
                        '<a href="#%s">%s</a><span class="navcount">%d</span></summary>'
                        '<div class="navkids">%s</div></details>'
                        % (nav_open, label_i, anchor, esc(d["name"]),
                           len(ch), inner))
            if ch:                               # window edge: nav jumps to its page
                return ('<a class="sub" href="%s"><span class="chip">%s</span>%s '
                        '<span class="navcount">%d</span></a>'
                        % (fname(ref), label_i, esc(d["name"]), len(ch)))
            return ('<a class="sub" href="#%s"><span class="chip">%s</span>%s</a>'
                    % (anchor, label_i, esc(d["name"])))

        def node_block(ref, idx, depth):
            d = domains[ref]
            ch = vis_kids(ref)
            label_i, anchor = dpath_idx(idx)
            if depth >= window:
                # L3 summary card: whole card clickable (codex fold); no
                # charters, no cascade — details live on the child's page.
                # "open > N inside" only when N > 0 (codex fold).
                # Summary text is MINIMAL: file enumerations and long tails
                # stay on the domain's own page (founder: details on click).
                brief = (d.get("description", "") or "").split(" Files (")[0]
                if len(brief) > 160:
                    brief = brief[:157].rstrip() + "..."
                more = ('<span class="more">open &rsaquo; %d inside</span>'
                        % len(ch)) if ch else ""
                return ('<a class="info summary" id="%s" href="%s">'
                        '<span class="chip">%s</span><b>%s</b><p>%s</p>%s%s</a>'
                        % (anchor, fname(ref), label_i, esc(d["name"]),
                           esc(brief), withheld_note(ref), more))
            name_html = '<a class="dlink" href="%s">%s</a>' % (fname(ref), esc(d["name"]))
            body = ('<span class="chip">%s</span><b>%s</b><p>%s</p>%s%s'
                    % (label_i, name_html, esc(d.get("description", "")),
                       charter_line(ref), withheld_note(ref)))
            if ch:
                inner = "".join(node_block(c, idx + [j], depth + 1)
                                for j, c in enumerate(ch, 1))
                body += ('<details class="cascade" open><summary>%d sub-domains</summary>'
                         '%s<div class="grid">%s</div></details>'
                         % (len(ch), org_diagram(page_ref, ref), inner))
            return '<div class="info" id="%s">%s</div>' % (anchor, body)

        rail, sections = [], []
        for i, t in enumerate(tops, 1):
            d = domains[t]
            ch = vis_kids(t)
            label_i, anchor = dpath_idx([i])
            rail.append(nav_entry(t, [i], 1))
            if ch:
                blocks = "".join(node_block(c, [i, j], 2) for j, c in enumerate(ch, 1))
            elif d.get("public_names_withheld") and kids.get(t):
                blocks = ('<div class="info withheld">%d entries — names withheld '
                          'on the public page</div>' % len(kids.get(t, [])))
            else:
                blocks = '<div class="info empty">no sub-%s yet</div>' % label.lower()
            sections.append(
                '<section id="%s" class="dept"><header><span class="chip big">%s</span>'
                '<div><h2><a class="dlink" href="%s">%s</a></h2><p class="desc">%s</p>%s</div>'
                '<span class="count">%d</span></header>%s<div class="grid">%s</div></section>'
                % (anchor, label_i, fname(t), esc(d["name"]), esc(d.get("description", "")),
                   charter_line(t), len(ch), org_diagram(page_ref, t), blocks))

        rootdiag = org_diagram(page_ref, page_ref)
        up = pd.get("parent_ref")
        uplink = ('<a class="sub up" href="%s">&lsaquo; up to %s</a>'
                  % (fname(up), esc(domains[up]["name"]))) if up else ""
        body_main = (('%(sections)s' % dict(sections="".join(sections)))
                     if tops else '<div class="info empty">leaf domain — no children</div>')
        return SITE_TMPL % dict(
            title="%s · %s" % (esc(pd["name"]), label), crumb=crumb(page_ref),
            uplink=uplink, rail="".join(rail), root=esc(pd["name"]),
            rootdesc=esc(pd.get("description", "")),
            rootchs=charters_section(page_ref) + withheld_note(page_ref),
            lanes=lane_chart(page_ref, tops),
            rootdiag=rootdiag, sections=body_main, n=len(kids.get(page_ref, [])),
            layers=window + 1, label_l=label.lower(), src=esc(T.get("source", "")),
            **{k: T[k] for k in ("bg", "card", "ink", "muted", "line",
                                 "accent", "accent_bg", "font")})

    anchor_of = {}
    made = 0
    for ref in domains:
        if ref in hidden:                        # no page for withheld names
            continue
        open(os.path.join(out_dir, fname(ref)), "w").write(page_for(ref))
        made += 1
    return made


# Zoom-page template: SAME two-column anatomy as the flat page (left index +
# search + diagrams at every level + dotted blocks) plus crumb/up-link.
SITE_TMPL = """<!doctype html>
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
nav a.up{color:var(--acc);font-size:.85rem}
.crumb{font-size:.85rem;color:var(--mut);margin-bottom:14px}
.crumb a{color:var(--acc);text-decoration:none}
.chip{font:600 .72rem/1 ui-monospace,Menlo,monospace;color:var(--ink);background:var(--accbg);border:1px solid var(--acc);border-radius:6px;padding:3px 7px;flex:none}
.chip.big{font-size:.85rem;padding:6px 10px}
h1{font-size:1.65rem;letter-spacing:-.01em}
.rootdesc{color:var(--mut);margin:6px 0 10px;max-width:60ch}
.dept{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:22px;scroll-margin-top:20px}
.dept:target{border-color:var(--acc)}
.dept header{display:flex;gap:14px;align-items:flex-start;margin-bottom:14px}
.dept h2{font-size:1.12rem}
.desc{color:var(--mut);font-size:.92rem;margin-top:2px;max-width:58ch}
.charter{font-size:.8rem;color:var(--mut);margin-top:6px;max-width:58ch}
.charter span{font:600 .68rem/1 ui-monospace,monospace;color:var(--acc);border:1px dotted var(--acc);border-radius:5px;padding:2px 6px;margin-right:6px}
.count{margin-left:auto;font:600 .75rem/1 ui-monospace,monospace;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:4px 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.info{border:1.5px dashed var(--line);border-radius:10px;padding:12px 14px;scroll-margin-top:20px}
.info:target{border-color:var(--acc)}
.info b{display:inline-block;margin-left:8px;font-size:.95rem}
.info p{color:var(--mut);font-size:.85rem;margin-top:6px}
.info.empty,.info.withheld,p.withheld{color:var(--mut);font-style:italic}
p.withheld{font-size:.85rem;margin-top:6px}
.chsec{margin:16px 0 4px}
.chh{font-size:1.02rem;margin-bottom:4px}
.chg{font:600 .7rem/1 ui-monospace,monospace;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;margin:10px 0 6px}
.chempty{color:var(--mut);font-style:italic;font-size:.85rem}
.st{font:600 .62rem/1 ui-monospace,monospace;border-radius:4px;padding:2px 5px;margin-left:6px;border:1px solid var(--line);color:var(--mut)}
.st-active{border-color:var(--acc);color:var(--acc)}
.st-retired{opacity:.65}
.chips{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start}
.chdot{display:inline-flex;align-items:center;gap:5px;font:600 .64rem/1 ui-monospace,monospace;color:var(--mut);margin-right:8px}
.chdot i{width:7px;height:7px;border-radius:50%%;background:var(--line);display:inline-block}
.chdot.st-active i{background:var(--acc)}
.chdot.st-shipped i{background:var(--mut)}
.chdot.st-retired i,.chdot.st-paused i{background:transparent;border:1.5px solid var(--mut)}
.chcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-height:36px;flex:1 1 260px;max-width:420px}
.chcard b{font-size:.88rem}
.chline{color:var(--mut);font-size:.8rem;margin-top:4px;max-width:52ch}
.chd{position:relative}
.chd summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:8px 14px;min-height:36px;font-size:.84rem}
.chd summary::-webkit-details-marker{display:none}
.chd summary:hover{border-color:var(--acc);background:var(--accbg)}
.chd summary:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.chd[open] summary{border-color:var(--acc);border-radius:10px 10px 0 0}
.chd b{font-weight:600}
.chpanel{border:1px solid var(--acc);border-top:none;border-radius:0 0 10px 10px;background:var(--card);padding:10px 14px;font-size:.8rem;max-width:420px}
.chpanel p{color:var(--mut);margin-bottom:4px}
.chpath{display:block;font:400 .7rem/1.5 ui-monospace,monospace;color:var(--mut);overflow-wrap:anywhere}
a.chlinkchip{display:inline-flex;align-items:center;background:var(--card);border:1px dashed var(--line);border-radius:999px;padding:8px 14px;min-height:36px;font-size:.84rem;color:inherit;text-decoration:none}
a.chlinkchip:hover{border-color:var(--acc);background:var(--accbg)}
.chowner{font-size:.7rem;color:var(--mut);margin-left:8px}
.chrow{margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.chlabel{font:600 .66rem/1 ui-monospace,monospace;color:var(--acc);border:1px dotted var(--acc);border-radius:5px;padding:2px 6px}
.chmini{font-size:.74rem;color:var(--mut);background:var(--card);border:1px solid var(--line);border-radius:999px;padding:3px 9px;cursor:default}
a.chmini{color:var(--acc);text-decoration:none;cursor:pointer}
.chlinks{display:block;font-size:.75rem;color:var(--mut);margin-top:2px}
.chlinks a{color:var(--acc);text-decoration:none}
.chart-n{font:600 .64rem/1 ui-monospace,monospace;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:2px 6px;margin-left:8px}
.lanes{margin:12px 0 8px}
.lanenote{font-size:.75rem;color:var(--mut);margin-bottom:8px}
.lanewrap{overflow-x:auto}
.lanetab{border-collapse:collapse;width:100%%;font-size:.8rem}
.lanetab thead th{text-align:center;color:var(--mut);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--line)}
.lanetab tbody th{text-align:left;font-weight:500;color:var(--ink);white-space:nowrap;padding:6px 8px;border-bottom:1px dotted var(--line)}
.lanetab td{text-align:center;padding:6px 4px;border-bottom:1px dotted var(--line);min-width:44px}
.lanetab td.lo{background:var(--acc);color:var(--card);font-weight:700;border-radius:4px}
.lanetab td.ll{background:var(--accbg);color:var(--acc);font-weight:600;border-radius:4px}
a.info.summary{display:block;color:inherit;text-decoration:none}
a.info.summary:hover{border-color:var(--acc);background:var(--accbg)}
.summary .more{display:inline-block;font-size:.78rem;color:var(--acc);margin-top:6px}
a.dlink{color:inherit;text-decoration:none}
a.dlink:hover{color:var(--acc)}
.cascade{margin-top:10px;border-top:1px dotted var(--line);padding-top:8px}
.cascade summary{cursor:pointer;font-size:.78rem;color:var(--acc);list-style:none}
.cascade summary::before{content:"\25B8 ";font-size:.7rem}
.cascade[open] summary::before{content:"\25BE "}
.cascade .grid{margin-top:10px;grid-template-columns:1fr}
.more a{font-size:.8rem;color:var(--acc);text-decoration:none}
.more{margin-top:8px}
.navgrp summary a{color:var(--ink);text-decoration:none;flex:1}
.navgrp summary a:hover{color:var(--acc)}
.navcount{font:600 .68rem/1 ui-monospace,monospace;color:var(--mut);border:1px solid var(--line);border-radius:999px;padding:1px 7px}
.navgrp summary{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:8px;cursor:pointer;list-style:none}
.navgrp summary::before{content:"\25B8";font-size:.7rem;color:var(--mut)}
.navgrp[open] summary::before{content:"\25BE"}
.navgrp summary:hover{background:var(--accbg)}
.navkids{margin:2px 0 6px 14px;border-left:2px solid var(--line);padding-left:8px}
.navkids a.sub{font-size:.85rem;padding:5px 6px}
.navkids .navgrp summary{padding:5px 6px;font-size:.88rem}
footer{color:var(--mut);font-size:.8rem;margin-top:8px}
.tree{margin:6px 0 18px;text-align:center}
.tnode{display:inline-block;background:var(--card);border:1.5px solid var(--acc);border-radius:8px;padding:6px 14px;font-size:.85rem;font-weight:600;color:var(--ink);text-decoration:none}
a.tnode:hover{background:var(--accbg)}
.tnode.troot{background:var(--accbg)}
.tdown{width:2px;height:14px;background:var(--line);margin:0 auto}
.tkids{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;position:relative;padding-top:14px}
.tkids::before{content:"";position:absolute;top:0;left:12%%;right:12%%;height:2px;background:var(--line)}
.tkids .tnode{position:relative;border-width:1px;border-color:var(--line);font-weight:500}
.tkids .tnode::before{content:"";position:absolute;top:-14px;left:50%%;width:2px;height:14px;background:var(--line)}
#q{width:100%%;margin-bottom:10px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;font-size:.9rem}
#q:focus{outline:2px solid var(--acc)}
.hidden{display:none !important}
@media(max-width:760px){.layout{grid-template-columns:1fr}nav{position:static;display:flex;flex-wrap:wrap;gap:4px}
.chips.dense .chd,.chips.dense .chd summary,a.chlinkchip{width:100%%}
.chd summary{min-height:44px}a.chlinkchip{min-height:44px}
.chcard{max-width:none;flex-basis:100%%}.chpanel{max-width:none}}
</style></head><body><div class="layout">
<nav><input id="q" type="search" placeholder="Search domains..." autocomplete="off">%(uplink)s%(rail)s</nav>
<main>
<p class="crumb">%(crumb)s</p>
<h1>%(root)s</h1>
<p class="rootdesc">%(rootdesc)s</p>
%(rootchs)s
%(rootdiag)s
%(lanes)s
%(sections)s
<footer>%(n)d children &middot; %(layers)d levels per page &middot; %(src)s</footer>
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
 n.classList.toggle('hidden',!hit);});
document.querySelectorAll('.chsec .chd, .chsec .chcard, .chsec a.chlinkchip').forEach(function(ch){
 var s=ch.querySelector('summary[title]');
 var txt=(ch.textContent+' '+((s?s.getAttribute('title'):ch.getAttribute('title'))||'')).toLowerCase();
 ch.classList.toggle('hidden',!(!v||txt.indexOf(v)>=0));});
document.querySelectorAll('.chsec .chips').forEach(function(g){
 var any=g.querySelector('.chd:not(.hidden),.chcard:not(.hidden),a.chlinkchip:not(.hidden)');
 g.classList.toggle('hidden',!any);
 var h=g.previousElementSibling;
 if(h&&h.classList.contains('chg'))h.classList.toggle('hidden',!any);});});})();
</script>
</div></body></html>
"""


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    label = "Departments" if "--label" not in " ".join(sys.argv) else \
        sys.argv[sys.argv.index("--label") + 1]
    if "--site" in sys.argv:
        out = args[0] if args else "domains"
        n = build_site(out, label=label)
        print("site: %d zoom pages in %s/" % (n, out))
    else:
        out = args[0] if args else "domains.html"
        p, n = build(out, label=label)
        print("wrote %s (%d domains)" % (p, n))
