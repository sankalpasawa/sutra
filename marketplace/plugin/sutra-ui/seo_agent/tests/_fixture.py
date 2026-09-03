"""tests/_fixture.py — what every suite does before it touches the package.

Three things, in one place so no suite drifts from the others. It puts the folder that
holds seo_agent/ on sys.path so a suite can be run as a plain file as well as with -m. It
points the data dir at a throwaway folder, so no test ever writes into a real install. And
it plants a small site index, because learn_voice refuses to run without one and the old
suites leaned on a real crawl that lived in the app's data/ folder.

The model stubs live here too. They match on the literal output keys each prompt asks for,
which is the only reliable signal, because prompts share vocabulary but never share their
output shape.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Four pages, shaped like index_site writes them. Enough text that learn_voice has prose
# to sample, and real-looking URLs so link candidates and the link checks have targets.
_PROSE = ("We build programmes for people who already run things. Every cohort is taught by "
          "practitioners, not lecturers, and every week ends with a decision made on real "
          "numbers. The work is direct. Short briefs, live cases, a room that argues back. "
          "Nobody leaves with a certificate they cannot explain. ") * 6

SITE_INDEX = {
    "domain": "example.com",
    "page_count": 4,
    "pages": [
        {"url": "https://example.com/", "title": "Example: education for operators",
         "description": "Practitioner-led programmes for founders and senior operators.",
         "h1": "Learn by running the numbers", "word_count": 240, "text": _PROSE,
         "top_keyword": "operator education", "position": 4, "keyword_volume": 900},
        {"url": "https://example.com/programmes", "title": "Programmes",
         "description": "Every programme we run, and who it is for.",
         "h1": "Programmes", "word_count": 210, "text": _PROSE,
         "top_keyword": "leadership programme", "position": 11, "keyword_volume": 1200},
        {"url": "https://example.com/blog/what-changes-after", "title": "What changes after a programme",
         "description": "The part nobody writes about: the six months after.",
         "h1": "What changes after", "word_count": 260, "text": _PROSE,
         "top_keyword": "after executive education", "position": 7, "keyword_volume": 300},
        {"url": "https://example.com/about", "title": "About", "description": "Who we are.",
         "h1": "About", "word_count": 190, "text": _PROSE,
         "top_keyword": None, "position": 0, "keyword_volume": 0},
    ],
    "indexed_at": "2026-01-01T00:00:00Z",
}


def setup():
    """Point the data dir at a temp folder and plant the site index. Returns the dir.

    SEO_AGENT_DATA wins when the runner set it, so all suites in one run share a folder
    the same way they shared data/ before. Otherwise each suite gets its own.
    """
    from seo_agent import store
    if not os.environ.get("SEO_AGENT_DATA", "").strip():
        os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="seo-agent-tests-")
    store.set_data_dir(os.environ["SEO_AGENT_DATA"])
    if not store.knowledge("site_index.json"):
        store.save_knowledge("site_index.json", SITE_INDEX)
    return store.data_dir()


# ---- the model stubs -----------------------------------------------------------------

def stub_json(prompt, system=None, retries=1):
    """Match on the literal output keys each prompt asks for. That is the only reliable
    signal, because prompts share vocabulary but never share their output shape."""
    p = prompt

    if '"competitors"' in p:
        return {"competitors": [{"domain": "rival-one.com", "why": "same programmes"},
                                {"domain": "rival-two.com", "why": "same buyers"},
                                {"domain": "rival-three.com", "why": "adjacent"}]}

    if '"topics"' in p:
        return {"topics": [{"id": "t%d" % i, "topic": "Topic number %d" % i,
                            "sparked_by": "rival keyword %d" % i,
                            "angle": "what they have not done, in a sentence",
                            "why_us": "it fits what we sell",
                            "est_volume": 400 + i * 90, "est_difficulty": 20 + i}
                           for i in range(1, 7)]}

    if '"what_they_all_cover"' in p:
        return {"what_they_all_cover": ["rankings", "fees", "eligibility", "placement", "alumni"],
                "the_gap": "Nobody writes about what actually changes for the leader afterwards.",
                "recommended_angle": "Lead with the outcome, not the curriculum."}

    if '"primary_keyword"' in p:
        return {"primary_keyword": "executive education india",
                "why": "Best volume against a difficulty we can realistically win.",
                "secondary_keywords": ["executive mba india", "leadership programmes india"]}

    if '"sections"' in p or '"meta_description"' in p:
        return {"title": "Executive Education in India, and What Changes After",
                "meta_description": "What actually changes for a leader after an executive programme.",
                "keyword_placement": "Primary in the H1 and the first paragraph.",
                "sections": [{"id": "s%d" % i, "heading": "Section %d heading" % i,
                              "covers": "what this section covers, in a sentence",
                              "words": 250, "internal_links": []} for i in range(1, 7)]}

    # learn_voice and anything else that describes the company
    return {"company": "Masters' Union", "what_they_sell": "practitioner-led business education",
            "who_buys": "founders, CHROs and senior operators",
            "summary": "Direct and concrete. Short sentences. No corporate padding.",
            "traits": ["direct", "concrete", "unfussy"],
            "avoid": ["delve", "leverage", "robust", "seamless"],
            "examples": ["We teach by doing.", "The classroom is the boardroom."]}


def stub_text(prompt, system=None):
    """Long enough that a written section looks like a real one."""
    return ("Executive programmes in India have grown quickly, and most of the coverage stops at "
            "rankings and fees. That leaves the question a buyer actually has unanswered.\n\n"
            "What changes after the programme is the part worth writing about. Decision speed, "
            "the quality of the bench below the founder, and whether a leader can hold a room.")
