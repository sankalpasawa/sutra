#!/usr/bin/env python3
"""test_phase0.py — the §9 Phase 0 behaviour contract, as runnable assertions.

PROTO-000: every shipped change carries a test. Phase 0 is "stop the bleeding"
— no UI, only the engine invariants that the pre-I-D5 code violated. Each test
below is one row of §9's Phase 0 table or one clause of its Proof-of-phase.

Stdlib `unittest` only. Python 3.9: no `match`, no PEP-604 unions.

HARNESS — why the reload dance is load-bearing
----------------------------------------------
`placement_engine` resolves HOME/DOMAINS/CHARTERS/PLACEMENTS/PLANS at IMPORT
time (module-level constants, `:67-74`). Setting SUTRA_NATIVE_HOME after the
first import therefore does NOTHING, and the suite would run against the live
registry at ~/.sutra-native/user-kit. So every setUp() mints a fresh
tempfile.mkdtemp(), exports it, and importlib.reload()s the module — reload
re-executes in the SAME module object, so `domains_page`'s `import
placement_engine as E` binding follows along without being reloaded itself.

`_assert_sandboxed()` is a hard belt-and-braces check: any path escaping the
temp dir aborts the test rather than writing to a real registry.
"""

import contextlib
import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

_LIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

#: Nothing in this suite may ever touch a live kit. Checked per test.
FORBIDDEN = os.path.realpath(os.path.expanduser("~/.sutra-native"))

TENANT = "T-local"
OTHER_TENANT = "T-fixture"


class Phase0Case(unittest.TestCase):
    """Base: a throwaway $SUTRA_NATIVE_HOME per test, torn down after."""

    def setUp(self):
        self._env_backup = dict(os.environ)
        self.home = os.path.realpath(tempfile.mkdtemp(prefix="sutra-phase0-"))
        os.environ["SUTRA_NATIVE_HOME"] = self.home
        os.environ["PLACEMENT_TENANT"] = TENANT
        os.environ["CLAUDE_PROJECT_DIR"] = self.home
        import placement_engine
        self.E = importlib.reload(placement_engine)
        self._assert_sandboxed()
        self.E._HELD.clear()
        self.E._ensure_dirs()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.clear()
        os.environ.update(self._env_backup)

    # ------------------------------------------------------------ guards ---

    def _assert_sandboxed(self):
        E = self.E
        for p in (E.HOME, E.DOMAINS, E.CHARTERS, E.PLACEMENTS, E.PLANS,
                  E.CURRENT, E.DOMAIN_INDEX, E.CHARTER_INDEX):
            real = os.path.realpath(p)
            self.assertTrue(real.startswith(self.home),
                            "engine path escaped the sandbox: %r" % p)
            self.assertFalse(real.startswith(FORBIDDEN),
                             "engine path points at the LIVE registry: %r" % p)

    # ------------------------------------------------------------ helpers --

    @staticmethod
    def read_bytes(path):
        with open(path, "rb") as fh:
            return fh.read()

    @staticmethod
    def read_text(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def read_json(self, path):
        return json.loads(self.read_text(path))

    def sha_file(self, path):
        return hashlib.sha256(self.read_bytes(path)).hexdigest()

    def dpath(self, ref):
        return os.path.join(self.E.DOMAINS, ref + ".json")

    def cpath(self, cid):
        return os.path.join(self.E.CHARTERS, cid + ".json")

    def seed_org(self, tenant=TENANT, root_name="Acme"):
        """root > (Alpha, Beta), Alpha > Alpha Sub. Returns the four refs."""
        E = self.E
        root, _ = E.mint_domain(None, root_name, [root_name.lower()], tenant,
                                origin="operator")
        alpha, _ = E.mint_domain(root, "Alpha", ["alpha", "billing"], tenant)
        beta, _ = E.mint_domain(root, "Beta", ["beta", "shipping"], tenant)
        sub, _ = E.mint_domain(alpha, "Alpha Sub", ["subalpha"], tenant)
        return root, alpha, beta, sub

    def seed_charter(self, ref, title, tenant=TENANT, **kw):
        return self.E.mint_charter_stub(
            ref, title, "Standing promise for %s." % title, [], [], tenant, **kw)

    def seed_placement(self, wid, ref, cid, tenant=TENANT):
        return self.E.write_placement({"kind": "file", "id": wid}, ref, cid,
                                      "matched", 0.7,
                                      {"domains": [], "charters": []}, tenant)

    def seed_wide_registry(self, tenant=TENANT, rows=105):
        """§9 Proof-of-phase: >=100 CURRENT rows across >=3 domains.

        A toy two-domain fixture passes on UNFIXED code — `restructure merge`
        appends superseding rows for the surviving target before removing the
        source file, so the stale rows fall outside `lint`'s 50-row window on
        any realistic registry. The fixture has to be wide enough to defeat
        that, which is the whole reason this helper exists.
        """
        root, alpha, beta, sub = self.seed_org(tenant)
        charters = {}
        for ref, title in ((root, "Acme Charter"), (alpha, "Alpha Charter"),
                           (beta, "Beta Charter"), (sub, "Alpha Sub Charter")):
            charters[ref] = self.seed_charter(ref, title, tenant)
        order = [alpha, beta, sub, root]
        for i in range(rows):
            ref = order[i % len(order)]
            self.seed_placement("/w/unit-%03d.md" % i, ref, charters[ref], tenant)
        return root, alpha, beta, sub, charters

    def snapshot(self, *dirs):
        """relpath -> sha256 over every file under `dirs`."""
        snap = {}
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for dirpath, _dirnames, filenames in os.walk(d):
                for fn in sorted(filenames):
                    p = os.path.join(dirpath, fn)
                    if not os.path.isfile(p):
                        continue
                    with open(p, "rb") as fh:
                        snap[os.path.relpath(p, self.home)] = \
                            hashlib.sha256(fh.read()).hexdigest()
        return snap

    def index_rows(self, path=None):
        return self.E._read_jsonl(path or self.E.DOMAIN_INDEX)

    def cli(self, *args):
        """Run main() and return (exit_code, parsed_json_stdout)."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.E.main(["placement_engine.py"] + list(args))
        txt = buf.getvalue()
        try:
            obj = json.loads(txt)
        except ValueError:
            obj = {"_raw": txt}
        return code, obj

    def cited_domain_refs(self):
        """Every domain_ref cited ANYWHERE on disk: CURRENT rows, placement
        bodies, charter bodies, and each domain's own parent/successor edges."""
        E = self.E
        cited = set(E._cited_domain_refs().keys())
        for fn in E.charter_body_files():
            body = E.load_charter(fn[:-len(".json")]) or {}
            if body.get("domain_ref"):
                cited.add(body["domain_ref"])
            for lr in (E.load_sidecar(body.get("id") or "")
                       .get("linked_domain_refs") or []):
                cited.add(lr)
        for _ref, d in E.load_domains().items():
            if d.get("parent_ref"):
                cited.add(d["parent_ref"])
            for s in (d.get("successor_refs") or []):
                cited.add(s)
        return cited


# =========================================================== 1 / 2 / 3 =====
# "Delete both os.remove calls" + "MERGE re-parents the source's children"
# + the §0.15 DELETE charter loop.

class TestNoDestruction(Phase0Case):

    def test_01_merge_keeps_the_source_file_and_stamps_the_tombstone(self):
        """§9: MERGE stamps status='retired' + successor_refs; the file STAYS."""
        E = self.E
        root, alpha, beta, _sub = self.seed_org()
        self.seed_charter(alpha, "Alpha Charter")

        r = E.restructure("merge", alpha, target=beta, tenant_id=TENANT)
        self.assertTrue(r["ok"], r)

        self.assertTrue(os.path.exists(self.dpath(alpha)),
                        "I-D5 violated: merge removed domains/<source>.json")
        d = E._load_domain(alpha)
        self.assertEqual(d["status"], "retired")
        self.assertEqual(d["successor_refs"], [beta])
        self.assertEqual(d["retire_reason_code"], "merged")
        self.assertIsNotNone(d["retired_at_ms"])
        self.assertIsNotNone(d["disposition_event_id"])
        # the ref must still resolve through the ordinary read path
        self.assertIn(alpha, E.load_domains())
        # ...and the target survives, unretired
        self.assertEqual(E._load_domain(beta).get("status", "active"), "active")
        self.assertEqual(E._load_domain(root).get("status", "active"), "active")

    def test_02_delete_keeps_the_file_reparents_children_rehomes_charters(self):
        """§9 + §0.15: DELETE's successor is the parent; children AND charters
        both move. The missing charter loop is the §0.15 bug."""
        E = self.E
        root, alpha, _beta, sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/alpha.md", alpha, cid)

        r = E.restructure("delete", alpha, tenant_id=TENANT)
        self.assertTrue(r["ok"], r)

        self.assertTrue(os.path.exists(self.dpath(alpha)),
                        "I-D5 violated: delete removed domains/<ref>.json")
        d = E._load_domain(alpha)
        self.assertEqual(d["status"], "retired")
        self.assertEqual(d["successor_refs"], [root],
                         "DELETE's successor is the parent")
        self.assertEqual(d["retire_reason_code"], "deleted")

        # children re-parented onto the successor
        self.assertEqual(E._load_domain(sub)["parent_ref"], root)
        self.assertEqual([c["ref"] for c in r["disposition"]["children"]], [sub])

        # charters re-homed (§0.15) — successor minted, original UNTOUCHED
        moved = r["disposition"]["charters"]
        self.assertEqual([m["id"] for m in moved], [cid])
        new_cid = moved[0]["successor_id"]
        self.assertNotEqual(new_cid, cid)
        self.assertTrue(os.path.exists(self.cpath(cid)),
                        "the old C-hash body must never be removed")
        succ = E.load_charter(new_cid)
        self.assertEqual(succ["domain_ref"], root)
        self.assertEqual(succ["supersedes"], cid)
        self.assertEqual(E.load_charter(cid)["domain_ref"], alpha,
                         "§0.12: domain_ref must NEVER be rewritten in place")
        # §2.2: the shipped status enum is UNCHANGED by this design and no
        # `superseded` value is introduced — the disposition rides `lifecycle`,
        # and supersession itself is DERIVED from `supersedes`.
        sc = E.load_sidecar(cid)
        self.assertEqual(sc["status"], "active",
                         "§2.2: the status enum must not be overloaded to mean "
                         "superseded — a merged department's history is not "
                         "'retired work'")
        self.assertEqual(sc["lifecycle"], "superseded")
        self.assertEqual(E.superseded_by(cid), new_cid)
        self.assertIsNone(E.superseded_by(new_cid))
        # and the current placement followed the charter
        cur = [p for p in E._current_placements()
               if (p.get("work_ref") or {}).get("id") == "/w/alpha.md"]
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["domain_ref"], root)
        self.assertEqual(cur[0]["charter_id"], new_cid)

    def test_03_merge_reparents_the_sources_children_to_the_target(self):
        """§9: 'MERGE re-parents the source's children to the target' —
        missing today, mirroring DELETE's loop."""
        E = self.E
        _root, alpha, beta, sub = self.seed_org()
        grand, _ = E.mint_domain(sub, "Alpha Grandchild", ["grand"], TENANT)

        r = E.restructure("merge", alpha, target=beta, tenant_id=TENANT)
        self.assertTrue(r["ok"], r)

        self.assertEqual(E._load_domain(sub)["parent_ref"], beta,
                         "ORG-003: merge orphaned the absorbed subtree")
        self.assertEqual([c["ref"] for c in r["disposition"]["children"]], [sub])
        # only DIRECT children move; the grandchild keeps riding its parent
        self.assertEqual(E._load_domain(grand)["parent_ref"], sub)
        # the whole subtree still reaches the root
        chain = [n["ref"] for n in E.ancestor_chain(grand)]
        self.assertIn(beta, chain)


# ================================================================== 4 ======
# Proof-of-phase clause 4: no dangling refs after a real restructure.

class TestGroundedness(Phase0Case):

    def test_04_every_cited_domain_ref_still_resolves_after_merge_and_delete(self):
        """§9 Proof clause 4, over a >=100-row / >=3-domain registry."""
        E = self.E
        root, alpha, beta, sub, _ch = self.seed_wide_registry()
        self.assertGreaterEqual(len(E._read_jsonl(E.CURRENT)), 100)

        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])
        self.assertTrue(E.restructure("delete", sub, tenant_id=TENANT)["ok"])

        domains = E.load_domains()
        missing = sorted(r for r in self.cited_domain_refs() if r not in domains)
        self.assertEqual(missing, [], "dangling domain_ref(s) after restructure")
        for ref in domains:
            self.assertTrue(os.path.isfile(self.dpath(ref)),
                            "%s resolves in the map but has no file" % ref)
        # every charter_id cited by a placement resolves to a body too
        for p in E.all_placements():
            self.assertTrue(os.path.isfile(self.cpath(p["charter_id"])),
                            "placement %s cites a missing charter" % p["id"])
        self.assertTrue(E.lint_full()["ok"], E.lint_full())
        self.assertNotIn(root, ())  # root retained for readability of the fixture


# ================================================================== 5 ======

class TestRetireLifecycle(Phase0Case):

    def test_05_retire_blocks_then_succeeds_writes_manifest_and_unretires(self):
        """§9 + §3.4: exit 2 while unmapped > 0; manifest BEFORE mutation;
        `unretire --from <manifest>` restores."""
        E = self.E
        _root, alpha, beta, sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/alpha.md", alpha, cid)

        # ---- blocked: charters + children + placements have no destination ---
        blocked = E.retire(alpha, successor_ref=None, tenant_id=TENANT)
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["exit"], 2)
        self.assertGreater(blocked["report"]["unmapped"], 0)
        codes = {b["code"] for b in blocked["report"]["blocks"]}
        self.assertTrue({"ORG-002", "ORG-003", "ORG-004"} <= codes, codes)
        self.assertEqual(E._load_domain(alpha).get("status", "active"), "active",
                         "a blocked retire must not have mutated anything")
        code, _ = self.cli("retire", alpha)
        self.assertEqual(code, 2, "CLI must exit 2 while disposition is incomplete")

        # ---- succeeds once every item is mapped -----------------------------
        ok = E.retire(alpha, successor_ref=beta, note="folded into Beta",
                      reason_code="superseded", tenant_id=TENANT)
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["successor_refs"], [beta])
        self.assertEqual(ok["children_reparented"], 1)
        self.assertEqual(ok["charters_superseded"], 1)
        self.assertEqual(ok["placements_repointed"], 1)

        mpath = ok["manifest"]
        self.assertTrue(os.path.isfile(mpath), "no pre-mutation manifest")
        self.assertTrue(os.path.realpath(mpath).startswith(
            os.path.realpath(E.PLANS)))
        self.assertTrue(os.path.basename(mpath).startswith("retire-%s-" % alpha))
        man = self.read_json(mpath)
        self.assertEqual(man["kind"], "retire-manifest")
        self.assertEqual(man["ref"], alpha)
        self.assertEqual(man["prior_domain"]["status"], "active")
        self.assertEqual(len(man["placements"]), 1)

        d = E._load_domain(alpha)
        self.assertEqual(d["status"], "retired")
        self.assertEqual(E._load_domain(sub)["parent_ref"], beta)
        self.assertTrue(os.path.exists(self.dpath(alpha)))

        # ---- unretire restores ---------------------------------------------
        back = E.unretire(alpha, mpath, tenant_id=TENANT)
        self.assertTrue(back["ok"], back)
        d = E._load_domain(alpha)
        self.assertEqual(d["status"], "active")
        self.assertEqual(d["successor_refs"], [])
        self.assertIsNone(d["retired_at_ms"])
        self.assertIsNone(d["retire_reason_code"])
        self.assertEqual(E._load_domain(sub)["parent_ref"], alpha,
                         "child not returned to the unretired parent")
        self.assertEqual(back["placements_restored"], 1)
        cur = [p for p in E._current_placements()
               if (p.get("work_ref") or {}).get("id") == "/w/alpha.md"]
        self.assertEqual([p["domain_ref"] for p in cur], [alpha])
        # §2.2: the successor charters CANNOT be deleted, so they are marked
        # lifecycle='reverted' and the derived superseded chip flips off.
        for new_cid in back["charters_reverted"]:
            self.assertEqual(E.load_sidecar(new_cid).get("lifecycle"), "reverted")
        self.assertTrue(os.path.exists(self.cpath(cid)))


# ================================================================== 6 ======

class TestCharterDisposition(Phase0Case):

    def test_06_charter_reassign_mints_successor_and_supersedes_the_original(self):
        """§3.5: reassign MINTS a successor with `supersedes` set, repoints the
        citing placements, and never mutates `domain_ref` on the old body."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        before_body = self.read_json(self.cpath(cid))
        before_sha = self.sha_file(self.cpath(cid))
        self.seed_placement("/w/alpha.md", alpha, cid)

        r = E.charter_reassign(cid, beta, note="alpha folded", tenant_id=TENANT)
        self.assertTrue(r["ok"], r)
        new_cid = r["successor_id"]
        self.assertNotEqual(new_cid, cid)
        self.assertEqual(r["placements_repointed"], 1)

        succ = E.load_charter(new_cid)
        self.assertEqual(succ["supersedes"], cid)
        self.assertEqual(succ["domain_ref"], beta)
        self.assertEqual(succ["schema"], E.CHARTER_SCHEMA)
        self.assertEqual(E.charter_id_of(succ), new_cid,
                         "the successor must hash to its own id")
        # §3.5 handoff briefing rides the SIDECAR, never the hashed body
        self.assertNotIn("handoff", succ)
        hand = E.load_sidecar(new_cid).get("handoff") or {}
        self.assertEqual(hand.get("from_charter_id"), cid)
        self.assertEqual(hand.get("from_domain_ref"), alpha)
        self.assertEqual(hand.get("open_placements_n"), 1)

        # old body byte-identical; the source is SUPERSEDED, not retired (§2.2:
        # the status enum is unchanged, supersession is derived from
        # `supersedes`), and the source domain stops offering it for new work.
        self.assertTrue(os.path.exists(self.cpath(cid)))
        self.assertEqual(self.sha_file(self.cpath(cid)), before_sha,
                         "§0.12: the old C-hash body was rewritten")
        self.assertEqual(self.read_json(self.cpath(cid)), before_body)
        self.assertEqual(E.load_charter(cid)["domain_ref"], alpha)
        self.assertEqual(E.load_sidecar(cid)["status"], "active",
                         "§2.2 introduces no `superseded` status value and "
                         "leaves the shipped enum alone")
        self.assertEqual(E.load_sidecar(cid)["lifecycle"], "superseded")
        self.assertEqual(E.superseded_by(cid), new_cid)
        # ...and the CHOICE surface honours it: alpha is still active and still
        # holds exactly one body — the source — so an unfiltered pick would hand
        # new work straight back to the charter just closed.
        self.assertEqual([c["id"] for c in E.charters_for(alpha)], [cid])
        self.assertIsNone(E.pick_charter(alpha, ["alpha"]),
                          "pick_charter offered a superseded charter as a "
                          "destination for new work")

        # placements followed
        cur = [p for p in E._current_placements()
               if (p.get("work_ref") or {}).get("id") == "/w/alpha.md"]
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["charter_id"], new_cid)
        self.assertEqual(cur[0]["domain_ref"], beta)
        self.assertEqual(cur[0]["phase"], "post-close")

        # charters/INDEX.jsonl carries the lifecycle row
        rows = [r2 for r2 in E._read_jsonl(E.CHARTER_INDEX)
                if r2.get("event") == "charter_reassigned" and r2.get("id") == cid]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["successor_id"], new_cid)
        self.assertEqual(rows[0]["to_domain_ref"], beta)

    def test_06c_unretire_clears_the_derived_superseded_flag(self):
        """§2.2 P0: "supersession is derived, never stored", and the reverted
        clause closes the contradiction with §3.4 — `unretire` CANNOT delete the
        successor charters a retire minted (I-D5 and content addressing both
        forbid it), so without it the restored domain's originals would read
        "superseded by C-…" forever."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/alpha.md", alpha, cid)

        r = E.retire(alpha, successor_ref=beta, tenant_id=TENANT)
        self.assertTrue(r["ok"], r)
        succ = r["report"]["charters"][0]["successor_id"]
        self.assertEqual(E.superseded_by(cid), succ)

        u = E.unretire(alpha, r["manifest"], tenant_id=TENANT)
        self.assertTrue(u["ok"], u)
        self.assertEqual(E.load_sidecar(succ)["lifecycle"], "reverted")
        self.assertIsNone(E.superseded_by(cid),
                          "the restored domain's original still reads "
                          "superseded — the chip would never switch off")
        self.assertTrue(os.path.exists(self.cpath(succ)),
                        "unretire must not delete the successor body")
        # the original takes new work again; the reverted successor does not
        self.assertEqual((E.pick_charter(alpha, ["alpha"]) or {}).get("id"), cid)

    def test_06b_charter_retire_flips_the_sidecar_only(self):
        """§3.5: `charter retire` uses the EXISTING status enum; no new value,
        no body write, no file removed."""
        E = self.E
        _root, alpha, _beta, _sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        before_sha = self.sha_file(self.cpath(cid))

        r = E.charter_retire(cid, note="superseded by hand", tenant_id=TENANT)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["before_status"], "active")
        self.assertEqual(E.load_sidecar(cid)["status"], "retired")
        self.assertIn("retired", E.CHARTER_STATUSES)
        self.assertEqual(self.sha_file(self.cpath(cid)), before_sha)
        self.assertEqual(E.charter_id_of(E.load_charter(cid)), cid)
        rows = [x for x in E._read_jsonl(E.CHARTER_INDEX)
                if x.get("event") == "charter_retired"]
        self.assertEqual([x["id"] for x in rows], [cid])


# ================================================================ 7 / 8 ====

class TestCharterHashing(Phase0Case):

    def test_07_fresh_charter_hashes_to_its_own_id(self):
        """§9 Proof clause 2 / §0.12: `mint_charter_stub` takes the FULL body
        so the hash is computed once. Zero mismatches from verify-charters."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        cid = E.mint_charter_stub(
            alpha, "Quarterly client reporting",
            "Client reporting runs monthly and closes in five days.",
            ["reporting"], ["billing"], TENANT,
            kind="project", status="shipped",
            artifacts=["os/native/primitives/domain.md"],
            linked_domain_refs=[beta],
            extras={"todos": [{"title": "ship the pack", "status": "open"}],
                    "metrics": [{"label": "cycle", "current": "5d",
                                 "target": "3d"}]})
        body = E.load_charter(cid)
        self.assertEqual(E.charter_id_of(body), cid)
        self.assertEqual(body["kind"], "project")
        self.assertEqual(body["schema"], E.CHARTER_SCHEMA)
        self.assertIsNone(body["supersedes"])
        # the operator-mutable set must be ABSENT from the hashed body (§2.2)
        for k in E._SIDECAR_KEYS:
            self.assertNotIn(k, body, "mutable key %r rode into the body" % k)
        sc = E.load_sidecar(cid)
        self.assertEqual(sc["status"], "shipped")
        self.assertEqual(sc["artifacts"], ["os/native/primitives/domain.md"])
        self.assertEqual(sc["linked_domain_refs"], [beta])
        self.assertEqual(sc["todos"][0]["title"], "ship the pack")

        # a whole registry minted through the shipped paths verifies clean —
        # including the engine's OWN mint-on-resolve path, which is the one
        # that ships a charter without any operator ever seeing it.
        self.seed_charter(beta, "Beta Charter")
        E.resolve({"kind": "file", "id": "/w/ledger/close.py"},
                  utterance="month end close",
                  paths=["/w/ledger/close.py"], tenant_id=TENANT)
        rep = E.verify_charters()
        self.assertEqual(rep["mismatched"], 0, rep["mismatches"])
        self.assertEqual(rep["grandfathered_legacy"], 0)
        self.assertTrue(rep["ok"])
        self.assertGreaterEqual(rep["checked"], 3,
                                "fixture did not exercise the mint-on-resolve path")
        code, _ = self.cli("verify-charters")
        self.assertEqual(code, 0)

    def test_07b_pipeline_and_seed_paths_mint_hash_stable_charters(self):
        """§0.12/§0.13: the two post-mint rewrite loops are gone. Both callers
        pass the full body, so the sidecar carries the extras."""
        E = self.E
        import charters_seed as CS
        _root, alpha, _beta, _sub = self.seed_org()
        warn = []
        extras = CS.validate_extras(
            {"todos": [{"title": "land phase 0", "status": "in-progress",
                        "tasks": [{"label": "tests", "done": False}]}],
             "milestones": [{"label": "M1", "status": "now"}],
             "goals": ["stop the bleeding"]},
            warn, "row[0]")
        cid = E.mint_charter_stub(alpha, "Phase 0", "Stop the bleeding.",
                                  [], [], TENANT, kind="project",
                                  status="active", artifacts=["os/native"],
                                  extras=extras)
        body = E.load_charter(cid)
        self.assertEqual(E.charter_id_of(body), cid)
        self.assertNotIn("todos", body)
        self.assertNotIn("status", body)
        sc = E.load_sidecar(cid)
        self.assertEqual(sc["goals"], ["stop the bleeding"])
        self.assertEqual(sc["milestones"][0]["label"], "M1")
        self.assertEqual(E.verify_charters()["mismatched"], 0)

    def test_08_sidecar_edit_changes_neither_the_id_nor_the_body_file(self):
        """§2.2: a todo tick must not change the charter id — C-<id>.html is
        called stable forever (§0.13)."""
        E = self.E
        _root, alpha, _beta, _sub = self.seed_org()
        cid = E.mint_charter_stub(
            alpha, "Alpha Charter", "Standing promise.", [], [], TENANT,
            extras={"todos": [{"title": "ship it", "status": "open"},
                              {"title": "measure it", "status": "open"}]})
        body_path = self.cpath(cid)
        before_bytes = self.read_bytes(body_path)
        before_body = json.loads(before_bytes.decode("utf-8"))

        sc = E.load_sidecar(cid)
        sc["todos"][0]["status"] = "done"
        sc["todos"][0]["done_at"] = "2026-08-01"
        E.save_sidecar(cid, sc)

        self.assertEqual(self.read_bytes(body_path), before_bytes,
                         "the hashed body was rewritten by a sidecar edit")
        self.assertEqual(E.load_charter(cid), before_body)
        self.assertEqual(E.charter_id_of(E.load_charter(cid)), cid)
        self.assertEqual(E.verify_charters()["mismatched"], 0)
        # ...and the render view still shows the flipped todo
        view = E.charter_view(cid)
        self.assertEqual(view["id"], cid)
        self.assertEqual(view["todos"][0]["status"], "done")
        self.assertEqual(view["domain_ref"], alpha)

    def test_08b_an_absent_sidecar_reports_ts_ms_unknown_not_now(self):
        """§2.2 introduces `ts_ms` precisely because "which charters existed in
        June" is unanswerable except by file mtime, which does not survive a
        reinstall. Falling back to `_now_ms()` on the READ path answered it
        WRONGLY, with a value that moved on every read and every build — and
        read as authoritative. Unknown is None."""
        E = self.E
        _root, alpha, _beta, _sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/a.md", alpha, cid)
        self.assertIsNotNone(E.load_sidecar(cid)["ts_ms"], "mint stamps ts_ms")

        os.remove(E._sidecar_path(cid))       # a plain engine-minted v1 stub
        self.assertEqual(E.verify_charters()["mismatched"], 0,
                         "fixture: a hash-clean body never reaches "
                         "migrate_charters' mismatch list, so it never got a "
                         "sidecar — that is why this path matters")
        first = E.load_sidecar(cid)["ts_ms"]
        self.assertIsNone(first, "the read fallback fabricated a ts_ms of NOW")
        self.assertIsNone(E.charter_view(cid)["ts_ms"])

        # ...and the backfill recovers it wherever history knows the answer
        self.assertEqual([r["id"] for r in E.backfill_sidecars()], [cid])
        self.assertIsNotNone(E.load_sidecar(cid)["ts_ms"])
        self.assertEqual(E.load_sidecar(cid)["status"], "active")
        self.assertEqual(E.backfill_sidecars(), [],
                         "backfill_sidecars is not idempotent")
        self.assertEqual(E.verify_charters()["mismatched"], 0)


# ================================================================== 9 ======

class TestConsolidateDryRun(Phase0Case):

    def test_09_consolidate_without_apply_mutates_nothing(self):
        """§9 + §5.3: the CLI default is dry-run. The AUTO tier may only EMIT
        A PLAN FILE — never call restructure. Proof clause 6."""
        E = self.E
        root, _alpha, _beta, _sub = self.seed_org()
        # two system-minted, untouched, near-identical siblings
        dup_a, _ = E.mint_domain(root, "Billing Invoices",
                                 ["billing", "invoices"], TENANT)
        dup_b, _ = E.mint_domain(root, "Invoices Billing",
                                 ["invoices", "billing"], TENANT)
        rep = E.mece_report(TENANT)
        self.assertGreaterEqual(rep["auto_mergeable"], 1,
                                "fixture failed to produce an auto-merge candidate")

        # `domains/`, `charters/`, `placements/` are the mutation surfaces.
        # `plans/` is deliberately EXCLUDED: the plan file is the documented
        # output of the dry run, not a mutation of the registry.
        before = self.snapshot(E.DOMAINS, E.CHARTERS, E.PLACEMENTS)
        out = E.consolidate(TENANT, apply_auto=False)
        after = self.snapshot(E.DOMAINS, E.CHARTERS, E.PLACEMENTS)

        self.assertEqual(before, after, "consolidate mutated the registry")
        self.assertEqual(out["auto_applied"], [])
        self.assertFalse(out["applied"])
        self.assertGreaterEqual(len(out["proposed"]), 1)
        self.assertIn("plan", out)
        plan = self.read_json(out["plan"])
        self.assertEqual(plan["plan_origin"], "auto-consolidate")
        self.assertIsNone(plan["validated_at_ms"])
        self.assertTrue(any(o["op"] == "merge" for o in plan["ops"]))
        for ref in (dup_a, dup_b):
            self.assertEqual(E._load_domain(ref).get("status", "active"), "active")

        # the CLI default is the dry run — no flags means zero merges
        before = self.snapshot(E.DOMAINS, E.CHARTERS, E.PLACEMENTS)
        code, obj = self.cli("consolidate")
        self.assertEqual(code, 0)
        self.assertFalse(obj["applied"])
        self.assertEqual(obj["auto_applied"], [])
        self.assertEqual(before, self.snapshot(E.DOMAINS, E.CHARTERS, E.PLACEMENTS))

        # ...and --apply is the ONLY thing that moves the tree
        code, obj = self.cli("consolidate", "--apply")
        self.assertEqual(code, 0)
        self.assertTrue(obj["applied"])
        self.assertGreaterEqual(len(obj["auto_applied"]), 1)
        self.assertNotEqual(before,
                            self.snapshot(E.DOMAINS, E.CHARTERS, E.PLACEMENTS))


    def test_09b_repeated_dry_runs_do_not_accumulate_plan_files(self):
        """The plan is CONTENT-ADDRESSED. Dry-run is now the DEFAULT path, so a
        ts-named plan file meant every invocation against an unchanged registry
        dropped another byte-identical file in plans/ — unbounded state, and
        `consolidate` alone among the sweeps would not be idempotent."""
        E = self.E
        root, _a, _b, _s = self.seed_org()
        E.mint_domain(root, "Billing Invoices", ["billing", "invoices"], TENANT)
        E.mint_domain(root, "Invoices Billing", ["invoices", "billing"], TENANT)

        first = E.consolidate(TENANT)["plan"]
        plans = sorted(os.listdir(E.PLANS))
        self.assertEqual(len(plans), 1)
        self.assertEqual(E.consolidate(TENANT)["plan"], first)
        self.assertEqual(sorted(os.listdir(E.PLANS)), plans,
                         "a second dry run dropped another plan file")
        self.assertNotIn("created_ms", os.path.basename(first))
        self.assertIsNotNone(self.read_json(first)["created_ms"])


# ================================================================= 10 ======

class TestRestructureEvents(Phase0Case):

    def test_10_rename_event_row_records_the_new_name(self):
        """§2.5: the enriched restructure event carries before/after on the
        mutable set — `name` included."""
        E = self.E
        _root, alpha, _beta, _sub = self.seed_org()
        n_before = len(self.index_rows())

        r = E.restructure("rename", alpha, name="Revenue Operations",
                          tenant_id=TENANT)
        self.assertTrue(r["ok"], r)
        self.assertEqual(E._load_domain(alpha)["name"], "Revenue Operations")
        self.assertTrue(E._load_domain(alpha)["touched_by_operator"],
                        "rename must latch touched_by_operator (never AUTO-merged)")

        rows = self.index_rows()[n_before:]
        ev = [x for x in rows if x.get("event") == "domain_restructured"
              and x.get("op") == "rename" and x.get("ref") == alpha]
        self.assertEqual(len(ev), 1, rows)
        row = ev[0]
        self.assertEqual(row["after"]["name"], "Revenue Operations")
        self.assertEqual(row["before"]["name"], "Alpha")
        self.assertEqual(row["tenant_id"], TENANT)
        self.assertIn("d_path", row["after"])
        self.assertIsNotNone(row["reorg_id"])
        self.assertIsNotNone(row["ts_ms"])
        self.assertEqual(r["after"]["name"], "Revenue Operations")

    def test_10b_restructure_event_carries_tenant_id(self):
        """§9: `tenant_id` is absent from domain_restructured today, while
        domain_minted carries it."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        E.restructure("move", alpha, target=beta, tenant_id=TENANT)
        E.restructure("merge", alpha, target=beta, tenant_id=TENANT)
        evs = [x for x in self.index_rows()
               if x.get("event") == "domain_restructured"]
        self.assertGreaterEqual(len(evs), 2)
        for x in evs:
            self.assertEqual(x.get("tenant_id"), TENANT,
                             "domain_restructured %r lost tenant_id" % x.get("op"))


# ================================================================= 11 ======

class TestLintFullAndReconcile(Phase0Case):

    def test_11_lint_full_exits_2_on_a_dangling_ref_reconcile_clears_it(self):
        """§9 Proof clause 4: whole-log scan, exit 2. The sampled lane's 50-row
        window is exactly why the pre-I-D5 damage was invisible."""
        E = self.E
        root, _alpha, _beta, _sub, _ch = self.seed_wide_registry()
        self.assertTrue(E.lint_full()["ok"])
        code, _ = self.cli("lint", "--full")
        self.assertEqual(code, 0)

        # seed pre-I-D5 damage: a CURRENT row + a placement body citing a
        # domain whose file the old os.remove() destroyed.
        ghost = "dref-ghost0000000"
        E._append_jsonl(E.CURRENT, {"work_ref_id": "/w/ghost.md",
                                    "work_ref_kind": "file",
                                    "tenant_id": TENANT,
                                    "placement_id": "PL-ghost000000000",
                                    "domain_ref": ghost,
                                    "ts_ms": E._now_ms()})
        # ...and push it out of the sampled lane's 50-row window
        for i in range(60):
            E._append_jsonl(E.CURRENT, {"work_ref_id": "/w/pad-%02d.md" % i,
                                        "tenant_id": TENANT,
                                        "placement_id": "PL-pad",
                                        "domain_ref": root,
                                        "ts_ms": E._now_ms()})

        rep = E.lint_full()
        self.assertFalse(rep["ok"], rep)
        self.assertEqual([e["ref"] for e in rep["dangling_domain_refs"]], [ghost])
        self.assertEqual(rep["mode"], "full")
        code, obj = self.cli("lint", "--full")
        self.assertEqual(code, 2, "lint --full must BLOCK on a dangling ref")
        self.assertFalse(obj["ok"])

        # the sampled lane is blind to it AND never blocks — that contrast is
        # the point of shipping --full (§0.3).
        code, obj = self.cli("lint")
        self.assertEqual(code, 0)
        self.assertEqual(obj["mode"], "sampled")

        # reconcile tombstones it: the ref resolves again, as `retired`
        rec = E.reconcile(TENANT)
        self.assertTrue(rec["ok"], rec)
        self.assertEqual([m["ref"] for m in rec["minted"]], [ghost])
        tomb = E._load_domain(ghost)
        self.assertEqual(tomb["status"], "retired")
        self.assertEqual(tomb["retire_reason_code"], "reconstructed")
        self.assertTrue(tomb["name"].startswith("[unrecovered]"),
                        "a tombstone must not read as recovered data")
        self.assertEqual(tomb["parent_ref"], root)

        self.assertTrue(E.lint_full()["ok"], E.lint_full())
        code, _ = self.cli("lint", "--full")
        self.assertEqual(code, 0, "reconcile did not clear the dangling ref")

        # idempotent
        again = E.reconcile(TENANT)
        self.assertEqual(again["minted"], [])
        self.assertTrue(E.lint_full()["ok"])

    def test_11b_a_legitimate_retire_never_turns_lint_full_red(self):
        """§9: a ref resolving to a tombstone is GROUNDED. `retire` must not
        make the blocking lane fire."""
        E = self.E
        _root, alpha, beta, sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/alpha.md", alpha, cid)
        self.assertTrue(E.retire(alpha, successor_ref=beta,
                                 tenant_id=TENANT)["ok"])
        self.assertTrue(E.lint_full()["ok"], E.lint_full())
        self.assertEqual(self.cli("lint", "--full")[0], 0)
        self.assertIsNotNone(sub)


# ================================================================= 12 ======

class TestRepairOrphanCharters(Phase0Case):

    def test_12_repair_rehomes_an_orphan_charter_and_is_idempotent(self):
        """§0.15 / §2.10: DELETE had no charter loop, so every charter on a
        deleted domain is unreachable through charters_for(). One sweep."""
        E = self.E
        root, alpha, _beta, _sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/alpha.md", alpha, cid)

        # reproduce the pre-fix damage: the domain went `retired` with NO
        # charter disposition (the old DELETE path).
        d = E._load_domain(alpha)
        E._mark_retired(d, [root], "deleted", None, "reorg-legacy", E._now_ms())
        E._save_domain(d)
        self.assertEqual(E.charters_for(root), [],
                         "fixture is wrong: the charter is not orphaned yet")

        dry = E.repair(TENANT, dry_run=True)
        self.assertEqual(len(dry["repaired"]), 1)
        self.assertEqual(E.charters_for(root), [], "--dry-run mutated the kit")

        rep = E.repair(TENANT)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["orphans"], 1)
        self.assertEqual(len(rep["repaired"]), 1)
        row = rep["repaired"][0]
        self.assertEqual(row["id"], cid)
        self.assertEqual(row["to_domain_ref"], root)
        self.assertEqual(row["via"], "successor")
        new_cid = row["successor_id"]

        succ = E.load_charter(new_cid)
        self.assertEqual(succ["domain_ref"], root)
        self.assertEqual(succ["supersedes"], cid)
        self.assertEqual(E.charter_id_of(succ), new_cid)
        self.assertEqual([c["id"] for c in E.charters_for(root)], [new_cid])
        # the original body is untouched and still on disk (I-D5's twin)
        self.assertTrue(os.path.exists(self.cpath(cid)))
        self.assertEqual(E.load_charter(cid)["domain_ref"], alpha)
        sc = E.load_sidecar(cid)
        self.assertEqual(sc["lifecycle"], "repaired")
        self.assertEqual(sc["repaired_successor_id"], new_cid)

        # ---- second run = zero moves ----------------------------------------
        before = self.snapshot(E.DOMAINS, E.CHARTERS, E.PLACEMENTS)
        again = E.repair(TENANT)
        self.assertTrue(again["ok"], again)
        self.assertEqual(again["repaired"], [], "repair is not idempotent")
        self.assertGreaterEqual(again["already_repaired"], 1)
        self.assertEqual(before, self.snapshot(E.DOMAINS, E.CHARTERS,
                                               E.PLACEMENTS))
        self.assertEqual(self.cli("repair")[0], 0)

    def test_12b_repair_does_not_re_mint_after_a_legitimate_merge(self):
        """§0.15 guard: a merged domain's charters already have successors, so
        `repair` must skip them — otherwise every merge grows a new successor
        on every run, forever."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        self.seed_charter(alpha, "Alpha Charter")
        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])
        rep = E.repair(TENANT)
        self.assertEqual(rep["repaired"], [], rep)
        self.assertGreaterEqual(rep["already_repaired"], 1)


# ================================================================= 13 ======

class TestLiveRefs(Phase0Case):

    def test_13_live_refs_hides_tombstones_but_domain_path_still_resolves(self):
        """§9: `live_refs()` at the five RENDER surfaces only. `domain_path()`
        always computes over the UNFILTERED map — a retired sibling keeps its
        D-number permanently."""
        E = self.E
        root, alpha, beta, sub = self.seed_org()
        self.seed_charter(alpha, "Alpha Charter")
        full_before = E.load_domains()
        path_before = E.domain_path(alpha, full_before)
        beta_path_before = E.domain_path(beta, full_before)
        sub_path_before = E.domain_path(sub, full_before)
        # Ordinals are asserted as INVARIANTS, never as literals: siblings
        # minted inside the same millisecond tie-break on the ref hash
        # (`domain_path` sorts by (ts_minted_ms, ref)), so which of Alpha/Beta
        # is D1 is stable on disk but not stable across fixture runs. What the
        # D-number-permanence rule actually promises is that these three
        # strings do not move when a sibling retires.
        self.assertEqual({path_before, beta_path_before}, {"D1", "D2"})
        self.assertEqual(sub_path_before, path_before + ".D1")

        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])
        domains = E.load_domains()

        # --- excluded from the CHOICE/RENDER surfaces ------------------------
        self.assertNotIn(alpha, E.live_refs(domains))
        self.assertIn(alpha, domains, "load_domains() must keep NO default filter")
        scored = E.score_domains(E.gather_evidence("alpha billing work"),
                                 TENANT, domains)
        self.assertNotIn(alpha, scored, "a tombstone must not be a candidate")
        ref, _conf, _mode = E.classify(
            E.gather_evidence("alpha billing work"), TENANT, domains)
        self.assertNotEqual(ref, alpha)

        code, tree = self.cli("tree")
        self.assertEqual(code, 0)
        shown = {r["ref"] for r in tree["domains"]}
        self.assertNotIn(alpha, shown)
        self.assertTrue({root, beta, sub} <= shown)
        self.assertEqual(tree["retired_hidden"], 1)
        code, tree_all = self.cli("tree", "--all")
        self.assertIn(alpha, {r["ref"] for r in tree_all["domains"]})
        arow = [r for r in tree_all["domains"] if r["ref"] == alpha][0]
        self.assertEqual(arow["status"], "retired")
        self.assertEqual(arow["successor_refs"], [beta])

        code, hits = self.cli("search", "Alpha")
        self.assertEqual(code, 0)
        self.assertNotIn(path_before, [h["path"] for h in hits["hits"]],
                         "search offered a retired domain as a destination")

        # --- but the ref still RESOLVES, and ordinals are permanent ----------
        self.assertTrue(os.path.exists(self.dpath(alpha)))
        self.assertEqual(E.domain_path(alpha, domains), path_before,
                         "the tombstone lost its D-number")
        self.assertEqual(E.domain_path(beta, domains), beta_path_before,
                         "a live sibling was RENUMBERED by the retirement")
        self.assertEqual(E.domain_path(sub, domains), beta_path_before + ".D1",
                         "the re-parented child took a new ordinal under Beta")
        self.assertEqual([n["ref"] for n in E.ancestor_chain(alpha, domains)],
                         [root, alpha])
        # write_placement's I-P2 check reads the FULL map, so history holds
        self.assertIn(alpha, E.load_domains())
        self.assertTrue(E.lint_full()["ok"])

    def test_13c_the_publish_surface_hides_tombstones_keeps_their_charters(self):
        """§2.1 names FIVE live_refs() surfaces; "the index-rail builder in
        domains_page.py" is the fifth — and the only one that auto-commits to a
        public GitHub Pages repo. Before I-D5 the `os.remove()` calls hid merged
        domains from the site implicitly; the row now stays on disk.

        The read-path table's other half holds at the same time: registry.json
        must still carry the tombstone's charters (§3.2.4's Archive tray, P0).
        """
        E = self.E
        import domains_page as P
        root, _alpha, beta, _sub = self.seed_org()
        # a name that appears NOWHERE else — "Alpha" is a substring of both
        # "Alpha Sub" and "Alpha Charter", so it cannot prove absence.
        gone, _ = E.mint_domain(root, "Zephyr Payables", ["zephyr"], TENANT)
        gcid = self.seed_charter(gone, "Legacy Payables Promise")
        self.assertTrue(E.restructure("merge", gone, target=beta,
                                      tenant_id=TENANT)["ok"])

        out_dir = os.path.join(self.home, "site")
        self.assertGreater(P.build_site(out_dir, label="Departments",
                                        tenant_id=TENANT), 0)
        files = sorted(os.listdir(out_dir))
        self.assertNotIn(gone + ".html", files,
                         "a retired domain kept its own published page")
        for fn in files:
            if not fn.endswith(".html"):
                continue
            text = self.read_text(os.path.join(out_dir, fn))
            self.assertNotIn("Zephyr Payables", text,
                             "retired department rendered in %s" % fn)
            self.assertNotIn(gone, text,
                             "retired department linked from %s" % fn)

        flat = os.path.join(self.home, "flat.html")
        P.build(flat, label="Departments", tenant_id=TENANT)
        self.assertNotIn("Zephyr Payables", self.read_text(flat))

        # ...but its charters survive in the registry, on BOTH export lanes
        reg = self.read_json(os.path.join(out_dir, "registry.json"))
        self.assertIn(gcid, reg["charters"],
                      "a charter homed to a tombstone vanished from "
                      "registry.json — §2.1 read-path table")
        exp = os.path.join(self.home, "export")
        os.makedirs(exp, exist_ok=True)
        P.export_registry_only(exp, tenant_id=TENANT)
        self.assertEqual(set(self.read_json(os.path.join(exp, "registry.json"))
                             ["charters"]), set(reg["charters"]))

    def test_13d_a_second_live_root_is_loud_not_last_wins(self):
        """`build_site` picked the root by last-wins dict iteration, so
        index.html was nondeterministic and the losing root's whole subtree
        vanished from the published site with no error."""
        E = self.E
        import domains_page as P
        self.seed_org()
        E.mint_domain(None, "Acme Holdings", ["holdings"], TENANT,
                      origin="operator")
        with self.assertRaises(SystemExit):
            P.build_site(os.path.join(self.home, "site2"), tenant_id=TENANT)

    def test_13b_floor_hold_never_lands_work_on_a_tombstone(self):
        """`_nearest_live_ancestor`: a floor-hold must resolve to a LIVE node."""
        E = self.E
        root, alpha, beta, sub = self.seed_org()
        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])
        domains = E.load_domains()
        self.assertEqual(E._nearest_live_ancestor(alpha, domains), root)
        self.assertEqual(E._nearest_live_ancestor(sub, domains), sub)


# ================================================================= 14 ======

class TestTenantFiltering(Phase0Case):

    def _seed_two_tenants(self):
        E = self.E
        a_root, a_alpha, a_beta, _a_sub = self.seed_org(TENANT, "Acme Local")
        b_root, _ = E.mint_domain(None, "Zebra Holdings", ["zebra"],
                                  OTHER_TENANT, origin="operator")
        b_kid, _ = E.mint_domain(b_root, "Bravo Logistics", ["bravo"],
                                 OTHER_TENANT)
        self.seed_charter(a_alpha, "Alpha Charter", TENANT)
        self.seed_charter(b_kid, "Bravo Secret Charter", OTHER_TENANT)
        return a_root, a_alpha, a_beta, b_root, b_kid

    def test_14_a_second_root_is_refused_rather_than_filtered(self):
        """TENANCY IS GONE, and this test replaces the one that specified it.

        What was here: `test_14_tenant_filtering_keeps_the_second_tenant_out_of
        _every_surface`. It seeded TWO tenants in ONE registry -- two parent-less
        roots -- and asserted that tree / search / the classifier / build_site /
        export_registry_only each filtered the second one out by label, with
        `--all-tenants` as the explicit opt-out.

        That capability has been REMOVED, deliberately, and this is the honest
        record of what was given up: two organisations can no longer share a
        registry. It was never isolation -- the selector was an env var, the
        kit was shared, and `tenant_refs`'s own docstring said "do not describe
        it with the word isolation" -- but it WAS a working misrouting guard,
        and it is gone.

        The replacement boundary is coarser and actually enforced: ONE REGISTRY
        PER PARTY (a separate SUTRA_NATIVE_HOME). A second org is not a label in
        this registry; it is a different registry.

        So the contract is now the opposite of the old one. A second parent-less
        root is not a tenant to be filtered -- it is damage, and every publish
        surface must refuse it LOUDLY rather than silently emit one arbitrary
        subtree.
        """
        E = self.E
        import domains_page as P

        a_root, _a_alpha, _a_beta, b_root, _b_kid = self._seed_two_tenants()
        domains = E.load_domains()

        # the label no longer selects anything
        self.assertEqual(len(E.tenant_refs(domains, TENANT)), len(domains),
                         "tenant_refs is retired and must be an identity function")
        self.assertEqual(len(E.tenant_refs(domains, OTHER_TENANT)), len(domains))

        # containment does, and it is the publish input set now
        under_a = E.subtree_refs(domains, a_root)
        self.assertIn(a_root, under_a)
        self.assertNotIn(b_root, under_a,
                         "a second root is not under the first by construction")

        # and BOTH publish surfaces refuse the ambiguity instead of guessing.
        # export_registry_only is the one that had no root assertion at all --
        # a drift-timer hook commits and pushes its output to a public repo.
        out_dir = os.path.join(self.home, "site")
        os.makedirs(out_dir, exist_ok=True)
        for fn, name in ((lambda: P.build_site(out_dir, label="Departments"), "build_site"),
                         (lambda: P.export_registry_only(out_dir), "export_registry_only")):
            with self.assertRaises(SystemExit, msg="%s must refuse two roots" % name) as cm:
                fn()
            self.assertIn("parent-less", str(cm.exception))

    def test_14b_root_lookup_no_longer_depends_on_a_label(self):
        """_root_ref matched `parent_ref is None AND tenant_id == X`. The tenant
        conjunct was the only thing that could make it miss on a registry that
        plainly has a root, and the miss MINTS A SECOND ROOT -- manufacturing
        exactly the damage the test above refuses. A mistyped PLACEMENT_TENANT
        was enough to trigger it."""
        E = self.E
        a_root, _a1, _a2, _b_root, _b_kid = self._seed_two_tenants()
        before = len(E.load_domains())
        # a tenant that has never existed used to mint a fresh "Root"
        got = E._root_ref("T-does-not-exist")
        self.assertEqual(len(E.load_domains()), before,
                         "root lookup must not MINT anything")
        self.assertIsNone(E.load_domains()[got].get("parent_ref"),
                          "the resolved ref must actually be a root")

    def test_15_mint_skips_non_active_siblings_and_refuses_a_dead_parent(self):
        """§2.1 I-D5: name reuse mints a NEW ref, never adopts the tombstone;
        minting under a frozen/retired parent is refused."""
        E = self.E
        root, alpha, beta, _sub = self.seed_org()
        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])

        again, created = E.mint_domain(root, "Alpha", ["alpha"], TENANT)
        self.assertTrue(created)
        self.assertNotEqual(again, alpha,
                            "I-D5: dedupe adopted a tombstone (name reuse)")
        self.assertEqual(E._load_domain(again)["status"], "active")
        # ...and it is genuinely idempotent among LIVE siblings
        third, created3 = E.mint_domain(root, "Alpha", ["alpha"], TENANT)
        self.assertFalse(created3)
        self.assertEqual(third, again)

        # a retired parent accepts nothing
        with self.assertRaises(ValueError):
            E.mint_domain(alpha, "Orphan", ["orphan"], TENANT)
        # ...nor a frozen one. Freeze is a WRITE boundary, not a read filter:
        # the frozen node stays a live_refs() candidate so the classifier can
        # still match it instead of manufacturing the duplicate it prevents.
        E.set_domain_fields(beta, status="frozen")
        with self.assertRaises(ValueError):
            E.mint_domain(beta, "Orphan", ["orphan"], TENANT)
        self.assertIn(beta, E.live_refs(E.load_domains()))

    def test_15c_mint_participates_in_the_restructure_flock(self):
        """§2.1 Mint interlock (P0): "`mint_domain` participates in the
        RESTRUCTURE flock".

        The per-parent lock is `domains/<parent>.lock` while retire/restructure
        hold `domains/RESTRUCTURE.lock` — two different lock FILES, therefore
        ZERO mutual exclusion. The race: session A holds RESTRUCTURE across
        `retire D --successor E` and re-parents D's children from a snapshot
        taken under it; session B mints a child of D, sees status=='active'
        (A has not stamped it yet) and writes. The child ends up parented to a
        tombstone, absent from the disposition report, and no verb ever notices.

        Asserted from a SEPARATE PROCESS: `_lock` is re-entrant within one
        process (`_HELD`), so a same-process helper would sail straight through
        and prove nothing.
        """
        E = self.E
        root, _alpha, _beta, _sub = self.seed_org()
        ready = os.path.join(self.home, "held")
        release = os.path.join(self.home, "release")
        holder = (
            "import os, sys, time\n"
            "sys.path.insert(0, %r)\n"
            "os.environ['SUTRA_NATIVE_HOME'] = %r\n"
            "import placement_engine as E\n"
            "with E._lock('RESTRUCTURE'):\n"
            "    open(%r, 'w').write('1')\n"
            "    while not os.path.exists(%r):\n"
            "        time.sleep(0.01)\n" % (_LIB, self.home, ready, release))
        proc = subprocess.Popen([sys.executable, "-c", holder])
        try:
            for _ in range(1000):
                if os.path.exists(ready):
                    break
                time.sleep(0.01)
            self.assertTrue(os.path.exists(ready),
                            "the helper process never took RESTRUCTURE")
            done = []
            t = threading.Thread(
                target=lambda: done.append(
                    E.mint_domain(root, "Late Child", ["late"], TENANT)))
            t.daemon = True
            t.start()
            t.join(0.6)
            self.assertEqual(done, [],
                             "mint_domain landed while another process held "
                             "RESTRUCTURE — the per-parent flock is a different "
                             "lock file and excludes nothing")
            with open(release, "w") as fh:
                fh.write("1")
            t.join(10)
            self.assertEqual(len(done), 1, "mint never completed after release")
            self.assertTrue(done[0][1])
        finally:
            if not os.path.exists(release):
                with open(release, "w") as fh:
                    fh.write("1")
            proc.wait(timeout=15)

    def test_15d_a_mint_racing_a_retire_is_refused_with_ORG_016(self):
        """The other half of the interlock: once the stamp lands, the mint is
        refused rather than parenting a live child to a tombstone."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        self.assertTrue(E.retire(alpha, successor_ref=beta,
                                 tenant_id=TENANT)["ok"])
        with self.assertRaises(ValueError) as cm:
            E.mint_domain(alpha, "Late Child", ["late"], TENANT)
        self.assertIn("ORG-016", str(cm.exception))
        self.assertEqual([r for r, d in E.load_domains().items()
                          if d.get("parent_ref") == alpha], [])
        # ...and the turn path does NOT crash on it (I-P3): resolve holds at the
        # nearest live ancestor instead of propagating the refusal.
        r = E.resolve({"kind": "file", "id": "/w/x.md"}, utterance="",
                      paths=[], tenant_id=TENANT)
        self.assertIn("placement", r)

    def test_15b_resolve_never_raises_when_the_root_is_a_tombstone(self):
        """I-P3 regression: mint refusing a dead parent must not make resolve()
        raise. `_root_ref` returns the LIVE root, exactly as `_tenant_root` does."""
        E = self.E
        # a root can only be retired by merging it into a node OUTSIDE its own
        # subtree — i.e. a second root. `merge root -> own child` is already
        # refused as a cycle, which is the check this one sits behind.
        r1, _ = E.mint_domain(None, "Acme", ["acme"], TENANT, origin="operator")
        r2, _ = E.mint_domain(None, "Acme Holdings", ["holdings"], TENANT,
                              origin="operator")
        root = E._root_ref(TENANT)
        other = r2 if root == r1 else r1
        self.assertTrue(E.restructure("merge", root, target=other,
                                      tenant_id=TENANT)["ok"])
        self.assertEqual(E._load_domain(root)["status"], "retired")

        live_root = E._root_ref(TENANT)
        self.assertEqual(live_root, other)
        self.assertNotEqual(live_root, root)
        self.assertEqual(E._load_domain(live_root).get("status", "active"),
                         "active")
        r = E.resolve({"kind": "file", "id": "/w/loose.md"},
                      utterance="", paths=[], tenant_id=TENANT)
        self.assertIn("placement", r)
        self.assertNotEqual(r["placement"]["domain_ref"], root)
        self.assertTrue(E.lint_full()["ok"])


class TestLockedDomainWrites(Phase0Case):

    def test_16_every_field_write_goes_through_one_audited_save(self):
        """§9: route every domain field write through `_save_domain()` under
        `_lock('RESTRUCTURE')`, appending `domain_updated {ref, before, after}`.
        `domains_pipeline._set_field` was an unlocked read-modify-write."""
        E = self.E
        import domains_pipeline as DP
        _root, alpha, _beta, _sub = self.seed_org()
        n_before = len(self.index_rows())

        DP._set_field(alpha, description="Owns invoicing.",
                      touched_by_operator=True)
        d = E._load_domain(alpha)
        self.assertEqual(d["description"], "Owns invoicing.")
        self.assertTrue(d["touched_by_operator"])

        rows = [x for x in self.index_rows()[n_before:]
                if x.get("event") == "domain_updated" and x.get("ref") == alpha]
        self.assertEqual(len(rows), 1, self.index_rows()[n_before:])
        self.assertEqual(rows[0]["after"]["description"], "Owns invoicing.")
        self.assertEqual(rows[0]["before"].get("description"), None)
        self.assertEqual(rows[0]["tenant_id"], TENANT)

        # a no-op write stays idempotent: same values, no second event
        DP._set_field(alpha, description="Owns invoicing.")
        rows = [x for x in self.index_rows()
                if x.get("event") == "domain_updated" and x.get("ref") == alpha]
        self.assertEqual(len(rows), 1, "a no-op write emitted a history row")

    def test_16c_writes_to_rows_other_than_the_event_subject_are_audited(self):
        """§9: "`domain_updated {ref, before, after, ts_ms}`" on EVERY domain
        field write. The `emit=False` default leaned on `domain_restructured`
        covering the same before/after — but `_domain_snapshot()`/`_delta()`
        snapshot ONLY the retiring `ref`, so a merge's permanent append to the
        surviving target's `principles` and every child re-parent landed with
        no audit row anywhere."""
        E = self.E
        _root, alpha, beta, sub = self.seed_org()
        E.set_domain_fields(alpha, principles=["ship weekly"])
        n = len(self.index_rows())

        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])
        upd = [x for x in self.index_rows()[n:]
               if x.get("event") == "domain_updated"]

        tgt = [x for x in upd if x["ref"] == beta]
        self.assertEqual(len(tgt), 1,
                         "the surviving target's mutation had no audit row")
        self.assertIn("ship weekly", tgt[0]["after"]["principles"])
        self.assertTrue(tgt[0]["after"]["touched_by_operator"])
        self.assertEqual(tgt[0]["tenant_id"], TENANT)

        kid = [x for x in upd if x["ref"] == sub]
        self.assertEqual(len(kid), 1,
                         "the child re-parent appeared only as a disposition "
                         "summary, never as before/after on the child's row")
        self.assertEqual(kid[0]["before"]["parent_ref"], alpha)
        self.assertEqual(kid[0]["after"]["parent_ref"], beta)

        # the SUBJECT stays single-logged: domain_restructured already carries it
        self.assertEqual([x for x in upd if x["ref"] == alpha], [],
                         "the event's own ref was double-logged")

    def test_16b_the_restructure_lock_is_re_entrant(self):
        """`_save_domain` takes _lock('RESTRUCTURE') from INSIDE retire, which
        already holds it. flock keys on the open file description, so without
        the depth counter this self-deadlocks."""
        E = self.E
        _root, alpha, beta, _sub = self.seed_org()
        with E._lock("RESTRUCTURE"):
            with E._lock("RESTRUCTURE"):
                E.set_domain_fields(alpha, description="nested")
        self.assertEqual(E._load_domain(alpha)["description"], "nested")
        self.assertEqual(E._HELD, {})
        self.assertTrue(E.retire(alpha, successor_ref=beta,
                                 tenant_id=TENANT)["ok"])


class TestPipelineStatus(Phase0Case):

    def test_18_status_counts_bodies_not_sidecars_and_live_coverage(self):
        """§2.2's split made `charters/<C-id>.page.json` sidecars end in
        `.json` too. Every other consumer moved to `charter_body_files()`;
        `domains_pipeline.status()` still did a raw listdir, so `charters.total`
        was ~2x the real count, `standing` gained one per sidecar (no `kind` ->
        the default) and `covered` gained a None from each sidecar's absent
        `domain_ref`."""
        E = self.E
        import domains_pipeline as DP
        root, alpha, beta, _sub = self.seed_org()
        self.seed_charter(alpha, "Alpha Charter")
        self.seed_charter(beta, "Beta Charter", kind="project")
        self.assertEqual(len(E.charter_body_files()), 2)
        self.assertEqual(len([fn for fn in os.listdir(E.CHARTERS)
                              if fn.endswith(".json")]), 4,
                         "fixture: two bodies AND two sidecars on disk")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            DP.status()
        st = json.loads(buf.getvalue())
        self.assertEqual(st["charters"]["total"], 2)
        self.assertEqual(st["charters"]["standing"], 1)
        self.assertEqual(st["charters"]["project"], 1)

        # ...and coverage is a LIVE-tree question: a tombstone is not a gap
        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            DP.status()
        st = json.loads(buf.getvalue())
        self.assertEqual(st["domains_live"], len(E.live_refs(E.load_domains())))
        self.assertNotIn("Alpha", st["coverage"]["domains_without_charter"])
        self.assertNotIn("Alpha", st["coverage"]["domains_without_description"])
        self.assertIsNotNone(root)


class TestReadPathSweep(Phase0Case):

    def test_17_the_five_read_path_call_sites_still_see_the_full_map(self):
        """§9 auditable sweep: `load_domains()`'s default is UNCHANGED, and
        every read-path consumer keeps receiving tombstones."""
        E = self.E
        root, alpha, beta, _sub = self.seed_org()
        cid = self.seed_charter(alpha, "Alpha Charter")
        self.seed_placement("/w/alpha.md", alpha, cid)
        self.assertTrue(E.restructure("merge", alpha, target=beta,
                                      tenant_id=TENANT)["ok"])

        domains = E.load_domains()
        self.assertIn(alpha, domains)                     # load_domains
        self.assertTrue(E.domain_path(alpha, domains))    # domain_path
        self.assertEqual([c["id"] for c in E.charters_for(alpha)], [cid])
        self.assertTrue(E.lint_full()["ok"])              # lint
        votes = E._adjacent_domain_votes(["/w/alpha.md"])  # _adjacent_domain_votes
        self.assertIn(beta, votes)
        # write_placement's I-P2 check: the tombstone still resolves, so the
        # merge's own superseding write could not have rejected itself.
        self.assertEqual(
            E.write_placement({"kind": "file", "id": "/w/x.md"}, root,
                              self.seed_charter(root, "Root Charter"),
                              "matched", 0.7, {"domains": [], "charters": []},
                              TENANT)["domain_ref"], root)
        with self.assertRaises(ValueError):
            E.write_placement({"kind": "file", "id": "/w/y.md"}, "dref-nope",
                              cid, "matched", 0.7,
                              {"domains": [], "charters": []}, TENANT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
