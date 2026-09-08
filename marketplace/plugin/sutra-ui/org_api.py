"""org_api.py -- Tier-3 panel backend: read-mostly registry endpoints + one
write endpoint (POST /api/classify, exactly one write_placement() call).

SAFETY (see marketplace/plugin/sutra-ui -- ground truth for this module):
  - Calls ONLY: load_domains, live_refs, tenant_refs, domain_path, charters_for,
    all_placements, charter_body_files, mece_report, lint_full, classify,
    gather_evidence, write_placement, _read_jsonl(CURRENT), charter_view,
    load_sidecar (render-only merge, same family as charter_view), tokenize
    (pure lexer, no I/O -- passed to reorg_sim.matched_terms_for so the
    "which terms matched" answer is lexed by the same function
    score_domains() uses, rather than a near-copy that disagrees at the edges).
  - NEVER calls: resolve, mint_domain, restructure, retire, unretire,
    charter_retire, charter_reassign, consolidate, reconcile, repair,
    verify_charters. test_forbidden_calls.py greps this file for those names
    and fails the build if any appear -- a provable negative.
  - Writes to disk in exactly three places:
      (a) write_placement() -> SUTRA_NATIVE_HOME (classify endpoint only, one
          placement per call)
      (b) the draft file under DRAFTS_DIR (outside SUTRA_NATIVE_HOME, mirrors
          ~/.sutra-ui/drafts/ per the design doc's §8.5.9 "What it writes")
      (c) the Teamsutra task store under ~/.sutra-ui/teamsutra/, via the
          teamsutra module only (creation lands INERT at status=draft; the
          queue/drop/release mutations are desktop-token-gated)
  - SUTRA_NATIVE_HOME resolution: the REAL registry (the engine's own default,
    ~/.sutra-native/user-kit) unless the env var overrides it. No fixture
    default -- an operator must never be shown seeded data dressed as theirs.
    The active root is logged loudly at import so a running server is never
    ambiguous about which registry it reads and writes.
"""
import base64
import binascii
import hashlib
import json
import logging
import hmac
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("sutra-ui.org")

# --------------------------------------------------------------- registry ---
# NO FIXTURE DEFAULT. This used to point at a seeded scratch registry so the
# panel always had a full-looking org to render. That was a mock component:
# it showed invented departments, charters and placements as though they were
# yours. The panel now reads the REAL registry -- whatever placement_engine
# resolves from SUTRA_NATIVE_HOME, defaulting to the engine's own default
# (~/.sutra-native/user-kit). If that registry is nearly empty, the panel
# shows it nearly empty, because that is the truth.
#
# Tests still seed an isolated tempfile.mkdtemp() and set SUTRA_NATIVE_HOME
# explicitly -- that is test isolation, not a mock shown to an operator.
_ACTIVE_HOME = os.environ.get("SUTRA_NATIVE_HOME") or os.path.expanduser(
    "~/.sutra-native/user-kit")
os.environ["SUTRA_NATIVE_HOME"] = _ACTIVE_HOME

logger.warning("=" * 72)
logger.warning("SUTRA_NATIVE_HOME (registry root) = %s", _ACTIVE_HOME)
logger.warning("=" * 72)
print("=" * 72, file=sys.stderr)
print("[org_api] SUTRA_NATIVE_HOME (registry root) = %s" % _ACTIVE_HOME, file=sys.stderr)
print("[org_api] WRITES: POST /api/classify appends ONE placement row here.", file=sys.stderr)
print("=" * 72, file=sys.stderr)

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402  (path insert must precede this import)
import reorg_sim as R  # noqa: E402
import teamsutra  # noqa: E402

import claude_local
import codex_auth  # Sutra's COPY of the Codex API key (keychain, never here)
import codex_install  # fetches the Codex CLI itself (npm --prefix, into ~/.sutra-ui)
import codex_login  # spawns `codex login`/`codex logout`; holds the live child
import codex_models  # asks codex which models it will run (app-server model/list)
import deepseek_auth  # validates + stores the DeepSeek key (keychain, never here)
import deepseek_install  # fetches the DeepSeek CLI itself (npm, into ~/.sutra-ui)
import deepseek_session  # the one-time code a BROWSER trades for a write token
import providers  # provider registry + ~/.sutra-ui/settings.json (no engine access)
import updates    # desktop-app + plugin version checks and installs (no engine access)
import routines   # local scheduled routines (launchd + the claude CLI; no engine access)
import proposals  # what the chat agent asks for; nothing here applies without approval

# --------------------------------------------------------------- drafts ----
# Draft plan storage. Outside SUTRA_NATIVE_HOME by design (§8.5.9 "What it
# writes"): the analogue of ~/.sutra-ui/drafts/ for this dev/test setup.
DRAFTS_DIR = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_DRAFTS", "~/.sutra-ui/drafts")))
DRAFT_PATH = DRAFTS_DIR / "draft.json"

router = APIRouter(prefix="/api", tags=["org"])


# ------------------------------------------------------- tenant scoping ----
# Every read endpoint below used to hardcode
#   os.environ.get("PLACEMENT_TENANT", "T-local")
# which makes the tenant a PROPERTY OF THE SERVER PROCESS. A tenant-first UI
# needs it to be a property of the REQUEST: pick a tenant on the landing
# screen, and every subsequent read is scoped to it without restarting
# uvicorn with a different env var.
#
# The override is passed EXPLICITLY into the engine calls that already take a
# tenant_id (tenant_refs / charters_for / all_placements / mece_report). It is
# deliberately NOT implemented by mutating os.environ["PLACEMENT_TENANT"] for
# the duration of the request: FastAPI runs these sync endpoints in a thread
# pool, so a global mutation would leak across concurrent requests and scope
# one operator's read to another's tenant. (placement_engine reads
# PLACEMENT_TENANT only in its CLI main(), never in the library functions used
# here -- verified -- so passing it explicitly is complete, not partial.)
#
# Absent ?tenant=, behaviour is byte-identical to before.

def _tenant_of_record(tenant=None):
    """The tenant this request is about: ?tenant= if given, else the server's
    PLACEMENT_TENANT, else "T-local" (the engine's own default)."""
    return (tenant or "").strip() or os.environ.get("PLACEMENT_TENANT", "T-local")


def _scope(tenant=None, all_tenants=False):
    """ALWAYS None -- i.e. unfiltered. Tenancy is removed.

    This is the single place the tenant filter entered every org endpoint, so
    it is the single place it leaves from. Returning None makes the engine's
    remaining optional filters (charters_for(tenant_id=...),
    all_placements(tenant_id=...)) unfiltered, which is what "one org per
    registry" means.

    Neutralising it HERE rather than at each endpoint matters: the domain-side
    filter and the CHARTER-side filter are separate, and removing only the
    first left /api/org/charters?tenant=<anything-unknown> returning zero rows
    while /tree returned all of them -- a half-removed filter that disagreed
    with itself. One chokepoint in, one chokepoint out.

    The arguments are kept so live callers do not 422; they are ignored.
    """
    return None


def _charter_ids_in_scope(scope, tenant_id):
    """Unique charter ids homed anywhere in `scope` (live AND retired domains,
    same reason org_charters() does not filter on liveness)."""
    seen = set()
    for ref in scope:
        for body in E.charters_for(ref, tenant_id=tenant_id):
            cid = body.get("id")
            if cid:
                seen.add(cid)
    return seen


# ------------------------------------------------------------- GET /tree ---

@router.get("/org/tree")
def org_tree(include_retired: bool = False, all_tenants: bool = False,
             tenant: Optional[str] = None):
    """Port of the CLI's `tree` (placement_engine.py ~:2566).

    domains = load_domains(); shown = domains if include_retired
                                      else live_refs(domains).

    TENANCY IS REMOVED. `scope` used to be `tenant_refs(domains, tenant_id)`,
    with ?tenant= overriding a PLACEMENT_TENANT env var and all_tenants=true as
    the opt-out. There is one org per registry now, so the whole registry is the
    scope and there is nothing to select between.

    `tenant` and `all_tenants` remain in the signature as ACCEPTED NO-OPS: they
    are query parameters a running panel and existing scripts may still send,
    and 422-ing them would break callers to no purpose. They no longer affect
    the response.
    """
    tenant_of_record = _tenant_of_record(tenant)
    tenant_id = None if all_tenants else tenant_of_record
    domains = E.load_domains()
    scope = domains          # tenancy removed: the whole registry is the scope
    shown = scope if include_retired else E.live_refs(scope)

    rows = []
    for ref, d in shown.items():
        rows.append({
            "ref": ref,
            "path": E.domain_path(ref, domains),
            "name": d.get("name"),
            "origin": d.get("origin"),
            "status": d.get("status", "active"),
            "successor_refs": d.get("successor_refs") or [],
            "touched": d.get("touched_by_operator"),
            "parent_ref": d.get("parent_ref"),
            # raw fields the panel's own client-side logic reads directly --
            # dPath() re-derives the D-path from ts_minted_ms + parent_ref,
            # inTenant()/tenant chips filter on tenant_id, the department
            # inspector prints description + mint_evidence and shows
            # retired_at_ms/retire_reason_code. "path" above is kept too
            # (server-precomputed via the same tie-break as dPath()) so
            # callers that want it pre-derived still get it; the raw fields
            # let the panel recompute identically once the adapter wiring
            # in app.py's /panel lands.
            "tenant_id": d.get("tenant_id"),
            "description": d.get("description"),
            "mint_evidence": d.get("mint_evidence") or [],
            "ts_minted_ms": d.get("ts_minted_ms"),
            "retired_at_ms": d.get("retired_at_ms"),
            "retire_reason_code": d.get("retire_reason_code"),
        })
    # Sort TENANT OF RECORD FIRST, then by path. Sorting by path alone is a
    # tie: D-numbering is per-tenant, so T-local's root and T-acme's root are
    # BOTH "D0" and the winner was whichever the underlying dict happened to
    # yield first. The panel consumes this order directly -- the org chart's
    # root row, the Tenants table, and (worse) the create-department parent
    # default, which took `the first row with no parent_ref`. That could be
    # ANOTHER tenant's root, so the dropdown read "D0 Sutra Labs" while the
    # copyable CLI string carried --parent <T-acme root>. Ordering here makes
    # the tenant of record deterministically lead; ts_minted_ms + ref break
    # any remaining tie so the order is stable across reads.
    rows.sort(key=lambda r: (0 if r.get("tenant_id") == tenant_of_record else 1,
                             r["path"], r.get("ts_minted_ms") or 0, r["ref"]))
    return rows


# ---------------------------------------------------------- GET /charters --

def _merged_charter_view(cid):
    """body + sidecar merge for render, via the engine's own charter_view()
    (handles the case where no sidecar exists on disk too)."""
    return E.charter_view(cid)


@router.get("/org/charters")
def org_charters(all_tenants: bool = False, tenant: Optional[str] = None):
    """EVERY charter in the tenant scope -- including ones homed to a RETIRED
    domain, merged body+sidecar per §2.2 (charter_view() does the merge).

    Scoping this to live_refs() was a real bug: a charter stranded on a
    tombstone is exactly the ORG-002 defect the Charters screen exists to
    surface (it renders the owner cell with a "tombstone" pill). Filtering it
    out made the one row the operator most needs to see the one row they
    could not see -- and silently dropped the rail count from 12 to 11 with
    no indication anything was hidden. Scope by TENANT (the §6 boundary),
    never by liveness.
    """
    tenant_id = _scope(tenant, all_tenants)
    domains = E.load_domains()
    scope = domains          # tenancy removed: the whole registry is the scope

    seen_ids = set()
    out = []
    for ref in scope:  # every domain in tenant scope, live AND retired
        for body in E.charters_for(ref, tenant_id=tenant_id):
            cid = body.get("id")
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            view = _merged_charter_view(cid)
            if view:
                out.append(view)
    out.sort(key=lambda c: c.get("id") or "")
    return out


# -------------------------------------------------------- GET /placements --

@router.get("/org/placements")
def org_placements(all_tenants: bool = False, tenant: Optional[str] = None):
    """write_placement()'s body dict (placement_engine.py, untouched by this
    tier) never stores a 'mode' key -- the panel's classifyTask()/runTurn()
    write mode:'match'|'floor' onto every placement row client-side and read
    p.mode==='floor' pervasively (Placements screen's 'held at ancestor'
    banner + per-row held pill, session rail 'held' badges in both Recent and
    By-department groupings, By-department held counts, SCREENS.health's
    held-count summary). Derive it here instead of editing the core engine:
    mode is a pure function of the placement's own stored confidence vs the
    engine's own CONFIDENCE_FLOOR (the same comparison classify() itself
    makes at write time -- see placement_engine.py's classify()), so this is
    not a guess, it's the identical predicate re-applied read-side."""
    tenant_id = _scope(tenant, all_tenants)
    rows = E.all_placements(tenant_id=tenant_id)
    for row in rows:
        conf = row.get("confidence")
        row["mode"] = "floor" if (conf is not None and conf < E.CONFIDENCE_FLOOR) else "match"
    rows.sort(key=lambda p: p.get("ts_ms", 0), reverse=True)
    return rows


# -------------------------------------------------------------- GET /stats -

@router.get("/org/stats")
def org_stats(tenant: Optional[str] = None):
    """Port of the CLI's `stats` (placement_engine.py ~:2757).

    Registry-wide by default (unchanged). With ?tenant=<id> every count is
    narrowed to that tenant -- domains via tenant_refs, charters via
    charters_for over that scope, placements/current rows via their own
    tenant_id field. `scope` names which of the two you are looking at, so a
    smaller number can never be mistaken for the registry shrinking.
    """
    _all = E.load_domains()
    if not tenant:
        return {
            "scope": "all-tenants",
            "tenant_id": None,
            "domains": len(_all),
            "domains_live": len(E.live_refs(_all)),
            "domains_retired": len(_all) - len(E.live_refs(_all)),
            "charters": len(E.charter_body_files()),
            "placements": len(E.all_placements()),
            "current_rows": len(E._read_jsonl(E.CURRENT)),
            "confidence_floor": E.CONFIDENCE_FLOOR,
        }

    tenant_id = _tenant_of_record(tenant)
    scope = _all             # tenancy removed: the whole registry is the scope
    live = E.live_refs(scope)
    return {
        "scope": "tenant",
        "tenant_id": tenant_id,
        "domains": len(scope),
        "domains_live": len(live),
        "domains_retired": len(scope) - len(live),
        "charters": len(_charter_ids_in_scope(scope, tenant_id)),
        "placements": len(E.all_placements(tenant_id=tenant_id)),
        "current_rows": sum(1 for r in E._read_jsonl(E.CURRENT)
                            if r.get("tenant_id") == tenant_id),
        "confidence_floor": E.CONFIDENCE_FLOOR,
    }


# ------------------------------------------------------------- GET /health -

@router.get("/org/health")
def org_health(tenant: Optional[str] = None):
    """MECE is per-tenant (mece_report takes a tenant_id and defaults to
    "T-local"); lint_full() walks the whole log and has no tenant argument, so
    it is reported as registry-wide rather than mislabelled as scoped."""
    tenant_id = _tenant_of_record(tenant)
    return {"mece": E.mece_report(tenant_id), "lint": E.lint_full(),
            "tenant_id": tenant_id, "lint_scope": "all-tenants"}


# ------------------------------------------------------------ GET /history -

@router.get("/org/history")
def org_history(tenant: Optional[str] = None):
    """domains/INDEX.jsonl, newest first, plus DERIVED completeness metadata.

    `history_complete_from_ms` does NOT exist as a stored field anywhere in
    placement_engine.py -- it is a design-doc concept (§5.4 / the as-of view),
    and inventing it as though the engine wrote it would be a fabrication.
    It IS honestly derivable: the Phase 0 work enriched `domain_restructured`
    events with before/after snapshots, so the boundary between "we know what
    changed" and "we only know THAT something changed" is the earliest event
    carrying a `before` key. Rows older than that are legacy: replaying them
    cannot reconstruct prior state, which is exactly why an as-of view before
    that timestamp must refuse rather than guess.

    Returned as `derived: true` so no caller mistakes it for stored state.
    """
    rows = E._read_jsonl(E.DOMAIN_INDEX)
    # ?tenant= drops rows belonging to a DIFFERENT tenant. Rows carrying no
    # tenant_id at all are kept: their tenant is unknown, and silently hiding
    # an event because a field is absent would put a hole in the timeline that
    # nothing on screen accounts for.
    if tenant:
        want = _tenant_of_record(tenant)
        rows = [r for r in rows
                if r.get("tenant_id") is None or r.get("tenant_id") == want]
    enriched = [r for r in rows if r.get("before") is not None]
    complete_from = min((r.get("ts_ms") or 0) for r in enriched) if enriched else None
    # `legacy_events` is printed under the timeline as "N legacy row(s) below
    # the line", so it has to count the rows the timeline actually greys out.
    # The timeline's predicate is `event === "domain_restructured" && !before`
    # -- a MINT carries no `before` because there is no prior state to
    # snapshot, not because anything was lost. Counting every row without a
    # `before` key reported 5 legacy rows under a timeline showing 1.
    legacy = [r for r in rows
              if r.get("event") == "domain_restructured" and r.get("before") is None]
    return {
        "events": sorted(rows, key=lambda r: r.get("ts_ms") or 0, reverse=True),
        "meta": {
            "tenant_id": _tenant_of_record(tenant) if tenant else None,
            "domain_index_lines": len(rows),
            "history_complete_from_ms": complete_from,
            "derived": True,
            "enriched_events": len(enriched),
            # restructure rows that cannot be replayed -- the greyed rows
            "legacy_events": len(legacy),
            # the broader "no before key at all" count, kept so the narrower
            # number above is never mistaken for it (mints live in the gap)
            "events_without_before": len(rows) - len(enriched),
        },
    }


# ------------------------------------------------------------- GET /skills -

@router.get("/skills")
def api_skills(request: Request = None):
    """Every slash command `claude` can actually resolve here.

    The Skills screen previously rendered TEN HARDCODED STRINGS and claimed
    "31 total". Both numbers were invented -- nothing was read from disk. This
    reads the same directories the CLI resolves (see skills_catalog.py), so
    what the screen lists is what will actually run, and the count is real.

    Deliberately generic: it walks plugins/cache/<marketplace>/<plugin>/<ver>/
    with no hardcoded plugin name, so a newly installed plugin appears with
    zero code change. That is what "AI agnostic" means here -- read what the
    assistant exposes, do not invent a parallel format for it.

    MULTI-PROVIDER: the ~/.claude scan is unchanged. Every OTHER configured
    provider is read the same way -- whatever capability files actually exist
    in its config dir -- and providers with no config dir contribute nothing.
    `providers` carries the per-provider entry count next to installed/
    configured/reason, so "0 entries" is always accompanied by WHY.

    Entries are not normalised into a fake common shape. Codex's AGENTS.md is
    a persona/prompt file, so it arrives as kind="instructions" with
    slash=null; it is not dressed up as a slash command that codex would not
    resolve. Anything whose provider binary is missing carries runnable=false
    plus the reason, so the palette can refuse to offer it.
    """
    import skills_catalog
    # project_dir is the VALIDATED workdir, not CLAUDE_PROJECT_DIR. Nothing in this
    # repo sets that variable (verified: not run.sh, sutra-ui.sh, install.sh or
    # electron/main.js), so the project-local `.claude/commands` tier was dead code
    # and a command the operator wrote for their own project never appeared.
    wd = providers.load_settings().get("workdir") or ""
    project_dir = wd if (wd and providers.workdir_allowed(wd) and os.path.isdir(wd)) else None

    bundle = skills_catalog.discover_all(project_dir=project_dir)
    items = bundle["items"]
    by_kind, by_source, by_provider = {}, {}, {}
    for e in items:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        by_provider[e["provider"]] = by_provider.get(e["provider"], 0) + 1
    payload = {"items": items, "total": len(items),
               "by_kind": by_kind, "by_source": by_source,
               "by_provider": by_provider,
               "runnable": sum(1 for e in items if e.get("runnable")),
               "providers": bundle["providers"]}

    # ---- change signature --------------------------------------------------
    # Hash the payload THIS CALL IS ABOUT TO RETURN, from the SAME scan. A separate
    # /signature endpoint would scan twice, and the client could then store a
    # fingerprint describing state it never received -- a MISSED update that never
    # self-corrects, because the next probe matches the stored value forever.
    #
    # Hash the whole payload, not count+mtime+slash-names:
    #   * 7 of 44 entries here have slash=None, so sorting slash names raises TypeError
    #   * max(mtime) is a monotone ceiling -- one file with a skewed-future mtime
    #     permanently blinds every later edit
    #   * neither notices a `runnable` flip, which is the doctrine-critical field
    # Measured: the hash adds ~0.2ms to a ~4.4ms scan.
    payload["signature"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:32]
    # read_at is added AFTER hashing, so the clock never enters the digest and two
    # identical scans always agree.
    payload["read_at"] = int(time.time())

    headers = {"ETag": payload["signature"], "Cache-Control": "no-cache"}
    if request is not None and request.headers.get("if-none-match") == payload["signature"]:
        # Unchanged: no body to parse, no re-render. Cache-Control is repeated here
        # because a 304 without it can still be pinned by an intermediate cache.
        return Response(status_code=304, headers=headers)
    return JSONResponse(payload, headers=headers)


# ------------------------------------------------------------- GET /search -

def _hay(*parts):
    out = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, (list, tuple)):
            out.extend(str(x) for x in p)
        else:
            out.append(str(p))
    return " ".join(out).lower()


@router.get("/org/search")
def org_search(q: str = "", limit: int = 40, tenant: Optional[str] = None):
    """Real retrieval across the registry. The rail item was DISABLED with the
    label "no index" -- true only if the answer had to be an FTS5 index. At
    this registry's actual scale (tens of domains, tens of charters, low
    thousands of placements at worst) a linear scan over already-loaded dicts
    answers in microseconds. Shipping a greyed-out item was the wrong call:
    it advertised a capability and delivered nothing.

    Matches on the fields a person would actually search by, and says WHICH
    field hit so the result is explainable rather than an opaque ranking.
    """
    term = (q or "").strip().lower()
    if not term:
        return {"query": "", "results": [], "counts": {}}

    # Registry-wide unless ?tenant= is given. (This local was previously
    # computed and never used -- search silently spanned every tenant while
    # reading as though it were scoped. Now the scoping is real and opt-in.)
    tenant_id = _tenant_of_record(tenant) if tenant else None
    domains = E.load_domains()
    results = []

    for ref, d in domains.items():
        fields = []
        if term in _hay(d.get("name")):
            fields.append("name")
        if term in _hay(d.get("description")):
            fields.append("description")
        if term in _hay(d.get("mint_evidence")):
            fields.append("mint_evidence")
        if fields:
            results.append({
                "kind": "domain", "ref": ref,
                "title": d.get("name"), "path": E.domain_path(ref, domains),
                "subtitle": d.get("description") or "",
                "matched_on": fields, "status": d.get("status", "active"),
                "tenant_id": d.get("tenant_id"),
                # name hits rank above evidence hits -- a department called
                # "Platform" should beat one that merely lists it as a term
                "score": 3 if "name" in fields else (2 if "description" in fields else 1),
            })

    # charter_body_files() returns FILENAMES ("C-<sha>.json"), not ids and not
    # dicts -- charter_view() wants the bare id, so passing the filename
    # straight through returned None for every charter and made charters
    # silently unsearchable. Strip the extension.
    for fname in E.charter_body_files():
        cid = fname[:-5] if fname.endswith(".json") else fname
        c = E.charter_view(cid)
        if not isinstance(c, dict):
            continue
        fields = []
        if term in _hay(c.get("title")):
            fields.append("title")
        if term in _hay(c.get("purpose")):
            fields.append("purpose")
        if term in _hay(c.get("scope_in")):
            fields.append("scope_in")
        if fields:
            owner = domains.get(c.get("domain_ref")) or {}
            results.append({
                "kind": "charter", "ref": c.get("id"),
                "title": c.get("title"), "path": c.get("id"),
                "subtitle": c.get("purpose") or "",
                "matched_on": fields, "status": c.get("status", "active"),
                "tenant_id": c.get("tenant_id"),
                "owner": owner.get("name"),
                "owner_retired": owner.get("status") == "retired",
                "score": 3 if "title" in fields else 2,
            })

    for p in E.all_placements():
        wid = (p.get("work_ref") or {}).get("id") or ""
        if term in wid.lower():
            d = domains.get(p.get("domain_ref")) or {}
            results.append({
                "kind": "placement", "ref": p.get("id"),
                "title": wid, "path": p.get("id"),
                "subtitle": "filed to %s" % (d.get("name") or p.get("domain_ref") or "?"),
                "matched_on": ["work_ref"], "status": p.get("phase"),
                "tenant_id": p.get("tenant_id"),
                "confidence": p.get("confidence"),
                "score": 2,
            })

    if tenant_id is not None:
        results = [r for r in results if r.get("tenant_id") == tenant_id]

    results.sort(key=lambda r: (-r["score"], r["kind"], str(r["title"] or "")))
    counts = {}
    for r in results:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return {"query": q, "results": results[:limit], "counts": counts,
            "tenant_id": tenant_id,
            "truncated": len(results) > limit}


# ---------------------------------------------------------- POST /classify -

class ClassifyRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


def _pick_charter_for_write(domains, ref):
    """Domain's own active charter, else nearest ancestor's -- the simple
    walk classify_task/pickCharter uses, so the charter picked for the
    WRITE matches the charter surfaced in the RESPONSE."""
    return R.pick_charter(domains, _charters_view_for_pick(domains), ref)


def _charters_view_for_pick(domains):
    """Merged charter views (status lives in the sidecar in this codebase;
    R.pick_charter reads c.get('status') so it needs the merged view, not
    the raw hashed body)."""
    out = []
    seen = set()
    for ref in domains:
        for body in E.charters_for(ref):
            cid = body.get("id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            v = E.charter_view(cid)
            if v:
                out.append(v)
    return out


@router.post("/classify")
def api_classify(req: ClassifyRequest, tenant: Optional[str] = None):
    """gather_evidence + classify() [NEVER resolve()], resolve a charter via
    a simple pick_charter walk, write_placement() exactly once with
    work_ref={"kind":"task","id":text}. Never 500s on an unreachable charter
    -- write_placement's I-P2 ValueError is caught and surfaced as
    {"blocked": str(e)}."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    # ?tenant= scopes the WRITE as well as the read: the placement is filed
    # under the tenant the UI is currently showing, not under whatever the
    # server was started with. Same resolution order as the read endpoints.
    tenant_id = _tenant_of_record(tenant)
    domains = E.load_domains()

    evidence = E.gather_evidence(utterance=text)
    domain_ref, confidence, mode = E.classify(evidence, tenant_id, domains)

    if domain_ref is None:
        return {
            "blocked": "classify() returned no candidate domain (mode=none) "
                       "-- nothing to route work_ref against",
            "mode": "none",
            "confidence": confidence,
        }

    charter = _pick_charter_for_write(domains, domain_ref)
    charter_id = charter.get("id") if charter else None

    result = {
        "mode": mode,
        "domain_ref": domain_ref,
        "domain_path": E.domain_path(domain_ref, domains),
        "domain_name": (domains.get(domain_ref) or {}).get("name"),
        "confidence": confidence,
        # WHY this domain won, not what was typed: intersect the utterance's
        # terms with the winner's own name tokens + mint_evidence -- the exact
        # set score_domains() overlaps against. Returning the raw tokens made
        # the panel render "Filed to Sutra Labs on `quarterly` `report`" for a
        # floor hold whose mint_evidence contains neither word. [] is honest
        # and the panel already renders that case without the "on ..." clause.
        "matched_terms": R.matched_terms_for(domains.get(domain_ref),
                                             evidence.get("terms"),
                                             tokenizer=E.tokenize),
        "charter": charter,
    }
    if mode == "floor":
        result["held_at_ref"] = domain_ref
        result["held_at_path"] = E.domain_path(domain_ref, domains)

    if charter_id is None:
        return {
            "blocked": "no charter is reachable from this department -- "
                       "write_placement rejects a null charter_id",
            **result,
        }

    try:
        placement = E.write_placement(
            work_ref={"kind": "task", "id": text},
            domain_ref=domain_ref,
            charter_id=charter_id,
            origin="hook",
            confidence=confidence,
            created={"domains": [], "charters": []},
            tenant_id=tenant_id,
            phase="open",
        )
    except ValueError as exc:
        return {"blocked": str(exc), **result}

    result["placement"] = placement
    return result


# ----------------------------------------------------------- POST /simulate -

class SimulateOp(BaseModel):
    op: str
    ref: str
    target: Optional[str] = None


class SimulateRequest(BaseModel):
    ops: List[Dict[str, Any]] = []
    base: Optional[Dict[str, Any]] = None
    # the CLIENT's Date.now(). reorg_sim used to derive "now" as
    # max(placement.ts_ms) to stay pure while the panel banded charter
    # freshness against the browser clock -- so ORG-009/ORG-020 and the
    # freshness pills measured from different instants and could contradict
    # each other on the same screen. One clock, sent by the side that also
    # renders the pills. Absent (a curl, a test) -> server wall clock.
    now_ms: Optional[int] = None


@router.post("/org/simulate")
def org_simulate(req: SimulateRequest):
    """Calls reorg_sim.simulate() against a FRESH load_domains() read --
    never a cached copy."""
    domains = E.load_domains()  # fresh read, every call
    charters = _charters_view_for_pick(domains)
    placements = E.all_placements()

    base = req.base
    base_mismatch = None
    if base:
        current_rows = len(E._read_jsonl(E.CURRENT))
        captured_lines = base.get("domain_index_lines")
        if captured_lines is not None and captured_lines != len(E._read_jsonl(E.DOMAIN_INDEX)):
            base_mismatch = {"_mismatch": True}

    now_ms = req.now_ms if req.now_ms is not None else int(time.time() * 1000)
    sim = R.simulate(req.ops or [], domains, charters, placements,
                     base=base_mismatch, now_ms=now_ms)
    return {
        "domains2": sim["domains2"],
        "findings": sim["findings"],
        "max_depth": sim["max_depth"],
        "not_checked": [{"code": c, "reason": r} for c, r in R.NOT_CHECKED],
    }


# ------------------------------------------------------------- GET/POST draft

@router.get("/org/draft")
def org_draft_get():
    if not DRAFT_PATH.exists():
        return {"ops": [], "rationale": "", "plan_origin": "studio-drag",
                "base": None, "validated_at_ms": None}
    try:
        return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise HTTPException(status_code=500, detail="draft file unreadable")


class DraftRequest(BaseModel):
    ops: List[Dict[str, Any]] = []
    rationale: str = ""
    base: Optional[Dict[str, Any]] = None
    validated_at_ms: Optional[int] = None  # ignored -- server always forces null


@router.post("/org/draft")
def org_draft_post(req: DraftRequest):
    """Writes ONE draft file under DRAFTS_DIR (outside SUTRA_NATIVE_HOME).
    plan_origin is fixed to "studio-drag"; validated_at_ms is ALWAYS forced
    to null server-side regardless of what the client sends -- only
    `org validate` (CLI, out of scope for this tier) may set it."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    draft = {
        "ops": req.ops or [],
        "rationale": req.rationale or "",
        "plan_origin": "studio-drag",
        "base": req.base,
        "validated_at_ms": None,  # forced, never trusts the client
        "saved_at_ms": int(time.time() * 1000),
    }
    tmp = DRAFT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(draft, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(DRAFT_PATH)
    return draft


# =========================================================== providers ======
# providers.py owns the availability logic and the settings file; these
# endpoints are transport only. Nothing here touches placement_engine.


@router.get("/providers")
def api_providers():
    """Every catalogued AI provider with its LIVE state, plus which one is
    active.

    `installed` is shutil.which() and nothing else. A provider is offered to
    the UI as selectable only when installed AND configured AND this build has
    an adapter for it -- see POST /providers/active, which refuses the rest.
    The adapter signal is a property of THIS CODEBASE, not the machine: an
    installed CLI we cannot drive is not selectable. When a provider is not
    usable, `reason` names the missing half and the path involved, so the UI
    never has to render a bare "unavailable".
    """
    detail = providers.active_provider_detail()
    return {
        "providers": providers.discover_providers(),
        "active": detail["id"],
        "active_source": detail["source"],
        # overrides (SUTRA_UI_PROVIDER / settings.json) that named something
        # unrunnable and were therefore NOT honoured -- surfaced rather than
        # silently substituted
        "ignored": detail["ignored"],
    }


class ActiveProviderRequest(BaseModel):
    id: str


@router.post("/providers/active")
def api_providers_set_active(req: ActiveProviderRequest):
    """Persist the active provider to ~/.sutra-ui/settings.json.

    REFUSES with 400 + the specific reason when the id is unknown or when the
    provider is not runnable (binary missing, never configured, or no adapter
    in this build). Letting the
    UI select a provider that cannot start would move the failure to the first
    chat message, where it surfaces as a dead websocket rather than an answer.
    """
    try:
        settings = providers.save_settings(provider=req.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail="could not write settings: %s" % exc)
    return {
        "active": settings["provider"],
        "provider": providers.provider_by_id(settings["provider"]),
        "settings": settings,
        "providers": providers.discover_providers(),
        # Who is signed in to Claude on this machine. None when unknown -- the
        # panel must render an unknown identity rather than a placeholder that
        # looks real. The header used to be a hardcoded "TC".
        "claude_account": claude_local.account(),
    }


def _codex_state():
    """Everything the Codex rows need to redraw themselves, in one answer.

    THE BUG THIS FIXES (2026-09-08). The panel keeps the CREDENTIAL and the
    READINESS in two different places -- `S.codexAuth` and `PROVIDERS` -- and
    only the first was ever refreshed after a sign-in. `PROVIDERS` is filled
    exactly once, by loadRuntime() inside boot(); nothing else in the app
    re-reads it. So a successful ChatGPT sign-in wrote ~/.codex/auth.json,
    flipped `configured` server-side, updated the sign-in block to "Signed in
    with ChatGPT" -- and left the row directly above it reading "Installed, but
    not signed in yet" with its radio disabled, until the operator reloaded the
    page. Sign-OUT had the same gap in the more dangerous direction: the row
    kept saying "Ready to use" over a Codex holding no credential.

    `providers` and `settings` ride along so the DEFAULT PROVIDER list
    re-evaluates from the SAME read that observed the change -- exactly what
    _deepseek_state() does for its own row, and what POST /settings/provider-bin
    does. The alternative was a second request the panel would have to know to
    fire, which is the round trip that was missing in the first place.

    `settings` is what makes sign-OUT complete: load_settings() re-runs
    active_provider_detail(), so a stored `provider: codex` that just stopped
    being runnable comes back in `provider_ignored` with the fallback already
    chosen -- the app's existing handling for a provider going away, not a new
    path.

    `runtime` is the OTHER half of a usable Codex, and it is not redundant with
    `providers`: the row's `installed` says whether a `codex` resolves, while
    this says whether an install could be attempted and why not. The Install
    control needs the second. codex_install.state() runs NO SUBPROCESS -- see
    its docstring -- so this is affordable on a route the sign-in poll hits
    every 2 seconds, and cheap next to the `codex login status` spawn that
    route already pays for.

    `models_by_provider` closes the SAME GAP one link further along, and it is
    the reason the Model picker read "CLI default" alone on a machine where
    discovery had just answered. The published model list is a SIBLING of
    `settings` in the /settings payload, not a key inside it -- so carrying
    `settings` here never carried the models, and the panel writes
    MODELS_BY_PROVIDER exactly once, in loadRuntime() inside boot(). Discovery
    cannot have run by then: refresh_if_stale() is reached only from the route
    below, which the panel asks for when the AI Provider screen opens. Boot
    therefore always published the pre-discovery list and nothing re-asked, so
    the picker stayed empty for the life of the window and a reload "fixed" it.

    It rides on THIS answer because refresh_if_stale() runs above, before this
    spread -- so the models discovered by this very request are in the reply
    that observed them. No new endpoint, no poll, no second round trip the
    client would have to know to fire. all_models_by_provider() is REUSED
    rather than reimplemented, and it spawns nothing (models_for() reads
    codex_models' cache; see its docstring and test_models_for_never_spawns),
    so this stays affordable on the route the sign-in poll hits every 2s.
    """
    return {"providers": providers.discover_providers(),
            "settings": providers.load_settings(),
            "models_by_provider": providers.all_models_by_provider(),
            "runtime": codex_install.state()}


@router.get("/providers/codex/auth")
def api_codex_auth():
    """Which credential the Codex CLI is holding -- and therefore how the
    operator is billed for it.

    Transport only; providers.codex_auth() owns the decision and is the single
    place that decides codex login state.

    KEPT OFF /providers AND /settings ON PURPOSE. Those two are read on every
    panel boot, every settings open and, through load_settings(), every fs
    call -- and this one spawns a subprocess. The panel asks for it when the
    AI Provider screen opens, and again after each sign-in action.

    Never 500s on a failed probe. A CLI that cannot be reached or answers in
    an unfamiliar shape comes back as state "unknown" with the reason, which
    the row renders as "could not tell" -- never as a billing mode. Claiming
    "usage included" to someone paying per token is the failure this endpoint
    is shaped to avoid.

    `login_in_flight` is merged in HERE rather than inside codex_auth(),
    because codex_login imports providers and the reverse would be a cycle --
    and providers.py's contract is reads plus one settings file, which holding
    live process state would break. It exists because a panel RELOAD loses its
    in-memory busy state: with a sign-in child running and about to change the
    credential, the row would otherwise render "Not signed in", which is the
    row lying about state.
    """
    auth = providers.codex_auth()
    # THE ONE PLACE MODEL DISCOVERY IS ALLOWED TO SPAWN. This request is
    # already paying for `codex login status`, and it is the request the
    # provider screen makes -- so it is where the picker's list can be brought
    # up to date without putting a subprocess anywhere near a render.
    #
    # TTL- AND STATE-GATED, so the 2-second sign-in poll does not start an
    # app-server per tick: unchanged state inside the TTL is a dict lookup.
    # Passing the state is also what makes the picker correct across a
    # credential change -- a ChatGPT plan and an API key are scoped by
    # different things, and rather than assume they offer the same models,
    # a change here re-asks Codex.
    codex_models.refresh_if_stale(auth.get("state"))
    return {**auth,
            **_codex_state(),
            "login_in_flight": codex_login.in_flight(),
            # WHETHER THERE IS A KEY TO RESTORE -- never a claim about which
            # credential is live. providers.codex_auth() above owns that, and
            # the two must not be conflated: a saved key says nothing about
            # what codex is holding right now, and the row renders the live
            # mode from the probe and the RESTORE OFFER from this.
            #
            # Merged HERE for the same reason login_in_flight is: codex_auth
            # imports providers, so providers importing it back would be a
            # cycle. Costs no subprocess -- state() reads one small file and
            # asks whether the keychain loads.
            "stored": codex_auth.state()}


class CodexLogoutRequest(BaseModel):
    #: Must be exactly True. Signing Codex out DESTROYS the credential it
    #: holds, and if that is an API key it is the only copy anywhere -- Sutra
    #: never had one. The panel's confirm dialog is client-side, so a caller
    #: reaching this route directly bypasses it; this flag is what stops a bare
    #: POST from being a permanent loss.
    confirm: bool = False


@router.post("/providers/codex/login")
def api_codex_login():
    """Start the Codex ChatGPT sign-in and return AT ONCE.

    The browser flow is a human round-trip -- three minutes, or never. This
    route does not wait for it: it spawns, hands back {"started": true}, and
    the panel polls GET /providers/codex/auth until the credential changes.
    Waiting here would park a threadpool worker, give the panel nothing to
    cancel (apiGet has no timeout), and orphan the child on a page reload.

    This is the BROWSER fallback. The desktop shell keeps its own IPC verb and
    keeps preferring it. Note one asymmetry in this path's favour: the binary
    is resolved through providers.provider_bin, so a hand-picked path set in
    Settings IS honoured here -- the IPC path cannot honour it, because
    executing a path the renderer chose would be a worse hole than the
    inconvenience.
    """
    try:
        return codex_login.start()
    except codex_login.NoBinary as exc:
        # THE ONE PLACE THAT PROVES INTENT AND GAP TOGETHER -- the operator
        # asked to sign Codex in, and there is no Codex to sign in to. Kicked
        # server-side so the runtime lands whatever the browser does next; see
        # _codex_kick_install. The refusal below is unchanged: this route
        # promises a browser window, not a 300s download.
        _codex_kick_install()
        raise HTTPException(status_code=400, detail={
            "code": "CODEX_NOT_ON_PATH", "message": str(exc),
            "user_action": "INSTALL_OR_SET_PATH"})
    except codex_login.Busy as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CODEX_BUSY",
            "message": "a codex %s is already running" % exc,
            "user_action": "CANCEL_FIRST"})
    except OSError as exc:
        raise HTTPException(status_code=500, detail={
            "code": "CODEX_SPAWN_FAILED",
            "message": "could not start codex: %s" % exc})


@router.post("/providers/codex/login/cancel")
def api_codex_login_cancel():
    """Stop a running sign-in. SIGTERM, then SIGKILL after the grace period.

    {"cancelled": false} when nothing was running is a fact, not a failure:
    Cancel can lose a race with the flow completing, and reporting an error for
    that would be a lie about state.
    """
    return {"cancelled": codex_login.cancel()}


@router.post("/providers/codex/logout")
def api_codex_logout(req: CodexLogoutRequest):
    """Remove the credential the codex CLI holds. Requires confirm: true.

    Blocking is fine here -- no human is in the loop, codex deletes a file and
    returns -- so this answers with the FRESH probe rather than leaving the
    panel to discover the new state on a second request.
    """
    if req.confirm is not True:
        raise HTTPException(status_code=400, detail={
            "code": "CONFIRM_REQUIRED",
            "message": "signing Codex out destroys the credential it holds, "
                       "and Sutra never had a copy. Send {\"confirm\": true} "
                       "to proceed.",
            "user_action": "CONFIRM"})
    try:
        result = codex_login.logout()
    except codex_login.NoBinary as exc:
        raise HTTPException(status_code=400, detail={
            "code": "CODEX_NOT_ON_PATH", "message": str(exc),
            "user_action": "INSTALL_OR_SET_PATH"})
    except codex_login.Busy as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CODEX_BUSY",
            "message": "a codex %s is running -- cancel it first" % exc,
            "user_action": "CANCEL_FIRST"})
    # The probe runs either way. A logout that FAILED still has to report what
    # codex actually holds now, or the row would show a state nobody verified.
    #
    # _codex_state() rides along for the same reason it does on the poll: this
    # is the read that observed the credential going away, so the provider row
    # and the active-provider fallback must re-evaluate from it rather than
    # keep boot()'s answer. Without it, signing out left "Ready to use" and an
    # enabled radio over a Codex that could no longer answer a message.
    return {**result, "auth": {**providers.codex_auth(),
                               "login_in_flight": codex_login.in_flight()},
            **_codex_state()}


@router.get("/providers/codex/plan")
def api_codex_plan():
    """How much of this ChatGPT plan's Codex allowance is spent.

    `account/rateLimits/read` over the same `codex app-server` transport
    codex_models already uses for model/list -- one mechanism, two reads.
    Measured 2026-09-09: answers in under a second and CONSUMES NO MODEL TURN.

    CHATGPT ONLY, and the state is read here rather than trusted from the
    client: a rate-limit window is a property of a ChatGPT PLAN, and the
    protocol's own PlanType enum has no API-key member. In any other state this
    answers `{"plan": null}` and asks Codex nothing -- so API-key mode never
    sends the request, and a credential change makes the indicator disappear
    rather than go stale.

    NOTHING ABOUT DOLLARS. API-key spend lives behind OpenAI's Admin API, which
    needs a separate and more privileged credential than Sutra holds. Not
    pursued on purpose.

    WHY IT HAS ITS OWN ROUTE rather than riding /providers/codex/auth: this is
    the GLOBAL usage figure, and the client fetches it through loadUsage() --
    the same function that already fetches Claude's windows and DeepSeek's
    balance, on boot, on screen open and after every completed turn. Folding it
    into the auth route would tie a global indicator to the provider screen.

    Never 500s. A failed read is `{"plan": null}` and the indicator draws
    nothing, which is the state before this existed.
    """
    state = providers.codex_auth().get("state")
    return {"state": state,
            "plan": codex_models.refresh_plan_if_stale(state)}


# ------------------------------------------------------ codex provisioning --
# THE OTHER HALF OF A USABLE CODEX. Everything above moves a CREDENTIAL; this
# puts the BINARY on the machine. They fail independently and the operator has
# to be able to tell which one is missing, so they are separate routes -- the
# same split POST /providers/deepseek/cli made, for the same reason.
#
# codex_install.py owns the decision and the refusals; this is transport.

def _codex_install_control(request):
    """Authorise a Codex CLI install, or refuse it with the reason that applies
    to THIS server.

    THREE LANES, AND THE THIRD ONE IS WHY THIS IS NOT A COPY OF
    _deepseek_write_control. Writing the two-lane version first was a mistake
    caught before it shipped, and the reason is worth keeping: on a
    DESKTOP-STARTED server neither of DeepSeek's lanes is reachable from the
    panel. The renderer deliberately never holds the desktop token (main.js:
    "the renderer never has it"), and deepseek_session.arm() mints no one-time
    code when SUTRA_DESKTOP_TOKEN is set -- so the desktop app's own window,
    the primary user of this feature, would have met a 403. DeepSeek escapes
    that only because it has an IPC verb (sutra:deepseek-cli-install) that
    calls the route from the MAIN process with the token attached; Codex has no
    such verb, and adding one would put the fix inside a frozen app binary
    where a newer panel could not rely on it.

      1. x-sutra-desktop-token  the Electron shell, calling from its main
                                process. Kept so a shell that does gain a verb
                                later needs no change here.
      2. x-sutra-session-token  a browser on a CLI-started server, holding the
                                token it traded this process's stdout code for.
      3. x-sutra-panel          THE PANEL ITSELF, either transport.

    WHY LANE 3 IS NOT A HOLE. app.py's origin guard already refuses every
    mutating request whose Origin is not loopback, and demands PANEL_TOKEN from
    any request that carries an Origin at all -- so no other page in any
    browser can reach this, because no other origin can read the panel to learn
    the token. What lane 3 additionally admits is a NON-BROWSER local process
    (no Origin, so the guard lets it through, exactly as it does for POST
    /providers/codex/login). And that is the same calculus codex_login.py
    already wrote down for its own routes: such a process can already run npm
    itself and already write ~/.sutra-ui/settings.json, so this hands it no
    authority it did not have.

    THE ROUTE TAKES NO ARGUMENTS, which is what makes that true. The package,
    the version and the destination are all constants in codex_install; a
    caller chooses nothing. The only effect obtainable is "the pinned Codex CLI
    exists in Sutra's own folder", idempotently. It is not a path to fetching
    arbitrary code, and it never touches a credential.

    >>> WHY deepseek_session APPEARS IN A CODEX ROUTE <<<
    The session token is a per-SERVER browser-write capability -- 80 bits on
    this process's stdout, single-use, nothing to do with DeepSeek's key. It
    lives in a module named for the feature that needed it first. Only
    verify() is called, so nothing about DeepSeek's install or credential
    behaviour is reachable from here, and nothing in that module is modified.
    EXTRACTION POINT: this and _deepseek_write_control() want one
    panel_session.py once a second provider needs the lane -- which is now.

    hmac.compare_digest on every literal comparison, matching _desktop_control
    and _deepseek_write_control: a `==` would stop at the first mismatching
    byte, which is a timing oracle for the token.
    """
    sent_desktop = request.headers.get("x-sutra-desktop-token") or ""
    if DESKTOP_TOKEN and sent_desktop and hmac.compare_digest(
            sent_desktop, DESKTOP_TOKEN):
        return
    if deepseek_session.verify(request.headers.get(deepseek_session.HEADER) or ""):
        return
    # Imported HERE rather than at module scope: app.py imports this module, so
    # a top-level `import app` would be a cycle.
    import app
    sent_panel = request.headers.get("x-sutra-panel") or ""
    if sent_panel and hmac.compare_digest(sent_panel, app.PANEL_TOKEN):
        return
    raise HTTPException(status_code=403, detail=(
        "installing the Codex CLI needs this panel's token, and this request "
        "carried none that matched. Reload the panel and try again."))


@router.post("/providers/codex/cli")
def api_codex_cli_install(request: Request):
    """Install the `codex` CLI into Sutra's own directory and register it.

    SYNCHRONOUS, and that is what makes it survive the window closing: uvicorn
    runs a sync endpoint on a worker thread and does not cancel it when the
    client goes away, so an npm fetch started here finishes whatever the panel
    does next. A caller that reloads and retries meets codex_install's
    single-flight lock, waits, and is answered ALREADY from the first run's
    result rather than unpacking a second copy over a half-written tree.

    Answers 200 with ok:false on a refusal, like its neighbours -- the state
    block rides along either way so the rows correct themselves even when the
    install did not happen. 4xx stays for the things that really are protocol
    problems: no token, or a malformed body.
    """
    _codex_install_control(request)
    try:
        out = codex_install.install()
    except codex_install.CodexInstallError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc),
                **_codex_state()}
    return {**out, **_codex_state()}


def _codex_kick_install():
    """Start the CLI install SERVER-SIDE and forget it.

    WHY, given that 07-loaders.js already offers an Install button and chains
    one onto a sign-in. Because that chain lives in the browser, and everything
    it depends on can be gone the moment after: the window closed, the page
    reloaded, the desktop bridge dead, an app binary too old to have the verb.
    Every one of those leaves the state this feature exists to abolish -- an
    operator who asked for Codex on a Mac that has no Codex runtime, and
    nothing running that will fix it.

    CALLED FROM THE ONE PLACE THAT PROVES THE INTENT AND THE GAP AT ONCE: the
    NoBinary arm of POST /providers/codex/login. Reaching it means the operator
    clicked "Sign in with ChatGPT" (intent) and `codex` did not resolve (gap).
    The request still refuses -- there is nothing to sign in to yet, and
    pretending otherwise would hold a 300s download open under a button that
    promised a browser -- but by the time they have read the message and come
    back, the runtime is usually there.

    NOT a replacement for the route. The panel still calls POST
    /providers/codex/cli, because that call is what carries progress and a real
    failure message to the screen; the single-flight lock is what makes the two
    safe together.

    DAEMON, and deliberately silent. There is no channel here to report into --
    the login response has already been computed -- and a failure is not lost:
    the provider row still reads "not installed" with its own reason, and the
    Install button is still there.

    NO CREDENTIAL IS INVOLVED. This fetches a binary. It does not read, write,
    validate or delete a ChatGPT session or a saved API key, and codex_install
    has no path to any of them.
    """
    def _run():
        try:
            codex_install.install()
        except Exception:            # noqa: BLE001 -- nothing to report into
            pass
    threading.Thread(target=_run, name="codex-cli-install",
                     daemon=True).start()


# ------------------------------------------------------- deepseek sign-in ---
# THE ONLY WRITE SURFACE FOR A DEEPSEEK KEY, and it is AUTHENTICATED -- by
# EITHER of two tokens, checked by _deepseek_write_control() below.
#
# WHY THESE ROUTES MAY EXIST AT ALL, when main.js says a route that accepted an
# API key would be "a credential WRITE surface any page on this machine could
# POST to". That sentence is about an UNAUTHENTICATED route, which is what the
# rest of this API is. These are not.
#
#   LANE 1, the desktop app: x-sutra-desktop-token, minted by the Electron
#   shell (main.js), handed only to the backend it spawns, attached by the MAIN
#   process -- the renderer never holds it, so no page in any browser can reach
#   these, and neither can a backend the shell merely attached to. Same
#   doctrine as POST /api/balance/actionable. UNCHANGED.
#
#   LANE 2, a browser on a CLI-run server: x-sutra-session-token, traded for
#   the one-time code this process printed on its own STDOUT (see
#   deepseek_session). A web page cannot read a terminal, so the capability
#   still only reaches a browser by the operator's own act of copying it
#   across -- and app.py's origin guard already refuses a cross-origin mutation
#   that does not carry PANEL_TOKEN, which another origin cannot read either.
#   Lane 2 exists ONLY when lane 1 does not: deepseek_session.arm() mints no
#   code when SUTRA_DESKTOP_TOKEN is set, so a desktop-started backend has
#   exactly the one door it always had.
#
# THE UPDATE ROUTES ARE NOT IN THIS. They still call _desktop_control(), which
# knows only about lane 1. Arming an unattended helper to replace
# /Applications/Sutra.app is a persistence primitive; signing a key into the
# operator's own keychain is not, and one gate for both would have quietly
# handed the first the second's threat model.
#
# WHY NOT COPY CODEX EXACTLY AND SPAWN IN THE SHELL. Codex's key goes to a
# CLI's stdin and Sutra keeps no copy, so it never needed a backend at all.
# DeepSeek's key has to be STORED by Sutra and read back by Python at request
# time (app.py's ws_chat, deepseek_usage.py) -- and the keychain adapter is
# Python (connectors/credentials/keychain.py). Electron safeStorage cannot
# serve those readers. So the store lives where the readers are, and the write
# crosses one authenticated loopback hop instead.
#
# THE KEY IS NEVER RETURNED, LOGGED OR ECHOED. What comes back is a mask, a
# code and a fixed sentence -- see deepseek_auth.
#
# 200 WITH ok:false for a classified refusal (bad key, network, env override,
# no keychain), matching POST /providers/codex/logout, which answers 200 with
# the operation's own result plus a fresh state. A rejected key is an expected
# outcome of this control, not a protocol error, and an HTTPException body
# would put the reason somewhere the shell has to unwrap. 4xx stays for the
# things that really are protocol problems: no token, or a malformed body.

def _deepseek_write_control(request):
    """Authorise a DeepSeek key write, or refuse it with the reason that
    applies to THIS server.

    hmac.compare_digest on both lanes, the way _desktop_control and app.py's
    /api/balance/actionable gate do it: a `==` here would compare byte by byte
    and stop at the first mismatch, which is a timing oracle for the token.

    THE REFUSAL SAYS WHICH LANE IS EVEN POSSIBLE. A single "forbidden" left the
    browser field looking broken; a desktop-started server has no code to
    paste, a paired-once server needs a restart, and only the third case is
    "paste the code" -- so each says so.
    """
    sent_desktop = request.headers.get("x-sutra-desktop-token") or ""
    if DESKTOP_TOKEN and sent_desktop and hmac.compare_digest(
            sent_desktop, DESKTOP_TOKEN):
        return
    sent_session = request.headers.get(deepseek_session.HEADER) or ""
    if deepseek_session.verify(sent_session):
        return
    if DESKTOP_TOKEN:
        raise HTTPException(status_code=403, detail=(
            "writing a DeepSeek key needs the desktop app's token, and this "
            "request carried none that matched. This server was started by the "
            "Sutra app, so sign in from its window."))
    detail = ("writing a DeepSeek key needs a session token, and this request "
              "carried none that matched. ")
    if sent_session:
        detail += ("A token stops working when the server restarts -- paste "
                   "this server's sign-in code again to get a new one.")
    else:
        detail += deepseek_session.state()["reason"] or ""
    raise HTTPException(status_code=403, detail=detail)


class DeepSeekSessionRequest(BaseModel):
    #: The one-time code from the server's stdout. Optional for the same reason
    #: DeepSeekKeyRequest.key is: FastAPI's validation errors can echo the
    #: offending INPUT, and a 422 quoting a half-typed code back into a
    #: response body is a worse answer than a classified refusal.
    code: Optional[str] = None


@router.post("/providers/deepseek/session")
def api_deepseek_session(req: DeepSeekSessionRequest):
    """Trade the one-time code for a session token that authorises key writes.

    UNGATED BY DESIGN, AND THAT IS NOT A HOLE. There is nothing this route
    could be gated BY -- it exists to hand out the credential the gate wants,
    which is the shape of every pairing exchange. What protects it is the code
    itself: 80 bits that live only on this process's stdout, single-use, and
    behind app.py's origin guard (a cross-origin POST without PANEL_TOKEN is
    refused, and no other origin can read the panel to learn PANEL_TOKEN).

    200 WITH ok:false for a classified refusal -- a mistyped code is an
    expected outcome of this control, and it must not land in the panel as a
    thrown fetch error whose message the operator has to decode. 4xx stays for
    protocol problems, and there are none left here.

    THE TOKEN IS RETURNED EXACTLY ONCE, in this response, and never appears in
    _deepseek_state() or GET /api/settings -- deepseek_session.state() reports
    that a code exists and never what it or the token is.
    """
    try:
        token = deepseek_session.exchange(req.code or "")
    except deepseek_session.SessionCodeError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc),
                **_deepseek_state()}
    return {"ok": True, "code": "PAIRED", "token": token,
            "message": "This browser can now save a DeepSeek key. The code is "
                       "used up -- restart the server if you need another.",
            **_deepseek_state()}


class DeepSeekKeyRequest(BaseModel):
    #: Trimmed and validated in deepseek_auth.clean(). Optional so a malformed
    #: body is a classified "no API key was given" rather than a 422 -- FastAPI's
    #: validation errors can echo the offending INPUT, and the input here is a
    #: live credential.
    key: Optional[str] = None


def _deepseek_state():
    """Everything the row needs to redraw itself, in one answer.

    `providers` and `settings` ride along so the DEFAULT PROVIDER list
    re-evaluates from the SAME read that performed the write -- exactly what
    POST /settings/provider-bin does. Without them the panel would have to
    fire a second request and could render a row that disagreed with the
    keychain for one paint.

    `settings` is what makes sign-OUT complete: load_settings() re-runs
    active_provider_detail(), so a stored `provider: deepseek` that just
    stopped being runnable comes back in `provider_ignored` with the fallback
    already chosen -- the app's existing handling for a provider going away,
    not a new path.
    """
    return {"auth": providers.deepseek_auth_state(),
            "providers": providers.discover_providers(),
            "settings": providers.load_settings()}


#: The saved-key sentence, which is true regardless of what else the machine
#: is missing. Split out because what follows it is NOT unconditional.
_DEEPSEEK_SAVED = ("DeepSeek accepted the key and it is saved on this Mac "
                   "(%s).")


def _deepseek_saved_message(mask, provider_rows):
    """What to tell the operator after a key write actually succeeded.

    THE BUG THIS FIXES. This message used to end with "DeepSeek is selectable
    above now -- no restart." unconditionally. A key is only ONE of DeepSeek's
    two requirements -- providers._describe sets `installed` from
    shutil.which() alone, and Sutra spawns `<bin> --acp` to talk to DeepSeek --
    so on a Mac without the CLI the panel confirmed a success in the same paint
    where the row above it correctly read "Not installed on this Mac". The
    operator had done nothing wrong and was sent looking at their key.

    The not-installed arm quotes the row's OWN `reason` rather than restating
    the requirement here: providers._deepseek_reason already composes that
    sentence (naming DEEPSEEK_CLI_PACKAGE, the PATH search, SUTRA_UI_DEEPSEEK_BIN),
    it is what the row itself renders, and a second copy in this module is a
    second thing to keep in step. `provider_rows` is the list from the same
    _deepseek_state() read that answered the write, so the message and the row
    can never disagree for a paint.

    Returns (code, message). The code discriminates the two outcomes for
    tests and for any future caller; no client branches on it today, and
    `ok` stays True in both -- the key IS saved, and the panel clears the
    field on `ok` (07-loaders.js).
    """
    saved = _DEEPSEEK_SAVED % mask
    row = next((p for p in (provider_rows or []) if p.get("id") == "deepseek"),
               None)
    #: No row at all should be impossible (deepseek is catalogued), and a
    #: missing row is still not evidence the CLI is there -- so say only what
    #: was actually established and let the row below speak for itself.
    if row is None:
        return "SAVED", saved
    if row.get("installed"):
        return "SAVED", "%s DeepSeek is selectable above now -- no restart." % saved
    reason = (row.get("reason") or "").strip()
    tail = (" DeepSeek is still not selectable above: %s" % reason if reason
            else " DeepSeek is still not selectable above -- see the row for why.")
    return "SAVED_NO_CLI", saved + tail


@router.post("/providers/deepseek/key")
def api_deepseek_key_save(req: DeepSeekKeyRequest, request: Request):
    """Validate a DeepSeek key against the API, then store it in the keychain.

    Validation happens BEFORE the write (deepseek_auth.save), so a key that
    DeepSeek will not accept never becomes a saved key the row claims works.

    A successful write does NOT imply a usable provider -- see
    _deepseek_saved_message.
    """
    _deepseek_write_control(request)
    try:
        marker = deepseek_auth.save(req.key or "")
    except deepseek_auth.DeepSeekAuthError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc),
                **_deepseek_state()}
    #: ONE read, shared by the message and the rows it must agree with.
    state = _deepseek_state()
    code, message = _deepseek_saved_message(marker["mask"], state["providers"])
    if code == "SAVED_NO_CLI":
        _deepseek_kick_install()
    return {"ok": True, "code": code, "mask": marker["mask"],
            "message": message, **state}


def _deepseek_kick_install():
    """Start the CLI install SERVER-SIDE, off the key request, and forget it.

    WHY, given that 07-loaders.js already chains the install onto a successful
    save. Because that chain lives in the browser, and everything it depends on
    can be gone the moment after the key is written: the window closed, the page
    reloaded, the desktop bridge dead, an app binary too old to have the verb
    (the panel is served fresh by the backend, preload.js ships frozen inside
    Sutra.app). Every one of those leaves the exact state this feature exists to
    abolish -- a validated key saved on a Mac with no CLI, and nothing running
    that will fix it. A correct key now means the install is ATTEMPTED, whatever
    the client does next.

    NOT a replacement for the route. The panel still calls it, because that call
    is what carries progress and a real failure message to the screen;
    deepseek_install's single-flight lock is what makes the two safe together --
    whichever arrives second waits, then answers ALREADY from the first one's
    result instead of unpacking npm over it a second time.

    DAEMON, and deliberately silent. An npm fetch is up to 300s and must not
    hold the 20s key request open (main.js DEEPSEEK_KEY_TIMEOUT), and there is
    no channel here to report into -- the key response has already been
    computed. A failure is not lost: the provider row still reads "not
    installed" with its own reason, and the Install button is still there.
    """
    def _run():
        try:
            deepseek_install.install()
        except Exception:            # noqa: BLE001 -- nothing to report into
            pass
    threading.Thread(target=_run, name="deepseek-cli-install",
                     daemon=True).start()


@router.post("/providers/deepseek/cli")
def api_deepseek_cli_install(request: Request):
    """Install the `deepseek` CLI, the OTHER half of a usable DeepSeek.

    WHY THIS IS NOT PART OF THE KEY WRITE, given that the panel fires it
    straight after one. Three reasons, and the first is decisive:

      1. The desktop bridge caps the key call at 20s (main.js
         DEEPSEEK_KEY_TIMEOUT, sized against deepseek_auth's 8s probe). An npm
         download does not fit in that and must not be made to try.
      2. The two can fail independently and the operator needs to know WHICH.
         Folding them into one call collapses "your key is wrong" and "npm
         could not reach the registry" into one refusal, and only one of those
         is about anything they typed.
      3. A key already saved on a Mac that has no CLI -- the exact state in the
         2026-09-07 screenshot -- needs the install WITHOUT a second key write.
         A separate route is the only shape that serves that case at all.

    SAME GATE AS THE KEY WRITE. Installing software is at least as
    consequential as saving a credential, so this goes through
    _deepseek_write_control() rather than being left open: an unauthenticated
    caller must not be able to make this server fetch and register an
    executable.

    Answers 200 with ok:false on a refusal, like its neighbours -- the state
    block rides along either way so the row corrects itself even when the
    install did not happen.
    """
    _deepseek_write_control(request)
    try:
        out = deepseek_install.install()
    except deepseek_install.DeepSeekInstallError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc),
                **_deepseek_state()}
    return {**out, **_deepseek_state()}


@router.post("/providers/deepseek/key/remove")
def api_deepseek_key_remove(request: Request):
    """Delete the stored key. Idempotent -- see deepseek_auth.remove."""
    _deepseek_write_control(request)
    try:
        out = deepseek_auth.remove()
    except deepseek_auth.DeepSeekAuthError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc),
                **_deepseek_state()}
    return {"ok": True, "code": "REMOVED", "removed": out["removed"],
            "message": ("The saved key is gone from the login keychain."
                        if out["removed"] else
                        "There was no saved key on this Mac to remove."),
            **_deepseek_state()}


# ============================================================ settings ======

@router.get("/settings")
def api_settings_get():
    """Panel settings: {provider, permission_mode, workdir}.

    Stored in ~/.sutra-ui/settings.json (NOT under SUTRA_NATIVE_HOME -- these
    are preferences, not governance state). Values absent or invalid in the
    file fall back to documented defaults, and `invalid_stored_values` reports
    anything that was ignored instead of quietly correcting it.

    permission_mode is one of plan|acceptEdits|bypassPermissions, default
    "plan":
      plan               the agent plans and proposes; every edit needs an
                         explicit approval. This is the default (SAFETY rule 4).
      acceptEdits        THE AGENT WRITES FILES WITHOUT ASKING. It can create,
                         modify and delete files under `workdir` with no
                         per-edit prompt. Choose it deliberately.
      bypassPermissions  everything auto-approved, including shell commands.
    """
    unlocked = providers.unsafe_modes_allowed()
    return {
        "settings": providers.load_settings(),
        "permission_modes": [
            {"id": m, "note": providers.PERMISSION_MODE_NOTES.get(m),
             "default": m == providers.DEFAULT_PERMISSION_MODE,
             "writes_files": m in providers.UNSAFE_PERMISSION_MODES,
             # A control the server will refuse must say so BEFORE it is
             # clicked. Without this the panel offered three modes, accepted
             # clicks on all three, and answered two of them with a 400 -- which
             # reads as "settings are broken" rather than "this is gated".
             "settable": m not in providers.UNSAFE_PERMISSION_MODES or unlocked,
             "requires_unlock": m in providers.UNSAFE_PERMISSION_MODES}
            for m in providers.PERMISSION_MODES
        ],
        "unsafe_modes_allowed": unlocked,
        "unsafe_modes_env": providers.UNSAFE_MODES_ENV,
        # An allow-list, not free text: the value reaches the provider's model
        # flag, where an unknown string fails as a dead socket seconds later
        # instead of a refusal -- or, on DeepSeek's fork, does not fail at all
        # and a different model quietly answers.
        #
        # KEYED BY PROVIDER, and the flat `models` list it replaces is GONE
        # rather than kept alongside. The panel is the only client, and a flat
        # list next to a keyed one is the same "two copies that can disagree"
        # this change exists to remove. Providers with no models simply have no
        # entry, which is how the picker knows not to render one.
        "models_by_provider": providers.all_models_by_provider(),
        # WHICH PANES MAY SHOW WHICH CONTROLS. Both are ADDITIONS: the flat
        # `permission_modes` above is unchanged and still carries all six with
        # their notes and gating, because it is the vocabulary -- these two say
        # who can honour what.
        #
        # The panel rendered Claude's controls on every pane. On a DeepSeek
        # pane all five turn options were collected, sent, and dropped by the
        # server (build_acp_args has no per-turn argv to put them in), and
        # three of the six permission modes ran as `default` while the control
        # kept displaying the choice. Same failure as the model picker before
        # models_by_provider: a control that cannot act is worse than an absent
        # one, because it reads as a setting that took effect.
        #
        # Keyed the same way, absent-when-empty for the same reason, so the
        # client's test for "does this pane have this control" is "is this
        # provider in this dict".
        "turn_options_by_provider": providers.all_turn_options_by_provider(),
        "permission_modes_by_provider": providers.all_permission_modes_by_provider(),
        "providers": providers.discover_providers(),
        # Who is signed in to Claude on this machine. None when unknown -- the
        # panel must render an unknown identity rather than a placeholder that
        # looks real. The header used to be a hardcoded "TC".
        "claude_account": claude_local.account(),
    }


class ProviderBinRequest(BaseModel):
    provider: str
    #: None or "" clears the override and returns to PATH lookup.
    path: Optional[str] = None


class SettingsRequest(BaseModel):
    provider: Optional[str] = None
    permission_mode: Optional[str] = None
    workdir: Optional[str] = None
    onboarded: Optional[bool] = None
    model: Optional[str] = None
    # str to GRANT (must equal providers.UNSAFE_ACK_PHRASE), False to withdraw.
    # Deliberately not a bare bool -- see providers.UNSAFE_ACK_PHRASE.
    unsafe_ack: Optional[Union[str, bool]] = None


@router.post("/settings/provider-bin")
def api_provider_bin(req: ProviderBinRequest):
    """Point the panel at a CLI it could not find on its own.

    This exists because the documented escape hatch was an environment
    variable, and a .app opened from Finder cannot be given one without
    `launchctl setenv` and a relaunch -- so the panel was naming a fix most of
    the people who needed it could not perform.

    The path is validated before it is stored: a file that does not exist or
    is not executable is refused here rather than accepted and failed later,
    because "found it and it will not run" is a worse error than "cannot find
    it" and points further from the mistake.
    """
    if providers.provider_by_id(req.provider) is None:
        raise HTTPException(status_code=400, detail={
            "code": "UNKNOWN_PROVIDER", "message": "no provider %r" % req.provider})
    try:
        stored = providers.set_provider_bin(req.provider, req.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={
            "code": "BAD_BINARY_PATH", "message": str(exc),
            "user_action": "PICK_ANOTHER_PATH"})
    return {"provider": req.provider, "path": stored,
            "providers": providers.discover_providers()}


@router.post("/settings")
def api_settings_post(req: SettingsRequest):
    """Partial update -- only the keys present in the body are written.

    Same refusal as POST /providers/active: a provider that is not runnable is
    rejected with 400 and the reason, never stored. An unknown permission_mode
    is rejected rather than silently downgraded, so the operator is never told
    a mode was applied when it was not.
    """
    if (req.provider is None and req.permission_mode is None
            and req.workdir is None and req.onboarded is None and req.model is None
            and req.unsafe_ack is None):
        raise HTTPException(
            status_code=400,
            detail="nothing to update -- send at least one of: provider, "
                   "permission_mode, workdir, onboarded, model")
    try:
        settings = providers.save_settings(
            provider=req.provider,
            permission_mode=req.permission_mode,
            workdir=req.workdir,
            onboarded=req.onboarded,
            model=req.model,
            unsafe_ack=req.unsafe_ack,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail="could not write settings: %s" % exc)
    return {"settings": settings}


# ============================================================ filesystem =====
# Backs the editor. Every path is resolved against the validated workdir and refused
# if it escapes -- the workdir is the agent's own cwd, so READING opens no surface the
# chat channel did not already have. WRITING is different in kind and is gated
# out-of-band (providers.EDIT_ENV), the same way unsafe permission modes are.
#
# Directories that are always skipped: they are enormous, uninteresting to edit, and
# walking them makes the tree endpoint unusable on a real project.
FS_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
                ".pytest_cache", "dist", "build", ".next", ".DS_Store", ".tox",
                ".sutra-attachments"}
FS_MAX_ENTRIES = 4000            # a tree bigger than this is truncated, and says so
FS_MAX_READ = 2 * 1024 * 1024    # refuse to open something that is not editable text


def _fs_root():
    wd = providers.load_settings().get("workdir") or ""
    if not wd or not providers.workdir_allowed(wd):
        raise HTTPException(status_code=400,
                            detail="the configured workdir is outside the allowed root; "
                                   "set it in Settings first")
    if not os.path.isdir(wd):
        raise HTTPException(status_code=404, detail="workdir %s does not exist" % wd)
    return os.path.realpath(wd)


def _fs_resolve(rel):
    """Resolve `rel` inside the workdir, or raise. realpath() FIRST, so a symlink
    pointing outside the tree is caught rather than followed."""
    root = _fs_root()
    if not rel or not isinstance(rel, str):
        raise HTTPException(status_code=400, detail="path is required")
    target = os.path.realpath(os.path.join(root, rel))
    if target != root and not target.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="path %r escapes the workdir" % rel)
    return root, target


@router.get("/fs/tree")
def api_fs_tree(md: int = 0):
    """Every editable file under the workdir, relative-path sorted.

    ``md=1`` filters to markdown DURING the walk, so the 4000-entry cap
    applies to markdown documents rather than to every file the walk meets
    first (r7: the lexical cap silently dropped whole later folders from the
    Workspace Folders lens — the founder's corpus fits untruncated once the
    filter runs pre-cap). Skip rules are identical either way, so the Editor
    screen and the folders lens disagree only by file type."""
    root = _fs_root()
    out, truncated = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in place -- os.walk only honours dirnames mutation, and descending
        # into node_modules first and filtering after is what makes this unusable.
        dirnames[:] = sorted(d for d in dirnames
                             if d not in FS_SKIP_DIRS and not d.startswith(".git"))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if md and not name.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            out.append({"path": os.path.relpath(full, root), "bytes": size})
            if len(out) >= FS_MAX_ENTRIES:
                truncated = True
                break
        if truncated:
            break
    return {"root": root, "files": out, "truncated": truncated,
            "editable": providers.editing_allowed(), "edit_env": providers.EDIT_ENV}


@router.get("/fs/read")
def api_fs_read(path: str):
    """One file's text. Binary is refused rather than mangled into replacement chars."""
    root, target = _fs_resolve(path)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="%s is not a file" % path)
    size = os.path.getsize(target)
    if size > FS_MAX_READ:
        raise HTTPException(status_code=413,
                            detail="%s is %d bytes; the editor opens files under %d"
                                   % (path, size, FS_MAX_READ))
    raw = open(target, "rb").read()
    if b"\x00" in raw:
        # Decoding this with errors="replace" would render a lossy version that,
        # if saved, would DESTROY the file. Refuse instead.
        raise HTTPException(status_code=415,
                            detail="%s looks binary; this editor only opens text" % path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415,
                            detail="%s is not valid UTF-8; this editor only opens text" % path)
    return {"path": os.path.relpath(target, root), "text": text, "bytes": size,
            "editable": providers.editing_allowed()}


class FsWriteRequest(BaseModel):
    path: str
    text: str
    # The bytes the client believed it was editing. A mismatch means the file changed
    # underneath (the AGENT very likely wrote it), and blindly saving would discard
    # that work with no warning.
    base_bytes: Optional[int] = None


@router.post("/fs/write")
def api_fs_write(req: FsWriteRequest):
    if not providers.editing_allowed():
        raise HTTPException(
            status_code=403,
            detail="editing is disabled. This endpoint writes to your files and the "
                   "panel is unauthenticated by construction, so it is gated out of "
                   "band: restart the server with %s=1 to enable it." % providers.EDIT_ENV)
    root, target = _fs_resolve(req.path)
    if os.path.isdir(target):
        raise HTTPException(status_code=400, detail="%s is a directory" % req.path)
    if os.path.exists(target) and req.base_bytes is not None:
        actual = os.path.getsize(target)
        if actual != req.base_bytes:
            raise HTTPException(
                status_code=409,
                detail="%s changed on disk since you opened it (%d bytes now, %d when "
                       "loaded). Reload before saving, or your edit would discard that "
                       "change." % (req.path, actual, req.base_bytes))
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        # tmp + replace: a crash mid-write must not leave a truncated source file.
        tmp = target + ".sutra-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(req.text)
        os.replace(tmp, target)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="could not write: %s" % exc)
    return {"path": os.path.relpath(target, root),
            "bytes": os.path.getsize(target), "saved": True}


# =========================================================== attachments =====
# A file the operator attaches has to be readable BY THE SUBPROCESS, which runs
# with cwd=<workdir>. So it is written INSIDE the workdir and referenced by a
# relative path -- no new read surface is opened, because the agent could already
# read anything under its own cwd.
#
# Transport is base64 in a JSON body rather than multipart on purpose:
# UploadFile requires `python-multipart`, and requirements.txt is deliberately
# three packages. A dependency is a permanent cost; base64 is a 33% size cost on
# a path that is already capped.

ATTACH_DIR = ".sutra-attachments"
ATTACH_MAX_BYTES = 12 * 1024 * 1024      # 12 MB decoded


class AttachRequest(BaseModel):
    name: str
    content_b64: str


@router.post("/attach")
def api_attach(req: AttachRequest):
    """Write one attachment under <workdir>/.sutra-attachments and return its
    relative path, which the composer references as @<path>."""
    wd = providers.load_settings().get("workdir") or ""
    if not wd or not providers.workdir_allowed(wd):
        raise HTTPException(status_code=400,
                            detail="the configured workdir is outside the allowed root; "
                                   "set it in Settings first")

    # basename() only -- "../../.ssh/authorized_keys" must become
    # "authorized_keys", never traverse. Then a conservative character filter:
    # the name ends up on disk and in a shell-adjacent @reference.
    safe = os.path.basename(req.name or "").strip().lstrip(".")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", safe)[:120]
    if not safe:
        raise HTTPException(status_code=400, detail="attachment needs a usable filename")

    try:
        blob = base64.b64decode(req.content_b64 or "", validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="content_b64 is not valid base64")
    if not blob:
        raise HTTPException(status_code=400, detail="attachment is empty")
    if len(blob) > ATTACH_MAX_BYTES:
        raise HTTPException(status_code=413, detail="attachment is larger than %d MB"
                            % (ATTACH_MAX_BYTES // (1024 * 1024)))

    dest_dir = os.path.join(wd, ATTACH_DIR)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        target = os.path.join(dest_dir, safe)
        # Never overwrite: two screenshots both named Screenshot.png are two
        # different files, and silently replacing the first loses the operator's data.
        stem, ext = os.path.splitext(safe)
        n = 1
        while os.path.exists(target):
            target = os.path.join(dest_dir, "%s-%d%s" % (stem, n, ext))
            n += 1
        # Belt-and-braces: the resolved path must still be inside the workdir even
        # after symlink resolution.
        if not os.path.realpath(target).startswith(os.path.realpath(wd) + os.sep):
            raise HTTPException(status_code=400, detail="attachment path escapes the workdir")
        with open(target, "wb") as fh:
            fh.write(blob)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail="could not write attachment: %s" % exc)

    rel = os.path.relpath(target, wd)
    return {"path": rel, "abs": target, "bytes": len(blob),
            "ref": "@" + rel}


# ================================================================== git =====
# READ-ONLY, and structurally so: every command below is on an allow-list of
# plumbing that cannot mutate a repository. There is no staging, commit, branch
# or push here on purpose -- those are a new class of side effect and belong
# behind their own out-of-band gate, the way UNSAFE_PERMISSION_MODES already is.
# Adding a mutating verb to GIT_CMDS is the one change that would break that.
#
# The repository is ALWAYS the settings workdir, re-validated through
# providers.workdir_allowed on every call. It is never taken from a query
# parameter: a caller-supplied path would turn this into a read oracle over the
# whole disk, which is exactly the hole the workdir picker closes.

GIT_CMDS = {
    "status": ["status", "--porcelain=v1", "--branch"],
    "log":    ["log", "-n", "40", "--pretty=format:%H%x1f%h%x1f%an%x1f%ar%x1f%s"],
    "diff":   ["diff"],
    "staged": ["diff", "--cached"],
}
GIT_MAX_BYTES = 400_000        # a diff bigger than this is truncated, and says so


def _git_repo():
    """The validated workdir, or an HTTPException. Never a client-supplied path."""
    wd = providers.load_settings().get("workdir") or ""
    if not wd or not providers.workdir_allowed(wd):
        raise HTTPException(status_code=400,
                            detail="the configured workdir is outside the allowed root; "
                                   "set it in Settings first")
    if not os.path.isdir(wd):
        raise HTTPException(status_code=404, detail="workdir %s does not exist" % wd)
    if not os.path.isdir(os.path.join(wd, ".git")):
        # A plain directory is not an error the operator caused -- say what is true.
        raise HTTPException(status_code=404,
                            detail="%s is not a git repository (no .git directory)" % wd)
    return wd


# ================================================================ usage =====
# Plan rate-limit utilization, the same data Claude Code's own /usage reports.
#
# READ-ONLY and ARGUMENT-FREE on purpose. There is nothing to parameterise: the
# windows belong to the authenticated account, not to a path or a session, so
# there is no caller-supplied input to validate and no way to point it somewhere
# it should not look.
#
# The OAuth token never crosses this boundary -- see usage.py, which builds an
# allow-list projection rather than filtering the raw payload.
@router.get("/usage")
def api_usage():
    """Rate-limit windows for this account, or an explicit unavailability.

    Never 5xx: usage.snapshot() fails open to {"available": false, "reason": ...}.
    A panel that cannot say "I don't know" would have to invent a number, and an
    invented utilization is the one thing a usage screen must never show.
    """
    import usage
    return usage.snapshot()


@router.get("/account")
def api_account():
    """The Claude account this panel runs on: who is signed in, on which plan,
    in which organisation, on what billing -- from ~/.claude.json plus the
    non-secret fields of the credential record. Local reads, no network, and a
    separate route from /usage on purpose: that payload's shape is shared with
    the PreToolUse guard and must not grow. Never 5xx: usage.account() fails
    open to {"available": false, "reason": ...}.
    """
    import usage
    return usage.account()


@router.get("/deepseek/usage")
def api_deepseek_usage():
    """DeepSeek's pay-as-you-go balance -- the equivalent fact to /usage for
    the deepseek provider, not the same fact: no five-hour/weekly window
    exists for a DeepSeek account, only a USD balance. Own route rather than a
    branch inside /usage, because the two payload shapes share no fields and a
    caller for one provider must never have to guess which keys the other left
    null. Never 5xx: deepseek_usage.snapshot() fails open to
    {"available": false, "reason": ...}.
    """
    import deepseek_usage
    return deepseek_usage.snapshot()


# ================================================================= repo =====
# The repository a SESSION is in, which is not necessarily the Settings workdir --
# see repo.py. `cwd` IS a caller-supplied path here, unlike /git/*, and is safe
# only because repo.py re-validates every one through providers.workdir_allowed
# before it reaches a subprocess. Both of these are reads.
@router.get("/repo")
def api_repo(cwd: str = ""):
    """Branch, upstream, ahead/behind, diff stat and remote for `cwd`.

    Never 5xx: repo.status() fails open to {"available": false, "reason": ...} so
    a session outside a repository, or a machine without git, renders a bar that
    says so instead of an error.
    """
    import repo
    return repo.status(cwd)


@router.get("/repo/pulls")
def api_repo_pulls(cwd: str = "", limit: int = 10):
    """Open pull requests, via the already-authenticated gh CLI."""
    import repo
    return repo.pulls(cwd, limit=max(1, min(int(limit or 10), 30)))


@router.post("/repo/pr-proposal")
def api_repo_pr_proposal(body: Dict[str, Any]):
    """PROPOSE a pull request. Creates nothing on GitHub.

    This endpoint writes an inert record and returns its id. The branch is not
    pushed and no PR exists until a human approves it at
    /api/proposals/{pid}/decide -- which is the same gate every other mutation
    goes through, and matters more here than for any of them because this is the
    first proposal kind whose effect leaves the machine.
    """
    import repo
    cwd = (body or {}).get("cwd") or ""
    st = repo.status(cwd)
    if not st.get("available"):
        raise HTTPException(status_code=400, detail=st.get("reason") or "not a repository")
    head = (body.get("head") or st.get("branch") or "").strip()
    base = (body.get("base") or "").strip()
    title = (body.get("title") or "").strip()
    if not head:
        raise HTTPException(status_code=400,
                            detail="this checkout has a detached HEAD — there is no branch to open a pull request from")
    if not base:
        raise HTTPException(status_code=400, detail="choose a base branch")
    if head == base:
        raise HTTPException(status_code=400,
                            detail="head and base are the same branch (%s)" % head)
    if not title:
        raise HTTPException(status_code=400, detail="a pull request needs a title")
    args = {"cwd": st["root"], "head": head, "base": base,
            "title": title, "body": body.get("body") or ""}
    # The summary is what the operator reads before approving, so it states the
    # PUSH as well as the PR -- the push is part of what approval authorises, and
    # a summary that mentioned only the PR would be understating the effect.
    summary = ("push %s to origin and open a pull request into %s on %s — %s"
               % (head, base, st.get("remote") or "the remote", title))
    p = proposals.create("pr.create", args, summary)
    return {"proposal": p}


@router.get("/git/{what}")
def api_git(what: str, path: Optional[str] = None):
    """status | log | diff | staged, for the configured workdir.

    `path` narrows a diff to ONE file. It is resolved against the repo and
    rejected if it escapes -- `../../etc/passwd` is a path traversal, not a
    filename, and `--` stops it being read as a flag.
    """
    if what not in GIT_CMDS:
        raise HTTPException(status_code=404, detail="unknown git view %r -- known: %s"
                            % (what, ", ".join(sorted(GIT_CMDS))))
    repo = _git_repo()
    argv = ["git", "-C", repo] + list(GIT_CMDS[what])

    if path:
        target = os.path.realpath(os.path.join(repo, path))
        if target != repo and not target.startswith(repo + os.sep):
            raise HTTPException(status_code=400,
                                detail="path %r escapes the repository" % path)
        if what in ("diff", "staged"):
            argv += ["--", os.path.relpath(target, repo)]

    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="git is not installed on this machine")
    except subprocess.SubprocessError as exc:
        raise HTTPException(status_code=500, detail="git failed: %s" % exc)

    if out.returncode != 0:
        raise HTTPException(status_code=500,
                            detail=(out.stderr or "git exited %d" % out.returncode).strip()[:600])

    text = out.stdout or ""
    truncated = len(text.encode("utf-8", "replace")) > GIT_MAX_BYTES
    if truncated:
        text = text[:GIT_MAX_BYTES]

    body = {"repo": repo, "view": what, "text": text, "truncated": truncated}
    if what == "log":
        # Parsed here rather than in the browser: the \x1f separator is a server
        # implementation detail and should not leak into the client.
        rows = []
        for line in text.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 5:
                rows.append(dict(zip(("sha", "short", "author", "when", "subject"), parts)))
        body["commits"] = rows
    if what == "status":
        files, branch = [], None
        for line in text.splitlines():
            if line.startswith("##"):
                branch = line[2:].strip()
                continue
            if len(line) > 3:
                files.append({"x": line[0], "y": line[1], "path": line[3:]})
        body["branch"] = branch
        body["files"] = files
    return body


# ============================================================= tenants ======

@router.get("/tenants")
def api_tenants():
    """ONE row: this registry. Tenancy is removed.

    This used to union every `tenant_id` observed on a domain or a placement and
    report a scope per tenant, which is what the panel's footer switcher and
    Tenants table were built on. There is one org per registry now, so there is
    exactly one row and nothing to switch between.

    The endpoint is KEPT rather than deleted because a running panel still calls
    it on boot; removing it would 404 a live client mid-session. It now reports
    the registry itself, and the counts are the registry's real counts -- not a
    per-label slice that no longer means anything.

    `tenant_id` stays in the payload as the ID STILL STAMPED ON THE ROWS, so the
    field is not a lie: it is dead data on disk, reported as such, not a
    selector. It is nothing's filter any more.
    """
    domains = E.load_domains()
    default_id = _tenant_of_record()

    # exactly one scope: the registry
    ids = [default_id]

    out = []
    for tid in ids:
        scope = domains      # tenancy removed: the whole registry is the scope
        live = E.live_refs(scope)
        roots = [(ref, d) for ref, d in scope.items() if not d.get("parent_ref")]
        roots.sort(key=lambda rd: (rd[1].get("ts_minted_ms") or 0, rd[0]))
        out.append({
            "tenant_id": tid,
            "domains": len(scope),
            "charters": len(_charter_ids_in_scope(scope, None)),
            "placements": len(E.all_placements()),
            "is_default": tid == default_id,
            # extras the landing screen would otherwise re-derive client-side
            "domains_live": len(live),
            "domains_retired": len(scope) - len(live),
            "root_ref": roots[0][0] if roots else None,
            "root_name": roots[0][1].get("name") if roots else None,
        })

    out.sort(key=lambda r: (0 if r["is_default"] else 1, r["tenant_id"]))
    return out


# =========================================================== proposals ======
# The chat agent can PROPOSE mutations (see sutra_mcp.py). Applying one is a
# separate, human act. The apply switch lives HERE rather than in proposals.py
# so that module never imports routines and cannot mutate anything by itself.

def _apply_proposal(kind, args):
    if kind == "routine.create":
        rec, launchd = routines.create(args)
        return {"routine": rec["id"], "launchd_ok": launchd.get("ok")}
    if kind == "routine.update":
        rec, launchd = routines.update(args["id"], args.get("patch") or {})
        return {"routine": rec["id"], "launchd_ok": launchd.get("ok")}
    if kind == "routine.delete":
        return routines.delete(args["id"])
    if kind == "routine.run":
        return routines.run_now(args["id"])
    if kind == "pr.create":
        import repo
        return repo.create_pull_request(args)
    raise ValueError("no way to apply %r" % kind)


@router.get("/proposals")
def api_proposals(pending_only: bool = False):
    return {"proposals": proposals.listing(include_decided=not pending_only),
            "store": str(proposals.store_dir())}


@router.post("/proposals/{pid}/decide")
def api_proposal_decide(pid: str, body: Dict[str, Any]):
    """approve=true applies it; approve=false rejects it. There is no third
    option and no automatic path -- an unapproved proposal simply expires."""
    if "approve" not in body:
        raise HTTPException(status_code=400, detail='send {"approve": true|false}')
    try:
        return proposals.decide(pid, bool(body["approve"]),
                                apply_fn=_apply_proposal)
    except KeyError:
        raise HTTPException(status_code=404, detail="no proposal %r" % pid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============================================================ routines ======
# Transport only; everything real is in routines.py, which is importable and
# testable without a server. Reads are GET, anything that touches launchd or the
# store is POST.

@router.get("/routines")
def api_routines():
    return routines.state()


@router.get("/routines/{rid}/runs")
def api_routine_runs(rid: str, limit: int = 10):
    try:
        return routines.runs(rid, limit=max(1, min(int(limit), 200)))
    except (KeyError, OSError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/routines/{rid}/output")
def api_routine_output(rid: str, name: str):
    try:
        # Parsed, not raw. `text` is still present so nothing that read this
        # endpoint before breaks, but the fields the panel actually renders --
        # the prose and the session id that makes the run resumable -- now come
        # out of the envelope here rather than being re-parsed in the browser.
        return routines.run_detail(rid, name)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such run output")
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/routines")
def api_routine_create(body: Dict[str, Any]):
    try:
        rec, launchd = routines.create(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"routine": rec, "launchd": launchd}


@router.post("/routines/reconcile")
def api_routines_reconcile(body: Optional[Dict[str, Any]] = None):
    return routines.reconcile(fix=bool((body or {}).get("fix")))


@router.post("/routines/{rid}")
def api_routine_update(rid: str, body: Dict[str, Any]):
    try:
        rec, launchd = routines.update(rid, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="no routine %r" % rid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"routine": rec, "launchd": launchd}


@router.post("/routines/{rid}/run")
def api_routine_run(rid: str, body: Optional[Dict[str, Any]] = None):
    # Confirmation is required because this spends money on the operator's plan.
    if not (body or {}).get("confirm"):
        raise HTTPException(status_code=400,
                            detail="running a routine starts a real agent turn; "
                                   "send {\"confirm\": true}")
    try:
        return routines.run_now(rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="no routine %r" % rid)
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/routines/{rid}/delete")
def api_routine_delete(rid: str, body: Optional[Dict[str, Any]] = None):
    if not (body or {}).get("confirm"):
        raise HTTPException(status_code=400, detail="send {\"confirm\": true}")
    try:
        return routines.delete(rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="no routine %r" % rid)
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============================================================= updates ======
# Transport only. Everything real lives in updates.py, which is importable and
# tested without a server. Checking is a GET because it changes nothing;
# installing is a POST because it very much does.

@router.get("/updates")
def api_updates():
    """Both components, checked live. Network calls, so this is never called on
    boot -- only when the operator asks."""
    return updates.all_state()


@router.post("/updates/plugin")
def api_updates_plugin():
    """Run the same update the daily hook runs, now."""
    try:
        return updates.install_plugin()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/updates/desktop")
def api_updates_desktop():
    """Download, VERIFY, and schedule the swap for after the app quits.

    Split deliberately: everything checkable (checksum, notarization, the
    bundle's own signature) is checked while the operator is still here to be
    told, and only then is the unattended helper armed.

    This is the MANUAL button and it stays exactly as it was -- it is the
    fallback when the automatic path has given up, and a fallback that shares
    the automatic path's failure modes is not a fallback.
    """
    # Checked BEFORE the 240MB download. A user once waited for the whole file
    # and was then told a folder was "not writable" -- the real answer, that the
    # app had never been dragged out of the installer image, was never said.
    blocked = updates.install_blocker()
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    try:
        got = updates.download_and_verify()
        sched = updates.install_desktop(got["dmg"], relaunch=True,
                                        version=got.get("version"))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sched["version"] = got.get("version")
    return sched


# ------------------------------------------------ automatic update path -----
# The three routes below can quit the app and replace the bundle on disk, so
# unlike everything else on this loopback API they are AUTHENTICATED.
#
# The rest of the API is unauthenticated because it is reachable only from
# 127.0.0.1 and does nothing a local user could not already do. These do:
# "arm" hands an unattended helper the authority to replace /Applications/
# Sutra.app, and any page in any browser on this machine can POST to localhost.
# That is a persistence primitive, not a convenience.
#
# The token is minted by the Electron shell and handed to the backend it spawns.
# Which produces exactly the right behaviour for free: when the shell ATTACHES
# to a backend it did not start (main.js does this), it has no token for that
# process, arming is refused, and automatic updating stays off for that session
# instead of quietly acting through a server whose lifetime it does not own.

DESKTOP_TOKEN = os.environ.get("SUTRA_DESKTOP_TOKEN") or None


def _desktop_control(request):
    """Authorise a desktop-control call, or refuse it with a reason."""
    if not DESKTOP_TOKEN:
        raise HTTPException(status_code=403, detail=(
            "this server was not started by the Sutra desktop app, so it "
            "cannot install or restart it"))
    sent = request.headers.get("x-sutra-desktop-token") or ""
    if not hmac.compare_digest(sent, DESKTOP_TOKEN):
        raise HTTPException(status_code=403, detail="bad desktop control token")


@router.get("/updates/staged")
def api_updates_staged():
    """Local staging state only -- no network. The panel polls this, and that
    is the ONLY reason it is allowed to: a route that reaches GitHub cannot be
    polled without turning every open panel into a crawler."""
    return updates.pending_state()


@router.post("/updates/desktop/stage")
def api_updates_stage(request: Request):
    """Download + verify into durable staging. Arms nothing."""
    _desktop_control(request)
    # Same pre-check as the manual button. Without it the AUTOMATIC path
    # re-downloads 240MB on every schedule tick on a machine that can never
    # install it, silently, forever.
    blocked = updates.install_blocker()
    if blocked:
        raise HTTPException(status_code=400, detail=blocked)
    try:
        return updates.stage_desktop()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/updates/desktop/arm")
async def api_updates_arm(request: Request):
    """Schedule the swap for after the shell exits.

    `wait_pid` is required and is the SHELL's pid, not this process's parent.
    See install_desktop() for why inferring it here is wrong.
    """
    _desktop_control(request)
    body = {}
    try:
        body = await request.json()
    except (ValueError, TypeError):
        pass
    pid = body.get("wait_pid")
    if not pid:
        raise HTTPException(status_code=400, detail="wait_pid is required")
    try:
        return updates.arm_desktop(int(pid), wait_start=body.get("wait_start"),
                                   relaunch=bool(body.get("relaunch")))
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/updates/desktop/resolve")
async def api_updates_resolve(request: Request):
    """Launch-time decision: what did the last attempt do, and what now."""
    _desktop_control(request)
    body = {}
    try:
        body = await request.json()
    except (ValueError, TypeError):
        pass
    try:
        return updates.resolve_pending(body.get("installed"))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ========================================================== automation ======
# The dispatcher and the scheduler, reported from the files they actually write.
#
# The honest shape of this, established before any of it was drawn:
#
#   DISPATCHER  real. bin/sutra-dispatch and bin/sutra-atom append JSONL ledgers
#               under <workdir>/.sutra/, and hooks/dispatch-gate.sh + atom-floor.sh
#               append verdicts under <workdir>/.enforcement/. All read-only here.
#
#   SCHEDULER   NOT real, and this endpoint says so rather than drawing an empty
#               table that implies "0 runs today". Cadence lives in the Native
#               daemon (marketplace/native, ADR-017: a daemon-side setInterval
#               tick, deliberately NOT OS cron/launchd). At v1.0 the daemon does
#               not run in this install and cadence-scheduler.ts does not even
#               evaluate `cron` -- its next-fire is +Infinity. So the only
#               truthful report is the daemon's own liveness files and the
#               trigger store, plus the reason there is nothing to show.
#
# Consistent with the no-fixture rule at the top of this file: where there is no
# data source, the answer is "there is no data source", never a plausible zero.

AUTOMATION_TAIL = 12          # recent rows returned per ledger
AUTOMATION_MAX_BYTES = 4 * 1024 * 1024   # refuse to walk a runaway ledger


def _read_jsonl_tail(path, limit=AUTOMATION_TAIL):
    """(total_rows, last `limit` parsed rows). Unparseable lines are counted but
    not returned -- a corrupt row is not a reason to report an empty ledger."""
    if not os.path.isfile(path):
        return 0, [], False
    try:
        if os.path.getsize(path) > AUTOMATION_MAX_BYTES:
            return 0, [], True
        rows, total = [], 0
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        return total, rows[-limit:], False
    except OSError:
        return 0, [], False


def _automation_root():
    """The configured workdir, unvalidated-for-git. Dispatch state is written into
    whatever project the agent runs in, so that is where it is read from."""
    wd = providers.load_settings().get("workdir") or ""
    if not wd or not providers.workdir_allowed(wd):
        raise HTTPException(status_code=400,
                            detail="the configured workdir is outside the allowed root; "
                                   "set it in Settings first")
    return wd


@router.get("/automation")
def api_automation():
    """Dispatcher activity and scheduler liveness for the configured workdir."""
    root = _automation_root()
    exists = os.path.isdir(root)

    j = lambda *p: os.path.join(root, *p)

    disp_total, disp_recent, disp_big = _read_jsonl_tail(j(".sutra", "dispatch-ledger.jsonl"))
    atom_total, atom_recent, _ = _read_jsonl_tail(j(".sutra", "atom-ledger.jsonl"))
    gate_total, gate_recent, _ = _read_jsonl_tail(j(".enforcement", "dispatch-gate.jsonl"))

    kinds, verdicts = {}, {}
    for r in disp_recent:
        k = str(r.get("kind") or "?")
        kinds[k] = kinds.get(k, 0) + 1
    for r in gate_recent:
        v = str(r.get("verdict") or "?")
        verdicts[v] = verdicts.get(v, 0) + 1

    # ---- scheduler: liveness, not activity -------------------------------
    home = _ACTIVE_HOME
    native_root = os.path.dirname(home.rstrip(os.sep)) or home
    pid_file = os.path.join(native_root, "native.pid")
    ready_file = os.path.join(native_root, "native.ready")
    triggers_dir = os.path.join(home, "triggers")
    triggers = []
    if os.path.isdir(triggers_dir):
        try:
            triggers = sorted(f for f in os.listdir(triggers_dir) if f.endswith(".json"))
        except OSError:
            triggers = []

    return {
        "root": root,
        "root_exists": exists,
        "dispatcher": {
            "ledger": {"path": ".sutra/dispatch-ledger.jsonl", "rows": disp_total,
                       "recent": disp_recent, "kinds": kinds, "too_large": disp_big},
            "atoms": {"path": ".sutra/atom-ledger.jsonl", "rows": atom_total,
                      "recent": atom_recent},
            "gate": {"path": ".enforcement/dispatch-gate.jsonl", "rows": gate_total,
                     "recent": gate_recent, "verdicts": verdicts},
        },
        "scheduler": {
            "daemon_running": os.path.isfile(pid_file),
            "pid_file": pid_file,
            "ready": os.path.isfile(ready_file),
            "triggers_dir": triggers_dir,
            "triggers_dir_exists": os.path.isdir(triggers_dir),
            "triggers": triggers,
            # Stated, not implied. See the block comment above.
            "note": "Cadence is a daemon-side tick in the Native engine (ADR-017), "
                    "not OS cron or launchd. This install has no running daemon, "
                    "and the v1.0 scheduler does not evaluate cron expressions at "
                    "all -- their next-fire time is +Infinity. Nothing is scheduled, "
                    "so nothing is reported as having run.",
        },
    }

# ------------------------------------------------------------- teamsutra ----
# The task store's transport. House rules (same as routines): reads are GET
# and unauthenticated on loopback; anything that changes state is POST, and
# every teamsutra WRITE additionally requires the desktop token — the port is
# unauthenticated, and "any local process can queue work for an unattended
# agent" is precisely the exposure the token exists to close. Creation is NOT
# exposed here at all: the chat files tasks through the MCP tool, at draft.

@router.get("/teamsutra/tasks")
def api_teamsutra_tasks():
    """The full board, oldest first, corrupt records visible as corrupt."""
    return {"tasks": teamsutra.listing()}


@router.post("/teamsutra/tasks/{tid}/queue")
def api_teamsutra_queue(tid: str, request: Request):
    """draft -> queued. The operator's click — the one transition that turns
    an inert record into claimable work."""
    _desktop_control(request)
    try:
        return teamsutra.set_status(tid, "queued")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/teamsutra/tasks/{tid}/drop")
def api_teamsutra_drop(tid: str, request: Request):
    _desktop_control(request)
    try:
        return teamsutra.drop(tid)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/teamsutra/tasks/{tid}/release")
def api_teamsutra_release(tid: str, request: Request):
    """claimed -> queued, explicitly and by a human. Crash recovery is a
    CLICK, never a timer: a stuck claim must not become a retry loop."""
    _desktop_control(request)
    try:
        return teamsutra.set_status(tid, "queued")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ------------------------------------------------- teamsutra: task.apply ----
# The one-click from a reviewed diff to a GitHub PR (APPLY-DESIGN v1.1).
# Everything below is the design's safety ledger made code: the diff is
# policed before git runs (D-A7), the target repo's origin must verify as
# sankalpasawa/sutra (D-A4), every subprocess is arg-list + no-prompt env +
# 120s timeout + bounded capture (D-A8), the per-task lock carries a 30-min
# TTL (D-A9), and success is a BRANCH PUSH + PR — main is unreachable from
# this code path and nothing merges itself.
import shutil    # noqa: E402
import tempfile  # noqa: E402

TS_APPLY_REPO_ENV = "SUTRA_UI_TEAMSUTRA_REPO"
TS_APPLY_REPO_DEFAULT = "~/Claude/asawa-holding/sutra"
TS_APPLY_GH_REPO = "sankalpasawa/sutra"
TS_APPLY_ORIGIN_RE = re.compile(
    r"^(?:git@github\.com:|https://github\.com/)sankalpasawa/sutra(?:\.git)?$")
TS_APPLY_DENY_RE = re.compile(r"^(?:\.github/|\.gitmodules$|\.githooks/|githooks/)")
TS_APPLY_MAX_LINES = 400
TS_APPLY_LOCK_TTL_S = 30 * 60
TS_APPLY_TIMEOUT_S = 120
TS_APPLY_SECRET_RE = re.compile(
    r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9-]{20,}|xox[a-z]-[A-Za-z0-9-]+)")


def _ts_apply_policy(diff):
    """Patch-policy gate (D-A7): the diff is untrusted machine output that a
    same-repo PR branch would hand to CI, so intent is policed before any git
    mechanics run. Returns a refusal string, or None when the diff is in policy."""
    if not diff or not diff.strip():
        return "task has no diff to apply"
    if "GIT binary patch" in diff or "\nBinary files " in diff:
        return "binary patch refused"
    if re.search(r"^(?:old|new) mode ", diff, re.M):
        return "file-mode change refused"
    paths = []
    for m in re.finditer(r"^diff --git a/(\S+) b/(\S+)$", diff, re.M):
        paths += [m.group(1), m.group(2)]
    # The worker's ts_extract_diff emits bare unified diffs — ---/+++ headers
    # with no `diff --git` line. Both forms are policed; neither is trusted.
    for m in re.finditer(r"^(?:---|\+\+\+) [ab]/(\S+)$", diff, re.M):
        paths.append(m.group(1))
    if not paths:
        return "diff has no recognizable file headers"
    for p in sorted(set(paths)):
        if p.startswith("/") or ".." in p.split("/"):
            return "path outside the repo tree: %s" % p
        if TS_APPLY_DENY_RE.match(p):
            return "policy-denied path (CI/hooks/submodules): %s" % p
    changed = sum(1 for ln in diff.splitlines()
                  if ln[:1] in "+-" and not ln.startswith(("+++", "---")))
    if changed > TS_APPLY_MAX_LINES:
        return "diff too large: %d changed lines (max %d)" % (changed, TS_APPLY_MAX_LINES)
    return None


def _ts_apply_sanitize(text):
    """apply_error is founder-visible and stored: strip the home prefix,
    redact token-shaped strings, then truncate (D-A8)."""
    out = (text or "").replace(os.path.expanduser("~"), "~")
    out = TS_APPLY_SECRET_RE.sub("[redacted]", out)
    return out[:500]


def _ts_run(args, cwd, timeout=TS_APPLY_TIMEOUT_S, env_extra=None):
    """One policed subprocess: arg-list exec, pinned cwd, prompt-disabled env,
    bounded capture. gh keeps HOME/PATH for its keyring config; git cannot
    prompt for credentials — a hang dies at the timeout instead."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
           "HOME": os.path.expanduser("~"),
           "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1"}
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(list(args), cwd=cwd, env=env, capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout or "")[-10000:], (p.stderr or "")[-10000:]


def _ts_apply_sweep():
    """Crash debris (D-A6/D-A9): apply worktrees and locks older than 24h are
    removed on the next apply attempt — lazily, so no startup hook is needed."""
    cutoff = time.time() - 24 * 3600
    for d in (Path(tempfile.gettempdir()), teamsutra.store_dir()):
        if not d.is_dir():
            continue
        for p in d.glob("ts-apply-*"):
            try:
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
        for p in d.glob(".apply-lock-*"):
            try:
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass


def _ts_apply(tid, run=_ts_run):
    """needs_review diff -> pushed branch -> open PR. `run` is injectable so
    the whole ladder is testable without touching git or the network."""
    rec = teamsutra.load(tid)
    if rec.get("status") != "needs_review":
        raise ValueError("apply needs a needs_review task; %s is %s"
                         % (tid, rec.get("status")))

    def fail(msg):
        m = _ts_apply_sanitize(msg)
        teamsutra.record_apply_result(tid, apply_error=m)
        raise ValueError(m)

    err = _ts_apply_policy(rec.get("diff"))
    if err:
        fail("policy: " + err)

    repo = os.path.realpath(os.path.expanduser(
        os.environ.get(TS_APPLY_REPO_ENV) or TS_APPLY_REPO_DEFAULT))
    # .git is a DIRECTORY in a plain checkout but a FILE in submodules and
    # worktrees — the default target is a submodule of asawa-holding, so an
    # isdir check here refused every real apply (caught by the live smoke).
    # Identity is enforced separately by the origin-URL preflight below.
    if not os.path.exists(os.path.join(repo, ".git")):
        fail("apply target is not a git repo: %s" % repo)

    _ts_apply_sweep()

    # Per-task lock with a TTL (D-A9): mkdir is the atomic claim, the mtime is
    # the age. A crashed apply cannot wedge the task past 30 minutes.
    lock = teamsutra.store_dir() / (".apply-lock-" + tid)
    teamsutra._mkdir_private(teamsutra.store_dir())
    if lock.is_dir():
        if time.time() - lock.stat().st_mtime > TS_APPLY_LOCK_TTL_S:
            shutil.rmtree(lock, ignore_errors=True)
        else:
            raise ValueError("apply already running for %s" % tid)
    os.mkdir(lock)

    branch = "teamsutra/" + tid
    title = "teamsutra: %s (%s)" % ((rec.get("title") or "task")[:120], tid)
    wt = None
    dfile = None
    try:
        # Preflight (D-A4/D-A10/D-A5): right origin, live auth + push perms,
        # then reconcile debris — adopt an open PR, clear a dead remote branch.
        rc, out, se = run(["git", "remote", "get-url", "origin"], cwd=repo)
        if rc or not TS_APPLY_ORIGIN_RE.match(out.strip()):
            fail("origin is not %s (got %r)" % (TS_APPLY_GH_REPO, out.strip()))
        rc, out, se = run(["gh", "auth", "status"], cwd=repo)
        if rc:
            fail("gh auth: " + (se or out))
        rc, out, se = run(["gh", "api", "repos/" + TS_APPLY_GH_REPO,
                           "--jq", ".permissions.push"], cwd=repo)
        if rc or out.strip() != "true":
            fail("no push permission on %s" % TS_APPLY_GH_REPO)
        rc, out, se = run(["gh", "pr", "list", "-R", TS_APPLY_GH_REPO,
                           "--head", branch, "--state", "open",
                           "--json", "url", "--jq", ".[0].url"], cwd=repo)
        if rc == 0 and out.strip():
            url = out.strip()
            teamsutra.set_status(tid, "done")
            teamsutra.record_apply_result(tid, pr_url=url, pr_state="open",
                                          applied_at=teamsutra.now_iso())
            return teamsutra.load(tid)
        rc, out, se = run(["git", "ls-remote", "--heads", "origin", branch], cwd=repo)
        if rc:
            fail("ls-remote: " + se)
        if out.strip():
            # Our machine-owned namespace: a remote branch with no open PR is
            # debris from a half-failure — clear it and redo clean (D-A5).
            rc, out, se = run(["git", "push", "origin", "--delete", branch], cwd=repo)
            if rc:
                fail("could not clear dead branch %s: %s" % (branch, se))

        rc, out, se = run(["git", "fetch", "origin", "main"], cwd=repo)
        if rc:
            fail("fetch: " + se)
        run(["git", "branch", "-D", branch], cwd=repo)  # stale local ref, if any
        wt = tempfile.mkdtemp(prefix="ts-apply-")
        rc, out, se = run(["git", "worktree", "add", "-b", branch, wt,
                           "origin/main"], cwd=repo)
        if rc:
            fail("worktree: " + se)
        dfile = os.path.join(tempfile.gettempdir(), "ts-apply-%s.patch" % tid)
        with open(dfile, "w") as f:
            f.write(rec["diff"])
        rc, out, se = run(["git", "apply", "--check", dfile], cwd=wt)
        if rc:
            fail("apply --check: " + se)
        rc, out, se = run(["git", "apply", dfile], cwd=wt)
        if rc:
            fail("apply: " + se)
        rc, out, se = run(["git", "add", "-A"], cwd=wt)
        if rc:
            fail("add: " + se)
        # The repo's pre-commit test gate fires inside this worktree too. For
        # a machine apply the commit is TRANSPORT of an already-human-reviewed
        # diff into a PR, where CI reruns the real suites and a human is the
        # merge. So this uses the gate's own documented override channel, with
        # the reason recorded — not a bypass, the sanctioned lane for commits
        # whose verification happens downstream (caught by live smoke; D-A11).
        rc, out, se = run(["git", "commit", "-m", title], cwd=wt,
                          env_extra={"SKIP_TESTS_ACK":
                                     "teamsutra apply %s: transport commit; "
                                     "verification is the PR's CI + human merge gate" % tid})
        if rc:
            fail("commit: " + (se or out))
        rc, out, se = run(["git", "push", "origin", branch], cwd=wt)
        if rc:
            fail("push: " + se)
        body = ("Filed from the panel as %s.\n\n%s\n\nWorker verify: %s"
                % (tid, (rec.get("body") or "")[:2000], rec.get("verify") or "n/a"))
        rc, out, se = run(["gh", "pr", "create", "-R", TS_APPLY_GH_REPO,
                           "--head", branch, "--base", "main",
                           "--title", title, "--body", body], cwd=wt)
        if rc:
            fail("pr create: " + se)
        url = (out.strip().splitlines() or [""])[-1]
        teamsutra.set_status(tid, "done")
        teamsutra.record_apply_result(tid, pr_url=url, pr_state="open",
                                      applied_at=teamsutra.now_iso())
        return teamsutra.load(tid)
    finally:
        if dfile:
            try:
                os.unlink(dfile)
            except OSError:
                pass
        if wt:
            run(["git", "worktree", "remove", "--force", wt], cwd=repo)
            shutil.rmtree(wt, ignore_errors=True)
        run(["git", "branch", "-D", branch], cwd=repo)  # remote/PR is the record
        shutil.rmtree(lock, ignore_errors=True)


@router.post("/teamsutra/tasks/{tid}/apply")
def api_teamsutra_apply(tid: str, request: Request):
    """needs_review -> open PR (APPLY-DESIGN v1.1). Desktop-token-gated like
    every teamsutra write; the electron id regex is UX, this one is the boundary."""
    _desktop_control(request)
    if not teamsutra.ID_RE.match(tid or ""):
        raise HTTPException(status_code=400, detail="bad task id")
    try:
        return _ts_apply(tid)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # timeout, OSError — record then surface
        msg = _ts_apply_sanitize(str(exc))
        try:
            teamsutra.record_apply_result(tid, apply_error=msg)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=msg)
