#!/usr/bin/env python3
"""charters_seed.py — fleet CLI: mine a client's past projects into charters.

The deterministic half of the mining flow (founder 2026-07-31). The session
LLM reads documents and fills candidate rows (grounding rules live in the
domains skill); THIS script owns everything mechanical: source discovery,
validation, resolution, idempotent minting, reporting. It never calls an
LLM, never deletes, never invents — a row without real evidence is rejected
(codex consult 2026-07-31: grounding floor).

Usage:
  charters_seed.py discover [root]            # scan repo -> sources + row skeletons (JSON to stdout)
  charters_seed.py apply <candidates.json>    # validate + mint; report JSON to stdout
      [--tenant T]                            # default $SUTRA_TENANT or T-local

Candidate row schema (LLM fills; script validates):
  {"title": "<1-60 chars>", "purpose": "<one sentence from the docs>",
   "status": "active|shipped|retired|paused",          # no default — reject if absent
   "owner_domain": "<dref | full path 'A > B > C' | unique domain name>",
   "linked": ["<same forms>"],                          # dropped with a warning if unresolvable
   "artifacts": ["<repo-relative, git-tracked>"],       # >=1 must survive validation
   "source": "<where this came from>"}                  # provenance, informational

apply semantics: existing same-title charter under the same owner -> SKIP
(strict idempotency; no silent updates — re-classification on re-run is a
risk, not a feature). Exit nonzero ONLY on malformed input / unreadable
registry; validation failures are report rows, not crashes.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import placement_engine as E  # noqa: E402

SRC_PAT = re.compile(
    r"(^|/)(plans?|decisions?|adrs?|rfcs?|architecture|evolution|roadmaps?"
    r"|postmortems?|changelog)", re.I)
STATUSES = {"active", "shipped", "retired", "paused"}


def _root(argroot=None):
    r = argroot or os.getcwd()
    try:
        return subprocess.check_output(
            ["git", "-C", r, "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return os.path.abspath(r)


def _tracked(root):
    out = set()

    def ls(d, pre=""):
        try:
            for ln in subprocess.check_output(
                    ["git", "-C", d, "ls-files"],
                    text=True, stderr=subprocess.DEVNULL).splitlines():
                if ln:
                    out.add(pre + ln)
        except Exception:
            pass

    ls(root)
    try:
        for ln in subprocess.check_output(
                ["git", "-C", root, "submodule", "status"],
                text=True, stderr=subprocess.DEVNULL).splitlines():
            parts = ln.split()
            if len(parts) > 1:
                ls(os.path.join(root, parts[1]), parts[1] + "/")
    except Exception:
        pass
    return out


def discover(argroot=None):
    root = _root(argroot)
    tracked = _tracked(root)
    buckets = {}
    for t in tracked:
        if not SRC_PAT.search(t):
            continue
        d = os.path.dirname(t)
        key = d if d and SRC_PAT.search(d) else t
        buckets[key] = buckets.get(key, 0) + 1
    sources = [{"path": k, "kind": "dir" if n > 1 else "file", "files": n}
               for k, n in sorted(buckets.items())]
    # One skeleton row PER SOURCE (codex: cardinality must be explicit) —
    # the LLM may split a source into several rows or drop it entirely.
    row = {"title": "", "purpose": "",
           "status": "active|shipped|retired|paused",
           "owner_domain": "<dref | full path 'A > B > C' | unique name>",
           "linked": [], "artifacts": [], "source": ""}
    print(json.dumps({"root": root, "sources": sources,
                      "rows": [dict(row, source=s["path"]) for s in sources]},
                     indent=2))
    return 0


def _resolve_domain(spec, domains, by_name, tenant):
    """dref -> exact full path -> unique leaf name; tenant-preferred."""
    spec = (spec or "").strip()
    if not spec:
        return None, "empty domain spec"
    if spec in domains:
        return spec, None
    if ">" in spec:
        names = [s.strip().lower() for s in spec.split(">") if s.strip()]
        hits = []
        for ref, d in domains.items():
            chain, cur, seen = [], ref, set()
            while cur in domains and cur not in seen:
                seen.add(cur)
                chain.append(domains[cur]["name"].strip().lower())
                cur = domains[cur].get("parent_ref")
            chain.reverse()
            if chain == names or (len(chain) >= len(names)
                                  and chain[-len(names):] == names):
                hits.append(ref)
        if len(hits) == 1:
            return hits[0], None
        return None, ("path '%s' %s" % (spec, "matched no domain" if not hits
                                        else "ambiguous (%d matches)" % len(hits)))
    hits = by_name.get(spec.lower(), [])
    if tenant and len(hits) > 1:
        th = [h for h in hits if domains[h].get("tenant_id") == tenant]
        if len(th) == 1:
            return th[0], None
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, "name '%s' matched no domain" % spec
    return None, ("name '%s' ambiguous (%d: %s) — use a dref or full path"
                  % (spec, len(hits), ", ".join(hits[:4])))


def apply_file(path, tenant):
    try:
        data = json.load(open(path))
    except (ValueError, OSError) as e:
        print(json.dumps({"error": "unreadable candidates file: %s" % e}))
        return 2
    rows = data.get("rows", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        print(json.dumps({"error": "candidates must be a list or {rows:[...]}"}))
        return 2
    root = _root()
    tracked = _tracked(root)
    domains = E.load_domains()
    by_name = {}
    for ref, d in domains.items():
        by_name.setdefault(d["name"].strip().lower(), []).append(ref)
    minted = skipped = rejected = 0
    warnings = []
    for i, r in enumerate(rows):
        tag = "row[%d] %s" % (i, str(r.get("title") or "?")[:40])
        title = str(r.get("title") or "").strip()
        purpose = str(r.get("purpose") or "").strip()
        status = str(r.get("status") or "").strip()
        if not (1 <= len(title) <= 60) or not purpose or status not in STATUSES:
            warnings.append(tag + ": REJECTED (title 1-60 / purpose / status "
                            "in %s required, no defaults)" % sorted(STATUSES))
            rejected += 1
            continue
        owner, err = _resolve_domain(r.get("owner_domain"), domains, by_name, tenant)
        if not owner:
            warnings.append(tag + ": REJECTED (owner: %s)" % err)
            rejected += 1
            continue
        links = []
        for l in r.get("linked") or []:
            lr, lerr = _resolve_domain(l, domains, by_name, tenant)
            if lr and lr != owner and lr not in links:
                links.append(lr)
            elif lerr:
                warnings.append(tag + ": link dropped (%s)" % lerr)
        arts = []
        for a in r.get("artifacts") or []:
            a = str(a).strip()
            if a.startswith("./"):
                a = a[2:]
            if ".." in a.split("/") or os.path.isabs(a):
                warnings.append(tag + ": artifact dropped (absolute/traversal): " + a)
                continue
            if a in tracked or any(t.startswith(a.rstrip("/") + "/") for t in tracked):
                arts.append(a)
            else:
                warnings.append(tag + ": artifact dropped (not git-tracked): " + a)
        if not arts:
            warnings.append(tag + ": REJECTED (no valid artifacts — every row "
                            "must cite real evidence)")
            rejected += 1
            continue
        existing = {c.get("title", "").strip().lower() for c in E.charters_for(owner)}
        if title.lower() in existing:
            skipped += 1
            continue
        E.mint_charter_stub(owner, title, purpose, arts[:10], [], tenant)
        for c in E.charters_for(owner):
            if c.get("title", "").strip().lower() == title.lower():
                fp = os.path.join(E.CHARTERS, c["id"] + ".json")
                c2 = json.load(open(fp))
                c2["kind"] = "project"
                c2["status"] = status
                c2["linked_domain_refs"] = links
                c2["artifacts"] = arts
                json.dump(c2, open(fp, "w"), sort_keys=True, indent=2)
                break
        minted += 1
    print(json.dumps({"minted": minted, "skipped_existing": skipped,
                      "rejected": rejected, "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    tenant = os.environ.get("SUTRA_TENANT", "T-local")
    if "--tenant" in args:
        i = args.index("--tenant")
        tenant = args[i + 1]
        del args[i:i + 2]
    if args[:1] == ["discover"]:
        sys.exit(discover(args[1] if len(args) > 1 else None))
    if args[:1] == ["apply"] and len(args) > 1:
        sys.exit(apply_file(args[1], tenant))
    print(__doc__)
    sys.exit(2)
