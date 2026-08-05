#!/usr/bin/env python3
"""org_import.py — rebuild a registry from a PUBLISHED domains export.

The inverse of lib/domains_page.py build_site(). Point it at a directory of
generated pages (`website/domains/`) and it reconstructs the domains and
charters that produced them, into a placement_engine registry.

Why this exists: the department tree lives only in the registry of the machine
that authored it. The published site is the only portable record of it. This
module makes that record reversible, so a second machine can carry the same
org instead of an empty one.

WHAT IS RECOVERED EXACTLY
  domains   ref, name, parent_ref, description, sibling ORDER (the D-path)
  charters  id, title, purpose, kind, status, owner domain, linked_domain_refs,
            artifacts, and the page extras (goals / metrics / milestones / todos)

  Nothing here is guessed. Every field is stated outright in the export except
  linked_domain_refs, which are inverted out of the O/L lane grid — see
  resolve_links() — and then CHECKED by re-deriving every lane cell on every
  page and comparing against the published HTML. A single mismatched cell
  fails the import.

WHAT IS NOT RECOVERED — stated, not silently faked
  1. `ts_minted_ms` is not in the export. It is load-bearing anyway, because
     placement_engine.domain_path() orders siblings by (ts_minted_ms, ref) and
     that ordering IS the D-path. Imported domains therefore get a synthetic,
     strictly increasing stamp assigned in published chip order, so D1..D5 and
     D1.1..D1.11 come out as published. The stamp is an IMPORT time, not a mint
     time; `origin: "operator"` and `import_source` mark every such record.
  2. A charter body is content-addressed (placement_engine.charter_id_of), but
     the export does not carry scope_in / scope_out / invariants. A body written
     under its PUBLISHED id therefore does not hash to that id. Id parity is the
     right trade: the ids are what every cross-link, every charter page and the
     panel's own view are keyed on. Each imported body records the reason in
     `id_not_content_addressed`.
  3. `artifacts` are recovered as the repo-relative path inside the GitHub URL
     the generator emitted. When the original path carried a submodule prefix
     that _gh_url() stripped, the recovered path is the in-repo one. The full
     URL is kept alongside in the sidecar so nothing is lost.

Usage:
  org_import.py <export-dir>                    # dry run: parse, verify, report
  org_import.py <export-dir> --apply            # back up, then write
  org_import.py <export-dir> --apply --home DIR # write to a specific registry
  org_import.py <export-dir> --json             # machine-readable report

--apply REFUSES to run unless the backup succeeded. It never overwrites an
existing domain or charter file: an id already on disk is reported as `skipped`.
"""
import argparse
import glob
import html
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import placement_engine as E  # noqa: E402

TENANT = os.environ.get("SUTRA_TENANT", "T-local")

# The generator's own markup, matched exactly as build_site() emits it.
_H1 = re.compile(r"<h1>(.*?)</h1>", re.S)
_ROOTDESC = re.compile(r'<p class="rootdesc">(.*?)</p>', re.S)
_CRUMB = re.compile(r'<p class="crumb">(.*?)</p>', re.S)
_CRUMB_LINK = re.compile(r'href="(index|dref-[0-9a-f]+)\.html"')
_CARD = re.compile(
    r'<a class="info[^"]*"[^>]*href="(dref-[0-9a-f]+)\.html"[^>]*>'
    r'\s*<span class="chip">([^<]*)</span>\s*<b>(.*?)</b>\s*(?:<p>(.*?)</p>)?', re.S)
# A page renders its DIRECT children as <section class="dept"> blocks and its
# grandchildren as .info cards. Both carry the chip; only the section carries
# the full (untruncated) description.
_SECT = re.compile(
    r'<section id="[^"]*" class="dept"><header><span class="chip big">([^<]*)</span>'
    r'<div><h2><a class="dlink" href="(dref-[0-9a-f]+)\.html">(.*?)</a></h2>'
    r'(?:<p class="desc">(.*?)</p>)?', re.S)
_THEAD = re.compile(r"<thead>(.*?)</thead>", re.S)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
_ROW = re.compile(
    r'<tr class="chtr[^"]*" data-status="([^"]*)" data-owner="([^"]*)">(.*?)</tr>', re.S)
_ROW_LINK = re.compile(
    r'<th scope="row"><a href="(C-[0-9a-f]+)\.html" title="([^"]*)">(.*?)</a></th>', re.S)
_KIND = re.compile(r'<td class="ckind">([^<]*)</td>')
_LANE_TD = re.compile(r'<td class="(lo|ll|ln)"[^>]*>')
_DOC = re.compile(r'<a class="doc" href="([^"]+)"[^>]*>.*?<b>(.*?)</b><span>(.*?)</span>', re.S)
_GH_BLOB = re.compile(r"^https://github\.com/[^/]+/[^/]+/(?:blob|tree)/[^/]+/(.*)$")
# charter page: the structured sections, exactly as charter_page() emits them
_GOAL = re.compile(r'<div class="goal"><span class="n">\d+</span>(.*?)</div>', re.S)
_METRIC = re.compile(
    r'<div class="metric"><div class="num" data-m="\d+">(.*?)</div>'
    r'<div class="lbl">(.*?)</div>(?:<div class="bar">.*?</div>)?'
    r'(?:<div class="tgt">target (.*?)</div>)?</div>', re.S)
_MILE = re.compile(
    r'<div class="mile (done|now|plan)" data-mi="\d+"(?: title="([^"]*)")?>'
    r'<i></i><b>(.*?)</b><span class="when">(.*?)</span></div>', re.S)
_ITEM = re.compile(
    r'<details class="item( doing)?" data-item="\d+"[^>]*><summary><i></i>'
    r'<b>(.*?)</b>(?:<span class="frac">[^<]*</span>)?'
    r'<span class="caret">[^<]*</span></summary>(.*?)</details>', re.S)
_TASK = re.compile(
    r'<tr data-task="\d+"><td(?: class="tdone")?>(.*?)</td><td class="st">'
    r'(?:<span class="chip (done|doing|rem)">[^<]*</span>)?</td></tr>', re.S)
_SHIPPED = re.compile(
    r'<div class="shipped"><i></i><div><b>(.*?)</b><p>'
    r'(?:<span class="date">(.*?)</span> &mdash; )?(.*?)</p></div></div>', re.S)
_BYLINE = re.compile(r'<p class="byline">(.*?)</p>', re.S)
_BY_LINK = re.compile(r'href="(dref-[0-9a-f]+)\.html"')


def _txt(x):
    return html.unescape(re.sub(r"<[^>]+>", "", x or "")).strip()


def _unesc(x):
    return html.unescape(x or "").strip()


def _page_ref(path):
    b = os.path.basename(path)
    return "ROOT" if b == "index.html" else b[:-5]


def _chip_key(chip):
    """'D1.11' -> (1, 11) so chips sort numerically, not lexically."""
    return tuple(int(n) for n in re.findall(r"\d+", chip or "")) or (0,)


class ImportError_(Exception):
    """A defect in the export or in this inversion. Never a partial write."""


# --------------------------------------------------------------------------
# parse
# --------------------------------------------------------------------------

def parse_export(site_dir):
    """Pure read. Returns a dict describing the org the export was made from.

    Raises ImportError_ if the export is not self-consistent — an unresolved
    parent, a charter row without a link, a lane header naming no child.
    """
    page_files = [p for p in sorted(glob.glob(os.path.join(site_dir, "*.html")))
                  if not os.path.basename(p).startswith("C-")]
    if not page_files:
        raise ImportError_("no domain pages found under %s" % site_dir)

    src, name, desc, parent, chip = {}, {}, {}, {}, {}
    for p in page_files:
        s = open(p, encoding="utf-8").read()
        ref = _page_ref(p)
        src[ref] = s
        m = _H1.search(s)
        name[ref] = _txt(m.group(1)) if m else ""
        d = _ROOTDESC.search(s)
        if d:
            desc[ref] = _txt(d.group(1))
        if ref == "ROOT":
            continue
        # PARENTHOOD comes from the page's own breadcrumb. Grid cards are not
        # containment: index.html renders a card for every depth-2 domain too.
        cm = _CRUMB.search(s)
        links = _CRUMB_LINK.findall(cm.group(1)) if cm else []
        parent[ref] = ("ROOT" if links[-1] == "index" else links[-1]) if links else "ROOT"

    # Chips carry the sibling ORDINAL, which is the only thing that reproduces
    # the D-path. NOTE they are PAGE-RELATIVE: "Governance Hooks" is chip D1 on
    # the Core Plugin page and D1.1 as a card one level up. Only the ordinal
    # among siblings is used, and siblings always appear together, so either
    # encoding orders them identically.
    #
    # Sections (a page's DIRECT children) are authoritative and are collected in
    # a first pass; cards are a fallback for anything a section did not cover.
    # Two passes rather than one, so the result cannot depend on glob order.
    for s in src.values():
        for m in _SECT.finditer(s):
            kid = m.group(2)
            chip.setdefault(kid, _txt(m.group(1)))
            name.setdefault(kid, _txt(m.group(3)))
            if kid not in desc:
                desc[kid] = _txt(m.group(4) or "")
    for s in src.values():
        for m in _CARD.finditer(s):
            kid = m.group(1)
            chip.setdefault(kid, _txt(m.group(2)))
            name.setdefault(kid, _txt(m.group(3)))
            if kid not in desc:
                desc[kid] = _txt(m.group(4) or "")

    unknown = sorted(r for r, pa in parent.items() if pa != "ROOT" and pa not in parent)
    if unknown:
        raise ImportError_("parent unresolved for: %s" % unknown[:5])

    kids = defaultdict(list)
    for r, pa in parent.items():
        kids[pa].append(r)
    for pa in kids:
        kids[pa].sort(key=lambda r: (_chip_key(chip.get(r)), r))

    # ---------------------------------------------------------- charters ---
    charters, lanes = {}, defaultdict(dict)
    for ref, s in src.items():
        th = _THEAD.search(s)
        if not th:
            continue
        heads = [_txt(h) for h in _TH.findall(th.group(1))][4:]
        by_name = {name.get(k, ""): k for k in kids[ref]}
        lane_refs = [by_name.get(h) for h in heads]
        if any(x is None for x in lane_refs):
            raise ImportError_(
                "%s: lane header names no child: %s"
                % (ref, [h for h, r in zip(heads, lane_refs) if r is None]))
        for status, owner, inner in _ROW.findall(s):
            lm = _ROW_LINK.search(inner)
            if not lm:
                raise ImportError_("%s: charter row without a link" % ref)
            cid = lm.group(1)
            km = _KIND.search(inner)
            rec = {"id": cid, "title": _txt(lm.group(3)), "purpose": _unesc(lm.group(2)),
                   "kind": km.group(1) if km else "standing",
                   "status": status, "owner": owner}
            prev = charters.setdefault(cid, rec)
            for k in ("title", "kind", "status", "owner"):
                if prev[k] != rec[k]:
                    raise ImportError_("%s: pages disagree on %s (%r vs %r)"
                                       % (cid, k, prev[k], rec[k]))
            roles = _LANE_TD.findall(inner)
            if lane_refs and len(roles) == len(lane_refs):
                lanes[cid][ref] = {lane_refs[i]: {"lo": "O", "ll": "L"}[r]
                                   for i, r in enumerate(roles) if r != "ln"}

    # TWO PARTIAL WITNESSES, so the answer is their UNION -- and then proved.
    #
    #   the lane grid   under-reports: a link only shows up as an L where a lane
    #                   column exists, and a page with no children renders none.
    #   the byline      under-reports too: charter_page() filters it to
    #                   `r in domains and r not in hidden`, i.e. to the domains
    #                   inside that page's render window (build_site window=2).
    #
    # Neither contains the other -- measured on this export, 24 charters where
    # they differ, with links unique to EACH side. Taking either alone loses
    # real links (and drops whole rows from the published table, since row
    # inclusion depends on how many lanes a charter spans). The union is then
    # handed to verify_lanes(), which re-derives every published cell: if the
    # union invented a link, a cell that should be blank comes back L and the
    # import fails rather than shipping a guess.
    grid = {cid: resolve_links(lanes.get(cid, {})) for cid in charters}
    stated, both_seen = {}, 0
    for cid in charters:
        s = _page_links(site_dir, cid)
        stated[cid] = set() if s is None else s
        if s is not None:
            both_seen += 1
    links = {cid: grid[cid] | stated[cid] for cid in charters}
    disagreements = [(cid, sorted(grid[cid]), sorted(stated[cid]))
                     for cid in charters if grid[cid] != stated[cid]]
    verify_lanes(charters, links, lanes, kids, parent)

    for cid, c in charters.items():
        c["artifacts"], c["artifact_urls"] = _artifacts(site_dir, cid)
        c["linked_domain_refs"] = sorted(links[cid])
    extras = {cid: e for cid, e in
              ((cid, _page_extras(site_dir, cid)) for cid in charters) if e}
    checked = _check_registry_json(site_dir, charters)

    return {"root_name": name.get("ROOT", ""),
            "root_desc": desc.get("ROOT", ""), "name": name, "desc": desc,
            "chip": chip, "parent": parent, "kids": dict(kids),
            "charters": charters, "extras": extras,
            "link_disagreements": disagreements,
            "status_cross_checked": checked}


def resolve_links(per_page):
    """Invert the O/L grid back into linked_domain_refs.

    domains_page.cols_for() rolls every linked ref UP to the direct child of the
    page it sits under, so an "L" in column X on page parent(X) means the
    charter links to something INSIDE subtree(X). The link is X itself unless an
    L for the same charter appears deeper, on page X.
    """
    out = set()
    for cols in per_page.values():
        for x, role in cols.items():
            if role != "L":
                continue
            deeper = per_page.get(x, {})
            if any(r == "L" for r in deeper.values()):
                continue                      # the real link is further down
            out.add(x)
    return out


def _child_of(parent, page, ref):
    """domains_page.child_of(), cycle guard included."""
    cur, seen = ref, set()
    while cur in parent and cur not in seen:
        seen.add(cur)
        if parent[cur] == page:
            return cur
        cur = parent[cur]
    return None


def verify_lanes(charters, links, lanes, kids, parent):
    """Re-derive every published lane cell from the recovered data. This is the
    proof that resolve_links() inverted the grid rather than approximating it."""
    bad, checked = [], 0
    for page, tops in kids.items():
        if not tops:
            continue
        tset = set(tops)
        for cid, c in charters.items():
            pub = lanes.get(cid, {}).get(page)
            if pub is None:
                continue
            got = {}
            for r in {c["owner"]} | links[cid]:
                if r == page:
                    continue
                col = _child_of(parent, page, r)
                if col not in tset:
                    continue
                role = "O" if r == c["owner"] else "L"
                if got.get(col) != "O":
                    got[col] = role
            checked += 1
            if got != pub:
                bad.append((cid, page, pub, got))
    if bad:
        raise ImportError_(
            "lane grid did not re-derive (%d of %d cells): %s"
            % (len(bad), checked, bad[:3]))
    return checked


def _artifacts(site_dir, cid):
    path = os.path.join(site_dir, cid + ".html")
    if not os.path.exists(path):
        return [], []
    s = open(path, encoding="utf-8").read()
    paths, urls = [], []
    for url, _label, _summary in _DOC.findall(s):
        url = _unesc(url)
        urls.append(url)
        m = _GH_BLOB.match(url)
        paths.append(_unesc(m.group(1)) if m else url)
    return paths, urls


def _check_registry_json(site_dir, charters):
    """registry.json is the site's LIVE overlay, not a sidecar dump.

    Its `metrics` / `milestones` / `items` arrays are POSITIONAL values keyed to
    the data-m / data-mi / data-item indices in the rendered page — ["100%",
    "0", "0"], not [{"label": ..., "current": ...}]. Copying them into a sidecar
    would write the wrong shape under the right key and crash the generator on
    the next build (charter_page does m.get("label")). So the arrays are NOT
    imported; the real structures come out of the charter page itself, via
    _page_extras(). What registry.json IS good for is a second opinion on
    status, which is checked here.
    """
    path = os.path.join(site_dir, "registry.json")
    if not os.path.exists(path):
        return 0
    reg = json.load(open(path, encoding="utf-8")).get("charters", {})
    n = 0
    for cid, row in reg.items():
        if cid not in charters or not row.get("status"):
            continue
        if row["status"] != charters[cid]["status"]:
            raise ImportError_("%s: registry.json says %s, the table says %s"
                               % (cid, row["status"], charters[cid]["status"]))
        n += 1
    return n


def _page_extras(site_dir, cid):
    """goals / metrics / milestones / todos, read back out of the charter page
    in the sidecar's own shape (placement_engine._sidecar_default)."""
    path = os.path.join(site_dir, cid + ".html")
    if not os.path.exists(path):
        return {}
    s = open(path, encoding="utf-8").read()
    out = {}

    goals = [_txt(g) for g in _GOAL.findall(s)]
    if goals:
        out["goals"] = goals

    metrics = []
    for cur, lbl, tgt in _METRIC.findall(s):
        metrics.append({"label": _txt(lbl), "current": _txt(cur),
                        "target": _txt(tgt or "")})
    if metrics:
        out["metrics"] = metrics

    miles = []
    for cls, done_when, label, target in _MILE.findall(s):
        m = {"label": _txt(label),
             "status": {"done": "done", "now": "now"}.get(cls, "planned"),
             "target": _txt(target)}
        if done_when:
            m["done_when"] = _unesc(done_when)
        miles.append(m)
    if miles:
        out["milestones"] = miles

    todos = []
    for doing, title, body in _ITEM.findall(s):
        tasks = []
        for label, chip in _TASK.findall(body):
            if not chip:
                continue          # the no-tasks placeholder row, not a task
            t = {"label": _txt(label), "done": chip == "done"}
            if chip == "doing":
                t["doing"] = True
            tasks.append(t)
        todos.append({"title": _txt(title),
                      "status": "in-progress" if doing else "open",
                      "tasks": tasks})
    for title, date, how in _SHIPPED.findall(s):
        t = {"title": _txt(title), "status": "done", "done_how": _txt(how)}
        if date:
            t["done_at"] = _txt(date)
        todos.append(t)
    if todos:
        out["todos"] = todos
    return out


def _page_links(site_dir, cid):
    """The charter page's byline states its linked domains outright
    ("works with X, Y"). An INDEPENDENT witness to the lane inversion."""
    path = os.path.join(site_dir, cid + ".html")
    if not os.path.exists(path):
        return None
    m = _BYLINE.search(open(path, encoding="utf-8").read())
    if not m:
        return None
    refs = _BY_LINK.findall(m.group(1))
    return set(refs[1:])          # refs[0] is the owner ("Owned by ...")


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def build_plan(parsed, home, tenant=TENANT, ts_base=None):
    """Turn the parsed export into exact file contents, without writing.

    The registry keeps ONE root. When the target already has one, the export's
    root is ALIASED onto it (renamed + described) rather than added beside it:
    two parentless domains is a broken registry — domain_path() calls both D0
    and every consumer picks whichever the filesystem yielded first.
    """
    domains_dir = os.path.join(home, "domains")
    charters_dir = os.path.join(home, "charters")
    existing = {}
    for fn in glob.glob(os.path.join(domains_dir, "*.json")):
        try:
            d = json.load(open(fn, encoding="utf-8"))
            if "ref" in d:
                existing[d["ref"]] = d
        except (ValueError, OSError):
            continue

    local_roots = [r for r, d in existing.items() if not d.get("parent_ref")]
    local_root = local_roots[0] if local_roots else None

    # Sibling ORDER is the D-path, and ordering is by (ts_minted_ms, ref).
    # Stamp a strictly increasing value in published chip order, and keep the
    # whole block BELOW any existing sibling so imported departments take
    # D1..D5 and anything already local keeps its place after them.
    oldest = min([d.get("ts_minted_ms", 0) for d in existing.values()] or [0])
    ts_base = ts_base if ts_base is not None else max(0, oldest - 10 ** 7)

    order, seq = [], [0]

    def walk(ref):
        for kid in parsed["kids"].get(ref, []):
            order.append(kid)
            walk(kid)

    walk("ROOT")

    # ONE root, always. When the target registry already has a parentless
    # domain the export's root is ALIASED onto it; when the target is empty the
    # export's root is created as a real domain. The failure this avoids is a
    # registry with two parentless nodes (domain_path() calls both D0) or with
    # none (every top-level department parented to the literal string "ROOT",
    # which resolves to nothing and makes the whole tree unrenderable).
    pub_root = _published_root(parsed)
    alias = {}
    new_domains, skipped_domains = [], []
    if local_root:
        alias["ROOT"] = local_root
        if pub_root:
            alias[pub_root] = local_root
    else:
        root_ref = pub_root or ("dref-" + E._sha({"import-root": parsed["root_name"]})[:16])
        alias["ROOT"] = root_ref
        if pub_root:
            alias[pub_root] = root_ref
        if root_ref not in existing:
            new_domains.append(_domain_doc(
                ref=root_ref, name=parsed["root_name"], parent_ref=None,
                description=parsed["root_desc"], tenant=tenant,
                ts=ts_base - 1))
        else:
            skipped_domains.append(root_ref)

    for i, ref in enumerate(order):
        if ref in existing:
            skipped_domains.append(ref)
            continue
        pa = parsed["parent"][ref]
        new_domains.append(_domain_doc(
            ref=ref, name=parsed["name"].get(ref, ""),
            parent_ref=alias.get(pa, pa),
            description=parsed["desc"].get(ref, ""),
            tenant=tenant, ts=ts_base + i))

    # the root: rename in place, never a second parentless node
    root_update = None
    if local_root and parsed["root_name"]:
        cur = existing[local_root]
        if cur.get("name") != parsed["root_name"] or \
                cur.get("description") != parsed["root_desc"]:
            root_update = {"ref": local_root, "name": parsed["root_name"],
                           "description": parsed["root_desc"],
                           "was_name": cur.get("name"),
                           "was_description": cur.get("description")}

    # charters: owners and links go through the same alias built above
    have = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(charters_dir, "*.json"))
            if not p.endswith(".page.json")}
    new_charters, skipped_charters = [], []
    for cid, c in sorted(parsed["charters"].items()):
        if cid in have:
            skipped_charters.append(cid)
            continue
        owner = alias.get(c["owner"], c["owner"])
        body = {
            "id": cid,
            "title": c["title"][:60],
            "domain_ref": owner,
            "purpose": c["purpose"],
            "scope_in": [], "scope_out": [],
            "obligations": [],
            "obligations_empty_reason":
                "imported from a published export: obligations are commitments "
                "and are never system-generated (ADR-028 Decision 5).",
            "invariants": [], "success_metrics": [], "constraints": [],
            "acl": [{"tenant_id": tenant, "access": "rw"}],
            "cutover_contract": None, "authority": {}, "termination": {},
            "tenant_id": tenant,
            "kind": c["kind"],
            "supersedes": None,
            "schema": E.CHARTER_SCHEMA,
            "id_not_content_addressed":
                "id is the PUBLISHED id. The export does not carry scope_in / "
                "scope_out / invariants, so this body cannot hash back to it. "
                "Id parity is preferred: every cross-link and page is keyed on it.",
        }
        sidecar = {"status": c["status"],
                   "artifacts": c["artifacts"],
                   "linked_domain_refs": [alias.get(r, r) for r in c["linked_domain_refs"]],
                   "goals": [], "metrics": [], "milestones": [], "todos": [],
                   "ts_ms": None,
                   "artifact_urls": c["artifact_urls"],
                   "import_source": "published-domains-export"}
        sidecar.update(parsed["extras"].get(cid, {}))
        new_charters.append((body, sidecar))

    return {"home": home, "local_root": local_root, "alias": alias,
            "ts_base": ts_base, "root_update": root_update,
            "domains": new_domains, "charters": new_charters,
            "skipped_domains": skipped_domains, "skipped_charters": skipped_charters}


def _domain_doc(ref, name, parent_ref, description, tenant, ts):
    """One domain record, in exactly the shape mint_domain() writes
    (placement_engine.py :365-384) plus `description` and `import_source`.

    `ts_minted_ms` is an IMPORT stamp, not a mint time — the export does not
    carry mint times, and this field is what domain_path() orders siblings by.
    Callers assign it in published order; `origin: "operator"` and
    `import_source` mark the record so it is never mistaken for a real mint.
    """
    return {
        "ref": ref,
        "name": name,
        "parent_ref": parent_ref,
        "description": description,
        "principles": [],
        "accountable": "tenant_owner",
        "authority": {},
        "tenant_id": tenant,
        "origin": "operator",
        "touched_by_operator": False,
        "mint_evidence": _evidence(name),
        "ts_minted_ms": ts,
        "status": "active",
        "successor_refs": [],
        "retired_at_ms": None,
        "retire_reason_code": None,
        "retire_note": None,
        "disposition_event_id": None,
        "import_source": "published-domains-export",
    }


def _published_root(parsed):
    """The export root's own ref: the owner of the rows rendered as 'here' on
    index.html — i.e. an owner that is not any page we parsed."""
    known = set(parsed["parent"])
    owners = {c["owner"] for c in parsed["charters"].values()}
    outside = sorted(owners - known)
    return outside[0] if len(outside) == 1 else None


def _evidence(name):
    toks = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t]
    return sorted(set(toks + ["imported"]))[:24]


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------

def backup(home):
    """tar.gz beside the registry. --apply refuses to proceed without one."""
    if not os.path.isdir(home):
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(os.path.dirname(os.path.abspath(home)),
                       "%s-backup-%s.tgz" % (os.path.basename(home.rstrip("/")), stamp))
    subprocess.check_call(["tar", "czf", out, "-C", os.path.dirname(os.path.abspath(home)),
                           os.path.basename(home.rstrip("/"))])
    return out


def apply_plan(plan):
    home = plan["home"]
    domains_dir = os.path.join(home, "domains")
    charters_dir = os.path.join(home, "charters")
    os.makedirs(domains_dir, exist_ok=True)
    os.makedirs(charters_dir, exist_ok=True)
    index = os.path.join(domains_dir, "INDEX.jsonl")

    wrote = {"domains": 0, "charters": 0, "sidecars": 0, "root_renamed": False}

    for d in plan["domains"]:
        path = os.path.join(domains_dir, d["ref"] + ".json")
        if os.path.exists(path):
            continue
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(d, fh, sort_keys=True, indent=2)
        wrote["domains"] += 1
        with open(index, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "domain_imported", "ref": d["ref"],
                                 "parent_ref": d["parent_ref"], "name": d["name"],
                                 "origin": d["origin"], "tenant_id": d["tenant_id"],
                                 "ts_ms": d["ts_minted_ms"],
                                 "source": "published-domains-export"},
                                sort_keys=True) + "\n")

    ru = plan["root_update"]
    if ru:
        path = os.path.join(domains_dir, ru["ref"] + ".json")
        doc = json.load(open(path, encoding="utf-8"))
        doc["name"] = ru["name"]
        doc["description"] = ru["description"]
        doc["touched_by_operator"] = True
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True, indent=2)
        wrote["root_renamed"] = True
        with open(index, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "domain_updated", "ref": ru["ref"],
                                 "name": ru["name"], "was_name": ru["was_name"],
                                 "source": "published-domains-export"},
                                sort_keys=True) + "\n")

    for body, sidecar in plan["charters"]:
        path = os.path.join(charters_dir, body["id"] + ".json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(body, fh, sort_keys=True, indent=2)
            wrote["charters"] += 1
        sc = os.path.join(charters_dir, body["id"] + ".page.json")
        if not os.path.exists(sc):
            with open(sc, "w", encoding="utf-8") as fh:
                json.dump(sidecar, fh, sort_keys=True, indent=2)
            wrote["sidecars"] += 1
    return wrote


# --------------------------------------------------------------------------
# report / cli
# --------------------------------------------------------------------------

def report(parsed, plan):
    p = parsed
    tops = p["kids"].get("ROOT", [])
    lines = [
        "export      : %d domains, %d charters, %d links"
        % (len(p["parent"]), len(p["charters"]),
           sum(len(c["linked_domain_refs"]) for c in p["charters"].values())),
        "registry    : %s" % plan["home"],
        "root        : %s  (local root %s %s)"
        % (p["root_name"], plan["local_root"],
           "renamed" if plan["root_update"] else "already matches"),
        "to write    : %d domains, %d charters (+%d sidecars)"
        % (len(plan["domains"]), len(plan["charters"]), len(plan["charters"])),
        "already there: %d domains, %d charters (left untouched)"
        % (len(plan["skipped_domains"]), len(plan["skipped_charters"])),
        "",
        "top-level departments, in the order the D-path will number them:",
    ]
    for i, r in enumerate(tops, 1):
        n = len(p["kids"].get(r, []))
        lines.append("  D%-3d %-26s %s" % (i, p["name"].get(r, ""),
                                           "%d sub" % n if n else ""))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export_dir")
    ap.add_argument("--home", default=os.environ.get("SUTRA_NATIVE_HOME")
                    or os.path.expanduser("~/.sutra-native/user-kit"))
    ap.add_argument("--tenant", default=TENANT)
    ap.add_argument("--apply", action="store_true",
                    help="back up, then write. Without it this is a dry run.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        parsed = parse_export(a.export_dir)
    except ImportError_ as e:
        print("org_import: %s" % e, file=sys.stderr)
        return 2
    plan = build_plan(parsed, a.home, tenant=a.tenant)

    if a.json:
        print(json.dumps({"domains": len(plan["domains"]),
                          "charters": len(plan["charters"]),
                          "skipped_domains": plan["skipped_domains"],
                          "skipped_charters": plan["skipped_charters"],
                          "root_update": plan["root_update"]}, indent=2))
    else:
        print(report(parsed, plan))

    if not a.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to write.")
        return 0

    b = backup(a.home)
    if os.path.isdir(a.home) and not b:
        print("org_import: backup failed; refusing to write", file=sys.stderr)
        return 3
    print("\nbackup      : %s" % (b or "(no existing registry to back up)"))
    wrote = apply_plan(plan)
    print("wrote       : %(domains)d domains, %(charters)d charters, "
          "%(sidecars)d sidecars" % wrote)
    if wrote["root_renamed"]:
        print("root renamed to %r" % parsed["root_name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
