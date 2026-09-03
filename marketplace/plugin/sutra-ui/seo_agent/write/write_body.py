"""write_body.py — Writer step 1: BODY. Write each section of the article into neutral, sourced prose.

  - ONE call per section, run in parallel. A call sees ONLY its own cards, so it cannot invent facts.
  - Every call also sees the article's SPINE and the FULL PLAN (every other section's headline, job and
    sub-topics) so twelve separately-written sections still pull in one direction and never overlap.
    They cannot see each other's TEXT, only the briefs.
  - The section's SHAPE arrives with the facts UNDER the heading they belong to: the opening's facts,
    then each authored sub-heading with its own. A writer cannot follow a shape it cannot see.
  - Facts carry a [c<id>] tag inline; CODE parses those into a provenance list. A tag pointing at a card
    not in this section is a hallucinated id: it is dropped from the prose and counted.
  - PRODUCT-FREE by default; the rule relaxes only for a section that IS about the brand.
  - Wrappers (intro/quick answer/FAQ/close) are NOT written here.
The writer brief (brand/writer-brief.md) is the ONE brand file the body writer reads.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import llm
from . import _common as C
from . import shape, tags

SYSTEM = ("You are a working writer. Reply with only the section that was asked for: the heading line, "
          "then the prose. No preamble, no sign-off, no notes about what you did.")


def _brief():
    b = C.sh.brand_file("writer-brief.md").strip()
    return b or "(no writer-brief.md for this company yet; write plainly, name no capability you cannot see)"


def _plan_block(sections, cur):
    lines = []
    for i, s in enumerate(sections, 1):
        mark = "    <<<< YOU WRITE THIS ONE" if s is cur else ""
        lines.append("%d. %s%s" % (i, s.get("headline", ""), mark))
        lines.append("   JOB: %s" % (s.get("job") or "(none given)"))
        lines.append("   COVERS: %s" % shape.covers(s))
    return "\n".join(lines)


def _facts(group, idx):
    lines = []
    for cid in group.get("card_ids", []):
        c = idx.get(C.nid(cid)) or {}
        text = (c.get("verbatim") or c.get("gloss") or "").strip().replace("\n", " ")[:C.BODY_CARD_CHARS]
        if not text:
            continue
        src = (c.get("source_urls") or [None])[0] or c.get("source_note") or "(no source)"
        ours = " [OUR OWN RESEARCH — name it in the prose]" if str(c.get("tag", "")).startswith("brand") else ""
        lines.append("  [c%s] %s  — source: %s%s" % (C.nid(cid), text, src, ours))
    return lines


def render_shape(sec, idx):
    """The section's SHAPE and its facts, together. Showing the facts UNDER their heading is the point."""
    lead, h3s = (sec.get("lead") or {}), (sec.get("h3s") or [])
    lead_facts = _facts(lead, idx)
    out = []
    if h3s:
        out.append("THE OPENING — write this first, directly under the section heading, with no "
                   "sub-heading of its own:")
        out += lead_facts or ["  (no facts of its own — open with a short lead-in to the sub-headings below)"]
        for h in h3s:
            out.append("")
            out.append('SUB-HEADING (render it exactly, as "### %s"):' % h.get("h3", ""))
            out += _facts(h, idx) or ["  (no facts — do not invent any; if it cannot be written, leave it out)"]
    else:
        out.append("THIS SECTION HAS NO SUB-HEADINGS. Write it straight through as prose under its "
                   "heading. Do NOT invent sub-headings.")
        out += lead_facts
    body = "\n".join(out).strip()
    return body or ("(this section has NO research facts — write honestly and generally; do NOT "
                    "claim any testing, survey or interview you did not run, and invent nothing.)")


def provenance(prose, sec, idx):
    """Parse the [c<id>] tags into a per-card provenance list, and drop any tag naming a card that is NOT
    in this section. Returns (clean prose, provenance, dropped count)."""
    allowed = {C.nid(c) for h in shape.groups(sec) for c in h.get("card_ids", [])}
    foreign = {cid for cid in tags.id_set(prose) if cid not in allowed}
    dropped = sum(1 for cid in tags.ids(prose) if cid in foreign)
    if foreign:
        prose = tags.drop(prose, foreign)
    seen, prov = set(), []
    for m in tags.BLOCK.finditer(prose):
        for cid in tags._block_ids(m.group(0)):
            if cid in seen:
                continue
            seen.add(cid)
            c = idx.get(cid) or {}
            claim = re.split(r"(?<=[.!?])\s", prose[:m.start()])[-1].strip()[-160:]
            prov.append({"card_id": cid, "source_url": (c.get("source_urls") or [None])[0],
                         "is_number": C.has_number(c.get("verbatim", "")), "claim": claim})
    return prose, prov, dropped


def _table_instruction(sec):
    cols = ((sec.get("table") or {}).get("columns")) or []
    if len(cols) < 2:
        return ""
    return ("\nRENDER THIS SECTION AS A MARKDOWN TABLE. Not a description of a table — the table itself.\n"
            "Columns, in this order: " + " | ".join(cols) + "\n"
            "  · Two or three sentences may set it up. The table is the section's payload, not an aside.\n"
            "  · Every row is built from the evidence below. A cell you cannot fill from the evidence is\n"
            "    a plain dash \"-\", never a guess and never a placeholder like \"varies\" or \"TBD\".\n"
            "  · Keep cells short — a figure, a phrase, a band.\n"
            "  · Keep each fact's [c...] tag with it, inside the cell.\n"
            "  · Standard markdown pipes, with the header separator row. Nothing else renders.\n")


def _list_instruction(sec):
    kind = ((sec.get("list") or {}).get("kind") or "").strip().lower()
    if kind not in ("numbered", "bulleted"):
        return ""
    marker = "1. 2. 3." if kind == "numbered" else "- "
    why = ("the ORDER MATTERS — these are steps performed in sequence, or a ranking"
           if kind == "numbered" else "the items are PARALLEL and could be read in any order")
    of = ((sec.get("list") or {}).get("of") or "").strip()
    return ("\nRENDER THIS SECTION'S PAYLOAD AS A %s LIST" % kind.upper()
            + (" — the items are: %s\n" % of if of else "\n")
            + "  · Use %s markers, one item per line. %s.\n" % (marker, why.capitalize())
            + "  · Two or three sentences set it up first. The list is the payload, not an aside.\n"
            + "  · Each item is a line or two. An item needing four sentences is a paragraph in disguise.\n"
            + "  · Keep each fact's [c...] tag on whichever item carries it.\n"
            + "  · The section is NOT only a list. It still needs prose around it: the set-up before,\n"
            + "    and what it means for the reader after. A section that is nothing but bullets reads\n"
            + "    as a slide deck.\n")


def _thin_note(sec, failures):
    mine = [f for f in failures if (f.get("section") or "") == (sec.get("headline") or "")]
    if not mine:
        return ""
    return ("\nA WARNING ABOUT THIS SECTION: it asked for extra research and the research did not happen for "
            + ("this topic: " if len(mine) == 1 else "these topics: ")
            + "; ".join('"%s"' % f.get("h3", "") for f in mine)
            + ".\nSo the facts below are all there is, and they are thinner than this section was "
              "designed for. Write what the material honestly supports and STOP. Do not stretch to "
              "reach the word target, and do not fill the gap with generalities.\n")


def _strip_h2(prose, head):
    """The writer is asked to open with "## <heading>"; the assembler adds it, so one copy is enough."""
    lines = (prose or "").strip().split("\n")
    while lines and (not lines[0].strip() or
                     (lines[0].lstrip().startswith("##") and not lines[0].lstrip().startswith("###")
                      and lines[0].lstrip("# ").strip().lower() == (head or "").strip().lower())):
        lines.pop(0)
    return "\n".join(lines).strip()


def run(st, idx, ctx, say=lambda *a: None):
    sections = st["sections"]
    brand = C.company()
    brief, persona, memory = _brief(), ctx["persona"], C.sh.memory_block()
    fields = [str(f).strip() for f in (st.get("item_fields") or []) if str(f).strip()]
    contract = ("\nTHIS ARTICLE'S PER-ITEM CONTRACT — your section IS one of the list's items, so it MUST end\n"
                "with exactly these labelled parts, in this order:\n"
                + "\n".join("  %d. **%s**" % (i + 1, f) for i, f in enumerate(fields))
                + "\nEvery other ITEM in this article ends with the same parts. That is the reason the article\n"
                  "exists: a reader comparing items across the page needs the same parts in the same place\n"
                  "every time. Write each as a real, usable answer for THIS item — never a placeholder, never\n"
                  "a note that it does not apply.\n") if fields else ""
    supporting = ("\nThis article is a list, and the item sections each end with a fixed set of labelled parts.\n"
                  "YOUR SECTION IS NOT ONE OF THE ITEMS — it is a supporting section. Do NOT add those parts,\n"
                  "and do not imitate the shape of an item section. Write it as ordinary prose.\n") if fields else ""
    failures = st.get("research_failures") or []
    spine = st.get("spine") or "(no spine stated)"

    def _write(sec):
        head = (sec.get("headline") or "").strip()
        is_brand = brand["brand"].lower() in head.lower()
        rule = (("This section IS about %s. Cover it factually and fairly from the facts above, name at "
                 "least one honest limitation, and never oversell or invent a capability.") % brand["brand"]
                if is_brand else
                ("Name %s as little as you can. This article earns trust by being useful, not by selling. "
                 "If naming it is genuinely the clearest way to make a point the section is already making, "
                 "you may. Never make %s the answer to the reader's problem, and never spend more than a line "
                 "on it.") % (brand["brand"], brand["brand"]))
        p = C.prompt("write-body", brand=brand["brand"], about=brand["about"],
                     title=ctx["title"] or "(none)", angle=ctx["angle"] or "(none)", spine=spine,
                     persona=persona, plan=_plan_block(sections, sec), heading=head,
                     job=sec.get("job") or "(none given)", word_target=str(sec.get("word_target") or 300),
                     item_contract=contract if sec.get("is_item") else supporting,
                     table=_table_instruction(sec), list=_list_instruction(sec),
                     thin=_thin_note(sec, failures), shape=render_shape(sec, idx),
                     product_rule=rule, brief=brief, field="", memory=memory)
        prose = _strip_h2(llm.text(p, SYSTEM), head)
        prose, prov, dropped = provenance(prose, sec, idx)
        return {"headline": head, "job": sec.get("job", ""), "word_target": sec.get("word_target"),
                "words": len(prose.split()), "prose": prose, "provenance": prov, "bad_tags_dropped": dropped}

    say("Writing every section", "%d sections, %d at a time" % (len(sections), llm.PARALLEL))
    results = {}
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        futs = {ex.submit(_write, s): i for i, s in enumerate(sections)}
        for f in as_completed(futs):
            i = futs[f]
            results[i] = f.result()
            r = results[i]
            say("Written: %s" % r["headline"][:50], "%d words (aimed for %s), %d sourced claims%s"
                % (r["words"], r["word_target"], len(r["provenance"]),
                   ", %d stray tags dropped" % r["bad_tags_dropped"] if r["bad_tags_dropped"] else ""))
    out = {"format": st.get("format_archetype"), "spine": spine, "item_fields": fields,
           "sections": [results[i] for i in range(len(sections))]}

    if fields:
        items = [(s, o) for s, o in zip(sections, out["sections"]) if s.get("is_item")]
        misses = []
        for _, sec_out in items:
            missing = [f for f in fields if f.lower() not in sec_out["prose"].lower()]
            if missing:
                misses.append((sec_out["headline"], missing))
        leaked = [o["headline"] for s, o in zip(sections, out["sections"])
                  if not s.get("is_item") and all(f.lower() in o["prose"].lower() for f in fields)]
        out["contract_misses"] = [{"section": h, "missing": m} for h, m in misses]
        out["contract_leaked"] = leaked
        say("Checked the per-item contract", "honoured in %d of %d item sections" % (len(items) - len(misses), len(items)))
    total = sum(s["words"] for s in out["sections"])
    say("Body written", "%d sections, %d words, %d sourced claims"
        % (len(out["sections"]), total, sum(len(s["provenance"]) for s in out["sections"])))
    return out
