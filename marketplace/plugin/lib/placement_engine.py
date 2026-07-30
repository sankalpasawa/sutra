#!/usr/bin/env python3
"""placement_engine.py — the ADR-028 placement engine.

Registry, classifier, restructure and MECE reporting for work placement.
Canon: sutra/os/decisions/ADR-028-mandatory-work-placement.md
       sutra/os/native/primitives/placement.md  (I-P1 .. I-P10)
       sutra/os/native/primitives/domain.md     (I-D1 .. I-D4)

Storage layout (SUTRA_NATIVE_HOME, default ~/.sutra-native/user-kit):
    domains/<ref>.json          stable opaque ref, assigned once, NEVER changes
    domains/INDEX.jsonl         APPEND-ONLY (see note 3)
    domains/<ref>.lock          flock target for atomic mint
    charters/C-<sha>.json       content-addressed, immutable
    placements/PL-<sha>.json    content-addressed, append-only
    placements/CURRENT.jsonl    APPEND-ONLY log, read tail-first

Peer-review folds (deepseek consult 2026-07-29, CHANGES-REQUIRED):

 1. flock(2), NOT O_EXCL lockfiles [P1]. An O_EXCL lock left behind by a
    crashed agent is indistinguishable from a live one, and would deadlock all
    minting under that parent until someone deleted it by hand. flock is
    released by the kernel when the fd closes or the process dies, so a crash
    cannot wedge the registry.

 2. Placement ids carry a per-process sequence nonce [P1]. Content-addressing
    alone means an identical re-placement collides to the same id and silently
    fails to record that a re-evaluation happened. ts_ms was already in the
    canonical form, but two events inside the same millisecond would still
    collide. `seq` closes that.

 3. INDEX.jsonl and CURRENT.jsonl are APPEND-ONLY, read tail-first [P1].
    A rewritten pointer file loses updates under concurrent writers (both read,
    both write, second clobbers first) and can be read torn mid-write. Appends
    of a single line under PIPE_BUF are atomic on POSIX.

 4. Adjacent placements DOMINATE the classifier score [P2]. If a file already
    has a placement, that is far stronger evidence than any term overlap. It is
    weighted an order of magnitude above the lexical signals rather than
    averaged in with them.
"""

import fcntl
import hashlib
import json
import os
import re
import sys
import time
from contextlib import contextmanager

# ---------------------------------------------------------------- config ----

HOME = os.environ.get("SUTRA_NATIVE_HOME") or os.path.expanduser("~/.sutra-native/user-kit")
DOMAINS = os.path.join(HOME, "domains")
CHARTERS = os.path.join(HOME, "charters")
PLACEMENTS = os.path.join(HOME, "placements")
CURRENT = os.path.join(PLACEMENTS, "CURRENT.jsonl")
DOMAIN_INDEX = os.path.join(DOMAINS, "INDEX.jsonl")

#: Set from measurement, not taste (OQ-028-2). Against a 46-domain registry
#: derived from the real plugin tree:
#:   path evidence, correct answer ...... 0.70 - 0.99   (4/4 correct)
#:   utterance only, correct answer ..... 0.49
#:   utterance only, WRONG answer ....... 0.40   ("gate" matching "Readability Gate")
#: 0.45 sits in the gap: path-backed work resolves, and a lone shared word
#: floor-holds at the ancestor instead of confidently asserting nonsense.
CONFIDENCE_FLOOR = float(os.environ.get("PLACEMENT_CONFIDENCE_FLOOR", "0.45"))
AUTO_MERGE_THRESHOLD = float(os.environ.get("PLACEMENT_AUTO_MERGE", "0.85"))

_SEQ = [0]  # per-process nonce; see fold 2


def _now_ms():
    return int(time.time() * 1000)


def _ensure_dirs():
    for d in (DOMAINS, CHARTERS, PLACEMENTS):
        os.makedirs(d, exist_ok=True)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(obj):
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _append_jsonl(path, row):
    """Single-line append. POSIX guarantees atomicity below PIPE_BUF."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # torn tail line — ignore, never crash a read
    return out


@contextmanager
def _lock(name):
    """flock-based mutex. Kernel releases on process death (fold 1)."""
    os.makedirs(DOMAINS, exist_ok=True)
    path = os.path.join(DOMAINS, "%s.lock" % re.sub(r"[^A-Za-z0-9_.-]", "_", name))
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


# ---------------------------------------------------------------- domains ---

def load_domains():
    """ref -> domain dict. Reads the per-domain files (the authority)."""
    _ensure_dirs()
    out = {}
    for fn in os.listdir(DOMAINS):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DOMAINS, fn), "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if "ref" in d:
                out[d["ref"]] = d
        except (ValueError, OSError):
            continue
    return out


def domain_path(ref, domains=None):
    """Derive the positional D-path by walking parent_ref (I-D1: display only)."""
    domains = domains if domains is not None else load_domains()
    chain, seen = [], set()
    cur = ref
    while cur and cur in domains and cur not in seen:
        seen.add(cur)
        chain.append(domains[cur])
        cur = domains[cur].get("parent_ref")
    chain.reverse()
    # Root renders as D0; its descendants do NOT carry a "D0." prefix, so the
    # tree reads D0 > D3 > D3.D2 > D3.D2.D7 exactly as canon and the docs show.
    parts = []
    for node in chain:
        parent = node.get("parent_ref")
        if parent is None:
            parts.append("D0")
            continue
        sibs = sorted(
            [r for r, d in domains.items() if d.get("parent_ref") == parent],
            key=lambda r: (domains[r].get("ts_minted_ms", 0), r),
        )
        idx = sibs.index(node["ref"]) + 1 if node["ref"] in sibs else 1
        parts.append("D%d" % idx)
    if len(parts) > 1 and parts[0] == "D0":
        parts = parts[1:]                     # drop the root prefix
    return ".".join(parts) if parts else "D0"


def ancestor_chain(ref, domains=None):
    domains = domains if domains is not None else load_domains()
    chain, seen, cur = [], set(), ref
    while cur and cur in domains and cur not in seen:
        seen.add(cur)
        chain.append(domains[cur])
        cur = domains[cur].get("parent_ref")
    chain.reverse()
    out = []
    for node in chain:
        out.append({
            "ref": node["ref"],
            "path": domain_path(node["ref"], domains),
            "name": node.get("name", ""),
            "is_new": False,
        })
    return out


def mint_domain(parent_ref, name, evidence, tenant_id, origin="system-minted"):
    """Atomic check-then-insert under the parent (I-D2 / I-P10).

    Returns (ref, created_bool). A concurrent loser adopts the winner's ref.
    """
    _ensure_dirs()
    lock_name = parent_ref if parent_ref else "ROOT"
    with _lock(lock_name):
        domains = load_domains()
        # re-check under the lock: did a peer already mint an equivalent sibling?
        norm = name.strip().lower()
        for ref, d in domains.items():
            if d.get("parent_ref") == parent_ref and d.get("name", "").strip().lower() == norm:
                return ref, False
        # I-D4 (codex F7.1): a system-minted Domain must carry non-empty
        # mint_evidence — unauditable authority otherwise. Derive from the name
        # as a floor rather than rejecting (rejecting would break I-P3).
        evidence = [e for e in (evidence or []) if e] or [norm]
        ref = "dref-" + _sha({"p": parent_ref, "n": norm, "t": tenant_id, "ts": _now_ms(),
                              "seq": _SEQ[0], "pid": os.getpid()})[:16]
        _SEQ[0] += 1
        doc = {
            "ref": ref,
            "name": name,
            "parent_ref": parent_ref,
            "principles": [],
            "accountable": "tenant_owner",
            "authority": {},
            "tenant_id": tenant_id,
            "origin": origin,
            "touched_by_operator": False,
            "mint_evidence": sorted(set(evidence))[:24],
            "ts_minted_ms": _now_ms(),
        }
        with open(os.path.join(DOMAINS, ref + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True, indent=2)
        _append_jsonl(DOMAIN_INDEX, {"event": "domain_minted", "ref": ref,
                                     "parent_ref": parent_ref, "name": name,
                                     "origin": origin, "tenant_id": tenant_id,
                                     "ts_ms": doc["ts_minted_ms"]})
        return ref, True


# --------------------------------------------------------------- charters ---

def charters_for(domain_ref):
    _ensure_dirs()
    out = []
    for fn in os.listdir(CHARTERS):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHARTERS, fn), "r", encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("domain_ref") == domain_ref:
                out.append(c)
        except (ValueError, OSError):
            continue
    return out


def mint_charter_stub(domain_ref, title, purpose, scope_in, scope_out, tenant_id):
    """Descriptive fields only. obligations stays EMPTY with a stated reason —
    the system never fabricates promises the operator did not make
    (ADR-028 Decision 5; satisfies Charter invariant I-2)."""
    _ensure_dirs()
    body = {
        "title": title[:60],
        "domain_ref": domain_ref,
        "purpose": purpose,
        "scope_in": scope_in,
        "scope_out": scope_out,
        "obligations": [],
        "obligations_empty_reason":
            "auto-minted stub: obligations are commitments and are never "
            "system-generated (ADR-028 Decision 5). Fill via B20 or by hand.",
        "invariants": [], "success_metrics": [], "constraints": [],
        "acl": [{"tenant_id": tenant_id, "access": "rw"}],
        "cutover_contract": None, "authority": {}, "termination": {},
        "tenant_id": tenant_id,
    }
    cid = "C-" + _sha(body)[:16]
    body["id"] = cid
    path = os.path.join(CHARTERS, cid + ".json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh, sort_keys=True, indent=2)
    return cid


# ------------------------------------------------------------- placements ---

def current_placement(work_ref_id):
    """Tail-first scan of the append-only CURRENT log (fold 3)."""
    rows = _read_jsonl(CURRENT)
    for row in reversed(rows):
        if row.get("work_ref_id") == work_ref_id:
            return row.get("placement_id")
    return None


def all_placements():
    _ensure_dirs()
    out = []
    for fn in os.listdir(PLACEMENTS):
        if not (fn.startswith("PL-") and fn.endswith(".json")):
            continue
        try:
            with open(os.path.join(PLACEMENTS, fn), "r", encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (ValueError, OSError):
            continue
    return out


def write_placement(work_ref, domain_ref, charter_id, origin, confidence,
                    created, tenant_id, supersedes=None, phase="pre-flight"):
    """Durable placement write.

    Codex F7.1 folds (2026-07-30):
    - I-P2 enforced AT THE WRITE BOUNDARY: domain_ref and charter_id must
      resolve or the write is a hard reject. Callers behaving is not an
      invariant; the primitive refusing bad refs is.
    - flock around the supersede-check + write so two processes resolving the
      same new work cannot both land unsuperseded "current" rows (I-P5).
    - id body carries os.getpid(): _SEQ alone is per-process, so two processes
      could still collide inside one millisecond with identical content.
    """
    _ensure_dirs()
    domains = load_domains()
    if domain_ref not in domains:
        raise ValueError("I-P2 reject: domain_ref %r does not resolve" % domain_ref)
    if not charter_id or not os.path.exists(os.path.join(CHARTERS, charter_id + ".json")):
        raise ValueError("I-P2 reject: charter_id %r does not resolve" % charter_id)

    with _lock("CURRENT"):
        prior = current_placement(work_ref.get("id"))
        if supersedes is None and prior:
            supersedes = prior          # never leave two unsuperseded currents
        _SEQ[0] += 1
        body = {
            "work_ref": work_ref,
            "domain_ref": domain_ref,
            "charter_id": charter_id,
            "origin": origin,
            "confidence": round(float(confidence), 4),
            "created": created,
            "supersedes": supersedes,
            "phase": phase,
            "tenant_id": tenant_id,
            "ts_ms": _now_ms(),
            "seq": _SEQ[0],
            "pid": os.getpid(),      # process-unique component of the id hash
        }
        pid_ = "PL-" + _sha(body)[:16]
        body["id"] = pid_
        with open(os.path.join(PLACEMENTS, pid_ + ".json"), "w", encoding="utf-8") as fh:
            json.dump(body, fh, sort_keys=True, indent=2)
        _append_jsonl(CURRENT, {"work_ref_id": work_ref.get("id"),
                                "work_ref_kind": work_ref.get("kind"),
                                "tenant_id": tenant_id,
                                "placement_id": pid_, "domain_ref": domain_ref,
                                "ts_ms": body["ts_ms"]})
    return body


# ------------------------------------------------------------- classifier ---

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_STOP = {"the", "and", "for", "with", "this", "that", "from", "into", "src",
         "lib", "test", "tests", "index", "main", "app", "new", "get", "set",
         "add", "use", "run", "let", "not", "are", "was", "has", "have", "you"}


def tokenize(*chunks):
    toks = set()
    for c in chunks:
        if not c:
            continue
        for m in _TOKEN.finditer(str(c).replace("/", " ").replace("-", " ").replace("_", " ").replace(".", " ")):
            t = m.group(0).lower()
            if t not in _STOP and not t.isdigit():
                toks.add(t)
    return toks


def gather_evidence(utterance="", paths=None, artifacts=None):
    paths = paths or []
    artifacts = artifacts or []
    return {
        "terms": tokenize(utterance),
        "paths": list(paths),
        "path_terms": tokenize(*paths),
        "artifacts": list(artifacts),
        "artifact_terms": tokenize(*artifacts),
    }


def _norm_path(p):
    """Absolute, symlink-resolved. Callers pass a mix of absolute and repo-
    relative paths; comparing them as raw strings means the adjacency signal —
    the strongest one we have — silently never fires. Observed live: a real file
    path scored as though it were unseen because the registry held it absolute
    and the query passed it relative."""
    if not p:
        return ""
    try:
        return os.path.realpath(os.path.abspath(os.path.expanduser(p)))
    except OSError:
        return p


def _adjacent_domain_votes(paths):
    """Strongest signal (fold 4): what domain do neighbouring files already
    resolve to? Weighted an order of magnitude above lexical overlap."""
    if not paths:
        return {}
    norm = {_norm_path(p) for p in paths if p}
    dirs = {os.path.dirname(p) for p in norm if p}
    tails = {os.sep.join(p.split(os.sep)[-2:]) for p in norm if p}
    # Codex F7.1 fold: CURRENT is append-only history — a re-placed file has
    # many rows. Voting over ALL of them let stale (superseded) placements
    # outvote the current one. Last row per work_ref wins; only currents vote.
    latest = {}
    for row in _read_jsonl(CURRENT):
        raw = row.get("work_ref_id") or ""
        if raw and row.get("domain_ref"):
            latest[raw] = row["domain_ref"]
    votes = {}
    for raw, ref in latest.items():
        wid = _norm_path(raw)
        if wid in norm:
            votes[ref] = votes.get(ref, 0) + 10.0            # same file
        elif os.path.dirname(wid) in dirs:
            votes[ref] = votes.get(ref, 0) + 4.0             # same directory
        elif os.sep.join(wid.split(os.sep)[-2:]) in tails:
            votes[ref] = votes.get(ref, 0) + 2.0             # same trailing dir/file
    return votes


def score_domains(evidence, tenant_id, domains=None):
    """Deterministic scoring. Same input -> same score, always."""
    domains = domains if domains is not None else load_domains()
    adj = _adjacent_domain_votes(evidence.get("paths"))
    lex = evidence["terms"] | evidence["path_terms"] | evidence["artifact_terms"]
    scored = {}
    for ref, d in sorted(domains.items()):
        if d.get("tenant_id") != tenant_id:
            continue
        dom_toks = tokenize(d.get("name", ""), *(d.get("mint_evidence") or []))
        overlap = len(lex & dom_toks)
        denom = float(len(dom_toks) or 1)
        lexical = overlap / denom
        depth = len(domain_path(ref, domains).split("."))
        score = adj.get(ref, 0.0) + (lexical * 3.0) + (0.15 * depth if overlap else 0.0)
        if score > 0:
            scored[ref] = score
    return scored


#: score at which absolute evidence is considered half-convincing. An adjacency
#: hit contributes 10.0, so a real neighbour match saturates; a single shared
#: word contributes ~1.0 and does not.
_ABS_HALF = 2.0
#: a lone candidate is WEAK evidence, not perfect evidence. See below.
_SOLO_MARGIN = 0.30


def classify(evidence, tenant_id, domains=None):
    """-> (domain_ref|None, confidence, mode) where mode is match|floor|none.

    Confidence blends ABSOLUTE evidence strength with the MARGIN over the
    runner-up. It is deliberately not `best / total`: that formulation returns
    1.0 whenever exactly one domain scores above zero, however feeble the match.
    Observed live — "fix the placement gate hook" matched "Readability Gate" on
    the single shared token "gate" and reported confidence 1.0, which meant the
    floor could never fire and I-P9 was unreachable code. A lone weak candidate
    must score LOW, not perfect.
    """
    domains = domains if domains is not None else load_domains()
    scored = score_domains(evidence, tenant_id, domains)
    if not scored:
        return None, 0.0, "none"

    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    best_ref, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0

    conf_abs = best_score / (best_score + _ABS_HALF)      # saturating, never 1.0
    conf_margin = ((best_score - second) / (best_score + second)
                   if second > 0 else _SOLO_MARGIN)
    confidence = round(min(1.0, 0.6 * conf_abs + 0.4 * conf_margin), 4)

    if confidence < CONFIDENCE_FLOOR:
        # I-P9: hold at the ancestor, do NOT mint noise off a weak signal
        parent = domains[best_ref].get("parent_ref")
        return (parent or best_ref), confidence, "floor"
    return best_ref, confidence, "match"


# ---------------------------------------------------------------- resolve ---

def _root_ref(tenant_id):
    domains = load_domains()
    for ref, d in sorted(domains.items()):
        if d.get("parent_ref") is None and d.get("tenant_id") == tenant_id:
            return ref
    ref, _ = mint_domain(None, os.environ.get("PLACEMENT_ROOT_NAME", "Root"),
                         ["root"], tenant_id, origin="system-minted")
    return ref


def _looks_like_file(part):
    """A path component with an extension is a file, not an area of concern."""
    return bool(re.search(r"\.[A-Za-z0-9]{1,6}$", part))


def _name_from_evidence(evidence):
    """Name a domain after an AREA, never after a file.

    A loose file at the repo root (README.md, LICENSE) describes no area, so it
    returns None and the caller places it at the nearest existing ancestor
    instead of minting. Naming domains after files is precisely the
    semantic-garbage failure the confidence floor exists to prevent: a 300-file
    repo would otherwise mint a domain per root-level file.
    """
    for p in evidence.get("paths") or []:
        parts = [x for x in p.split(os.sep) if x and x not in (".", "..") and not x.startswith(".")]
        dirs = [x for x in parts if not _looks_like_file(x)]
        if dirs:
            return dirs[-1].replace("-", " ").replace("_", " ").title()
    terms = [t for t in sorted(evidence.get("terms") or []) if len(t) > 3][:2]
    if terms:
        return " ".join(t.title() for t in terms)
    return None   # nothing nameable -> caller falls back to the ancestor


def resolve(work_ref, utterance="", paths=None, artifacts=None,
            tenant_id="T-local", phase="pre-flight"):
    """The main entry point. Never raises on a missing domain (I-P3)."""
    _ensure_dirs()
    existing = current_placement(work_ref.get("id"))
    if existing and phase == "pre-flight":
        for p in all_placements():
            if p.get("id") == existing:
                return {"placement": p, "reused": True}

    evidence = gather_evidence(utterance, paths, artifacts)
    ev_terms = sorted(evidence["terms"] | evidence["path_terms"])[:24]
    domains = load_domains()
    if not domains:
        _root_ref(tenant_id)
        domains = load_domains()

    ref, confidence, mode = classify(evidence, tenant_id, domains)
    created = {"domains": [], "charters": []}

    if mode == "none" or ref is None:
        parent = _root_ref(tenant_id)
        name = _name_from_evidence(evidence)
        if name is None:
            # Nothing nameable (a loose root-level file). Place at the ancestor
            # rather than minting a node named after a file (I-P9 in spirit).
            ref, origin, confidence = parent, "matched", 0.2
        else:
            ref, was_new = mint_domain(parent, name, ev_terms, tenant_id)
            if was_new:
                created["domains"].append(ref)
            origin = "minted"
            confidence = 0.5
    elif mode == "floor":
        origin = "matched"          # floor-hold: ancestor, no new node (I-P9)
    else:
        origin = "matched"

    chs = charters_for(ref)
    if chs:
        charter_id = sorted(c["id"] for c in chs)[0]
    else:
        domains = load_domains()
        nm = domains.get(ref, {}).get("name", "Work")
        charter_id = mint_charter_stub(
            ref, "%s Charter" % nm,
            "Work carried out under %s." % nm,
            sorted(set(evidence["paths"]))[:8], [], tenant_id)
        created["charters"].append(charter_id)

    p = write_placement(work_ref, ref, charter_id, origin, confidence,
                        created, tenant_id, phase=phase)
    return {"placement": p, "reused": False, "mode": mode}


def classify_only(utterance="", paths=None, artifacts=None, tenant_id="T-local"):
    """Read-only resolution. Matches against the existing tree; NEVER mints.

    This is what runs at prompt time, where the only evidence is the utterance.
    Minting from an utterance alone would create a domain per novel phrasing and
    blow the tree apart within a day — the exact drift the confidence floor
    exists to prevent. Real minting happens once work touches actual paths.
    """
    domains = load_domains()
    if not domains:
        return {"resolved": False, "reason": "empty-registry",
                "chain": [], "charter": {}, "confidence": 0.0}
    evidence = gather_evidence(utterance, paths, artifacts)
    ref, confidence, mode = classify(evidence, tenant_id, domains)
    if ref is None or mode == "none":
        return {"resolved": False, "reason": "no-match",
                "chain": [], "charter": {}, "confidence": round(confidence, 4)}
    chs = charters_for(ref)
    charter = {}
    if chs:
        c = sorted(chs, key=lambda x: x["id"])[0]
        charter = {"id": c["id"], "title": c.get("title", ""),
                   "promise": c.get("purpose", "")}
    return {
        "resolved": True, "mode": mode, "domain_ref": ref,
        "confidence": round(confidence, 4),
        "chain": [{k: v for k, v in n.items() if k != "ref"}
                  for n in ancestor_chain(ref, domains)],
        "charter": charter, "created": {"domains": [], "charters": []}, "units": 1,
    }


def render_payload(placement):
    """Shape the JSON that lib/placement-render.sh consumes."""
    domains = load_domains()
    ref = placement["domain_ref"]
    chain = ancestor_chain(ref, domains)
    for node in chain:
        if node["ref"] in (placement.get("created", {}).get("domains") or []):
            node["is_new"] = True
    charter = {}
    for c in charters_for(ref):
        if c["id"] == placement["charter_id"]:
            charter = {
                "id": c["id"], "title": c.get("title", ""),
                "promise": c.get("purpose", ""),
                "scope_in": ", ".join(c.get("scope_in") or [])[:60],
                "scope_out": ", ".join(c.get("scope_out") or [])[:60],
                "is_new": c["id"] in (placement.get("created", {}).get("charters") or []),
            }
    return {"chain": [{k: v for k, v in n.items() if k != "ref"} for n in chain],
            "charter": charter, "created": placement.get("created", {}), "units": 1}


# ------------------------------------------------------------ MECE report ---

def mece_report(tenant_id="T-local"):
    """Turns P5 from an assertion into a runnable check (ADR-028 Decision 6)."""
    domains = load_domains()
    mine = {r: d for r, d in domains.items() if d.get("tenant_id") == tenant_id}
    by_parent = {}
    for r, d in mine.items():
        by_parent.setdefault(d.get("parent_ref"), []).append(r)

    overlaps = []
    for parent, sibs in sorted(by_parent.items(), key=lambda kv: str(kv[0])):
        for i in range(len(sibs)):
            for j in range(i + 1, len(sibs)):
                a, b = sorted([sibs[i], sibs[j]])
                ta = tokenize(mine[a].get("name", ""), *(mine[a].get("mint_evidence") or []))
                tb = tokenize(mine[b].get("name", ""), *(mine[b].get("mint_evidence") or []))
                if not ta or not tb:
                    continue
                jac = len(ta & tb) / float(len(ta | tb))
                if jac >= 0.5:
                    overlaps.append({
                        "a": a, "b": b, "a_name": mine[a].get("name"),
                        "b_name": mine[b].get("name"), "similarity": round(jac, 3),
                        "auto_mergeable": bool(
                            jac >= AUTO_MERGE_THRESHOLD
                            and mine[a].get("origin") == "system-minted"
                            and mine[b].get("origin") == "system-minted"
                            and not mine[a].get("touched_by_operator")
                            and not mine[b].get("touched_by_operator")),
                    })
    placed = {r.get("work_ref_id") for r in _read_jsonl(CURRENT)}
    return {
        "domains": len(mine),
        "me_violations": len(overlaps),
        "overlaps": sorted(overlaps, key=lambda o: -o["similarity"])[:20],
        "ce_addressed_units": len(placed),
        "auto_mergeable": sum(1 for o in overlaps if o["auto_mergeable"]),
    }


# ------------------------------------------------------------ restructure ---

def _save_domain(d):
    with open(os.path.join(DOMAINS, d["ref"] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, sort_keys=True, indent=2)


def _is_descendant(candidate, ancestor, domains):
    """True if `candidate` sits anywhere under `ancestor` in the tree."""
    seen, cur = set(), candidate
    while cur and cur in domains and cur not in seen:
        if cur == ancestor:
            return True
        seen.add(cur)
        cur = domains[cur].get("parent_ref")
    return False


def restructure(op, ref, target=None, name=None, tenant_id="T-local"):
    """rename | move | merge | delete. MOVE re-mints ZERO placements (I-P8).

    Codex F7.1 folds (2026-07-30): the whole operation runs under a global
    restructure lock (mint was flocked; restructure was ordinary multi-file
    writes — lost updates under concurrency). MOVE rejects cycles (re-parenting
    under one's own descendant orphans the subtree from the root). DELETE
    re-parents CHILD DOMAINS, not just placements — children were orphaned.
    """
    with _lock("RESTRUCTURE"):
        return _restructure_locked(op, ref, target, name, tenant_id)


def _restructure_locked(op, ref, target=None, name=None, tenant_id="T-local"):
    domains = load_domains()
    if ref not in domains:
        return {"ok": False, "error": "unknown domain ref"}
    d = domains[ref]
    moved = 0

    if op == "rename":
        d["name"] = name or d["name"]
        d["touched_by_operator"] = True      # permanent latch: never AUTO-merged again
        _save_domain(d)

    elif op == "move":
        if target not in domains:
            return {"ok": False, "error": "unknown target"}
        if target == ref or _is_descendant(target, ref, domains):
            return {"ok": False, "error": "cycle: target is inside the moved subtree"}
        d["parent_ref"] = target
        d["touched_by_operator"] = True
        _save_domain(d)
        moved = 0                             # the whole point of stable refs

    elif op == "merge":
        if target not in domains:
            return {"ok": False, "error": "unknown target"}
        for p in all_placements():
            if p.get("domain_ref") == ref and current_placement(p["work_ref"]["id"]) == p["id"]:
                write_placement(p["work_ref"], target, p["charter_id"], "matched",
                                p.get("confidence", 0.5), {"domains": [], "charters": []},
                                tenant_id, supersedes=p["id"], phase="post-close")
                moved += 1
        for c in charters_for(ref):
            c["domain_ref"] = target
            with open(os.path.join(CHARTERS, c["id"] + ".json"), "w", encoding="utf-8") as fh:
                json.dump(c, fh, sort_keys=True, indent=2)
        tgt = domains[target]
        tgt["principles"] = (tgt.get("principles") or []) + (d.get("principles") or [])
        tgt["touched_by_operator"] = True
        _save_domain(tgt)
        os.remove(os.path.join(DOMAINS, ref + ".json"))

    elif op == "delete":
        parent = d.get("parent_ref")
        if parent is None:
            return {"ok": False, "error": "cannot delete the root domain"}
        for p in all_placements():
            if p.get("domain_ref") == ref and current_placement(p["work_ref"]["id"]) == p["id"]:
                write_placement(p["work_ref"], parent, p["charter_id"], "matched",
                                p.get("confidence", 0.5), {"domains": [], "charters": []},
                                tenant_id, supersedes=p["id"], phase="post-close")
                moved += 1
        # children re-parent to the deleted node's parent — never orphaned
        for cref, cd in domains.items():
            if cd.get("parent_ref") == ref:
                cd["parent_ref"] = parent
                _save_domain(cd)
        os.remove(os.path.join(DOMAINS, ref + ".json"))
    else:
        return {"ok": False, "error": "unknown op"}

    _append_jsonl(DOMAIN_INDEX, {"event": "domain_restructured", "op": op,
                                 "ref": ref, "target": target,
                                 "placements_repointed": moved, "ts_ms": _now_ms()})
    return {"ok": True, "op": op, "placements_repointed": moved}


def consolidate(tenant_id="T-local", apply_auto=True):
    """Two-tier: AUTO-merge system-minted untouched near-duplicates; PROPOSE
    everything the operator has ever touched (ADR-028 Decision 1 corollary)."""
    rep = mece_report(tenant_id)
    applied, proposed = [], []
    for o in rep["overlaps"]:
        if o["auto_mergeable"] and apply_auto:
            r = restructure("merge", o["b"], target=o["a"], tenant_id=tenant_id)
            if r.get("ok"):
                applied.append(o)
        else:
            proposed.append(o)
    return {"auto_applied": applied, "proposed": proposed}


# ------------------------------------------------------------------- scan ---

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".next", "target", ".claude", ".enforcement", ".analytics"}


def place_placement_at(file_path, domain_ref, tenant_id):
    """Stamp a backfilled placement at an already-resolved domain.

    Used by the bulk scan, which derives the domain from directory structure
    rather than from the classifier — the structure IS the evidence there.
    """
    chs = charters_for(domain_ref)
    if chs:
        charter_id = sorted(c["id"] for c in chs)[0]
    else:
        nm = load_domains().get(domain_ref, {}).get("name", "Work")
        charter_id = mint_charter_stub(domain_ref, "%s Charter" % nm,
                                       "Work carried out under %s." % nm,
                                       [], [], tenant_id)
    return write_placement({"kind": "file", "id": file_path}, domain_ref,
                           charter_id, "backfilled", 0.7,
                           {"domains": [], "charters": []}, tenant_id)


def scan(root, tenant_id="T-local", max_files=4000, level_cap=2):
    """B22 one-time discovery: enumerate, derive one level at a time, stop
    descending where evidence is thin. Idempotent and resumable."""
    _ensure_dirs()
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            files.append(os.path.join(dirpath, fn))
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break

    # Bucket by DIRECTORY, never by file. A loose file at the repo root belongs
    # to the root domain — it does not describe an area of its own. Bucketing by
    # file is what produced one domain per root-level file on the first run.
    buckets = {}
    for f in files:
        rel = os.path.relpath(f, root)
        parts = rel.split(os.sep)
        dirs = parts[:-1][:level_cap]          # drop the filename, cap the depth
        buckets.setdefault(os.sep.join(dirs), []).append(f)

    addressed = already = root_level = 0
    for key in sorted(buckets):
        for f in buckets[key]:
            if current_placement(f):
                already += 1
                continue
            if not key:
                # no directory -> nothing nameable; resolve() places it at root
                resolve({"kind": "file", "id": f}, utterance="", paths=[],
                        tenant_id=tenant_id)
                root_level += 1
            else:
                # Mint the bucket's directory chain NESTED, so os/engines becomes
                # Os > Engines rather than two siblings of the root. Depth grows
                # from real structure, one level at a time (B22's contract).
                parent = _root_ref(tenant_id)
                for seg in key.split(os.sep):
                    nm = seg.replace("-", " ").replace("_", " ").title()
                    parent, was_new = mint_domain(parent, nm, [seg], tenant_id)
                place_placement_at(f, parent, tenant_id)
            addressed += 1
    return {"units_enumerated": len(files), "units_addressed": addressed,
            "already_addressed": already, "buckets": len(buckets),
            "root_level_files": root_level, "mece": mece_report(tenant_id)}


# -------------------------------------------------------------------- CLI ---

def _out(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


def main(argv):
    if len(argv) < 2:
        _out({"error": "usage: placement_engine.py <resolve|tree|mece|consolidate|"
                       "restructure|scan|stats> ..."}); return 2
    cmd = argv[1]
    tenant = os.environ.get("PLACEMENT_TENANT", "T-local")

    if cmd == "resolve":
        kind = argv[2] if len(argv) > 2 else "utterance"
        wid = argv[3] if len(argv) > 3 else "w-%d" % _now_ms()
        utt = argv[4] if len(argv) > 4 else ""
        paths = argv[5:] if len(argv) > 5 else []
        r = resolve({"kind": kind, "id": wid}, utterance=utt, paths=paths, tenant_id=tenant)
        _out({"placement": r["placement"], "reused": r.get("reused"),
              "render": render_payload(r["placement"])})
    elif cmd == "classify":
        # read-only; used by the per-turn hook. Never mints.
        utt = argv[2] if len(argv) > 2 else ""
        paths = argv[3:] if len(argv) > 3 else []
        _out(classify_only(utt, paths, tenant_id=tenant))
    elif cmd == "tree":
        domains = load_domains()
        _out({"domains": [{"ref": r, "path": domain_path(r, domains),
                           "name": d.get("name"), "origin": d.get("origin"),
                           "touched": d.get("touched_by_operator")}
                          for r, d in sorted(domains.items(),
                                             key=lambda kv: domain_path(kv[0], domains))]})
    elif cmd == "mece":
        _out(mece_report(tenant))
    elif cmd == "consolidate":
        _out(consolidate(tenant, apply_auto=("--dry-run" not in argv)))
    elif cmd == "restructure":
        _out(restructure(argv[2], argv[3],
                         target=(argv[4] if len(argv) > 4 else None),
                         name=(argv[4] if len(argv) > 4 else None), tenant_id=tenant))
    elif cmd == "scan":
        _out(scan(argv[2] if len(argv) > 2 else ".", tenant))
    elif cmd == "stats":
        _out({"home": HOME, "domains": len(load_domains()),
              "charters": len(os.listdir(CHARTERS)) if os.path.isdir(CHARTERS) else 0,
              "placements": len(all_placements()),
              "current_rows": len(_read_jsonl(CURRENT)),
              "confidence_floor": CONFIDENCE_FLOOR})
    else:
        _out({"error": "unknown command: %s" % cmd}); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
