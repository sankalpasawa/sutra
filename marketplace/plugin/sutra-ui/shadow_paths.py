"""ONE WORKING DIRECTORY. The worker's and Shadow's must be the same one.

THE FAILURE THIS CLOSES (founder, 2026-09-21). A worker finished a dashboard
task in ONE turn. Shadow then spent five more worker turns because it could
not find the artifact -- and the artifact had never moved. Shadow asked the
worker to relocate a correct file, which created a real mismatch, which
Shadow then investigated across further turns with `pwd`, `stat`, `find` and
`realpath`. Every one of those turns was spent on Shadow's own confusion.

THE MECHANISM, and it is two lines of drift:

    app._shadow_workdir_for_delegates()   settings["workdir"] or WORKDIR
    shadow_probe.default_root()           settings["workdir"] or ""

`shadow_probe`'s comment said "SAME SOURCE as
app._shadow_workdir_for_delegates ... so reading it here cannot drift from
the directory the delegate is actually spawned in". It was not the same
source: it dropped the fallback. With `workdir` unset the WORKER runs in
`~/sutra-ui-workspace` and the PROBE resolves against `""`, which raises
ProbeUnsafe("no workdir configured") -- and `run()` turns that into
`met=False`, which is indistinguishable from "the worker did not do it".

So Shadow read its own misconfiguration as a worker failure and drove the
worker at it. Measured: `run({"kind":"file_exists",...}, "")` returns
`met=False, reason="probe refused: no workdir configured"` -- a verdict on
the WORK, produced by a fault in the VERIFIER.

THE RULE. There is one authoritative root and one resolver, and every probe,
evidence reader and decision packet goes through them. A component that
invents its own root is how the worker and the supervisor end up looking at
different directories, which is the whole bug.

WHAT THIS MODULE IS NOT. It is not a search path: it resolves ONE root and
confines to it. It never looks for an artifact in a second location, never
falls back to another directory when a file is absent, and never copies or
moves anything. "Shadow could not find it here" is an answer; "Shadow found
it somewhere else" is how artifacts start migrating.
"""

import os

#: The last-resort root, byte-identical to app.WORKDIR's own default. THIS
#: CONSTANT IS THE FIX: the fallback existed on the worker's side and not on
#: the verifier's, and that asymmetry is what let the two drift.
DEFAULT_WORKDIR = "~/sutra-ui-workspace"

#: The env override app.WORKDIR honours, honoured here for the same reason.
WORKDIR_ENV = "SUTRA_UI_WORKDIR"


def _clean(value):
    value = str(value or "").strip()
    return os.path.expanduser(value) if value else ""


def mission_artifact_root(mission=None):
    """THE authoritative working directory for this mission's artifacts.

    ORDER, and every step is the same one the worker's spawn takes:

      1. the mission's OWN stamped workdir, when it has one. A mission that
         recorded where it ran is the strongest possible statement about
         where its artifacts are, and it survives a settings change made
         after the work was done.
      2. the founder's configured workdir (providers.load_settings)
      3. $SUTRA_UI_WORKDIR
      4. DEFAULT_WORKDIR

    NEVER RETURNS "" WHEN A DIRECTORY CAN BE NAMED, which is the specific
    regression this exists to prevent: an empty root makes every probe refuse
    itself, and a refused probe used to read as a failed check.

    NEVER RAISES. A settings file that cannot be read costs the configured
    value, never the answer.
    """
    if isinstance(mission, dict):
        got = _clean(mission.get("workdir") or mission.get("artifact_root"))
        if got:
            return got
    try:
        import providers
        got = _clean((providers.load_settings() or {}).get("workdir"))
        if got:
            return got
    except Exception:                    # noqa: BLE001 -- fall through
        pass
    got = _clean(os.environ.get(WORKDIR_ENV))
    return got or _clean(DEFAULT_WORKDIR)


class ArtifactUnsafe(Exception):
    """The path does not resolve inside the mission's root.

    NOT A VERDICT ON THE WORK -- callers turn it into a VERIFIER error, never
    into "the worker did not do it". That distinction is the point of this
    whole module.
    """


def resolve_artifact(path, mission=None, root=None):
    """The real path this names inside the mission's root, or ArtifactUnsafe.

    ONE COMPARISON, AFTER realpath, exactly as shadow_probe.resolve does --
    and shadow_probe.resolve now delegates here so there is one answer rather
    than two that can drift. realpath collapses `..`, a symlinked leaf and a
    symlinked parent into the same question: does the resolved path still sit
    under the resolved root.

    The ROOT is realpath'd too: on macOS the obvious workdirs are reached
    through symlinks (/tmp -> /private/tmp) and comparing a resolved path
    against an unresolved root would refuse every legitimate artifact.

    A path with SPACES, a relative path and an absolute path that lands
    inside are all ordinary and all allowed; nothing here is expanduser'd,
    because an artifact path is a location in the workdir and not a shell
    word.
    """
    root = _clean(root) or mission_artifact_root(mission)
    if not root:
        raise ArtifactUnsafe("no workdir configured")
    real_root = os.path.realpath(root)
    if not os.path.isdir(real_root):
        raise ArtifactUnsafe("workdir does not exist: %s" % real_root)
    path = str(path or "")
    if "\x00" in path:
        raise ArtifactUnsafe("path contains NUL")
    candidate = path if os.path.isabs(path) else os.path.join(real_root, path)
    try:
        real = os.path.realpath(candidate)
    except OSError as exc:               # pragma: no cover -- ELOOP etc
        raise ArtifactUnsafe("unresolvable path: %s" % exc)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise ArtifactUnsafe("path escapes the workdir")
    return real


def agrees_with_worker(mission=None):
    """(ok, detail) -- does the verifier's root match the worker's spawn cwd?

    THE ASSERTION THE OLD COMMENT MADE AND THE CODE DID NOT KEEP. It is a
    diagnostic rather than a guard: callers report the mismatch as a VERIFIER
    fault, which is what stops it reaching the worker as corrective work.

    Imported lazily and never raises -- app pulls in the world, and this is
    called from the engine.
    """
    mine = mission_artifact_root(mission)
    try:
        import app
        theirs = _clean(app._shadow_workdir_for_delegates())
    except Exception as exc:             # noqa: BLE001 -- cannot compare
        return True, "worker cwd unavailable (%s)" % str(exc)[:60]
    if not theirs:
        return True, "worker cwd unavailable"
    if os.path.realpath(mine) == os.path.realpath(theirs):
        return True, mine
    return False, ("verifier root %s is not the worker's cwd %s"
                   % (mine, theirs))


# ─────────────────────────── ARTIFACT OWNERSHIP ──────────────────────────
#
# THE FAILURE THIS CLOSES (founder, 2026-09-21). A Europe trip mission's
# decision surface showed `marc-marquez.txt`, `motogp-top-10-news.md`,
# `weight-loss-plan.html` and several of Shadow's own source files. None
# belonged to that mission. Reproduced exactly: twelve candidate paths for a
# mission whose only criterion was about an itinerary.
#
# THE MECHANISM. `shadow_decision.candidate_paths` and
# `shadow_judge.evidence_for` both treated "untracked in the working
# directory" as "produced by this mission". In a shared workdir -- which is
# the normal case, because every mission runs in the founder's repo -- that
# is every file any previous mission ever created, plus anything the founder
# happens to be editing.
#
# WHY IT WAS WRONG EVEN WHEN IT LOOKED RIGHT. git status answers "what is not
# committed", which has NOTHING to do with which mission made it. The two
# coincide only when exactly one mission has ever run in that directory. It
# was introduced to let the judge see a newly created file (the MotoGP
# artifact-lane fix) and it did solve that -- by giving every mission access
# to every other mission's output.
#
# THE RULE NOW: a mission may consume an artifact only if it OWNS it, and
# ownership is explicit. Discovery is not ownership. A file that merely
# exists near the work is not evidence about the work.

def owned_artifacts(mission):
    """The paths this mission may read as its own. THE ONLY SOURCE.

    TWO WAYS TO OWN A FILE, and both are explicit statements by Shadow about
    THIS mission:

      1. a path named by one of this mission's own probes. The decider wrote
         that probe as part of this contract, so the path is part of what the
         mission was asked to produce.
      2. a path on the mission's own `artifacts` list, when something upstream
         recorded one deterministically.

    WHAT IS NOT HERE, and its absence is the fix: no git status, no directory
    walk, no glob, no mtime heuristic, no filename similarity. A file nobody
    associated with this mission does not exist to it -- which is the honest
    answer, because Shadow genuinely does not know whose it is.

    NEVER RAISES; an unreadable record simply owns nothing.
    """
    out = []
    if not isinstance(mission, dict):
        return out

    def _add(path):
        path = str(path or "").strip()
        if path and path not in out:
            out.append(path)

    for path in (mission.get("artifacts") or []):
        _add(path)
    try:
        import mission_engine
        for c in (mission.get("done_when") or []):
            if not isinstance(c, dict):
                continue
            for probe in mission_engine.probes_of(c):
                _add(probe.get("path"))
    except Exception:                    # noqa: BLE001 -- fewer paths, not fatal
        pass
    return out
