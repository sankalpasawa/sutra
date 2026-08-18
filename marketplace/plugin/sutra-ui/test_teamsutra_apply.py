"""test_teamsutra_apply.py — the task.apply ladder (APPLY-DESIGN v1.1).

_ts_apply takes an injectable `run`, so every rung — origin verification,
auth preflight, PR adoption, dead-branch clearing, policy refusals, the
push-failure path — is provable without git, gh, or the network. What is
pinned here, in order of importance:

  1. main is unreachable: no invocation ever pushes anything but the
     teamsutra/* branch, and a wrong origin refuses before any mutation.
  2. Failure leaves the task AT needs_review with a recorded apply_error —
     no transition, no corruption, lock always released.
  3. The patch-policy gate runs before any subprocess at all.
"""
import os
import shutil
import tempfile
import unittest


GOOD_DIFF = """diff --git a/static/js/11-teamsutra.js b/static/js/11-teamsutra.js
index 1111111..2222222 100644
--- a/static/js/11-teamsutra.js
+++ b/static/js/11-teamsutra.js
@@ -1,1 +1,1 @@
-old
+new
"""

CI_DIFF = GOOD_DIFF.replace("static/js/11-teamsutra.js", ".github/workflows/x.yml")

# What the worker's ts_extract_diff actually emits: a bare unified diff,
# ---/+++ headers only, no `diff --git` line. The 2.107.0 gate refused this
# shape — every real worker diff — so this fixture pins the 2.107.1 fix.
BARE_DIFF = """--- a/marketplace/plugin/sutra-ui/routines.py
+++ b/marketplace/plugin/sutra-ui/routines.py
@@ -1,1 +1,1 @@
-old
+new
"""

BARE_CI_DIFF = BARE_DIFF.replace("marketplace/plugin/sutra-ui/routines.py",
                                 ".github/workflows/x.yml")

HAPPY = [
    ("git remote get-url origin", (0, "git@github.com:sankalpasawa/sutra.git\n", "")),
    ("gh auth status", (0, "logged in", "")),
    ("gh api repos/sankalpasawa/sutra", (0, "true\n", "")),
    ("gh pr list", (0, "", "")),
    ("git ls-remote", (0, "", "")),
    ("git push origin --delete", (0, "", "")),
    ("git fetch", (0, "", "")),
    ("git branch -D", (1, "", "not found")),
    ("git worktree add", (0, "", "")),
    ("git apply --check", (0, "", "")),
    ("git apply", (0, "", "")),
    ("git add -A", (0, "", "")),
    ("git commit", (0, "", "")),
    ("git push origin teamsutra/", (0, "", "")),
    ("gh pr create", (0, "https://github.com/sankalpasawa/sutra/pull/999\n", "")),
    ("git worktree remove", (0, "", "")),
]


def fake_runner(script, calls):
    def run(args, cwd, timeout=None):
        calls.append(tuple(args))
        joined = " ".join(args)
        for prefix, resp in script:
            if joined.startswith(prefix):
                return resp
        return (0, "", "")
    return run


class TestTsApply(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix=".sutra-test-", dir=os.path.expanduser("~"))
        self._env = dict(os.environ)
        os.environ["SUTRA_UI_TEAMSUTRA"] = os.path.join(self.tmp, "teamsutra")
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        os.environ["SUTRA_UI_TEAMSUTRA_REPO"] = repo
        import teamsutra
        import org_api
        self.T, self.A = teamsutra, org_api

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reviewed_task(self, diff=GOOD_DIFF):
        rec = self.T.create({"title": "bubble z-index", "body": "b", "kind": "bug",
                             "source": {"selection": None, "screen": "x",
                                        "domain_ref": None}})
        self.T.set_status(rec["id"], "queued")
        self.T.set_status(rec["id"], "claimed")
        self.T.set_status(rec["id"], "needs_review", diff=diff)
        return rec["id"]

    def test_happy_path_opens_pr_and_never_touches_main(self):
        tid = self._reviewed_task()
        calls = []
        out = self.A._ts_apply(tid, run=fake_runner(HAPPY, calls))
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["pr_url"], "https://github.com/sankalpasawa/sutra/pull/999")
        self.assertEqual(out["pr_state"], "open")
        for c in calls:
            if c[:2] == ("git", "push"):
                self.assertNotIn("main", c)                 # branch push only
                self.assertEqual(c[2], "origin")            # remote allowlist
        self.assertFalse((self.T.store_dir() / (".apply-lock-" + tid)).exists())

    def test_push_failure_stays_at_needs_review_with_error(self):
        tid = self._reviewed_task()
        script = [(p, r) for p, r in HAPPY if not p.startswith("git push origin teamsutra/")]
        script.insert(0, ("git push origin teamsutra/", (1, "", "remote: denied")))
        calls = []
        with self.assertRaises(ValueError):
            self.A._ts_apply(tid, run=fake_runner(script, calls))
        rec = self.T.load(tid)
        self.assertEqual(rec["status"], "needs_review")
        self.assertIn("push", rec["apply_error"])
        self.assertIn(("git", "worktree", "remove", "--force"),
                      [c[:4] for c in calls])               # cleanup ran
        self.assertFalse((self.T.store_dir() / (".apply-lock-" + tid)).exists())

    def test_policy_refuses_ci_paths_before_any_subprocess(self):
        tid = self._reviewed_task(diff=CI_DIFF)
        calls = []
        with self.assertRaises(ValueError):
            self.A._ts_apply(tid, run=fake_runner(HAPPY, calls))
        self.assertEqual(calls, [])                         # no git/gh at all
        rec = self.T.load(tid)
        self.assertEqual(rec["status"], "needs_review")
        self.assertIn("policy-denied path", rec["apply_error"])

    def test_open_pr_is_adopted_not_duplicated(self):
        tid = self._reviewed_task()
        script = [("gh pr list", (0, "https://github.com/sankalpasawa/sutra/pull/500\n", ""))] + HAPPY
        calls = []
        out = self.A._ts_apply(tid, run=fake_runner(script, calls))
        self.assertEqual(out["pr_url"], "https://github.com/sankalpasawa/sutra/pull/500")
        self.assertEqual(out["status"], "done")
        self.assertNotIn(("git", "worktree", "add"),
                         [c[:3] for c in calls])            # no second attempt

    def test_wrong_origin_refuses_before_mutation(self):
        tid = self._reviewed_task()
        script = [("git remote get-url origin",
                   (0, "git@github.com:tchandrakar/sutra.git\n", ""))] + HAPPY[1:]
        calls = []
        with self.assertRaises(ValueError):
            self.A._ts_apply(tid, run=fake_runner(script, calls))
        self.assertIn("origin is not", self.T.load(tid)["apply_error"])
        mutating = [c for c in calls if c[:2] in (("git", "push"), ("git", "commit"),
                                                  ("git", "apply"))]
        self.assertEqual(mutating, [])

    def test_worker_bare_diff_is_accepted(self):
        tid = self._reviewed_task(diff=BARE_DIFF)
        calls = []
        out = self.A._ts_apply(tid, run=fake_runner(HAPPY, calls))
        self.assertEqual(out["status"], "done")
        self.assertTrue(out["pr_url"])

    def test_worker_bare_diff_is_still_policed(self):
        tid = self._reviewed_task(diff=BARE_CI_DIFF)
        with self.assertRaises(ValueError):
            self.A._ts_apply(tid, run=fake_runner(HAPPY, []))
        self.assertIn("policy-denied path", self.T.load(tid)["apply_error"])

    def test_non_needs_review_task_refused(self):
        rec = self.T.create({"title": "t", "body": "b", "kind": "bug",
                             "source": {"selection": None, "screen": "x",
                                        "domain_ref": None}})
        with self.assertRaises(ValueError):
            self.A._ts_apply(rec["id"], run=fake_runner(HAPPY, []))


if __name__ == "__main__":
    unittest.main()
