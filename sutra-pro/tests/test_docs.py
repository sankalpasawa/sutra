"""The doc checker (GAP-DOCS): the real documents pass it, and each kind of drift makes it fail.

The real run asserts the four documents match the code. The rest feeds the checker broken text (a wrong flag, a missing row, a dead link) and
expects exactly that problem; the real command parser is built once and shared.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts" / "check_docs.py")
cd = importlib.util.module_from_spec(_spec)
sys.modules["check_docs"] = cd
_spec.loader.exec_module(cd)


@pytest.fixture(scope="module")
def cli():
    return cd.RealCli()


@pytest.fixture(scope="module")
def real():
    return {name: (ROOT / name).read_text(encoding="utf-8") for name in cd.DOCS}


def only(problems, *needles):
    """The problems that mention every needle."""
    return [p for p in problems if all(n in p for n in needles)]


def edited(real, name, old, new, count=1):
    assert old in real[name], f"fixture drift: {old!r} not in {name}"
    return {name: real[name].replace(old, new, count)}


# ---- the real documents ------------------------------------------------------------------------------------------------------------

def test_the_real_documents_pass_the_checker(capsys):
    assert cd.main([]) == 0
    assert "docs check: ok" in capsys.readouterr().out
    assert cd.run_checks(ROOT) == []


def test_the_checker_runs_as_a_script():
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_docs.py")], capture_output=True, text=True, timeout=60,
                          env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin", "TMPDIR": "/tmp"})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "docs check: ok" in done.stdout


def test_the_four_documents_exist_and_have_substance(real):
    assert set(real) == {"docs/GETTING-STARTED.md", "docs/OPERATIONS.md", "docs/TROUBLESHOOTING.md", "docs/ENVIRONMENT.md"}
    for name, text in real.items():
        assert text.startswith("# ") and len(text.splitlines()) > 40, name


def test_the_documents_name_the_real_number_of_doctor_checks(real):
    from sutra_app.ops.doctor import CHECK_IDS
    assert len(CHECK_IDS) == 14
    assert "fourteen checks" in real["docs/GETTING-STARTED.md"] and "fourteen checks" in real["docs/OPERATIONS.md"]


def test_a_missing_document_is_reported_and_the_rest_still_run(tmp_path, capsys):
    problems = cd.run_checks(tmp_path)
    assert len(only(problems, "the document is missing")) == 4
    assert only(problems, "coverage:")                                    # nothing is documented in an empty checkout
    assert cd.main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "::error::docs/OPERATIONS.md: the document is missing" in out and "problem(s)" in out


# ---- markdown helpers --------------------------------------------------------------------------------------------------------------

def test_slugify_follows_the_github_rule():
    assert cd.slugify("Doctor: `python`") == "doctor-python"
    assert cd.slugify("1. The commands") == "1-the-commands"
    assert cd.slugify("F1 Claude or Codex cannot be reached") == "f1-claude-or-codex-cannot-be-reached"


def test_anchors_number_repeats_and_skip_fenced_lines():
    text = "# A\n## B\n## B\n```\n# not a heading\n```\n### C d\n"
    assert cd.anchors_of(text) == {"a", "b", "b-1", "c-d"}


def test_table_cells_keep_an_escaped_pipe_inside_its_cell():
    assert cd.table_cells("| `x` | a\\|b | c |") == ["`x`", "a|b", "c"]
    assert cd.table_cells("not a row") is None
    assert cd.table_cells("| open") is None


def test_snippets_are_code_lines_and_spans_never_prose():
    text = "Run sutra-pro doctor now. Or `sutra-pro stop`.\n```bash\nsutra-pro status\n```\n"
    assert [s for _, s in cd.snippets(text)] == ["sutra-pro stop", "sutra-pro status"]


# ---- reading a command -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("snippet,expected", [
    ("sutra-pro doctor --offline", ["doctor", "--offline"]),
    ("$ sutra-pro stop --wait 5", ["stop", "--wait", "5"]),
    ("SUTRA_PORT=9000 sutra-pro --no-browser", ["--no-browser"]),
    ("python -m sutra_app status", ["status"]),
    ("scripts/run.sh --port 9000", ["--port", "9000"]),
    ("sutra-pro doctor --json | head", ["doctor", "--json"]),
    ("sutra-pro status  # is it up", ["status"]),
    ("sutra-pro stop && sutra-pro", ["stop"]),
    ("sutra-pro", []),
])
def test_parse_command_reads_the_words_up_to_a_shell_operator(snippet, expected):
    assert cd.parse_command(snippet) == expected


@pytest.mark.parametrize("snippet", ["uv tool install sutra-pro", "the sutra-pro command", "sutra-prox status", "echo sutra-pro"])
def test_parse_command_ignores_what_is_not_a_command(snippet):
    assert cd.parse_command(snippet) is None


def test_resolve_walks_the_tree_and_leaves_arguments_alone(cli):
    assert cd.resolve(cli, ["config", "set", "budget", "200"]) == (("config", "set"), None)
    assert cd.resolve(cli, ["restore", "x.tar.gz"]) == (("restore",), None)
    assert cd.resolve(cli, ["serve", "--port", "1"]) == ((), None)
    assert cd.resolve(cli, ["--port", "9000"]) == ((), None)
    assert cd.resolve(cli, ["[serve]", "[flags]"]) == ((), None)             # placeholders are not commands
    assert cd.resolve(cli, ["export", "team", "web"]) == (("export", "team"), None)


def test_resolve_names_an_unknown_command_and_what_exists(cli):
    words, problem = cd.resolve(cli, ["explode"])
    assert words == () and "`explode` is not a command" in problem and "doctor" in problem
    words, problem = cd.resolve(cli, ["config", "frob"])
    assert words == ("config",) and "`frob` is not a command of `sutra-pro config`" in problem and "sync-library" in problem


def test_the_real_parser_reports_its_tree_help_and_flags(cli):
    assert "serve" in cli.children(()) and "doctor" in cli.children(())
    assert cli.children(("config",)) == ["show", "set", "init", "sync-library"]
    assert cli.children(("doctor",)) == [] and cli.children(("serve",)) == []
    assert "--no-browser" in cli.help(()) and "--no-browser" in cli.help(("serve",))
    assert "--generate-override-key" in cli.help(("config", "init"))
    assert cli.flags(("stop",)) == {"--data-dir", "--json", "--wait"}
    assert {"--port", "--browser", "--verbose"} <= cli.flags(())
    assert ("config", "sync-library") in cli.leaves() and () in cli.leaves() and ("config",) not in cli.leaves()


# ---- commands in the documents -----------------------------------------------------------------------------------------------------

def docs_with(text, name="docs/OPERATIONS.md"):
    return {name: text}


def test_a_flag_the_command_does_not_have_is_reported(cli):
    problems = cd.check_commands(cli, docs_with("```\nsutra-pro doctor --fast\n```\n"))
    assert len(problems) == 1 and "docs/OPERATIONS.md:2" in problems[0] and "--fast" in problems[0] and "sutra-pro doctor --help" in problems[0]


def test_a_flag_of_another_command_is_reported(cli):
    problems = cd.check_commands(cli, docs_with("`sutra-pro stop --dry-run`\n"))
    assert len(problems) == 1 and "--dry-run" in problems[0]


def test_a_flag_with_an_equals_sign_is_checked_by_its_name(cli):
    assert cd.check_commands(cli, docs_with("`sutra-pro --port=9000`\n")) == []
    assert len(cd.check_commands(cli, docs_with("`sutra-pro --prot=9000`\n"))) == 1


def test_an_unknown_command_or_subcommand_is_reported(cli):
    assert len(only(cd.check_commands(cli, docs_with("`sutra-pro frobnicate`\n")), "frobnicate")) == 1
    assert len(only(cd.check_commands(cli, docs_with("`sutra-pro export frob`\n")), "frob")) == 1


def test_the_twin_spellings_are_checked_too(cli):
    assert len(cd.check_commands(cli, docs_with("`python -m sutra_app nope`\n"))) == 1
    assert len(cd.check_commands(cli, docs_with("`scripts/run.sh --nope`\n"))) == 1


def test_a_table_row_is_checked_against_its_command(cli):
    good = "| `sutra-pro stop` | `--data-dir D`, `--wait S` | note |\n"
    bad = "| `sutra-pro stop` | `--data-dir D`, `--older-than AGE` | note |\n"
    assert cd.check_commands(cli, docs_with(good)) == []
    problems = cd.check_commands(cli, docs_with(bad))
    assert len(problems) == 1 and "--older-than" in problems[0]
    assert len(cd.check_commands(cli, docs_with("| `sutra-pro frob` | x |\n"))) == 1


def test_prose_and_other_programs_are_not_checked(cli):
    text = "Use sutra-pro doctor --nope in prose.\n`uv tool install --nope x`\n`some-other-tool --flag`\n"
    assert cd.check_commands(cli, docs_with(text)) == []


def test_every_scanned_file_is_checked(cli):
    problems = cd.check_commands(cli, {"README.md": "`sutra-pro doctor --nope`\n", "docs/OPERATIONS.md": "`sutra-pro status --nope`\n"})
    assert [p.split(":")[0] for p in problems] == ["README.md", "docs/OPERATIONS.md"]


# ---- coverage ----------------------------------------------------------------------------------------------------------------------

def test_every_real_command_is_documented(cli, real):
    assert cd.check_coverage(cli, real) == []


def test_an_undocumented_command_is_reported(cli, real):
    stripped = {n: t.replace("sutra-pro prune", "sutra-pro  prune").replace("`sutra-pro prune`", "`prune`") for n, t in real.items()}
    stripped = {n: "\n".join(line for line in t.splitlines() if "sutra-pro prune" not in line and "sutra-pro  prune" not in line) for n, t in stripped.items()}
    problems = cd.check_coverage(cli, stripped)
    assert len(only(problems, "`sutra-pro prune` is not documented")) == 1


def test_an_undocumented_flag_is_reported(cli, real):
    stripped = {n: "\n".join(line for line in t.splitlines() if "--older-than" not in line) for n, t in real.items()}
    assert only(cd.check_coverage(cli, stripped), "--older-than", "`sutra-pro prune`")


def test_a_flag_documented_for_the_wrong_command_does_not_cover_the_right_one(cli):
    docs = {"docs/OPERATIONS.md": "| `sutra-pro status` | `--wait S` |\n| `sutra-pro stop` | `--json` |\n"}
    assert len(only(cd.check_commands(cli, docs), "--wait", "sutra-pro status --help")) == 1
    problems = cd.check_coverage(cli, docs)
    assert len(only(problems, "the flag --wait of `sutra-pro stop` is not documented")) == 1


def test_coverage_looks_at_the_four_documents_only(cli):
    problems = cd.check_coverage(cli, {"README.md": "`sutra-pro doctor`\n"})
    assert only(problems, "`sutra-pro doctor` is not documented")


# ---- environment -------------------------------------------------------------------------------------------------------------------

def test_default_text_writes_flags_numbers_and_nothing():
    assert [cd.default_text(v) for v in (True, False, None, "", 120.0, 8780, "auto", 15.5)] == ["1", "0", "unset", "unset", "120", "8780", "auto", "15.5"]


def test_the_real_environment_document_passes(real):
    assert cd.check_environment(real["docs/ENVIRONMENT.md"]) == []


def test_an_app_variable_without_a_row_is_reported(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `SUTRA_WATCH_MS` |", "| `SUTRA_WATCH_MSX` |")["docs/ENVIRONMENT.md"]
    problems = cd.check_environment(text)
    assert problems == ["docs/ENVIRONMENT.md: the variable SUTRA_WATCH_MS has no row (| `SUTRA_WATCH_MS` | ...)"]


def test_an_engine_variable_without_a_row_is_reported(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `J2_TAP_MIN` |", "| `J2_TAP_MINX` |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "J2_TAP_MIN has no row")) == 1


@pytest.mark.parametrize("old", ["| `J2_OVERRIDE_KEY` |", "| `J2_SMTP_PASSWORD` |", "| `SUTRA_BROWSER_APP` |", "| `SUTRA_CLAUDE_MODEL` |", "| `CLAUDE_CLI_MODEL` |"])
def test_the_secret_browser_and_model_names_need_rows(real, old):
    text = edited(real, "docs/ENVIRONMENT.md", old, old.replace("` |", "X` |"))["docs/ENVIRONMENT.md"]
    assert len(cd.check_environment(text)) == 1


def test_a_wrong_app_default_is_reported(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `SUTRA_PORT` | `port` | `8780` |", "| `SUTRA_PORT` | `port` | `9000` |")["docs/ENVIRONMENT.md"]
    problems = cd.check_environment(text)
    assert len(problems) == 1 and "SUTRA_PORT default is `8780`" in problems[0]


def test_a_whole_number_default_may_be_written_with_or_without_a_point(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `SUTRA_CHAT_TIMEOUT` | `chat_timeout` | `120` |", "| `SUTRA_CHAT_TIMEOUT` | `chat_timeout` | `120.0` |")["docs/ENVIRONMENT.md"]
    assert cd.check_environment(text) == []


def test_a_wrong_engine_default_is_reported(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `J2_BUDGET` | `budget` | `100` |", "| `J2_BUDGET` | `budget` | `101` |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "J2_BUDGET default is `100`")) == 1


def test_a_wrong_locked_flag_is_reported_both_ways(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `J2_CHROME` | `chrome` | `unset` | yes |", "| `J2_CHROME` | `chrome` | `unset` | no |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "J2_CHROME", "Locked must be yes")) == 1
    text = edited(real, "docs/ENVIRONMENT.md", "| `J2_BUDGET` | `budget` | `100` | no |", "| `J2_BUDGET` | `budget` | `100` | yes |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "J2_BUDGET", "Locked must be no")) == 1


def test_a_wrong_task_flag_is_reported(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `J2_OUTPUT` | `output` | `auto` | no | yes |", "| `J2_OUTPUT` | `output` | `auto` | no | no |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "J2_OUTPUT", "Task must be yes")) == 1


def test_a_wrong_field_name_is_reported(real):
    text = edited(real, "docs/ENVIRONMENT.md", "| `SUTRA_HOST` | `host` |", "| `SUTRA_HOST` | `hostname` |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "SUTRA_HOST must name the field `host`")) == 1
    text = edited(real, "docs/ENVIRONMENT.md", "| `J2_DELAY` | `delay` |", "| `J2_DELAY` | `pause` |")["docs/ENVIRONMENT.md"]
    assert len(only(cd.check_environment(text), "J2_DELAY must name the field `delay`")) == 1


def test_a_name_found_in_the_source_needs_a_row(real, tmp_path):
    (tmp_path / "sutra_app").mkdir()
    (tmp_path / "sutra_app" / "newthing.py").write_text('X = os.environ.get("SUTRA_BRAND_NEW")\nY = "SUTRA_NAMES"\n')
    (tmp_path / "scripts" / "macos").mkdir(parents=True)
    (tmp_path / "scripts" / "macos" / "launcher.sh").write_text('echo "${SUTRA_LAUNCH_ONLY:-1}"\n')
    problems = cd.check_environment(real["docs/ENVIRONMENT.md"], tmp_path)
    assert sorted(p.split()[3] for p in problems) == ["SUTRA_BRAND_NEW", "SUTRA_LAUNCH_ONLY"]            # SUTRA_NAMES is a Python constant, not a variable


def test_the_real_source_names_are_all_found():
    names = cd.scan_source_names(ROOT)
    assert {"SUTRA_PORT", "SUTRA_NODES", "SUTRA_START_TIMEOUT", "SUTRA_BUNDLE_CACHE", "SUTRA_BROWSER_APP"} <= names
    assert "SUTRA_NAMES" not in names


# ---- troubleshooting ---------------------------------------------------------------------------------------------------------------

def test_the_real_troubleshooting_document_passes(real):
    assert cd.check_troubleshooting(real["docs/TROUBLESHOOTING.md"]) == []


def test_a_missing_failure_entry_is_reported(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "### F7 ", "### X7 ")["docs/TROUBLESHOOTING.md"]
    assert cd.check_troubleshooting(text) == ["docs/TROUBLESHOOTING.md: there is no entry `### F7 ...` for the failure F7"]


def test_f1_does_not_stand_in_for_f10(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "### F10 ", "### X10 ")["docs/TROUBLESHOOTING.md"]
    assert len(only(cd.check_troubleshooting(text), "F10")) == 1


def test_a_missing_doctor_entry_is_reported(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "### Doctor: `gh`", "### Doctor: `github`")["docs/TROUBLESHOOTING.md"]
    problems = cd.check_troubleshooting(text)
    assert len(problems) == 1 and "doctor check gh" in problems[0]


def test_the_failure_codes_come_from_the_design_table(tmp_path):
    assert cd.failure_codes(tmp_path) == [f"F{n}" for n in range(1, 11)]                         # no design file: the ten of the plan
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "orchestrator.md").write_text("| F1 | a |\n| F2 | b |\n| F11 | c |\n")
    assert cd.failure_codes(tmp_path) == ["F1", "F2", "F11"]
    assert cd.failure_codes(ROOT) == [f"F{n}" for n in range(1, 11)]


def test_an_error_code_row_with_the_wrong_status_is_reported(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "| `store_busy` | 503 |", "| `store_busy` | 500 |")["docs/TROUBLESHOOTING.md"]
    assert len(only(cd.check_troubleshooting(text), "`store_busy` is HTTP 503")) == 1


def test_a_missing_api_error_row_is_reported(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "| `bad_origin` | 403 |", "| `bad_origins` | 403 |")["docs/TROUBLESHOOTING.md"]
    assert len(only(cd.check_troubleshooting(text), "API error code `bad_origin` has no row")) == 1


def test_a_connector_error_row_with_the_wrong_kind_is_reported(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "| `quota` | quota |", "| `quota` | auth |")["docs/TROUBLESHOOTING.md"]
    assert len(only(cd.check_troubleshooting(text), "`quota` is kind quota")) == 1


def test_a_missing_connector_error_row_is_reported(real):
    text = edited(real, "docs/TROUBLESHOOTING.md", "| `session_lost` | unavailable |", "| `session_gone` | unavailable |")["docs/TROUBLESHOOTING.md"]
    assert len(only(cd.check_troubleshooting(text), "connector error code `session_lost` has no row")) == 1


def test_the_code_cli_missing_needs_a_row_in_each_table(real):
    text = real["docs/TROUBLESHOOTING.md"]
    assert text.count("| `cli_missing` |") == 2
    one = text.replace("| `cli_missing` | 503 |", "| `cli_gone` | 503 |")
    assert len(only(cd.check_troubleshooting(one), "`cli_missing` has no row")) == 1


# ---- links -------------------------------------------------------------------------------------------------------------------------

def test_a_link_to_a_missing_file_is_reported():
    problems = cd.check_links("docs/OPERATIONS.md", "see [x](NOPE.md)\n", ROOT)
    assert problems == ["docs/OPERATIONS.md:1: dead link NOPE.md: NOPE.md does not exist"]


def test_links_resolve_from_the_folder_of_the_document():
    assert cd.check_links("docs/OPERATIONS.md", "[a](ENVIRONMENT.md) [b](../README.md) [c](design/)\n", ROOT) == []
    assert len(cd.check_links("README.md", "[a](ENVIRONMENT.md)\n", ROOT)) == 1                     # README.md is one folder up


def test_an_anchor_must_be_a_heading_of_the_target():
    assert cd.check_links("docs/OPERATIONS.md", "[a](ENVIRONMENT.md#3-secrets-the-override-key-and-the-smtp-login)\n", ROOT) == []
    problems = cd.check_links("docs/OPERATIONS.md", "[a](ENVIRONMENT.md#no-such-part)\n", ROOT)
    assert len(problems) == 1 and "no heading `no-such-part` in ENVIRONMENT.md" in problems[0]


def test_an_anchor_in_the_same_document_is_checked():
    assert cd.check_links("docs/OPERATIONS.md", "# Top\n[a](#top)\n", ROOT) == []
    assert len(cd.check_links("docs/OPERATIONS.md", "# Top\n[a](#bottom)\n", ROOT)) == 1


def test_external_links_code_spans_fences_and_images_are_not_checked():
    text = "[a](https://example.com/x) [b](mailto:x@y.z)\n`[c](NOPE.md)`\n```\n[d](NOPE.md)\n```\n![e](NOPE.png)\n"
    assert cd.check_links("docs/OPERATIONS.md", text, ROOT) == []


def test_a_link_with_a_title_is_still_a_link():
    assert len(cd.check_links("docs/OPERATIONS.md", '[a](NOPE.md "the title")\n', ROOT)) == 1
