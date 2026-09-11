"""A Shadow delegate becomes a NORMAL Sutra chat -- publication + ownership.

WHAT THIS PINS
--------------
The product contract for the first Shadow -> Chat slice, at the two seams it
actually lives in:

  PUBLICATION   a delegate that really started becomes discoverable through
                the EXISTING chats inventory (chat_store's reverse index, which
                app._owned_transcripts calls "the whole definition of a Sutra
                chat"), titled "Shadow Task -- <task>", linked to its mission --
                and a delegate that did NOT start publishes nothing.

  OWNERSHIP     at most ONE Sutra runtime may write to one Claude session.
                shadow_runner.driving() is the one read, release_delegate() is
                the one reaper, and the fence survives a restart by being
                rebuilt from mission state already on disk (target_mode ==
                "new" + non-terminal) rather than from any new store.

WHY THE ORDER INSIDE publish() IS TESTED AND NOT JUST THE OUTCOME. The
mission's target_session is written FIRST, before anything visible exists,
because provision_target only writes it after the spawner returns -- a crash
in that window would leave a chat in the rail that no durable record names,
which is exactly what recover_on_boot() rebuilds ownership from. begin_segment
is written LAST, because the index row is the only visible write, so no
partial failure can show a chat whose record is missing.

The fake CLI and the registry/teardown discipline are lifted from
test_shadow_delegate.py deliberately -- same seam, same hygiene, so a leaked
delegate cannot outlive a lane.

stdlib only: unittest + asyncio.run(), matching test_shadow_delegate.py.

Run: ./run-tests.sh test_shadow_chat_publication.py
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

# IMPORT-TIME ISOLATION, before `import app`. Same reason and same keys as
# test_shadow_delegate.py: app.py runs _ensure_workdir() at module level, and
# chat_store / shadow_ledger resolve their homes from env. SUTRA_UI_CHATS is
# the addition -- this lane WRITES chat records, and it must never touch the
# operator's own ~/.sutra-ui/chats.
_ENV_TMP = tempfile.mkdtemp(prefix="shadow-chatpub-env-")
os.environ["SUTRA_UI_WORKDIR"] = os.path.join(_ENV_TMP, "workspace")
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_NATIVE_HOME"] = os.path.join(_ENV_TMP, "native")
os.environ["SUTRA_SHADOW_HOME"] = os.path.join(_ENV_TMP, "shadow")
os.environ["SUTRA_UI_CHATS"] = os.path.join(_ENV_TMP, "chats")

import app                      # noqa: E402  (env above must be set first)
import chat_store               # noqa: E402
import mission_engine           # noqa: E402
import session_runtime          # noqa: E402
import shadow_runner            # noqa: E402


# Claude's stream-json, just enough of it -- lifted from
# test_shadow_delegate.FAKE_OK. argv[1] is a turn log; argv[2] is the
# ~/.claude/projects stand-in this fake writes its transcript into, so
# session_reader can resolve the id the way it resolves a real one.
FAKE_OK = r"""#!/usr/bin/env python3
import json, os, sys
log, projects = sys.argv[1], sys.argv[2]
sid = "pubfake-%d" % os.getpid()
proj = os.path.join(projects, "-tmp-project")
os.makedirs(proj, exist_ok=True)
tr = os.path.join(proj, sid + ".jsonl")
def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    try:
        frame = json.loads(line)
    except ValueError:
        continue
    try:
        msg = frame["message"]["content"][0]["text"]
    except Exception:
        msg = ""
    with open(log, "a") as handle:
        handle.write(json.dumps({"msg": msg}) + "\n")
    # a REAL transcript record, so resolve_path/append_title/_claude_session_meta
    # all behave as they do against claude's own tree
    with open(tr, "a") as handle:
        handle.write(json.dumps({"type": "user", "sessionId": sid,
                                 "cwd": "/tmp/project",
                                 "message": {"role": "user", "content": msg}}) + "\n")
    emit({"type": "system", "subtype": "init", "session_id": sid,
          "model": "fake", "tools": [], "mcp_servers": [],
          "slash_commands": [], "permissionMode": "plan", "cwd": os.getcwd()})
    emit({"type": "stream_event", "session_id": sid,
          "event": {"delta": {"type": "text_delta", "text": "ok"}}})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "session_id": sid, "duration_ms": 1, "num_turns": 1,
          "total_cost_usd": 0.0})
"""

# Accepts the manifest turn and dies WITHOUT a `result`: the boot-failure path.
FAKE_DEAD = r"""#!/usr/bin/env python3
import sys
sys.stdin.readline()
"""


def _write_fake(directory, body, name):
    path = os.path.join(directory, name)
    with open(path, "w") as handle:
        handle.write(body)
    os.chmod(path, 0o755)
    return path


class Base(unittest.TestCase):
    """A delegate spawn against the fake CLI, with everything it touches
    pointed at a temp dir and reaped afterwards."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shadow-chatpub-")
        self.log = os.path.join(self.tmp, "turns.jsonl")
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(self.projects, exist_ok=True)
        self.fake = _write_fake(self.tmp, FAKE_OK, "fake-claude")
        self.dead = _write_fake(self.tmp, FAKE_DEAD, "dead-claude")
        self.registered = []
        self.sids = []
        self.store = mission_engine.MissionStore()
        # session_reader reads ONE tree; point it at the fake's
        import session_reader
        self._projects_was = session_reader.PROJECTS
        session_reader.PROJECTS = __import__("pathlib").Path(self.projects)
        # the delegate cwd the publisher stamps on the chat record
        self._workdir_was = app._shadow_workdir_for_delegates
        app._shadow_workdir_for_delegates = lambda: self.tmp

    def tearDown(self):
        import session_reader
        session_reader.PROJECTS = self._projects_was
        app._shadow_workdir_for_delegates = self._workdir_was
        # A leaked delegate is a live subprocess, so this is not optional.
        for _sid, rt in self.registered:
            try:
                rt.kill_group()
                rt.clear()
            except Exception:
                pass
        for sid in self.sids:
            session_runtime.RUNTIMES.pop(sid, None)
            shadow_runner.DELEGATES.pop(sid, None)
            shadow_runner._BOUNDARIES.pop(sid, None)
            shadow_runner._RECENT_TEXT.pop(sid, None)
            shadow_runner._LAST_FRAME_TS.pop(sid, None)
        shadow_runner._OBSERVED.clear()
        shadow_runner._ORPHANED.clear()

    def _register(self, sid, rt):
        self.registered.append((sid, rt))
        self.sids.append(sid)
        session_runtime.register_runtime(sid, rt)

    def _build_args(self, binary):
        def build_args():
            return [sys.executable, binary, self.log, self.projects]
        return build_args

    def _mission(self, objective="Ship the referral webhook end to end"):
        m = self.store.create(objective, "fix", target_mode="new")
        return self.store.transition(m["id"], "brief_confirm", "test")

    def _spawn(self, mission, binary=None):
        """The real spawner with the real publisher injected."""
        async def go():
            return await shadow_runner.spawn_delegate_session(
                self._build_args(binary or self.fake), self.tmp,
                "manifest for %s" % mission["id"], self._register,
                publish=app._publish_delegate_chat(mission))
        return asyncio.run(go())


# ------------------------------------------------------------ publication --
class TestPublication(Base):

    def test_01_a_started_delegate_is_published_as_a_normal_chat(self):
        """CONTRACT 1. Not "a chat-like thing": a row in the ONE inventory
        app._owned_transcripts calls the whole definition of a Sutra chat."""
        m = self._mission()
        sid = self._spawn(m)
        sutra_id = chat_store.resolve("claude", sid)
        self.assertTrue(sutra_id, "the session is bound to a chat record")
        rec = chat_store.load(sutra_id)
        self.assertIsNotNone(rec, "and that record is on disk")
        # THE INDEX ROW is what makes it discoverable -- the same key format
        # _owned_transcripts iterates.
        self.assertIn("claude:" + sid, chat_store.index())
        # and the segment binds this provider session, from turn 0
        self.assertEqual(chat_store.active_segment(rec),
                         {"provider": "claude", "native_id": sid,
                          "from_turn": 0})

    def test_02_it_reaches_the_chats_inventory_itself(self):
        """Not just the index: the function the /api/sessions rail is built
        from must actually return this session."""
        m = self._mission()
        sid = self._spawn(m)
        owned = [c[2] for c in app._owned_transcripts()]
        self.assertIn(sid, owned,
                      "a published delegate is in the normal Chats inventory")

    def test_03_the_title_is_the_shadow_task_name(self):
        """CONTRACT 2. The rail reads a transcript's custom-title record, NOT
        chat_store.title -- so this asserts the thing the operator sees."""
        import session_reader
        m = self._mission("Ship the referral webhook end to end")
        sid = self._spawn(m)
        meta = session_reader.head_meta(sid)
        self.assertTrue(meta["title"].startswith("Shadow Task — "),
                        "got %r" % meta["title"])
        self.assertIn("referral webhook", meta["title"])
        # and it is a REAL on-disk title record, not a first-message fallback
        row = session_reader._claude_session_meta(
            session_reader.resolve_path(sid))
        self.assertEqual(row["title_source"], "custom")

    def test_04_the_title_never_shows_the_shadow_tag_or_the_manifest(self):
        """The manifest is turn 0 and carries the [Shadow · mission] tag; a
        chat named after it would be unreadable in the rail."""
        import session_reader
        m = self._mission()
        sid = self._spawn(m)
        title = session_reader.head_meta(sid)["title"]
        self.assertNotIn("[Shadow", title)
        self.assertNotIn("manifest", title)

    def test_05_a_long_objective_is_trimmed_not_dumped(self):
        long = "Rebuild " + ("the ingest pipeline " * 12)
        self.assertLessEqual(len(app._shadow_chat_title({"objective": long})),
                             90, "must fit the rail's 90-char title budget")
        self.assertTrue(app._shadow_chat_title({"objective": ""}).endswith(
            "untitled"), "an objective-less mission still gets a name")

    def test_06_the_mission_is_linked_to_the_durable_chat(self):
        """CONTRACT: the Mission/Goal knows the Chat identity, via the
        smallest additive field."""
        m = self._mission()
        sid = self._spawn(m)
        after = self.store.load(m["id"])
        self.assertEqual(after["target_session"], sid)
        self.assertEqual(after["target_chat"], chat_store.resolve("claude", sid))

    def test_07_target_session_is_written_BEFORE_anything_is_visible(self):
        """THE ORDERING PROPERTY, and the reason it exists.

        provision_target writes target_session only AFTER the spawner returns.
        Publishing first would leave a window where a chat is in the rail but
        no durable record names the session -- and recover_on_boot() rebuilds
        ownership from exactly that record, so a crash there is the two-writer
        case this slice exists to prevent. Asserted by observing the mission
        at the moment the chat becomes visible.
        """
        m = self._mission()
        seen = {}
        real_begin = chat_store.begin_segment

        def spy(rec, provider, native_id):
            # the instant before the index row (the only visible write)
            seen["mission"] = self.store.load(m["id"])
            return real_begin(rec, provider, native_id)

        chat_store.begin_segment = spy
        try:
            sid = self._spawn(m)
        finally:
            chat_store.begin_segment = real_begin
        self.assertEqual(seen["mission"]["target_session"], sid,
                         "the session must be recoverable from disk before "
                         "the chat can ever be opened")

    def test_08_publication_is_idempotent(self):
        """A re-spawn or a retry must never mint a twin chat."""
        m = self._mission()
        sid = self._spawn(m)
        first = chat_store.resolve("claude", sid)
        again = app._publish_delegate_chat(m)(sid)
        self.assertEqual(again, first)
        rows = [k for k in chat_store.index() if k == "claude:" + sid]
        self.assertEqual(len(rows), 1, "one session, one chat")


# ---------------------------------------------------------------- failure --
class TestFailedStartPublishesNothing(Base):

    def test_10_a_child_that_never_results_publishes_no_chat(self):
        """CONTRACT 6. The rail must never show a chat that never started."""
        m = self._mission()
        before = dict(chat_store.index())
        with self.assertRaises(RuntimeError):
            self._spawn(m, binary=self.dead)
        self.assertEqual(chat_store.index(), before,
                         "no index row -- nothing is discoverable")
        self.assertEqual(self.registered, [], "and nothing was registered")
        self.assertIsNone(self.store.load(m["id"]).get("target_chat"))

    def test_11_the_failure_leaves_no_ownership_behind(self):
        m = self._mission()
        with self.assertRaises(RuntimeError):
            self._spawn(m, binary=self.dead)
        self.assertEqual(
            [k for k in shadow_runner.DELEGATES if "dead" in str(k)], [])

    def test_12_a_publish_failure_never_strands_a_running_session(self):
        """A live Claude process must not be thrown away to save a rail row:
        publication failure is ledgered, the session still returns."""
        m = self._mission()
        real = chat_store.begin_segment

        def boom(*a, **k):
            raise OSError("disk full")

        chat_store.begin_segment = boom
        try:
            sid = self._spawn(m)
        finally:
            chat_store.begin_segment = real
        self.assertTrue(sid, "the delegate still booted and is drivable")
        self.assertIsNone(chat_store.resolve("claude", sid),
                          "and nothing half-visible was published")


# -------------------------------------------------------------- ownership --
class TestOwnership(Base):

    def test_20_one_owner_per_session(self):
        """CONTRACT 4/B. driving() is the one read, and it is true exactly
        while Shadow holds the session."""
        m = self._mission()
        sid = self._spawn(m)
        self.assertEqual(shadow_runner.driving(sid), sid)
        shadow_runner.release_delegate(sid)
        self.assertIsNone(shadow_runner.driving(sid))

    def test_21_release_kills_the_process_and_drops_the_registry_row(self):
        m = self._mission()
        sid = self._spawn(m)
        rt = shadow_runner.DELEGATES[sid]
        self.assertIs(session_runtime.lookup_runtime(sid), rt)
        shadow_runner.release_delegate(sid)
        self.assertNotIn(sid, shadow_runner.DELEGATES)
        self.assertIsNone(session_runtime.lookup_runtime(sid),
                          "a released session has no runtime to write through")

    def test_22_release_is_idempotent_and_harmless_when_unowned(self):
        self.assertIsNone(shadow_runner.release_delegate("no-such-session"))
        m = self._mission()
        sid = self._spawn(m)
        shadow_runner.release_delegate(sid)
        self.assertIsNone(shadow_runner.release_delegate(sid))

    def test_23_an_attached_founder_chat_is_never_driving(self):
        """ATTACHED is excluded on purpose: typing in the founder's own chat
        is a takeover, not a collision, and that path is unchanged."""
        shadow_runner.ATTACHED["founder-sid"] = object()
        try:
            self.assertIsNone(shadow_runner.driving("founder-sid"))
        finally:
            shadow_runner.ATTACHED.pop("founder-sid", None)

    def test_24_an_unowned_session_is_never_driving(self):
        self.assertIsNone(shadow_runner.driving("some-ordinary-chat"))
        self.assertIsNone(shadow_runner.driving(None))
        self.assertIsNone(shadow_runner.driving(""))


# ------------------------------------------------------- completion + life --
class TestCompletion(Base):

    def test_30_the_chat_outlives_the_mission(self):
        """CONTRACT 5. Ownership ends; the chat stays, permanently, as an
        ordinary chat -- not deleted, not archived, not retyped."""
        m = self._mission()
        sid = self._spawn(m)
        sutra_id = chat_store.resolve("claude", sid)
        self.store.transition(m["id"], "running", "admitted")
        self.store.transition(m["id"], "done", "done_when met")
        shadow_runner.release_delegate(sid)

        self.assertIsNone(shadow_runner.driving(sid), "ownership released")
        self.assertEqual(chat_store.resolve("claude", sid), sutra_id,
                         "the chat record is untouched")
        self.assertIn("claude:" + sid, chat_store.index(),
                      "and still discoverable")
        self.assertIn(sid, [c[2] for c in app._owned_transcripts()],
                      "still in the normal Chats inventory after completion")

    def test_31_shutdown_releases_owned_sessions(self):
        """Cancelling a task does not stop a process: spawn() uses
        start_new_session=True, so a clean stop must reap what it owns."""
        m = self._mission()
        sid = self._spawn(m)
        rt = shadow_runner.DELEGATES[sid]
        shadow_runner.shutdown()
        self.assertNotIn(sid, shadow_runner.DELEGATES)
        self.assertIsNone(rt.proc, "the delegate process was reaped")


# ------------------------------------------------------------ restart fence --
class TestRestartFence(Base):
    """F1-a: ownership survives a restart by being rebuilt from mission state
    already on disk. No new persistent store, no new entity."""

    def test_40_recover_on_boot_fences_an_orphaned_delegate_session(self):
        m = self.store.create("orphan", "fix", target_mode="new",
                              target_session="orphan-sid")
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        shadow_runner.RUNNING.pop(m["id"], None)
        shadow_runner.recover_on_boot()
        self.assertEqual(shadow_runner.driving("orphan-sid"), "orphan-sid",
                         "a session a dead process owned stays fenced")

    def test_41_an_attached_mission_is_never_fenced(self):
        """target_mode is the durable discriminator: a chat Shadow merely
        ATTACHED to is the founder's and must stay typeable."""
        m = self.store.create("attached", "fix", target_mode="existing",
                              target_session="founder-chat")
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        shadow_runner.recover_on_boot()
        self.assertIsNone(shadow_runner.driving("founder-chat"))

    def test_42_a_finished_mission_is_never_fenced(self):
        m = self.store.create("finished", "fix", target_mode="new",
                              target_session="done-sid")
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        self.store.transition(m["id"], "done", "t")
        shadow_runner.recover_on_boot()
        self.assertIsNone(shadow_runner.driving("done-sid"))

    def test_43_the_fence_expires_when_the_mission_ends_elsewhere(self):
        """A founder can stop a mission from Shadow Home, which never reaches
        release_delegate(). The fence must not outlive the work, or the chat
        is permanently un-typeable."""
        m = self.store.create("stopme", "fix", target_mode="new",
                              target_session="stop-sid")
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        shadow_runner.RUNNING.pop(m["id"], None)
        shadow_runner.recover_on_boot()
        self.assertEqual(shadow_runner.driving("stop-sid"), "stop-sid")
        # the founder stops it from Shadow Home -- no runner, no reaper
        self.store.transition(m["id"], "stopped", "founder stop (home)")
        self.assertIsNone(shadow_runner.driving("stop-sid"))
        self.assertNotIn("stop-sid", shadow_runner._ORPHANED,
                         "and the fence is discarded, not re-checked forever")

    def test_44_release_clears_a_fence_too(self):
        shadow_runner._ORPHANED.add("fenced-sid")
        shadow_runner.release_delegate("fenced-sid")
        self.assertNotIn("fenced-sid", shadow_runner._ORPHANED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
