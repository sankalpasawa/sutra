"""test_update_swap_nesting.py -- the installer never moves the new bundle INSIDE the old one.

The failure this pins happened to the owner on 2026-09-24. He clicked update, the
app went away, and it never came back. What was left in /Applications was

    Sutra.app/
      Contents/Resources/payload/...        <- stale leftovers, no Contents/MacOS
      Sutra.app.new-50908/                  <- the complete, valid 2.300.0 bundle

so macOS had a Sutra.app with nothing to launch, and the whole new version was
sitting one level too deep inside it.

THE DEFECT IS ONE LINE OF SHELL SEMANTICS. `mv src dst` replaces dst when dst is
a file, but when dst is an EXISTING DIRECTORY it moves src *into* it -- and exits
0 doing so. The helper's swap read that exit 0 as "installed": it deleted its
recovery breadcrumb, deleted the backup it could have rolled back to, wrote
install-result.json saying success, and relaunched into a bundle with no
executable. Every gate before it (codesign, team id, bundle id, version) had
passed, because none of them looks at where the bundle landed.

`mv "$APP" "$BAK"` is supposed to guarantee $APP is gone before the second mv, so
the second mv is only ever a rename. It did not, and "supposed to" was the entire
protection. The trigger for $APP surviving could not be reconstructed afterwards
(the staging directory had already cleaned itself up), which is precisely why the
swap has to check rather than assume: the step cannot tell a rename from a nest,
so it must not be the thing deciding whether the install worked.

Three things are pinned here:

  1. The shell behaviour itself, so nobody "simplifies" the guard away believing
     mv refuses an existing directory. It does not; it nests, and returns 0.
  2. The swap REFUSES when $APP still exists after being moved aside, restores
     the old bundle, and exits non-zero. Nothing is nested.
  3. A bundle that lands without a runnable executable is rolled back, not
     reported as installed -- checked while the backup still exists.

Run: .venv/bin/python -m pytest -q test_update_swap_nesting.py
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>App</string>
</dict></plist>
"""


def _swap_block():
    """The swap half of the installer helper, lifted out of updates.py verbatim.

    Read from the real file rather than copied here, so the test cannot drift
    away from the code it is protecting: edit the helper and this test runs the
    edit.
    """
    src = (HERE / "updates.py").read_text(encoding="utf-8")
    start = src.index('if ! mv "$APP" "$BAK"; then')
    end = src.index('rm -rf "$BAK"', start) + len('rm -rf "$BAK"')
    return src[start:end]


def _bundle(path, with_exe=True):
    (path / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (path / "Contents" / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")
    if with_exe:
        exe = path / "Contents" / "MacOS" / "App"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)


def _run(tmp, move_aside, with_exe=True):
    """Run the real swap block with `move_aside` standing in for `mv $APP $BAK`.

    That one line is the variable: in the healthy case it removes $APP, and in
    the 2026-09-24 case it reported success and left $APP standing.
    """
    app = tmp / "App.app"
    stage_setup = 'STAGE="${APP}.new-$$"\nBAK="${APP}.old-$$"\nRECOVER="$TMP/recover.json"\n'
    script = (
        "set -u\n"
        'die() { echo "DIE[$1] $2" >&2; exit 1; }\n'
        'APP="$TMP/App.app"\n' + stage_setup +
        'mkdir -p "$STAGE/Contents/MacOS"\n'
        'cp "$APP/Contents/Info.plist" "$STAGE/Contents/Info.plist"\n'
        + ('printf "#!/bin/sh\\n" > "$STAGE/Contents/MacOS/App"; chmod +x "$STAGE/Contents/MacOS/App"\n'
           if with_exe else "")
        + 'echo "{}" > "$RECOVER"\n'
        # the line under test's control, swapped in per case
        + move_aside + "\n"
        + _swap_block().replace('if ! mv "$APP" "$BAK"; then\n'
                                '  rm -f "$RECOVER"; rm -rf "$STAGE"; die swap "could not move the old bundle aside"\n'
                                'fi\n', "")
        + '\necho INSTALLED_OK\n'
    )
    return subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True,
                          env={**os.environ, "TMP": str(tmp)}), app


def test_mv_nests_into_an_existing_directory_and_returns_zero():
    """The shell behaviour the whole guard exists for. If this ever stops being
    true the guard is still harmless, but the reason for it is gone."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "App.app" / "Contents").mkdir(parents=True)
        (tmp / "App.app.new-1" / "Contents").mkdir(parents=True)
        r = subprocess.run(["/bin/mv", str(tmp / "App.app.new-1"), str(tmp / "App.app")],
                           capture_output=True, text=True)
        assert r.returncode == 0, "mv reported failure; the premise has changed"
        assert (tmp / "App.app" / "App.app.new-1").is_dir(), \
            "mv did not nest, so the 2026-09-24 layout is no longer reachable this way"


def test_healthy_swap_installs_and_leaves_nothing_behind():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bundle(tmp / "App.app")
        r, app = _run(tmp, 'mv "$APP" "$BAK"')
        assert "INSTALLED_OK" in r.stdout, r.stderr
        assert (app / "Contents" / "MacOS" / "App").exists()
        assert not list(tmp.glob("App.app.new-*")), "a stage copy was left behind"
        assert not list(tmp.glob("App.app.old-*")), "a backup was left behind"
        assert not list(app.glob("App.app.new-*")), "the new bundle was nested"


def test_app_surviving_the_move_aside_is_refused_not_nested():
    """The 2026-09-24 bug. The move-aside 'succeeds' but $APP is still there."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bundle(tmp / "App.app")
        # copy instead of move: exit 0, $APP still standing -- the observed state
        r, app = _run(tmp, 'cp -R "$APP" "$BAK"')
        assert "INSTALLED_OK" not in r.stdout, "a nesting swap was reported as installed"
        assert "still exists after being moved aside" in r.stderr, r.stderr
        assert not list(app.glob("App.app.new-*")), \
            "the new bundle was moved INSIDE the old one -- the original defect"
        assert (app / "Contents" / "MacOS").exists(), "the old bundle was not put back"
        assert not list(tmp.glob("App.app.old-*")), "the backup was left behind"


def test_bundle_without_an_executable_is_rolled_back():
    """A swap can exit 0 and still leave something that cannot launch. That is
    the difference the user actually experiences, so it is checked before the
    backup is thrown away."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _bundle(tmp / "App.app")
        r, app = _run(tmp, 'mv "$APP" "$BAK"', with_exe=False)
        assert "INSTALLED_OK" not in r.stdout, "an unlaunchable bundle was reported as installed"
        assert "no runnable executable" in r.stderr, r.stderr
        assert (app / "Contents" / "MacOS" / "App").exists(), \
            "the old, working bundle was not restored"


def test_the_guard_is_present_in_the_shipped_helper():
    """Pins the guard in updates.py itself, so removing it fails here even if
    somebody rewrites the test harness above."""
    src = (HERE / "updates.py").read_text(encoding="utf-8")
    assert re.search(r'if \[ -e "\$APP" \]; then', src), \
        "the existence check before the second mv is gone"
    assert "CFBundleExecutable" in src, \
        "the post-swap executable check is gone"
