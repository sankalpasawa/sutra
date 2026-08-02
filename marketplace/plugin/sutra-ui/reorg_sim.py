#!/usr/bin/env python3
"""reorg_sim.py -- pure-function reorg simulation for the Tier-3 studio.

NO DISK WRITES. Ports simulate() / blockCodesForMove() / classifyTask() from
the reviewed design 1:1 (stopword list, ancestor exemption on ORG-001,
mint_evidence-inclusion in the overlap token set, 0.40 threshold -- NOT the
design doc's untuned 0.55, per this session's verified finding).

classify_task() delegates the actual scoring to the REAL
placement_engine.classify()/gather_evidence() -- it does not reimplement
score_domains -- and layers the mode="floor" nearest-live-ancestor walk on
top, since that presentation logic exists only in the JS reference, not in
the CLI.

Everything here operates on in-memory dicts the caller supplies (a domains
map from a FRESH placement_engine.load_domains() read, plus charters/
placements lists). No function in this module touches SUTRA_NATIVE_HOME,
opens a file, or calls any placement_engine mutator.
"""
import re

DAY = 86400000
DEPTH_BAND = 4                    # ORG-007 target band
STALE_MS = 180 * DAY              # ORG-020
AGING_MS = 90 * DAY
PROJECT_IDLE_MS = 30 * DAY        # ORG-009
OVERLAP_WARN = 0.40               # ORG-001 Jaccard threshold (tuned, NOT the doc's 0.55)

# Function words only -- articles, prepositions, conjunctions, pronouns,
# auxiliaries. Content verbs ("draft", "fix", "review") are NOT stripped: they
# carry routing signal. Ported verbatim from the reviewed design's STOP set.
_STOP = set((
    "a an the this that these those and or but if then so of to in on at by for "
    "from with about into over under is are was were be been being do does did have has had "
    "i we you it they my our your their me us them can could should would will shall may might "
    "please need want just"
).split(" "))

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tok(s):
    """Mirrors JS tok(): lowercase, [a-z0-9]+ tokens, len>1, minus STOP."""
    if not s:
        return set()
    return {w for w in _TOKEN_RE.findall(str(s).lower())
            if len(w) > 1 and w not in _STOP}


def jac(a, b):
    """Jaccard similarity of two token sets."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return (inter / union) if union else 0.0


# --------------------------------------------------------------- helpers ---

def _st(d):
    return d.get("status") or "active"


def _is_live(d):
    return _st(d) != "retired"


def _get(domains, ref):
    return domains.get(ref)


def _is_descendant(domains, ref, ancestor_ref):
    """True if `ref` is a descendant of `ancestor_ref` (walks parent_ref up)."""
    n = _get(domains, ref)
    seen = set()
    while n and n.get("parent_ref"):
        if n["parent_ref"] in seen:
            break
        seen.add(n["ref"])
        if n["parent_ref"] == ancestor_ref:
            return True
        n = _get(domains, n["parent_ref"])
    return False


def _charters_of(charters, ref):
    return [c for c in charters if c.get("domain_ref") == ref]


def _placements_of(placements, ref):
    return [p for p in placements if p.get("domain_ref") == ref]


def _depth(domains, ref):
    n = _get(domains, ref)
    k = 0
    seen = set()
    while n and n.get("parent_ref"):
        if n["ref"] in seen:
            break
        seen.add(n["ref"])
        k += 1
        n = _get(domains, n["parent_ref"])
    return k


def _last_routed(placements, charter_id):
    ts = [p.get("ts_ms") for p in placements if p.get("charter_id") == charter_id]
    return max(ts) if ts else None


def nearest_live_ancestor_of(domains, ref):
    """Walk up from ref (exclusive) to the first live ancestor. Falls back to
    the tenant's live root if none found -- mirrors nearestLiveAncestorOf()."""
    n = _get(domains, ref)
    seen = set()
    while n and n.get("parent_ref"):
        if n["ref"] in seen:
            break
        seen.add(n["ref"])
        parent = _get(domains, n["parent_ref"])
        if parent and _is_live(parent):
            return parent
        n = parent
    # fall back: any live root in the same tenant as `ref`, else any live root
    start = _get(domains, ref)
    tenant = start.get("tenant_id") if start else None
    roots = [d for d in domains.values() if _is_live(d) and not d.get("parent_ref")]
    for r in roots:
        if tenant is None or r.get("tenant_id") == tenant:
            return r
    return roots[0] if roots else None


def _now_ref(placements, now_ms=None):
    """The instant staleness is measured from. An explicit now_ms wins; with
    none, derive it as max(placement.ts_ms) -- the original pure behaviour."""
    if now_ms is not None:
        return now_ms
    all_ts = [p.get("ts_ms") for p in placements if p.get("ts_ms") is not None]
    return max(all_ts) if all_ts else 0


def matched_terms_for(domain, terms, tokenizer=None):
    """The subset of the utterance's terms that could actually have made THIS
    domain win -- i.e. the intersection with the domain's own name tokens +
    mint_evidence, which is the EXACT token set placement_engine's
    score_domains() overlaps the utterance against.

    Returning the raw utterance tokens instead (what the panel rendered as
    "Filed to X on `term` `term`") states a reason the engine never gave: a
    turn held at the root reported "matched terms" the root's mint_evidence
    does not contain, and the operator reads that as the evidence that routed
    it. An empty list is a truthful answer -- nothing in the utterance matched
    the winner's evidence (a floor hold is exactly that case) -- and the panel
    already has an honest branch for it.

    tokenizer: pass placement_engine.tokenize so the domain side is lexed by
    the same function score_domains() uses; without one, fall back to this
    module's own tok() so the helper stays pure/importable on its own.
    """
    if not domain:
        return []
    evidence_terms = list(domain.get("mint_evidence") or [])
    if tokenizer is not None:
        dom_toks = set(tokenizer(domain.get("name") or "", *evidence_terms))
    else:
        dom_toks = tok(" ".join([domain.get("name") or ""] + [str(x) for x in evidence_terms]))
    dom_toks = {str(t).lower() for t in dom_toks}
    return sorted({str(t) for t in (terms or []) if str(t).lower() in dom_toks})


# ------------------------------------------------------------- simulate() --

def simulate(ops, domains, charters=None, placements=None, base=None, now_ms=None):
    """The reorg simulator: pure, no disk writes.

    Args:
        ops: list of {"op": "move", "ref": <dref>, "target": <dref>}
        domains: dict[ref, domain] -- the FRESH load (do not pass a cache)
        charters: list of charter dicts (merged body+sidecar view; needs
            "domain_ref", "status", "kind", "id", "title" at minimum)
        placements: list of placement dicts (needs "domain_ref", "charter_id",
            "id", "ts_ms")
        base: optional {"domain_index_lines": int, ...} -- if the caller's
            draft carries a captured base and it no longer matches the
            current registry fingerprint, pass a dict with a mismatched
            "domain_index_lines" (or omit to skip ORG-010).
        now_ms: the clock the staleness codes (ORG-009 idle, ORG-020 dormant)
            measure against. DEFAULT (None) keeps the original pure behaviour
            -- "now" is derived as max(placement.ts_ms) -- so pure callers are
            unaffected. But the panel bands charter freshness against the
            BROWSER's Date.now(), and deriving a different "now" here made the
            two halves of the same screen disagree: a charter could read
            "stale 214d" in the Charters table while ORG-020 stayed silent in
            Health, because the server's derived "now" was the newest
            placement, not today. The HTTP layer therefore passes ONE explicit
            clock (the client's own Date.now()) so both sides band against the
            same instant.

    Returns {"domains2": dict[ref, domain], "findings": [...], "max_depth": int}
    """
    charters = charters or []
    placements = placements or []

    # domains2 = deep-ish copy with ops applied (MOVE only, per §8.5.9 arity rule)
    domains2 = {ref: dict(d) for ref, d in domains.items()}
    for op in ops:
        if op.get("op") == "move":
            n = domains2.get(op.get("ref"))
            if n is not None:
                n["parent_ref"] = op.get("target")

    findings = []
    live_list = [d for d in domains2.values() if _is_live(d)]

    def desc2(ref, anc):
        return _is_descendant(domains2, ref, anc)

    # ORG-006 block -- cycle in parent_ref
    for d in live_list:
        if d.get("parent_ref") and desc2(d["parent_ref"], d["ref"]):
            findings.append({"code": "ORG-006", "sev": "block",
                              "subject": d.get("name") + " is inside its own subtree"})

    # ORG-003 block -- live child whose parent is not live
    live_refs_set = {d["ref"] for d in live_list}
    for d in live_list:
        p = d.get("parent_ref")
        if p and p not in live_refs_set:
            findings.append({"code": "ORG-003", "sev": "block",
                              "subject": d.get("name") + "'s parent is not live"})

    # ORG-002 block -- live charter homed to a tombstone with no disposition
    for d in domains2.values():
        if _st(d) == "retired":
            for c in _charters_of(charters, d["ref"]):
                if c.get("status") != "retired":
                    findings.append({"code": "ORG-002", "sev": "block",
                                      "subject": '"' + str(c.get("title")) + '" is homed to retired ' + str(d.get("name"))})

    # ORG-004 block -- placement citing an unresolvable ref (full scan)
    for p in placements:
        if p.get("domain_ref") not in domains2:
            findings.append({"code": "ORG-004", "sev": "block",
                              "subject": str(p.get("id")) + " cites " + str(p.get("domain_ref"))[:13] + "…"})

    # ORG-018 block -- two live siblings sharing a normalized name
    def norm(s):
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    for d in live_list:
        clash = None
        for o in live_list:
            if o["ref"] != d["ref"] and o.get("parent_ref") == d.get("parent_ref") and norm(o.get("name")) == norm(d.get("name")):
                clash = o
                break
        if clash and d["ref"] < clash["ref"]:
            findings.append({"code": "ORG-018", "sev": "block",
                              "subject": 'two live siblings named "' + str(d.get("name")) + '"'})

    # ORG-017 block -- an op crossing tenants
    for op in ops:
        s = domains2.get(op.get("ref"))
        t = domains2.get(op.get("target"))
        if s and t and s.get("tenant_id") != t.get("tenant_id"):
            findings.append({"code": "ORG-017", "sev": "block",
                              "subject": str(s.get("tenant_id")) + " → " + str(t.get("tenant_id"))})

    # ORG-001 warn -- overlapping mandates. Jaccard over name + description +
    # mint_evidence. Ancestor/descendant pairs are EXEMPT.
    def om_tok(d):
        return tok((d.get("name") or "") + " " + (d.get("description") or "") + " "
                   + " ".join(d.get("mint_evidence") or []))

    def related(a, b):
        return desc2(a["ref"], b["ref"]) or desc2(b["ref"], a["ref"])

    for i in range(len(live_list)):
        for j in range(i + 1, len(live_list)):
            a, b = live_list[i], live_list[j]
            if related(a, b):
                continue
            s = jac(om_tok(a), om_tok(b))
            if s > OVERLAP_WARN:
                findings.append({"code": "ORG-001", "sev": "warn",
                                  "subject": a.get("name") + " ↔ " + b.get("name") + " (" + ("%.2f" % s) + ")"})

    # ORG-007 warn -- depth beyond band
    max_d = 0
    for d in live_list:
        max_d = max(max_d, _depth(domains2, d["ref"]))
    if max_d > DEPTH_BAND:
        findings.append({"code": "ORG-007", "sev": "warn",
                          "subject": "max depth " + str(max_d) + " > band " + str(DEPTH_BAND)})

    # ORG-008 warn -- live domain with zero live charters
    for d in live_list:
        live_charters = [c for c in _charters_of(charters, d["ref"]) if c.get("status") != "retired"]
        if not live_charters:
            findings.append({"code": "ORG-008", "sev": "warn",
                              "subject": d.get("name") + " holds no charter"})

    # ORG-009 warn -- only project charters, idle >30d
    for d in live_list:
        cs = [c for c in _charters_of(charters, d["ref"]) if c.get("status") != "retired"]
        if cs and all(c.get("kind") == "project" for c in cs):
            ts = [p.get("ts_ms") for p in _placements_of(placements, d["ref"])]
            newest = max(ts) if ts else None
            # now_ms when the caller supplies one (the panel sends its own
            # Date.now(), so Health and the freshness pills share a clock);
            # otherwise fall back to the pure derivation -- max ts_ms across
            # all placements -- so this function stays wall-clock-free for
            # callers that need determinism.
            now_ref = _now_ref(placements, now_ms)
            if not ts or newest < now_ref - PROJECT_IDLE_MS:
                findings.append({"code": "ORG-009", "sev": "warn",
                                  "subject": d.get("name") + " — only project charters, idle"})

    # ORG-020 warn -- every standing charter dormant past the stale band
    now_ref = _now_ref(placements, now_ms)
    for d in live_list:
        sc = [c for c in _charters_of(charters, d["ref"])
              if c.get("kind") == "standing" and c.get("status") == "active"]
        if sc:
            def dormant(c):
                lr = _last_routed(placements, c.get("id"))
                return lr is None or lr < now_ref - STALE_MS
            if all(dormant(c) for c in sc):
                findings.append({"code": "ORG-020", "sev": "warn",
                                  "subject": d.get("name") + " — all standing charters dormant"})

    # ORG-010 block -- the draft's base no longer matches the registry
    if base and isinstance(base, dict) and base.get("_mismatch"):
        findings.append({"code": "ORG-010", "sev": "block",
                          "subject": "registry moved since base was captured"})

    return {"domains2": domains2, "findings": findings, "max_depth": max_d}


# ------------------------------------------------------- block_codes_for_move --

def block_codes_for_move(src, target, all_domains):
    """Port of JS blockCodesForMove(src, t). Per-hover budget: reads the
    in-memory domains dict only, no charter/placement scan (that is why
    ORG-001/002/004/009 are NOT ring codes -- §8.5.9).

    Args:
        src: the domain dict being dragged
        target: the domain dict being dropped onto
        all_domains: dict[ref, domain] -- the full (unfiltered) map

    Returns: list of {"code": ..., "subject": ...}
    """
    codes = []
    if target["ref"] == src["ref"] or _is_descendant(all_domains, target["ref"], src["ref"]):
        codes.append({"code": "ORG-006", "subject": target.get("name") + " is inside " + src.get("name")})
    if _st(target) != "active":
        codes.append({"code": "ORG-016", "subject": target.get("name") + " is " + _st(target)})
    if target.get("tenant_id") != src.get("tenant_id"):
        codes.append({"code": "ORG-017", "subject": str(target.get("tenant_id")) + " ≠ " + str(src.get("tenant_id"))})

    def norm(s):
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    for d in all_domains.values():
        if (d.get("ref") != src.get("ref") and d.get("parent_ref") == target.get("ref")
                and _st(d) != "retired" and norm(d.get("name")) == norm(src.get("name"))):
            codes.append({"code": "ORG-018", "subject": 'a live sibling is already named "' + str(src.get("name")) + '"'})
            break

    return codes


# codes that cannot be evaluated -- never 0, never passed, never a green tick.
# Ported verbatim from the reviewed design's NOT_CHECKED list.
NOT_CHECKED = [
    ("ORG-005", "authority.ceilings has no writer (0 occurrences). Ph4."),
    ("ORG-011", "no applied plan exists; revert has no target. Apply is CLI-only (§5.1)."),
    ("ORG-012", "origin='unrouted' has no writer (0 occurrences). Floor-held shown separately -- a different signal."),
    ("ORG-013", "filesystem marker, not observable from a browser. Markers >24h downgrade to warn."),
    ("ORG-014", "Workflow.domain_ref unpopulated. Ph4."),
    ("ORG-019", "last_routed_ms has no writer (0 occurrences). Freshness derived at render instead."),
]


# ------------------------------------------------------------- classify_task --

def pick_charter(domains, charters, ref):
    """domain's own active charter, else inherit from the nearest ancestor
    that has one. Ports JS pickCharter(): a simple walk, distinct from the
    real engine's pick_charter() (which also scores by evidence overlap) --
    per the task spec this is intentionally the SIMPLE ancestor-walk variant."""
    n = domains.get(ref)
    seen = set()
    while n:
        active = [c for c in _charters_of(charters, n["ref"]) if c.get("status") == "active"]
        if active:
            return active[0]
        parent_ref = n.get("parent_ref")
        if not parent_ref or n["ref"] in seen:
            return None
        seen.add(n["ref"])
        n = domains.get(parent_ref)
    return None


def classify_task(text, domains, tenant_id, recent_placements=None,
                   pe_classify=None, pe_gather_evidence=None, pe_tokenize=None):
    """The entry-point classifier. PREFERS the REAL classify()+gather_evidence()
    from placement_engine.py for the actual scoring -- callers pass those two
    functions in (pe_classify, pe_gather_evidence) so this module never
    imports placement_engine itself and stays a pure function of its inputs.

    Layers the mode="floor" nearest-live-ancestor walk on top (identical to
    nearestLiveAncestorOf() in the JS), since that presentation logic does
    not exist in the CLI/engine.

    Returns {"mode": "match"|"floor"|"none", "domain_ref": str|None,
             "confidence": float, "matched_terms": [...] (best-effort)}
    """
    if pe_classify is None or pe_gather_evidence is None:
        raise ValueError("classify_task requires the real placement_engine "
                          "classify()/gather_evidence() callables")

    evidence = pe_gather_evidence(utterance=text)
    domain_ref, confidence, mode = pe_classify(evidence, tenant_id, domains)

    # matched_terms is a claim about WHY this domain won -- intersect against
    # the winner's own evidence, never the raw utterance (see
    # matched_terms_for). No winner => nothing matched anything.
    matched_terms = matched_terms_for(domains.get(domain_ref) if domain_ref else None,
                                      evidence.get("terms"), tokenizer=pe_tokenize)

    if domain_ref is None:
        return {"mode": "none", "domain_ref": None, "confidence": 0.0,
                "matched_terms": matched_terms}

    if mode == "floor":
        # classify() already walked to the nearest live ancestor internally
        # (I-P9) and returned it as domain_ref -- surface which node it held
        # at, mirroring nearestLiveAncestorOf() in the JS reference for the
        # presentation layer.
        return {"mode": "floor", "domain_ref": domain_ref, "confidence": confidence,
                "matched_terms": matched_terms,
                "held_at_ref": domain_ref}

    return {"mode": mode, "domain_ref": domain_ref, "confidence": confidence,
            "matched_terms": matched_terms}
