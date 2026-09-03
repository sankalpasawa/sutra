"""enrich.py — Architect step 2: ENRICH. The research the structure asked for, and the safety net.

The original went out to the web for every needs_research marker: plan queries, DataForSEO organic
search, download pages, extract new cards (ids 9001+). That is a paid web search this agent does not
run, so this step does the honest thing instead: it records every marker as research that did not
happen, in the structure itself, where the writer reads it and where the report shows it.

WHAT STILL RUNS, because it protects the article regardless of where the material came from:
  THE SAFETY NET. The architect may create a sub-heading with no boxes and rely on research to fill it.
  With no research, that leaves a heading with nothing under it, so it is removed here and recorded.
  Also catches an empty sub-heading created by mistake.
  THE THIN FLAG. A section that asked for research and did not get it stays in the article thinner
  than it was designed to be. It is recorded as a research failure so write_body warns the writer not
  to pad, exactly as the original did for a marker that came back empty.
"""

SKIP_NOTE = "enrichment skipped: needs DataForSEO web search"


def run(shaped, say=lambda *a: None):
    markers = []
    for si, sec in enumerate(shaped["sections"]):
        for r in (sec.get("needs_research") or []):
            if isinstance(r, str):
                markers.append((si, r.strip(), "opening"))
            elif isinstance(r, dict) and str(r.get("topic") or "").strip():
                markers.append((si, str(r["topic"]).strip(), str(r.get("goes_to") or "opening").strip()))

    log = [{"section": shaped["sections"][si]["headline"], "h3": topic, "goes_to": dest,
            "status": SKIP_NOTE, "queries": [], "pages": []} for si, topic, dest in markers]
    if markers:
        say("Extra research requested but not run", "%d request(s): %s" % (len(markers), SKIP_NOTE))

    emptied = []
    for sec in shaped["sections"]:
        keep = []
        for h in sec.get("h3s") or []:
            if h.get("card_ids"):
                keep.append(h)
            else:
                emptied.append({"section": sec["headline"], "h3": h.get("h3", "")})
        sec["h3s"] = keep
    if emptied:
        shaped["empty_subheadings_removed"] = emptied
        say("Removed sub-headings with nothing under them", "%d" % len(emptied))

    failed = [{"section": x.get("section"), "h3": x.get("h3"), "status": x.get("status"),
               "queries": [], "pages_loaded": 0} for x in log]
    if failed:
        shaped["research_failures"] = failed
    shaped["enrichment"] = {"skipped": SKIP_NOTE if markers else "", "markers": len(markers), "log": log,
                            "new_cards": 0}
    return {"structure": shaped, "enriched_cards": {}, "log": log}
