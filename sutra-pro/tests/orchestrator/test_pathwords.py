"""pathwords (gap package chart-insight): the words Sutra writes for the owner say a file's name, never this machine's folders.

The cases are the old app's test_j2ui_common C1-6, re-expressed over injected roots: a relative path and a date stay, a path under the
home, the data folder, the temp folder or the install folder is shortened, `~/...` and a Windows drive path too, and a page of a site
('/home/about') is left alone because it is not under a folder of this machine."""
import os

import pytest

from sutra_app.orchestrator import pathwords
from sutra_app.orchestrator.pathwords import compile_rule, machine_roots, shorten

HOME = "/Users/me"
ROOTS = (HOME, "/srv/sutra/data", "/tmp/pytest-of-me", "/opt/apps/sutra-pro")


def short(text: str, roots=ROOTS) -> str:
    return shorten(text, roots)


def test_a_relative_path_a_date_and_a_url_are_left_alone():
    for words in ("build/v1/index.html", "due 5/6/2026 and 24/7/365", "https://example.test/var/log/x", "see docs/guide.md and ./a/b.txt"):
        assert short(words) == words


def test_a_path_under_the_home_is_shortened_to_its_file_name_and_the_sentence_end_stays():
    assert short("wrote /Users/me/y/z.txt.") == "wrote z.txt."
    assert short("(/Users/me/a.md) and \"/Users/me/b/c.md\"") == "(a.md) and \"c.md\""
    assert short("/Users/me/.local/share/uv/tools/sutra-pro/lib/python3.11/site-packages/x/tools.py:12, in run") == "tools.py:12, in run"
    assert short("see /Users/me/a and /Users/me/b") == "see a and b"


def test_the_data_folder_the_temp_folder_and_the_install_folder_count_as_this_machine():
    assert short("file /srv/sutra/data/departments/web/runs/j2-1/run.stderr.log ended") == "file run.stderr.log ended"
    assert short("in /tmp/pytest-of-me/t1/x.txt.") == "in x.txt."
    assert short("at /opt/apps/sutra-pro/sutra_app/engine/j2.py line 3") == "at j2.py line 3"
    assert short("at /private/var/folders/ab/T/x/") == "at x"
    assert short("/Volumes/Disk/site/index.html") == "index.html"


def test_a_home_path_and_a_windows_drive_path_are_shortened_where_a_path_would_start():
    assert short("saved to ~/notes/a.md, ok") == "saved to a.md, ok"
    assert short("C:\\Users\\me\\f.txt now") == "f.txt now"
    assert short("C:/Users/me/f.txt and D:\\x\\y.md") == "f.txt and y.md"                  # a drive and a backslash is a path whatever the folder
    assert short("Plan B:/pricing and E:/Program/z") == "Plan B:/pricing and E:/Program/z"       # a drive and a slash needs a Windows folder after it
    assert short("C:/ProgramData/x/y.cfg and C:/Windows/System32/a.dll") == "y.cfg and a.dll"


@pytest.mark.parametrize("words", [
    "go to /home/about", "Never link /private/area and always keep /home/about first", "/private/members", "/etc/terms and /var/news",
    "/opt/shop/cart", "/tmp/stage/a", "/root/x/y", "/Users/login/settings", "see /home/about/team.", "(/home/about)", '"/private/members/"',
    "Plan B:/pricing", "Plan B:/pricing/page", "a:/b/c", "C:/pricing/page", "Q&A:/faq/page", "keep /home/about, /private/area and /var/news",
])
def test_a_route_quoted_in_the_owners_words_is_not_a_machine_path(words):
    assert short(words) == words


@pytest.mark.parametrize("words", [
    "Make /home the landing page", "keep /private hidden", "see /var and /tmp and /etc", "the /opt-in page", "send /root to /login",
    "/home", "/private", "/var", "/tmp", "/etc", "/opt", "/root", "/Users", "/Volumes", "/opt-in", "/home/ and /root/ are pages",
    "Q&A:/faq and ratio 1:/2", "about~/home and a~/b", "see /homepage and /rooted and /variable",
])
def test_a_folder_alone_is_a_page_not_a_path(words):
    assert short(words) == words


def test_a_deeper_folder_of_this_machine_itself_is_a_path_but_a_single_name_folder_is_not():
    assert short("running in /Users/me.") == "running in me."
    assert short("running in /srv/sutra/data now") == "running in data now"
    assert short("a /Users/medic and /Users/me2/x stay", roots=("/Users/me",)) == "a /Users/medic and /Users/me2/x stay"


def test_a_text_that_is_not_text_or_is_empty_comes_back_as_it_is():
    assert shorten("", ROOTS) == ""
    assert shorten(None, ROOTS) is None            # type: ignore[arg-type]
    assert shorten(12, ROOTS) == 12                # type: ignore[arg-type]


def test_machine_roots_names_each_folder_as_named_and_as_resolved_longest_first(tmp_path):
    real = tmp_path / "data"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    roots = machine_roots([link], home="/Users/me", temp="/tmp/t", install="/opt/apps/x")
    for want in (str(link), os.path.realpath(link), "/Users/me", "/tmp/t", "/opt/apps/x", "/private/var/folders", "/Volumes"):
        assert want in roots, want
    assert "/" not in roots and all(r.startswith("/") and not r.endswith("/") for r in roots)
    assert list(roots) == sorted(roots, key=lambda r: (-len(r), r))


def test_the_default_roots_hold_the_real_home_the_temp_folder_and_where_the_app_is_installed():
    roots = machine_roots()
    here = os.path.realpath(pathwords.__file__)
    assert os.path.realpath(os.path.expanduser("~")) in roots or len(os.path.realpath(os.path.expanduser("~"))) <= 1
    assert os.path.realpath(__import__("tempfile").gettempdir()) in roots
    assert any(here.startswith(r + os.sep) for r in roots), "the install folder of the app is among the roots"
    assert shorten(here) == "pathwords.py"


def test_a_root_of_one_name_never_turns_a_whole_top_folder_into_paths():
    roots = machine_roots(home="/Users/me", temp="/tmp/t", install="/opt")
    assert "/opt" in roots                      # a caller who injects it means it ...
    assert shorten("see /usr/guide and /srv/pages", roots) == "see /usr/guide and /srv/pages"       # ... but nothing else is guessed


def test_the_compiled_rule_is_a_pattern_of_the_roots_given():
    rule = compile_rule(["/Users/me"])
    assert rule.search("/Users/me/a") and not rule.search("/Users/you/a")
    assert not compile_rule([]).search("/Users/me/a")
