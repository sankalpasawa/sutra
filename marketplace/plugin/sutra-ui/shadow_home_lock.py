"""One recoverer per Shadow home (founder, 2026-09-16).

THE GAP THIS CLOSES. Nothing stopped two Shadow backends from booting against
one shadow home. `app._shadow_recover()` runs an unguarded boot sequence --
recover_on_boot, _clear_stale_start_requests, the stall watch, the two
setters, resume_after_restart, drain_queue -- and every step of it mutates the
shared mission store. The per-mission `loop_pid` lease in shadow_runner was
added after the incident its own docstring records ("five app boots in eight
seconds each re-adopted the same mission"), but it fences the mission LOOP,
and boot does damage before any loop exists. Two examples nothing else catches:

  * _clear_stale_start_requests() strips `start_requested_at` from every draft
    and brief_confirm mission, so a second app booting while the first has a
    start in flight erases the first one's stamp.
  * boot drain_queue -> _promote_after_slot_freed -> MissionEngine.
    provision_target, which checks `if m.get("target_session"): return` BEFORE
    it awaits the spawner -- and the spawner sends the manifest and waits out
    an entire first agentic turn. Two boots both pass that check and both
    spawn a real Claude delegate for one mission. The loop lease cannot help:
    it is consulted in _launch, which runs AFTER the spawn returns. The losing
    save then raises the stale-seq ValueError and the mission goes `failed`,
    leaving an orphan worker behind it.

NOT THE SAME THING AS THE LOOP LEASE, and neither subsumes the other:

    shadow_runner.loop_held_elsewhere()   one DRIVER per mission, at any time
    claim_recovery() (here)               one RECOVERER per home, at boot

The lease still catches a founder Start/Resume/answer landing on a server that
does not hold this lock -- app.py calls shadow_runner._launch directly from
the intervention route. This lock still catches everything boot does before
any loop exists. Keep both.

A LEASE, NOT OWNERSHIP, and the name is deliberate. Plenty of processes write
this home without holding this: every sutra_mcp.py child appends to the
ledger, and the founder's own server drives missions. Gating a ledger write on
this would deadlock the MCP child. What it gates is RECOVERY -- the boot
block, and nothing else. _launch, MissionScheduler.start and the
founder-triggered drains are deliberately ungated (a founder pressing Start in
a window they are looking at deserves a refusal they can see, not a silent
no-op; and the cap is computed from the shared store, so aggregate safety
holds regardless of who computes it).

FLOCK, NOT A PIDFILE. Electron SIGKILLs the uvicorn child on quit, so no
release hook can be relied on; the kernel drops an flock when the process
dies, whatever killed it. routines.py:390 uses mkdir+pid and needs a
STALE_AFTER heuristic for exactly that reason -- and a shadow home is
legitimately held for days, so no timeout would be correct here.

THE LOCK FILE LIVES INSIDE THE HOME. Beta (~/.sutra-ui-beta/shadow) and stable
therefore get separate leases for free, and pytest's temp-home redirect
isolates every test for free. No new env var, so test_channel_isolation's
sweep of backend data-path variables is unaffected.
"""
import asyncio
import errno
import fcntl
import json
import os
import time

import shadow_ledger

LOCK_NAME = ".recovery.lock"

#: fd of the held lease, and the home it belongs to.
#:
#: THIS MODULE HOLDS IT, AND THAT IS THE REASON THIS MODULE EXISTS.
#: test_shadow_say.py reloads shadow_ledger mid-run while a uvicorn is up on
#: the same home, and importlib.reload zeroes module globals with the fd still
#: open and now unreferenced. On macOS flock conflicts across two fds in ONE
#: process, so the next claim would fail against itself and (fail-open aside)
#: read as a rival that does not exist. Nothing reloads this module. It also
#: keeps the question cheap to ask: shadow_runner pulls in mission_engine,
#: session_reader, providers, shadow_feed and session_runtime, and a status
#: probe should not have to import the mission engine to learn who is
#: recovering.
_LOCK = {"fd": None, "home": None}

#: the re-arm task, and whether a win has already run recovery. Singleton, the
#: same shape as shadow_runner._STALL_TASK.
_REARM = {"task": None, "done": False}


def _home():
    """The home this lease belongs to, fully resolved.

    REALPATH, not the raw env value: macOS tempfile.mkdtemp() hands back
    /var/folders/... whose realpath is /private/var/folders/..., and comparing
    raw strings would make one home look like two -- a needless release and
    re-acquire, and every one of those is a window where nobody holds it.
    """
    return os.path.realpath(shadow_ledger.shadow_home())


def _lock_path(home):
    return os.path.join(home, LOCK_NAME)


def recovery_holder():
    """Who the lock file says holds the lease, or None.

    ADVISORY, ALWAYS. This is for the refusal message and the status pane; it
    is never the basis of the decision. The decision is flock's and only
    flock's -- a record can be stale, truncated or garbage, and a pid in a
    file proves nothing about a live process.
    """
    try:
        with open(_lock_path(_home()), encoding="utf-8") as handle:
            row = json.load(handle)
        return row if isinstance(row, dict) else None
    except (OSError, ValueError, RuntimeError):
        return None


def holds_recovery():
    """Does THIS process hold the lease for the home resolving right now?"""
    if _LOCK["fd"] is None:
        return False
    try:
        return _LOCK["home"] == _home()
    except RuntimeError:                # shadow_home() refuses under pytest
        return False


def release_recovery():
    """Drop the lease.

    Best-effort: the kernel does this on process death anyway, so a failure
    here costs nothing. shadow_runner.shutdown() calls it so a clean restart
    does not race the kernel's cleanup for its own successor.
    """
    fd = _LOCK["fd"]
    _LOCK["fd"] = None
    _LOCK["home"] = None
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _write_record(fd, home):
    """Stamp who we are into the file we now hold.

    Advisory data for the refusal message and the status pane -- never
    load-bearing, so failing to write it does not lose the lease we already
    hold.

    FTRUNCATE FIRST: a shorter record written over a longer one leaves
    trailing bytes and the next reader gets garbage JSON. The holder pid is
    the only forensic value this file has; keep it parseable.
    """
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, (json.dumps({
            "pid": os.getpid(),
            "build": shadow_ledger.build_id(),
            "home": home,
            "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }) + "\n").encode("utf-8"))
        os.fsync(fd)
    except (OSError, ValueError):
        pass


def claim_recovery():
    """Try to become the one process recovering this home.

    Returns (owned, holder). `owned` True means go ahead and run the boot
    block; `holder` is the advisory record of whoever refused us, or None.

    IDEMPOTENT. Already holding this home returns True without touching the
    file, so the in-function guards in shadow_runner cost nothing once app.py
    has claimed. Holding a DIFFERENT home releases the old one first -- the
    test lanes swap SUTRA_SHADOW_HOME between cases, and a lease on last
    case's tempdir must not answer for this one.

    FAILS OPEN ON EVERYTHING THAT IS NOT A RIVAL, which is the rule every
    other guard in this subsystem follows (_app_process_alive "FAILS OPEN",
    loop_held_elsewhere "never raises"). Only EWOULDBLOCK/EAGAIN means
    "someone else has it". EROFS, ENOLCK, EOPNOTSUPP (NFS, SMB, exFAT) and
    EACCES all mean "there is no lock service here", which is not evidence of
    a rival: refusing on those would silently disable boot recovery forever on
    those installs, and a silent permanent loss of recovery is a far worse
    outcome than the duplicate this module exists to prevent.
    """
    try:
        home = _home()
    except RuntimeError:
        # shadow_home() refuses the live home under pytest. Not a rival, and
        # not ours to re-raise here -- the caller hits it on its own next
        # store access, where the message is about the store.
        return True, None
    if _LOCK["fd"] is not None:
        if _LOCK["home"] == home:
            return True, None
        release_recovery()
    try:
        # makedirs FIRST. shadow_home() does not create the home -- only
        # _path() and mission_engine._home() do, and only for their own
        # subdirs -- so on a fresh install the very first claim would land on
        # ENOENT before MissionStore had ever touched the disk.
        os.makedirs(home, exist_ok=True)
        # O_CLOEXEC EXPLICITLY, not inherited from PEP 446's default. This
        # process spawns claude children with start_new_session=True that
        # deliberately outlive the app; an fd leaked into one of those would
        # hold this flock in an orphan forever and NO future app could ever
        # recover this home -- the exact stale-lock failure flock was chosen
        # to avoid. Too important to leave to an interpreter default a future
        # refactor could step around.
        fd = os.open(_lock_path(home),
                     os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0),
                     0o600)
    except OSError:
        return True, None               # no lock service here -- proceed
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        try:
            os.close(fd)
        except OSError:
            pass
        if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return False, recovery_holder()     # a real rival holds it
        return True, None               # no lock service here -- proceed
    _LOCK["fd"] = fd
    _LOCK["home"] = home
    _write_record(fd, home)
    return True, None


def start_rearm(run_recovery, interval=30):
    """Poll for the lease until we win it, then run recovery ONCE.

    WHY THIS IS NOT OPTIONAL. app._shadow_recover() is the only caller of the
    boot block and it runs once, at startup, so without a re-arm a refusal is
    permanent for the life of the process. The losing case is common, not
    exotic:

      * a crashloop or a port fight, where whoever won the lock is frequently
        the instance that then dies -- which is the exact shape of the "five
        app boots in eight seconds" incident;
      * the self-update path, where electron/main.js launches the replacement
        app (`open -n -a`) while the old backend may still hold the lease, and
        the old one then quits.

    In both, today's code recovers those missions. A bare refusal would strand
    them paused forever -- a strict regression in precisely the scenario this
    feature exists for.

    SINGLETON, and the same idiom as shadow_runner.start_stall_watch(): a
    repeat call reuses the live task. `done` latches, so a win runs recovery
    exactly once however many times this is called.

    NOT AN INLINE RETRY. electron's waitForOwnBackend fails the whole app
    after 45s, and a startup event blocks the port from accepting, so blocking
    here risks a dead launch instead of a late recovery.
    """
    if _REARM["done"]:
        return None
    task = _REARM.get("task")
    if task is not None and not task.done():
        return task

    async def loop():
        while not _REARM["done"]:
            await asyncio.sleep(interval)
            try:
                owned, _holder = claim_recovery()
            except Exception:           # noqa: BLE001 -- keep polling
                continue
            if not owned:
                continue
            _REARM["done"] = True
            try:
                await run_recovery()
            except Exception:           # noqa: BLE001 -- recorded by the
                pass                    # callee's own ledger rows
            return

    try:
        task = asyncio.get_event_loop().create_task(loop())
    except RuntimeError:                # no running loop (a sync caller)
        return None
    _REARM["task"] = task
    return task


def stop_rearm():
    """Cancel the re-arm poll. Called from shadow_runner.shutdown()."""
    task = _REARM.get("task")
    if task is not None:
        task.cancel()
    _REARM["task"] = None
