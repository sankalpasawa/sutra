"""The GitHub workflows (.github/workflows): structure checked with PyYAML, without a network and without GitHub.

Two layers. The RULES are small functions over a parsed workflow (pinned actions, permissions, secrets, untrusted input); they
are applied to every workflow in the folder, so the next workflow added is held to them too, and each rule is proved on
synthetic bad workflows so it cannot go quiet. The SHAPE tests pin what ci.yml and release-wheel.yml promise (docs/RELEASE.md).
"""
import fnmatch
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
# the workflows of this product live at the root of the Sutra repository, next to the old product's, with a sutra-pro- prefix (D98)
WORKFLOWS = ROOT.parent / ".github" / "workflows"
PREFIX = "sutra-pro-"

# the majors the release work package pins (a major tag moves with fixes; a branch would move with anything)
MAJORS = {
    "actions/checkout": "v4",
    "astral-sh/setup-uv": "v5",
    "actions/setup-node": "v4",
    "actions/upload-artifact": "v4",
    "softprops/action-gh-release": "v2",
}


def workflow_paths():
    return sorted([*WORKFLOWS.glob(PREFIX + "*.yml"), *WORKFLOWS.glob(PREFIX + "*.yaml")])


def load(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def named(name):
    return load(WORKFLOWS / (PREFIX + name))


# ---------------------------------------------------------------- the rules (functions over a parsed workflow)

def triggers(wf):
    """The `on:` table as a dict. PyYAML follows YAML 1.1, where a bare `on` is the boolean True: look under both keys."""
    on = wf["on"] if "on" in wf else wf[True]
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return on


def steps_of(job):
    return job.get("steps", [])


def all_uses(wf):
    """(where, uses) for every action a workflow uses: steps and reusable-workflow jobs."""
    for job_id, job in wf["jobs"].items():
        if "uses" in job:
            yield f"jobs.{job_id}", job["uses"]
        for index, step in enumerate(steps_of(job)):
            if "uses" in step:
                yield f"jobs.{job_id}.steps[{index}]", step["uses"]


# a version tag (v4, v4.1.7, 4.1.7) or a full commit sha; a branch name (main, master, latest, release/v1) is neither
PINNED_REF = re.compile(r"v?[0-9]+(?:\.[0-9]+){0,2}|[0-9a-f]{40}")


def unpinned(uses):
    """Why an action reference is not pinned to a version tag, or None when it is."""
    if uses.startswith("./"):
        return None                       # an action of this very repository
    if uses.startswith("docker://"):
        return "a docker image is not pinned by a version tag"
    if "@" not in uses:
        return "has no @ref"
    ref = uses.rsplit("@", 1)[1]
    return None if PINNED_REF.fullmatch(ref) else f"@{ref} is not a version tag"


SECRET_VALUE = re.compile(r"\bsecrets\.|\bgithub\.token\b")
PRINTER = re.compile(r"\b(?:echo|printf|print|cat|tee)\b")
ENV_DUMPERS = [
    re.compile(p) for p in (
        r"\bset\s+-[a-zA-Z]*x", r"\bset\s+-o\s+xtrace", r"\b(?:ba|z)?sh\s+-[a-zA-Z]*x", r"\bprintenv\b",
        r"(?:^|[;&|]\s*)env\s*(?:$|[;&|])", r"\bexport\s+-p\b", r"\bdeclare\s+-[a-zA-Z]*p",
    )
]


def logical_lines(script):
    """A script as the shell reads it: a backslash continuation joins lines, and a here-document body joins the line that opens it."""
    lines = script.replace("\\\n", " ").splitlines()
    out, i = [], 0
    while i < len(lines):
        line, i = lines[i], i + 1
        opening = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)
        if opening:
            body = []
            while i < len(lines) and lines[i].strip() != opening.group(1):
                body.append(lines[i])
                i += 1
            i += 1                                    # the terminator line
            line = " ".join([line, *body])
        out.append(line)
    return out


def secret_leaks(wf):
    """Run steps that put a secret where the log or a later step can read it. A heuristic, strict on purpose:
    - a ${{ secrets.* }} written into the script text (it must arrive through env:);
    - a printing command (echo, printf, cat, tee) on a line that names a secret-bearing variable and does not redirect it;
    - a command that dumps the environment or traces commands (set -x, env, printenv) in a step that holds a secret."""
    leaks = []
    for job_id, job in wf["jobs"].items():
        for index, step in enumerate(steps_of(job)):
            if "run" not in step:
                continue
            where = f"jobs.{job_id}.steps[{index}]"
            script = str(step["run"])
            if re.search(r"\$\{\{[^}]*\bsecrets\.", script):
                leaks.append(f"{where}: a secret is written into the script text")
            env = {**(wf.get("env") or {}), **(job.get("env") or {}), **(step.get("env") or {})}
            names = [k for k, v in env.items() if SECRET_VALUE.search(str(v))]
            if not names:
                continue
            lines = logical_lines(script)
            if any(p.search(line) for p in ENV_DUMPERS for line in lines):
                leaks.append(f"{where}: dumps the environment or traces commands while it holds {names}")
            for line in lines:
                refs = any(re.search(rf"\$\{{?{re.escape(n)}\b", line) for n in names)
                if refs and PRINTER.search(line) and ">" not in line:
                    leaks.append(f"{where}: prints a secret-bearing variable: {line.strip()}")
    return leaks


SAFE_CONTEXTS = {"matrix", "runner", "env", "steps", "needs", "strategy", "job"}


def untrusted_in_run(wf):
    """${{ }} expressions inside a run: script that read a context other than the safe ones. A tag, a branch name, an input or
    a pull request title is attacker-chosen text; written into the script it becomes code. It belongs in env:, quoted."""
    found = []
    for job_id, job in wf["jobs"].items():
        for index, step in enumerate(steps_of(job)):
            for expression in re.findall(r"\$\{\{(.*?)\}\}", str(step.get("run", "")), re.S):
                bare = re.sub(r"'[^']*'", "''", expression)
                for token in re.findall(r"[A-Za-z_][\w-]*(?:\.[\w*-]+)*\(?", bare):
                    if token.endswith("(") or token in ("true", "false", "null"):
                        continue
                    if token.split(".")[0] not in SAFE_CONTEXTS:
                        found.append(f"jobs.{job_id}.steps[{index}]: ${{{{ {expression.strip()} }}}} reads {token}")
    return found


def permission_problems(wf):
    """The top-level permissions: a table of read, write or none (least privilege starts from `contents: read`)."""
    perms = wf.get("permissions")
    if not isinstance(perms, dict) or not perms:
        return ["no top-level permissions table"]
    return [f"{scope}: {level!r} is not read, write or none" for scope, level in perms.items() if level not in ("read", "write", "none")]


def effective_permissions(wf, job):
    return job.get("permissions", wf.get("permissions"))


def cannot_write_release(wf):
    """Jobs that upload to a release without being able to write contents."""
    bad = []
    for job_id, job in wf["jobs"].items():
        if any(str(s.get("uses", "")).startswith("softprops/action-gh-release@") for s in steps_of(job)):
            perms = effective_permissions(wf, job)
            if not isinstance(perms, dict) or perms.get("contents") != "write":
                bad.append(job_id)
    return bad


def step_texts(step):
    """The names a step sets in env and its run script, as (kind, text)."""
    for key in (step.get("env") or {}):
        yield "env", key
    if "run" in step:
        yield "run", str(step["run"])


def env_names_and_scripts(wf):
    """Every env variable name and every run script of a workflow, as (where, text)."""
    for key in (wf.get("env") or {}):
        yield "env", key
    for job_id, job in wf["jobs"].items():
        for key in (job.get("env") or {}):
            yield f"jobs.{job_id}.env", key
        for index, step in enumerate(steps_of(job)):
            for kind, text in step_texts(step):
                yield f"jobs.{job_id}.steps[{index}].{kind}", text


def mentions(wf, name):
    return [where for where, text in env_names_and_scripts(wf) if re.search(rf"\b{name}\b", text)]


def strings(node):
    """Every string in a parsed document, keys included."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from strings(key)
            yield from strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from strings(item)


def needs_of(job):
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def needs_closure(wf, job_id):
    """Every job that job_id waits for, directly or through others."""
    seen, todo = set(), needs_of(wf["jobs"][job_id])
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            todo += needs_of(wf["jobs"][current])
    return seen


def commands(job):
    return [str(step["run"]).strip() for step in steps_of(job) if "run" in step]


def action_steps(job, prefix):
    return [step for step in steps_of(job) if str(step.get("uses", "")).startswith(prefix)]


def synthetic(*steps, env=None, job_env=None, permissions=None, job_permissions=None):
    """A minimal parsed workflow with one job, for proving a rule on a bad example."""
    job = {"runs-on": "ubuntu-latest", "steps": list(steps)}
    if job_env:
        job["env"] = job_env
    if job_permissions:
        job["permissions"] = job_permissions
    wf = {"name": "x", True: "push", "jobs": {"j": job}}
    if env:
        wf["env"] = env
    if permissions:
        wf["permissions"] = permissions
    return wf


# ---------------------------------------------------------------- every workflow in the folder

def test_the_expected_workflows_exist():
    names = {p.name for p in workflow_paths()}
    assert {"sutra-pro-ci.yml", "sutra-pro-release-wheel.yml", "sutra-pro-release-macos.yml"} <= names


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_every_workflow_parses_into_a_named_workflow_with_jobs(path):
    wf = load(path)
    assert isinstance(wf, dict)
    assert isinstance(wf.get("name"), str) and wf["name"]
    assert triggers(wf), "no trigger"
    assert isinstance(wf.get("jobs"), dict) and wf["jobs"], "no jobs"
    for job_id, job in wf["jobs"].items():
        assert "runs-on" in job or "uses" in job, f"job {job_id} has no runner"
        assert job.get("steps") or "uses" in job, f"job {job_id} has no steps"
        for step in steps_of(job):
            assert ("run" in step) != ("uses" in step), f"job {job_id}: a step needs exactly one of run and uses: {step}"


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_every_uses_is_pinned_to_a_version_tag_never_a_branch(path):
    problems = [f"{where}: {ref} {why}" for where, ref in all_uses(load(path)) if (why := unpinned(ref))]
    assert not problems, problems


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_the_known_actions_stay_on_the_majors_the_package_pinned(path):
    for where, ref in all_uses(load(path)):
        action, _, version = ref.partition("@")
        if action in MAJORS:
            assert version == MAJORS[action], f"{where}: {ref} should be {action}@{MAJORS[action]}"


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_every_workflow_sets_top_level_permissions(path):
    assert permission_problems(load(path)) == [], "set permissions: at the top of the file, least privilege first"


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_no_workflow_runs_on_pull_request_target_or_a_schedule(path):
    """pull_request_target runs with write permissions on code from a fork; no workflow here needs it."""
    assert not {"pull_request_target", "schedule", "workflow_run"} & set(triggers(load(path)))


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_no_run_step_echoes_a_secret(path):
    assert secret_leaks(load(path)) == []


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_run_scripts_take_attacker_chosen_text_only_through_env(path):
    assert untrusted_in_run(load(path)) == []


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_a_job_that_uploads_to_a_release_can_write_contents(path):
    assert cannot_write_release(load(path)) == []


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_live_and_browser_suites_are_never_switched_on(path):
    wf = load(path)
    assert mentions(wf, "SUTRA_LIVE") == [] and mentions(wf, "SUTRA_BROWSER") == []


@pytest.mark.parametrize("path", workflow_paths(), ids=lambda p: p.name)
def test_the_slow_suites_are_switched_on_only_by_a_manual_slow_run(path):
    wf = load(path)
    for job_id, job in wf["jobs"].items():
        for index, step in enumerate(steps_of(job)):
            if any(re.search(r"\bSUTRA_SLOW\b", text) for _, text in step_texts(step)):
                assert "inputs.slow" in str(step.get("if", "")), f"jobs.{job_id}.steps[{index}] sets SUTRA_SLOW without inputs.slow"


# ---------------------------------------------------------------- the rules themselves, on bad workflows

@pytest.mark.parametrize("uses", [
    "actions/checkout@v4", "actions/checkout@v4.1.7", "actions/checkout@4", "astral-sh/setup-uv@v5", "owner/repo/path/x@v1.2",
    "actions/checkout@" + "a" * 40, "./.github/actions/mine", "org/repo/.github/workflows/w.yml@v2",
])
def test_pinned_references_are_accepted(uses):
    assert unpinned(uses) is None


@pytest.mark.parametrize("uses,why", [
    ("actions/checkout@main", "@main"), ("actions/checkout@master", "@master"), ("actions/checkout@latest", "@latest"),
    ("actions/checkout@HEAD", "@HEAD"), ("actions/checkout@release/v1", "@release/v1"), ("actions/checkout@v4-beta", "@v4-beta"),
    ("actions/checkout@develop", "@develop"), ("actions/checkout@" + "a" * 7, "@aaaaaaa"), ("actions/checkout@", "@"),
    ("actions/checkout@v", "@v"), ("actions/checkout@v4.1.7.2", "@v4.1.7.2"), ("actions/checkout", "no @ref"),
    ("docker://alpine:3.20", "docker"),
])
def test_unpinned_references_are_refused(uses, why):
    assert why in unpinned(uses)


def test_the_pin_rule_reaches_job_level_and_step_level_uses():
    wf = {"jobs": {"a": {"uses": "org/repo/.github/workflows/w.yml@main"}, "b": {"steps": [{"uses": "x/y@v1"}, {"uses": "x/z@main"}]}}}
    assert list(all_uses(wf)) == [("jobs.a", "org/repo/.github/workflows/w.yml@main"), ("jobs.b.steps[0]", "x/y@v1"),
                                  ("jobs.b.steps[1]", "x/z@main")]


@pytest.mark.parametrize("value,expected", [("push", {"push": None}), (["push", "pull_request"], {"push": None, "pull_request": None}),
                                            ({"push": {"branches": ["main"]}}, {"push": {"branches": ["main"]}})])
def test_triggers_reads_on_under_the_yaml_1_1_boolean_key(value, expected):
    assert triggers({True: value}) == expected
    assert triggers({"on": value}) == expected


@pytest.mark.parametrize("step", [
    {"run": 'echo "${{ secrets.TOKEN }}"'},
    {"run": 'echo "$TOKEN"', "env": {"TOKEN": "${{ secrets.TOKEN }}"}},
    {"run": "echo ${TOKEN}", "env": {"TOKEN": "${{ secrets.TOKEN }}"}},
    {"run": 'echo "$TOKEN" | base64', "env": {"TOKEN": "${{ secrets.TOKEN }}"}},                  # encoded is still printed
    {"run": 'printf "%s" "$GH_TOKEN"', "env": {"GH_TOKEN": "${{ github.token }}"}},
    {"run": 'echo "token is $GH_TOKEN" \\\n  done', "env": {"GH_TOKEN": "${{ github.token }}"}},
    {"run": 'echo start \\\n  "$KEY"', "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "cat <<EOF\n$KEY\nEOF", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "set -x\ncurl x", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "set -euxo pipefail\ncurl x", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "bash -x script.sh", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "printenv", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "env | sort", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "env", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "export -p", "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": "set -o xtrace", "env": {"KEY": "${{ secrets.KEY }}"}},
])
def test_a_step_that_leaks_a_secret_is_found(step):
    assert secret_leaks(synthetic(step)), step


@pytest.mark.parametrize("script,expected", [
    ("a\nb", ["a", "b"]),
    ("a \\\n  b\nc", ["a    b", "c"]),
    ("cat <<EOF\nx\ny\nEOF\nnext", ["cat <<EOF x y", "next"]),
    ("cat <<'EOF'\n$K\nEOF\nnext", ["cat <<'EOF' $K", "next"]),
    ('cat <<-"END"\n$K\n  END\nnext', ['cat <<-"END" $K', "next"]),
    ("cat <<EOF\nnever closed", ["cat <<EOF never closed"]),
    ("", []),
])
def test_logical_lines_follow_the_shell(script, expected):
    assert logical_lines(script) == expected


def test_a_secret_held_by_the_job_or_the_workflow_is_watched_too():
    step = {"run": 'echo "$KEY"'}
    assert secret_leaks(synthetic(step, job_env={"KEY": "${{ secrets.KEY }}"}))
    assert secret_leaks(synthetic(step, env={"KEY": "${{ secrets.KEY }}"}))


@pytest.mark.parametrize("step", [
    {"run": "echo hello"},
    {"run": 'echo "$HOME"', "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": 'echo "$KEYBOARD"', "env": {"KEY": "${{ secrets.KEY }}"}},                           # another variable, same prefix
    {"run": 'printf "%s" "$KEY" | base64 --decode > "$RUNNER_TEMP/k.p12"', "env": {"KEY": "${{ secrets.KEY }}"}},
    {"run": 'gh release download "$TAG"', "env": {"GH_TOKEN": "${{ github.token }}", "TAG": "v1"}},
    {"run": "set -euo pipefail\ngh release view x", "env": {"GH_TOKEN": "${{ github.token }}"}},
    {"run": "set -x\nls", "env": {"PLAIN": "value"}},                                           # tracing without a secret in reach
    {"run": "env | sort"},                                                                       # no secret in reach
    {"run": 'echo "$NAME"', "env": {"NAME": "${{ matrix.name }}"}},
    {"uses": "actions/checkout@v4"},
])
def test_a_step_that_keeps_its_secret_is_not_flagged(step):
    assert secret_leaks(synthetic(step)) == []


@pytest.mark.parametrize("script", [
    "echo ${{ github.event.pull_request.title }}", "echo ${{ github.head_ref }}", "echo ${{ github.ref_name }}",
    "echo ${{ inputs.tag }}", "echo ${{ inputs.tag || github.ref_name }}", "echo ${{ github.event.inputs.tag }}",
    "echo ${{ secrets.X }}", "echo ${{ vars.X }}", "echo ${{ github.actor }}", "echo ${{ github }}",
    "echo ${{ format('{0}', github.ref) }}", "echo ${{ matrix.os }} ${{ github.sha }}", "echo ${{ contains(inputs.tag, 'x') }}",
    "echo ${{\n  github.ref_name }}",
])
def test_attacker_chosen_text_in_a_script_is_found(script):
    assert untrusted_in_run(synthetic({"run": script})), script


@pytest.mark.parametrize("script", [
    "echo ${{ matrix.os }}", "echo ${{ runner.temp }}", "echo ${{ env.X }}", "echo ${{ steps.a.outputs.wheel }}",
    "echo ${{ needs.build.outputs.v }}", "echo ${{ strategy.job-index }}", "echo ${{ job.status }}",
    "echo ${{ contains(matrix.os, 'ubuntu') }}", "echo ${{ format('{0}-{1}', matrix.os, matrix.python) }}",
    "echo ${{ matrix.os == 'macos-15' && 'a.b' || 'c.d' }}", "echo ${{ true }}", "echo plain text", 'echo "$TAG"',
])
def test_safe_contexts_in_a_script_are_not_flagged(script):
    assert untrusted_in_run(synthetic({"run": script})) == []


@pytest.mark.parametrize("perms,expected", [
    ({"contents": "read"}, []),
    ({"contents": "write", "pull-requests": "none"}, []),
    (None, ["no top-level permissions table"]),
    ({}, ["no top-level permissions table"]),
    ("read-all", ["no top-level permissions table"]),
    ({"contents": "reed"}, ["contents: 'reed' is not read, write or none"]),
    ({"contents": True}, ["contents: True is not read, write or none"]),
])
def test_the_permissions_rule(perms, expected):
    wf = {"jobs": {}}
    if perms is not None:
        wf["permissions"] = perms
    assert permission_problems(wf) == expected


def test_a_release_upload_without_write_permission_is_found():
    upload = {"uses": "softprops/action-gh-release@v2"}
    assert cannot_write_release(synthetic(upload, permissions={"contents": "read"})) == ["j"]
    assert cannot_write_release(synthetic(upload)) == ["j"]                          # no permissions at all
    assert cannot_write_release(synthetic(upload, permissions={"contents": "write"})) == []
    assert cannot_write_release(synthetic(upload, permissions={"contents": "read"}, job_permissions={"contents": "write"})) == []
    assert cannot_write_release(synthetic(upload, permissions={"contents": "write"}, job_permissions={"contents": "read"})) == ["j"]
    assert cannot_write_release(synthetic({"uses": "actions/checkout@v4"}, permissions={"contents": "read"})) == []


def test_mentions_finds_a_name_in_env_keys_and_scripts_only_as_a_whole_word():
    wf = synthetic({"run": "SUTRA_LIVE=1 pytest", "env": {"SUTRA_BROWSER": "1"}}, env={"SUTRA_LIVE": "1"}, job_env={"OTHER": "x"})
    assert mentions(wf, "SUTRA_LIVE") == ["env", "jobs.j.steps[0].run"]
    assert mentions(wf, "SUTRA_BROWSER") == ["jobs.j.steps[0].env"]
    assert mentions(wf, "SUTRA") == [] and mentions(wf, "SUTRA_LIVE_X") == []


# ---------------------------------------------------------------- ci.yml

@pytest.fixture(scope="module")
def ci():
    return named("ci.yml")


def test_ci_is_named_ci_and_runs_on_push_to_main_pull_requests_and_manual_dispatch(ci):
    assert ci["name"] == "ci"
    on = triggers(ci)
    assert set(on) == {"push", "pull_request", "workflow_dispatch"}
    assert on["push"] == {"branches": ["main"]}, "a tag push must not run ci: the release workflow owns tags"
    assert not on["pull_request"], "pull requests of every branch run ci, with no path filter"
    slow = on["workflow_dispatch"]["inputs"]["slow"]
    assert slow["type"] == "boolean" and slow["default"] is False and "SUTRA_SLOW" in slow["description"]
    assert list(on["workflow_dispatch"]["inputs"]) == ["slow"]


def test_ci_reads_the_repository_and_cancels_superseded_runs(ci):
    assert ci["permissions"] == {"contents": "read"}
    assert ci["concurrency"] == {"group": "ci-${{ github.ref }}", "cancel-in-progress": True}


def test_ci_has_a_test_job_and_a_package_job_with_time_limits(ci):
    assert list(ci["jobs"]) == ["test", "package"]
    for job in ci["jobs"].values():
        assert isinstance(job["timeout-minutes"], int) and 0 < job["timeout-minutes"] <= 60


def test_ci_test_runs_on_ubuntu_and_macos_without_fail_fast(ci):
    job = ci["jobs"]["test"]
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"]["matrix"] == {"os": ["ubuntu-latest", "macos-15"]}
    assert job["strategy"]["fail-fast"] is False, "a macOS-only break must not be hidden by the ubuntu leg going red first"


def test_ci_test_sets_up_uv_and_node_20_with_pinned_majors(ci):
    job = ci["jobs"]["test"]
    assert [s["uses"] for s in steps_of(job) if "uses" in s] == ["actions/checkout@v4", "astral-sh/setup-uv@v5", "actions/setup-node@v4"]
    (node,) = action_steps(job, "actions/setup-node@")
    assert str(node["with"]["node-version"]) == "20"


def test_ci_test_installs_checks_the_plan_and_runs_the_local_gate_in_that_order(ci):
    run = commands(ci["jobs"]["test"])
    assert run == [
        "uv venv .venv --python 3.11",
        'uv pip install --python .venv/bin/python -e ".[dev]"',
        "scripts/py scripts/plan_tools.py check",
        "scripts/gate.sh",
        "SUTRA_SLOW=1 scripts/py -m pytest",
    ]


def test_ci_runs_the_gate_and_the_plan_check_unconditionally(ci):
    gated = [s for s in steps_of(ci["jobs"]["test"]) if "scripts/gate.sh" in s.get("run", "") or "plan_tools" in s.get("run", "")]
    assert len(gated) == 2 and all("if" not in s and "continue-on-error" not in s for s in gated)


def test_ci_runs_the_slow_suites_only_when_asked(ci):
    slow = [s for s in steps_of(ci["jobs"]["test"]) if "SUTRA_SLOW" in s.get("run", "")]
    assert len(slow) == 1
    assert slow[0]["if"].replace(" ", "") == "${{inputs.slow}}"
    assert mentions(ci, "SUTRA_SLOW") == ["jobs.test.steps[%d].run" % steps_of(ci["jobs"]["test"]).index(slow[0])]


def test_ci_package_builds_checks_installs_and_keeps_the_distribution(ci):
    job = ci["jobs"]["package"]
    assert job["runs-on"] == "ubuntu-latest"
    run = commands(job)
    assert run[0] == "uv venv .venv --python 3.11"
    assert run[1] == "uv build"
    assert run[2] == "scripts/py scripts/check_wheel.py dist/*.whl"
    install = run[3]
    assert 'uv venv "$RUNNER_TEMP/clean" --python 3.11' in install
    assert 'uv pip install --python "$RUNNER_TEMP/clean/bin/python" dist/*.whl' in install
    assert install.index("cd \"$RUNNER_TEMP\"") < install.index('"$RUNNER_TEMP/clean/bin/sutra-pro" --help'), "run it outside the checkout"
    assert len(run) == 4
    (upload,) = action_steps(job, "actions/upload-artifact@")
    assert upload["with"]["path"] == "dist/" and upload["with"]["name"] == "dist" and upload["with"]["if-no-files-found"] == "error"


def test_ci_package_does_not_run_the_test_suites(ci):
    assert not any("pytest" in c or "gate.sh" in c for c in commands(ci["jobs"]["package"]))


# ---------------------------------------------------------------- release-wheel.yml

@pytest.fixture(scope="module")
def rel():
    return named("release-wheel.yml")


def test_release_wheel_triggers_on_v_tags_and_manual_dispatch_with_a_tag_input(rel):
    assert rel["name"] == "release-wheel"
    on = triggers(rel)
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"tags": ["v*"]}, "tags only: a branch push must not release"
    tag = on["workflow_dispatch"]["inputs"]["tag"]
    assert tag["required"] is True and "already exist" in tag["description"]
    assert list(on["workflow_dispatch"]["inputs"]) == ["tag"]


def test_the_tag_filter_matches_release_tags_and_not_other_names(rel):
    pattern = triggers(rel)["push"]["tags"][0]
    for tag in ("v0.1.0", "v1.2.3-beta.1", "v10.0.0"):
        assert fnmatch.fnmatchcase(tag, pattern), tag
    for tag in ("0.1.0", "release-0.1.0", "V0.1.0", "x"):
        assert not fnmatch.fnmatchcase(tag, pattern), tag


def test_release_wheel_defaults_to_read_only_and_never_cancels_a_release_in_flight(rel):
    assert rel["permissions"] == {"contents": "read"}
    assert rel["concurrency"] == {"group": "release-wheel-${{ inputs.tag || github.ref_name }}", "cancel-in-progress": False}


def test_release_wheel_has_the_jobs_guard_build_verify_in_that_order_with_time_limits(rel):
    assert list(rel["jobs"]) == ["guard", "build", "verify"]
    for job in rel["jobs"].values():
        assert isinstance(job["timeout-minutes"], int) and 0 < job["timeout-minutes"] <= 30


def test_the_guard_is_first_runs_on_ubuntu_and_everything_else_waits_for_it(rel):
    jobs = rel["jobs"]
    assert list(jobs)[0] == "guard" and not needs_of(jobs["guard"])
    assert jobs["guard"]["runs-on"] == "ubuntu-latest"
    for job_id in ("build", "verify"):
        assert "guard" in needs_closure(rel, job_id), f"{job_id} can run before the guard has passed"
    assert needs_of(jobs["build"]) == ["guard"]
    assert sorted(needs_of(jobs["verify"])) == ["build", "guard"]


def test_the_guard_runs_check_release_tag_on_the_tag_through_env(rel):
    steps = [s for s in steps_of(rel["jobs"]["guard"]) if "check_release_tag.py" in s.get("run", "")]
    assert len(steps) == 1
    (step,) = steps
    assert step["env"] == {"TAG": "${{ inputs.tag || github.ref_name }}"}
    assert step["run"].strip() == 'scripts/py scripts/check_release_tag.py "$TAG"'
    assert "if" not in step, "the guard must run on pushes and on dispatches alike"


def test_the_guard_checks_the_format_before_it_prints_or_queries_a_dispatched_tag(rel):
    steps = steps_of(rel["jobs"]["guard"])
    order = [i for i, s in enumerate(steps) if "check_release_tag.py" in s.get("run", "")]
    exists = [i for i, s in enumerate(steps) if "ls-remote" in s.get("run", "")]
    assert len(order) == 1 and len(exists) == 1 and order[0] < exists[0]
    step = steps[exists[0]]
    assert step["if"] == "github.event_name == 'workflow_dispatch'"
    assert step["env"] == {"TAG": "${{ inputs.tag }}"}
    assert 'git ls-remote --exit-code --tags origin "refs/tags/$TAG"' in step["run"]


def test_the_guard_sets_up_the_python_that_scripts_py_needs(rel):
    run = commands(rel["jobs"]["guard"])
    assert run[0] == "uv venv .venv --python 3.11"
    assert [s["uses"] for s in steps_of(rel["jobs"]["guard"]) if "uses" in s] == ["actions/checkout@v4", "astral-sh/setup-uv@v5"]


def test_only_the_build_job_can_write(rel):
    assert "permissions" not in rel["jobs"]["guard"] and "permissions" not in rel["jobs"]["verify"]
    assert rel["jobs"]["build"]["permissions"] == {"contents": "write"}


def test_the_build_builds_checks_the_wheel_and_writes_a_checksum_for_each_asset(rel):
    job = rel["jobs"]["build"]
    assert job["runs-on"] == "ubuntu-latest"
    run = commands(job)
    assert run[:3] == ["uv venv .venv --python 3.11", "uv build", "scripts/py scripts/check_wheel.py dist/*.whl"]
    stage = run[3]
    assert 'shasum -a 256 "$asset" > "$asset.sha256"' in stage
    assert 'for asset in "$wheel" sutra_pro-py3-none-any.whl; do' in stage, "one checksum for the versioned wheel and one for the alias"
    assert 'cp "dist/$wheel" "release/$wheel"' in stage and 'cp "dist/$wheel" release/sutra_pro-py3-none-any.whl' in stage
    assert "exactly one wheel" in stage
    assert stage.index("shopt -s nullglob") < stage.index("wheels=(dist/*.whl)"), "an unmatched glob must count as zero, not as one"
    assert '[ "${#wheels[@]}" -eq 1 ]' in stage, "exactly one wheel, not at least one"


def test_the_build_checks_the_wheel_name_against_the_tag_through_env(rel):
    stage = next(s for s in steps_of(rel["jobs"]["build"]) if s.get("id") == "assets")
    assert stage["env"] == {"TAG": "${{ inputs.tag || github.ref_name }}"}
    assert 'want="${TAG#v}"' in stage["run"] and 'want="${want%-beta.*}"' in stage["run"]
    assert '"sutra_pro-$want-py3-none-any.whl"' in stage["run"]


def test_the_build_checks_the_wheel_before_it_names_or_uploads_anything(rel):
    run = [s.get("run", s.get("uses")) for s in steps_of(rel["jobs"]["build"])]
    positions = {key: next(i for i, text in enumerate(run) if key in text)
                 for key in ("uv build", "check_wheel.py", "shasum", "softprops/action-gh-release")}
    assert positions["uv build"] < positions["check_wheel.py"] < positions["shasum"] < positions["softprops/action-gh-release"]


def test_the_build_uploads_the_wheels_and_their_checksums_under_the_tag(rel):
    (upload,) = action_steps(rel["jobs"]["build"], "softprops/action-gh-release@")
    assert upload["uses"] == "softprops/action-gh-release@v2"
    with_ = upload["with"]
    assert with_["tag_name"] == "${{ inputs.tag || github.ref_name }}"
    assert with_["fail_on_unmatched_files"] is True
    assert with_["files"].split() == ["release/*.whl", "release/*.whl.sha256"]


def test_a_beta_tag_is_a_prerelease_and_a_stable_tag_is_not(rel):
    (upload,) = action_steps(rel["jobs"]["build"], "softprops/action-gh-release@")
    assert upload["with"]["prerelease"] == "${{ contains(inputs.tag || github.ref_name, '-beta.') }}"


def test_the_release_body_tells_how_to_install_and_names_the_assets(rel):
    (upload,) = action_steps(rel["jobs"]["build"], "softprops/action-gh-release@")
    body = upload["with"]["body"]
    assert "uv tool install https://github.com/${{ github.repository }}/releases/download/" in body
    assert "${{ steps.assets.outputs.wheel }}" in body and "sutra_pro-py3-none-any.whl" in body and "shasum -a 256 -c" in body


def test_verify_runs_on_ubuntu_and_macos_without_fail_fast(rel):
    job = rel["jobs"]["verify"]
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"]["matrix"] == {"os": ["ubuntu-latest", "macos-15"]}
    assert job["strategy"]["fail-fast"] is False


def test_verify_installs_the_published_wheel_not_the_one_the_build_made(rel):
    job = rel["jobs"]["verify"]
    assert [s["uses"] for s in steps_of(job) if "uses" in s] == ["astral-sh/setup-uv@v5"], "no checkout: only released files are used"
    download, checksums, install = commands(job)
    assert 'gh release download "$TAG" --repo "$GITHUB_REPOSITORY" --dir released' in download
    assert "--pattern '*.whl'" in download and "--pattern '*.whl.sha256'" in download
    assert 'shasum -a 256 -c "${checksums[@]}"' in checksums and 'cmp "${versioned[0]}" sutra_pro-py3-none-any.whl' in checksums
    assert 'uv venv "$RUNNER_TEMP/fresh" --python 3.11' in install
    for script in (checksums, install):
        assert script.index("shopt -s nullglob") < script.index("=("), "an unmatched glob must count as zero, not as one"
    assert '[ "${#checksums[@]}" -eq 2 ]' in checksums and '[ "${#versioned[@]}" -eq 1 ]' in checksums
    assert '[ "${#wheels[@]}" -eq 1 ]' in install
    assert 'uv pip install --python "$RUNNER_TEMP/fresh/bin/python" "${wheels[0]}"' in install
    assert install.index('cd "$RUNNER_TEMP"') < install.index('"$RUNNER_TEMP/fresh/bin/sutra-pro" --help')


def test_verify_downloads_with_the_workflow_token_through_env(rel):
    step = next(s for s in steps_of(rel["jobs"]["verify"]) if "gh release download" in s.get("run", ""))
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}", "TAG": "${{ inputs.tag || github.ref_name }}"}


def test_release_wheel_names_the_two_assets_it_promises(rel):
    text = (WORKFLOWS / "sutra-pro-release-wheel.yml").read_text()
    assert "sutra_pro-py3-none-any.whl" in text and "-py3-none-any.whl" in text


def test_neither_workflow_uses_a_secret_other_than_the_workflow_token():
    for name in ("ci.yml", "release-wheel.yml"):
        assert [text for text in strings(named(name)) if "secrets." in text] == [], name


# ---------------------------------------------------------------- docs/RELEASE.md

def test_the_release_doc_names_the_workflows_jobs_assets_and_commands_that_exist():
    doc = (ROOT / "docs" / "RELEASE.md").read_text()
    for workflow, wf in (("ci", named("ci.yml")), ("release-wheel", named("release-wheel.yml"))):
        assert wf["name"] == workflow
        for job_id in wf["jobs"]:
            assert f"**{workflow} / {job_id}" in doc, f"docs/RELEASE.md does not describe {workflow} / {job_id}"
    for needle in ("sutra_pro-py3-none-any.whl", "sutra_pro-X.Y.Z-py3-none-any.whl", "vX.Y.Z-beta.N", "uv tool install",
                   "gh workflow run release-wheel -f tag=vX.Y.Z --ref vX.Y.Z", "shasum -a 256 -c", "REL-2", "check_wheel.py",
                   "check_release_tag.py", "SUTRA_SLOW=1"):
        assert needle in doc, f"docs/RELEASE.md does not mention {needle!r}"
    assert "sutra_pro-py3-none-any.whl" in (WORKFLOWS / "sutra-pro-release-wheel.yml").read_text()


def test_the_repair_command_in_the_doc_is_the_one_the_guard_prints():
    doc = (ROOT / "docs" / "RELEASE.md").read_text()
    assert "gh workflow run release-wheel -f tag=vX.Y.Z --ref vX.Y.Z" in doc
    assert "gh workflow run release-wheel -f tag=vX.Y.Z --ref vX.Y.Z" in (WORKFLOWS / "sutra-pro-release-wheel.yml").read_text()
