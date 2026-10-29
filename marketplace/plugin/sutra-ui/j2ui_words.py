"""j2ui_words.py -- the words the J2 page says for a department (A5.1.4), the 57th key of api/state.

The page is the prototype's, written for a website team. A department of another kind sees the same page in neutral words:
each value here is the kind's own (layer_models.a5_words) with the department's name put in. Nothing is invented: a website
department gets the empty object (the page's own text stands), and a kind with no entry gets the fallback. The result is
checked as page.words once per read of the department (the caller keeps it in ctx.memo['state'], not per poll)."""
from layer_models.a5_words import kind_words

import layer_schema as S

WEBSITE = "website"


def _name(d):
    return " ".join(str((d or {}).get("name") or "").split())


def noun_of(kind):
    """The noun of a kind's work in the page's words ('site' for a website; 'work' for a kind with none)."""
    if kind == WEBSITE:
        return "site"
    return kind_words(kind).noun or "work"


def label_of(kind):
    """The capitalised noun of the kind: the page's output label ('Website' for a website)."""
    return "Website" if kind == WEBSITE else noun_of(kind).capitalize()


def words_for(dept):
    """The page.words of a department: {} for a website; else the kind's words with the department's name in, validated."""
    kind = (dept or {}).get("kind")
    if kind == WEBSITE:
        return {}
    out = kind_words(kind).model_dump(exclude_none=True)
    name = _name(dept) or "This department"
    noun = out.get("noun") or "work"
    out.update({
        "team": name[:80],
        "describe": "Describe what you want %s to do..." % name[:40],
        "describe_long": "Describe what you want %s to do, in your own words. It will ask for anything it needs to know." % name[:40],
        "start": "Tell %s what you need. It will ask for what it has to know, then get to work." % name[:40],
        "ready": "Your %s is ready" % noun,
        "examples": [], "follow_ups": []})
    S.check("page.words", out)
    return out
