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
    charters/C-<sha>.json       content-addressed HASHED BODY, immutable.
                                id == sha256(canonical body, `id` excluded);
                                `verify-charters` re-checks every one.
    charters/C-<sha>.page.json  MUTABLE sidecar — status, artifacts,
                                linked_domain_refs, goals, metrics, milestones,
                                todos, ts_ms, lifecycle, handoff (§2.2). Never
                                hashed; merged over the body by charter_view().
    charters/INDEX.jsonl        APPEND-ONLY charter lifecycle log
    placements/PL-<sha>.json    content-addressed, append-only
    placements/CURRENT.jsonl    APPEND-ONLY log, read tail-first
    plans/retire-<dref>-<ts>.json   pre-mutation recovery manifests

I-D5 (no destruction): a minted domain's file is NEVER removed. MERGE and
DELETE stamp status='retired' + successor_refs and leave the row in place;
`retire`/`unretire` are the operator-facing form of the same transition.
`load_domains()` therefore keeps NO default filter — use `live_refs()` at
render and choice surfaces only, and never inside `domain_path()`.

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
PLANS = os.path.join(HOME, "plans")
CURRENT = os.path.join(PLACEMENTS, "CURRENT.jsonl")
DOMAIN_INDEX = os.path.join(DOMAINS, "INDEX.jsonl")
CHARTER_INDEX = os.path.join(CHARTERS, "INDEX.jsonl")

#: Domain lifecycle (I-D5). active <-> frozen; active|frozen -> retired;
#: retired -> active ONLY via `unretire --from <manifest>`. A minted domain's
#: file is NEVER removed — `retired` is the terminal state, not deletion.
DOMAIN_STATUSES = ("active", "frozen", "retired")

#: Charter body shape version (§2.2). A body with no `schema` key is v1 and
#: verifies against the SAME rule — sha256 of the canonical body with `id`
#: excluded — because v1 hashed the body before `id` was stamped onto it.
CHARTER_SCHEMA = 2
#: closed enum, shipped, UNCHANGED by the body/sidecar split. Lives in the
#: sidecar; `superseded` is DERIVED from `supersedes`, never a status value.
CHARTER_STATUSES = ("active", "shipped", "retired", "paused")
#: `reconstructed` is NOT an operator choice — `reconcile` is its only writer.
#: It marks a tombstone minted to stand in for a domain file the pre-I-D5
#: os.remove() destroyed: the ref is cited by placement history, the row it
#: named is gone forever, and this code says so on the record rather than
#: letting the gap read as a normal retirement.
RETIRE_REASON_CODES = ("merged", "deleted", "split", "superseded", "duplicate",
                       "out_of_scope", "dormant", "abandoned_draft",
                       "reconstructed")

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


#: lock name -> re-entry depth for THIS process. flock(2) is keyed on the open
#: file description, so a second os.open() of the same lock file from the same
#: process is a DIFFERENT description and LOCK_EX on it blocks forever. Routing
#: every domain write through _save_domain() (§9 Phase 0) means the restructure
#: lock is now entered from inside itself, so the guard is load-bearing, not
#: defensive: without it `retire` self-deadlocks on its first _save_domain().
_HELD = {}


@contextmanager
def _lock(name):
    """flock-based mutex, re-entrant within one process. Kernel releases on
    process death (fold 1); the depth counter handles nesting."""
    os.makedirs(DOMAINS, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    if _HELD.get(key):
        _HELD[key] += 1
        try:
            yield
        finally:
            _HELD[key] -= 1
        return
    path = os.path.join(DOMAINS, "%s.lock" % key)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _HELD[key] = 1
        yield
    finally:
        _HELD.pop(key, None)
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


def live_refs(domains):
    """Render/choice-surface filter: drops `retired` nodes ONLY (I-D5).

    `load_domains()` deliberately keeps NO default filter — write_placement's
    I-P2 check, lint, _adjacent_domain_votes, domain_path and every charter
    consumer must keep seeing tombstones, or the retire path breaks its own
    happy path and every just-retired ref reads as newly unresolvable.

    `frozen` is excluded from NOTHING at read time: resolve() mints a new
    sibling whenever classify finds no candidate, so a frozen domain hidden
    from the classifier manufactures the duplicate it exists to prevent.
    Freeze is a WRITE-boundary rule.

    NEVER pass the result of this into domain_path(): ordinals are computed
    over the full sibling set and a retired sibling keeps its D-number
    permanently.
    """
    return {r: d for r, d in domains.items()
            if d.get("status", "active") != "retired"}


def tenant_refs(domains, tenant_id=None):
    """RETIRED. Returns every domain, whatever is passed.

    This was the publish-surface filter that kept one tenant's nodes and dropped
    the rest. Tenancy is gone: `subtree_refs()` replaces it, selecting by
    containment from the root instead of by a label stamped on each row.

    Kept as an identity function, briefly, so an out-of-tree caller degrades to
    "sees everything" rather than crashing -- which is the safe direction for a
    READ filter, and the honest one now that there is nothing to separate. It
    takes no part in any decision and should be deleted once no caller remains.

    What it never was, by its own former docstring: isolation. All tenants
    shared one $SUTRA_NATIVE_HOME and the selector was an env var, so nothing
    stopped a process that could read the kit from reading every tenant in it.
    The boundary that actually holds is ONE REGISTRY PER PARTY -- a separate
    SUTRA_NATIVE_HOME, enforced by the filesystem rather than by a string.
    """
    return dict(domains)


def subtree_refs(domains, root_ref):
    """Publish-surface filter by CONTAINMENT: every domain at or below `root_ref`.

    The replacement for tenant_refs() as the publish chokepoint. Both answer
    "which domains belong to this org", but they answer it differently:

        tenant_refs   by LABEL      -- a tenant_id string stamped on each row
        subtree_refs  by STRUCTURE  -- reachability from the root by parent_ref

    Structure is the better answer here because it cannot disagree with the tree
    the site actually renders. A row whose tenant_id was mistyped silently
    vanished from the published site while still sitting in the registry; a row
    that is not under the root is not part of the org by construction, and the
    same walk that publishes it is the one that selects it.

    UNFILTERED BY LIVENESS, deliberately: retired nodes stay in, because
    export_registry_only must keep emitting tombstoned rows (§2.1) so a charter
    homed to a retired domain still reaches the Archive tray. Compose with
    live_refs() when the caller wants only live ones, exactly as before.

    NEVER pass the result into domain_path(): ordinals are computed over the
    full sibling set, the same rule live_refs() and tenant_refs() carry.
    """
    kids = {}
    for r, d in domains.items():
        kids.setdefault(d.get("parent_ref"), []).append(r)
    out, stack, seen = {}, [root_ref], set()
    while stack:
        r = stack.pop()
        # the cycle guard is not theoretical: a damaged parent_ref loop must not
        # hang a publish, which is exactly where this runs unattended
        if r in seen or r not in domains:
            continue
        seen.add(r)
        out[r] = domains[r]
        stack.extend(kids.get(r, ()))
    return out


def _nearest_live_ancestor(ref, domains):
    """Walk up to the first non-retired node. Floor-holds must not land work
    on a tombstone, which accepts no new placements."""
    seen, cur = set(), ref
    while cur and cur in domains and cur not in seen:
        if domains[cur].get("status", "active") != "retired":
            return cur
        seen.add(cur)
        cur = domains[cur].get("parent_ref")
    return None


def domain_path(ref, domains=None):
    """Derive the positional D-path by walking parent_ref (I-D1: display only).

    ALWAYS computed over the UNFILTERED domain set: retirement removes a node
    from display, never from its sibling ordinal (I-D5). Passing a
    live_refs()-filtered dict in here is a bug — it renumbers live siblings.
    """
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

    Locking (§2.1 Mint interlock, P0): RESTRUCTURE **outermost**, then the
    per-parent lock. The per-parent flock alone is a DIFFERENT lock FILE from
    `domains/RESTRUCTURE.lock`, so it gave zero mutual exclusion against
    `retire`/`restructure`/`org apply`: those snapshot `load_domains()` under
    RESTRUCTURE and re-parent children from that snapshot, so a mint landing
    mid-transition parents a live child to a node about to become a tombstone —
    invisible to the disposition report and to every later verb. `_lock` is
    re-entrant (`_HELD`), so internal callers pay nothing. RESTRUCTURE -> parent
    matches retire/restructure (which take RESTRUCTURE first and never take a
    per-parent lock), so the order cannot cycle.
    """
    _ensure_dirs()
    lock_name = parent_ref if parent_ref else "ROOT"
    with _lock("RESTRUCTURE"), _lock(lock_name):
        domains = load_domains()
        # A `frozen` or `retired` parent is a WRITE boundary (§9 Phase 0):
        # freeze exists to stop the tree growing there, and a tombstone accepts
        # nothing at all. Re-checked HERE, under the lock, so a concurrent
        # `retire`/`org apply` cannot slip a child under a node it just closed.
        parent_doc = domains.get(parent_ref) if parent_ref else None
        if parent_doc is not None and parent_doc.get("status", "active") != "active":
            raise ValueError("ORG-016 reject: parent %s is %s, not active"
                             % (parent_ref, parent_doc.get("status", "active")))
        # re-check under the lock: did a peer already mint an equivalent sibling?
        norm = name.strip().lower()
        for ref, d in domains.items():
            if (d.get("parent_ref") == parent_ref
                    and d.get("status", "active") == "active"
                    and d.get("name", "").strip().lower() == norm):
                return ref, False
        # Refs are never reused; NAMES are. I-D5 keeps retired files in place,
        # which would otherwise turn this dedupe into tombstone adoption — the
        # new mint would return a retired ref that refuses placements.
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
            # ---- lifecycle (I-D5). Absent status reads as "active". ----
            "status": "active",
            "successor_refs": [],
            "retired_at_ms": None,
            "retire_reason_code": None,
            "retire_note": None,
            "disposition_event_id": None,
        }
        with open(os.path.join(DOMAINS, ref + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True, indent=2)
        _append_jsonl(DOMAIN_INDEX, {"event": "domain_minted", "ref": ref,
                                     "parent_ref": parent_ref, "name": name,
                                     "origin": origin, "tenant_id": tenant_id,
                                     "ts_ms": doc["ts_minted_ms"]})
        return ref, True


# --------------------------------------------------------------- charters ---

def _is_body_file(fn):
    """charters/ holds bodies AND `<C-id>.page.json` sidecars. Both end in
    `.json`; only the first is a charter."""
    return fn.endswith(".json") and not fn.endswith(".page.json")


def charter_body_files():
    _ensure_dirs()
    return sorted(fn for fn in os.listdir(CHARTERS) if _is_body_file(fn))


def charters_for(domain_ref, tenant_id=None):
    """Charters homed to `domain_ref`. `tenant_id=None` is UNFILTERED (§6) —
    the default keeps every six-positional call site's semantics unchanged."""
    _ensure_dirs()
    out = []
    for fn in os.listdir(CHARTERS):
        if not _is_body_file(fn):
            continue
        try:
            with open(os.path.join(CHARTERS, fn), "r", encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("domain_ref") != domain_ref:
                continue
            if tenant_id and c.get("tenant_id") != tenant_id:
                continue
            out.append(c)
        except (ValueError, OSError):
            continue
    return out


def pick_charter(domain_ref, evidence_terms=None):
    """A Domain hosts MANY charters; each charter lives in one Domain.
    Which one a work unit runs under = best evidence overlap between the
    turn's terms and each charter's title/purpose/scope_in; deterministic
    tie-break by id. With one charter this degrades to that charter.

    CHOICE surface — the charter-side twin of `live_refs()`. A `retired` charter
    and a SUPERSEDED one are not destinations for new work: after `charter
    reassign C-x <other domain>` the source domain is still active and still
    holds exactly one body (the source), so an unfiltered pick handed new work
    straight back to the charter the operator had just closed, and the site
    rendered an st-retired pill on a live domain's page.

    Returning None when every charter on the domain is closed is NOT an I-P3
    hazard: all three callers already handle it — `resolve` mints a fresh stub
    (which is the correct answer for new work on a domain whose charters are all
    closed), `classify_only` reports no charter, `touch` keeps the current one.
    """
    chs = _open_charters(charters_for(domain_ref))
    if not chs:
        return None
    if len(chs) == 1 or not evidence_terms:
        return sorted(chs, key=lambda c: c["id"])[0]
    ev = set(evidence_terms)
    def score(c):
        toks = tokenize(c.get("title",""), c.get("purpose",""),
                        *(c.get("scope_in") or []))
        return (len(ev & toks), c["id"])
    best = sorted(chs, key=lambda c: (-score(c)[0], c["id"]))[0]
    return best


def mint_charter_stub(domain_ref, title, purpose, scope_in, scope_out, tenant_id,
                      kind="standing", supersedes=None, status="active",
                      artifacts=None, linked_domain_refs=None, extras=None):
    """Mint a charter from its FULL body, hashing exactly once (§2.2).

    obligations stays EMPTY with a stated reason — the system never fabricates
    promises the operator did not make (ADR-028 Decision 5; Charter I-2).

    `kind`, `supersedes` and `schema` are part of the HASHED body. Everything
    the operator edits weekly — status, artifacts, linked_domain_refs, goals,
    metrics, milestones, todos — goes to the sidecar, written here at mint so
    no caller ever has to reopen the C-<hash> file. The post-mint rewrite loops
    in charters_seed/domains_pipeline (§0.12/§0.13) were the reason every
    project charter on disk fails to hash to its own id; passing the whole body
    in is what deletes them.

    Trailing arguments all default, so the six-positional call sites
    (resolve, place_placement_at, domains_pipeline) keep working unchanged.
    """
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
        "kind": kind,
        "supersedes": supersedes,
        "schema": CHARTER_SCHEMA,
    }
    cid = charter_id_of(body)
    body["id"] = cid
    path = os.path.join(CHARTERS, cid + ".json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh, sort_keys=True, indent=2)
    if not os.path.exists(_sidecar_path(cid)):
        # never clobber an operator-edited sidecar on an idempotent re-mint
        sc = _sidecar_default(_now_ms())     # mint IS the ts_ms we can vouch for
        if status:
            sc["status"] = status
        sc["artifacts"] = list(artifacts or [])
        sc["linked_domain_refs"] = list(linked_domain_refs or [])
        for k, v in (extras or {}).items():
            sc[k] = v
        save_sidecar(cid, sc)
    return cid


def load_charter(charter_id):
    """The hashed body, or None. Bodies are immutable — never written back."""
    if not charter_id:
        return None
    try:
        with open(os.path.join(CHARTERS, charter_id + ".json"), "r", encoding="utf-8") as fh:
            c = json.load(fh)
        return c if isinstance(c, dict) else None
    except (ValueError, OSError):
        return None


#: The operator-mutable set (§2.2). These live in charters/<C-id>.page.json and
#: are NEVER part of the hashed body — a todo tick must not change the charter
#: id and break C-<id>.html, which domains_page calls stable forever (§0.13).
_SIDECAR_KEYS = ("status", "artifacts", "linked_domain_refs", "goals",
                 "metrics", "milestones", "todos")

#: Exactly what the two pre-fix post-mint rewrite loops wrote back into the
#: hashed body (charters_seed.py:269-279, domains_pipeline.py:200-207).
#: Stripping these is what RESTORES a damaged legacy body to the shape it was
#: hashed over, which is why migration can grandfather the id instead of
#: re-minting it and orphaning every placement that cites it.
_LEGACY_BODY_KEYS = _SIDECAR_KEYS + ("kind",)


def charter_id_of(body):
    """The content address of a charter body. `id` is EXCLUDED — v1 hashed the
    body before stamping id onto it, so one rule verifies both schemas."""
    return "C-" + _sha(dict((k, v) for k, v in body.items() if k != "id"))[:16]


def _sidecar_path(charter_id):
    return os.path.join(CHARTERS, charter_id + ".page.json")


def _sidecar_default(ts_ms=None):
    """The empty sidecar. `ts_ms` is passed ONLY on a write path.

    §2.2 introduces `ts_ms` precisely because "which charters existed in June"
    is otherwise unanswerable. Defaulting it to `_now_ms()` on the READ fallback
    made that worse than absent: a charter with no `.page.json` reported a
    fabricated timestamp of NOW that moved on every read and every build, and
    read as authoritative. Unknown is `None`; only mint/backfill stamp a value.
    """
    return {"status": "active", "artifacts": [], "linked_domain_refs": [],
            "goals": [], "metrics": [], "milestones": [], "todos": [],
            "ts_ms": ts_ms}


def load_sidecar(charter_id):
    """Sidecar if present; otherwise seed from whatever mutable keys the body
    still carries, so nothing is lost before the split lands. An absent sidecar
    reports `ts_ms: None` — UNKNOWN, never a fabricated now()."""
    base = _sidecar_default()
    try:
        with open(_sidecar_path(charter_id), "r", encoding="utf-8") as fh:
            sc = json.load(fh)
        if isinstance(sc, dict):
            base.update(sc)
            return base
    except (ValueError, OSError):
        pass
    body = load_charter(charter_id) or {}
    for k in _SIDECAR_KEYS:
        if k in body:
            base[k] = body[k]
    return base


def save_sidecar(charter_id, sidecar):
    os.makedirs(CHARTERS, exist_ok=True)
    with open(_sidecar_path(charter_id), "w", encoding="utf-8") as fh:
        json.dump(sidecar, fh, sort_keys=True, indent=2)


def charter_view(body_or_id):
    """Body + sidecar merged for RENDER (§2.2). The sidecar wins its own keys;
    the body is never mutated — callers get a copy. `id` and `domain_ref` are
    body-only by construction: the sidecar has no say in identity or home."""
    body = load_charter(body_or_id) if isinstance(body_or_id, str) else body_or_id
    if not body:
        return None
    cid = body.get("id") or ""
    view = dict(body)
    for k, v in (load_sidecar(cid) or {}).items():
        if k not in ("id", "domain_ref"):
            view[k] = v
    view.setdefault("kind", "standing")
    return view


def superseded_ids():
    """{superseded_id: successor_id}. Supersession is DERIVED, never stored.

    §2.2: a charter is superseded iff some OTHER body names it in `supersedes`
    AND that successor's sidecar does not carry `lifecycle='reverted'`. The
    reverted clause is what lets `unretire` undo a retire without deleting the
    successor charters the retire minted — I-D5 and content addressing both
    forbid deleting them, so the flag has to switch off from the successor side.

    This is the Phase 0 stand-in for §7.3's `edge(src,'supersedes',dst)` rows
    with `valid_to_ms`: same predicate, computed off the bodies on disk instead
    of a read model that does not exist yet.
    """
    out = {}
    for fn in charter_body_files():
        cid = fn[:-len(".json")]
        body = load_charter(cid) or {}
        src = body.get("supersedes")
        if not src:
            continue
        if load_sidecar(body.get("id") or cid).get("lifecycle") == "reverted":
            continue
        out.setdefault(src, body.get("id") or cid)
    return out


def superseded_by(charter_id):
    """The LIVE successor superseding `charter_id`, or None. Never stored."""
    if not charter_id:
        return None
    return superseded_ids().get(charter_id)


def _open_charters(charters):
    """The subset that may still receive NEW work: not `retired` in the sidecar
    and not superseded by a live successor. Callers fall back to the unfiltered
    list when this is empty (I-P3)."""
    supers = superseded_ids()
    out = []
    for c in charters:
        cid = c.get("id") or ""
        if cid in supers:
            continue
        if load_sidecar(cid).get("status", "active") == "retired":
            continue
        out.append(c)
    return out


def _mint_successor_charter(old, target_ref, reason, open_placements_n=0):
    """Amendment = a NEW content-addressed charter with `supersedes` set.

    `restructure merge` used to rewrite `domain_ref` inside the existing
    C-<hash> file, so the charter stopped hashing to its own id. Charters are
    immutable; re-homing mints a successor and leaves the original in place
    (I-D5's charter-side twin). Supersession is DERIVED from `supersedes`,
    never stamped on the superseded body.
    """
    prior = load_sidecar(old.get("id") or "")
    # a legacy (pre-split) body may still carry the mutable set inline; those
    # keys must NOT ride into the successor's hashed body or the successor is
    # born with the same defect (§0.13).
    body = dict((k, v) for k, v in old.items()
                if k != "id" and k not in _SIDECAR_KEYS)
    body["domain_ref"] = target_ref
    body["supersedes"] = old.get("id")
    body["schema"] = CHARTER_SCHEMA
    body["kind"] = old.get("kind") or prior.get("kind") or "standing"
    cid = charter_id_of(body)
    body["id"] = cid
    path = os.path.join(CHARTERS, cid + ".json")
    if not os.path.exists(path):
        os.makedirs(CHARTERS, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh, sort_keys=True, indent=2)
    elif os.path.exists(_sidecar_path(cid)):
        return cid            # idempotent re-mint: never clobber a live sidecar
    sc = _sidecar_default(_now_ms())
    sc["status"] = prior.get("status", "active")
    sc["artifacts"] = list(prior.get("artifacts") or [])
    sc["linked_domain_refs"] = list(prior.get("linked_domain_refs") or [])
    # §3.5 handoff: the receiving domain gets a briefing instead of bare
    # responsibility. Sidecar-only — the hashed body stays clean.
    sc["handoff"] = {"from_domain_ref": old.get("domain_ref"),
                     "from_charter_id": old.get("id"),
                     "open_placements_n": open_placements_n,
                     "artifacts": sc["artifacts"][:8],
                     "reason": reason, "ts_ms": sc["ts_ms"]}
    save_sidecar(cid, sc)
    return cid


# ------------------------------------------------------------- placements ---

def current_placement(work_ref_id):
    """Tail-first scan of the append-only CURRENT log (fold 3)."""
    rows = _read_jsonl(CURRENT)
    for row in reversed(rows):
        if row.get("work_ref_id") == work_ref_id:
            return row.get("placement_id")
    return None


def all_placements(tenant_id=None):
    """Every placement body. `tenant_id=None` is UNFILTERED (§6) — resolve()'s
    reuse lookup and `stats` both want the whole set."""
    _ensure_dirs()
    out = []
    for fn in os.listdir(PLACEMENTS):
        if not (fn.startswith("PL-") and fn.endswith(".json")):
            continue
        try:
            with open(os.path.join(PLACEMENTS, fn), "r", encoding="utf-8") as fh:
                p = json.load(fh)
            if tenant_id and p.get("tenant_id") != tenant_id:
                continue
            out.append(p)
        except (ValueError, OSError):
            continue
    return out


def _current_placements():
    """Placement bodies that are still the CURRENT row for their work_ref.

    One tail pass over CURRENT.jsonl instead of one per candidate — the
    restructure/retire loops used to call current_placement() inside the
    all_placements() loop, which is a full log re-read per placement.
    """
    latest = {}
    for row in _read_jsonl(CURRENT):
        wid = row.get("work_ref_id")
        if wid:
            latest[wid] = row.get("placement_id")
    out = []
    for p in all_placements():
        wid = (p.get("work_ref") or {}).get("id")
        if wid and latest.get(wid) == p.get("id"):
            out.append(p)
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
    # CHOICE surface: retired nodes are not candidates (I-D5). Votes and
    # domain_path still read the FULL map — history and ordinals are unfiltered.
    adj = _adjacent_domain_votes(evidence.get("paths"))
    lex = evidence["terms"] | evidence["path_terms"] | evidence["artifact_terms"]
    scored = {}
    for ref, d in sorted(live_refs(domains).items()):
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
        # I-P9: hold at the ancestor, do NOT mint noise off a weak signal.
        # The ancestor may itself be a tombstone — hold at the nearest LIVE one.
        parent = domains[best_ref].get("parent_ref")
        if parent:
            parent = _nearest_live_ancestor(parent, domains)
        return (parent or best_ref), confidence, "floor"
    return best_ref, confidence, "match"


# ---------------------------------------------------------------- resolve ---

def _root_ref(tenant_id):
    """The tenant's LIVE root — every mint in resolve()/scan() hangs off it.

    The liveness filter is load-bearing now that mint_domain refuses a
    non-active parent (§9 Phase 0): `restructure merge` can retire a root, and
    handing that tombstone back here would make resolve() RAISE, breaking I-P3
    ("never fails on a missing domain"). Same rule as `_tenant_root`.

    Minting is the LAST resort, not the second one. `_tenant_root`'s docstring
    names the hazard — "rather than manufacturing a SECOND parent-less node,
    which the site generator reads as the tree's root" — and this is the
    function that manufactures it, so a retired root resolves through its own
    `successor_refs` chain first (same transitive read `_live_destination` does
    for charters). The successor must belong to the SAME tenant: §6 forbids
    silently re-homing one tenant's work under another's root.
    """
    domains = load_domains()
    # THE TENANT CONJUNCT IS GONE, and that is a safety improvement rather than
    # a relaxation. It was the only thing that could make this lookup MISS on a
    # registry that plainly has a root -- a mistyped PLACEMENT_TENANT was enough
    # -- and the miss is not benign: control falls through to the mint below and
    # manufactures a SECOND parent-less node, which every publish surface then
    # refuses to disambiguate. Matching the root by structure alone makes that
    # branch unreachable while any live root exists.
    for ref, d in sorted(domains.items()):
        if d.get("parent_ref") is None and d.get("status", "active") == "active":
            return ref
    for ref, d in sorted(domains.items()):
        if d.get("parent_ref") is None:
            dest, _how = _live_destination(ref, domains, None)
            if dest:
                return dest
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
            try:
                ref, was_new = mint_domain(parent, name, ev_terms, tenant_id)
                origin = "minted"
            except ValueError:
                # ORG-016: the parent went frozen/retired between _root_ref()
                # and the mint. I-P3 and this function's own contract ("never
                # raises on a missing domain") outrank the mint, so hold at the
                # nearest LIVE ancestor exactly as the confidence floor does.
                ref = _nearest_live_ancestor(parent, load_domains()) or parent
                was_new, origin = False, "matched"
            if was_new:
                created["domains"].append(ref)
            confidence = 0.5
    elif mode == "floor":
        origin = "matched"          # floor-hold: ancestor, no new node (I-P9)
    else:
        origin = "matched"

    picked = pick_charter(ref, ev_terms)
    if picked:
        charter_id = picked["id"]
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
    domains = load_domains()          # FULL map: ancestor_chain/domain_path need it
    if not live_refs(domains):
        return {"resolved": False, "reason": "empty-registry",
                "chain": [], "charter": {}, "confidence": 0.0}
    evidence = gather_evidence(utterance, paths, artifacts)
    ref, confidence, mode = classify(evidence, tenant_id, domains)
    if ref is None or mode == "none":
        return {"resolved": False, "reason": "no-match",
                "chain": [], "charter": {}, "confidence": round(confidence, 4)}
    charter = {}
    c = pick_charter(ref, sorted(evidence["terms"] | evidence["path_terms"]))
    if c:
        charter = {"id": c["id"], "title": c.get("title", ""),
                   "promise": c.get("purpose", ""),
                   "of": len(charters_for(ref))}
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
    # CHOICE surface: a tombstone cannot violate ME with a live sibling, and a
    # retired pair must never become a consolidate merge candidate (I-D5).
    mine = {r: d for r, d in live_refs(domains).items()
            if d.get("tenant_id") == tenant_id}
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

def _load_domain(ref):
    """One domain row straight off disk — the `before` half of every audited
    write. load_domains() would re-read the whole directory for one file."""
    try:
        with open(os.path.join(DOMAINS, ref + ".json"), "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (ValueError, OSError):
        return None


def _changed(before, after):
    """Changed fields ONLY, over the WHOLE row. `_delta()` is deliberately
    narrow (_EVENT_FIELDS + d_path) because a restructure event replays the
    tree; `domain_updated` has to carry whatever the operator actually touched
    — `description`, `design`, `touched_by_operator` — none of which are in
    _EVENT_FIELDS."""
    keys = sorted(set(before) | set(after))
    diff = [k for k in keys if before.get(k) != after.get(k)]
    return (dict((k, before.get(k)) for k in diff),
            dict((k, after.get(k)) for k in diff))


def _save_domain(d, emit=True, event="domain_updated", tenant_id=None):
    """THE domain write path (§9 Phase 0). Locked, and audited by default.

    Every mutation of a `domains/<ref>.json` row goes through here, under
    `_lock('RESTRUCTURE')` — the lock is re-entrant (see `_HELD`), so the
    restructure/retire/unretire internals that already hold it pay nothing.
    `domains_pipeline._set_field` was an UNLOCKED json.load/json.dump pair: it
    lost updates against any concurrent restructure and left no audit row at
    all. It now calls `set_domain_fields()`, which calls this.

    `emit=True` is the default, and the ONLY legitimate `emit=False` is the
    write on the ref that the surrounding event is already ABOUT. The old
    default was the other way round, on the rationale that the restructure
    family appends a richer `domain_restructured` row covering the same
    before/after — but `_domain_snapshot()`/`_delta()` snapshot ONLY the
    retiring `ref`. Every write the operation makes to some OTHER row landed
    with no audit anywhere: `merge`'s append to the surviving target's
    `principles` (permanent, append-only) and every child re-parent, which
    appeared only as a `disposition.children` summary and never as before/after
    on the child's own row. Suppress the subject's write, audit the rest.
    """
    ref = d["ref"]
    with _lock("RESTRUCTURE"):
        prior = _load_domain(ref) if emit else None
        with open(os.path.join(DOMAINS, ref + ".json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, sort_keys=True, indent=2)
        if not emit:
            return d
        b, a = _changed(prior or {}, d)
        if not a:
            return d                      # no-op write: no event, stays idempotent
        _append_jsonl(DOMAIN_INDEX, {
            "event": event, "ref": ref,
            "tenant_id": tenant_id or d.get("tenant_id"),
            "before": b, "after": a, "ts_ms": _now_ms()})
    return d


def set_domain_fields(ref, **fields):
    """Operator-facing field write — the ONLY supported way to change a domain
    row outside the restructure family (§9 Phase 0). Read-modify-write under
    the restructure lock, audited as `domain_updated`."""
    with _lock("RESTRUCTURE"):
        d = _load_domain(ref)
        if d is None:
            raise ValueError("unknown domain ref %r" % ref)
        d.update(fields)
        _save_domain(d, emit=True)
    return d


def _is_descendant(candidate, ancestor, domains):
    """True if `candidate` sits anywhere under `ancestor` in the tree."""
    seen, cur = set(), candidate
    while cur and cur in domains and cur not in seen:
        if cur == ancestor:
            return True
        seen.add(cur)
        cur = domains[cur].get("parent_ref")
    return False


def _reorg_id(ref, op):
    _SEQ[0] += 1
    return "reorg-" + _sha({"ref": ref, "op": op, "ts": _now_ms(),
                            "seq": _SEQ[0], "pid": os.getpid()})[:16]


#: the mutable set §2.5 requires before/after on. `d_path` is RECORDED, never
#: recomputed at replay time — sibling ordinals depend on the tree's membership
#: at that instant.
_EVENT_FIELDS = ("name", "description", "parent_ref", "status", "successor_refs")


def _domain_snapshot(ref, domains):
    d = domains.get(ref) or {}
    snap = dict((k, d.get(k)) for k in _EVENT_FIELDS)
    snap["status"] = d.get("status", "active")
    snap["successor_refs"] = list(d.get("successor_refs") or [])
    snap["d_path"] = domain_path(ref, domains) if ref in domains else None
    return snap


def _delta(before, after):
    """Changed fields only, plus d_path always (replay needs the ordinal)."""
    keys = sorted(k for k in _EVENT_FIELDS + ("d_path",)
                  if k == "d_path" or before.get(k) != after.get(k))
    return (dict((k, before.get(k)) for k in keys),
            dict((k, after.get(k)) for k in keys))


def _mark_retired(d, successor_refs, reason_code, note, event_id, ts_ms):
    """I-D5: the terminal state is a lifecycle stamp, not an unlink."""
    d["status"] = "retired"
    d["successor_refs"] = list(successor_refs)
    d["retired_at_ms"] = ts_ms
    d["retire_reason_code"] = reason_code
    d["retire_note"] = note
    d["disposition_event_id"] = event_id
    return d


def _write_plan_file(name, obj):
    os.makedirs(PLANS, exist_ok=True)
    path = os.path.join(PLANS, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True, indent=2)
    return path


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
    before = _domain_snapshot(ref, domains)
    reorg_id = _reorg_id(ref, op)
    disposition = {"charters": [], "children": []}
    ts = _now_ms()

    # emit=False ONLY on `ref` itself: the `domain_restructured` row below
    # carries its before/after. Every OTHER row this op touches is audited.
    if op == "rename":
        d["name"] = name or d["name"]
        d["touched_by_operator"] = True      # permanent latch: never AUTO-merged again
        _save_domain(d, emit=False)

    elif op == "move":
        if target not in domains:
            return {"ok": False, "error": "unknown target"}
        if target == ref or _is_descendant(target, ref, domains):
            return {"ok": False, "error": "cycle: target is inside the moved subtree"}
        d["parent_ref"] = target
        d["touched_by_operator"] = True
        _save_domain(d, emit=False)
        moved = 0                             # the whole point of stable refs

    elif op in ("merge", "delete"):
        if op == "merge":
            if target not in domains:
                return {"ok": False, "error": "unknown target"}
            if target == ref or _is_descendant(target, ref, domains):
                return {"ok": False, "error": "cycle: target is inside the merged subtree"}
            successor, reason = target, "merged"
        else:
            successor = d.get("parent_ref")
            if successor is None:
                return {"ok": False, "error": "cannot delete the root domain"}
            reason = "deleted"
        if domains.get(successor, {}).get("status", "active") != "active":
            return {"ok": False, "error": "ORG-016: successor %s is not active" % successor}
        # ORG-017, mirroring disposition_report: a cross-tenant merge is the one
        # way to retire a tenant's ONLY root (its whole subtree is inside it, so
        # every same-tenant target trips the cycle check), which then leaves
        # `_root_ref` with no live parent-less node of that tenant to return.
        if domains[successor].get("tenant_id") != d.get("tenant_id"):
            return {"ok": False,
                    "error": "ORG-017: successor %s belongs to another tenant"
                             % successor}
        moved, disposition = _dispose_onto(ref, successor, reason, tenant_id, domains)
        if op == "merge":
            tgt = domains[target]
            tgt["principles"] = (tgt.get("principles") or []) + (d.get("principles") or [])
            tgt["touched_by_operator"] = True
            _save_domain(tgt)     # AUDITED: the event's before/after covers `ref`, not the target
        # I-D5: the file STAYS. Both os.remove() calls that used to live here
        # are what stranded every charter and CURRENT row citing this ref.
        _mark_retired(d, [successor], reason, None, reorg_id, ts)
        _save_domain(d, emit=False)
    else:
        return {"ok": False, "error": "unknown op"}

    after = _domain_snapshot(ref, load_domains())
    b, a = _delta(before, after)
    _append_jsonl(DOMAIN_INDEX, {"event": "domain_restructured", "op": op,
                                 "reorg_id": reorg_id, "tenant_id": tenant_id,
                                 "ref": ref, "target": target,
                                 "placements_repointed": moved,
                                 "retire_reason_code": d.get("retire_reason_code"),
                                 "before": b, "after": a,
                                 "disposition": disposition, "ts_ms": ts})
    return {"ok": True, "op": op, "reorg_id": reorg_id,
            "placements_repointed": moved, "before": b, "after": a,
            "disposition": disposition}


def _dispose_onto(ref, successor, reason, tenant_id, domains):
    """Move everything ref owns onto `successor`, in the only safe order:
    charters first (placements must cite a charter that already resolves),
    then current placements, then CHILD DOMAINS.

    The child loop existed only on DELETE (`:787-790`); MERGE orphaned every
    subtree it absorbed — ORG-003, lifted here so both ops share one path.
    """
    disposition = {"charters": [], "children": []}
    current = _current_placements()
    by_charter = {}
    for p in current:
        by_charter.setdefault(p.get("charter_id"), []).append(p)

    charter_map = {}
    ts = _now_ms()
    for c in sorted(charters_for(ref), key=lambda c: c["id"]):
        new_cid = _mint_successor_charter(c, successor, reason,
                                          len(by_charter.get(c["id"]) or []))
        charter_map[c["id"]] = new_cid
        # §0.12: the old C-hash file is NEVER rewritten, and §2.2's shipped
        # status enum is NOT overloaded either. Supersession is DERIVED from
        # `supersedes` (see superseded_ids()); flipping the source to `retired`
        # made a merged department's history read as "retired work" and dropped
        # it out of the charter table's default `active` filter, and left
        # merge/delete and `retire()` (which deliberately does not flip source
        # sidecars, so unretire can restore placements onto them) with two
        # different on-disk states for one logical transition. The disposition
        # rides the `lifecycle` key the sidecar already uses for
        # reverted/orphaned/repaired, plus the charters/INDEX.jsonl row.
        sc = load_sidecar(c["id"])
        sc["lifecycle"] = "superseded"
        save_sidecar(c["id"], sc)
        _append_jsonl(CHARTER_INDEX, {
            "event": "charter_reassigned", "id": c["id"],
            "successor_id": new_cid, "from_domain_ref": ref,
            "to_domain_ref": successor, "status": sc.get("status", "active"),
            "lifecycle": "superseded", "reason": reason,
            "tenant_id": c.get("tenant_id", tenant_id), "ts_ms": ts})
        disposition["charters"].append({"id": c["id"], "to": successor,
                                        "successor_id": new_cid})
    moved = 0
    for p in current:
        if p.get("domain_ref") != ref:
            continue
        write_placement(p["work_ref"], successor,
                        charter_map.get(p.get("charter_id"), p.get("charter_id")),
                        "matched", p.get("confidence", 0.5),
                        {"domains": [], "charters": []}, tenant_id,
                        supersedes=p["id"], phase="post-close")
        moved += 1
    for cref, cd in sorted(domains.items()):
        if cd.get("parent_ref") == ref:
            cd["parent_ref"] = successor
            _save_domain(cd)
            disposition["children"].append({"ref": cref, "to": successor})
    return moved, disposition


# --------------------------------------------------------------- lifecycle --

def disposition_report(ref, successor_ref=None, domains=None):
    """What retiring `ref` would strand, and whether anything is unmapped.

    Checklist, not a confirm dialog (§3.4): every charter, every child domain
    and every current placement needs a destination before the verb may run.
    On the CLI one `--successor` maps all of them; the per-item `to` rows are
    still the authoritative mapping, and `successor_refs` is the summary.
    """
    domains = domains if domains is not None else load_domains()
    rep = {"ref": ref, "name": None, "successor_ref": successor_ref,
           "prior_status": None, "charters": [], "children": [],
           "placements": [], "unmapped": 0, "blocks": []}
    if ref not in domains:
        rep["blocks"].append({"code": "ORG-000",
                              "message": "unknown domain ref %s" % ref})
        return rep
    d = domains[ref]
    rep["name"] = d.get("name", "")
    rep["prior_status"] = d.get("status", "active")
    if d.get("parent_ref") is None:
        rep["blocks"].append({"code": "ORG-003",
                              "message": "cannot retire the root domain"})
    if successor_ref is not None:
        why = None
        if successor_ref not in domains:
            why = "successor %s does not resolve" % successor_ref
        elif successor_ref == ref or _is_descendant(successor_ref, ref, domains):
            why = "successor %s is inside the retiring subtree" % successor_ref
        elif domains[successor_ref].get("status", "active") != "active":
            why = "successor %s is not active" % successor_ref
        if why:
            rep["blocks"].append({"code": "ORG-016", "message": why})
            successor_ref = None
        elif domains[successor_ref].get("tenant_id") != d.get("tenant_id"):
            rep["blocks"].append({
                "code": "ORG-017",
                "message": "successor %s belongs to another tenant" % successor_ref})
            successor_ref = None
    for c in sorted(charters_for(ref), key=lambda c: c["id"]):
        rep["charters"].append({"id": c["id"], "title": c.get("title", ""),
                                "to": successor_ref})
    for cref, cd in sorted(domains.items()):
        if cd.get("parent_ref") == ref:
            rep["children"].append({"ref": cref, "name": cd.get("name", ""),
                                    "to": successor_ref})
    for p in _current_placements():
        if p.get("domain_ref") == ref:
            rep["placements"].append({"id": p["id"],
                                      "work_ref_id": (p.get("work_ref") or {}).get("id"),
                                      "charter_id": p.get("charter_id"),
                                      "to": successor_ref})
    rep["unmapped"] = sum(1 for grp in ("charters", "children", "placements")
                          for it in rep[grp] if not it.get("to"))
    for grp, code, what in (("charters", "ORG-002", "charters"),
                            ("children", "ORG-003", "child domains"),
                            ("placements", "ORG-004", "current placements")):
        n = sum(1 for it in rep[grp] if not it.get("to"))
        if n:
            rep["blocks"].append({
                "code": code,
                "message": "%d %s on the retiring domain have no successor "
                           "mapping" % (n, what)})
    rep["blocked"] = bool(rep["blocks"] or rep["unmapped"])
    return rep


def retire(ref, successor_ref=None, note=None, reason_code="superseded",
           tenant_id="T-local"):
    """Terminal lifecycle transition. The file is KEPT (I-D5).

    Exits 2 (ok=False, exit=2) with the disposition report while anything
    dangles. Writes the recovery manifest to plans/retire-<dref>-<ts>.json
    BEFORE mutating, so `unretire --from` is possible even if the process dies
    halfway through.
    """
    _ensure_dirs()
    if reason_code not in RETIRE_REASON_CODES:
        return {"ok": False, "exit": 2,
                "error": "retire_reason_code must be one of %s"
                         % (list(RETIRE_REASON_CODES),)}
    if reason_code == "reconstructed":
        return {"ok": False, "exit": 2,
                "error": "reason 'reconstructed' is reserved for `reconcile` — "
                         "it asserts the row was never authored, only inferred"}
    with _lock("RESTRUCTURE"):
        domains = load_domains()
        rep = disposition_report(ref, successor_ref, domains)
        if rep["blocked"]:
            return {"ok": False, "exit": 2, "error": "disposition incomplete",
                    "report": rep}
        d = domains[ref]
        if d.get("status", "active") == "retired":
            return {"ok": False, "exit": 2, "error": "domain is already retired",
                    "report": rep}
        ts = _now_ms()
        reorg_id = _reorg_id(ref, "retire")
        before = _domain_snapshot(ref, domains)
        current = [p for p in _current_placements() if p.get("domain_ref") == ref]

        # ---- pre-mutation manifest: recovery must not depend on success ----
        manifest = {
            "kind": "retire-manifest", "version": 1, "ref": ref,
            "reorg_id": reorg_id, "ts_ms": ts,
            "tenant_id": d.get("tenant_id", tenant_id),
            "successor_ref": successor_ref, "reason_code": reason_code,
            "note": note, "prior_domain": json.loads(json.dumps(d)),
            "charters": [dict(c) for c in rep["charters"]],
            "children": [dict(c) for c in rep["children"]],
            "placements": [{"id": p["id"], "work_ref": p.get("work_ref"),
                            "charter_id": p.get("charter_id"),
                            "confidence": p.get("confidence", 0.5)}
                           for p in current],
            "applied": None,
        }
        mpath = _write_plan_file("retire-%s-%d.json" % (ref, ts), manifest)

        applied = {"charters": [], "placements": [], "children": [], "ts_ms": ts}
        by_charter = {}
        for p in _current_placements():
            by_charter.setdefault(p.get("charter_id"), []).append(p)
        charter_map = {}
        for item in rep["charters"]:
            body = load_charter(item["id"])
            if not body:
                continue
            new_cid = _mint_successor_charter(body, item["to"],
                                              note or reason_code,
                                              len(by_charter.get(item["id"]) or []))
            charter_map[item["id"]] = new_cid
            item["successor_id"] = new_cid
            applied["charters"].append({"id": item["id"],
                                        "successor_id": new_cid, "to": item["to"]})
            _append_jsonl(CHARTER_INDEX, {
                "event": "charter_reassigned", "id": item["id"],
                "successor_id": new_cid, "from_domain_ref": ref,
                "to_domain_ref": item["to"], "reorg_id": reorg_id,
                "reason": reason_code, "note": note,
                "tenant_id": d.get("tenant_id", tenant_id), "ts_ms": ts})
        for p in current:
            body = write_placement(
                p["work_ref"], successor_ref,
                charter_map.get(p.get("charter_id"), p.get("charter_id")),
                "matched", p.get("confidence", 0.5),
                {"domains": [], "charters": []}, tenant_id,
                supersedes=p["id"], phase="post-close")
            applied["placements"].append({"from": p["id"], "to": body["id"]})
        for item in rep["children"]:
            cd = domains.get(item["ref"])
            if cd is None:
                continue
            cd["parent_ref"] = item["to"]
            _save_domain(cd)
            applied["children"].append({"ref": item["ref"], "to": item["to"]})

        _mark_retired(d, [successor_ref] if successor_ref else [],
                      reason_code, note, reorg_id, ts)
        _save_domain(d, emit=False)   # `ref` is the subject of the event below

        after = _domain_snapshot(ref, load_domains())
        b, a = _delta(before, after)
        _append_jsonl(DOMAIN_INDEX, {
            "event": "domain_restructured", "op": "retire",
            "reorg_id": reorg_id, "tenant_id": d.get("tenant_id", tenant_id),
            "ref": ref, "target": successor_ref,
            "placements_repointed": len(applied["placements"]),
            "retire_reason_code": reason_code, "before": b, "after": a,
            "disposition": {"charters": applied["charters"],
                            "children": applied["children"]},
            "manifest": mpath, "ts_ms": ts})

        manifest["applied"] = applied
        _write_plan_file("retire-%s-%d.json" % (ref, ts), manifest)
        return {"ok": True, "ref": ref, "reorg_id": reorg_id,
                "manifest": mpath, "successor_refs": d["successor_refs"],
                "placements_repointed": len(applied["placements"]),
                "charters_superseded": len(applied["charters"]),
                "children_reparented": len(applied["children"]),
                "report": rep}


def unretire(ref, manifest_path, tenant_id="T-local"):
    """Undo a retire from its manifest. Append-only, therefore always safe.

    It CANNOT delete the successor charters the retire minted — I-D5 and
    content addressing both forbid it — so each is marked lifecycle='reverted'
    in its sidecar and the superseded-by chip derives itself off.
    """
    _ensure_dirs()
    if not manifest_path or not os.path.exists(manifest_path):
        return {"ok": False, "exit": 2, "error": "manifest not found: %r" % manifest_path}
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            man = json.load(fh)
    except (ValueError, OSError) as exc:
        return {"ok": False, "exit": 2, "error": "unreadable manifest: %s" % exc}
    if man.get("kind") != "retire-manifest" or man.get("ref") != ref:
        return {"ok": False, "exit": 2,
                "error": "manifest does not describe a retire of %s" % ref}

    with _lock("RESTRUCTURE"):
        domains = load_domains()
        if ref not in domains:
            return {"ok": False, "exit": 2, "error": "unknown domain ref"}
        d = domains[ref]
        if d.get("status", "active") != "retired":
            return {"ok": False, "exit": 2, "error": "domain is not retired"}
        parent = d.get("parent_ref")
        if parent is not None and domains.get(parent, {}).get("status", "active") != "active":
            return {"ok": False, "exit": 2,
                    "error": "ORG-016: parent %s is not active" % parent}
        norm = (d.get("name") or "").strip().lower()
        for r2, d2 in domains.items():
            if (r2 != ref and d2.get("parent_ref") == parent
                    and d2.get("status", "active") != "retired"
                    and (d2.get("name") or "").strip().lower() == norm):
                return {"ok": False, "exit": 2,
                        "error": "ORG-018: live sibling %s already holds the "
                                 "name %r" % (r2, d.get("name"))}

        ts = _now_ms()
        reorg_id = _reorg_id(ref, "unretire")
        before = _domain_snapshot(ref, domains)
        d["status"] = "active"
        d["successor_refs"] = []
        d["retired_at_ms"] = None
        d["retire_reason_code"] = None
        d["retire_note"] = None
        d["disposition_event_id"] = None
        _save_domain(d, emit=False)   # `ref` is the subject of the event below

        applied = man.get("applied") or {}
        children = 0
        for item in applied.get("children") or man.get("children") or []:
            cd = domains.get(item.get("ref"))
            if cd is not None and cd.get("parent_ref") == item.get("to"):
                cd["parent_ref"] = ref
                _save_domain(cd)
                children += 1
        reverted = []
        for item in applied.get("charters") or []:
            new_cid = item.get("successor_id")
            if not new_cid:
                continue
            sc = load_sidecar(new_cid)
            sc["lifecycle"] = "reverted"
            save_sidecar(new_cid, sc)
            reverted.append(new_cid)
            _append_jsonl(CHARTER_INDEX, {
                "event": "charter_reverted", "id": new_cid,
                "supersedes": item.get("id"), "reorg_id": reorg_id,
                "restored_domain_ref": ref, "ts_ms": ts})
        restored = 0
        for item in man.get("placements") or []:
            work_ref = item.get("work_ref") or {}
            if not work_ref.get("id"):
                continue
            write_placement(work_ref, ref, item.get("charter_id"), "matched",
                            item.get("confidence", 0.5),
                            {"domains": [], "charters": []},
                            man.get("tenant_id", tenant_id), phase="post-close")
            restored += 1

        after = _domain_snapshot(ref, load_domains())
        b, a = _delta(before, after)
        _append_jsonl(DOMAIN_INDEX, {
            "event": "domain_restructured", "op": "unretire",
            "reorg_id": reorg_id, "tenant_id": man.get("tenant_id", tenant_id),
            "ref": ref, "target": None, "placements_repointed": restored,
            "retire_reason_code": None, "before": b, "after": a,
            "disposition": {"charters": [{"id": c, "to": None} for c in reverted],
                            "children": [{"ref": i.get("ref"), "to": ref}
                                         for i in (applied.get("children") or [])]},
            "manifest": manifest_path, "ts_ms": ts})
        return {"ok": True, "ref": ref, "reorg_id": reorg_id,
                "placements_restored": restored,
                "children_restored": children,
                "charters_reverted": reverted,
                "from_manifest": manifest_path}


def charter_retire(charter_id, note=None, tenant_id="T-local"):
    """§3.5. Flips the EXISTING sidecar status enum to `retired` and appends to
    charters/INDEX.jsonl. The hashed body is never touched; no file is removed."""
    _ensure_dirs()
    body = load_charter(charter_id)
    if body is None:
        return {"ok": False, "exit": 2, "error": "unknown charter id %r" % charter_id}
    with _lock("RESTRUCTURE"):
        sc = load_sidecar(charter_id)
        prior = sc.get("status", "active")
        sc["status"] = "retired"
        save_sidecar(charter_id, sc)
        ts = _now_ms()
        _append_jsonl(CHARTER_INDEX, {
            "event": "charter_retired", "id": charter_id,
            "domain_ref": body.get("domain_ref"), "before_status": prior,
            "after_status": "retired", "note": note,
            "tenant_id": body.get("tenant_id", tenant_id), "ts_ms": ts})
    return {"ok": True, "id": charter_id, "before_status": prior,
            "status": "retired", "sidecar": _sidecar_path(charter_id)}


def charter_reassign(charter_id, target_ref, note=None, tenant_id="T-local"):
    """§3.5. Mints a SUCCESSOR charter homed to `target_ref` with `supersedes`
    set — never rewrites domain_ref on the old C-hash — and repoints every
    current placement citing the old charter with phase='post-close'."""
    _ensure_dirs()
    body = load_charter(charter_id)
    if body is None:
        return {"ok": False, "exit": 2, "error": "unknown charter id %r" % charter_id}
    with _lock("RESTRUCTURE"):
        domains = load_domains()
        if target_ref not in domains:
            return {"ok": False, "exit": 2,
                    "error": "target domain %r does not resolve" % target_ref}
        if domains[target_ref].get("status", "active") != "active":
            return {"ok": False, "exit": 2,
                    "error": "ORG-016: target %s is not active" % target_ref}
        if domains[target_ref].get("tenant_id") != body.get("tenant_id", tenant_id):
            return {"ok": False, "exit": 2,
                    "error": "ORG-017: target %s belongs to another tenant" % target_ref}
        if body.get("domain_ref") == target_ref:
            return {"ok": False, "exit": 2,
                    "error": "charter is already homed to %s" % target_ref}
        citing = [p for p in _current_placements()
                  if p.get("charter_id") == charter_id]
        new_cid = _mint_successor_charter(body, target_ref,
                                          note or "charter reassign", len(citing))
        moved = 0
        for p in citing:
            write_placement(p["work_ref"], target_ref, new_cid, "matched",
                            p.get("confidence", 0.5),
                            {"domains": [], "charters": []}, tenant_id,
                            supersedes=p["id"], phase="post-close")
            moved += 1
        # The source keeps its shipped status (§2.2: the enum is UNCHANGED by
        # this design and no `superseded` value is introduced). Supersession is
        # DERIVED from `supersedes` — `pick_charter` reads it, so the source
        # stops receiving new work without its history being relabelled
        # "retired". The disposition rides `lifecycle`, not the status enum.
        sc = load_sidecar(charter_id)
        status = sc.get("status", "active")
        sc["lifecycle"] = "superseded"
        save_sidecar(charter_id, sc)
        ts = _now_ms()
        _append_jsonl(CHARTER_INDEX, {
            "event": "charter_reassigned", "id": charter_id,
            "successor_id": new_cid, "from_domain_ref": body.get("domain_ref"),
            "to_domain_ref": target_ref, "placements_repointed": moved,
            "status": status, "lifecycle": "superseded",
            "note": note, "tenant_id": body.get("tenant_id", tenant_id),
            "ts_ms": ts})
    return {"ok": True, "id": charter_id, "successor_id": new_cid,
            "from_domain_ref": body.get("domain_ref"),
            "to_domain_ref": target_ref, "placements_repointed": moved,
            "status": status, "lifecycle": "superseded",
            "sidecar": _sidecar_path(new_cid)}


def verify_charters(limit=200):
    """Re-hash every charter body with `id` excluded (§2.2 / Phase 0).

    Reports the mismatch count so the pre-fix damage is MEASURABLE: every
    project charter minted through the old post-mint rewrite loops fails, and
    that number is the baseline the Phase 0 proof measures against. Bodies with
    no `schema` key are v1 and verify under the same rule.
    """
    _ensure_dirs()
    checked, mismatches, legacy = 0, [], 0
    for fn in charter_body_files():
        try:
            with open(os.path.join(CHARTERS, fn), "r", encoding="utf-8") as fh:
                body = json.load(fh)
        except (ValueError, OSError) as exc:
            mismatches.append({"file": fn, "id": None, "expected_id": None,
                               "reason": "unreadable: %s" % exc})
            checked += 1
            continue
        if not isinstance(body, dict):
            mismatches.append({"file": fn, "id": None, "expected_id": None,
                               "reason": "not an object"})
            checked += 1
            continue
        checked += 1
        cid = body.get("id") or fn[:-len(".json")]
        expected = charter_id_of(body)
        if expected == cid:
            continue
        sc = {}
        try:
            with open(_sidecar_path(cid), "r", encoding="utf-8") as fh:
                sc = json.load(fh) or {}
        except (ValueError, OSError):
            sc = {}
        if sc.get("legacy_hash"):
            legacy += 1                 # grandfathered by migrate; not a defect
            continue
        mismatches.append({
            "file": fn, "id": cid, "expected_id": expected,
            "schema": body.get("schema", 1),
            "mutable_keys_in_body": sorted(k for k in _LEGACY_BODY_KEYS
                                           if k in body),
            "reason": "body does not hash to its own id"})
    mismatches.sort(key=lambda m: m["file"])
    return {"ok": not mismatches, "checked": checked,
            "mismatched": len(mismatches), "grandfathered_legacy": legacy,
            "mismatches": mismatches if limit is None else mismatches[:limit]}


def _charter_first_seen():
    """charter_id -> the earliest ms we can VOUCH for, from history only.

    charters/INDEX.jsonl rows and placement `ts_ms` are the two surfaces that
    dated a charter before sidecars existed. Anything absent from both stays
    absent — §2.2 wants "which charters existed in June" answerable, and a
    fabricated date answers it wrongly, which is worse.
    """
    seen = {}

    def _bump(cid, ts):
        if cid and ts and (cid not in seen or ts < seen[cid]):
            seen[cid] = ts

    for row in _read_jsonl(CHARTER_INDEX):
        _bump(row.get("id"), row.get("ts_ms"))
        _bump(row.get("successor_id"), row.get("ts_ms"))
    for p in all_placements():
        _bump(p.get("charter_id"), p.get("ts_ms"))
    return seen


def backfill_sidecars(dry_run=False):
    """Give EVERY charter body a sidecar — not only the mismatched ones.

    `migrate_charters` only ever wrote sidecars for charters on
    `verify_charters`'s mismatch list, but an engine-minted v1 stub that nobody
    ever rewrote hashes correctly, so it was never migrated and never got one.
    With `load_sidecar`'s fallback that made its `ts_ms` unknown forever; the
    fallback no longer fabricates one, and this makes the unknown recoverable
    where history knows the answer. Idempotent: an existing sidecar is never
    touched.
    """
    _ensure_dirs()
    seen, written = None, []
    for fn in charter_body_files():
        cid = fn[:-len(".json")]
        if os.path.exists(_sidecar_path(cid)):
            continue
        if seen is None:
            seen = _charter_first_seen()
        written.append({"id": cid, "ts_ms": seen.get(cid)})
        if dry_run:
            continue
        body = load_charter(cid) or {}
        sc = _sidecar_default(seen.get(cid))
        for k in _SIDECAR_KEYS:      # a pre-split body may still carry them
            if k in body:
                sc[k] = body[k]
        if sc.get("status") not in CHARTER_STATUSES:
            sc["status"] = "active"
        save_sidecar(cid, sc)
    return written


def migrate_charters(dry_run=False):
    """One-time legacy split: hash-stable body + sidecar, id UNCHANGED (§2.2).

    Semantics, and why the id is grandfathered rather than re-minted: a C-id is
    cited by placements (I-P2 rejects an unresolvable charter_id) and is the
    filename of C-<id>.html, which domains_page calls stable forever. Re-minting
    would orphan both. So for each mismatched charter:

      1. the operator-mutable set is lifted into charters/<C-id>.page.json
         (an existing sidecar always wins — it is the newer writer);
      2. `_LEGACY_BODY_KEYS` are stripped from the body. Those are EXACTLY the
         keys the two post-mint rewrite loops added, so for damage of that kind
         the stripped body hashes to its own id again — 'reconciled', a true
         repair, not a fudge;
      3. if it still does not hash (damage from elsewhere, e.g. the old merge
         `domain_ref` rewrite whose original body is unrecoverable), the id is
         kept anyway and the sidecar records `legacy_hash: true` plus
         `legacy_expected_id` — 'grandfathered'. verify-charters then passes it
         and the deviation stays on the record instead of being erased.

    `kind` is a HASHED-body field for new charters, but on a legacy body it was
    written post-mint, so it is stripped with the rest and preserved in the
    sidecar; charter_view() merges it back and nothing renders differently.
    No file is ever removed (I-D5's charter-side twin).
    """
    _ensure_dirs()
    rep = verify_charters(limit=None)
    out = {"dry_run": bool(dry_run), "checked": rep["checked"],
           "mismatched_before": rep["mismatched"],
           "reconciled": [], "grandfathered": [], "unreadable": []}
    if dry_run:
        for m in rep["mismatches"]:
            if not m.get("id"):
                out["unreadable"].append(m["file"])
                continue
            (out["reconciled"] if m.get("mutable_keys_in_body")
             else out["grandfathered"]).append(m["id"])
        out["sidecars_backfilled"] = [r["id"] for r in backfill_sidecars(True)]
        return out
    ts = _now_ms()
    with _lock("RESTRUCTURE"):
        for m in rep["mismatches"]:
            cid = m.get("id")
            if not cid:
                out["unreadable"].append(m["file"])
                continue
            path = os.path.join(CHARTERS, cid + ".json")
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    body = json.load(fh)
            except (ValueError, OSError):
                out["unreadable"].append(m["file"])
                continue
            sc = load_sidecar(cid)      # seeds from the body when absent
            for k in _LEGACY_BODY_KEYS:
                # an existing sidecar is the newer writer and wins — but its
                # DEFAULTS (empty list, absent key) must not shadow real data
                # sitting in the body, or migration silently drops artifacts.
                if k in body and not sc.get(k):
                    sc[k] = body[k]
            sc["kind"] = sc.get("kind") or body.get("kind") or "standing"
            if sc.get("status") not in CHARTER_STATUSES:
                sc["status"] = "active"
            body = dict((k, v) for k, v in body.items()
                        if k not in _LEGACY_BODY_KEYS)
            body["id"] = cid
            expected = charter_id_of(body)
            if expected == cid:
                sc.pop("legacy_hash", None)
                sc.pop("legacy_expected_id", None)
                out["reconciled"].append(cid)
                event = "charter_migrated"
            else:
                sc["legacy_hash"] = True
                sc["legacy_expected_id"] = expected
                out["grandfathered"].append(cid)
                event = "charter_grandfathered"
            save_sidecar(cid, sc)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(body, fh, sort_keys=True, indent=2)
            _append_jsonl(CHARTER_INDEX, {
                "event": event, "id": cid, "domain_ref": body.get("domain_ref"),
                "expected_id": expected, "schema_before": m.get("schema", 1),
                "moved_to_sidecar": m.get("mutable_keys_in_body") or [],
                "tenant_id": body.get("tenant_id"), "ts_ms": ts})
        # every REMAINING body gets one too — a hash-clean legacy stub never
        # appeared on the mismatch list and so never got a sidecar at all.
        out["sidecars_backfilled"] = [r["id"] for r in backfill_sidecars()]
    after = verify_charters()
    out["mismatched_after"] = after["mismatched"]
    out["grandfathered_legacy"] = after["grandfathered_legacy"]
    out["ok"] = after["ok"]
    return out


# --------------------------------------------------------------- recovery ---
#
# reconcile + repair are the v1 DAMAGE-RECOVERY path (§2.10, §0.15). They are
# not part of the steady-state lifecycle: both exist only because MERGE and
# DELETE used to call os.remove() on domains/<ref>.json, and that damage is
# already on every registry that ran the old code. Deleting os.remove stops new
# damage; these two verbs address the old damage, and both are idempotent so
# they can be re-run after any subsequent discovery.


def _index_history():
    """ref -> {parent_ref, name, tenant_id, ts_ms} recovered from INDEX.jsonl.

    The append-only domain log is the ONLY surviving trace of a row the
    pre-I-D5 os.remove() unlinked. Later rows win: `domain_minted` carries the
    mint-time parent, `domain_restructured`'s before/after carry any later
    re-parent (`after` last, so it wins within a row).
    """
    hist = {}
    for row in _read_jsonl(DOMAIN_INDEX):
        ref = row.get("ref")
        if not ref:
            continue
        h = hist.setdefault(ref, {})
        for k in ("name", "tenant_id", "ts_ms"):
            if row.get(k):
                h[k] = row[k]
        if row.get("parent_ref"):
            h["parent_ref"] = row["parent_ref"]
        for half in ("before", "after"):
            blob = row.get(half)
            if not isinstance(blob, dict):
                continue
            if blob.get("parent_ref"):
                h["parent_ref"] = blob["parent_ref"]
            if blob.get("name"):
                h["name"] = blob["name"]
    return hist


def _cited_domain_refs():
    """ref -> citation counts, over EVERY placement citation on disk.

    Both surfaces are read: CURRENT.jsonl rows (the append-only log, including
    superseded rows — a stale row citing a destroyed domain is exactly the
    damage §0.3 describes) and the PL-<sha> bodies.
    """
    cited = {}

    def _bump(ref, key, tenant):
        c = cited.setdefault(ref, {"ref": ref, "current_rows": 0,
                                   "placements": 0, "tenant_id": None})
        c[key] += 1
        if tenant and not c["tenant_id"]:
            c["tenant_id"] = tenant
        return c

    for row in _read_jsonl(CURRENT):
        if row.get("domain_ref"):
            _bump(row["domain_ref"], "current_rows", row.get("tenant_id"))
    for p in all_placements():
        if p.get("domain_ref"):
            _bump(p["domain_ref"], "placements", p.get("tenant_id"))
    return cited


def _tenant_root(tenant_id, domains):
    """The live root to hang unrecoverable things under. Prefers the tenant's
    own root; falls back to any root rather than manufacturing a SECOND
    parent-less node, which the site generator reads as the tree's root."""
    for ref, d in sorted(domains.items()):
        if (d.get("parent_ref") is None and d.get("tenant_id") == tenant_id
                and d.get("status", "active") != "retired"):
            return ref
    for ref, d in sorted(domains.items()):
        if d.get("parent_ref") is None and d.get("status", "active") != "retired":
            return ref
    return None


def reconcile(tenant_id="T-local", dry_run=False):
    """Tombstone backfill for pre-I-D5 os.remove() damage (§2.10). IDEMPOTENT.

    Every `domain_ref` that placement history asserts existed but that has no
    `domains/<ref>.json` gets ONE minimal tombstone, so the ref resolves again
    — as a `retired` node that accepts no new work, which is what it already
    was. Without this, `lint --full` reports those rows forever and there is no
    legal way to clear them: I-D5 forbids deleting the placement history that
    cites them, and the destroyed row cannot be re-authored.

    Three deliberate choices:

    * **The name is `[unrecovered] <ref>`, not `(recovered)`.** The row is NOT a
      reconstruction — name, description, principles and mint_evidence are all
      gone. A tombstone that reads as recovered data is worse than the dangling
      ref it replaces, because the dangling ref at least announces itself.
    * **`ts_minted_ms` is NOW, not the recovered mint time.** Sibling ordinals
      are ordered by `ts_minted_ms`, so back-dating a tombstone would slot it
      into the middle of its parent's sibling list and RENUMBER every live
      sibling after it — breaking D-number permanence, the one property I-D5
      exists to protect. The recovered timestamp is kept as
      `recovered_ts_minted_ms` for the record.
    * **The recovered parent is used only if it resolves to a row on disk
      today.** Chaining tombstone onto tombstone could re-create a cycle out of
      a log that no longer describes a consistent tree; anything unresolvable
      lands on the tenant root. `resolution` records which happened.
    """
    _ensure_dirs()
    with _lock("RESTRUCTURE"):
        domains = load_domains()
        cited = _cited_domain_refs()
        missing = sorted(r for r in cited if r not in domains)
        out = {"ok": True, "dry_run": bool(dry_run), "tenant_id": tenant_id,
               "cited_refs": len(cited), "already_resolved": len(cited) - len(missing),
               "minted": [], "skipped": []}
        if not missing:
            return out
        root = _tenant_root(tenant_id, domains)
        if root is None:
            out["ok"] = False
            out["error"] = ("no live root domain — nothing to re-home %d "
                            "tombstone(s) under" % len(missing))
            return out
        hist = _index_history()
        ts = _now_ms()
        for ref in missing:
            h = hist.get(ref) or {}
            hinted = h.get("parent_ref")
            if hinted and hinted in domains and hinted != ref:
                parent, how = hinted, "index-parent"
            else:
                parent, how = root, "root-fallback"
            tid = (cited[ref].get("tenant_id") or h.get("tenant_id")
                   or domains.get(parent, {}).get("tenant_id") or tenant_id)
            doc = {
                "ref": ref,
                "name": "[unrecovered] %s" % ref,
                "parent_ref": parent,
                "principles": [],
                "accountable": "tenant_owner",
                "authority": {},
                "tenant_id": tid,
                "origin": "system-minted",
                "touched_by_operator": False,
                "mint_evidence": ["recovered"],
                "ts_minted_ms": ts,
                "recovered": True,
                "recovered_ts_minted_ms": h.get("ts_ms"),
                "recovered_name": h.get("name"),
                "status": "retired",
                "successor_refs": [],
                "retired_at_ms": ts,
                "retire_reason_code": "reconstructed",
                "retire_note": "minted by reconcile: the original row was "
                               "destroyed by the pre-I-D5 os.remove() path",
                "disposition_event_id": None,
            }
            row = {"ref": ref, "parent_ref": parent, "resolution": how,
                   "current_rows": cited[ref]["current_rows"],
                   "placements": cited[ref]["placements"],
                   "tenant_id": tid}
            out["minted"].append(row)
            if dry_run:
                continue
            # emit=False: `domain_reconstructed` below IS this row's event, and
            # a before/after over an empty prior is noise, not audit.
            _save_domain(doc, emit=False)
            _append_jsonl(DOMAIN_INDEX, {
                "event": "domain_reconstructed", "ref": ref,
                "parent_ref": parent, "resolution": how, "tenant_id": tid,
                "cited_by": {"current_rows": cited[ref]["current_rows"],
                             "placements": cited[ref]["placements"]},
                "recovered_name": h.get("name"),
                "retire_reason_code": "reconstructed", "ts_ms": ts})
        return out


def _live_destination(ref, domains, root):
    """Where work homed at `ref` belongs now -> (dest_ref, how).

    I-D5's succession-liveness corollary: a chain of retirements resolves
    TRANSITIVELY at read time, never by rewriting `successor_refs`. So follow
    successor_refs[0] to the first live node; if the chain dead-ends (or never
    existed — pre-I-D5 rows have none) fall back to the nearest live ancestor,
    and only then to the root.
    """
    seen, cur = set(), ref
    while cur and cur not in seen:
        seen.add(cur)
        d = domains.get(cur)
        if d is None:
            break
        if d.get("status", "active") != "retired":
            return cur, ("home" if cur == ref else "successor")
        succ = [s for s in (d.get("successor_refs") or []) if s]
        cur = succ[0] if succ else None
    parent = (domains.get(ref) or {}).get("parent_ref")
    anc = _nearest_live_ancestor(parent, domains) if parent else None
    if anc:
        return anc, "ancestor"
    return root, "root"


def repair(tenant_id="T-local", dry_run=False):
    """Orphan-charter re-home — the §0.15 DELETE bug. IDEMPOTENT.

    DELETE re-pointed placements and re-parented child domains but had NO
    charter loop, unlike MERGE. Every charter on a previously deleted domain is
    therefore unreachable through `charters_for()` and renders nowhere. This
    sweep re-homes each one to the nearest LIVE destination.

    Re-homing mints a SUCCESSOR with `supersedes` set (`charter_reassign`'s
    primitive) — it never rewrites `domain_ref` inside the old C-hash file,
    which is the §0.12 bug that stopped charters hashing to their own ids. The
    original body stays exactly where it is; its sidecar records where it went.

    Two things make it idempotent, and BOTH are load-bearing:

    * `repaired_successor_id` on the source sidecar — content addressing alone
      makes a second run mint the same successor id, but the COUNTS have to
      stop moving too or "reports counts" means nothing.
    * **Anything already superseded is skipped.** A legitimately merged or
      retired domain is `retired` with its charters' successors already minted
      by `_dispose_onto`/`retire`. Those sources are homed to a retired domain
      forever — by design — so without this guard `repair` would mint a second
      successor for every charter after every merge, for the rest of time.
      The test is derived from content (`supersedes` on some other body), not
      from bookkeeping, so it holds for charters moved before this verb existed.

    Placements are deliberately NOT re-pointed here. A current placement citing
    the orphan charter still resolves once `reconcile` has tombstoned its
    domain, and moving live work is `retire` / `charter reassign` — an operator
    verb with a disposition report, not a recovery sweep.
    """
    _ensure_dirs()
    with _lock("RESTRUCTURE"):
        domains = load_domains()
        root = _tenant_root(tenant_id, domains)
        by_charter = {}
        for p in _current_placements():
            by_charter.setdefault(p.get("charter_id"), []).append(p)
        out = {"ok": True, "dry_run": bool(dry_run), "tenant_id": tenant_id,
               "scanned": 0, "orphans": 0, "already_repaired": 0,
               "repaired": [], "unresolvable": []}
        bodies = {}
        superseded = set()
        for fn in charter_body_files():
            body = load_charter(fn[:-len(".json")])
            if not body:
                continue
            bodies[fn] = body
            if body.get("supersedes"):
                superseded.add(body["supersedes"])
        ts = _now_ms()
        for fn in sorted(bodies):
            body = bodies[fn]
            cid = body.get("id") or fn[:-len(".json")]
            ctid = body.get("tenant_id", tenant_id)
            if ctid != tenant_id:
                continue
            out["scanned"] += 1
            dref = body.get("domain_ref")
            home = domains.get(dref)
            if home is not None and home.get("status", "active") != "retired":
                continue                      # homed to a live domain: nothing to do
            out["orphans"] += 1
            sc = load_sidecar(cid)
            done = sc.get("repaired_successor_id")
            if cid in superseded or (
                    done and os.path.exists(os.path.join(CHARTERS, done + ".json"))):
                out["already_repaired"] += 1
                continue
            dest, how = _live_destination(dref, domains, root)
            if not dest:
                out["unresolvable"].append({"id": cid, "domain_ref": dref})
                out["ok"] = False
                continue
            row = {"id": cid, "from_domain_ref": dref, "to_domain_ref": dest,
                   "via": how, "placements_citing": len(by_charter.get(cid) or [])}
            if dry_run:
                out["repaired"].append(row)
                continue
            new_cid = _mint_successor_charter(
                body, dest, "repair: orphaned by pre-I-D5 delete",
                len(by_charter.get(cid) or []))
            row["successor_id"] = new_cid
            if how == "root":
                # §2.10: unrecoverable home -> the root, and SAY so on the
                # successor rather than letting it read as a deliberate re-home.
                nsc = load_sidecar(new_cid)
                nsc["lifecycle"] = "orphaned"
                save_sidecar(new_cid, nsc)
            # `lifecycle`, NOT the shipped status enum (§2.2): the source is
            # superseded, not retired work, and `superseded_ids()` is what
            # keeps new work off it.
            sc["lifecycle"] = "repaired"
            sc["repaired_successor_id"] = new_cid
            save_sidecar(cid, sc)
            _append_jsonl(CHARTER_INDEX, {
                "event": "charter_repaired", "id": cid, "successor_id": new_cid,
                "from_domain_ref": dref, "to_domain_ref": dest,
                "resolution": how, "reason": "orphaned-by-delete",
                "placements_citing": row["placements_citing"],
                "tenant_id": ctid, "ts_ms": ts})
            out["repaired"].append(row)
        return out


def lint_full():
    """Full-registry groundedness scan (§9 Phase 0). BLOCKS on any dangling ref.

    The sampled `lint` reads `CURRENT.jsonl[-50:]` and always exits 0 by design
    — "visibility, never blockage". That window is precisely why the pre-I-D5
    damage was invisible in practice: `restructure merge` appends superseding
    rows for the SURVIVING target before removing the source file, so on any
    realistic registry the stale rows fall outside the last 50 (§0.3). This
    reads every CURRENT row, every placement body and every charter body, and
    exits 2.

    Only refs with NO row in `domains/` count as dangling. A ref resolving to a
    `retired` tombstone is grounded — that is the whole point of I-D5 — so a
    legitimate `retire` must never turn this red.
    """
    _ensure_dirs()
    domains = load_domains()
    rows = _read_jsonl(CURRENT)
    placements = all_placements()
    dom = {}
    cha = {}

    def _dom(ref, key):
        e = dom.setdefault(ref, {"ref": ref, "current_rows": 0,
                                 "placements": 0, "charters": 0})
        e[key] += 1

    for r in rows:
        ref = r.get("domain_ref")
        if ref and ref not in domains:
            _dom(ref, "current_rows")
    charter_ok = {}

    def _resolves(cid):
        if cid not in charter_ok:
            charter_ok[cid] = bool(cid) and os.path.exists(
                os.path.join(CHARTERS, cid + ".json"))
        return charter_ok[cid]

    for p in placements:
        ref = p.get("domain_ref")
        if ref and ref not in domains:
            _dom(ref, "placements")
        cid = p.get("charter_id")
        if not _resolves(cid):
            e = cha.setdefault(cid, {"id": cid, "placements": 0})
            e["placements"] += 1
    charters = 0
    for fn in charter_body_files():
        charters += 1
        body = load_charter(fn[:-len(".json")])
        ref = (body or {}).get("domain_ref")
        if ref and ref not in domains:
            _dom(ref, "charters")

    dangling_d = sorted(dom.values(), key=lambda e: e["ref"])
    dangling_c = sorted(cha.values(), key=lambda e: str(e["id"]))
    issues = []
    if dangling_d:
        issues.append("%d domain_ref(s) cited by %d CURRENT row(s), %d "
                      "placement(s) and %d charter(s) have no row in domains/ "
                      "— run `reconcile`"
                      % (len(dangling_d), sum(e["current_rows"] for e in dangling_d),
                         sum(e["placements"] for e in dangling_d),
                         sum(e["charters"] for e in dangling_d)))
    if dangling_c:
        issues.append("%d charter_id(s) cited by %d placement(s) have no body "
                      "in charters/ — unrecoverable; the placements must be "
                      "superseded" % (len(dangling_c),
                                      sum(e["placements"] for e in dangling_c)))
    return {"ok": not issues, "mode": "full", "issues": issues,
            "checked_current_rows": len(rows),
            "checked_placements": len(placements),
            "checked_charters": charters, "domains": len(domains),
            "dangling_domain_refs": dangling_d,
            "dangling_charter_ids": dangling_c}


def consolidate(tenant_id="T-local", apply_auto=False):
    """Two-tier: AUTO-merge system-minted untouched near-duplicates; PROPOSE
    everything the operator has ever touched (ADR-028 Decision 1 corollary).

    apply_auto now defaults to FALSE (§5.3 B20 amendment): the unattended path
    is exactly the one that reached os.remove. Without --apply the AUTO tier
    may only EMIT A PLAN file; nothing calls restructure implicitly. The tier
    survives as plan provenance — plan_origin='auto-consolidate'.
    """
    rep = mece_report(tenant_id)
    applied, proposed, ops = [], [], []
    for o in rep["overlaps"]:
        if o["auto_mergeable"] and apply_auto:
            r = restructure("merge", o["b"], target=o["a"], tenant_id=tenant_id)
            if r.get("ok"):
                applied.append(o)
        else:
            proposed.append(o)
            if o["auto_mergeable"]:
                ops.append({"op": "merge", "ref": o["b"], "target": o["a"],
                            "similarity": o["similarity"]})
    out = {"auto_applied": applied, "proposed": proposed,
           "applied": bool(apply_auto), "auto_mergeable": len(ops)}
    if not apply_auto and ops:
        # CONTENT-ADDRESSED, like everything else in this module. Dry-run is now
        # the DEFAULT path, so a ts-named plan meant every invocation against an
        # unchanged registry dropped another byte-identical file in plans/ —
        # unbounded state, and `consolidate` alone among the sweeps would not be
        # idempotent. `created_ms` stays in the BODY, out of the identity.
        plan_id = "plan-consolidate-" + _sha({"tenant_id": tenant_id,
                                              "ops": ops})[:16]
        path = os.path.join(PLANS, plan_id + ".json")
        out["plan"] = path if os.path.exists(path) else _write_plan_file(
            plan_id + ".json",
            {"plan_id": plan_id, "created_ms": _now_ms(), "tenant_id": tenant_id,
             "plan_origin": "auto-consolidate",
             "rationale": "sibling overlap >= %.2f on system-minted, untouched "
                          "nodes" % AUTO_MERGE_THRESHOLD,
             "validated_at_ms": None, "ops": ops, "validations": []})
    return out


# ------------------------------------------------------------------- scan ---

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".next", "target", ".claude", ".enforcement", ".analytics"}


def place_placement_at(file_path, domain_ref, tenant_id):
    """Stamp a backfilled placement at an already-resolved domain.

    Used by the bulk scan, which derives the domain from directory structure
    rather than from the classifier — the structure IS the evidence there.
    """
    # CHOICE surface, same rule as pick_charter: a closed charter takes no new
    # work; an empty set mints a fresh stub below.
    chs = _open_charters(charters_for(domain_ref))
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
                    try:
                        parent, was_new = mint_domain(parent, nm, [seg], tenant_id)
                    except ValueError:
                        # ORG-016: a frozen/retired node on the chain. Stop
                        # descending and place at the last LIVE one rather than
                        # crashing a bulk scan half way through.
                        break
                place_placement_at(f, parent, tenant_id)
            addressed += 1
    return {"units_enumerated": len(files), "units_addressed": addressed,
            "already_addressed": already, "buckets": len(buckets),
            "root_level_files": root_level, "mece": mece_report(tenant_id)}


# -------------------------------------------------------------------- CLI ---

def _out(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


def _flag(argv, name, default=None):
    """--name value. Returns default when absent or dangling."""
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1]
    return default


def main(argv):
    if len(argv) < 2:
        _out({"error": "usage: placement_engine.py <resolve|tree|mece|consolidate|"
                       "restructure|retire|unretire|charter|verify-charters|"
                       "migrate-charters|reconcile|repair|lint|scan|stats> ...",
              "lifecycle": [
                  "retire <ref> --successor <ref2> [--reason <code>] [--note ...]",
                  "unretire <ref> --from <manifest.json>",
                  "charter retire <C-id> [--note ...]",
                  "charter reassign <C-id> <dref> [--note ...]",
                  "verify-charters [--repair-legacy]   (exit 2 on any mismatch)",
                  "migrate-charters [--dry-run]        (legacy split, id kept)"],
              "recovery": [
                  "lint [--full]        (--full: whole log, exit 2 on dangling refs)",
                  "reconcile [--dry-run]  (tombstone every destroyed domain_ref)",
                  "repair [--dry-run]     (re-home charters orphaned by DELETE)"]})
        return 2
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
        # RENDER surface: tombstones are hidden (--all shows the archive), but
        # D-numbers are still computed over the FULL map — retired siblings keep
        # their ordinal permanently (I-D5).
        # §6: also a TENANT surface. --all-tenants is the explicit opt-out;
        # domain_path still reads the FULL map, so a cross-tenant ancestor
        # cannot renumber anything by being filtered out of the listing.
        domains = load_domains()
        # tenancy removed: every domain is in scope. --all-tenants is kept as
        # an accepted no-op flag so existing scripts do not start failing.
        scope = dict(domains)
        shown = scope if "--all" in argv else live_refs(scope)
        _out({"tenant_id": None if "--all-tenants" in argv else tenant,
              "domains": [{"ref": r, "path": domain_path(r, domains),
                           "name": d.get("name"), "origin": d.get("origin"),
                           "status": d.get("status", "active"),
                           "successor_refs": d.get("successor_refs") or [],
                           "touched": d.get("touched_by_operator")}
                          for r, d in sorted(shown.items(),
                                             key=lambda kv: domain_path(kv[0], domains))],
              "retired_hidden": len(domains) - len(shown)})
    elif cmd == "mece":
        _out(mece_report(tenant))
    elif cmd == "consolidate":
        # dry-run by DEFAULT (§5.3): auto-merge may only emit a plan file.
        _out(consolidate(tenant, apply_auto=("--apply" in argv)))
    elif cmd == "restructure":
        _out(restructure(argv[2], argv[3],
                         target=(argv[4] if len(argv) > 4 else None),
                         name=(argv[4] if len(argv) > 4 else None), tenant_id=tenant))
    elif cmd == "retire":
        if len(argv) < 3:
            _out({"error": "usage: retire <ref> --successor <ref2> "
                           "[--reason <code>] [--note ...]"}); return 2
        if "--report" in argv:
            _out(disposition_report(argv[2], _flag(argv, "--successor")))
            return 0
        r = retire(argv[2], successor_ref=_flag(argv, "--successor"),
                   note=_flag(argv, "--note"),
                   reason_code=_flag(argv, "--reason", "superseded"),
                   tenant_id=tenant)
        _out(r)
        return 0 if r.get("ok") else 2
    elif cmd == "unretire":
        if len(argv) < 3:
            _out({"error": "usage: unretire <ref> --from <manifest.json>"}); return 2
        r = unretire(argv[2], _flag(argv, "--from"), tenant_id=tenant)
        _out(r)
        return 0 if r.get("ok") else 2
    elif cmd == "charter":
        sub = argv[2] if len(argv) > 2 else ""
        cid = argv[3] if len(argv) > 3 else ""
        if sub == "retire" and cid:
            r = charter_retire(cid, note=_flag(argv, "--note"), tenant_id=tenant)
        elif sub == "reassign" and cid:
            tgt = _flag(argv, "--to")
            if not tgt and len(argv) > 4 and not argv[4].startswith("--"):
                tgt = argv[4]
            if not tgt:
                _out({"error": "usage: charter reassign <C-id> <dref> [--note ...]"})
                return 2
            r = charter_reassign(cid, tgt, note=_flag(argv, "--note"), tenant_id=tenant)
        else:
            _out({"error": "usage: charter <retire|reassign> <C-id> [...]"}); return 2
        _out(r)
        return 0 if r.get("ok") else 2
    elif cmd in ("verify-charters", "migrate-charters"):
        # Phase 0 baseline: print the mismatch count so pre-fix damage is
        # measurable. Exit 2 while ANY body fails to hash to its own id.
        # NOT named `repair`: that is a module-level verb now, and a local of
        # the same name makes it local to the whole of main().
        repair_legacy = cmd == "migrate-charters" or "--repair-legacy" in argv
        if repair_legacy:
            r = migrate_charters(dry_run=("--dry-run" in argv))
            _out(r)
            if r.get("dry_run"):
                return 0
            return 0 if r.get("ok") else 2
        r = verify_charters()
        _out(r)
        return 0 if r["ok"] else 2
    elif cmd == "scan":
        _out(scan(argv[2] if len(argv) > 2 else ".", tenant))
    elif cmd == "search":
        # Search the whole module surface: domain names, descriptions, charter
        # titles/purposes. Read-only; ranked by match count.
        q = " ".join(a for a in argv[2:] if not a.startswith("--")).strip().lower()
        if not q:
            _out({"error": "usage: search <terms> [--all-tenants]"}); return 2
        terms = [t for t in re.split(r"\s+", q) if t]
        domains = load_domains()          # FULL map: domain_path needs it
        # tenancy removed: every domain is in scope. --all-tenants is kept as
        # an accepted no-op flag so existing scripts do not start failing.
        scope = dict(domains)
        hits = []
        for ref, d in live_refs(scope).items():   # RENDER + TENANT surface (§6)
            chs = charters_for(ref)
            hay = " ".join([d.get("name", ""), d.get("description", "")] +
                           [c.get("title", "") + " " + c.get("purpose", "")
                            for c in chs]).lower()
            n = sum(hay.count(t) for t in terms)
            if n:
                hits.append({"path": domain_path(ref, domains), "name": d["name"],
                             "description": d.get("description", ""),
                             "charters": [c.get("title", "") for c in chs],
                             "score": n})
        hits.sort(key=lambda h: (-h["score"], h["path"]))
        _out({"query": q, "hits": hits[:20], "total": len(hits)})
    elif cmd == "touch":
        # On-touch minting + post-close correction (ADR-028 phase F, task 8).
        # First touch of an unaddressed file -> durable backfill/mint. Touch of
        # a file whose evidence now resolves elsewhere at >= floor confidence
        # -> superseding row with phase=post-close (I-P5: append, never mutate).
        f = argv[2] if len(argv) > 2 else ""
        if not f:
            _out({"error": "usage: touch <file>"}); return 2
        fid = _norm_path(f)
        existing_pid = current_placement(fid)
        evidence = gather_evidence("", [f])
        domains = load_domains()
        ref, conf, mode = classify(evidence, tenant, domains)
        if not existing_pid:
            r = resolve({"kind": "file", "id": fid}, utterance="", paths=[f],
                        tenant_id=tenant)
            _out({"action": "backfilled", "placement": r["placement"]["id"],
                  "domain_ref": r["placement"]["domain_ref"]})
        else:
            cur = None
            for pl in all_placements():
                if pl.get("id") == existing_pid:
                    cur = pl; break
            cur_ref = cur.get("domain_ref") if cur else None
            if (ref and mode == "match" and cur_ref and ref != cur_ref
                    and conf >= CONFIDENCE_FLOOR):
                picked = pick_charter(ref, sorted(evidence["terms"] | evidence["path_terms"]))
                body = write_placement({"kind": "file", "id": fid}, ref,
                                       picked["id"] if picked else cur["charter_id"],
                                       "matched", conf, {"domains": [], "charters": []},
                                       tenant, supersedes=existing_pid,
                                       phase="post-close")
                _out({"action": "post-close-supersede", "from": cur_ref,
                      "to": ref, "placement": body["id"]})
            else:
                _out({"action": "reused", "placement": existing_pid})
    elif cmd == "lint":
        # Groundedness lint (grounding rung 5). SEPARATE from the gate by
        # dual-lane decision: the gate checks presence; this checks truth.
        # The SAMPLED lane always exits 0 — visibility, never blockage — and is
        # what the per-turn hook runs. `--full` is the Phase 0 lane: whole log,
        # every placement, every charter, and it BLOCKS (exit 2).
        if "--full" in argv:
            r = lint_full()
            _out(r)
            return 0 if r["ok"] else 2
        issues = []
        repo = os.environ.get("CLAUDE_PROJECT_DIR", ".")
        mpath = os.path.join(repo, ".claude", "placement-registered")
        domains = load_domains()
        if os.path.exists(mpath):
            kv = {}
            for line in open(mpath):
                if "=" in line:
                    k, v = line.strip().split("=", 1); kv[k] = v
            ref = kv.get("DOMAIN_REF", "")
            if ref and ref not in domains and ref != "unresolved":
                issues.append("marker DOMAIN_REF %r does not resolve" % ref)
            cid = kv.get("CHARTER_ID", "")
            if cid and cid != "unresolved" and not os.path.exists(
                    os.path.join(CHARTERS, cid + ".json")):
                issues.append("marker CHARTER_ID %r does not resolve" % cid)
            if kv.get("ORIGIN") not in ("matched", "minted", "backfilled",
                                        "unresolved", None, ""):
                issues.append("marker ORIGIN %r not legal" % kv.get("ORIGIN"))
            if kv.get("SOURCE") != "engine":
                issues.append("marker is %s-written, not engine output"
                              % (kv.get("SOURCE") or "hand"))
        else:
            issues.append("no placement marker on disk")
        rows = _read_jsonl(CURRENT)[-50:]
        bad = sum(1 for r in rows if r.get("domain_ref") not in domains)
        if bad:
            issues.append("%d/%d recent CURRENT rows cite unresolvable domains"
                          % (bad, len(rows)))
        _out({"ok": not issues, "mode": "sampled", "issues": issues,
              "checked_rows": len(rows), "domains": len(domains),
              "note": "sampled lane: last 50 CURRENT rows, never blocks. "
                      "`lint --full` scans everything and exits 2."})
    elif cmd == "reconcile":
        r = reconcile(tenant, dry_run=("--dry-run" in argv))
        _out(r)
        return 0 if r.get("ok") else 2
    elif cmd == "repair":
        r = repair(tenant, dry_run=("--dry-run" in argv))
        _out(r)
        return 0 if r.get("ok") else 2
    elif cmd == "stats":
        _all = load_domains()
        _out({"home": HOME, "domains": len(_all),
              "domains_live": len(live_refs(_all)),
              "domains_retired": len(_all) - len(live_refs(_all)),
              # bodies only — sidecars also end in `.json` and are not charters
              "charters": len(charter_body_files()) if os.path.isdir(CHARTERS) else 0,
              "placements": len(all_placements()),
              "current_rows": len(_read_jsonl(CURRENT)),
              "confidence_floor": CONFIDENCE_FLOOR})
    else:
        _out({"error": "unknown command: %s" % cmd}); return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
