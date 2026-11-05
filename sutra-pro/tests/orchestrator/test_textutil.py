"""slugify, tokens, name_key, jaccard, parse_yes_no, one_line_title (design 2, 5.2, 5.4)."""
import pytest

from sutra_app.orchestrator.textutil import jaccard, name_key, one_line_title, parse_yes_no, slugify, stem, tokens


def test_slugify():
    assert slugify("Coffee Shop & Café!") == "coffee-shop-caf"
    assert slugify("  --Hello__World--  ") == "hello-world"
    assert slugify("???") == "" and slugify("") == ""
    assert slugify("a" * 10 + " " + "b" * 40, max_len=12) == "aaaaaaaaaa-b"
    assert slugify("abc def", max_len=4) == "abc"                       # no trailing hyphen after the cut
    with pytest.raises(TypeError):
        slugify(None)


def test_tokens_keep_words_of_three_letters_and_drop_stop_words():
    assert tokens("I want a website for my coffee shop, it is NEW") == frozenset({"website", "coffee", "shop"})
    assert tokens("Go to X1 now") == frozenset()                        # two-letter words never count
    assert tokens("web3 site") == frozenset({"web3", "site"})
    assert tokens("") == frozenset()
    with pytest.raises(TypeError):
        tokens(3)


def test_name_key_strips_one_plural_s():
    assert name_key("Sales") == name_key("Sale") == frozenset({"sale"})
    assert name_key("Business Plans") == name_key("Business Plan")
    assert stem("class") == "class" and stem("gas") == "gas" and stem("bus") == "bus"      # short words and `ss` stay


def test_jaccard():
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert jaccard({"a"}, {"a"}) == 1.0 and jaccard({"a"}, {"b"}) == 0.0
    assert jaccard([], []) == 0.0 and jaccard({"a"}, []) == 0.0
    assert jaccard(["a", "a", "b"], iter(["b", "a"])) == 1.0           # lists, repeats and iterators are sets


@pytest.mark.parametrize("text", ["yes", "Y", " OK ", "okay.", "Sure!", "go ahead", "Do  It", "approve"])
def test_yes(text):
    assert parse_yes_no(text) is True


@pytest.mark.parametrize("text", ["no", "N", "Nope.", "cancel", "leave it", "REJECT"])
def test_no(text):
    assert parse_yes_no(text) is False


@pytest.mark.parametrize("text", ["yes please", "no thanks", "ok but add a menu", "", "  ", "maybe", "yes\nno", None, 3])
def test_neither(text):
    assert parse_yes_no(text) is None


def test_one_line_title():
    assert one_line_title("A coffee\nshop   landing page") == "A coffee shop landing page"
    long = "Make a landing page for my coffee shop with a menu and opening hours please"
    assert one_line_title(long, 30) == "Make a landing page for my"         # 28 chars: the cut word "coffee" is dropped whole
    assert one_line_title("abc def", 3) == "abc"                              # the cut falls exactly on a space
    assert one_line_title("x" * 90, 60) == "x" * 60                           # one long word is cut hard
    assert len(one_line_title(long, 60)) <= 60 and one_line_title("short") == "short"
