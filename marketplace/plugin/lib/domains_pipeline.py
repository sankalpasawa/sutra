#!/usr/bin/env python3
"""domains_pipeline.py — the ENTIRE domains lifecycle as scripts (founder
2026-07-31: "not just past projects — the entire thing runs systematically").

One CLI, every stage idempotent, JSON out. The LLM's ONLY job between calls
is filling grounded skeletons; everything mechanical lives here. Wraps the
primitives that already ship (placement_engine, charters_seed, domains_page)
— no new ontology.

Stages (in order; each safe to re-run):
  init <company> [--tenant T]     ensure the root domain exists
  structure skeleton              template rows for departments (LLM fills)
  structure apply <f.json>        validate + mint departments (mint-only;
                                  restructure stays an explicit operator op)
  charters skeleton               rows for every domain WITHOUT a charter
  charters apply <f.json>         mint standing stubs (skip covered domains)
  projects discover|apply ...     delegates to charters_seed.py (same shapes)
  design show                     current D0 design tokens
  design set <f.json>             full token set + source required;
                                  prints previous -> new
  publish <site_dir> [--label L] [--commit]
                                  build zoom site + stamp (+ local commit);
                                  NEVER enables automation (consent boundary)
  autopublish on <site_dir> | off explicit consent for the auto-refresh hook
  status                          coverage dashboard

Exit nonzero only on malformed input/unreadable registry. Every apply prints
per-row outcomes (minted/skipped/rejected + reason) — codex fold 2026-07-31.
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import placement_engine as E  # noqa: E402

TOKEN_KEYS = ("bg", "card", "ink", "muted", "line", "accent", "accent_bg",
              "font", "source")


def _out(obj, code=0):
    print(json.dumps(obj, indent=2))
    return code


def _root_dom(domains):
    for r, d in domains.items():
        if d.get("parent_ref") is None:
            return r
    return None


def _by_name(domains):
    m = {}
    for ref, d in domains.items():
        m.setdefault(d["name"].strip().lower(), []).append(ref)
    return m


def _resolve(spec, domains, by_name):
    spec = (spec or "").strip()
    if spec in domains:
        return spec, None
    if ">" in spec:
        names = [s.strip().lower() for s in spec.split(">") if s.strip()]
        hits = []
        for ref in domains:
            chain, cur, seen = [], ref, set()
            while cur in domains and cur not in seen:
                seen.add(cur)
                chain.append(domains[cur]["name"].strip().lower())
                cur = domains[cur].get("parent_ref")
            chain.reverse()
            if chain == names or (len(chain) >= len(names)
                                  and chain[-len(names):] == names):
                hits.append(ref)
        return (hits[0], None) if len(hits) == 1 else \
            (None, "path '%s' resolved to %d domains" % (spec, len(hits)))
    hits = by_name.get(spec.lower(), [])
    return (hits[0], None) if len(hits) == 1 else \
        (None, "name '%s' resolved to %d domains" % (spec, len(hits)))


def _set_field(ref, **fields):
    """Route through the engine's single locked domain write path (§9 Phase 0).

    This was an UNLOCKED json.load / json.dump pair: it raced every concurrent
    restructure (both read, both write, second clobbers first — the exact
    lost-update the flocks at placement_engine.py exist to prevent) and left no
    audit row. `set_domain_fields` takes _lock('RESTRUCTURE') and appends
    `domain_updated {ref, before, after, ts_ms}` with the changed fields only.
    """
    return E.set_domain_fields(ref, **fields)


# ---------------------------------------------------------------- stages ----

def init(company, tenant):
    domains = E.load_domains()
    root = _root_dom(domains)
    if root:
        return _out({"stage": "init", "result": "exists",
                     "root": root, "name": domains[root]["name"]})
    ref, created = E.mint_domain(None, company, [company.lower()], tenant,
                                 origin="operator")
    _set_field(ref, touched_by_operator=True)
    return _out({"stage": "init", "result": "minted", "root": ref,
                 "name": company})


def structure_skeleton():
    domains = E.load_domains()
    tree = []
    for ref, d in sorted(domains.items(), key=lambda t: t[1].get("ts_minted_ms", 0)):
        tree.append({"ref": ref, "name": d["name"],
                     "parent_ref": d.get("parent_ref"),
                     "description": d.get("description", "")})
    row = {"name": "<1-40 chars, business-form (like a real org chart), "
                   "sibling-unique>",
           "parent": "<dref | full path 'A > B' | unique name>",
           "description": "<one line, what this department owns>"}
    return _out({"stage": "structure", "existing": tree, "rows": [row]})


def structure_apply(path, tenant):
    try:
        data = json.load(open(path))
    except (ValueError, OSError) as e:
        return _out({"error": "unreadable: %s" % e}, 2)
    rows = data.get("rows", data) if isinstance(data, dict) else data
    domains = E.load_domains()
    by_name = _by_name(domains)
    outcomes = []
    minted = 0
    for i, r in enumerate(rows):
        name = str(r.get("name") or "").strip()
        desc = str(r.get("description") or "").strip()
        if not (1 <= len(name) <= 40):
            outcomes.append({"row": i, "name": name, "outcome": "rejected",
                             "reason": "name must be 1-40 chars"})
            continue
        parent, err = _resolve(r.get("parent"), domains, by_name)
        if not parent:
            outcomes.append({"row": i, "name": name, "outcome": "rejected",
                             "reason": "parent: %s" % err})
            continue
        # MECE floor: engine mint is idempotent on (parent, name) — an
        # existing sibling of the same name returns its ref, no duplicate.
        # ORG-016: mint refuses a frozen/retired parent (§9 Phase 0). That is a
        # per-row rejection here, not a crash — this stage reports outcomes.
        try:
            ref, created = E.mint_domain(parent, name, [desc or name.lower()],
                                         tenant, origin="operator")
        except ValueError as e:
            outcomes.append({"row": i, "name": name, "outcome": "rejected",
                             "reason": str(e)})
            continue
        fields = {"touched_by_operator": True}
        if desc:
            fields["description"] = desc
        _set_field(ref, **fields)
        minted += 1 if created else 0
        outcomes.append({"row": i, "name": name, "ref": ref,
                         "outcome": "minted" if created else "existing"})
        domains = E.load_domains()
        by_name = _by_name(domains)
    return _out({"stage": "structure", "minted": minted, "outcomes": outcomes})


def charters_skeleton():
    domains = E.load_domains()
    uncovered = [ref for ref in domains if not E.charters_for(ref)]
    rows = [{"domain": ref, "domain_name": domains[ref]["name"],
             "title": "<charter title, <=60 chars>",
             "purpose": "<one sentence: the department's standing promise>"}
            for ref in uncovered]
    return _out({"stage": "charters", "uncovered": len(uncovered), "rows": rows})


def charters_apply(path, tenant):
    try:
        data = json.load(open(path))
    except (ValueError, OSError) as e:
        return _out({"error": "unreadable: %s" % e}, 2)
    rows = data.get("rows", data) if isinstance(data, dict) else data
    domains = E.load_domains()
    by_name = _by_name(domains)
    outcomes = []
    minted = 0
    for i, r in enumerate(rows):
        ref, err = _resolve(r.get("domain") or r.get("domain_name"),
                            domains, by_name)
        title = str(r.get("title") or "").strip()
        purpose = str(r.get("purpose") or "").strip()
        if not ref:
            outcomes.append({"row": i, "outcome": "rejected",
                             "reason": "domain: %s" % err})
            continue
        if not (1 <= len(title) <= 60) or not purpose or title.startswith("<"):
            outcomes.append({"row": i, "outcome": "rejected",
                             "reason": "title/purpose required (no templates)"})
            continue
        if E.charters_for(ref):
            outcomes.append({"row": i, "domain": ref, "outcome": "skipped",
                             "reason": "already has a charter"})
            continue
        import charters_seed as CS
        warn = []
        extras = CS.validate_extras(r, warn, "row[%d]" % i)
        # ONE mint over the FULL body (§0.13): extras are operator-mutable and
        # go to charters/<C-id>.page.json. Reopening the C-<hash> file to write
        # todos back meant every todo tick changed the charter's identity.
        E.mint_charter_stub(ref, title, purpose, [], [], tenant, extras=extras)
        minted += 1
        o = {"row": i, "domain": ref, "outcome": "minted"}
        if warn:
            o["warnings"] = warn
        outcomes.append(o)
    return _out({"stage": "charters", "minted": minted, "outcomes": outcomes})


def design_show():
    domains = E.load_domains()
    root = _root_dom(domains)
    return _out({"stage": "design", "root": root,
                 "design": (domains.get(root) or {}).get("design") or None})


def design_set(path):
    try:
        tok = json.load(open(path))
    except (ValueError, OSError) as e:
        return _out({"error": "unreadable: %s" % e}, 2)
    missing = [k for k in TOKEN_KEYS if not str(tok.get(k) or "").strip()]
    if missing:
        return _out({"error": "design set requires ALL tokens + source; "
                              "missing: %s" % missing}, 2)
    domains = E.load_domains()
    root = _root_dom(domains)
    prev = (domains.get(root) or {}).get("design")
    _set_field(root, design={k: tok[k] for k in TOKEN_KEYS})
    return _out({"stage": "design", "result": "set", "previous": prev,
                 "new": {k: tok[k] for k in TOKEN_KEYS}})


def publish(site_dir, label, commit, tenant="T-local"):
    import domains_page as P
    # §6: the publish input set is ONE tenant's. Passed explicitly rather than
    # left to the env var, so the pipeline's --tenant is what governs the
    # public artifact.
    n = P.build_site(site_dir, label=label, tenant_id=tenant)
    # stamp = the auto-refresh fingerprint (same recipe as the hook)
    import hashlib
    h = hashlib.sha256()
    kit = E.HOME
    try:
        h.update(open(os.path.join(kit, "domains", "INDEX.jsonl"), "rb").read())
    except OSError:
        pass
    for sub in ("domains", "charters"):
        d = os.path.join(kit, sub)
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                h.update(open(os.path.join(d, fn), "rb").read())
    open(os.path.join(site_dir, ".registry-stamp"), "w").write(h.hexdigest() + "\n")
    committed = False
    if commit:
        try:
            repo = subprocess.check_output(
                ["git", "-C", site_dir, "rev-parse", "--show-toplevel"],
                text=True, stderr=subprocess.DEVNULL).strip()
            subprocess.run(["git", "-C", repo, "add", "-A", "--",
                            os.path.abspath(site_dir)], check=False)
            r = subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                                "chore(domains): pipeline publish"], check=False)
            committed = r.returncode == 0
        except Exception:
            pass
    # Consent boundary (codex): publish NEVER writes the autopublish opt-in.
    return _out({"stage": "publish", "pages": n, "site_dir": site_dir,
                 "committed": committed,
                 "note": "auto-refresh stays OFF until 'autopublish on' is "
                         "run explicitly"})


def autopublish(mode, site_dir=None, label="Departments", tenant="T-local"):
    root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True).strip()
    cfg = os.path.join(root, ".claude", "domains-autopublish")
    if mode == "off":
        if os.path.exists(cfg):
            os.remove(cfg)
        return _out({"stage": "autopublish", "result": "off"})
    if not site_dir:
        return _out({"error": "autopublish on requires <site_dir>"}, 2)
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    rel = os.path.relpath(os.path.abspath(site_dir), root)
    # TENANT is pinned AT CONSENT TIME (§6): the operator consents to publishing
    # ONE tenant's registry, and the hook must not silently widen that later by
    # picking up a different PLACEMENT_TENANT from some other session's env.
    open(cfg, "w").write("SITE_DIR=%s\nLABEL=%s\nTENANT=%s\n" % (rel, label, tenant))
    return _out({"stage": "autopublish", "result": "on", "site_dir": rel,
                 "tenant": tenant})


def status():
    domains = E.load_domains()
    root = _root_dom(domains)
    ch_all = []
    # BODIES only. `charters/<C-id>.page.json` sidecars also end in `.json`
    # (§2.2), so the old listdir loop double-counted every charter, inflated
    # `standing` by one per sidecar (no `kind` -> the "standing" default) and
    # put a None in `covered` from each sidecar's absent `domain_ref`. Every
    # other consumer already moved to charter_body_files(); this one had not.
    for fn in E.charter_body_files():
        try:
            ch_all.append(json.load(open(os.path.join(E.CHARTERS, fn))))
        except (ValueError, OSError):
            pass
    covered = {c.get("domain_ref") for c in ch_all}
    # Coverage is a LIVE-tree question (I-D5): a tombstone with no description
    # is not a gap the operator can close, and reporting it as one never clears.
    live = E.live_refs(domains)
    no_desc = [live[r]["name"] for r in live if not live[r].get("description")]
    no_charter = [live[r]["name"] for r in live if r not in covered]
    return _out({"stage": "status",
                 "domains": len(domains),
                 "domains_live": len(live),
                 "charters": {"total": len(ch_all),
                              "standing": sum(1 for c in ch_all
                                              if c.get("kind", "standing") == "standing"),
                              "project": sum(1 for c in ch_all
                                             if c.get("kind") == "project")},
                 "coverage": {"domains_without_description": no_desc,
                              "domains_without_charter": no_charter},
                 "design_set": bool((domains.get(root) or {}).get("design"))})


if __name__ == "__main__":
    a = sys.argv[1:]
    tenant = os.environ.get("SUTRA_TENANT", "T-local")
    if "--tenant" in a:
        i = a.index("--tenant")
        tenant = a[i + 1]
        del a[i:i + 2]
    try:
        if a[:1] == ["init"] and len(a) > 1:
            sys.exit(init(a[1], tenant))
        if a[:2] == ["structure", "skeleton"]:
            sys.exit(structure_skeleton())
        if a[:2] == ["structure", "apply"] and len(a) > 2:
            sys.exit(structure_apply(a[2], tenant))
        if a[:2] == ["charters", "skeleton"]:
            sys.exit(charters_skeleton())
        if a[:2] == ["charters", "apply"] and len(a) > 2:
            sys.exit(charters_apply(a[2], tenant))
        if a[:1] == ["projects"]:
            # normalized delegation (codex): same exit + JSON shape
            r = subprocess.run([sys.executable,
                                os.path.join(_HERE, "charters_seed.py")] + a[1:]
                               + ["--tenant", tenant])
            sys.exit(r.returncode)
        if a[:2] == ["design", "show"]:
            sys.exit(design_show())
        if a[:2] == ["design", "set"] and len(a) > 2:
            sys.exit(design_set(a[2]))
        if a[:1] == ["publish"] and len(a) > 1:
            label = a[a.index("--label") + 1] if "--label" in a else "Departments"
            sys.exit(publish(a[1], label, "--commit" in a, tenant))
        if a[:2] == ["autopublish", "on"] and len(a) > 2:
            label = a[a.index("--label") + 1] if "--label" in a else "Departments"
            sys.exit(autopublish("on", a[2], label, tenant))
        if a[:2] == ["autopublish", "off"]:
            sys.exit(autopublish("off"))
        if a[:1] == ["status"]:
            sys.exit(status())
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(2)
    print(__doc__)
    sys.exit(2)
