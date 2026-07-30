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

    def cname(cid):
        """Charter page filename — content-addressed id, stable forever."""
        return cid + ".html"

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

    def charter_table(page_ref, tops):
        """ONE structured surface (founder 2026-07-30): own + linked +
        cross-cutting charters in the same table. Canonical row per charter
        (codex P1): relationship precedence own > linked > cross; child O/L
        cells aggregated regardless of which relation admitted the row.
        Charter names click through to their structured page."""
        tset = set(tops)

        def cols_for(c):
            cols = {}
            for r in set([c.get("domain_ref")] + c["linked_domain_refs"]):
                if r == page_ref or r not in domains:
                    continue
                col = child_of(page_ref, r)
                if col not in tset:
                    continue
                role = "O" if r == c.get("domain_ref") else "L"
                if cols.get(col) != "O":
                    cols[col] = role
            return cols

        RELS = [("own", "Own"), ("linked", "Linked"), ("cross", "Cross-cutting below")]
        picked = []
        for c in all_ch:
            owner = c.get("domain_ref")
            if owner in hidden or owner not in domains:
                continue
            cols = cols_for(c)
            if owner == page_ref:
                rel = "own"
            elif page_ref in c["linked_domain_refs"]:
                rel = "linked"
            elif len(cols) >= 2:
                rel = "cross"
            else:
                continue
            picked.append((c, rel, cols))
        if not picked:
            return ('<section class="chsec"><h2 class="chh">Charters</h2>'
                    '<p class="chempty">none yet</p></section>')

        show_cols = bool(tops) and any(cols for _, _, cols in picked)
        ncols = 4 + (len(tops) if show_cols else 0)
        relrank = {"own": 0, "linked": 1, "cross": 2}
        picked.sort(key=lambda t: (relrank[t[1]],
                                   0 if t[0]["kind"] == "standing" else 1,
                                   t[0]["title"].lower()))
        body = []
        cur_rel = None
        for c, rel, cols in picked:
            if rel != cur_rel:
                cur_rel = rel
                label_r = dict(RELS)[rel]
                body.append('<tr class="grp"><td colspan="%d">%s</td></tr>'
                            % (ncols, label_r))
            owner = c.get("domain_ref")
            own_cell = ('<span class="cown-here">here</span>' if owner == page_ref
                        else '<a href="%s">%s</a>' % (fname(owner), esc(domains[owner]["name"])))
            cells = ""
            if show_cols:
                for t in tops:
                    m = cols.get(t)
                    if m == "O":
                        cells += ('<td class="lo" title="owner: %s">O</td>'
                                  % esc(domains[t]["name"]))
                    elif m == "L":
                        cells += ('<td class="ll" title="linked: %s">L</td>'
                                  % esc(domains[t]["name"]))
                    else:
                        cells += '<td class="ln"></td>'
            body.append(
                '<tr class="chtr" data-status="%s"><th scope="row">'
                '<a href="%s" title="%s">%s</a></th>'
                '<td class="ckind">%s</td><td>%s</td><td class="cown">%s</td>%s</tr>'
                % (c["status"], cname(c["id"]), esc(c.get("purpose", "")),
                   esc(c["title"]), c["kind"], st_dot(c), own_cell, cells))
        childh = "".join('<th scope="col">%s</th>' % esc(domains[t]["name"])
                         for t in tops) if show_cols else ""
        statuses = sorted({c["status"] for c, _, _ in picked})
        fil = ""
        if len(picked) > 4 and len(statuses) > 1:
            btns = '<button data-st="all" aria-pressed="true">all</button>' + "".join(
                '<button data-st="%s" aria-pressed="false">%s</button>' % (s, s)
                for s in statuses)
            fil = '<div class="chfil">%s</div>' % btns
        legend = ('<p class="lanenote">O owner &middot; L linked</p>' if show_cols else "")
        return ('<section class="chsec"><h2 class="chh">Charters</h2>%s%s'
                '<div class="lanewrap"><table class="lanetab chtab">'
                '<thead><tr><th scope="col">Charter</th><th scope="col">Kind</th>'
                '<th scope="col">Status</th><th scope="col">Owner</th>%s</tr></thead>'
                '<tbody>%s<tr class="chnone hidden"><td colspan="%d">no charters match</td></tr>'
                '</tbody></table></div></section>'
                % (legend, fil, childh, "".join(body), ncols))

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

    def charter_page(c):
        """Structured per-charter page (founder 2026-07-30): every field a
        labelled row, nothing prose-shaped. Codex fold: explicit owner
        up-link beside the breadcrumb."""
        owner = c.get("domain_ref")
        oname = esc(domains[owner]["name"])
        rows = [("Purpose", esc(c.get("purpose", ""))),
                ("Kind", c["kind"]),
                ("Status", st_dot(c)),
                ("Owner", '<a href="%s">%s</a>' % (fname(owner), oname))]
        links = [r for r in c["linked_domain_refs"] if r in domains and r not in hidden]
        if links:
            rows.append(("Linked", ", ".join(
                '<a href="%s">%s</a>' % (fname(r), esc(domains[r]["name"])) for r in links)))
        if c["artifacts"]:
            rows.append(("Artifacts", "".join(
                '<code class="chpath">%s</code>' % esc(a) for a in c["artifacts"])))
        for fld, lab in (("scope_in", "Scope in"), ("obligations", "Obligations")):
            vals = c.get(fld) or []
            if vals:
                rows.append((lab, "".join('<code class="chpath">%s</code>' % esc(str(v))
                                          for v in vals)))
        dl = "".join('<div class="chdlrow"><dt>%s</dt><dd>%s</dd></div>' % (k, v)
                     for k, v in rows)
        return CH_TMPL % dict(
            title=esc(c["title"]) + " · Charter",
            crumb=crumb(owner) + " &rsaquo; <b>%s</b>" % esc(c["title"]),
            uplink='<a class="sub up" href="%s">&lsaquo; %s</a>' % (fname(owner), oname),
            name=esc(c["title"]), cid=c["id"], dl=dl,
            **{k: T[k] for k in ("bg", "card", "ink", "muted", "line",
                                 "accent", "accent_bg", "font")})

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
            rootchs=charter_table(page_ref, tops) + withheld_note(page_ref),
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
    for c in all_ch:                             # one structured page per charter
        if c.get("domain_ref") in hidden or c.get("domain_ref") not in domains:
            continue
        open(os.path.join(out_dir, cname(c["id"])), "w").write(charter_page(c))
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
.chdot{display:inline-flex;align-items:center;gap:5px;font:600 .64rem/1 ui-monospace,monospace;color:var(--mut)}
.chdot i{width:7px;height:7px;border-radius:50%%;background:var(--line);display:inline-block}
.chdot.st-active i{background:var(--acc)}
.chdot.st-shipped i{background:var(--mut)}
.chdot.st-retired i,.chdot.st-paused i{background:transparent;border:1.5px solid var(--mut)}
.chfil{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.chfil button{font:600 .7rem/1 ui-monospace,monospace;color:var(--mut);background:var(--card);border:1px solid var(--line);border-radius:999px;padding:6px 12px;min-height:30px;cursor:pointer}
.chfil button:hover{border-color:var(--acc)}
.chfil button[aria-pressed="true"]{background:var(--accbg);border-color:var(--acc);color:var(--acc)}
.chfil button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.chtab thead th{text-align:left}
.chtab tbody th a{color:inherit;text-decoration:none;border-bottom:1px dotted var(--acc)}
.chtab tbody th a:hover{color:var(--acc)}
.chtab tr.grp td{font:600 .66rem/1 ui-monospace,monospace;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;padding:10px 8px 4px;border-bottom:none;text-align:left}
.chtab td.ckind{font:400 .74rem/1 ui-monospace,monospace;color:var(--mut);text-align:left}
.chtab td.cown{text-align:left;font-size:.78rem}
.chtab td.cown a{color:var(--acc);text-decoration:none}
.cown-here{font:600 .68rem/1 ui-monospace,monospace;color:var(--mut)}
.chtab tr.chnone td{color:var(--mut);font-style:italic;text-align:left}
.chpath{display:block;font:400 .7rem/1.5 ui-monospace,monospace;color:var(--mut);overflow-wrap:anywhere}
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
.chtab tbody th{white-space:nowrap}.chtab tr.chtr{height:44px}
.chfil button{min-height:40px}}
</style></head><body><div class="layout">
<nav><input id="q" type="search" placeholder="Search domains..." autocomplete="off">%(uplink)s%(rail)s</nav>
<main>
<p class="crumb">%(crumb)s</p>
<h1>%(root)s</h1>
<p class="rootdesc">%(rootdesc)s</p>
%(rootchs)s
%(rootdiag)s
%(sections)s
<footer>%(n)d children &middot; %(layers)d levels per page &middot; %(src)s</footer>
</main>
<script>
(function(){var q=document.getElementById('q');var FIL='all';
function chApply(){var v=q?q.value.trim().toLowerCase():'';
 document.querySelectorAll('tr.chtr').forEach(function(r){
  var okS=(FIL==='all')||r.getAttribute('data-status')===FIL;
  var a=r.querySelector('a[title]');
  var t=(r.textContent+' '+(a?a.getAttribute('title'):'')).toLowerCase();
  r.classList.toggle('hidden',!(okS&&(!v||t.indexOf(v)>=0)));});
 document.querySelectorAll('tr.grp').forEach(function(g){
  var n=g.nextElementSibling,any=false;
  while(n&&!n.classList.contains('grp')){
   if(n.classList.contains('chtr')&&!n.classList.contains('hidden'))any=true;
   n=n.nextElementSibling;}
  g.classList.toggle('hidden',!any);});
 var anyrow=document.querySelector('tr.chtr:not(.hidden)');
 document.querySelectorAll('tr.chnone').forEach(function(e){
  e.classList.toggle('hidden',!!anyrow);});}
document.querySelectorAll('.chfil button').forEach(function(b){
 b.addEventListener('click',function(){FIL=b.getAttribute('data-st');
  document.querySelectorAll('.chfil button').forEach(function(x){
   x.setAttribute('aria-pressed',x===b?'true':'false');});chApply();});});
if(q)q.addEventListener('input',function(){var v=q.value.trim().toLowerCase();
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
chApply();});})();
</script>
</div></body></html>
"""


CH_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<style>
:root{--bg:%(bg)s;--card:%(card)s;--ink:%(ink)s;--mut:%(muted)s;--line:%(line)s;--acc:%(accent)s;--accbg:%(accent_bg)s}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.55 %(font)s}
.wrap{max-width:760px;margin:0 auto;padding:36px 20px}
.crumb{font-size:.85rem;color:var(--mut);margin-bottom:8px}
.crumb a{color:var(--acc);text-decoration:none}
a.up{display:inline-block;color:var(--acc);text-decoration:none;font-size:.85rem;margin-bottom:16px}
h1{font-size:1.4rem;letter-spacing:-.01em;margin-bottom:4px}
.cid{font:400 .72rem/1 ui-monospace,monospace;color:var(--mut);margin-bottom:18px}
.chdl{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 0}
.chdlrow{display:grid;grid-template-columns:120px 1fr;gap:12px;padding:10px 16px;border-bottom:1px dotted var(--line)}
.chdlrow:last-child{border-bottom:none}
dt{font:600 .7rem/1.8 ui-monospace,monospace;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
dd{font-size:.9rem}
dd a{color:var(--acc);text-decoration:none}
.chdot{display:inline-flex;align-items:center;gap:5px;font:600 .68rem/1 ui-monospace,monospace;color:var(--mut)}
.chdot i{width:7px;height:7px;border-radius:50%%;background:var(--line);display:inline-block}
.chdot.st-active i{background:var(--acc)}
.chdot.st-shipped i{background:var(--mut)}
.chdot.st-retired i,.chdot.st-paused i{background:transparent;border:1.5px solid var(--mut)}
.chpath{display:block;font:400 .74rem/1.7 ui-monospace,monospace;color:var(--mut);overflow-wrap:anywhere}
@media(max-width:560px){.chdlrow{grid-template-columns:1fr;gap:2px}}
</style></head><body><div class="wrap">
<p class="crumb">%(crumb)s</p>
%(uplink)s
<h1>%(name)s</h1>
<p class="cid">%(cid)s</p>
<dl class="chdl">%(dl)s</dl>
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
