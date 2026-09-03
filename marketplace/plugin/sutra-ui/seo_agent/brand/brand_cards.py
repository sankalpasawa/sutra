"""brand/brand_cards.py — builder 10: the company's own material as cards.

Port of 8-brand-cards/scripts/run_brand_cards.py. Two sources, kept apart all the way through
because downstream they are rationed differently:

  RESEARCH = the company's own study in stats.md (a `## ` block with `### ` questions under it):
             neutral data about its market. A model per batch of sections decides WHICH rows are
             worth a sentence (a judgment); code mints the ids and checks every card.
  RESULTS  = what a named customer achieved, parsed from stories.md. DETERMINISTIC: the file has a
             fixed per-entry shape, so this is parsing, not judgment. No model.

Card ids live in reserved bands so a card's origin is readable from its number alone:
  1..999 research cards from an article's own gathering · 8001+ THIS builder · 9001+ the architect.

Reads:  brand/stats.md · brand/stories.md
Writes: brand/_work/brand-cards/{results.json, research.json} · brand/brand-cards.json
"""
import re

from .. import llm
from .. import store
from . import _common as cm

OUTPUT = "brand-cards.json"
WORK = "_work/brand-cards/"
RESEARCH_MD = "stats.md"
RESULTS_MD = "stories.md"
ID_BASE = 8001
BC_BATCH = 3                # research sections per extraction call
_NUM = re.compile(r"\d")


# ---- step 1: customer results (deterministic) --------------------------------------------------

def results_cards(say):
    text = cm.read(RESULTS_MD)
    if not text.strip():
        say("No stories.md", "customer results skipped")
        return []
    # Entries are "### <title>" followed by a prose paragraph and three labelled lines.
    blocks = re.split(r"^### ", text, flags=re.M)[1:]
    out, skipped = [], 0
    for b in blocks:
        lines = b.strip().splitlines()
        title = lines[0].strip()
        if title.startswith("<"):                          # the template's own "how to add one" example
            continue
        body = "\n".join(lines[1:])
        story = "\n".join(l for l in lines[1:] if l.strip() and not l.strip().startswith("-")).strip()

        def field(label):
            m = re.search(r"^-\s*%s\s*:\s*(.+)$" % label, body, flags=re.M | re.I)
            return m.group(1).strip() if m else ""

        point, number, source = field("Point it makes"), field(r"Number \(if any\)"), field(r"Source(?: / approved by)?")
        um = re.search(r"https?://\S+", source)
        url = um.group(0).rstrip(").,") if um else ""
        if not story or not url:
            skipped += 1
            continue
        unconfirmed = "⚠️" in title
        out.append({"gloss": point or title.replace("⚠️", "").strip(),
                    "verbatim": ("%s. %s" % (title.replace("⚠️", "").strip(), story)).strip(),
                    "number": number, "source_urls": [url], "tag": "brand-result", "confirmed": not unconfirmed})
    cm.save(WORK + "results.json", out)
    say("Parsed the customer results", "%d entries%s" % (len(out), ("; %d skipped (no story text or no source URL)" % skipped) if skipped else ""))
    return out


# ---- step 2: the research study (model per batch) -----------------------------------------------

def split_study(text):
    """(header, [question sections]). A QUESTION SECTION is a `## ` block that has `### ` questions
    under it. Everything before the first of those is the header: the study's name, date, base and
    caveats. Splitting on the first `## ` instead loses all of that, because the study's own
    description usually sits under a `## ` of its own."""
    starts = [m.start() for m in re.finditer(r"^## ", text, flags=re.M)] + [len(text)]
    header_end, sections = len(text), []
    for i in range(len(starts) - 1):
        block = text[starts[i]:starts[i + 1]]
        if re.search(r"^### ", block, flags=re.M):
            if not sections:
                header_end = starts[i]
            sections.append(block.rstrip())
    return text[:header_end].strip(), sections


def citation(header):
    """The study's own name, taken from the first bold run in the header. In stats.md the header also
    carries the template's own `> **Rule:**` line, so the study's own `## ` block (the last one in the
    header) is searched first and the whole header only as a fallback."""
    blocks = re.split(r"^## ", header, flags=re.M)
    for chunk in ([blocks[-1]] if len(blocks) > 1 else []) + [header]:
        m = re.search(r"\*\*(.+?)\*\*", chunk, flags=re.S)
        if m and m.group(1).strip().rstrip(":").lower() != "rule":
            return m.group(1).strip().rstrip(".")
    return ""


def research_cards(co, say, research_url):
    text = cm.read(RESEARCH_MD)
    if not text.strip():
        say("No stats.md", "research skipped")
        return []
    header, sections = split_study(text)
    if not sections:
        say("No research study in stats.md", "no `## ` block with `### ` questions under it; the stat tables are company proof, not a study, so research cards are skipped")
        return []
    cite = citation(header)
    if not cite:
        say("No study name in the header", "expected a **bold** title; cards will carry no citation")
    batches = ["\n\n".join(sections[i:i + BC_BATCH]) for i in range(0, len(sections), BC_BATCH)]
    tpl = cm.prompt("extract-research-cards")

    def one(chunk):
        r = llm.json_call(cm.fill(tpl, brand=co["brand"], niche=co.get("niche_definition") or "",
                                  study_header=header, content=chunk))
        return (r or {}).get("findings") or [] if isinstance(r, dict) else []

    found = []
    for _b, res, err in cm.parallel(one, batches, say, "Extracting findings", every=1):   # source order kept
        if err:
            say("A batch of the study could not be read", str(err)[:80])
        else:
            found += [f for f in res if isinstance(f, dict)]
    out = []
    for f in found:
        v = str(f.get("verbatim") or "").strip()
        if not v:
            continue
        out.append({"gloss": str(f.get("gloss") or "").strip() or v[:90], "verbatim": v,
                    "topics": [str(t).strip().lower() for t in (f.get("topics") or []) if str(t).strip()],
                    "source_note": cite, "source_urls": [research_url] if research_url else [],
                    "tag": "brand-research"})
    cm.save(WORK + "research.json", out)
    say("Extracted the research findings", "%d from %d sections" % (len(out), len(sections)))
    return out


# ---- step 3: mint ids and write the pool --------------------------------------------------------

def build(co, research, results, research_url, say):
    cards, cid = {"research": [], "results": []}, ID_BASE
    for c in research:
        cards["research"].append(dict(c, id=cid, card_id=cid))
        cid += 1
    for c in results:
        cards["results"].append(dict(c, id=cid, card_id=cid))
        cid += 1
    # VERIFY, DON'T TRUST. A card with no digit in it carries no finding, and a research card with no
    # base cannot be quoted honestly: both are surfaced rather than shipped quietly.
    no_number = [c["id"] for c in cards["research"] if not _NUM.search(c["verbatim"])]
    no_base = [c["id"] for c in cards["research"] if "n=" not in c["verbatim"].lower()]
    no_source = [c["id"] for c in cards["results"] if not c.get("source_urls")]
    unconfirmed = [c["id"] for c in cards["results"] if not c.get("confirmed", True)]
    pool = {"brand": co["brand"], "id_base": ID_BASE, "next_free_id": cid,
            "research_source": (research[0].get("source_note") if research else ""),
            "research_url": research_url,
            "counts": {"research": len(cards["research"]), "results": len(cards["results"])},
            "warnings": {"no_number": no_number, "no_base": no_base, "no_source": no_source, "unconfirmed_results": unconfirmed},
            "research": cards["research"], "results": cards["results"]}
    cm.save(OUTPUT, pool)
    say("Minted the card ids", "ids %d..%d: %d research, %d results" % (ID_BASE, cid - 1, len(cards["research"]), len(cards["results"])))
    notes = []
    if no_number:
        notes.append("brand-cards.json: %d research cards carry no number (%s)" % (len(no_number), no_number[:6]))
    if no_base:
        notes.append("brand-cards.json: %d research cards carry no (n=…) base (%s)" % (len(no_base), no_base[:6]))
    if no_source:
        notes.append("brand-cards.json: %d customer results carry no source URL" % len(no_source))
    if unconfirmed:
        notes.append("brand-cards.json: %d result cards come from ⚠️ unconfirmed stories" % len(unconfirmed))
    if research and not research_url:
        say("The research is unpublished", "cards carry a written citation and no link; set research_url in the company record once it has a public home")
    return pool, notes


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept brand-cards.json", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT], "needs_review": []}
    if not cm.exists(RESEARCH_MD) and not cm.exists(RESULTS_MD):
        raise RuntimeError("Neither stats.md nor stories.md exists yet; the brand-facts step comes first.")
    rec = store.knowledge("brand/company.json") or {}
    research_url = str(rec.get("research_url") or "").strip()      # empty = unpublished; never invent a URL
    results = results_cards(say)
    research = research_cards(co, say, research_url)
    _pool, notes = build(co, research, results, research_url, say)
    return {"files": [OUTPUT], "needs_review": notes}
