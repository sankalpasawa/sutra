"""workspace_api.py -- the Workspace screen's read-only backend (PLAN-100
S39-S52). Five GET endpoints under /api/workspace/*, contract of record
API-CONTRACT.md; error families ERROR-MODEL.md; projection rules MIGRATION.md.

SAFETY (same posture as org_api.py's header -- ground truth for this module):
  - ZERO write endpoints. Saving rides the existing /api/fs/write and the
    sidecar; this surface is a read-only projection (ARCH.md#components).
    The ONLY file this module ever appends to is its own local telemetry
    JSONL (counts only -- no query text, no paths, no titles; PRD.md §5).
  - Registry access is READ-ONLY through the same engine calls org_api is
    allowed: load_domains, live_refs, domain_path, charters_for,
    charter_view, all_placements, charter_body_files -- plus org_api's own
    org_search for the records lane (imported, never forked). None of the
    engine mutators are named anywhere in this file.
  - Every client-supplied path resolves through org_api._fs_resolve
    (realpath FIRST, containment against _fs_root, which gates on
    providers.workdir_allowed) before any stat. The bulk tree join uses
    _join_resolve(), the identical predicate with the root hoisted out of
    the per-placement loop -- _fs_resolve recomputes _fs_root (a settings
    read) per call, which is fine once per request and pathological once
    per placement.
  - Flag-gated PER REQUEST (FLAG.md): the router mounts unconditionally in
    app.py (integrator, S39); with flags.workspace absent/false in
    ~/.sutra-ui/settings.json every endpoint answers the typed 404 with the
    flag hint. Server-side, per request, so killing the flag needs no
    restart and no client cooperation.

Identity rule (API-CONTRACT.md#identity, S33): a document is its
workdir-relative path; a record is its registry ref. No endpoint accepts one
where the other is due; /resolve is the only translator and answers with a
typed target rather than guessing.
"""
import functools
import json
import os
import re
import time
import urllib.parse

from fastapi import APIRouter, HTTPException

import org_api      # path guards (_fs_root/_fs_resolve), org_search, FS caps
import providers    # settings file + flag read (FLAG.md: backend reads settings.json)

E = org_api.E       # placement_engine, already imported (and path-wired) by org_api

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# ------------------------------------------------------------- constants ----

WS_FLAG = "workspace"
FLAG_OFF_MESSAGE = ("workspace flag is off — set flags.workspace in "
                    "~/.sutra-ui/settings.json")

# Tree cap mirrors the Files tree's own ceiling so the two surfaces can never
# disagree about "too big" (API-CONTRACT.md#tree; org_api.py FS_MAX_ENTRIES).
# Referenced, not copied, so a future bump moves both together.
TREE_MAX_DOC_ROWS = org_api.FS_MAX_ENTRIES

# Search caps + snippet budget (API-CONTRACT.md#search).
SEARCH_DOC_CAP = 20
SEARCH_REC_CAP = 10
SNIPPET_MAX = 140

LINKED_FROM_CAP = 10   # doc endpoint; [] in v1 until a link index exists
RESOLVE_ALSO_CAP = 5   # bare-title collision losers (API-CONTRACT.md#resolve)

# Tree cache TTL backstop (ARCH.md#caching): a directory's mtime only moves on
# direct-child churn, so an in-place edit deep in the tree is invisible to the
# signature -- the TTL bounds that staleness window.
TREE_CACHE_TTL_S = 5.0

# Server-side per-request counters (PLAN-100 S52). Deliberately a SEPARATE
# file from the client's episode-level events (S71) so a request count is
# never mistaken for a user action count. Rows are {"ts", "event"} ONLY.
TELEMETRY_PATH = os.path.expanduser(
    os.environ.get("SUTRA_UI_WS_TELEMETRY", "~/.sutra-ui/workspace-telemetry.jsonl"))

# One entry per workdir root: {"sig": tuple, "ts": float, "payload": dict}.
_TREE_CACHE = {}


# ---------------------------------------------------------- typed errors ----

class _WsError(Exception):
    """Internal carrier for the one typed envelope every non-2xx response
    wears (API-CONTRACT.md#errors). Raised anywhere below an endpoint,
    rendered exactly once by the _guarded wrapper -- so no path can leak a
    bare FastAPI {"detail": ...} shape the frontend does not switch on."""

    def __init__(self, status, kind, message):
        super().__init__(message)
        self.status, self.kind, self.message = status, kind, message


def _envelope(status, kind, message):
    # JSONResponse imported lazily would hide the dependency; import once here.
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status,
                        content={"error": {"kind": kind, "message": message}})


def _flag_on():
    """flags.workspace from ~/.sutra-ui/settings.json, per request (FLAG.md).

    Read through providers._raw_settings() rather than load_settings():
    load_settings() normalises to its three contract keys and does not pass
    unknown keys like `flags` through -- and it probes provider binaries,
    which is per-request cost this boolean does not justify. _raw_settings()
    is the same file, same never-raises posture, one json read.
    """
    flags = providers._raw_settings().get("flags")
    # S92 CUTOVER (founder, 2026-08-25): absent now means ON — the Workspace
    # is the default org surface fleet-wide. An explicit false is the only
    # off-switch (FLAG.md rollback path, unchanged).
    if not isinstance(flags, dict):
        return True
    return flags.get(WS_FLAG) is not False


def _guarded(event):
    """Endpoint wrapper: flag gate first (FLAG.md: no client-only gating),
    typed-envelope rendering for _WsError, telemetry count on success only.
    functools.wraps keeps the signature visible to FastAPI's DI."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _flag_on():
                return _envelope(404, "not_found", FLAG_OFF_MESSAGE)
            try:
                out = fn(*args, **kwargs)
            except _WsError as exc:
                return _envelope(exc.status, exc.kind, exc.message)
            _telemetry(event)
            return out
        return wrapper
    return deco


def _telemetry(event):
    """Append one {"ts", "event"} row. Counts only -- no query text, no paths,
    no titles, no content (PRD.md §5). Local JSONL, never transmitted. A
    telemetry failure must never fail a read endpoint, so this swallows OS
    errors rather than surfacing them."""
    try:
        parent = os.path.dirname(TELEMETRY_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(TELEMETRY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": int(time.time()), "event": event}) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------ path guards ---

def _root():
    """The validated workdir, or engine_down. _fs_root's own refusals (workdir
    unset / outside the allowed root / missing) mean the DOCUMENT UNIVERSE is
    unavailable -- that is the F1 family (state 13), not a per-path 404."""
    try:
        return org_api._fs_root()
    except HTTPException as exc:
        raise _WsError(503, "engine_down",
                       "workdir unavailable: %s" % exc.detail)


def _resolve_doc_param(rel):
    """A client-supplied ?path= / doc link, through org_api._fs_resolve.

    Guard failures map to `not_found` (404), never a distinct 400: the four
    kinds in ERROR-MODEL.md are closed ("No other kinds exist"), and an
    escape attempt learns nothing beyond "no such document". _root() runs
    first so an engine-level failure keeps its own family."""
    root = _root()
    if not isinstance(rel, str) or not rel.strip():
        raise _WsError(404, "not_found", "path is required")
    if not rel.lower().endswith(".md"):
        raise _WsError(404, "not_found",
                       "%s is not a document (.md only)" % rel)
    try:
        root, target = org_api._fs_resolve(rel)
    except HTTPException:
        raise _WsError(404, "not_found", "no document at %s" % rel)
    return root, target


def _join_resolve(root, rel):
    """The tree join's guard: same predicate as org_api._fs_resolve (realpath
    FIRST, containment against root) with the root hoisted out of the
    per-placement loop. Returns the resolved target or None -- a registry row
    whose path fails validation contributes NO doc row (MIGRATION.md M5) but
    must never crash the projection."""
    if not rel or not isinstance(rel, str):
        return None
    target = os.path.realpath(os.path.join(root, rel))
    if target != root and not target.startswith(root + os.sep):
        return None
    return target


_DOC_SEGMENT_BAD = ("", ".", "..")


def _valid_doc_link(rel):
    """The shipped sbPageFromPath rules, re-validated server-side
    (DEEPLINKS.md §2: client validation is a courtesy, never the guard):
    string; no ':' or '\\'; no control chars; not starting '/' or '~';
    ends .md; no empty/'.'/'..' segments."""
    if not isinstance(rel, str) or not rel:
        return False
    if ":" in rel or "\\" in rel:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in rel):
        return False
    if rel.startswith("/") or rel.startswith("~"):
        return False
    if not rel.lower().endswith(".md"):
        return False
    if any(seg in _DOC_SEGMENT_BAD for seg in rel.split("/")):
        return False
    return True


# --------------------------------------------------------- registry reads ---

def _load_domains():
    """load_domains() skips unreadable ROWS itself (corrupted-registry corpus
    relies on that); what it cannot survive is an unreadable STORE -- that is
    F1, engine_down."""
    try:
        return E.load_domains()
    except Exception as exc:
        raise _WsError(503, "engine_down",
                       "registry store is unreadable: %s" % exc)


def _all_placements():
    try:
        return E.all_placements()
    except Exception as exc:
        raise _WsError(503, "engine_down",
                       "registry store is unreadable: %s" % exc)


def _charter_view(cid):
    try:
        return E.charter_view(cid)
    except Exception as exc:
        raise _WsError(503, "engine_down",
                       "registry store is unreadable: %s" % exc)


# ----------------------------------------------------------- doc plumbing ---

def _doc_title(target, rel):
    """First `# ` heading, else the filename stem -- DISPLAY ONLY, never
    identity (API-CONTRACT.md#identity). Reads at most 64KB: the H1 of any
    real document is in the first lines, and titling must stay cheap at the
    4000-row cap."""
    try:
        with open(target, "rb") as fh:
            head = fh.read(65536)
        for line in head.decode("utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip() or _stem(rel)
    except OSError:
        pass
    return _stem(rel)


def _stem(rel):
    base = rel.rsplit("/", 1)[-1]
    return base[:-3] if base.lower().endswith(".md") else base


#: mtime-keyed content cache (named follow-up, promoted 2026-08-25 when the
#: cold search measured 2.3-6s on the founder's corpus and read as "search is
#: broken"). Keyed by path -> (mtime_ns, size, text); a changed file misses on
#: either component. Bounded: an over-cap insert evicts the oldest entries —
#: this is a warm-set cache, not an archive.
_TEXT_CACHE = {}
_TEXT_CACHE_MAX = 8192


def _read_text(target):
    """Document text for search/word-count. Display-lane decode (replace),
    matching _doc_title -- the byte-exact lane stays /api/fs/read. Oversized
    or unreadable files yield ''. NUL means binary (org_api's own predicate):
    not a document body worth scanning. mtime+size-keyed cache in front."""
    try:
        st = os.stat(target)
        key = (st.st_mtime_ns, st.st_size)
        hit = _TEXT_CACHE.get(target)
        if hit and hit[0] == key:
            return hit[1]
        if st.st_size > org_api.FS_MAX_READ:
            return ""
        with open(target, "rb") as fh:
            raw = fh.read()
        if b"\x00" in raw:
            text = ""
        else:
            text = raw.decode("utf-8", errors="replace")
        if len(_TEXT_CACHE) >= _TEXT_CACHE_MAX:
            for k in list(_TEXT_CACHE)[:_TEXT_CACHE_MAX // 8]:
                del _TEXT_CACHE[k]
        _TEXT_CACHE[target] = (key, text)
        return text
    except OSError:
        return ""


# Snippets are built server-side as PLAIN TEXT plus integer ranges -- nothing
# renderable crosses the wire (ARCH.md#threats). Control chars and markdown
# markup are stripped; '<' and '>' go too, so even a client that forgot esc()
# has nothing to render. Ranges are computed AGAINST the stripped text, so
# stripping can never skew them.
_STRIP_CHARS = re.compile(r"[\x00-\x1f\x7f`*_#>|<\[\]]")


def _plain(text):
    return re.sub(r"\s+", " ", _STRIP_CHARS.sub(" ", text)).strip()


def _term_ranges(snippet, term):
    """[start, end) offsets of every case-insensitive hit of `term` in
    `snippet`, in Unicode code points -- which is exactly what Python string
    indices are, and what the client's code-point-aware <mark> wrap expects
    (API-CONTRACT.md#search)."""
    ranges, hay, needle = [], snippet.lower(), term.lower()
    start = 0
    while True:
        idx = hay.find(needle, start)
        if idx < 0:
            break
        ranges.append([idx, idx + len(needle)])
        start = idx + max(len(needle), 1)
    return ranges


def _snippet(text, term):
    """<=140 plain chars windowed around the first hit, with match ranges.
    No hit in `text` yields the head of the text with empty ranges (the
    fold-in lane, where the PATH matched rather than the content)."""
    plain = _plain(text)
    idx = plain.lower().find(term.lower())
    if idx < 0:
        return {"text": plain[:SNIPPET_MAX], "ranges": []}
    start = max(0, idx - (SNIPPET_MAX // 3))
    if start:
        # Nudge to a word boundary so the window never opens mid-word.
        sp = plain.find(" ", start)
        if 0 <= sp < idx:
            start = sp + 1
    window = plain[start:start + SNIPPET_MAX]
    return {"text": window, "ranges": _term_ranges(window, term)}


# ------------------------------------------------------------- tree build ---

def _domain_order(domains):
    """org_tree's presentation order minus the retired tenant tie-break:
    D-path, then mint time, then ref -- deterministic across reads."""
    return sorted(domains.keys(),
                  key=lambda r: (E.domain_path(r, domains) or "",
                                 domains[r].get("ts_minted_ms") or 0, r))


def _norm_rel(rel, root=None):
    """Placement work_ref.id normalised for joining: forward slashes, a
    leading "./" peeled. NOT lstrip("./") -- that strips a character SET and
    would rewrite "../escape.md" into "escape.md", laundering a traversal
    into a joinable path.

    The registry stores work ids as ABSOLUTE paths (the classifier records
    what the session touched, from wherever it ran). An absolute id inside
    root joins as its relative form; one outside root stays absolute and is
    rejected downstream by _join_resolve — outside-root work is real but not
    part of THIS workdir's document universe."""
    rel = rel.replace("\\", "/")
    if root and rel.startswith("/"):
        real_root = os.path.realpath(root)
        if rel == real_root or rel.startswith(real_root + "/"):
            rel = rel[len(real_root):].lstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _doc_placements(placements):
    """The placements that NAME documents: work_ref.id ends .md (M1 -- the
    document universe is .md files; utterance/task refs are not documents).
    Keyed lookups are lowercase (M2: case-insensitive, APFS)."""
    out = []
    for p in placements:
        wid = ((p.get("work_ref") or {}).get("id") or "")
        if isinstance(wid, str) and wid.lower().endswith(".md"):
            out.append(p)
    return out


def _tree_signature(root):
    """Registry store files + fs root dir mtimes (ARCH.md#caching). mtime_ns:
    second-granularity would make back-to-back test writes invisible."""
    parts = []
    for path in (E.DOMAINS, E.CHARTERS, E.PLACEMENTS, E.CURRENT, root):
        try:
            parts.append(os.stat(path).st_mtime_ns)
        except OSError:
            parts.append(0)
    return tuple(parts)


def _sort_docs(rows):
    """mtime desc; missing rows (mtime None) sink to the end, newest-first is
    a statement about files that exist."""
    rows.sort(key=lambda r: (r["mtime"] is None, -(r["mtime"] or 0), r["path"]))
    return rows


def _build_tree(root):
    """The projection (MIGRATION.md): registry placements joined to files on
    disk, plus Unfiled. Read-only, idempotent by construction (M6/M7)."""
    domains = _load_domains()
    placements = _doc_placements(_all_placements())

    # Placement -> disk join, deduped on (path, charter) (M10).
    by_charter = {}          # charter_id -> [doc row]
    placed_paths = set()     # lowercase rel paths named by ANY doc placement
    seen_pairs = set()
    for p in placements:
        rel = _norm_rel(p["work_ref"]["id"], root)
        cid = p.get("charter_id") or ""
        key = (rel.lower(), cid)
        if not cid or key in seen_pairs:
            continue
        seen_pairs.add(key)
        placed_paths.add(rel.lower())
        target = _join_resolve(root, rel)
        if target is None:
            continue                       # invalid path: no row (M5)
        try:
            mtime = int(os.stat(target).st_mtime) if os.path.isfile(target) else None
        except OSError:
            mtime = None
        if mtime is None:
            # F2: the doc stays LISTED with missing:true, struck-through in
            # the tree; it is excluded from counts (state 14 shows 145).
            row = {"path": rel, "title": _stem(rel), "mtime": None,
                   "missing": True}
        else:
            row = {"path": rel, "title": _doc_title(target, rel),
                   "mtime": mtime, "missing": False}
        by_charter.setdefault(cid, []).append(row)

    # Departments: all live ones (empty render collapsed counts), retired only
    # when a doc row would otherwise vanish with them (tombstoned filing must
    # stay reachable -- same reasoning as org_charters' liveness note).
    doc_rows = 0
    truncated = False
    departments = []
    for ref in _domain_order(domains):
        d = domains[ref]
        charters = []
        dept_count = 0
        seen_cids = set()
        try:
            bodies = E.charters_for(ref)
        except Exception:
            bodies = []
        for body in bodies:
            cid = body.get("id")
            if not cid or cid in seen_cids:
                continue
            seen_cids.add(cid)
            view = _charter_view(cid) or {}
            docs = _sort_docs(list(by_charter.get(cid, [])))
            dept_count += sum(1 for r in docs if not r["missing"])
            if doc_rows + len(docs) > TREE_MAX_DOC_ROWS:
                # Row cap (mirrors FS_MAX_ENTRIES): stop EMITTING doc rows,
                # keep the spine + counts so the org chart never half-renders.
                docs = docs[:max(0, TREE_MAX_DOC_ROWS - doc_rows)]
                truncated = True
            doc_rows += len(docs)
            charters.append({"id": cid,
                             "title": view.get("title") or cid,
                             "docs": docs})
        has_rows = any(c["docs"] for c in charters) or any(
            by_charter.get(c["id"]) for c in charters)
        if d.get("status", "active") != "retired" or has_rows:
            departments.append({"ref": ref, "name": d.get("name"),
                                "count": dept_count, "charters": charters})

    # Unfiled: .md under the workdir with no placement (M4; named, never
    # hidden). Same prune set as /api/fs/tree so the two walks agree about
    # what a project even contains.
    unfiled = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(dn for dn in dirnames
                             if dn not in org_api.FS_SKIP_DIRS
                             and not dn.startswith("."))
        # dot-dirs pruned wholesale: .claude, .tmp, .sutra and kin hold
        # machine state, not documents — indexing them made Unfiled noise
        # and turned a $HOME-rooted walk pathological (S90 probe finding).
        for name in sorted(filenames):
            if name.startswith(".") or not name.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel.lower() in placed_paths:
                continue
            try:
                mtime = int(os.stat(full).st_mtime)
            except OSError:
                continue
            unfiled.append({"path": rel, "title": _doc_title(full, rel),
                            "mtime": mtime})
    unfiled.sort(key=lambda r: (-r["mtime"], r["path"]))
    if doc_rows + len(unfiled) > TREE_MAX_DOC_ROWS:
        unfiled = unfiled[:max(0, TREE_MAX_DOC_ROWS - doc_rows)]
        truncated = True
    doc_rows += len(unfiled)

    return {"departments": departments, "unfiled": unfiled,
            "doc_rows": doc_rows, "truncated": truncated,
            "generated_at": int(time.time())}


def _tree(root):
    """Cache wrapper: signature match AND within TTL serves the cached
    payload; either miss rebuilds. One entry per workdir (ARCH.md#caching)."""
    sig = _tree_signature(root)
    now = time.time()
    ent = _TREE_CACHE.get(root)
    if ent and ent["sig"] == sig and (now - ent["ts"]) <= TREE_CACHE_TTL_S:
        return ent["payload"]
    payload = _build_tree(root)
    _TREE_CACHE[root] = {"sig": sig, "ts": now, "payload": payload}
    return payload


# -------------------------------------------------------------- endpoints ---

@router.get("/tree")
@_guarded("tree_served")
def ws_tree():
    """Left pane, both lenses' spine data (states 01, 05, 06). An empty
    registry is 200 with empty arrays -- fresh install is data, not an error
    (ERROR-MODEL F4)."""
    return _tree(_root())


@router.get("/search")
@_guarded("search_served")
def ws_search(q: str = ""):
    """Documents (name + content, server-built snippets) then records
    (org_search's registry scan, imported not forked). Zero hits is data
    (state 09)."""
    term = (q or "").strip()
    if not term:
        return {"query": "", "documents": [], "records": [],
                "counts": {}, "truncated": False}
    root = _root()
    tree = _tree(root)

    # Document universe with filing display strings, straight off the joined
    # tree (missing docs are skipped: nothing on disk to read or open).
    universe = []
    for dept in tree["departments"]:
        for ch in dept["charters"]:
            for row in ch["docs"]:
                if not row["missing"]:
                    universe.append((row, dept["name"], ch["title"]))
    for row in tree["unfiled"]:
        universe.append((row, None, None))

    title_hits, body_hits = [], []
    seen_paths = set()
    tl = term.lower()
    for row, dept_name, charter_title in universe:
        target = _join_resolve(root, row["path"])
        if target is None:
            continue
        title = row["title"] or ""
        text = _read_text(target)
        in_title = tl in title.lower()
        in_body = tl in _plain(text).lower()
        if not in_title and not in_body:
            continue
        snippet = _snippet(text if in_body else title, term)
        entry = {"path": row["path"], "title": title,
                 "filing": {"department": dept_name, "charter": charter_title},
                 "snippet": snippet}
        (title_hits if in_title else body_hits).append((row["mtime"] or 0, entry))
        seen_paths.add(row["path"].lower())

    # Ordering: title hit > body hit, then mtime desc (API-CONTRACT.md#search).
    title_hits.sort(key=lambda t: -t[0])
    body_hits.sort(key=lambda t: -t[0])
    documents = [e for _, e in title_hits] + [e for _, e in body_hits]

    # Records via org_search -- the SAME registry scan, reused (S44). Limit is
    # raised past the caps so placement rows survive to be folded or dropped.
    rec = org_api.org_search(q=term, limit=SEARCH_REC_CAP + SEARCH_DOC_CAP + 200)
    records = []
    for r in rec.get("results", []):
        kind = r.get("kind")
        if kind == "domain":
            records.append({"kind": "department", "ref": r.get("ref"),
                            "title": r.get("title"),
                            "matched_on": r.get("matched_on") or []})
        elif kind == "charter":
            records.append({"kind": "charter", "ref": r.get("ref"),
                            "title": r.get("title"),
                            "matched_on": r.get("matched_on") or []})
        elif kind == "placement":
            # A placement hit folds into documents[] when its work_ref.id
            # resolves to a doc on disk, and is dropped otherwise -- never a
            # third group (Identity rule).
            wid = _norm_rel(r.get("title") or "")
            if not wid.lower().endswith(".md") or wid.lower() in seen_paths:
                continue
            target = _join_resolve(root, wid)
            if target is None or not os.path.isfile(target):
                continue
            filing = _filing_names(wid)
            documents.append({
                "path": wid, "title": _doc_title(target, wid),
                "filing": filing,
                "snippet": _snippet(_read_text(target), term)})
            seen_paths.add(wid.lower())

    doc_total, rec_total = len(documents), len(records)
    return {"query": term,
            "documents": documents[:SEARCH_DOC_CAP],
            "records": records[:SEARCH_REC_CAP],
            "counts": {"documents": doc_total, "records": rec_total},
            "truncated": doc_total > SEARCH_DOC_CAP or rec_total > SEARCH_REC_CAP}


def _filing_names(rel):
    """Display strings for a doc's filing (search rows). Latest placement wins
    when several file the same path (M3 renders all in the TREE; a one-line
    crumb has room for one)."""
    p = _latest_placement_for(rel)
    if not p:
        return {"department": None, "charter": None}
    domains = _load_domains()
    d = domains.get(p.get("domain_ref")) or {}
    view = _charter_view(p.get("charter_id")) or {}
    return {"department": d.get("name"), "charter": view.get("title")}


def _latest_placement_for(rel):
    rl = rel.lower()
    best = None
    root = _root()
    for p in _doc_placements(_all_placements()):
        # root is REQUIRED here: absolute placement ids only join after
        # relativization, and the tree path (line ~408) already passes it.
        # Omitting it made the doc endpoint deny a filing the tree displayed
        # (reviewer 2026-08-25, finding 5).
        if _norm_rel(p["work_ref"]["id"], root).lower() != rl:
            continue
        if best is None or (p.get("ts_ms") or 0) > (best.get("ts_ms") or 0):
            best = p
    return best


@router.get("/charter")
@_guarded("record_opened")
def ws_charter(id: str = ""):
    """Charter page data (states 02, 04): merged charter_view + this
    charter's docs joined to disk, mtime desc."""
    domains = _load_domains()
    if not domains:
        raise _WsError(404, "registry_empty",
                       "registry loads but holds no departments")
    view = _charter_view((id or "").strip())
    if not view:
        raise _WsError(404, "not_found", "no charter %s" % (id or "?"))
    root = _root()
    dref = view.get("domain_ref")
    dept = domains.get(dref) or {}

    docs, doc_count = [], 0
    seen = set()
    for p in _doc_placements(_all_placements()):
        if p.get("charter_id") != view.get("id"):
            continue
        rel = _norm_rel(p["work_ref"]["id"])
        if rel.lower() in seen:
            continue
        seen.add(rel.lower())
        target = _join_resolve(root, rel)
        if target is None or not os.path.isfile(target):
            continue      # missing/invalid: no row here (M5) -- the TREE
            #               carries the struck-through missing marker
        doc_count += 1
        docs.append({"path": rel, "title": _doc_title(target, rel),
                     "mtime": int(os.stat(target).st_mtime)})
    docs = _sort_docs([dict(d, missing=False) for d in docs])
    for d in docs:
        d.pop("missing", None)
    docs = docs[:TREE_MAX_DOC_ROWS]     # same 4000-row discipline as the tree

    return {"charter": {"id": view.get("id"),
                        "title": view.get("title"),
                        "purpose": view.get("purpose"),
                        "status": view.get("status", "active"),
                        "address": E.domain_path(dref, domains) if dept else None,
                        "department": ({"ref": dref, "name": dept.get("name")}
                                       if dept else None)},
            "docs": docs,
            "doc_count": doc_count}


@router.get("/doc")
@_guarded("doc_opened")
def ws_doc(path: str = ""):
    """Crumb + context rail for one document (S49). NO content field -- the
    sidecar iframe renders content; this is metadata only."""
    root, target = _resolve_doc_param(path)
    if not os.path.isfile(target):
        raise _WsError(404, "not_found",
                       "This document is no longer there: %s" % path)
    rel = os.path.relpath(target, root).replace(os.sep, "/")
    st = os.stat(target)
    text = _read_text(target)

    p = _latest_placement_for(rel)
    if p:
        domains = _load_domains()
        d = domains.get(p.get("domain_ref")) or {}
        view = _charter_view(p.get("charter_id")) or {}
        filing = {"department": ({"ref": p.get("domain_ref"),
                                  "name": d.get("name")} if d else None),
                  "charter": ({"id": p.get("charter_id"),
                               "title": view.get("title")} if view else None),
                  "placement_ref": p.get("id")}
    else:
        # Unfiled: all three null -> FILING rail shows "none" (state 06).
        filing = {"department": None, "charter": None, "placement_ref": None}

    return {"path": rel,
            "title": _doc_title(target, rel),
            "filing": filing,
            "meta": {"mtime": int(st.st_mtime), "bytes": st.st_size,
                     # words = prose words: markup stripped first, so "# " and
                     # fence noise never inflate the rail's stat (state 07)
                     "words": len(_plain(text).split())},
            # v1: no link index yet -- [] is the contract's allowed answer
            # (API-CONTRACT.md#doc, Open question), capped when it lands.
            "linked_from": []}


@router.get("/resolve")
@_guarded("resolve_served")
def ws_resolve(link: str = ""):
    """The ONLY path<->ref translator (Identity rule). Accepts a
    sutra://workspace deep link or panel route, a workdir-relative doc path,
    or a bare wikilink title -- answers a typed target, never a guess."""
    raw = (link or "").strip()
    if not raw:
        raise _WsError(404, "not_found", "link is required")

    # Deep-link / route forms (DEEPLINKS.md §1, §5): decode exactly once,
    # doc > charter > dept precedence, unknown params ignored.
    for prefix in ("sutra://workspace", "workspace"):
        if raw == prefix or raw.startswith(prefix + "?") or \
                raw.startswith(prefix + "/"):
            rest = raw[len(prefix):]
            if rest.startswith("?"):
                params = urllib.parse.parse_qs(rest[1:], keep_blank_values=True)
                doc = (params.get("doc") or [None])[0]
                charter = (params.get("charter") or [None])[0]
                dept = (params.get("dept") or [None])[0]
            else:
                # sutra://workspace/<dept>/<charter>/<doc> -- deepest wins.
                segs = [urllib.parse.unquote(s)
                        for s in rest.split("/") if s]
                dept = segs[0] if len(segs) > 0 else None
                charter = segs[1] if len(segs) > 1 else None
                doc = "/".join(segs[2:]) if len(segs) > 2 else None
            if doc:
                return _resolve_doc_target(doc)
            if charter:
                return _resolve_charter_target(charter)
            if dept:
                return _resolve_dept_target(dept)
            raise _WsError(404, "not_found", "link addresses nothing")

    # Workdir-relative doc path.
    if "/" in raw or raw.lower().endswith(".md"):
        return _resolve_doc_target(raw)

    # Bare registry refs.
    domains = _load_domains()
    if raw in domains:
        return {"target": {"type": "department", "ref": raw}}
    if re.fullmatch(r"C-[0-9a-fA-F]+", raw):
        return _resolve_charter_target(raw)

    # Bare wikilink title over the doc universe: most-recent mtime wins,
    # the rest come back as `also`, cap 5 (API-CONTRACT.md#resolve Decision).
    root = _root()
    tree = _tree(root)
    hits = []
    tl = raw.lower()
    for dept in tree["departments"]:
        for ch in dept["charters"]:
            for row in ch["docs"]:
                if not row["missing"] and (row["title"] or "").lower() == tl:
                    hits.append(row)
    for row in tree["unfiled"]:
        if (row["title"] or "").lower() == tl:
            hits.append(row)
    # One doc can be filed under several charters (M3): one path, one target.
    uniq, seen = [], set()
    for row in sorted(hits, key=lambda r: -(r["mtime"] or 0)):
        if row["path"].lower() not in seen:
            seen.add(row["path"].lower())
            uniq.append(row)
    if not uniq:
        if not domains:
            # An empty registry cannot answer ref-shaped links, and with no
            # docs matching either, emptiness IS the cause -- name it (F4).
            raise _WsError(404, "registry_empty",
                           "registry loads but holds no departments")
        raise _WsError(404, "not_found", "nothing named %r" % raw)
    out = {"target": {"type": "doc", "path": uniq[0]["path"]}}
    if len(uniq) > 1:
        out["also"] = [{"type": "doc", "path": r["path"]}
                       for r in uniq[1:1 + RESOLVE_ALSO_CAP]]
    return out


def _resolve_doc_target(rel):
    rel = rel.strip()
    if not _valid_doc_link(rel):
        raise _WsError(404, "not_found", "invalid document link")
    root = _root()
    target = _join_resolve(root, rel)
    if target is None:
        raise _WsError(404, "not_found", "no document at %s" % rel)
    if os.path.isfile(target):
        canon = os.path.relpath(target, root).replace(os.sep, "/")
        return {"target": {"type": "doc", "path": canon}}
    # Disk lacks it. If the REGISTRY knows the path, disk and registry
    # disagree -- that is F3's family on the resolve surface: 409 mismatch.
    if _latest_placement_for(rel):
        raise _WsError(409, "mismatch",
                       "the registry files %s but it is not on disk" % rel)
    raise _WsError(404, "not_found", "no document at %s" % rel)


def _resolve_charter_target(cid):
    cid = cid.strip()
    if not re.fullmatch(r"C-[0-9a-fA-F]+", cid):
        raise _WsError(404, "not_found", "invalid charter id")
    domains = _load_domains()
    if not domains:
        raise _WsError(404, "registry_empty",
                       "registry loads but holds no departments")
    if not _charter_view(cid):
        raise _WsError(404, "not_found", "no charter %s" % cid)
    return {"target": {"type": "charter", "ref": cid}}


def _resolve_dept_target(ref):
    ref = ref.strip()
    domains = _load_domains()
    if not domains:
        raise _WsError(404, "registry_empty",
                       "registry loads but holds no departments")
    if ref not in domains:
        raise _WsError(404, "not_found", "no department %s" % ref)
    return {"target": {"type": "department", "ref": ref}}
