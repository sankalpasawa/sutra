"""test_j2ui_words.py -- the words the J2 page says for a department (j2ui_words.py; A5.1.4).

Named claims:
  W-1  for every kind of the Library and for hostile names the words are a valid page.words
  W-2  a website gets the empty object; any other kind's words carry no website, PRD or document word, and no examples or follow-ups
  W-3  a kind with no entry gets the fallback; the name is trimmed and put in as given (the page escapes it)
  W-4  the words are read once per read of the department (ctx.memo['state']), not per poll
"""
import re

import pytest

from test_fixtures.j2ui.core_fixtures import mods  # noqa: F401 -- a fixture

import layer_schema as S
import website_dept as W
import j2ui_words as X
from layer_models.a5_words import FALLBACK_WORDS

HOSTILE = ("City Care", "<b>x</b>", "y" * 300, "", "  spaced   out  ")
BANNED = re.compile(r"website|\bsite\b|PRD|document|\bpage\b", re.I)


@pytest.mark.parametrize("kind", list(W.KINDS) + ["not-a-kind", None])
@pytest.mark.parametrize("name", HOSTILE)
def test_w1_every_kind_and_hostile_name_is_a_valid_page_words(kind, name):
    w = X.words_for({"kind": kind, "name": name})
    assert S.validate("page.words", w) == []


@pytest.mark.parametrize("kind", [k for k in W.KINDS if k != "website"])
def test_w2_a_neutral_kind_says_no_website_word(kind):
    w = X.words_for({"kind": kind, "name": "Ops"})
    assert w["examples"] == [] and w["follow_ups"] == []
    flat = " | ".join(str(v) for k, v in w.items() if k != "hide_tabs")
    assert not BANNED.search(flat), flat


def test_w2_a_website_gets_the_empty_object():
    assert X.words_for({"kind": "website", "name": "City Care"}) == {}
    assert X.label_of("website") == "Website" and X.noun_of("website") == "site"


def test_w3_unknown_kind_uses_the_fallback_and_the_name_is_put_in():
    w = X.words_for({"kind": "nope", "name": "<b>x</b>"})
    assert w["noun"] == FALLBACK_WORDS.noun == "work" and w["team"] == "<b>x</b>"
    assert len(X.words_for({"kind": "default", "name": "y" * 300})["team"]) == 80
    assert X.label_of("organic") == "Work" and X.label_of("default") == "Result" and X.label_of("zzz") == "Work"


def test_w4_the_words_are_built_once_per_read(mods, monkeypatch):
    import j2ui_common as C
    import j2ui_state
    ref = "dref-w4"
    mods.W.create(ref, "Ops", None, kind="default")
    n = []
    real = X.words_for
    monkeypatch.setattr(X, "words_for", lambda d: n.append(1) or real(d))
    ctx = C.get_ctx(ref)
    for since in (0, 0, 1):
        assert j2ui_state.build_state(ctx, since)["words"]["team"] == "Ops"
    assert len(n) == 1
