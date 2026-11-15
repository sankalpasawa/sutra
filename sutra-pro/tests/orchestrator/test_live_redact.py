"""The live-text hold-back redactor (streaming design D204, work package STR-4): a secret split across pieces never reaches the page, the store or a snapshot,
and nothing is held back when the tail starts no secret."""
from __future__ import annotations

import itertools
import random

import pytest

from sutra_app.orchestrator.live_redact import HoldBack, holdback_factory
from sutra_app.orchestrator.redact import REDACTED, Redactor


def make(*secrets, environ=None):
    return Redactor(environ=environ or {}, extra=secrets)


def run(redactor, pieces):
    hold = HoldBack(redactor)
    out = [hold.push(p) for p in pieces]
    out.append(hold.finish())
    return out


def pieces_at(text, cuts):
    bounds = [0, *sorted(cuts), len(text)]
    return [text[a:b] for a, b in zip(bounds, bounds[1:])]


SECRETS = ["hunter2-password", "correct horse battery staple", "line one\nline two\nline three", "sk-ant-0123456789abcdef", "a b c d e f g h"]


@pytest.mark.parametrize("secret", SECRETS)
def test_a_secret_split_at_every_single_boundary_never_appears(secret):
    r = make(secret)
    text = f"before {secret} after"
    for k in range(1, len(text)):
        frames = run(r, [text[:k], text[k:]])
        assert secret not in "".join(frames) and all(secret not in f for f in frames)
        assert "".join(frames) == r(text)


@pytest.mark.parametrize("secret", SECRETS[:4])
def test_a_secret_split_at_every_pair_of_boundaries_never_appears(secret):
    r = make(secret)
    text = f"x {secret} y"
    for a, b in itertools.combinations(range(1, len(text)), 2):
        frames = run(r, pieces_at(text, (a, b)))
        assert secret not in "".join(frames) and "".join(frames) == r(text)


@pytest.mark.parametrize("secret", SECRETS)
def test_a_secret_arriving_one_character_at_a_time_never_appears(secret):
    r = make(secret)
    text = f"say {secret}, then {secret} again."
    frames = run(r, list(text))
    assert all(secret not in f for f in frames) and "".join(frames) == r(text) == f"say {REDACTED}, then {REDACTED} again."


def test_nothing_is_held_when_the_tail_starts_no_secret():
    hold = HoldBack(make("sk-ant-0123456789abcdef"))
    assert hold.push("Hello, world") == "Hello, world" and hold.held == ""
    assert hold.push(" and more z") == " and more z" and hold.held == ""            # `z` is the start of no secret: shown at once, nothing held
    assert hold.push(" s") == " " and hold.held == "s"                                # `s` begins `sk-ant-...`: held until the next piece says which it is
    assert hold.push("o") == "so" and hold.held == ""


def test_a_trailing_s_is_emitted_at_once_when_no_secret_starts_with_s():
    hold = HoldBack(make("hunter2-password"))
    assert hold.push("two words s") == "two words s" and hold.held == ""


def test_the_tail_that_could_still_become_a_secret_is_held_and_then_released():
    hold = HoldBack(make("sk-ant-0123456789abcdef"))
    assert hold.push("key: sk-ant-0123") == "key: " and hold.held == "sk-ant-0123"
    assert hold.push("456789abcdef!") == f"{REDACTED}!" and hold.held == ""
    h2 = HoldBack(make("sk-ant-0123456789abcdef"))
    assert h2.push("x sk-ant-01") == "x " and h2.finish() == "sk-ant-01"                  # the block ended: a partial prefix is not a secret
    assert h2.finish() == "" and h2.held == ""


def test_what_is_held_is_bounded_by_the_longest_secret():
    secret = "ab" * 20
    hold = HoldBack(make(secret))
    peak = 0
    for ch in "abababababababababababababababababababab" * 3 + "x":
        hold.push(ch)
        peak = max(peak, len(hold.held))
    assert peak <= len(secret) - 1                                       # never more than the longest secret minus one


def test_a_complete_secret_that_the_cut_would_split_is_redacted_whole():
    """Overlap: the tail `efgh` begins the second secret and sits inside the first, complete one: the first is shown redacted, never cut in two."""
    r = make("abcdefgh", "efghXXXXXX")
    frames = run(r, ["abcdefgh"])
    assert "abcd" not in "".join(frames) and "".join(frames) == REDACTED
    frames = run(r, ["abcdefgh", "!"])
    assert "".join(frames) == f"{REDACTED}!"
    frames = run(r, ["abcdefgh", "XXXXXX"])
    assert "abcdefgh" not in "".join(frames) and "efghXXXXXX" not in "".join(frames)


def test_a_shorter_secret_that_is_also_the_start_of_a_longer_one_is_held_for_the_longer():
    r = make("abcdefgh", "abcdefghij")
    frames = run(r, ["z abcdefgh", "ij!"])
    assert "".join(frames) == f"z {REDACTED}!"
    frames = run(r, ["z abcdefgh", "k"])
    assert "".join(frames) == f"z {REDACTED}k"


def test_extra_secrets_shorter_than_the_environment_minimum_are_held_too():
    r = make("pw1")                                                      # explicit extras count at any length
    frames = run(r, ["the pw", "1 is"])
    assert "pw1" not in "".join(frames) and "".join(frames) == f"the {REDACTED} is"


def test_the_secret_set_is_read_on_every_push():
    env = {}
    r = Redactor(environ=env)
    hold = HoldBack(r)
    assert hold.push("token=zzzzyyyy") == "token=zzzzyyyy"               # not a secret yet: shown, and never taken back
    env["API_KEY"] = "mid-turn-secret-value"
    assert hold.push(" now mid-turn-sec") == " now " and hold.held == "mid-turn-sec"
    assert hold.push("ret-value.") == f"{REDACTED}."


def test_a_redactor_without_a_secret_list_holds_nothing():
    hold = HoldBack(lambda text: text.replace("x", "y"))
    assert hold.push("axb") == "ayb" and hold.held == "" and hold.finish() == ""


def test_a_redactor_whose_secret_list_raises_holds_nothing_and_does_not_break():
    class Broken:
        def secrets(self):
            raise RuntimeError("no")

        def __call__(self, text):
            return text
    assert HoldBack(Broken()).push("hello") == "hello"


def test_empty_pieces_and_an_empty_block_are_fine():
    hold = HoldBack(make("hunter2-password"))
    assert hold.push("") == "" and hold.finish() == "" and hold.push(None) == ""


def test_random_chunkings_over_a_tiny_alphabet_never_show_a_secret():
    """Overlapping, repeated and nested secrets over the alphabet a, b, space and newline, cut at random places."""
    rng = random.Random(7)
    for _ in range(400):
        secrets = ["".join(rng.choice("ab \n") for _ in range(rng.randint(8, 14))) for _ in range(rng.randint(1, 3))]
        r = make(*secrets)
        text = "".join(rng.choice("ab \n") if rng.random() < 0.5 else rng.choice(secrets) for _ in range(rng.randint(5, 40)))
        cuts = {rng.randrange(1, len(text)) for _ in range(rng.randint(0, 12))} if len(text) > 1 else set()
        shown = "".join(run(r, pieces_at(text, cuts)))
        assert not any(s in shown for s in secrets), (secrets, text, cuts, shown)


def test_the_factory_makes_a_fresh_hold_back_per_block():
    factory = holdback_factory(make("hunter2-password"))
    a, b = factory(), factory()
    a.push("hunter2-")
    assert a.held and b.held == "" and a is not b


def test_the_stored_text_is_what_was_shown():
    r = make("hunter2-password")
    text = "My password is hunter2-password, keep it. Done."
    shown = "".join(run(r, pieces_at(text, {10, 20, 30, 33})))
    assert shown == "My password is [redacted], keep it. Done." == r(text)
