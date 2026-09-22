"""library_tabs.py — the five read-only Library tabs, assembled once, deterministically.

Reads: the run's own artifact files (research.json, work-shape.json, work-allocate.json,
       work-headings.json, blueprint.json, write-report.json, source-check.json, plus whether
       dossier.md / voices-from-the-field.md / source-check.md exist), through
       store.load_artifact -- an internal read of the run's own folder, not the public
       containment-gated artifact route, so none of these need to join
       store.EXTRA_ARTIFACT_FILES to be read here.
Writes: nothing. Every tab is assembled fresh, on every call, from what the run already saved.

NO AI CALL ANYWHERE IN THIS FILE, and nothing here is invented: a field that is not on disk is
left out or shown empty, never guessed. Same run, same screen, every time.

Each tab function takes the meta dict store.library_get() already produced (so the milestone
strip is read once) and returns None when that tab's own gate is not met, so the screen can grey
it out. `all_tabs` assembles the four that are server-side (Draft is the existing draft field on
/library/{id}, read-only, and needs nothing extra).

SINCE 2026-09-21 THE ASSEMBLED TABS ARE ALSO KEPT, and that is the one thing in this file that
writes. The owner: "all of that, that particular file stays locally only. I don't want that. Just
these things should be available for everybody in the workspace." Assembling is still the fresh
path and still wins whenever the run folder is there; `save` writes the same assembled dict into
the row's own tabs.json while the run still exists, and `served` falls back to it once the run is
gone -- on the author's Mac after the chat is deleted, and on every teammate's Mac, where the run
never existed at all. Nothing new is invented on that path: what is served from tabs.json is
byte-for-byte what this file assembled on the Mac that ran the article.
"""
import json

from . import store


def _run_artifact(meta, name):
    chat_id, run_id = meta.get("chat_id"), meta.get("run_id")
    if not chat_id or not run_id:
        return None
    return store.load_artifact(chat_id, run_id, name)


def _milestone_done(meta, key):
    strip = meta.get("milestones")
    if strip is None:
        strip = store.milestones(meta.get("chat_id"), meta.get("run_id"))
    return any(m["key"] == key and m["exists"] for m in strip)


def _has_doc(meta, fname):
    return bool(_run_artifact(meta, fname))


# ---- tab 1: Search picture ----------------------------------------------------------------------
# Greyed out until "picture" (search-picture.md) exists: the write phase's gather step is what
# cleans the question lists and cross-references them, even though the rows below are read
# straight off research.json, which usually exists earlier. Devansh's rule, not a technical limit.

def _kw_row(k):
    if not isinstance(k, dict) or not k.get("keyword"):
        return None
    return {"keyword": k["keyword"], "volume": k.get("volume"), "kd": k.get("kd")}


def search_picture(meta):
    if not _milestone_done(meta, "picture"):
        return None
    rs = _run_artifact(meta, "research.json") or {}
    kw = rs.get("keywords") or {}
    serp = rs.get("serp") or {}
    winners = rs.get("winners") or {}
    band = (rs.get("build_spec") or {}).get("word_band") or {}
    avg = None
    if band.get("min") and band.get("max"):
        avg = (int(band["min"]) + int(band["max"])) // 2
    who_ranks = [{"rank": r.get("rank"), "title": (r.get("title") or r.get("url") or ""),
                  "url": r.get("url") or "", "domain": r.get("domain") or ""}
                 for r in (serp.get("who_ranks") or []) if isinstance(r, dict) and r.get("url")]
    ai = serp.get("ai_overview") or {}
    return {
        "primary": _kw_row(kw.get("primary")),
        "variations": [row for row in (_kw_row(v) for v in (kw.get("variations") or [])) if row],
        "secondary": [row for row in (_kw_row(v) for v in (kw.get("secondary") or [])) if row],
        "in_body": [t for t in (kw.get("in_body") or []) if isinstance(t, str) and t.strip()],
        "avg_words": avg, "band": {"min": band.get("min"), "max": band.get("max")} if avg else None,
        "who_ranks": who_ranks,
        "ai_overview": (ai.get("text") or "").strip() or None,
        "paa": [q for q in (serp.get("paa_on") or []) if isinstance(q, str) and q.strip()],
        "common": [h for h in (winners.get("common_h2s") or []) if isinstance(h, str) and h.strip()],
        "gaps": [g for g in (winners.get("gaps_to_own") or []) if isinstance(g, str) and g.strip()],
    }


# ---- tab 2: Research -----------------------------------------------------------------------------

def _persona_line(p):
    if not isinstance(p, dict):
        return str(p or "").strip()
    return " — ".join(x for x in (p.get("name") or "", p.get("lens") or "") if x)


def research(meta):
    if not _milestone_done(meta, "research"):
        return None
    rs = _run_artifact(meta, "research.json") or {}
    world = rs.get("world") or {}
    evidence = rs.get("evidence") or {}
    team = [t for t in evidence.get("team") or [] if isinstance(t, dict)]
    turns = [t for t in evidence.get("turns") or [] if isinstance(t, dict)]
    researchers = []
    for t in team:
        role = t.get("role") or ""
        qs = [x.get("question") for x in turns if x.get("persona") == role and x.get("question")]
        researchers.append({"role": role, "focus": t.get("focus") or "", "questions": qs})
    reuse = rs.get("reuse") or {}
    have_it = None
    if reuse.get("chosen_links"):
        have_it = {"verdict": reuse.get("verdict") or "", "why": reuse.get("why") or "",
                  "links": reuse.get("chosen_links") or []}
    return {
        "angle": rs.get("angle") or "", "spine": rs.get("spine") or "",
        "about": world.get("about") or "", "not_about": world.get("not_about") or "",
        "persona": _persona_line(rs.get("persona")),
        "researchers": researchers,
        "have_it": have_it,
        "dossier": _has_doc(meta, "dossier.md"),
        "voices": _has_doc(meta, "voices-from-the-field.md"),
    }


# ---- tab 3: Architect ----------------------------------------------------------------------------
# Shows the architect's OUTPUT (work-shape.json / work-allocate.json / work-headings.json), not the
# candidate menu (blueprint.json) -- that only feeds the "what was left out" overlay. Greyed out
# until work-headings.json exists: before that the final headings are not decided yet.

def architect(meta):
    if not _milestone_done(meta, "plan"):
        return None
    wh = _run_artifact(meta, "work-headings.json")
    if not wh:
        return None                              # the run has not reached the architect phase yet
    ws = _run_artifact(meta, "work-shape.json") or {}
    wa = _run_artifact(meta, "work-allocate.json") or {}
    bp = _run_artifact(meta, "blueprint.json") or {}

    st = wh.get("structure") or {}
    shape_secs = (ws.get("structure") or {}).get("sections") or []
    alloc_secs = (wa.get("structure") or {}).get("sections") or []
    alloc_raw = ((wa.get("allocation") or {}).get("raw") or {}).get("allocation") or []
    budget = st.get("word_budget") or (wa.get("structure") or {}).get("word_budget") or {}

    sections = []
    for i, sec in enumerate(st.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        shape_sec = shape_secs[i] if i < len(shape_secs) and isinstance(shape_secs[i], dict) else {}
        alloc_sec = alloc_secs[i] if i < len(alloc_secs) and isinstance(alloc_secs[i], dict) else {}
        why = next((a.get("why") or "" for a in alloc_raw
                   if isinstance(a, dict) and a.get("section") == i), "")
        n_facts = len(shape_sec.get("boxes") or sec.get("boxes") or [])
        sections.append({
            "headline": sec.get("headline") or "", "job": shape_sec.get("job") or "",
            "word_target": alloc_sec.get("word_target") or sec.get("word_target") or 0,
            "n_facts": n_facts,
            "h3s": sec.get("h3s") or shape_sec.get("h3s") or [],
            "why": why,
        })

    # Diffed against the WORKING shape's headlines, not the final ones: headings.py renames every
    # section it keeps, so a final headline rarely matches its blueprint candidate's wording any
    # more, but shape.py -- the step that actually decides keep-or-drop -- picks its survivors
    # straight off the candidate menu without rewriting them (write/plan_select.py's audit.drops
    # is the same diff, computed while the run is live; this is that diff done again, from disk).
    chosen = set()
    for s in shape_secs:
        if isinstance(s, dict) and s.get("headline"):
            chosen.add(s["headline"].strip().lower())
    dropped = []
    for s in bp.get("sections") or []:
        if not isinstance(s, dict):
            continue
        heading = (s.get("h2") or s.get("heading") or "").strip()
        if heading and heading.lower() not in chosen:
            dropped.append(heading)
    for d in (ws.get("structure") or {}).get("dropped_items") or []:
        if isinstance(d, str) and d.strip() and d not in dropped:
            dropped.append(d.strip())
    faq_items = []
    for f in bp.get("faq") or []:
        if isinstance(f, dict):
            q = (f.get("q") or f.get("question") or "").strip()
            if q:
                faq_items.append(q)

    left_out = None
    if dropped or faq_items:
        left_out = {
            "sections": dropped, "faq": faq_items,
            "note": "%d candidate section%s and %d question%s did not earn their place" % (
                len(dropped), "" if len(dropped) == 1 else "s",
                len(faq_items), "" if len(faq_items) == 1 else "s"),
        }

    return {
        "format": st.get("format_archetype") or "", "spine": st.get("spine") or "",
        "target_words": budget.get("target"), "n_sections": len(sections),
        "n_sub_headings": sum(len(s["h3s"]) for s in sections),
        "sections": sections, "left_out": left_out,
    }


# ---- tab 5: Edits ---------------------------------------------------------------------------------
# The plain-English label per write phase editing step, in the order write_article.py's STEPS runs
# them (tools/write_article.py:41-43, the same labels the `step()` calls there use). Only the
# passes that actually left a report get a row -- a run stopped mid-way shows only what happened.
EDIT_STEP_LABELS = [
    ("blend", "Joined the sections into one piece"),
    ("wrapper", "Wrote the intro, quick answer, FAQ and close"),
    ("coherence", "Read the article whole"),
    ("readable", "Rewrote it to be read"),
    ("sentences", "Re-shaped the sentences"),
    ("slop", "Removed the tells of machine writing"),
    ("links", "Laid in the links"),
    ("clean", "Scrubbed stray characters"),
]


def _coverage_rows(rows, field):
    """One tab row per topic: its name, and the one thing the screen says next to it. A row with no
    topic is dropped rather than rendered as a blank line."""
    return [{"topic": str(r.get("topic") or "").strip(), field: str(r.get(field) or "").strip()}
            for r in (rows or []) if isinstance(r, dict) and str(r.get("topic") or "").strip()]


def _coverage(rep):
    """What the draft covered of the topics every ranking page covers, and why each drop happened.

    None for every article written before this shipped, which is the point: a run with no such
    record renders nothing at all rather than an empty box claiming it covered nothing.

    Read from the readable step's own report, which is where write/readable.py::coverage_report
    puts it, and from the top level too, so it is found whichever place write-report.json carries
    it. Nothing is computed here: what is on disk is what is shown, or there is no row.
    """
    cov = rep.get("coverage_report")
    if not isinstance(cov, dict):
        cov = ((rep.get("steps") or {}).get("readable") or {}).get("coverage_report")
    if not isinstance(cov, dict) or not cov.get("expected_total"):
        return None
    return {"expected_total": cov.get("expected_total"),
            "covered": _coverage_rows(cov.get("covered"), "section"),
            "dropped": _coverage_rows(cov.get("dropped"), "why")}


def edits(meta):
    if not _milestone_done(meta, "edited"):
        return None
    rep = _run_artifact(meta, "write-report.json") or {}
    steps_present = rep.get("steps") or {}
    passes = [label for key, label in EDIT_STEP_LABELS if key in steps_present]

    sc = _run_artifact(meta, "source-check.json") or {}
    counts = sc.get("counts") or {}
    source_check = None
    if counts:
        source_check = {"checked": counts.get("checked") or 0, "fine": counts.get("supported") or 0,
                        "corrected": counts.get("corrected") or 0, "softened": counts.get("softened") or 0,
                        "removed": counts.get("removed") or 0}

    words = (rep.get("length") or {}).get("words")
    rs = _run_artifact(meta, "research.json") or {}
    band = (rs.get("build_spec") or {}).get("word_band") or {}
    target = None
    if band.get("min") and band.get("max"):
        target = (int(band["min"]) + int(band["max"])) // 2
    elif band.get("min") or band.get("max"):
        target = band.get("min") or band.get("max")

    # THE LINKS REPORT MOVED HERE FROM THE DRAFT (owner, 2026-09-22: "the draft should be super
    # clean... just the article"). The draft view used to show, above the article, which internal
    # pages were linked and which sources survived. That was stripped so the draft is only the
    # article -- but stripped is not deleted. This is the only place anyone can see whether the
    # links landed and the sources held, so it lands on the Edits tab beside the coverage report,
    # which is where somebody opening a finished article goes looking for exactly this.
    links = _run_artifact(meta, "links-report.json")
    return {"passes": passes, "source_check": source_check, "coverage": _coverage(rep),
           "links": links if isinstance(links, dict) and links else None,
           "has_source_check_doc": _has_doc(meta, "source-check.md"),
           "words": words, "target_words": target}


def all_tabs(meta):
    """{"search_picture", "research", "architect", "edits"}, each None when not yet available.
    Draft is not here: the screen already has it on /library/{id}'s own `draft` field.

    Gated on the milestone strip ON THE META IT IS HANDED, which is what makes `save` and `served`
    below pass the RUN's own strip rather than the one library_get returns: since 2026-09-21 that
    one can be a record of tabs already kept (store._kept_strip), and assembling against a record
    would open every gate and then read a run folder that is not there -- four dicts full of
    blanks, which is exactly the empty shell this whole change exists to stop showing.
    """
    return {"search_picture": search_picture(meta), "research": research(meta),
           "architect": architect(meta), "edits": edits(meta)}


# ---- keeping them, and serving them once the run is gone -----------------------------------------
#
# THE SIZE GUARD. Every row of the `library` table is carried to every teammate and sits in their
# meta jsonb for good, so a pathological article must not make everyone pay for it. Measured on a
# real article the four tabs are 28.3 KB in total, so 400 KB is roughly fourteen times the real
# thing: comfortably out of the way of anything normal, and still a hard ceiling. Over it, the
# LARGEST tab is dropped and the smaller ones are kept -- a person who loses the 300 KB architect
# table still has the research and the search picture -- and what was dropped is recorded on the
# row, so the screen can say so plainly instead of showing a tab that is silently empty.
TABS_MAX_BYTES = 400_000

TAB_KEYS = tuple(store.TAB_MILESTONE)          # the four assembled tabs, in strip order


def _bytes(tabs):
    return len(json.dumps(tabs, ensure_ascii=False).encode("utf-8"))


def fit(tabs):
    """(tabs, dropped): the tabs cut down to TABS_MAX_BYTES, largest first. Never raises.

    Dropping is by whole tab, never by trimming inside one: half a research tab reads as a thin
    run rather than as a cut, and a person cannot tell the two apart from the screen.
    """
    tabs = dict(tabs or {})
    dropped = []
    while _bytes(tabs) > TABS_MAX_BYTES:
        present = [k for k in TAB_KEYS if tabs.get(k)]
        if not present:
            break                               # nothing left to drop: the shell alone is over
        biggest = max(present, key=lambda k: _bytes({k: tabs[k]}))
        tabs[biggest] = None
        dropped.append(biggest)
    return tabs, dropped


def _run_strip(meta):
    """The RUN's own milestone strip. [] when the run folder is gone (store.milestones' own rule)."""
    return store.milestones(meta.get("chat_id"), meta.get("run_id"))


def save(item_id, meta=None):
    """Assemble this row's tabs from its run and keep them with the article. None when there is no
    run to assemble from.

    Called at the moment an article is saved to the Library, while the run's artifacts are
    certainly still on disk, and again by the backfill for articles saved before this existed.
    Idempotent: the same run assembles to the same four tables every time (nothing in this file
    calls a model or reads a clock), so running it twice writes the same file twice.
    """
    meta = meta or store.library_get(item_id)
    if not meta:
        return None
    strip = _run_strip(meta)
    if not strip:
        return None                             # the run is gone; there is nothing to assemble
    tabs = all_tabs(dict(meta, milestones=strip))
    if not any(tabs.get(k) for k in TAB_KEYS):
        return None                             # the run never reached a single tab's gate
    kept_now = [k for k in TAB_KEYS if tabs.get(k)]
    tabs, dropped = fit(tabs)
    tabs["dropped"] = dropped
    store.save_library_tabs(item_id, tabs, kept=[k for k in kept_now if k not in dropped],
                            dropped=dropped)
    return tabs


def ensure(item_id, meta=None):
    """Keep the tabs if this row has none yet. Cheap enough to sit on every save path: one stat
    when they are already there, and never raises -- an article must save whatever happens here."""
    try:
        if store.read_library_tabs(item_id):
            return None
        return save(item_id, meta)
    except Exception:                           # noqa: BLE001 -- a record is not worth losing a save
        return None


def served(meta):
    """What GET /library/{id}/tabs answers: the four tabs plus where they came from.

    THE ORDER IS THE WHOLE POINT. The run is read FIRST whenever its folder is there, because a
    live run's tabs change under you and a file written at save time would go stale on the one
    screen a person watches while the article is being written. Only when the run is gone -- a
    deleted chat, or a teammate who never had it -- does the kept copy answer, which is what makes
    a teammate's screen show the same five tabs the author sees.

      source "run"    assembled just now from the run's own artifacts
      source "saved"  the copy kept with the article when it was saved
      source "none"   neither: an article from before the tabs were kept, and nothing to show.
                      The screen says that in plain words rather than drawing an empty tab.
    """
    strip = _run_strip(meta)
    if strip:
        tabs = all_tabs(dict(meta, milestones=strip))
        if any(tabs.get(k) for k in TAB_KEYS):
            return dict(tabs, source="run", dropped=[])
    saved = store.read_library_tabs(meta.get("id") or "") or {}
    out = {k: saved.get(k) for k in TAB_KEYS}
    # what the size guard cut is read from the row's own stamp when tabs.json itself does not say,
    # so "this one was too big to share" stays sayable even when every tab was over the ceiling
    dropped = list(saved.get("dropped") or (meta.get("tabs_saved") or {}).get("dropped") or [])
    return dict(out, source="saved" if any(out.values()) else "none", dropped=dropped)
