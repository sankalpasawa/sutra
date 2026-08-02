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
import sys, os, html, json, subprocess, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import placement_engine as E  # noqa: E402

NEUTRAL = {"bg": "#fafaf9", "card": "#ffffff", "ink": "#1c1917", "muted": "#78716c",
           "line": "#e7e5e4", "accent": "#1d4ed8", "accent_bg": "#eff4ff",
           "font": "-apple-system,'Segoe UI',Roboto,sans-serif", "source": "neutral fallback"}


def _tenant(tenant_id):
    """§6: there is no unfiltered publish path. A publish surface with a
    defaultable tenant is the performed barrier the design forbids — one
    forgotten call site republishes a second tenant onto a public Pages repo —
    so the default is the ACTIVE tenant, never None."""
    return tenant_id or os.environ.get("PLACEMENT_TENANT", "T-local")


def _render_set(tenant_id):
    """-> (all_domains, live, kids, root, all_kids) for ONE tenant.

    TENANT surface (§6): filter the INPUT SET, not the output. Second-tenant
    domains must be absent from the build, not suppressed inside it.

    RENDER surface (§2.1): `live_refs()` belongs at the five render surfaces,
    and "the index-rail builder in domains_page.py" is one of them — the only
    one that auto-commits to a PUBLIC GitHub Pages repo. Before I-D5 the merge
    and delete paths called `os.remove()` on `domains/<ref>.json`, so a merged
    department fell out of `load_domains()` and off the site implicitly; the row
    now stays with `status='retired'`, and without this filter it keeps its own
    dref-<id>.html page, its left-nav entry, its org-diagram node and its crumb.
    §2.1's state table says retired = "in live tree: no (Archive tray)".

    The FULL tenant map comes back alongside it for two reasons: the registry
    export's `domain_ref not in domains` membership check must keep seeing
    tombstones (§2.1's read-path table — otherwise every charter homed to a
    retired domain vanishes from registry.json, killing §3.2.4's Archive tray),
    and a LIVE child whose parent was retired would otherwise fall out of `kids`
    and take its whole subtree off the site with no error. Those re-attach to
    the nearest live ancestor.
    """
    all_domains = E.tenant_refs(E.load_domains(), tenant_id)
    if not all_domains:
        raise SystemExit("registry empty for tenant %s — run a scan or seed the "
                         "org tree first" % tenant_id)
    live = E.live_refs(all_domains)
    roots = sorted(r for r, d in live.items() if d.get("parent_ref") is None)
    if not roots:
        raise SystemExit("tenant %s has no live root domain" % tenant_id)
    if len(roots) > 1:
        # LOUD, not last-wins: the old `for r, d in domains.items(): if p is
        # None: root = r` made index.html nondeterministic across runs, and only
        # the winner's subtree was walked — the other root and everything under
        # it vanished from the published site silently.
        raise SystemExit("tenant %s has %d parent-less live domains (%s) — a "
                         "publish must not guess which one is the root; merge "
                         "or retire the extras first"
                         % (tenant_id, len(roots), ", ".join(roots)))
    root = roots[0]
    all_kids, kids = {}, {}
    for r, d in all_domains.items():
        all_kids.setdefault(d.get("parent_ref"), []).append(r)
    for r, d in live.items():
        p = d.get("parent_ref")
        if p is not None and p not in live:
            p = E._nearest_live_ancestor(p, all_domains) or root
        kids.setdefault(p, []).append(r)
    for v in kids.values():
        v.sort(key=lambda r: live[r].get("ts_minted_ms", 0))
    return all_domains, live, kids, root, all_kids


def build(out_path, label="Domains", title=None, tenant_id=None):
    tenant_id = _tenant(tenant_id)
    _all, domains, kids, root, _all_kids = _render_set(tenant_id)
    rootd = domains[root]
    T = dict(NEUTRAL)
    T.update(rootd.get("design") or {})

    def esc(s): return html.escape(s or "")

    def charter_line(ref):
        # a domain hosts MANY charters — render every one (founder 2026-07-30)
        chs = sorted(E.charters_for(ref, tenant_id), key=lambda x: x["id"])
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


def build_site(out_dir, label="Domains", window=2, tenant_id=None):
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
    index.html = the root domain.

    TENANT (§6): `tenant_id` filters the build's INPUT SET. A second tenant must
    be ABSENT from the input, not filtered out of the output — every downstream
    guard here (`domain_ref not in domains`) then excludes its charters,
    its pages and its registry.json rows for free, with no per-surface filter to
    forget. The CLI requires `--tenant`; the default is the active tenant, never
    unfiltered.

    RENDER (§2.1): `domains` is the LIVE set — a retired department gets no
    page, no nav entry and no org-diagram node. `all_domains` keeps the
    tombstones for the registry export's membership check only (see
    `_render_set`)."""
    tenant_id = _tenant(tenant_id)
    all_domains, domains, kids, root, all_kids = _render_set(tenant_id)
    os.makedirs(out_dir, exist_ok=True)
    T = dict(NEUTRAL)
    T.update(domains[root].get("design") or {})

    # Privacy parity with the flat renderer (codex fold 2026-07-30): a
    # `public_names_withheld` domain hides its children's names, and no page
    # is generated for any hidden descendant — a ref-named page would leak
    # the very names the flag withholds. Walked over the FULL map: a retired
    # descendant is still withheld in the registry export.
    hidden = set()
    def _hide(ref):
        for c in all_kids.get(ref, []):
            hidden.add(c); _hide(c)
    for r, d in all_domains.items():
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
    # §2.2: the hashed body is joined with its mutable sidecar HERE, at render.
    # The sidecar wins its own keys; the body is never written back — that
    # rewrite is what broke content addressing (§0.12/§0.13). C-<id>.html
    # naming is unchanged: the id still comes from the body.
    all_ch = []
    for fn in E.charter_body_files():
        try:
            body = json.load(open(os.path.join(E.CHARTERS, fn)))
        except (ValueError, OSError):
            continue
        if not isinstance(body, dict):
            continue
        body.setdefault("id", fn[:-len(".json")])
        c = E.charter_view(body)
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

    # ---- GitHub links for artifacts (founder 2026-07-31) -------------------
    # Resolved from the repo's ACTUAL remotes at build time — fleet-generic,
    # submodule-aware, zero hardcoded URLs. Absolute/machine-local paths stay
    # plain text (they have no web home).
    def _remote_web(repo_dir):
        try:
            url = subprocess.check_output(
                ["git", "-C", repo_dir, "remote", "get-url", "origin"],
                text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return None
        if url.endswith(".git"):
            url = url[:-4]
        if url.startswith("git@"):
            url = "https://" + url[4:].replace(":", "/", 1)
        return url if url.startswith("https://") else None

    def _repo_branch(repo_dir):
        try:
            b = subprocess.check_output(
                ["git", "-C", repo_dir, "rev-parse", "--abbrev-ref", "HEAD"],
                text=True, stderr=subprocess.DEVNULL).strip()
            return b if b and b != "HEAD" else "main"
        except Exception:
            return "main"

    _work_root = None
    try:
        _work_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        pass
    _art_repos = []                              # (prefix, web, branch) longest-first
    if _work_root:
        try:
            for line in subprocess.check_output(
                    ["git", "-C", _work_root, "submodule", "status"],
                    text=True, stderr=subprocess.DEVNULL).splitlines():
                sub = line.split()[1] if len(line.split()) > 1 else ""
                if not sub:
                    continue
                w = _remote_web(os.path.join(_work_root, sub))
                if w:
                    _art_repos.append((sub + "/", w, _repo_branch(os.path.join(_work_root, sub))))
        except Exception:
            pass
        w = _remote_web(_work_root)
        if w:
            _art_repos.append(("", w, _repo_branch(_work_root)))
        _art_repos.sort(key=lambda t: -len(t[0]))

    # Verify-then-link (founder + codex 2026-07-31): an artifact links ONLY
    # when it resolves to a git-TRACKED file/dir — never a 404. Absolute
    # paths under the work root normalize to repo-relative; bare filenames
    # resolve by UNIQUE suffix (and show the matched path); directories link
    # to tree/. Every linked file carries a one-line content-derived summary
    # — templatized, zero hardcoding.
    _tracked = set()
    if _work_root:
        def _ls(repo_dir, prefix=""):
            try:
                for ln in subprocess.check_output(
                        ["git", "-C", repo_dir, "ls-files"],
                        text=True, stderr=subprocess.DEVNULL).splitlines():
                    if ln:
                        _tracked.add(prefix + ln)
            except Exception:
                pass
        _ls(_work_root)
        for _p, _w, _b in _art_repos:
            if _p:
                _ls(os.path.join(_work_root, _p), _p)

    def _norm_art(p):
        p = (p or "").split("#")[0].strip().replace("\\", "/")
        while "//" in p:
            p = p.replace("//", "/")
        if p.startswith("./"):
            p = p[2:]
        if _work_root and os.path.isabs(p):
            wr = _work_root.rstrip("/") + "/"
            if p.startswith(wr):
                p = p[len(wr):]
            else:
                return None                      # machine-local, no web home
        return p.rstrip("/")

    def _resolve_art(p0):
        p = _norm_art(p0)
        if not p or os.path.isabs(p) or not _work_root:
            return None, None
        if p in _tracked:
            return p, "file"
        if os.path.isdir(os.path.join(_work_root, p)) and \
                any(t.startswith(p + "/") for t in _tracked):
            return p, "dir"
        cands = [t for t in _tracked if t.endswith("/" + p)]
        if len(cands) == 1:
            return cands[0], "file"
        return None, None

    def _gh_url(path, kind):
        for prefix, web, branch in _art_repos:
            if path.startswith(prefix) or prefix == "":
                rel = path[len(prefix):] if prefix else path
                enc = "/".join(urllib.parse.quote(seg) for seg in rel.split("/"))
                return "%s/%s/%s/%s" % (web, "tree" if kind == "dir" else "blob",
                                        urllib.parse.quote(branch), enc)
        return None

    _SUM_SKIP = ("#!", "# -*-", "# shellcheck", "# spdx", "# copyright",
                 "# license", "// eslint", "<!--")

    def _summary(path, kind):
        if kind == "dir":
            return "directory - %d tracked files" % sum(
                1 for t in _tracked if t.startswith(path + "/"))
        try:
            with open(os.path.join(_work_root, path), "r", errors="replace") as fh:
                head = fh.read(2048).splitlines()
        except Exception:
            return ""
        in_fm = False
        for i, ln in enumerate(head):
            s = ln.strip()
            if i == 0 and s == "---":
                in_fm = True
                continue
            if in_fm:
                in_fm = s != "---"
                continue
            if not s or set(s) <= set("#/-=* "):
                continue
            if any(s.lower().startswith(k) for k in _SUM_SKIP):
                continue
            for pre in ("#", "//", '"""', "'''"):
                if s.startswith(pre):
                    s = s[len(pre):].strip("#/\"' ").strip()
                    break
            if s:
                return s[:110]
        return ""

    def art_html(orig):
        path, kind = _resolve_art(orig)
        if not path:
            return ('<code class="chpath dead" title="not found in the '
                    'published repos">%s</code>' % esc(orig))
        url = _gh_url(path, kind)
        if not url:
            return '<code class="chpath">%s</code>' % esc(orig)
        summ = _summary(path, kind)
        label = esc(path)
        if _norm_art(orig) != path:              # suffix-resolved: show the match
            label = '%s <span class="chres">&rarr; %s</span>' % (esc(orig), esc(path))
        out = ('<a class="chpath" href="%s" target="_blank" rel="noopener" '
               'title="%s">%s</a>' % (esc(url), esc(summ or path), label))
        if summ:
            out += '<span class="chsum">%s</span>' % esc(summ)
        return out

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

        picked = []
        for c in all_ch:
            owner = c.get("domain_ref")
            if owner in hidden or owner not in domains:
                continue
            cols = cols_for(c)
            if owner == page_ref or page_ref in c["linked_domain_refs"] \
                    or len(cols) >= 2:
                picked.append((c, cols))
        if not picked:
            return ('<section class="chsec"><h2 class="chh">Charters</h2>'
                    '<p class="chempty">none yet</p></section>')

        show_cols = bool(tops) and any(cols for _, cols in picked)
        ncols = 4 + (len(tops) if show_cols else 0)
        # Owner grouping IS the structure (founder 2026-07-31): "here" block
        # first, then owners by name; standing before projects within a block.
        def _oname(c):
            return "" if c["domain_ref"] == page_ref else domains[c["domain_ref"]]["name"].lower()
        picked.sort(key=lambda t: (0 if t[0]["domain_ref"] == page_ref else 1,
                                   _oname(t[0]),
                                   0 if t[0]["kind"] == "standing" else 1,
                                   t[0]["title"].lower()))
        body = []
        prev_owner = object()
        for c, cols in picked:
            owner = c.get("domain_ref")
            first = owner != prev_owner
            prev_owner = owner
            if owner == page_ref:
                otxt = ('<span class="cown-here" aria-label="Owned by this '
                        'department">here</span>')
            else:
                otxt = '<a href="%s">%s</a>' % (fname(owner), esc(domains[owner]["name"]))
            # Visual merge, JS-safe (codex): every row keeps its owner cell
            # (screen readers hear it); repeats are hidden VISUALLY only and
            # recomputed to first-VISIBLE after any filter/search pass.
            own_cell = ('<td class="cown" data-o="1"><span class="ctxt%s">%s</span></td>'
                        % ("" if first else " ohide", otxt))
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
                '<tr class="chtr%s" data-status="%s" data-owner="%s">%s'
                '<th scope="row"><a href="%s" title="%s">%s</a></th>'
                '<td class="ckind">%s</td><td>%s</td>%s</tr>'
                % (" obreak" if first else "", c["status"], owner, own_cell,
                   cname(c["id"]), esc(c.get("purpose", "")), esc(c["title"]),
                   c["kind"], st_dot(c), cells))
        childh = "".join('<th scope="col">%s</th>' % esc(domains[t]["name"])
                         for t in tops) if show_cols else ""
        statuses = sorted({c["status"] for c, _ in picked})
        # Default = active; fall back to all when nothing is active (codex:
        # an empty first paint on a non-empty page is not acceptable).
        deffil = "active" if any(c["status"] == "active" for c, _ in picked) else "all"
        fil = ""
        if len(statuses) > 1:
            btns = "".join(
                '<button data-st="%s" aria-pressed="%s">%s</button>'
                % (s, "true" if s == deffil else "false", s)
                for s in ["all"] + statuses)
            fil = '<div class="chfil">%s</div>' % btns
        else:
            deffil = "all"
        legend = ('<p class="lanenote">O owner &middot; L linked</p>' if show_cols else "")
        return ('<section class="chsec"><h2 class="chh">Charters</h2>%s%s'
                '<div class="lanewrap"><table class="lanetab chtab" data-deffil="%s">'
                '<thead><tr><th scope="col">Owner</th><th scope="col">Charter</th>'
                '<th scope="col">Kind</th><th scope="col">Status</th>%s</tr></thead>'
                '<tbody>%s<tr class="chnone hidden"><td colspan="%d">no charters match</td></tr>'
                '</tbody></table></div></section>'
                % (legend, fil, deffil, childh, "".join(body), ncols))

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

    def _num(s):
        try:
            return float(str(s).replace("%", "").replace("<", "").replace(">", "").strip())
        except ValueError:
            return None

    def _metric_bar(cur, tgt):
        """Honest bar semantics (codex fold): '<N' targets are lower-is-better
        — the bar shows margin WITHIN target; '0' target met only at 0."""
        cv, tv = _num(cur), _num(tgt)
        if cv is None or tv is None:
            return ""
        t = str(tgt).strip()
        if t.startswith("<"):
            w = 0 if tv == 0 else max(5, min(100, int((1 - cv / tv) * 100)))
            if cv >= tv:
                w = 0
        elif tv == 0:
            w = 100 if cv == 0 else 0
        else:
            w = max(0, min(100, int(cv / tv * 100)))
        return '<div class="bar"><i style="width:%d%%"></i></div>' % w

    def _doc_entry(raw):
        path, kind = _resolve_art(raw)
        if not path:
            return None
        url = _gh_url(path, kind)
        if not url:
            return None
        summ = _summary(path, kind)
        base = os.path.basename(path.rstrip("/"))
        base = os.path.splitext(base)[0].replace("-", " ").replace("_", " ").strip()
        title = (base[:1].upper() + base[1:]) if base else path
        return (path, '<a class="doc" href="%s" target="_blank" rel="noopener">'
                      '<span class="arr">&#8599;</span><b>%s</b><span>%s</span></a>'
                % (esc(url), esc(title), esc(summ or path)))

    def charter_page(c):
        """Consumer charter page (founder-approved mock v6, 2026-08-01).
        Every section renders ONLY when its data exists — all 98 pre-existing
        sparse charters degrade to header + documents + fine print (codex:
        no empty shells). No internal field names on the page; the
        translation lives in the section labels."""
        owner = c.get("domain_ref")
        oname = esc(domains[owner]["name"])
        goals = [g for g in (c.get("goals") or []) if str(g).strip()]
        metrics = c.get("metrics") or []
        miles = c.get("milestones") or []
        todos = c.get("todos") or []
        links = [r for r in c["linked_domain_refs"] if r in domains and r not in hidden]
        S = []

        if goals:
            rows = "".join('<div class="goal"><span class="n">%d</span>%s</div>'
                           % (i, esc(str(g))) for i, g in enumerate(goals, 1))
            S.append('<section><div class="sh">Goals</div>'
                     '<div class="card">%s</div></section>' % rows)

        cells = []
        for m in metrics:
            lbl = str(m.get("label") or "").strip()
            cur = str(m.get("current") if m.get("current") is not None else "").strip()
            if not lbl or not cur:
                continue
            tgt = str(m.get("target") if m.get("target") is not None else "").strip()
            cells.append('<div class="metric"><div class="num" data-m="%d">%s</div>'
                         '<div class="lbl">%s</div>%s%s</div>'
                         % (len(cells), esc(cur), esc(lbl), _metric_bar(cur, tgt),
                            ('<div class="tgt">target %s</div>' % esc(tgt)) if tgt else ""))
        if cells:
            S.append('<section><div class="sh">How it&#39;s measuring up</div>'
                     '<div class="mgrid">%s</div></section>' % "".join(cells))

        prog = []
        if miles:
            # Trust array order (codex): never sort; fill runs to the 'now'
            # dot, else through the last 'done'.
            n = len(miles)
            fill_idx = next((i for i, m in enumerate(miles)
                             if m.get("status") == "now"), None)
            if fill_idx is None:
                dones = [i for i, m in enumerate(miles) if m.get("status") == "done"]
                fill_idx = dones[-1] if dones else 0
            fillw = 0 if n < 2 else int(fill_idx / (n - 1) * 100)
            dots = []
            for m in miles:
                st = m.get("status", "planned")
                cls = {"done": "done", "now": "now"}.get(st, "plan")
                dots.append('<div class="mile %s" data-mi="%d"%s><i></i><b>%s</b>'
                            '<span class="when">%s</span></div>'
                            % (cls, len(dots), (' title="%s"' % esc(m["done_when"]))
                               if m.get("done_when") else "",
                               esc(str(m.get("label", ""))), esc(str(m.get("target", "")))))
            prog.append('<div class="track"><span class="fill" style="width:%d%%"></span>%s</div>'
                        % (fillw, "".join(dots)))
        active = [t for t in todos if t.get("status") in ("open", "in-progress")
                  and str(t.get("title", "")).strip()]
        shipped = [t for t in todos if t.get("status") == "done"
                   and str(t.get("title", "")).strip()]
        if active or shipped:
            now_lab = next((m.get("label") for m in miles if m.get("status") == "now"), None)
            card = ['<div class="pgroup">Happening now%s</div>'
                    % (" &middot; " + esc(str(now_lab)) if now_lab else "")]
            for j, t in enumerate(active):
                tasks = [x for x in (t.get("tasks") or [])
                         if str(x.get("label", "")).strip()]
                dcount = sum(1 for x in tasks if x.get("done"))
                frac = ('<span class="frac">%d/%d done</span>' % (dcount, len(tasks))) \
                    if tasks else ""
                doing = t.get("status") == "in-progress"
                trs = ""
                for ti, x in enumerate(tasks):
                    if x.get("done"):
                        trs += ('<tr data-task="%d"><td class="tdone">%s</td><td class="st">'
                                '<span class="chip done">Done</span></td></tr>' % (ti, esc(x["label"])))
                    elif x.get("doing"):
                        trs += ('<tr data-task="%d"><td>%s</td><td class="st">'
                                '<span class="chip doing">In progress</span></td></tr>' % (ti, esc(x["label"])))
                    else:
                        trs += ('<tr data-task="%d"><td>%s</td><td class="st">'
                                '<span class="chip rem">Remaining</span></td></tr>' % (ti, esc(x["label"])))
                body = ('<table class="tasktab">%s</table>' % trs) if trs else \
                    ('<table class="tasktab"><tr><td>%s</td><td class="st"></td></tr></table>'
                     % esc(str(t.get("done_when") or t.get("impact") or "")))
                card.append('<details class="item%s" data-item="%d"%s><summary><i></i><b>%s</b>%s'
                            '<span class="caret">&#9656;</span></summary>%s</details>'
                            % (" doing" if doing else "", j, " open" if j == 0 and doing else "",
                               esc(t["title"]), frac, body))
            if shipped:
                rows = "".join(
                    '<div class="shipped"><i></i><div><b>%s</b><p>%s%s</p></div></div>'
                    % (esc(t["title"]),
                       ('<span class="date">%s</span> &mdash; ' % esc(t["done_at"]))
                       if t.get("done_at") else "",
                       esc(str(t.get("done_how", "")))) for t in shipped)
                card.append('<details class="fold"><summary>%d shipped &mdash; see them'
                            '</summary>%s</details>' % (len(shipped), rows))
            prog.append('<div class="card">%s</div>' % "".join(card))
        if prog:
            S.append('<section><div class="sh">Progress</div>%s</section>' % "".join(prog))

        # Key documents = artifacts UNION scope_in, deduped on RESOLVED path.
        seen_docs, docs = set(), []
        for raw in list(c["artifacts"]) + [str(v) for v in (c.get("scope_in") or [])]:
            e = _doc_entry(raw)
            if e and e[0] not in seen_docs:
                seen_docs.add(e[0])
                docs.append(e[1])
        if docs:
            S.append('<section><div class="sh">Key documents</div>'
                     '<div class="card">%s</div></section>' % "".join(docs))

        fps = []
        if c.get("obligations"):
            fps.append(("We promise", " ".join(esc(str(v)) for v in c["obligations"]), ""))
        if c.get("invariants"):
            fps.append(("Never changes", " &middot; ".join(esc(str(v)) for v in c["invariants"]), ""))
        sm = c.get("success_metrics") or []
        if sm and not cells:
            fps.append(("How we measure success",
                        "".join('<span class="pill">%s</span>' % esc(str(v)) for v in sm), ""))
        so = [str(v) for v in (c.get("scope_out") or []) if str(v).strip()]
        if so:
            fps.append(("Out of scope", " &middot; ".join(esc(v) for v in so), " mut"))
        if c.get("termination"):
            fps.append(("Reviewed", esc(str(c["termination"])), " mut"))
        if fps:
            fcells = "".join('<div class="fcell"><div class="k">%s</div>'
                             '<div class="v%s">%s</div></div>' % (k, m, v)
                             for k, v, m in fps)
            S.append('<section class="fpsec"><div class="sh">The fine print</div>'
                     '<div class="fp">%s</div></section>' % fcells)

        byline = ('Owned by <a href="%s">%s</a>' % (fname(owner), oname))
        if links:
            byline += " &middot; works with " + ", ".join(
                '<a href="%s">%s</a>' % (fname(r), esc(domains[r]["name"])) for r in links)
        return CH_TMPL % dict(
            cid=c["id"],
            title=esc(c["title"]) + " · Charter",
            crumb=crumb(owner) + " / <b>%s</b>" % esc(c["title"]),
            status=c["status"], name=esc(c["title"]),
            sub=esc(c.get("purpose", "")), byline=byline,
            body="".join(S),
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


    def export_registry(out_dir):
        """Volatile data view for on-the-fly hydration (founder 2026-08-01).
        Mirrors EXACTLY what the pages rendered, in the same order —
        hydration is patch-only and count-validated (codex fold)."""
        out = {}
        for c in all_ch:
            # §2.1 read-path table: this membership check reads the FULL tenant
            # map on purpose. Filtering it to live refs would drop every charter
            # homed to a retired domain out of registry.json and kill §3.2.4's
            # Archive tray and §4.2's tombstones — both P0.
            if c.get("domain_ref") in hidden or c.get("domain_ref") not in all_domains:
                continue
            row = {"status": c["status"]}
            mets = [str(m.get("current", "")).strip()
                    for m in (c.get("metrics") or [])
                    if str(m.get("label", "")).strip() and m.get("current") is not None]
            if mets:
                row["metrics"] = mets
            mis = [m.get("status", "planned") for m in (c.get("milestones") or [])]
            if mis:
                row["milestones"] = mis
            acts = [t for t in (c.get("todos") or [])
                    if t.get("status") in ("open", "in-progress")
                    and str(t.get("title", "")).strip()]
            items = [[bool(x.get("done")) for x in (t.get("tasks") or [])
                      if str(x.get("label", "")).strip()] for t in acts]
            if items:
                row["items"] = items
            out[c["id"]] = row
        payload = {"charters": out}
        with open(os.path.join(out_dir, "registry.json"), "w") as fh:
            json.dump(payload, fh, sort_keys=True)
        return len(out)

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
    export_registry(out_dir)
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
.chtab td.ckind{font:400 .74rem/1 ui-monospace,monospace;color:var(--mut);text-align:left}
.ctxt.ohide{opacity:0}
tr.obreak th,tr.obreak td{border-top:2px solid var(--line)}
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
(function(){var q=document.getElementById('q');
var tb=document.querySelector('table.chtab');
var FIL=tb?(tb.getAttribute('data-deffil')||'all'):'all';
function chApply(){var v=q?q.value.trim().toLowerCase():'';
 document.querySelectorAll('tr.chtr').forEach(function(r){
  var okS=(FIL==='all')||r.getAttribute('data-status')===FIL;
  var a=r.querySelector('a[title]');
  var t=(r.textContent+' '+(a?a.getAttribute('title'):'')).toLowerCase();
  r.classList.toggle('hidden',!(okS&&(!v||t.indexOf(v)>=0)));});
 var seen={};
 document.querySelectorAll('tr.chtr').forEach(function(r){
  var s=r.querySelector('td.cown .ctxt');if(!s)return;
  s.classList.add('ohide');r.classList.remove('obreak');});
 document.querySelectorAll('tr.chtr:not(.hidden)').forEach(function(r){
  var o=r.getAttribute('data-owner');var s=r.querySelector('td.cown .ctxt');
  if(!s)return;
  if(!seen[o]){seen[o]=1;s.classList.remove('ohide');r.classList.add('obreak');}});
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
chApply();});
chApply();})();
</script>
</div></body></html>
"""


CH_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<style>
:root{--bg:%(bg)s;--card:%(card)s;--ink:%(ink)s;--mut:%(muted)s;--line:%(line)s;--acc:%(accent)s;--accbg:%(accent_bg)s;--ok:#8a9a7b;--okbg:#eef1e8}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.6 %(font)s}
.wrap{max-width:680px;margin:0 auto;padding:48px 24px 64px}
.crumb{font-size:.8rem;color:var(--mut);margin-bottom:28px}
.crumb a{color:var(--mut);text-decoration:none}
.crumb a:hover{color:var(--acc)}
.crumb b{color:var(--ink);font-weight:500}
.badge{display:inline-block;font-size:.72rem;font-weight:600;color:var(--acc);background:var(--accbg);border-radius:999px;padding:4px 12px;margin-bottom:14px;text-transform:capitalize}
h1{font-size:1.75rem;line-height:1.25;letter-spacing:-.02em;font-weight:700;margin-bottom:10px}
.sub{font-size:1.02rem;color:var(--mut);max-width:52ch;margin-bottom:6px}
.byline{font-size:.8rem;color:var(--mut);margin-bottom:36px}
.byline a{color:var(--acc);text-decoration:none}
section{margin-bottom:44px}
.sh{font-size:.72rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.goal{display:flex;gap:14px;padding:16px 20px;border-top:1px solid var(--line);font-size:.94rem}
.goal:first-child{border-top:none}
.goal .n{flex:none;width:26px;height:26px;border-radius:50%%;background:var(--accbg);color:var(--acc);font-weight:700;font-size:.8rem;display:flex;align-items:center;justify-content:center;margin-top:1px}
.mgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.metric{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 18px 16px}
.metric .num{font-size:1.6rem;font-weight:700;letter-spacing:-.02em}
.metric .lbl{font-size:.78rem;color:var(--mut);margin:2px 0 10px}
.bar{height:5px;border-radius:3px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%%;background:var(--acc);border-radius:3px}
.metric .tgt{font-size:.68rem;color:var(--mut);margin-top:6px}
.land{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:.84rem}
.lnode{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 14px;text-decoration:none;color:var(--ink)}
.lnode:hover{border-color:var(--acc)}
.lnode.me{border:1.5px solid var(--acc);background:var(--accbg);font-weight:600}
.lnode small{display:block;font-size:.66rem;color:var(--mut);font-weight:400}
.larr{color:var(--mut);font-size:.8rem}
.lmore{font-size:.78rem;color:var(--mut)}
.lmore a{color:var(--acc);text-decoration:none}
.track{position:relative;display:flex;justify-content:space-between;margin:8px 2px 26px}
.track::before{content:"";position:absolute;top:8px;left:12px;right:12px;height:2px;background:var(--line);border-radius:2px}
.track .fill{position:absolute;top:8px;left:12px;max-width:calc(100%% - 24px);height:2px;background:var(--acc);border-radius:2px}
.mile{position:relative;flex:1;text-align:center;padding-top:30px;font-size:.8rem;min-width:0}
.mile i{position:absolute;top:0;left:50%%;transform:translateX(-50%%);width:18px;height:18px;border-radius:50%%;border:2px solid var(--acc);background:var(--acc)}
.mile.done i::after{content:"\2713";position:absolute;inset:0;color:var(--card);font-size:.6rem;line-height:14px;text-align:center;font-weight:700}
.mile.now i{background:var(--card);box-shadow:0 0 0 4px var(--accbg)}
.mile.plan i{background:var(--card);border-color:var(--line)}
.mile b{display:block;font-weight:600;line-height:1.35;padding:0 4px}
.mile.now b{color:var(--acc)}
.mile.plan b{color:var(--mut);font-weight:500}
.mile .when{color:var(--mut);font-size:.72rem}
.pgroup{padding:12px 18px 4px;font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--acc)}
details.item{border-top:1px solid var(--line)}
details.item:first-of-type{border-top:none}
details.item summary{list-style:none;cursor:pointer;display:flex;gap:12px;align-items:center;padding:11px 18px}
details.item summary::-webkit-details-marker{display:none}
details.item summary:hover{background:var(--accbg)}
details.item summary i{flex:none;width:9px;height:9px;border-radius:50%%;border:2px solid var(--line);background:var(--card)}
details.item.doing summary i{border-color:var(--acc);background:var(--accbg)}
details.item summary b{font-size:.88rem;font-weight:600;min-width:0;flex:1}
.frac{flex:none;font-size:.7rem;color:var(--mut);background:var(--bg);border-radius:999px;padding:3px 9px;white-space:nowrap}
details.item.doing .frac{color:var(--acc);background:var(--accbg)}
details.item summary .caret{flex:none;color:var(--mut);font-size:.7rem;transition:transform .15s}
details.item[open] summary .caret{transform:rotate(90deg)}
.tasktab{width:100%%;border-collapse:collapse;font-size:.8rem}
.tasktab td{padding:8px 18px 8px 39px;border-top:1px dotted var(--line)}
.tasktab td.st{width:110px;text-align:right;padding-right:18px;padding-left:0}
.chip{display:inline-block;font-size:.68rem;font-weight:600;border-radius:999px;padding:3px 10px}
.chip.done{color:var(--ok);background:var(--okbg)}
.chip.doing{color:var(--acc);background:var(--accbg)}
.chip.rem{color:var(--mut);background:var(--bg)}
.tasktab td.tdone{color:var(--mut);text-decoration:line-through;text-decoration-color:var(--line)}
details.fold summary{list-style:none;cursor:pointer;padding:12px 18px;font-size:.8rem;color:var(--mut);border-top:1px solid var(--line);text-align:center}
details.fold summary::-webkit-details-marker{display:none}
details.fold summary:hover{color:var(--acc)}
.shipped{display:flex;gap:12px;align-items:flex-start;padding:11px 18px;border-top:1px dotted var(--line)}
.shipped i{flex:none;width:9px;height:9px;border-radius:50%%;border:2px solid var(--ok);background:var(--ok);margin-top:6px}
.shipped b{font-size:.86rem;font-weight:600;display:block}
.shipped p{font-size:.8rem;color:var(--mut)}
.shipped p .date{color:var(--ink);font-weight:500}
.doc{display:block;padding:14px 20px;border-top:1px solid var(--line);text-decoration:none;color:inherit}
.doc:first-child{border-top:none}
.doc:hover{background:var(--accbg)}
.doc b{font-size:.9rem;font-weight:600;display:block}
.doc span{font-size:.8rem;color:var(--mut)}
.doc .arr{float:right;color:var(--acc);font-size:.8rem;margin-top:8px}
.fp{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.fcell{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 20px}
.fcell .k{font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-bottom:6px}
.fcell .v{font-size:.85rem}
.fcell .v.mut{color:var(--mut)}
.pill{display:inline-block;background:var(--bg);border-radius:999px;padding:4px 12px;font-size:.8rem;margin:3px 6px 0 0}
footer{color:var(--mut);font-size:.75rem;text-align:center;margin-top:48px}
@media(max-width:560px){
 .wrap{padding:32px 18px 48px}
 h1{font-size:1.45rem}
 .track{flex-direction:column;gap:18px}
 .track::before,.track .fill{display:none}
 .mile{text-align:left;padding:0 0 0 30px}
 .mile i{left:0;transform:none}
 .tasktab td{padding-left:18px}}
</style></head><body><div class="wrap">
<p class="crumb">%(crumb)s</p>
<span class="badge" data-cid="%(cid)s">%(status)s</span>
<h1>%(name)s</h1>
<p class="sub">%(sub)s</p>
<p class="byline">%(byline)s</p>
%(body)s
<footer>generated from the live registry</footer>
<script>
(function(){var b=document.querySelector('[data-cid]');if(!b)return;
fetch('registry.json?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()})
.then(function(d){var c=d.charters&&d.charters[b.getAttribute('data-cid')];if(!c)return;
var ST={active:1,shipped:1,retired:1,paused:1};
if(c.status&&ST[c.status])b.textContent=c.status;
var nums=document.querySelectorAll('[data-m]');
if(c.metrics&&nums.length===c.metrics.length)
 nums.forEach(function(el,i){el.textContent=c.metrics[i];});
var MS={done:'done',now:'now',planned:'plan',dropped:'plan'};
var mi=document.querySelectorAll('[data-mi]');
if(c.milestones&&mi.length===c.milestones.length)
 mi.forEach(function(el,i){var s=MS[c.milestones[i]];if(!s)return;
  el.classList.remove('done','now','plan');el.classList.add(s);});
var dets=document.querySelectorAll('[data-item]');
if(c.items&&dets.length===c.items.length)
 dets.forEach(function(det,i){var rows=det.querySelectorAll('[data-task]');
  var st=c.items[i];if(!st||rows.length!==st.length)return;var n=0;
  rows.forEach(function(tr,j){var td=tr.querySelector('td');var chip=tr.querySelector('.chip');
   if(!td||!chip)return;
   if(st[j]){n++;td.classList.add('tdone');chip.className='chip done';chip.textContent='Done';}
   else{td.classList.remove('tdone');if(chip.className!=='chip doing'){chip.className='chip rem';chip.textContent='Remaining';}}});
  var f=det.querySelector('.frac');if(f&&st.length)f.textContent=n+'/'+st.length+' done';});
}).catch(function(){});})();
</script>
</div></body></html>
"""


def export_registry_only(out_dir, tenant_id=None):
    """Fast-lane export (hook): write ONLY registry.json — the volatile view —
    without regenerating pages. Same shapes/order as build_site's export, and
    the same tenant rule (§6): the INPUT SET is filtered, so a second tenant's
    charters are absent rather than suppressed.

    NOT live-filtered, deliberately, and this is the one publish surface where
    that is correct: §2.1's read-path table names `export_registry_only` as a
    consumer that must keep seeing tombstones, because a charter homed to a
    retired domain still has to reach §3.2.4's Archive tray. The PAGES drop
    retired departments (see `_render_set`); the registry keeps their rows."""
    tenant_id = _tenant(tenant_id)
    domains = E.tenant_refs(E.load_domains(), tenant_id)
    kids = {}
    for r, d in domains.items():
        kids.setdefault(d.get("parent_ref"), []).append(r)
    hidden = set()

    def _hide(ref):
        for c2 in kids.get(ref, []):
            hidden.add(c2)
            _hide(c2)
    for r, d in domains.items():
        if d.get("public_names_withheld"):
            _hide(r)
    out = {}
    for fn in E.charter_body_files():
        try:
            body = json.load(open(os.path.join(E.CHARTERS, fn)))
        except (ValueError, OSError):
            continue
        if not isinstance(body, dict):
            continue
        body.setdefault("id", fn[:-len(".json")])
        c = E.charter_view(body)        # body + sidecar; body never mutated
        c.setdefault("status", "active")
        if c.get("domain_ref") in hidden or c.get("domain_ref") not in domains:
            continue
        row = {"status": c["status"]}
        mets = [str(m.get("current", "")).strip()
                for m in (c.get("metrics") or [])
                if str(m.get("label", "")).strip() and m.get("current") is not None]
        if mets:
            row["metrics"] = mets
        mis = [m.get("status", "planned") for m in (c.get("milestones") or [])]
        if mis:
            row["milestones"] = mis
        acts = [t for t in (c.get("todos") or [])
                if t.get("status") in ("open", "in-progress")
                and str(t.get("title", "")).strip()]
        items = [[bool(x.get("done")) for x in (t.get("tasks") or [])
                  if str(x.get("label", "")).strip()] for t in acts]
        if items:
            row["items"] = items
        out[c.get("id", fn[:-5])] = row
    with open(os.path.join(out_dir, "registry.json"), "w") as fh:
        json.dump({"charters": out}, fh, sort_keys=True)
    return len(out)


#: flags that CONSUME the next argv token. Everything else that starts with
#: "--" is a bare switch and everything left over is a positional.
_VALUE_FLAGS = ("--label", "--tenant")


def _parse_argv(argv):
    """-> (positionals, {flag: value}). Consumes by POSITION, never by value.

    Two fragilities this replaces, both of the same class as the engine's
    `_flag()` (which existed for exactly this and was not used here):
    `sys.argv[sys.argv.index('--tenant') + 1]` raised an uncaught IndexError
    when the flag was last, and `[a for a in args if a != tenant]` stripped
    EVERY positional equal to the tenant string — so an out-dir named after the
    tenant was silently dropped and the site was written to ./domains/ instead.
    """
    pos, flags, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        if a in _VALUE_FLAGS:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit("%s requires a value" % a)
            flags[a] = argv[i + 1]
            i += 2
            continue
        if not a.startswith("--"):
            pos.append(a)
        i += 1
    return pos, flags


if __name__ == "__main__":
    args, flags = _parse_argv(sys.argv[1:])
    label = flags.get("--label", "Departments")
    # §6: --tenant is REQUIRED on every publish path. A defaulted tenant on a
    # public-artifact generator is how a second tenant reaches GitHub Pages.
    if "--tenant" not in flags:
        raise SystemExit("--tenant <T-id> is required (§6): a publish must name "
                         "the tenant whose registry it is allowed to render")
    tenant = flags["--tenant"]
    if "--export-registry" in sys.argv:
        out = args[0] if args else "domains"
        n = export_registry_only(out, tenant_id=tenant)
        print("registry.json: %d charters -> %s/ [%s]" % (n, out, tenant))
    elif "--site" in sys.argv:
        out = args[0] if args else "domains"
        n = build_site(out, label=label, tenant_id=tenant)
        print("site: %d zoom pages in %s/ [%s]" % (n, out, tenant))
    else:
        out = args[0] if args else "domains.html"
        p, n = build(out, label=label, tenant_id=tenant)
        print("wrote %s (%d domains) [%s]" % (p, n, tenant))
