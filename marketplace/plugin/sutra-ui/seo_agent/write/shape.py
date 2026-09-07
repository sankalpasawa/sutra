"""shape.py — Architect step 1: SHAPE. Design the article's final BODY structure from numbered boxes.

Reads:  the frozen plan (H2s -> H3s -> card_ids + tags), the card index, the article context and the
        format's Structure rules (prompts/write/formats/<archetype>.md).
Writes: the shaped structure: sections (headline, job, covers, lead boxes, authored H3s, table, list,
        needs_research markers), the spine, benched boxes, unused boxes, shared-box warnings.

- Every H3 in the plan is a numbered BOX (#1..#N, plan order). Cards live inside their box.
- The AI designs the body with FREEDOM: sections, order, merges. It answers ONLY with headlines + box
  numbers. One box belongs to one section. Wrappers are another step's job.
- Roads by archetype:
    simple    (answer-bait / how-to / common-spine / data-report / glossary): one structure call
    listicle  : detect-items -> budget arithmetic -> structure call (items each get a section)
    comparison: detect-entities -> find-yardsticks -> filter (>= SHAPE_MIN_YARDSTICK_PCT% info) -> structure
    template  : structure call that also returns the artifact spec
- Code validates every box number, keeps one box in one place inside a section, drops a table without
  two named columns and a list without a renderable kind, reroutes a research request whose destination
  is not one of the section's own sub-headings, and audits unused boxes.
"""
from .. import llm
from . import _common as C


def mint_boxes(plan):
    """Number every H3 across the plan: box #1..#N in plan order."""
    boxes, n = [], 0
    for sec in plan["sections"]:
        for h in sec["h3s"]:
            n += 1
            boxes.append({"n": n, "h2": sec["h2"], "h3": h["h3"], "tags": h.get("tags", []),
                          "card_ids": h.get("card_ids", [])})
    return boxes


def _gloss(idx, cid):
    c = idx.get(C.nid(cid)) or {}
    return (c.get("gloss") or c.get("verbatim") or "").strip().replace("\n", " ")


def _boxes_block(boxes, idx, with_cards="gloss"):
    """The material block. with_cards: 'gloss' (structure calls) or 'full' (detector/filter calls).
    The "serves:" line (which research promise a box carries) is deliberately absent: knowing a box was
    bought to fill a promise biases the architect into placing it rather than judging it."""
    lines, cur_h2 = [], None
    for b in boxes:
        if b["h2"] != cur_h2:
            cur_h2 = b["h2"]
            lines.append('\nH2: "%s"' % cur_h2)
        lines.append("  [#%d] %s   (%d cards)" % (b["n"], b["h3"], len(b["card_ids"])))
        for cid in b["card_ids"]:
            g = _gloss(idx, cid)
            if not g:
                continue
            if with_cards == "full":
                v = ((idx.get(C.nid(cid)) or {}).get("verbatim") or "").strip().replace("\n", " ")[:200]
                lines.append("      - %s" % g + (" — " + v if v and v != g else ""))
            else:
                lines.append("      - %s" % g)
    return "\n".join(lines).strip()


def budget_maths(word_band):
    """ONE BUDGET FOR BOTH STEPS. shape sizes its ceiling from the same number allocate divides up.

    budget      = the band's midpoint, cut by ARCH_BAND_SHRINK (every section of a real run overshot)
    sec_target  = a CEILING on sections: budget / WORDS_PER_SECTION, never below 4
    w_para      = WORDS_PER_SENTENCE x SENTENCES_PER_PARAGRAPH
    paras/sec   = WORDS_PER_SECTION / w_para;  paras/subhead = MIN_WORDS_PER_SUBHEAD / w_para
    """
    band = word_band or {}
    budget = int(((band.get("min") or 0) + (band.get("max") or 0)) / 2) or 1500
    budget = max(1, round(budget * (1 - C.ARCH_BAND_SHRINK)))
    sec_target = max(4, round(budget / C.WORDS_PER_SECTION))
    w_para = C.WORDS_PER_SENTENCE * C.SENTENCES_PER_PARAGRAPH
    return {"budget": budget, "section_target": sec_target, "words_per_paragraph": w_para,
            "paragraphs_per_section": max(1, round(C.WORDS_PER_SECTION / w_para)),
            "paragraphs_per_subhead": max(1, round(C.MIN_WORDS_PER_SUBHEAD / w_para))}


def listicle_budget(budget, n_items):
    """FIT THE LIST TO THE BUDGET: supporting sections are reserved first, the rest is divided by items."""
    reserve = C.LISTICLE_SUPPORTING_SECTIONS * C.WORDS_PER_SECTION
    item_budget = max(0, budget - reserve)
    fits = item_budget // C.LISTICLE_MIN_ITEM_WORDS if C.LISTICLE_MIN_ITEM_WORDS else n_items
    return {"reserve": reserve, "item_budget": item_budget, "fits": fits,
            "expected_drops": max(0, n_items - max(fits, C.LISTICLE_MIN_ITEMS)) if n_items and fits < n_items else 0}


def run(plan, idx, ctx, say=lambda *a: None):
    brand = C.company()
    arch = plan["format_archetype"]
    fmt_structure = C.format_rules(arch)
    boxes = mint_boxes(plan)
    bymap = {b["n"]: b for b in boxes}
    maths = budget_maths(plan.get("word_band"))
    say("Laying out the material", "%d boxes of facts, format %s, room for %d sections in about %d words"
        % (len(boxes), arch, maths["section_target"], maths["budget"]))

    common = {"WORD_BUDGET": "{:,}".format(maths["budget"]), "SECTION_TARGET": maths["section_target"],
              "WORDS_PER_SENTENCE": C.WORDS_PER_SENTENCE,
              "SENTENCES_PER_PARAGRAPH": C.SENTENCES_PER_PARAGRAPH,
              "WORDS_PER_PARAGRAPH": maths["words_per_paragraph"],
              "WORDS_PER_SECTION": C.WORDS_PER_SECTION,
              "PARAGRAPHS_PER_SECTION": maths["paragraphs_per_section"],
              "MIN_WORDS_PER_SUBHEAD": C.MIN_WORDS_PER_SUBHEAD,
              "PARAGRAPHS_PER_SUBHEAD": maths["paragraphs_per_subhead"],
              "TITLE": ctx["title"] or "(none)", "ANGLE": ctx["angle"] or "(none)", "H1": plan.get("h1", ""),
              "FORMAT_STRUCTURE": fmt_structure,
              "WORLD_ABOUT": C.or_na(ctx, "about"), "WORLD_NOT_ABOUT": C.or_na(ctx, "not_about"),
              "PERSONA": ctx["persona"],
              "INTENT": plan.get("search_intent") or "(not recorded for this article)",
              "AI_OVERVIEW": plan.get("ai_overview") or "(Google shows no AI Overview for this query)",
              "TABLE_STAKES": "\n".join("  %d. %s" % (i, x) for i, x in
                                        enumerate(plan.get("table_stakes") or [], 1)) or "  (none found)",
              "THE_GAP": "\n".join("  - %s" % x for x in (plan.get("gaps_to_own") or [])) or "  (none found)",
              "BRAND": brand["brand"], "ABOUT": brand["about"], "MEMORY": C.sh.memory_block()}
    entities, yardsticks, work = [], [], {"maths": maths}
    pre = {k: common[k] for k in ("BRAND", "ABOUT", "TITLE", "ANGLE", "WORLD_ABOUT", "WORLD_NOT_ABOUT", "PERSONA")}

    if arch == "comparison-rankings":
        mat_full = _boxes_block(boxes, idx, "full")
        got = llm.json_call(C.prompt("detect-entities", **pre, material=mat_full)) or {}
        cand = [e for e in got.get("entities", []) if isinstance(e, dict) and e.get("name")]
        work["detected_entities"] = cand
        say("Found the options being compared", ", ".join(e["name"] for e in cand) or "none")
        ents = "\n".join("- %s" % e["name"] for e in cand) or "(none)"
        got = llm.json_call(C.prompt("find-yardsticks", **pre, entities=ents, material=mat_full)) or {}
        yardsticks = [str(y) for y in got.get("yardsticks", [])][:6]
        work["yardsticks"] = yardsticks
        got = llm.json_call(C.prompt("filter-tools", **pre, entities=ents,
                                     yardsticks="\n".join("- %s" % y for y in yardsticks), pages_note="",
                                     material=mat_full, min_pct=C.SHAPE_MIN_YARDSTICK_PCT)) or {}
        work["filtered_tools"] = got
        entities = [e["name"] for e in got.get("keep", []) if isinstance(e, dict) and e.get("name")]
        dropped = [e.get("name") for e in got.get("dropped", []) if isinstance(e, dict) and e.get("name")]
        category = str(got.get("category") or "").strip() or "(not stated)"
        say("Kept the options with enough material", "%d kept, %d dropped" % (len(entities), len(dropped)))
        ent_lines = []
        for e in got.get("keep", []):
            if not (isinstance(e, dict) and e.get("name")):
                continue
            cov = [str(y) for y in (e.get("yardsticks_covered") or [])]
            missing = [y for y in yardsticks if y not in cov]
            ent_lines.append("- %s" % e["name"] + ("   MISSING INFORMATION ON: %s" % ", ".join(missing) if missing else ""))
        sp = C.prompt("structure-comparison", **common, boxes=_boxes_block(boxes, idx), category=category,
                      entities="\n".join(ent_lines) or "(none)",
                      dropped="\n".join("- %s" % d for d in dropped) or "(none were removed)",
                      yardsticks="\n".join("- %s" % y for y in yardsticks) or "(none)")
    elif arch == "listicle":
        got = llm.json_call(C.prompt("detect-items", **pre, max_items=C.LISTICLE_MAX_ITEMS,
                                     material=_boxes_block(boxes, idx, "full"))) or {}
        cand = [e for e in got.get("entities", []) if isinstance(e, dict) and e.get("name")][:C.LISTICLE_MAX_ITEMS]
        work["detected_items"] = cand
        entities = [e["name"] for e in cand]
        lb = listicle_budget(maths["budget"], len(entities))
        work["listicle_budget"] = lb
        say("Found the list items", "%d of %d allowed; room for about %d at %d words each"
            % (len(entities), C.LISTICLE_MAX_ITEMS, lb["fits"], C.LISTICLE_MIN_ITEM_WORDS))
        sp = C.prompt("structure-listicle", **common, boxes=_boxes_block(boxes, idx),
                      supporting_reserve="{:,}".format(lb["reserve"]), supporting_max=C.LISTICLE_SUPPORTING_SECTIONS,
                      min_item_words=C.LISTICLE_MIN_ITEM_WORDS, min_items=C.LISTICLE_MIN_ITEMS,
                      entities="\n".join("- %s   (%s cards)" % (e["name"], e.get("count") or 0) for e in cand) or "(none)")
    elif arch == "template-resource":
        sp = C.prompt("structure-template", **common, boxes=_boxes_block(boxes, idx))
    else:                                   # the simple road (incl. data-report, glossary, common-spine)
        sp = C.prompt("structure-simple", **common, boxes=_boxes_block(boxes, idx))

    say("Designing the sections", "one call over every box")
    out = llm.json_call(sp) or {}
    work["structure_reply"] = out

    # --- validate + assemble ------------------------------------------------
    used, shared, sections, bad_dest = set(), [], [], []

    def _claim(raw, seen_here):
        """Box numbers from one answer slot. Drops non-numbers, unknown boxes, and any box already
        claimed elsewhere in THIS section (a box belongs in exactly one place inside a section)."""
        nums = []
        for x in raw or []:
            try:
                n = int(x)
            except (TypeError, ValueError):
                continue
            if n not in bymap or n in seen_here:
                continue
            seen_here.add(n)
            nums.append(n)
            if n in used:
                shared.append(n)
            used.add(n)
        return nums

    def _group(title, nums, is_lead=False):
        cards, tags_, from_h2, labels = [], [], "", []
        for n in nums:
            cards += bymap[n]["card_ids"]
            tags_ += [t for t in bymap[n]["tags"] if t not in tags_]
            labels.append(bymap[n]["h3"])
            from_h2 = from_h2 or bymap[n]["h2"]
        g = {"h3": title, "boxes": nums, "box_labels": labels, "from_h2": from_h2, "tags": tags_, "card_ids": cards}
        if is_lead:
            g["is_lead"] = True
        return g

    for s in out.get("sections", []) if isinstance(out.get("sections"), list) else []:
        if not isinstance(s, dict):
            continue
        head = str(s.get("headline") or "").strip() or "(headline missing)"
        seen_here = set()
        answered_new = ("lead_boxes" in s) or bool(s.get("h3s"))
        lead_nums = _claim(s.get("lead_boxes") if answered_new else s.get("boxes"), seen_here)
        h3s = []
        for h in (s.get("h3s") or []):
            if not isinstance(h, dict):
                continue
            title = str(h.get("h3") or "").strip()
            hn = _claim(h.get("boxes"), seen_here)
            if not title:                      # an H3 with no title is not a heading; fold its boxes up
                lead_nums += hn
                continue
            h3s.append(_group(title, hn))
        titles = {h["h3"] for h in h3s}
        nr = []
        for x in (s.get("needs_research") or []):
            if isinstance(x, str):
                topic, dest = x.strip(), "opening"
            elif isinstance(x, dict):
                topic, dest = str(x.get("topic") or "").strip(), str(x.get("goes_to") or "").strip()
            else:
                continue
            if not topic:
                continue
            if dest not in titles and dest.lower() != "opening":
                if dest:
                    bad_dest.append((head, dest))
                dest = "opening"
            nr.append({"topic": topic, "goes_to": dest})
        tbl = s.get("table") if isinstance(s.get("table"), dict) else None
        cols = [str(c).strip() for c in ((tbl or {}).get("columns") or []) if str(c).strip()]
        lst = s.get("list") if isinstance(s.get("list"), dict) else None
        kind = str((lst or {}).get("kind") or "").strip().lower()
        kind = kind if kind in ("numbered", "bulleted") else ""
        sections.append({
            "headline": head,
            "covers": str(s.get("covers") or "").strip() or None,
            "job": str(s.get("job") or "").strip(),
            "is_item": bool(s.get("is_item")),
            "boxes": lead_nums + [n for h in h3s for n in h["boxes"]],
            "table": {"columns": cols} if len(cols) >= 2 else None,
            "list": {"kind": kind, "of": str((lst or {}).get("of") or "").strip()} if kind else None,
            "needs_research": nr,
            "lead": _group("", lead_nums, is_lead=True),
            "h3s": h3s,
        })
    bench_why = {}
    for b in out.get("benched") or []:
        try:
            bench_why[int(b.get("box"))] = str(b.get("why") or "").strip()
        except (TypeError, ValueError, AttributeError):
            continue
    if not sections:
        raise ValueError("the structure call returned no sections")
    unused = [b for b in boxes if b["n"] not in used]
    item_fields = [str(x).strip() for x in (out.get("item_fields") or []) if str(x).strip()][:4]
    dropped_items = [{"item": str(d.get("item") or "").strip(), "why": str(d.get("why") or "").strip()}
                     for d in (out.get("dropped_items") or []) if isinstance(d, dict) and str(d.get("item") or "").strip()]
    result = {"format_archetype": arch, "spine": str(out.get("spine") or "").strip(),
              "coverage_note": str(out.get("coverage_note") or "").strip(),
              "item_fields": item_fields, "dropped_items": dropped_items,
              "sections": sections, "entities": entities, "yardsticks": yardsticks,
              "artifact": out.get("artifact") if isinstance(out.get("artifact"), dict) else None,
              "unused_boxes": [{"n": b["n"], "h3": b["h3"], "from_h2": b["h2"], "cards": len(b["card_ids"]),
                                "serves": b["tags"], "why_benched": bench_why.get(b["n"], "")} for b in unused],
              "shared_box_warnings": sorted(set(shared)),
              "bad_research_destinations": [{"section": h, "asked": d} for h, d in bad_dest],
              "word_budget_maths": maths, "h1": plan.get("h1", "")}
    coverage, reopened = compute_coverage(sections, plan)
    result["coverage"] = coverage
    result["reopened_holes"] = reopened
    n_h3 = sum(len(s["h3s"]) for s in sections)
    say("Structure designed", "%d sections, %d sub-headings, %d of %d boxes used, %d research requests"
        % (len(sections), n_h3, len(used), len(boxes), sum(len(s["needs_research"]) for s in sections)))
    if bad_dest:
        say("Some research requests named a sub-heading that does not exist",
            "%d sent to the section's opening instead" % len(bad_dest))
    return {"structure": result, "work": work}


def groups(sec):
    """Every card-carrying group in a section: the lead (the prose above the first H3) then each H3."""
    lead = sec.get("lead")
    return ([lead] if lead else []) + list(sec.get("h3s") or [])


def covers(sec):
    """One line describing what a section covers: the authored H3s, else the box labels."""
    h3s = [h.get("h3", "") for h in (sec.get("h3s") or []) if h.get("h3")]
    if h3s:
        return " · ".join(h3s)
    labels = [l for g in groups(sec) for l in (g.get("box_labels") or []) if l]
    return " · ".join(labels) or "(no sub-topics)"


def compute_coverage(sections, plan):
    """Promise coverage over the boxes actually placed. Returns (coverage dict, reopened list)."""
    served = {t for s in sections for h in groups(s) for t in h.get("tags", [])}
    coverage, reopened = {}, []
    for kind, key, label in [("gap", "gaps_to_own", "Gaps"), ("common-h2", "winners_common_h2s", "Table-stakes"),
                             ("paa", "paa_pool", "PAA questions")]:
        items = plan.get(key) or []
        holes = [x for x in items if "%s: %s" % (kind, x) not in served]
        coverage[label] = "%d/%d" % (len(items) - len(holes), len(items))
        for h in holes:
            reopened.append("%s: %s" % (label, h[:70]))
    return coverage, reopened
