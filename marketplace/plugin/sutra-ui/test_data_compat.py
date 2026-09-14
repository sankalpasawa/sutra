"""REAL USER DATA MUST STILL LOAD -- the provider cleanup, measured against it.

WHY THIS FILE EXISTS
Every other test in this repo runs on data the test itself just made up. That
proves the code is self-consistent; it does not prove that the 139 chats, the
settings file and the routines already sitting on the owner's disk survive a
refactor. Backwards compatibility is the whole point of the provider cleanup
(shared spec, rule 5: "every existing settings key, chat file and routine must
still load and behave the same"), so it needs a check that runs against the real
thing.

WHAT IT READS
A read-only backup of the owner's live Sutra data, taken before the cleanup:

    ~/.sutra-ui-backups/2026-09-14-before-provider-cleanup/sutra-ui

MEASURED CONTENTS on the day it was taken: 139 chat records plus _index.json
(158 index rows), 656 messages, 176 provider segments (175 claude, 1 deepseek),
a settings.json carrying five keys, and an empty routines/ directory.

HOW IT HANDLES THAT DATA
IT IS COPIED, ALWAYS, AND THE ORIGINAL IS NEVER OPENED FOR WRITING. setUpModule
copies chats/, settings.json and routines/ into a fresh tempfile directory and
points SUTRA_UI_CHATS / SUTRA_UI_ROUTINES and providers.SETTINGS_PATH at the
COPY. The round-trip tests then save into the copy, which is what makes
"save then load" testable at all -- and which is exactly why it may not be the
original. `_refuse_live_paths()` re-checks before every test that nothing has
been pointed back at ~/.sutra-ui, and fails loudly rather than writing there.

The backup itself is 4.3 GB (shadow/, modules/, agents/ and the rest); only the
three paths this file asserts on are copied, which is 664 KB.

IF THE BACKUP IS NOT THERE
Every test SKIPS with the path it looked for. A machine that is not the owner's
cannot have this data, and failing there would make the suite unrunnable for
everyone else.

WHAT IS ASSERTED
  1. Every chat file loads through chat_store.load() with no exception, and the
     count matches the number of files on disk.
  2. chat_store.resolve("<provider>", "<native_id>") still returns the same
     sutra id for every row in the backup's _index.json.
  3. Every chat survives a load -> save -> load round trip with its
     provider_history and its message blocks unchanged, compared as JSON.
     `updated` is excluded, because chat_store.save() re-stamps it by design.
  4. The index is still byte-identical after all 139 chats have been re-saved --
     which is the interesting half, since save() REBUILDS index rows rather than
     appending to them.
  5. providers.load_settings() returns the same effective permission mode,
     workdir, per-provider models, flags and consent state as the golden
     recorded from this same file; and save_settings() with no arguments (a
     pure rewrite) drops no key.
  6. Every routine loads through routines.load() and keeps its model and
     permission_mode.

ONE HONEST GAP, STATED RATHER THAN PAPERED OVER
All 656 stored blocks in this backup are `text`. The typed-block shapes the
replay renderer depends on -- `thinking`, `tool_use`, `tool_result` -- do not
occur in the owner's real data, so the real-data round trip cannot exercise
them. test_typed_blocks_round_trip covers those with a SYNTHETIC record written
into the same copied store, and is labelled as such. It is not evidence about
the owner's data; it is evidence about the format the owner's data will be
written in next.

The settings golden pins `provider` too, and that value depends on which
provider CLIs are installed on the machine -- it is meaningful here only because
this whole file is gated on a backup that exists on exactly one Mac.

    .venv/bin/python -m pytest -q test_data_compat.py
    SUTRA_GOLDEN_UPDATE=1 .venv/bin/python -m pytest -q test_data_compat.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DIR = os.path.join(HERE, "tests", "golden")

BACKUP = os.path.expanduser(
    "~/.sutra-ui-backups/2026-09-14-before-provider-cleanup/sutra-ui")
LIVE = os.path.realpath(os.path.expanduser("~/.sutra-ui"))

UPDATE = os.environ.get("SUTRA_GOLDEN_UPDATE") == "1"

# The same import-time isolation the other suites use. It must run before
# `import providers`, which resolves SETTINGS_PATH at import. setUpModule
# re-points the module attribute afterwards as well, because in a
# whole-directory run another module may have imported providers first and
# frozen a different path.
_ENV_TMP = tempfile.mkdtemp(prefix="p0-datacompat-")
os.environ.setdefault("SUTRA_UI_WORKDIR", os.path.join(_ENV_TMP, "workspace"))
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ.setdefault("SUTRA_NATIVE_HOME", os.path.join(_ENV_TMP, "native"))
os.environ.setdefault("SUTRA_SHADOW_HOME", os.path.join(_ENV_TMP, "shadow"))

sys.path.insert(0, HERE)

import chat_store                           # noqa: E402
import json_store                           # noqa: E402
import providers                            # noqa: E402
import routines                             # noqa: E402

#: The copy every test reads and writes. Filled by setUpModule.
COPY = {}


def _have_backup():
    return os.path.isdir(os.path.join(BACKUP, "chats"))


def setUpModule():
    """Copy the three paths under test out of the backup, once."""
    if not _have_backup():
        return
    root = tempfile.mkdtemp(prefix="p0-datacompat-copy-")
    chats = os.path.join(root, "chats")
    shutil.copytree(os.path.join(BACKUP, "chats"), chats)
    settings = os.path.join(root, "settings.json")
    src_settings = os.path.join(BACKUP, "settings.json")
    if os.path.exists(src_settings):
        shutil.copyfile(src_settings, settings)
    routines_dir = os.path.join(root, "routines")
    src_routines = os.path.join(BACKUP, "routines")
    if os.path.isdir(src_routines):
        shutil.copytree(src_routines, routines_dir)
    else:
        os.makedirs(routines_dir)
    COPY.update({"root": root, "chats": chats, "settings": settings,
                 "routines": routines_dir})


def _refuse_live_paths():
    """Fail loudly rather than let a test write to the operator's real data.

    Cheap, and re-run before every test: the env vars this file sets are
    process-global, and another module in a whole-directory run can pop them at
    teardown (nineteen modules in this repo do exactly that to
    SUTRA_SHADOW_HOME -- see conftest.py).
    """
    for label, path in (("chats", chat_store.store_dir()),
                        ("routines", routines.store_dir()),
                        ("settings", providers.SETTINGS_PATH)):
        real = os.path.realpath(str(path))
        if real == LIVE or real.startswith(LIVE + os.sep):
            raise AssertionError(
                "%s resolves to the operator's LIVE data (%s). Refusing to run "
                "-- this suite writes, and it may only ever write to its copy."
                % (label, real))


class DataCompatCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not _have_backup():
            raise unittest.SkipTest(
                "no live-data backup at %s -- this suite asserts against the "
                "owner's real Sutra data and has nothing to check without it. "
                "Not a failure: every other machine skips here." % BACKUP)

    def setUp(self):
        os.environ["SUTRA_UI_CHATS"] = COPY["chats"]
        os.environ["SUTRA_UI_ROUTINES"] = COPY["routines"]
        os.environ["SUTRA_UI_SETTINGS"] = COPY["settings"]
        # providers froze SETTINGS_PATH at import; re-point it at the copy.
        self._saved_settings_path = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = type(providers.SETTINGS_PATH)(COPY["settings"])
        _refuse_live_paths()

    def tearDown(self):
        providers.SETTINGS_PATH = self._saved_settings_path

    # -- golden helper, same contract as test_provider_golden.check ---------

    def check(self, name, actual):
        path = os.path.join(GOLDEN_DIR, name + ".json")
        actual = json.loads(json.dumps(actual))
        if UPDATE:
            os.makedirs(GOLDEN_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(actual, indent=2, sort_keys=True) + "\n")
            return actual
        self.assertTrue(os.path.exists(path),
                        "no golden at %s -- record it with "
                        "SUTRA_GOLDEN_UPDATE=1" % path)
        with open(path, encoding="utf-8") as fh:
            expected = json.load(fh)
        self.assertEqual(expected, actual,
                         "%s changed. This is REAL USER DATA: a difference here "
                         "means an existing install would behave differently "
                         "after the refactor." % name)
        return actual

    # -- shared readers ------------------------------------------------------

    def chat_ids(self):
        return sorted(
            f[:-5] for f in os.listdir(COPY["chats"])
            if f.endswith(".json") and f != "_index.json")

    def backup_index(self):
        with open(os.path.join(BACKUP, "chats", "_index.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)


# ------------------------------------------------------------------- chats --

class TestChatsLoad(DataCompatCase):

    def test_every_chat_file_loads(self):
        """No exception, nothing returning None, and the count matches disk."""
        ids = self.chat_ids()
        self.assertTrue(ids, "the copied store has no chat files")
        loaded, failures = 0, []
        for sid in ids:
            try:
                rec = chat_store.load(sid)
            except Exception as exc:                      # noqa: BLE001
                failures.append((sid, "%s: %s" % (type(exc).__name__, exc)))
                continue
            if rec is None:
                failures.append((sid, "load() returned None"))
                continue
            self.assertEqual(rec["sutra_id"], sid)
            loaded += 1
        self.assertEqual(failures, [], "chats that would not load")
        self.assertEqual(loaded, len(ids))

    def test_counts_match_the_recorded_shape(self):
        """The census, goldened. A chat, a message, a segment or a block type
        that stops surviving the read shows up here as a number."""
        census = {"chats": 0, "messages": 0, "segments": 0,
                  "index_rows": len(self.backup_index()),
                  "block_types": {}, "segment_providers": {},
                  "message_roles": {}, "switched_chats": 0}
        for sid in self.chat_ids():
            rec = chat_store.load(sid)
            census["chats"] += 1
            census["segments"] += len(rec["provider_history"])
            if chat_store.switched(rec):
                census["switched_chats"] += 1
            for seg in rec["provider_history"]:
                key = seg["provider"]
                census["segment_providers"][key] = \
                    census["segment_providers"].get(key, 0) + 1
            for msg in rec["messages"]:
                census["messages"] += 1
                census["message_roles"][msg["role"]] = \
                    census["message_roles"].get(msg["role"], 0) + 1
                for blk in msg["blocks"]:
                    census["block_types"][blk["type"]] = \
                        census["block_types"].get(blk["type"], 0) + 1
        self.check("data_compat_chat_census", census)


class TestChatIndex(DataCompatCase):

    def test_index_resolves_every_row_to_the_same_id(self):
        """"<provider>:<native_id>" -> sutra id, for all 158 rows."""
        rows = self.backup_index()
        self.assertTrue(rows)
        wrong = []
        for key, sutra_id in rows.items():
            provider, _, native_id = key.partition(":")
            got = chat_store.resolve(provider, native_id)
            if got != sutra_id:
                wrong.append({"key": key, "expected": sutra_id, "got": got})
        self.assertEqual(wrong, [], "index rows that stopped resolving")

    def test_every_segment_is_indexed(self):
        """The other direction: a segment the index does not know about cannot
        be found on reconnect, which is how a resumed chat loses its history."""
        missing = []
        for sid in self.chat_ids():
            for seg in chat_store.load(sid)["provider_history"]:
                if chat_store.resolve(seg["provider"], seg["native_id"]) is None:
                    missing.append({"sutra_id": sid, "segment": seg})
        self.assertEqual(missing, [], "segments absent from the index")


class TestChatRoundTrip(DataCompatCase):

    def test_load_save_load_is_unchanged(self):
        """Every chat, through save() and back. `updated` is excluded: save()
        re-stamps it on purpose, so comparing it would only ever measure the
        clock."""
        differences = []
        for sid in self.chat_ids():
            before = chat_store.load(sid)
            chat_store.save(dict(before))
            after = chat_store.load(sid)
            for rec in (before, after):
                rec.pop("updated", None)
            if before != after:
                differences.append({
                    "sutra_id": sid,
                    "provider_history_changed":
                        before["provider_history"] != after["provider_history"],
                    "messages_changed": before["messages"] != after["messages"],
                })
        self.assertEqual(differences, [], "chats changed by a round trip")

    def test_index_survives_re_saving_every_chat(self):
        """save() REBUILDS this chat's index rows rather than appending, so
        re-saving all 139 records is the real test of that rebuild."""
        expected = self.backup_index()
        for sid in self.chat_ids():
            chat_store.save(dict(chat_store.load(sid)))
        self.assertEqual(chat_store.index(), expected)

    def test_typed_blocks_round_trip(self):
        """SYNTHETIC, and labelled as such (see the module header's stated gap).

        The owner's 656 real blocks are all `text`, so the real-data round trip
        above cannot say anything about thinking / tool_use / tool_result. This
        writes one record carrying all four into the SAME copied store and reads
        it back, so the typed-block contract is still pinned.
        """
        rec = chat_store.create(cwd="/tmp/x", title="typed blocks")
        chat_store.begin_segment(rec, "claude", "native-typed-1")
        chat_store.append_turn(rec, "user", [chat_store.block_text("do a thing")])
        chat_store.append_turn(rec, "assistant", [
            chat_store.block_thinking("private"),
            chat_store.block_tool_use("Bash", {"command": "echo hi"}, "toolu_1"),
            chat_store.block_tool_result("hi", "toolu_1", is_error=False),
            chat_store.block_text("done"),
        ])
        chat_store.begin_segment(rec, "codex", "native-typed-2")
        chat_store.append_turn(rec, "user", [chat_store.block_text("again")])

        first = chat_store.load(rec["sutra_id"])
        chat_store.save(dict(first))
        second = chat_store.load(rec["sutra_id"])
        for one in (first, second):
            one.pop("updated", None)
            one.pop("created", None)
            one["sutra_id"] = "<generated>"
            for msg in one["messages"]:
                msg["ts"] = "<ts>"
        self.assertEqual(first, second)
        self.assertEqual([b["type"] for b in first["messages"][1]["blocks"]],
                         ["thinking", "tool_use", "tool_result", "text"])
        self.assertEqual([s["provider"] for s in first["provider_history"]],
                         ["claude", "codex"])
        self.check("data_compat_typed_blocks", first)


# ---------------------------------------------------------------- settings --

#: Keys of load_settings() that are derived from the FILE and must not move.
#: `settings_path` and `settings_file_exists` are excluded because they name a
#: temp directory; `deepseek_auth` because it reads a keychain mask that is not
#: part of the provider-cleanup contract; the permission-mode NOTE strings
#: because they are UI copy W2/W3 may legitimately reword.
_SETTINGS_CONTRACT = (
    "provider", "provider_stored", "provider_source",
    "permission_mode", "permission_mode_effective", "permission_mode_clamped",
    "workdir", "workdir_source", "onboarded", "chat_scope",
    "model", "model_by_provider", "flags", "unsafe_modes_allowed",
    "unsafe_modes_env", "invalid_stored_values",
)


class TestSettings(DataCompatCase):

    def _contract(self):
        s = providers.load_settings()
        out = {k: s.get(k) for k in _SETTINGS_CONTRACT}
        home = os.path.realpath(os.path.expanduser("~"))
        if isinstance(out.get("workdir"), str):
            out["workdir"] = out["workdir"].replace(home, "<home>")
        return out

    def test_effective_settings_match_the_golden(self):
        self.check("data_compat_settings", self._contract())

    def test_stored_file_is_what_the_backup_holds(self):
        """The copy is faithful -- otherwise every assertion above is about a
        file this test invented."""
        with open(os.path.join(BACKUP, "settings.json"), encoding="utf-8") as fh:
            original = json.load(fh)
        with open(COPY["settings"], encoding="utf-8") as fh:
            copied = json.load(fh)
        self.assertEqual(original, copied)

    def test_save_load_round_trip_drops_no_key(self):
        """save_settings() with every argument None is a pure rewrite. Any key
        missing afterwards is a key an existing install would silently lose."""
        with open(COPY["settings"], encoding="utf-8") as fh:
            before = json.load(fh)
        before_contract = self._contract()
        providers.save_settings()
        with open(COPY["settings"], encoding="utf-8") as fh:
            after = json.load(fh)
        self.assertEqual(sorted(before), sorted(after), "a settings key was lost")
        self.assertEqual(before, after, "a settings value changed")
        self.assertEqual(before_contract, self._contract())

    def test_every_stored_key_is_still_understood(self):
        """Nothing in the file may land in invalid_stored_values -- that field
        is load_settings()' own report of a value it had to discard."""
        self.assertEqual(providers.load_settings()["invalid_stored_values"], {})

    def test_permission_mode_and_consent_survive(self):
        """The two that decide what the agent is allowed to do."""
        with open(COPY["settings"], encoding="utf-8") as fh:
            raw = json.load(fh)
        s = providers.load_settings()
        self.assertEqual(s["permission_mode"], raw["permission_mode"])
        self.assertEqual(s["unsafe_modes_allowed"],
                         bool(raw.get("unsafe_modes_acknowledged")))
        self.assertIn(s["permission_mode"], providers.PERMISSION_MODES)

    def test_workdir_is_preserved_verbatim(self):
        with open(COPY["settings"], encoding="utf-8") as fh:
            raw = json.load(fh)
        self.assertEqual(providers.load_settings()["workdir"],
                         os.path.expanduser(raw["workdir"]))
        self.assertEqual(providers.load_settings()["workdir_source"], "stored")

    def test_per_provider_models_resolve(self):
        """model_by_provider is the real storage; `model` is the legacy
        accessor onto the claude slot. They may not disagree."""
        s = providers.load_settings()
        self.assertEqual(s["model"], s["model_by_provider"].get("claude", ""))
        for pid, value in s["model_by_provider"].items():
            self.assertTrue(value == "" or
                            value in providers.selectable_model_ids_for(pid),
                            "stored model %r is no longer selectable for %s"
                            % (value, pid))


# ---------------------------------------------------------------- routines --

class TestRoutines(DataCompatCase):

    def test_every_routine_loads(self):
        """Each routine through routines.load(), keeping its model and
        permission_mode.

        MEASURED 2026-09-14: the backup's routines/ holds only a .heartbeat
        file -- the owner has no saved routines, so `ids` is empty and this
        asserts the census rather than a record. The census is goldened, so the
        day a routine exists the golden has to be re-recorded deliberately
        instead of the count silently changing.
        """
        ids = routines.list_ids()
        census = {"count": len(ids), "ids": list(ids), "records": []}
        for rid in ids:
            rec = routines.load(rid)             # raises on a schema mismatch
            self.assertEqual(rec["id"], rid)
            self.assertIn("model", rec, "routine %s lost its model" % rid)
            self.assertIn("permission_mode", rec,
                          "routine %s lost its permission_mode" % rid)
            self.assertIn(rec["permission_mode"], providers.PERMISSION_MODES)
            census["records"].append({
                "id": rid,
                "schema": rec.get("schema"),
                "model": rec.get("model"),
                "permission_mode": rec.get("permission_mode"),
                "enabled": rec.get("enabled"),
            })
        self.check("data_compat_routines", census)

    def test_store_dir_points_at_the_copy(self):
        """The guard itself, asserted -- a suite that writes must prove where."""
        self.assertEqual(os.path.realpath(str(routines.store_dir())),
                         os.path.realpath(COPY["routines"]))
        self.assertNotEqual(os.path.realpath(str(routines.store_dir())),
                            os.path.join(LIVE, "routines"))


# ------------------------------------------------------------ the live guard --

class TestNoLiveWrites(unittest.TestCase):
    """Runs even without the backup: it is about where this file points, not
    about what it found there."""

    def test_module_never_targets_live_data(self):
        for path in (os.environ.get("SUTRA_UI_CHATS"),
                     os.environ.get("SUTRA_UI_ROUTINES"),
                     os.environ.get("SUTRA_UI_SETTINGS")):
            if not path:
                continue
            real = os.path.realpath(os.path.expanduser(path))
            self.assertFalse(real == LIVE or real.startswith(LIVE + os.sep),
                             "%s points inside the live data dir" % path)

    def test_backup_source_is_only_ever_read(self):
        """The backup tree must not be writable through anything this file
        configures -- every env var points into a tempdir instead."""
        if not _have_backup():
            self.skipTest("no backup on this machine")
        backup_real = os.path.realpath(BACKUP)
        for path in (chat_store.store_dir(), routines.store_dir(),
                     providers.SETTINGS_PATH):
            real = os.path.realpath(str(path))
            self.assertFalse(real.startswith(backup_real + os.sep),
                             "%s would write into the backup" % real)


if __name__ == "__main__":
    if "--update" in sys.argv:
        sys.argv.remove("--update")
        UPDATE = True
        os.environ["SUTRA_GOLDEN_UPDATE"] = "1"
    unittest.main()
