"""The citation checker of a cited answer (DV-1): the marks an answer writes, and what code finds when it looks for each one in the owner's folder.

What the tests hold the module to: a label comes from code alone; a path that could reach anything but a plain file inside the folder is "could not find"
(and no file outside the folder is ever opened, whatever the spelling); the file, the range and the quote are each checked; a hostile or odd answer is
never an exception."""
from __future__ import annotations

import builtins
import contextlib
import ntpath
import os
import posixpath
import stat
import sys

import pytest

from sutra_app.orchestrator import citations as c
from sutra_app.orchestrator.citations import CHECKED, MISSING, Mark, absolute_parts, check_answer, check_mark, clean_relative, parse_marks, spelling_problem

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX links or pipes")


@pytest.fixture
def folder(tmp_path):
    """A folder of the owner's with a few files, and a file next to it that is NOT in it."""
    home = tmp_path / "proj"
    (home / "src" / "deep").mkdir(parents=True)
    (home / "src" / "app.py").write_text("import os\n\ndef main():\n    print('hello   world')\n    return 0\n", encoding="utf-8")
    (home / "src" / "deep" / "note.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (home / "README.md").write_text("# Title\r\nSecond line\r\nThird line", encoding="utf-8")
    (home / "empty.txt").write_text("", encoding="utf-8")
    (home / "blob.bin").write_bytes(b"\x00\x01\x02binary\n")
    (home / "Makefile").write_text("all:\n\ttrue\n", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret one\nsecret two\n", encoding="utf-8")
    return str(home)


def one(folder, path, start=1, end=None, quote=None):
    return check_mark(Mark(path, start, start if end is None else end, quote), folder)


# ---- reading the marks ----------------------------------------------------------------------------------------------------------------

def test_a_range_a_single_line_a_quote_and_an_en_dash_are_read():
    found = parse_marks('It starts in [src/app.py:3-4] and returns at [src/app.py:5], see [README.md:2 "Second line"] or [a.py:7\u20139] and [b.py:1 \u201cwords here\u201d].')
    assert found == [Mark("src/app.py", 3, 4), Mark("src/app.py", 5, 5), Mark("README.md", 2, 2, "Second line"), Mark("a.py", 7, 9), Mark("b.py", 1, 1, "words here")]


def test_the_same_mark_is_one_mark_and_the_order_is_the_answers():
    assert parse_marks("[b.py:1-2] then [a.py:1-2] then [b.py:1-2] again") == [Mark("b.py", 1, 2), Mark("a.py", 1, 2)]


def test_text_that_is_not_a_citation_is_not_a_mark():
    text = ("A list [x] and [ ] of tasks, a link [docs](https://example.test/a:1), an array a[i:j], the version [1.2.3], a bare [path.py], "
            "a range [a.py:], a number too big [a.py:12345678901], an empty path [:12], and [see below: 12].")
    assert parse_marks(text) == []
    assert parse_marks("") == [] and parse_marks(None) == [] and parse_marks(12) == []         # type: ignore[arg-type]


def test_marks_in_a_fenced_code_block_are_examples_not_sources():
    text = "Before [a.py:1-2].\n```python\nx = values[1:2]  # [b.py:3-4]\n```\nAfter [c.py:5-6].\n~~~\n[d.py:7-8]\n~~~\nEnd [e.py:9-10]."
    assert parse_marks(text) == [Mark("a.py", 1, 2), Mark("c.py", 5, 6), Mark("e.py", 9, 10)]
    assert parse_marks("Look:\n```\n[never.py:1-2]\nthe fence is not closed") == []


def test_a_mark_in_inline_code_still_counts_but_a_slice_with_letters_is_only_a_mark_that_will_not_be_found(folder):
    assert parse_marks("see `[src/app.py:1-2]` here") == [Mark("src/app.py", 1, 2)]
    assert check_mark(parse_marks("the slice [start:5] is")[0], folder).label == MISSING


def test_a_path_may_have_spaces_and_a_windows_path_is_read_so_it_can_be_refused_in_words():
    assert parse_marks("[My Folder/a b.py:3-4]") == [Mark("My Folder/a b.py", 3, 4)]
    assert parse_marks(r"[C:\proj\a.py:3-4]") == [Mark(r"C:\proj\a.py", 3, 4)]


def test_a_long_quote_or_one_that_runs_over_a_line_end_is_no_quote_of_the_mark():
    assert parse_marks('[a.py:1-2 "one\ntwo"]') == []
    assert parse_marks('[a.py:1-2 "no end]') == []


# ---- a good citation ------------------------------------------------------------------------------------------------------------------

def test_a_file_and_lines_that_exist_are_checked_and_the_label_says_what_was_looked_at(folder):
    got = one(folder, "src/app.py", 3, 5)
    assert (got.label, got.how, got.reason) == (CHECKED, "lines", "")
    assert one(folder, "src/app.py", 5).label == CHECKED                              # the last line, which ends with a newline
    assert one(folder, "Makefile", 1, 2).label == CHECKED                              # a file with no extension
    assert one(folder, "./src//deep/note.md", 1, 3).label == CHECKED                   # `.` and a doubled slash are only spelling


def test_a_quote_on_those_lines_is_checked_with_white_space_squeezed_and_case_kept(folder):
    assert one(folder, "src/app.py", 4, 4, "print('hello world')").how == "quote"      # three spaces in the file, one in the quote
    assert one(folder, "src/app.py", 3, 4, "def main(): print(").how == "quote"        # across a line end
    assert one(folder, "README.md", 1, 3, "Second line Third").how == "quote"          # CRLF line ends do not get in the way
    wrong_case = one(folder, "src/app.py", 4, 4, "PRINT('hello world')")
    assert (wrong_case.label, wrong_case.reason) == (MISSING, "the quoted words are not on those lines")


def test_a_quote_that_is_on_another_line_of_the_file_is_not_on_these_lines(folder):
    got = one(folder, "src/app.py", 1, 1, "return 0")                                    # it is on line 5
    assert got.label == MISSING and got.reason == "the quoted words are not on those lines"


def test_a_quote_too_short_to_prove_anything_is_not_used_and_one_too_long_is_refused(folder):
    assert one(folder, "src/app.py", 1, 1, "xyz").how == "lines"                        # 3 characters: the lines are checked, the quote is not claimed
    long = one(folder, "src/app.py", 1, 5, "a" * 301)
    assert long.label == MISSING and "longer than 300" in long.reason


# ---- a citation that is not found -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, start, end, reason", [
    ("src/nope.py", 1, 1, "there is no such file"),
    ("src/app.py/inside.txt", 1, 1, "there is no such file"),                           # a file used as a folder
    ("src", 1, 1, "that is not a file"),                                                  # a folder
    ("src/app.py", 6, 6, "the file has only 5 lines"),
    ("src/app.py", 4, 9, "the file has only 5 lines"),
    ("src/deep/note.md", 4, 4, "the file has only 3 lines"),
    ("empty.txt", 1, 1, "the file has only 0 lines"),
    ("blob.bin", 1, 1, "the file is not text"),
    ("src/app.py", 0, 2, "the lines are not a valid range"),
    ("src/app.py", 5, 2, "the lines are not a valid range"),
    ("src/app.py", 1, 10_000_001, "that line number is too big"),
    ("src/app.py", 1, 401, "the range is wider than 400 lines, too wide to be a source"),
])
def test_a_citation_that_does_not_hold_says_why_in_words(folder, path, start, end, reason):
    got = one(folder, path, start, end)
    assert (got.label, got.how, got.reason) == (MISSING, "", reason)


def test_a_file_over_the_size_limit_is_not_read(folder, monkeypatch):
    monkeypatch.setattr(c, "MAX_FILE_BYTES", 10)
    assert one(folder, "src/app.py", 1, 1).reason == "the file is too large to check"


def test_no_working_folder_means_nothing_can_be_found():
    assert one("", "a.py").reason == "no working folder is set"
    assert one(None, "a.py").reason == "no working folder is set"                       # type: ignore[arg-type]


# ---- hostile paths --------------------------------------------------------------------------------------------------------------------

HOSTILE = [
    "../outside.txt", "src/../../outside.txt", "src/deep/../../../outside.txt", "./../outside.txt", "..", "src/..", "....//outside.txt",
    "/etc/passwd", "/etc/hosts", "/outside.txt", "//outside.txt", "~", "~/outside.txt", "~root/x",
    r"..\outside.txt", r"src\..\..\outside.txt", r"src\app.py", r"C:\Windows\win.ini", "C:/Windows/win.ini", "C:win.ini", "c:", r"\\server\share\x",
    r"\\?\C:\Windows\win.ini", r"\\.\PhysicalDrive0", "/C:/Windows/win.ini",
    "src/app.py::$DATA", "src/app.py:stream", "src/app.py.", "src/app.py ", " src/app.py", "src/app.py...", "src/ /app.py", "src/. /app.py",
    "NUL", "nul.txt", "src/CON", "src/con.txt", "AUX", "PRN.log", "COM1", "com9.txt", "LPT1", "CONIN$", "CONOUT$",
    "a\x00b", "src/app.py\x00.txt", "a\nb", "a\tb", "src/\x1fapp.py", "src/app.py\x7f",
    "src/*.py", "src/app.p?", "src/<app>.py", "src/a|b", "",  "   ", ".", "./", "/", "//", "./.",
    "x" * 301,
]


@pytest.mark.parametrize("path", HOSTILE)
def test_a_hostile_path_is_never_found_and_nothing_outside_the_folder_is_opened(folder, tmp_path, monkeypatch, path):
    opened: list[str] = []
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda p, *a, **k: (opened.append(str(p)), real_open(p, *a, **k))[1])
    got = check_mark(Mark(path, 1, 1), folder)
    assert got.label == MISSING and got.how == "" and got.reason != ""
    root = os.path.realpath(folder)
    assert all(os.path.realpath(p).startswith(root + os.sep) for p in opened), opened      # at most something inside the folder; here, nothing at all
    assert opened == []


def test_the_outside_file_is_real_so_the_refusals_above_mean_something(folder, tmp_path):
    assert (tmp_path / "outside.txt").read_text().startswith("secret one")
    assert os.path.exists(os.path.join(folder, "..", "outside.txt"))


def test_an_absolute_path_is_kept_only_when_it_is_inside_the_folder(folder, tmp_path):
    inside = os.path.join(folder, "src", "app.py")
    assert one(folder, inside, 1, 2).label == CHECKED
    assert one(folder, str(tmp_path / "outside.txt"), 1, 1).reason == "the path is not inside the folder"
    assert one(folder, os.path.join(folder, "src", "..", "..", "outside.txt"), 1, 1).label == MISSING
    assert one(folder, os.path.join(folder, "src", "..", "README.md"), 1, 1).reason == "the path goes up out of the folder"     # `..` is refused even when it comes back
    assert one(folder, folder, 1, 1).label == MISSING                                    # the folder itself is not a file


@POSIX_ONLY
def test_a_link_out_of_the_folder_is_outside_but_a_link_inside_is_fine(folder, tmp_path):
    os.symlink(str(tmp_path / "outside.txt"), os.path.join(folder, "link-to-outside.txt"))
    os.symlink(str(tmp_path), os.path.join(folder, "link-to-parent"))
    os.symlink(os.path.join(folder, "src", "app.py"), os.path.join(folder, "link-inside.py"))
    os.symlink(os.path.join(folder, "nowhere"), os.path.join(folder, "dangling"))
    assert one(folder, "link-to-outside.txt", 1, 1).reason == "the path leads outside the folder"
    assert one(folder, "link-to-parent/outside.txt", 1, 1).reason == "the path leads outside the folder"           # a folder link that leads out
    assert one(folder, "link-to-parent/proj/src/app.py", 1, 1).label == CHECKED                                   # out and back in: it ends inside
    assert one(folder, "link-inside.py", 1, 2).label == CHECKED
    assert one(folder, "dangling", 1, 1).reason == "there is no such file"


@POSIX_ONLY
def test_a_pipe_is_not_opened_for_reading(folder):
    path = os.path.join(folder, "pipe")
    os.mkfifo(path)
    assert stat.S_ISFIFO(os.stat(path).st_mode)
    got = one(folder, "pipe", 1, 1)                                                      # would block for ever if it were read
    assert got.label == MISSING and got.reason == "that is not a file"


def test_the_spelling_check_alone_names_the_reason_and_gives_the_parts():
    assert clean_relative("src/./deep//note.md") == (["src", "deep", "note.md"], "")
    assert clean_relative("Makefile") == (["Makefile"], "")
    assert clean_relative(".gitignore") == ([".gitignore"], "")
    assert clean_relative("a/../b") == (None, "the path goes up out of the folder")
    assert clean_relative("a\\b")[0] is None and clean_relative("C:x")[0] is None and clean_relative("~/x")[0] is None
    assert clean_relative(None)[0] is None                                              # type: ignore[arg-type]


# ---- a refusal by spelling comes before any file-system call (M1: on Windows realpath of a UNC path connects to the host) -----------------------------------------------------

WINDOWS = [
    r"\\server\share\x.txt", "//server/share/x.txt", "//attacker.example/s/x", r"\\attacker.example\s\x", r"\\.\pipe\x", r"\\.\PhysicalDrive0", r"\\?\C:\Windows\win.ini",
    r"\\?\UNC\host\share\x", "//./pipe/x", "//?/C:/x", "C:", "c:x.txt", r"C:\Windows\win.ini", "C:/Windows/win.ini", "/C:/Windows/win.ini", "x:stream", "src/app.py::$DATA",
    "src/app.py:Zone.Identifier", r"PROGRA~1\x.txt", r"src\app.py", r"..\x", "CON", "nul.txt", "src/COM1", "LPT1.log", "AUX", "src/PRN.txt", "con.", "src/app.py. ",
]


@contextlib.contextmanager
def no_file_system(*extra):
    """Every file-system entry a check could use is replaced, for the body of the `with` only, by a function that fails the test when called (pytest's own use of the file system
    happens outside it)."""
    def trap(*a, **k):
        raise AssertionError("the file system was asked for a refused path")
    saved = []
    targets = [(os.path, n) for n in ("realpath", "exists", "isfile", "isdir", "samefile", "lexists")] + [(os, n) for n in ("stat", "lstat", "fstat", "open", "scandir", "listdir", "readlink", "access")]
    targets.append((builtins, "open"))
    try:
        for owner, name in targets:
            saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, trap)
        yield
    finally:
        for owner, name, original in reversed(saved):
            setattr(owner, name, original)


@pytest.mark.parametrize("path", WINDOWS)
def test_a_windows_spelling_is_refused_before_the_file_system_is_asked(path):
    with no_file_system():
        got = check_mark(Mark(path, 1, 1), "/some/folder")
    assert got.label == MISSING and got.reason != "" and got.reason != "the file could not be read"


@pytest.mark.parametrize("path", ["/etc/passwd", "/", "//", "/some/folder", "/some/folderEvil/x.txt", "/some/other/x.txt", "/some/folder/../x.txt", "/some/folder/./../x.txt"])
def test_an_absolute_path_is_compared_with_the_folder_as_text_first(path):
    with no_file_system():
        got = check_mark(Mark(path, 1, 1), "/some/folder")
    assert got.label == MISSING and got.reason in ("the path is not inside the folder", "the path goes up out of the folder", "the path is not written as a path inside the folder (use / and no drive letter)")


def test_the_pure_parts_say_the_same_for_every_ntpath_absolute_spelling(monkeypatch):
    """What `ntpath` (Windows) calls absolute is refused by text, or compared with the folder as text; none of it needs a Windows machine to be tested."""
    for path in WINDOWS + [r"\\x", "/x", "//x", r"\\", "C:\\", "D:/x"]:
        if ntpath.isabs(path) or ntpath.splitdrive(path)[0]:
            assert spelling_problem(path) != "" or (path.startswith("/") and not path.startswith("//")), path
    assert absolute_parts("//server/share/x", "/some/folder") is None
    assert absolute_parts(r"\\server\share\x", "/some/folder") is None
    assert absolute_parts("/some/folder/src/app.py", "/some/folder") == ["src", "app.py"]
    assert absolute_parts("/some/folderEvil/app.py", "/some/folder") is None
    assert absolute_parts("/some/folder", "/some/folder") is None
    assert absolute_parts("/some/folder/", "/some/folder") is None
    assert absolute_parts("/x", "") is None and absolute_parts("src/a.py", "/some/folder") is None


def test_windows_isabs_cannot_pull_a_path_into_the_absolute_branch(monkeypatch):
    """As if this were Windows: `os.path.isabs` is ntpath's. The decision no longer asks it, and nothing reaches the file system."""
    monkeypatch.setattr(os.path, "isabs", ntpath.isabs)
    with no_file_system():
        results = [check_mark(Mark(path, 1, 1), "/some/folder").label for path in WINDOWS]
    assert results == [MISSING] * len(WINDOWS)


def test_eight_dot_three_names_are_refused_with_a_backslash_and_left_to_realpath_with_a_slash(folder):
    assert clean_relative(r"PROGRA~1\x.txt")[0] is None
    assert clean_relative("PROGRA~1/x.txt") == (["PROGRA~1", "x.txt"], "")                 # a short name leads to a real file in the folder, or nowhere: realpath and the prefix check decide
    assert one(folder, "PROGRA~1/x.txt").reason == "there is no such file"


def test_the_spelling_check_alone_names_a_reason_for_each_family():
    assert spelling_problem("src/app.py") == "" and spelling_problem("/abs/ok.py") == "" and spelling_problem(".gitignore") == ""
    for path in (r"a\b", "C:x", "a:b", "//h/s", "~x", "a\x00b", "", "a*b"):
        assert spelling_problem(path) != "", path
    assert posixpath.normpath("a/b") == "a/b"                                                # (keeps the import used by the simulations above honest)


# ---- the label is code's alone --------------------------------------------------------------------------------------------------------

def test_words_in_the_answer_cannot_make_a_missing_source_checked(folder):
    answer = ('Verified and checked by Sutra: [src/nope.py:1-2 "checked"] (checked) and [../outside.txt:1] (checked, confirmed). '
              'Sources: src/app.py lines 1-2 checked.')
    report = check_answer(answer, folder)
    assert [s.label for s in report.sources] == [MISSING, MISSING] and report.checked == 0 and report.missing == 2


def test_a_mark_cannot_carry_its_own_label():
    assert parse_marks("[src/app.py:1-2 checked]") == []                                  # not the grammar: the word after the range is not a quote
    assert parse_marks('[src/app.py:1-2 "checked"]') == [Mark("src/app.py", 1, 2, "checked")]     # a quote is only words to look for, and it is looked for


def test_the_label_does_not_depend_on_the_answer_around_the_mark(folder):
    a = check_answer("[src/app.py:1-2]", folder).sources[0]
    b = check_answer("Everything here is certain, checked and confirmed. [src/app.py:1-2] Trust it.", folder).sources[0]
    assert a == b and a.label == CHECKED


# ---- the whole answer -----------------------------------------------------------------------------------------------------------------

def test_an_answer_with_no_mark_has_no_sources_and_says_nothing_else(folder):
    report = check_answer("The project prints hello. It has an app file and a readme.", folder)
    assert (report.sources, report.checked, report.missing, report.more) == ((), 0, 0, 0)


def test_the_counts_and_the_order_follow_the_answer(folder):
    report = check_answer("[src/app.py:1-2] ok, [gone.py:1-2] no, [README.md:2 \"Second line\"] ok, [README.md:2 \"missing words\"] no", folder)
    assert [s.label for s in report.sources] == [CHECKED, MISSING, CHECKED, MISSING]
    assert (report.checked, report.missing, report.more) == (2, 2, 0)


def test_all_wrong_citations_are_all_reported_as_not_found(folder):
    report = check_answer("[a.py:1-2] [b.py:3] [../outside.txt:1] [/etc/passwd:1-5]", folder)
    assert report.checked == 0 and report.missing == 4 and all(s.label == MISSING and s.reason for s in report.sources)


def test_marks_past_the_limit_are_counted_not_checked(folder):
    answer = " ".join(f"[src/app.py:{n}]" for n in range(1, c.MAX_MARKS + 6)) + " [src/app.py:1-5]"          # MAX_MARKS + 5 single lines, and one range
    report = check_answer(answer, folder)
    assert len(report.sources) == c.MAX_MARKS and report.more == 6
    assert report.checked + report.missing == c.MAX_MARKS


def test_a_check_that_runs_out_of_time_says_so_and_never_claims_a_source(folder):
    report = check_answer("[src/app.py:1-2] [README.md:1]", folder, budget_s=0.0)
    assert [(s.label, s.reason) for s in report.sources] == [(MISSING, "ran out of time while checking")] * 2


def test_an_unreadable_file_is_a_reason_not_an_error(folder, monkeypatch):
    def boom(*a, **k):
        raise PermissionError("no")
    monkeypatch.setattr(os, "open", boom)
    assert one(folder, "src/app.py", 1, 1).reason == "the file could not be read"


def test_the_same_answer_and_folder_give_the_same_report(folder):
    answer = '[src/app.py:3-4 "def main"] [x/y.py:1-9] [README.md:3]'
    assert check_answer(answer, folder) == check_answer(answer, folder)
