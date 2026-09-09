"""render.py — the two documents a person reads, and the trail behind them.

The original ends a research run with files, not just data: `research-doc-<slug>.md` (the brief),
`research-notes.md` (the agent's own caveats) and `bundle-<slug>.md` (the cover sheet that points
at everything). The port computed every input for all three and rendered none of them, so the only
way to check a run was to read JSON.

PURE ASSEMBLY, the way `10-dataforseo/scripts/s7_assemble.py` is: the keyword, snapshot and winners
sections are lifted verbatim from what those steps already wrote. Nothing here re-summarises, and
nothing here decides anything. The verdict and the build spec were written earlier by assemble.py
and are only laid out.

Reads: the research artifact plus the run's _work files. Writes: research-doc.md, bundle.md.
"""
import os

from . import _common as _c


def _plural(n, word, many=None):
    """These documents are read by a person, and "1 questions" reads like a bug."""
    return "%d %s" % (n, word if n == 1 else (many or word + "s"))

# work file -> what a person should call it, in the order the run produced them. This is the port
# of the original's numbered proof/ folder, which is how a run was audited.
TRAIL = [
    ("world.json", "The world statement", "what this subject is and is not about"),
    ("seeds.json", "The seed phrases", "what the keyword search started from"),
    ("pool.json", "Every keyword found", "the raw pool before any filter"),
    ("shortlist.json", "The keywords worth pricing", "volume and difficulty filter applied"),
    ("metrics.json", "The priced keywords", "real volume, difficulty and intent for each"),
    ("keywords.json", "The chosen keyword set", "primary, variations, secondaries and spokes"),
    ("serp.json", "The live search results", "what Google actually returns for the primary"),
    ("snapshot.json", "The search-results read", "who ranks, the answer box, People Also Ask"),
    ("pages.json", "The winning pages", "the pages that rank, read in full"),
    ("winners.json", "What the winners cover", "their common headings and the gaps we can own"),
    ("topic-gate.json", "Is this ours to write", "and the angle the results argue for"),
    ("spine.json", "The spine", "what the article argues, in one paragraph"),
    ("persona.json", "The reader", "who this is written to"),
    ("curate.json", "The research conversation", "every question asked and what the expert answered"),
    ("dossier.json", "The dossier", "the cited write-up the facts were lifted from"),
    ("dossier-cards.json", "The facts", "one card per fact, each quoted and sourced"),
    ("gap-check.json", "The gap check", "what the evidence still does not cover"),
    ("gap-evidence.json", "The gap fill", "what the extra searches found"),
    ("ownpage.json", "Your own pages", "matched by meaning, for internal links"),
    ("brief.json", "The verdict and build spec", "the call on whether to write it, and to what shape"),
]


def trail(chat_id, run_id, store):
    """The evidence trail: every step's own file, named in plain English, newest last."""
    out = []
    work = os.path.join(store.run_dir(chat_id, run_id), "artifacts", "_work")
    for name, label, note in TRAIL:
        p = os.path.join(work, name)
        if os.path.exists(p):
            out.append({"file": name, "label": label, "note": note,
                        "bytes": os.path.getsize(p)})
    return out


def _lift(md, header):
    """A section, verbatim, under our own heading. Only the machine-only readlist block and the
    file's own heading are stripped, exactly as the original does."""
    import re
    txt = re.sub(r"```readlist.*?```", "", md or "", flags=re.S).strip()
    lines = txt.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return header + "\n\n" + "\n".join(lines).strip()


def _bullets(items):
    return "\n".join("- %s" % i for i in items if str(i).strip()) or "(none)"


def research_doc(research, keywords_md, snapshot_md, winners_md, trail_rows):
    """The brief a person reads. Pure assembly."""
    bs = research.get("build_spec") or {}
    band = bs.get("word_band") or {}
    spec = [
        "**Word band:** %s to %s" % (band.get("min", "?"), band.get("max", "?")),
        "**Featured snippet target:** %s" % (bs.get("featured_snippet_target") or "(none named)"),
        "**Close:** %s" % (bs.get("close") or "(none named)"),
    ]
    if bs.get("structure"):
        spec.append("\n**Structure**\n" + _bullets(bs["structure"]))
    if bs.get("primary_sources"):
        spec.append("\n**Primary sources to cite**\n" + _bullets(bs["primary_sources"]))

    boxes = "\n".join("- [%s] %s" % ("x" if c.get("pass") else " ", c.get("check", ""))
                      for c in (research.get("completeness") or [])) or "(not computed)"
    proof = "\n".join("- `%s` — %s: %s" % (r["file"], r["label"], r["note"]) for r in trail_rows) or "(none)"

    ev = research.get("evidence") or {}
    how = []
    if ev.get("team"):
        how.append("A research team of %d interviewed an expert over %s, across %s."
                   % (len(ev["team"]), _plural(ev.get("questions", 0), "question"),
                      _plural(ev.get("searches", 0), "search")))
        how.append("Team: " + "; ".join("%s (%s)" % (r["role"], r.get("focus", "")[:70]) for r in ev["team"]))
        if ev.get("dossier_words"):
            how.append("Their findings were written up as a %d-word dossier over %s, and the facts "
                       "below were lifted from it." % (ev["dossier_words"],
                                                       _plural(len(ev.get("dossier_sources") or []), "source")))
    else:
        how.append("Evidence came from reading the pages that rank for the keyword set, one pass.")

    parts = [
        "# Research brief — %s" % (research.get("topic") or "this article"),
        "> **Angle:** %s" % (research.get("angle") or "(none)"),
        "## Verdict\n\n" + (_bullets(research.get("verdict") or []) if isinstance(research.get("verdict"), list)
                            else str(research.get("verdict") or "(none)")),
        "## How the evidence was gathered\n\n" + "\n\n".join(how),
        _lift(keywords_md, "## Keywords"),
        _lift(snapshot_md, "## SERP snapshot"),
        _lift(winners_md, "## What the winners cover"),
        "## Build spec\n\n" + "\n".join(spec),
        "## Proof map (every claim above traces to one of these)\n\n" + proof,
        "## Completeness (each box is a real check, computed here)\n\n" + boxes,
    ]
    if research.get("demo_data"):
        parts.insert(1, "> **DEMO DATA.** DataForSEO was not connected for this run, so every volume, "
                        "difficulty and ranking figure below is a placeholder, not a measurement.")
    if research.get("notes"):
        parts.append("## Notes from the run\n\n" + _bullets(research["notes"]))
    return "\n\n".join(p for p in parts if p.strip())


def bundle(research, trail_rows, brand_files):
    """The cover sheet: everything needed to write this, and where each piece lives.

    Ported from `14-research-conductor/scripts/bundle.py::_cover_sheet`. In the original the
    pointers are file paths; here they are the screens the person can actually click.
    """
    kw = research.get("keywords") or {}
    pr = kw.get("primary") or {}
    bs = research.get("build_spec") or {}
    band = bs.get("word_band") or {}
    per = research.get("persona") or {}
    ev = research.get("evidence") or {}
    rows = [
        "**Title:** %s" % (research.get("topic") or ""),
        "**Distinct angle:** %s" % (research.get("angle") or ""),
        "**Primary keyword:** %s (%s a month, difficulty %s)%s"
        % (pr.get("keyword", "?"), pr.get("volume", "?"), pr.get("kd", "?"),
           "  ⚠️ demo data, not a measurement" if research.get("demo_data") else ""),
        "**Target length:** %s to %s words, from the pages actually ranking for this keyword"
        % (band.get("min", "?"), band.get("max", "?")),
        "**Format:** %s" % (bs.get("format") or research.get("format_archetype") or "decided at the plan step"),
        "**Reuse verdict:** %s" % ((research.get("reuse") or {}).get("verdict") or "(not checked)"),
        "**Reader (write to this depth, never name them):** %s" % (per.get("name") or "a practitioner"),
    ]
    if ev.get("team"):
        rows.append("**Researched by:** %s, over %s"
                    % (", ".join(r["role"] for r in ev["team"]),
                       _plural(ev.get("questions", 0), "question")))
    # (label, the brand files it points at; empty means it always shows)
    POINTERS = [
        ("**The plan** — the article's headings, evidence and links (the Article plan checkpoint)", []),
        ("**Voice** — Knowledge › brand-voice.md", ["brand-voice.md"]),
        ("**Style and mechanics** — Knowledge › style-guide.md", ["style-guide.md"]),
        ("**Product facts** — Knowledge › features.md", ["features.md"]),
        ("**SEO/AEO/GEO checklist** — Knowledge › seo-aeo-geo-checklist.md", ["seo-aeo-geo-checklist.md"]),
        # opinions.md was deleted in 2.248.0: nothing ever read it, and it asked the owner to answer
        # an interview whose answers no step used.
        ("**Cite-from material** — Knowledge › stats.md, stories.md", ["stats.md", "stories.md"]),
        ("**Worked examples** — Knowledge › writing-examples.md", ["writing-examples.md"]),
        ("**Writing integrity** — Knowledge › writing-integrity.md", ["writing-integrity.md"]),
        ("**The writer brief** — Knowledge › writer-brief.md", ["writer-brief.md"]),
        ("**The research detail** — the evidence trail below, and the dossier", []),
    ]
    have = {str(f).lower().split("/")[-1] for f in (brand_files or [])}
    # a pointer to a file that is not there is worse than no pointer; renumber what survives, or
    # the list reads 1, 10 and looks broken
    kept = [text for text, needs in POINTERS if not needs or any(n in have for n in needs)]
    pointers = ["%d. %s" % (i, t) for i, t in enumerate(kept, start=1)]
    trail_md = "\n".join("- **%s** — %s (`%s`)" % (r["label"], r["note"], r["file"]) for r in trail_rows)
    return "\n\n".join([
        "# Research bundle — %s" % (research.get("topic") or "this article"),
        "> Everything needed to write this article, and where each piece is.",
        "\n".join(rows),
        "## What to open, in order\n\n" + "\n".join(pointers),
        "## The evidence trail\n\nEvery step of the research kept its own file. Open any of them to "
        "see exactly what that step did.\n\n" + trail_md,
    ])


# ---- the search picture ---------------------------------------------------------------------------
# One file a person can read WHILE the article is being written, instead of being stopped and asked to
# approve things. Written at the END of the write phase's gather step, because that is where the
# People-Also-Ask questions, the related searches and the table-stakes topics are vetted: what is on
# the page is then the same filtered set the plan is built from, not a rawer list that would disagree
# with the article.
#
# PURE ASSEMBLY, and NO MODEL CALL, for the same reason research_doc is: a model writing this could
# quietly drop a number or soften a gap, and then the file stops being evidence of anything. Every
# line below is lifted from research.json or from the vetted lists gather already produced.

_NOTHING = "(nothing was recorded for this run)"


def _figure(v):
    """A number exactly as the step wrote it, or a plain phrase. Never the word None on a page."""
    s = "" if v is None else str(v).strip()
    return s if s and s.lower() not in ("none", "null", "?") else "not measured"


def _kw_row(item):
    """One keyword line, whether the step stored the full record or only the phrase."""
    if isinstance(item, dict):
        return str(item.get("keyword") or "").strip(), _figure(item.get("volume")), _figure(item.get("kd"))
    return str(item or "").strip(), "not measured", "not measured"


def _kw_table(items):
    rows = [r for r in (_kw_row(i) for i in items or []) if r[0]]
    if not rows:
        return "(none)"
    return ("| keyword | searches a month | difficulty |\n|---|---|---|\n"
            + "\n".join("| %s | %s | %s |" % r for r in rows))


def _key(s):
    return " ".join(str(s or "").split()).lower()


def _tagged(items, ids, kind, kept=()):
    """One list, each line carrying the id the plan step mints for it, so a section tagged
    "paa: Q3" in the plan can be traced straight back to the question here. Same minting
    (write/plan_select.py::tag_maps), so the ids are the same ids."""
    idx = {_key(text): i for i, text in ((ids or {}).get(kind) or {}).items()}
    marks = {_key(k) for k in kept or ()}
    out = []
    for it in items or []:
        t = str(it).strip()
        if not t:
            continue
        i = idx.get(_key(t))
        out.append("- %s%s%s" % (("**%s** " % i) if i else "", t,
                                 " (kept)" if _key(t) in marks else ""))
    return "\n".join(out) or "(none)"


def _kept_line(noun, many, returned, vetted_from, kept):
    """The line that stops this reading as things going missing. Someone who saw 22 questions on the
    research brief and 9 here has to be able to see why, in numbers, on the page."""
    raised = max(returned, vetted_from)
    if not raised:
        return ("The search results raised no %s for this keyword. Nothing was filtered out: there "
                "was nothing to filter." % many)
    parts = []
    if returned > vetted_from > 0:
        gone = returned - vetted_from
        parts.append("The search results returned %s. %d %s set aside during research as belonging to a "
                     "different subject, leaving %d." % (_plural(returned, noun, many), gone,
                                                         "was" if gone == 1 else "were", vetted_from))
        parts.append("Of those %d, %d %s kept here." % (vetted_from, kept, "is" if kept == 1 else "are"))
    else:
        parts.append("The search results raised %s. %d %s kept here."
                     % (_plural(raised, noun, many), kept, "is" if kept == 1 else "are"))
    parts.append("These are the ones a reader of THIS article would care about: the filtered set, "
                 "not everything the search results raised.")
    return " ".join(parts)


def _set_aside(raw, kept):
    k = {_key(x) for x in kept or ()}
    left = [str(x).strip() for x in raw or [] if str(x).strip() and _key(x) not in k]
    if not left:
        return ""
    # NOT "set aside": the funnel line above already uses that for what the research step dropped,
    # and two set-asides on one page reads as one thing counted twice.
    return ("\n\n**Raised, but not kept for this article**\n\n" + _bullets(left))


def _who_ranks(serp):
    rows = []
    for n, x in enumerate(serp.get("who_ranks") or [], start=1):
        if not isinstance(x, dict):
            rows.append("%d. %s" % (n, x))
            continue
        rank = x.get("rank") or n
        head = ", ".join(p for p in [str(x.get("domain") or "").strip(), str(x.get("title") or "").strip()] if p)
        url = str(x.get("url") or "").strip()
        rows.append("%s. %s%s" % (rank, head or "(no title recorded)", ("\n   %s" % url) if url else ""))
    body = "\n".join(rows) or _NOTHING
    note = str(serp.get("who_ranks_text") or "").strip()
    return (body + "\n\n" + note) if note else body


def search_picture(research, vetted, ids=None):
    """The search picture: what the search results actually said, laid out to be read alongside the
    plan. PURE ASSEMBLY of research.json plus the vetted lists; nothing here decides or summarises.

    `vetted` carries what gather kept and what it started from:
        {paa_raw, paa_kept, related_raw, related_kept, table_stakes_raw, table_stakes_kept,
         persona (the reader the article is written to), note}
    `ids` is write/plan_select.py::tag_maps(group_b) — the same minted G/T/Q/R ids the plan tags
    against, so a person can read a tag in the plan and find the item it names in here.
    """
    r = research or {}
    v = vetted or {}
    kw, serp, win = r.get("keywords") or {}, r.get("serp") or {}, r.get("winners") or {}
    # the reader the ARTICLE is written to, which is the blueprint's when it has one: the picture
    # must not name a different reader from the one the writer targets (single source of truth).
    per = v.get("persona") or r.get("persona") or {}
    demo = bool(r.get("demo_data"))

    prim = kw.get("primary")
    prim = prim if isinstance(prim, dict) else {"keyword": prim}
    name = str(prim.get("keyword") or "").strip()
    kw_lines = []
    if name:
        kw_lines.append("**Primary:** `%s`, %s searches a month, difficulty %s, intent %s%s"
                        % (name, _figure(prim.get("volume")), _figure(prim.get("kd")),
                           _figure(prim.get("intent")),
                           "  (demo data, not a measurement)" if demo else ""))
        if str(prim.get("why") or "").strip():
            kw_lines.append("Why this one: %s" % str(prim.get("why")).strip())
    else:
        kw_lines.append(_NOTHING)
    kw_lines.append("**Variations** (same intent, woven in-body)\n\n" + _kw_table(kw.get("variations")))
    kw_lines.append("**Secondaries** (each one anchors a section)\n\n"
                    + _kw_table(kw.get("secondary") or kw.get("secondaries")))

    paa_raw, paa_kept = list(v.get("paa_raw") or []), list(v.get("paa_kept") or [])
    rel_raw, rel_kept = list(v.get("related_raw") or []), list(v.get("related_kept") or [])
    stakes_raw = list(v.get("table_stakes_raw") or win.get("common_h2s") or [])
    stakes_kept = list(v.get("table_stakes_kept") or [])
    # what Google returned before ANY filter, so the funnel reads end to end
    paa_returned = len(serp.get("paa") or []) or (len(serp.get("paa_on") or []) + len(serp.get("paa_off") or []))
    rel_returned = len(serp.get("related_on") or []) + len(serp.get("related_off") or [])

    q_body = _kept_line("question", "questions", paa_returned, len(paa_raw), len(paa_kept)) + "\n\n" \
        + _tagged(paa_kept, ids, "paa") + _set_aside(paa_raw, paa_kept)
    r_body = _kept_line("related search", "related searches", rel_returned, len(rel_raw), len(rel_kept)) + "\n\n" \
        + _tagged(rel_kept, ids, "related") + _set_aside(rel_raw, rel_kept)
    if str(v.get("note") or "").strip():
        q_body += "\n\n**%s**" % str(v["note"]).strip()

    stakes_body = ("%s every ranking page covers. %d of them were kept as the ones this article has to "
                   "cover too.\n\n" % (_plural(len(stakes_raw), "topic"), len(stakes_kept))
                   + _tagged(stakes_raw, ids, "common-h2", kept=stakes_kept))

    who = per.get("name") or ""
    lens = str(per.get("lens") or "").strip()
    persona_lines = [l for l in ["**Reader (write to this depth, never name them):** %s"
                                 % (who or "a practitioner, not an academic"),
                                 ("Their lens: %s" % lens) if lens else "",
                                 ("Why this reader: %s" % str(per.get("why")).strip()) if per.get("why") else ""]
                     if l.strip()]

    verdict = r.get("verdict")
    verdict_md = _bullets(verdict) if isinstance(verdict, list) else str(verdict or "").strip()
    gate = r.get("topic_gate") or {}
    end = ["**The angle the search results argued for:** %s" % (r.get("angle") or "(none recorded)"),
           verdict_md or _NOTHING]
    if str(gate.get("why") or "").strip():
        end.append("Why this topic is ours to write: %s" % str(gate["why"]).strip())
    if gate.get("angle_changed"):
        why_changed = str(gate.get("why_changed") or "").strip()
        end.append("The angle was rewritten from the real search results"
                   + ((": %s" % why_changed) if why_changed else "."))

    parts = [
        "# The search picture: %s" % (r.get("topic") or "this article"),
        "> What the search results actually said, and what was kept from them. Every line is lifted "
        "from the research run and the plan step's own filter. Nothing here was re-written, and no "
        "model wrote this page.",
        "## The keyword and its numbers\n\n" + "\n\n".join(kw_lines),
        "## Who ranks now\n\n" + _who_ranks(serp),
        "## What they all cover\n\n" + stakes_body,
        "## What none of them cover\n\n" + _tagged(win.get("gaps_to_own"), ids, "gap"),
        "## What the winners cover that this article should not\n\n" + _bullets(win.get("drift") or []),
        "## The questions worth answering\n\n" + q_body,
        "## Related searches\n\n" + r_body,
        "## Who this is written for\n\n" + "\n\n".join(persona_lines),
        "## The verdict, and the angle it argued for\n\n" + "\n\n".join(x for x in end if x.strip()),
    ]
    if demo:
        parts.insert(1, "> **DEMO DATA.** DataForSEO was not connected for this run, so every volume, "
                        "difficulty and ranking figure below is a placeholder, not a measurement.")
    return "\n\n".join(p for p in parts if p.strip()) + "\n"
