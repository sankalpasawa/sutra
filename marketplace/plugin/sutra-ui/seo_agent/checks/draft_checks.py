"""draft_checks.py — the last gate before a human reads the article.

Two of these earn the file on their own.

The targeted-edit check is the promise the editor makes. Someone asks for one paragraph to
change, and the only honest way to say "nothing else moved" is to compare every other block
and count. Without it, "nothing was lost" is a claim rather than a fact, and a model that
quietly reworded three paragraphs looks exactly like one that behaved.

The orphaned-reference check is the sneaky one. Delete a section and the article still says
"as we covered earlier" four paragraphs later. Nothing errors. No link breaks. It simply
reads as broken to the first person who gets there, which is usually a reader rather than
the writer.

Everything statistical stays at warn, per the rule in checks/__init__.py. Only a fault that
can be proved from data already on disk says fail.
"""
import concurrent.futures
import re

from . import (ai_writing, artifact, is_same_site, item, norm_url,
                    primary_keyword, result, site_index, site_urls)

LINK_TIMEOUT = 5.0            # seconds per external link, checked concurrently
LINK_WORKERS = 8
KEYWORD_MIN = 0.004           # 0.4% — below this the article is not really about it
KEYWORD_MAX = 0.025           # 2.5% — above this it reads as stuffed
CLAIM_WINDOW = 320            # chars either side of a number to look for a citation

MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)

# Phrases that only make sense if something they point at actually exists.
BACKREF = re.compile(
    r"\b(as (?:we )?(?:discussed|covered|mentioned|saw|noted) (?:above|earlier|previously)"
    r"|as (?:noted|mentioned) (?:above|earlier)"
    r"|in the (?:previous|preceding|last) section"
    r"|earlier in this (?:article|piece|guide))\b", re.I)
FORWARDREF = re.compile(
    r"\b(as (?:we(?:'ll| will)? )?(?:see|cover|discuss|explore) below"
    r"|in the (?:next|following) section"
    r"|below,? we(?:'ll| will)?"
    r"|later in this (?:article|piece|guide))\b", re.I)

# A sentence that already says where its number came from. Deliberately narrow: the bare
# word "source" used to excuse any claim, which meant "with no source in sight" counted as
# cited. An attribution names somebody, so that is what this looks for.
CITED = re.compile(
    r"\b(according to|per (?:the |a )?\w+|cited (?:in|by)|reported by|"
    r"source:|sources:|\(source\b|survey by|study by|research by|data from)\b", re.I)

# A sentence carrying one of these is making a claim a reader may want to check.
HAS_NUMBER = re.compile(r"(\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s?%|\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\s?(?:x|times)\b)")


# ---- reading the draft -------------------------------------------------------------------

def blocks(md):
    """Paragraph blocks, the same unit editing/edit_block.py addresses. Ids must match, or
    a drift report would point at a block the user cannot find."""
    return (md or "").split("\n\n")


def prose(md):
    """The text a reader sees: no headings, no code, no link syntax."""
    text = re.sub(r"```.*?```", " ", md or "", flags=re.S)
    text = HEADING.sub(" ", text)
    text = MD_LINK.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def links(md):
    return [(m.group(1), m.group(2)) for m in MD_LINK.finditer(md or "")]


def headings(md):
    return [(len(m.group(1)), m.group(2).strip()) for m in HEADING.finditer(md or "")]


def where_in(md, needle):
    """Which paragraph a string sits in, so a finding can point somewhere real."""
    for i, b in enumerate(blocks(md)):
        if needle and needle in b:
            return "paragraph %d" % (i + 1)
    return "the draft"


# ---- 1. only the targeted block changed ---------------------------------------------------

def check_only_target_changed(md, previous):
    if not previous:
        return result("only_targeted_block_changed", "pass",
                      "Nothing to compare against, so there is nothing to prove.")
    old, new = blocks(previous), blocks(md)
    if len(old) != len(new):
        return result("only_targeted_block_changed", "fail",
                      "The number of paragraphs changed, %d to %d. An edit should leave the "
                      "count alone, or every later paragraph now means something different."
                      % (len(old), len(new)))
    moved = [i for i in range(len(old)) if old[i] != new[i]]
    if len(moved) <= 1:
        return result("only_targeted_block_changed", "pass",
                      "One paragraph changed. Every other one is byte-identical.")
    return result("only_targeted_block_changed", "fail",
                  "%d paragraphs changed when one was meant to." % len(moved),
                  [item("paragraph %d" % (i + 1), old[i].strip()[:120],
                        "Restore this paragraph. Only the one you asked about should move.")
                   for i in moved])


# ---- 2. internal links point at pages that exist -------------------------------------------

def check_internal_links(md, ctx):
    idx = site_index(ctx) or {}
    domain = idx.get("domain")
    known = site_urls(ctx)
    if not known:
        return result("internal_links_resolve", "warn",
                      "No site index on file, so internal links cannot be verified.")
    bad = []
    checked = 0
    for anchor, url in links(md):
        if not is_same_site(url, domain):
            continue
        checked += 1
        if norm_url(url, domain) not in known:
            bad.append(item(where_in(md, url), url,
                            "Not a page in the site index. Link to a real page or drop it."))
    if not checked:
        return result("internal_links_resolve", "pass", "No internal links to check.")
    if bad:
        return result("internal_links_resolve", "fail",
                      "%d of %d internal links point at pages that do not exist."
                      % (len(bad), checked), bad)
    return result("internal_links_resolve", "pass",
                  "All %d internal links resolve to real pages." % checked)


# ---- 3. external links are alive ----------------------------------------------------------

def _alive(url):
    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=LINK_TIMEOUT) as c:
            r = c.head(url)
            if r.status_code >= 400:          # some hosts refuse HEAD but serve GET
                r = c.get(url)
            return url, r.status_code
    except Exception as e:
        return url, str(e)[:60]


def check_external_links(md, ctx):
    idx = site_index(ctx) or {}
    domain = idx.get("domain")
    urls = sorted({u for _, u in links(md)
                   if u.startswith("http") and not is_same_site(u, domain)})
    if not urls:
        return result("external_links_alive", "pass", "No external links to check.")
    bad = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=LINK_WORKERS) as ex:
        for url, status in ex.map(_alive, urls):
            if status != 200:
                bad.append(item(where_in(md, url), url,
                                "Returned %s. Check it, or cite something else." % status))
    if bad:
        # Never fail on this. A slow host or a bot-blocker is not a fault in the writing.
        return result("external_links_alive", "warn",
                      "%d of %d external links did not answer cleanly." % (len(bad), len(urls)), bad)
    return result("external_links_alive", "pass", "All %d external links answered." % len(urls))


# ---- 4. no orphaned cross-references -------------------------------------------------------

def check_orphaned_references(md):
    heads = headings(md)
    body_blocks = blocks(md)
    found = []
    for i, block in enumerate(body_blocks):
        if HEADING.match(block.strip()):
            continue
        heads_before = sum(1 for h in HEADING.finditer("\n\n".join(body_blocks[:i])))
        heads_after = len(heads) - heads_before
        for m in BACKREF.finditer(block):
            # A back-reference in the first section has nothing behind it to refer to.
            if heads_before <= 1:
                found.append(item("paragraph %d" % (i + 1), m.group(0),
                                  "Nothing comes before this to refer back to. Cut the phrase "
                                  "or move the section it points at."))
        for m in FORWARDREF.finditer(block):
            if heads_after <= 0:
                found.append(item("paragraph %d" % (i + 1), m.group(0),
                                  "Nothing comes after this. Cut the phrase or add the section "
                                  "it promises."))
    if found:
        return result("no_orphaned_references", "warn",
                      "%d cross-reference(s) point at a section that is not there." % len(found),
                      found)
    return result("no_orphaned_references", "pass",
                  "Every 'as we covered' has something to refer to.")


# ---- 5. the primary keyword is present, and not stuffed ------------------------------------

def check_keyword(md, ctx):
    kw = primary_keyword(ctx)
    if not kw:
        return result("keyword_present", "pass",
                      "No primary keyword on record, so there is nothing to measure.")
    text = prose(md).lower()
    words = max(len(text.split()), 1)
    hits = len(re.findall(re.escape(kw.lower()), text))
    if hits == 0:
        return result("keyword_present", "fail",
                      "The primary keyword '%s' does not appear in the draft." % kw,
                      [item("the draft", kw, "Work it into the opening and at least one heading.")])
    density = (hits * len(kw.split())) / words
    pct = round(density * 100, 2)
    if density < KEYWORD_MIN:
        return result("keyword_present", "warn",
                      "'%s' appears %d time(s), %.2f%%. Thin for the primary keyword."
                      % (kw, hits, pct))
    if density > KEYWORD_MAX:
        return result("keyword_present", "warn",
                      "'%s' appears %d time(s), %.2f%%. That reads as stuffed."
                      % (kw, hits, pct))
    return result("keyword_present", "pass",
                  "'%s' appears %d time(s), %.2f%%." % (kw, hits, pct))


# ---- 6. claims carry a source ---------------------------------------------------------------

def check_claims_have_sources(md):
    naked = []
    for i, block in enumerate(blocks(md)):
        if HEADING.match(block.strip()):
            continue
        has_link = bool(MD_LINK.search(block))
        for s in sentences(block):
            m = HAS_NUMBER.search(s)
            if not m:
                continue
            if has_link or CITED.search(s):
                continue
            naked.append(item("paragraph %d" % (i + 1), s.strip()[:140],
                              "Cite where %s came from, or cut the number." % m.group(0)))
    if naked:
        return result("claims_have_sources", "warn",
                      "%d claim(s) carry a number with nothing to check it against." % len(naked),
                      naked[:12])
    return result("claims_have_sources", "pass", "Every number has a source nearby.")


# ---- 7. heading structure -------------------------------------------------------------------

def check_heading_structure(md, ctx):
    heads = headings(md)
    if not heads:
        return result("heading_structure", "fail", "The draft has no headings at all.")
    h1s = [h for h in heads if h[0] == 1]
    if len(h1s) != 1:
        return result("heading_structure", "fail",
                      "An article needs exactly one H1. This one has %d." % len(h1s),
                      [item("the draft", t, "Demote it to H2, or make it the title.")
                       for _, t in h1s[1:]])
    if heads[0][0] != 1:
        return result("heading_structure", "fail", "The draft does not open with its H1.")

    skips = []
    prev = heads[0][0]
    for level, title in heads[1:]:
        if level > prev + 1:
            skips.append(item(title, "H%d after H%d" % (level, prev),
                              "Use H%d, or add the level in between." % (prev + 1)))
        prev = level
    if skips:
        return result("heading_structure", "warn",
                      "%d heading(s) skip a level." % len(skips), skips)

    bp = artifact(ctx, "blueprint.json") or {}
    planned = [s.get("heading", "").strip().lower()
               for s in (bp.get("sections") or []) if s.get("heading")]
    if planned:
        written = {t.strip().lower() for _, t in heads}
        missing = [p for p in planned if p not in written]
        if missing:
            return result("heading_structure", "warn",
                          "%d planned section(s) are not in the draft." % len(missing),
                          [item("the draft", p, "Write it, or drop it from the blueprint.")
                           for p in missing])
    return result("heading_structure", "pass",
                  "One H1, %d headings, no skipped levels." % len(heads))


# ---- the door -------------------------------------------------------------------------------

def run(md, previous=None, ctx=None):
    ctx = ctx or {}
    voice = None
    try:
        from . import brand_voice
        voice = brand_voice(ctx)
    except Exception:
        pass
    return [
        check_only_target_changed(md, previous),
        check_heading_structure(md, ctx),
        check_internal_links(md, ctx),
        check_external_links(md, ctx),
        check_orphaned_references(md),
        check_keyword(md, ctx),
        check_claims_have_sources(md),
        ai_writing.check(md, voice=voice),
    ]
