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
        ("**Cite-from material** — Knowledge › stats.md, opinions.md, stories.md",
         ["stats.md", "opinions.md", "stories.md"]),
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
