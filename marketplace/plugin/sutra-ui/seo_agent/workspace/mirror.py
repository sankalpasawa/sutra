"""mirror.py — landing an arriving change in the LOCAL knowledge base.

Sutra reads the local knowledge base and nothing else (WORKSPACE-PLAN.md section 6). So a change
that came down the `changes` log has done nothing at all until it is written into the same file
Sutra was already reading it from. That is this module, and it is the only thing in the workspace
package that touches the knowledge base.

THE ONE RULE HERE: NOTHING WRITES A KNOWLEDGE FILE BY HAND FROM THIS FILE.

Every one of these files already has a module that owns its format, and several of those formats
are load-bearing in ways that are not obvious from looking at the file:

    ideas          assets/_common.save_ideas    the sheet's row schema, ticks and all
    prompts        prompts/store.save/reset     under the DATA dir, never the bundle, and the
                                                {{TOKEN}} check that stops a holed prompt shipping
    cta_links      brand/cta.parse + .render    the `<!--mine-->` mark, and two downstream regexes
    competitors    store.save_knowledge         {"competitors": [...]}, the shape suggest_topics reads
    company        store.save_knowledge         brand/company.json, merged not replaced
    library        store.library_finish/_delete the row id is never re-minted
    pages          store.save_knowledge         site_index.json AND content-database.jsonl together

A second writer that reinvents one of those formats is how the file quietly ends up in two shapes
and a builder three steps later reads nothing. So each handler below reads through the owning
module, edits rows, and writes back through the owning module.

LAST-WRITE-WINS (section 8, the owner's ruling). An arriving row REPLACES the local one whole. No
merge, no three-way, no field-level cleverness. Two people editing one prompt: last save wins.

DELETIONS ARE ORDINARY ROWS. The log carries an `op` column (insert | update | delete), so "40
pages are gone" is 40 perfectly normal log rows and needs no special path. See `is_gone`, which
also carries the one exception the pages delta forces on us.

EVERY APPLIED CHANGE IS RECORDED with its `actor`, to workspace/applied.jsonl, so the UI can say
"Ravi, 21:40" without asking Supabase anything.

Reads:  the `changes` rows sync hands it.
Writes: the knowledge base, through the owning helpers; workspace/applied.jsonl;
        workspace/refused.jsonl.
"""
import json
import os

from .. import store


# ---- the kind vocabulary, and the shape a row has ON THE WIRE --------------------------------------
#
# `kind` in the log is the TABLE NAME (the trigger writes tg_table_name), so the two are the same
# word. This is the ONE place the mapping lives: sync builds its pushes from it and outbox is handed
# the table name rather than working it out again.
#
# `changes` is deliberately absent. A client never writes the log — the trigger does, and that is
# the point of the trigger (WORKSPACE-PLAN section 3). `outbox.enqueue` and `outbox._send` both
# refuse it.

TABLES = {
    "ideas":       ("ideas", "idea_id"),
    "prompts":     ("prompts", "name"),
    "competitors": ("competitors", "domain"),
    "cta_links":   ("cta_links", "url"),
    "company":     ("company", "workspace_id"),
    "library":     ("library", "item_id"),
    "pages":       ("pages", "url"),
}

KINDS = tuple(TABLES)

# Kinds whose primary key the DATABASE fills in. `company.workspace_id` defaults to
# current_workspace_id(), so a push must not put a made-up key in it: there is one company row, and
# that default is what makes a second one impossible rather than merely discouraged.
PK_DEFAULTED = ("company",)

# Tables that log changes but have nothing to land in the local knowledge base. Applied as no-ops
# rather than refused, or every teammate's `last_seen_at` heartbeat would fill refused.jsonl with
# rows that are not faults.
IGNORED_KINDS = ("workspace", "members")

APPLIED_LOG = "applied.jsonl"       # what landed, with its actor, for the UI's activity line
REFUSED_LOG = "refused.jsonl"       # what could never land, and why. Loud, never silent.


class MirrorRefused(Exception):
    """This row can never apply, however many times it is retried.

    A prompt that fails its own token check, a kind this build has never heard of, a row with no
    key. The cursor ADVANCES past a refusal, because retrying for ever would wedge every later
    change behind it — but the row is written to refused.jsonl first, so it is visible rather than
    lost. Anything else that escapes a handler is treated as transient (a full disk, a file being
    replaced under us) and blocks the drain so the next poll retries it.
    """


# ---- where this module's own files live ---------------------------------------------------------

def dir_():
    """<data>/workspace/ — the sync bookkeeping, beside knowledge/ and library/."""
    return os.path.join(store.data_dir(), "workspace")


def _log(name, row):
    store.append_jsonl(os.path.join(dir_(), name), row)


def recent(limit=50, name=APPLIED_LOG):
    """The last few applied changes, newest first, for the activity line.

    Each row carries `actor` and `at`, which is the whole reason the log is written: the UI must be
    able to say "Ravi, 21:40" without a round trip to Supabase.
    """
    rows = store.read_jsonl(os.path.join(dir_(), name))
    return list(reversed(rows[-int(limit or 50):]))


# ---- the delete convention -------------------------------------------------------------------------

def is_gone(row):
    """Is this log row telling us the thing is gone? Takes the LOG ROW, not the payload.

    The trigger writes `op` (insert | update | delete) as a column of `changes` and puts
    `to_jsonb(old)` in the payload of a delete, so the payload of a deletion is a full, ordinary
    row and reading the payload alone cannot tell a delete from an update. `op` is the answer.

    THE ONE EXCEPTION, AND IT IS NOT A DETAIL. `pages` is a DELTA, not the site: it carries only
    what changed since the pack was built and is TRIMMED when the pack is rebuilt (section 3). That
    trim is a DELETE of rows from `pages`, and the trigger logs it exactly like any other delete. If
    this treated it as "the page is gone", every rebuild of the pack would delete real pages out of
    every teammate's catalogue. So for `pages` and only `pages`, the page is gone when the row says
    so itself — `op = 'gone'`, the column the pages table carries for exactly this — and a log row
    with op='delete' on `pages` is the delta being tidied and means nothing to us.
    """
    op = str(row.get("op") or "").lower()
    payload = row.get("payload")
    if row.get("kind") == "pages":
        return isinstance(payload, dict) and str(payload.get("op") or "").lower() == "gone"
    if op == "delete":
        return True
    # Belt and braces for a payload that spells it out anyway (a hand-written migration, a row
    # typed into the Supabase Table Editor). Costs nothing; catches the case where op is missing.
    if payload is None:
        return True
    if isinstance(payload, dict) and (payload.get("_deleted") or payload.get("deleted")):
        return True
    return False


def _trimmed(row):
    """A `pages` delete: the delta being tidied after a pack rebuild, not a page going away."""
    return row.get("kind") == "pages" and str(row.get("op") or "").lower() == "delete"


def _key(row):
    k = row.get("key")
    if k is None or str(k).strip() == "":
        raise MirrorRefused("a %s change with no key" % (row.get("kind") or "?"))
    return str(k)


# ---- the wire shape <-> the local shape ---------------------------------------------------------------
#
# The tables were designed so a person can open Supabase's own Table Editor and read their own rows
# (section 3). That is why `ideas` has readable `title`/`kind`/`ticked` columns BESIDE the `data`
# blob that actually carries the sheet row, and `library` has `title`/`status` beside `meta`.
#
# `data` and `meta` are the authority; the flat columns are for reading. Nothing below ever takes
# one value off both, which is what stops the two copies drifting into disagreement.

def from_wire(kind, key, payload):
    """One database row as the local knowledge base wants it."""
    p = payload if isinstance(payload, dict) else {}
    if kind == "ideas":
        row = dict(p.get("data") or {})
        if not row:                                  # a row typed straight into the Table Editor
            row = {"title": p.get("title") or "", "format": p.get("kind") or "",
                   "status": "done" if p.get("ticked") else "open"}
        row["id"] = key
        return row
    if kind == "prompts":
        return p.get("body") if p.get("body") is not None else (p.get("text") or "")
    if kind == "competitors":
        return {"domain": key.strip().lower(), "why": p.get("why") or "",
                "added_by": p.get("added_by") or "", "last_used": None}
    if kind == "cta_links":
        return {"url": key, "note": p.get("why") or "", "title": p.get("label") or "", "mine": True}
    if kind == "company":
        # The column names are the database's; the file's names are the file's, and several other
        # modules read them (tools/_shared.company). Translated here, once.
        out = {}
        for wire, local in (("brand", "brand"), ("domain", "domain"),
                            ("one_liner", "brand_oneliner"), ("niche", "niche_definition")):
            if p.get(wire) is not None:
                out[local] = p[wire]
        return out
    if kind == "library":
        meta = dict(p.get("meta") or {})
        meta["title"] = p.get("title") or meta.get("title") or "Untitled"
        meta["status"] = p.get("status") or meta.get("status") or "ready"
        meta["draft"] = p.get("body_md") if p.get("body_md") is not None else meta.get("draft")
        return meta
    if kind == "pages":
        page = {"url": key, "title": p.get("title") or "", "description": p.get("description") or "",
                "type": p.get("type") or "", "word_count": int(p.get("word_count") or 0)}
        return page, (p.get("body") or "")
    raise MirrorRefused("no wire shape for kind %r" % kind)


def to_wire(kind, key, local, actor="", gone=False):
    """A local change as the database wants it. The other half of `from_wire`, in the same file so
    the two cannot drift apart."""
    local = local or {}
    if kind == "ideas":
        return {"idea_id": key, "title": local.get("title") or "", "kind": local.get("format") or "",
                "ticked": local.get("status") == "done", "data": local, "actor": actor}
    if kind == "prompts":
        body = local if isinstance(local, str) else (local.get("text") or local.get("body") or "")
        return {"name": key, "body": body, "actor": actor}
    if kind == "competitors":
        return {"domain": key.strip().lower(), "why": local.get("why") or "",
                "added_by": local.get("added_by") or actor}
    if kind == "cta_links":
        return {"url": key, "label": local.get("title") or "", "why": local.get("note") or "",
                "added_by": local.get("added_by") or actor}
    if kind == "company":
        # No workspace_id: the column defaults to current_workspace_id() and that default is what
        # guarantees there is exactly one company row.
        return {"brand": local.get("brand") or "", "domain": local.get("domain") or "",
                "one_liner": local.get("brand_oneliner") or "",
                "niche": local.get("niche_definition") or "", "actor": actor}
    if kind == "library":
        meta = {k: v for k, v in local.items()
                if k not in ("title", "status", "draft", "draft_md", "url", "id",
                             "milestones", "research", "blueprint")}
        return {"item_id": key, "title": local.get("title") or "",
                "status": local.get("status") or "ready", "url": local.get("url") or "",
                "body_md": local.get("draft") or local.get("draft_md") or "",
                "meta": meta, "actor": actor}
    if kind == "pages":
        # A page going away is an UPDATE to op='gone', never a delete: deleting the row would be
        # indistinguishable from the pack rebuild trimming the delta. See `is_gone`.
        return {"url": key, "op": "gone" if gone else "changed",
                "title": local.get("title") or "", "description": local.get("description") or "",
                "type": local.get("type") or "", "word_count": int(local.get("word_count") or 0),
                "body": local.get("body") or local.get("text") or "", "actor": actor}
    raise ValueError("no wire shape for kind %r" % kind)


# ---- ideas -> the asset sheet ------------------------------------------------------------------------

def _ideas(rows):
    """knowledge/assets/ideas.json, through assets/_common.

    Imported here rather than at module top: assets/_common pulls in llm and tools/_shared, and a
    poll thread that starts before the engine is needed should not drag the whole engine in with it.
    The same reason applies to every lazy import below.
    """
    from ..assets import _common as acm
    sheet = acm.ideas()
    by_id = {str(r.get("id")): i for i, r in enumerate(sheet) if r.get("id")}
    out = []
    for row in rows:
        key = _key(row)
        if is_gone(row):
            i = by_id.pop(key, None)
            if i is not None:
                sheet[i] = None
            out.append("removed")
            continue
        # Whole-row replace: last write wins, and a tick (`status`/`built`) is just another field
        # of the row, so it travels with it and needs no path of its own.
        idea = from_wire("ideas", key, row.get("payload"))
        i = by_id.get(key)
        if i is None:
            by_id[key] = len(sheet)
            sheet.append(idea)
        else:
            sheet[i] = idea
        out.append("applied")
    acm.save_ideas([r for r in sheet if r is not None])
    return out


# ---- prompts -> the override dir ----------------------------------------------------------------------

def _prompts(rows):
    """The owner's copy of a prompt, through prompts/store.

    prompts/store owns two things this must not reimplement: WHERE an edited prompt lives (under
    the data dir, never the app bundle, or the next DMG throws it away), and the {{TOKEN}} check
    that refuses a prompt with a hole in it. A save that fails the check is REFUSED rather than
    retried — a teammate on a newer build may have saved a prompt whose tokens this build does not
    have, and retrying that for ever would wedge the log.
    """
    from ..prompts import store as pstore
    out = []
    for row in rows:
        name = _key(row)
        if not pstore.known(name):
            raise MirrorRefused("prompt %r is not one this build can change" % name)
        if is_gone(row):
            pstore.reset(name)          # deleting his copy IS the reset; there is nothing else to undo
            out.append("removed")
            continue
        text = from_wire("prompts", name, row.get("payload"))
        try:
            pstore.save(name, text if isinstance(text, str) else "")
        except pstore.PromptError as e:
            raise MirrorRefused("prompt %r: %s" % (name, e))
        out.append("applied")
    return out


# ---- competitors -> knowledge/competitors.json -----------------------------------------------------------

def _competitors(rows):
    """{"competitors": [{domain, why, ...}]} — the shape suggest_topics and onboard both read.

    Read tolerantly (older saves are a bare list, or plain strings), write the one canonical shape.
    """
    raw = store.knowledge("competitors.json") or []
    if isinstance(raw, dict):
        raw = raw.get("competitors") or []
    kept = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            kept.append({"domain": item.strip(), "why": "", "last_used": None})
        elif isinstance(item, dict) and item.get("domain"):
            kept.append(dict(item))
    by_dom = {str(r["domain"]).strip().lower(): i for i, r in enumerate(kept)}
    out = []
    for row in rows:
        dom = _key(row).strip().lower()
        if is_gone(row):
            i = by_dom.pop(dom, None)
            if i is not None:
                kept[i] = None
            out.append("removed")
            continue
        rec = from_wire("competitors", dom, row.get("payload"))
        i = by_dom.get(dom)
        if i is None:
            by_dom[dom] = len(kept)
            kept.append(rec)
        else:
            kept[i] = rec
        out.append("applied")
    store.save_knowledge("competitors.json", {"competitors": [r for r in kept if r is not None]})
    return out


# ---- cta_links -> knowledge/brand/cta-pages.md -----------------------------------------------------------

def _cta(rows):
    """The call-to-action list, through brand/cta's own parser and writer.

    NOT through `cta.save()`, deliberately: that is the person's whole-list write and it marks every
    row it is handed as `mine`, which would flip the generated rows to person-authored the first
    time a synced link landed. `parse` -> edit -> `render` is the same module and the same format,
    and it keeps each row's existing `mine` mark. A row that arrives over the wire is `mine` because
    somebody typed it on the other Mac.
    """
    from ..brand import cta
    from ..brand import _common as bcm
    from ..tools import _shared as sh
    parsed, dropped = cta.parse(bcm.read(cta.OUTPUT))
    by_url = {cta._norm(r["url"]): i for i, r in enumerate(parsed)}
    out = []
    for row in rows:
        url = _key(row)
        n = cta._norm(url)
        if is_gone(row):
            i = by_url.pop(n, None)
            if i is not None:
                parsed[i] = None
            out.append("removed")
            continue
        wire = from_wire("cta_links", url, row.get("payload"))
        prev = parsed[by_url[n]] if n in by_url else {}
        # The catalogue facts under a row (its kind, its traffic, the three product facts) are what
        # the writer reads when it picks a close. They are per-install, never sent, and must survive
        # a synced edit of the note above them.
        rec = {"url": url, "note": wire["note"] or prev.get("note", ""),
               "title": wire["title"] or prev.get("title", ""), "mine": True,
               "kind": prev.get("kind", ""), "traffic": prev.get("traffic", 0),
               "features": prev.get("features") or []}
        if n in by_url:
            parsed[by_url[n]] = rec
        else:
            by_url[n] = len(parsed)
            parsed.append(rec)
        out.append("applied")
    cta.render(sh.company().get("brand") or "", [r for r in parsed if r is not None], dropped)
    return out


# ---- company -> knowledge/brand/company.json ---------------------------------------------------------

def _company(rows):
    """One row, merged field by field into the record.

    The same read/mutate/save every other writer of this file does (index_site, brand_voice).
    MERGED rather than replaced because the record carries fields nobody syncs — `wordpress_url` is
    per-install, and so is `location_name` — and a whole-row replace would blank them on every
    teammate every time somebody corrected the one-liner.
    """
    rec = store.knowledge("brand/company.json") or {}
    out = []
    for row in rows:
        if is_gone(row):
            out.append("removed")       # there is one company; deleting it is not a thing to honour
            continue
        rec.update(from_wire("company", _key(row) if row.get("key") else "", row.get("payload")))
        out.append("applied")
    store.save_knowledge("brand/company.json", rec)
    return out


# ---- library -> the Library --------------------------------------------------------------------------

def _library(rows):
    """A teammate's finished article goes straight into the shared Library (section 8).

    Through `store.library_finish`, which owns the row id rule: the id a row is born with is the id
    it keeps. `library_finish` also copies a run's artifacts in beside the article — on a teammate's
    Mac that run folder does not exist, so the copy loop finds nothing and skips, which is correct:
    `milestones()` then reports [] ("we cannot know") rather than five falses ("it never got that
    far"), and a colleague's finished article does not read as a broken one.
    """
    out = []
    for row in rows:
        item_id = _key(row)
        if is_gone(row):
            store.library_delete(item_id)
            out.append("removed")
            continue
        meta = from_wire("library", item_id, row.get("payload"))
        title = meta.pop("title", "") or "Untitled"
        # A payload with no body must not blank an article that is already here. The log carries
        # meta-only updates (a status change), and those are the common case after the first send.
        draft = meta.pop("draft", None)
        if draft is None:
            draft = (store.library_get(item_id) or {}).get("draft") or ""
        store.library_finish(item_id, title, draft, meta)
        out.append("applied")
    return out


# ---- pages -> the catalogue and content-database.jsonl -------------------------------------------------

def _content_db():
    """{url: row} out of knowledge/content-database.jsonl, in file order."""
    out = {}
    for line in (store.knowledge("content-database.jsonl") or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("url"):
            out[str(d["url"]).rstrip("/")] = d
    return out


def _pages(rows):
    """site_index.json AND content-database.jsonl, together, the way refresh_site writes them.

    Both files or neither. refresh_site keeps the light catalogue rows in site_index.json and the
    page BODIES in content-database.jsonl, and a page that exists in one but not the other is a
    page some builder will read as empty. A page marked `gone` is REMOVED from both — that is
    section 8's ruling that a refresh dropping 40 pages drops them for everyone.

    A log row that is the pages DELTA being trimmed after a pack rebuild is skipped entirely (see
    `is_gone`): it says nothing about whether the page still exists.

    Written once for the whole batch, not once per row: sync hands this a contiguous run of page
    changes precisely so a 40-page delete rewrites a large file once rather than forty times.
    """
    idx = store.knowledge("site_index.json") or {}
    if not isinstance(idx, dict):
        idx = {"pages": idx if isinstance(idx, list) else []}
    pages = idx.get("pages") or []
    by_url = {str(p.get("url") or "").rstrip("/"): i for i, p in enumerate(pages) if p.get("url")}
    bodies = _content_db()
    out, touched = [], False
    for row in rows:
        url = _key(row)
        n = url.rstrip("/")
        if _trimmed(row):
            out.append("ignored")           # the delta being tidied, not a page going away
            continue
        touched = True
        if is_gone(row):
            i = by_url.pop(n, None)
            if i is not None:
                pages[i] = None
            bodies.pop(n, None)
            out.append("removed")
            continue
        page, body = from_wire("pages", url, row.get("payload"))
        i = by_url.get(n)
        if i is None:
            by_url[n] = len(pages)
            pages.append(page)
        else:
            pages[i] = page
        if body:
            bodies[n] = {"url": url, "type": page.get("type", ""),
                         "title": page.get("title", ""), "body": body}
        out.append("applied")
    if touched:
        pages = [p for p in pages if p is not None]
        idx["pages"] = pages
        idx["page_count"] = len(pages)
        idx["last_refreshed_at"] = store.now()
        store.save_knowledge("site_index.json", idx)
        store.save_knowledge("content-database.jsonl",
                             "".join(json.dumps(v, ensure_ascii=False) + "\n"
                                     for v in bodies.values()))
    return out


def _ignore(rows):
    """`workspace` and `members`: logged, but there is nothing local to write."""
    return ["ignored"] * len(rows)


HANDLERS = {"ideas": _ideas, "prompts": _prompts, "competitors": _competitors,
            "cta_links": _cta, "company": _company, "library": _library, "pages": _pages}
for _k in IGNORED_KINDS:
    HANDLERS[_k] = _ignore


# ---- the door ---------------------------------------------------------------------------------------

def apply_batch(rows):
    """Apply a contiguous run of log rows OF ONE KIND, and return one result dict per row.

    Batched on purpose. The cursor advances per batch, and a batch is one file write, so a refresh
    that dropped 40 pages rewrites content-database.jsonl once instead of forty times. Crash safety
    is unchanged: a crash part-way through leaves the cursor before the whole batch, so the batch
    replays. Every handler here is idempotent by construction — an upsert by key, or a delete of a
    key that may already be gone — so a replay converges on the same state rather than doubling
    anything.

    Raises MirrorRefused when the batch can never apply. Anything else that escapes is transient
    and sync will retry it.
    """
    rows = list(rows or [])
    if not rows:
        return []
    kinds = {r.get("kind") for r in rows}
    if len(kinds) != 1:
        raise ValueError("apply_batch takes one kind at a time, got %s" % sorted(kinds))
    kind = rows[0].get("kind")
    fn = HANDLERS.get(kind)
    if fn is None:
        # A kind this build has never heard of is a NEWER Sutra's table, and that is exactly what
        # workspace.schema_version exists for. Blocking on it would freeze every later change
        # behind it for ever, so it is refused loudly and the cursor moves on.
        raise MirrorRefused("no handler for kind %r (this build knows: %s)"
                            % (kind, ", ".join(KINDS)))
    actions = fn(rows)
    out = []
    for row, action in zip(rows, actions):
        rec = {"at": store.now(), "id": row.get("id"), "kind": kind, "key": row.get("key"),
               "actor": row.get("actor") or "", "op": row.get("op") or "", "action": action}
        if action != "ignored":
            _log(APPLIED_LOG, rec)
        out.append(rec)
    return out


def apply(row):
    """One log row. The batch of one."""
    return apply_batch([row])[0]


def refuse(row, why):
    """Record a row that can never apply, so it is visible rather than lost."""
    rec = {"at": store.now(), "id": row.get("id"), "kind": row.get("kind"), "key": row.get("key"),
           "actor": row.get("actor") or "", "action": "refused", "why": str(why)[:400]}
    _log(REFUSED_LOG, rec)
    return rec
