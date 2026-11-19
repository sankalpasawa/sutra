"""Pulse tests. Plain script, stdlib only, mock mode, temp dirs only.

Run: cd prototypes/pulse && python3 pulse_test.py
Google libraries are blocked and sockets raise, so any accidental network or Google import fails loudly.
"""
import sys

# Block Google libraries before anything can import them (FR-5, NFR-1).
for _name in ("google", "google.auth", "google.oauth2", "google.oauth2.service_account",
              "googleapiclient", "googleapiclient.discovery", "googleapiclient.errors"):
    sys.modules[_name] = None

import socket  # noqa: E402


class _NoSocket:
    def __init__(self, *a, **k):
        raise RuntimeError("network disabled in pulse_test.py")


socket.socket = _NoSocket
socket.create_connection = _NoSocket

import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config  # noqa: E402
import errors  # noqa: E402
from errors import PulseError, TransientError, HistoryExpired  # noqa: E402


class BaseCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"
        self.state = self.tmp / "state"
        self.home = self.tmp / "home"
        for d in (self.out, self.state, self.home):
            d.mkdir()
        self.env_file = self.tmp / ".env"
        self.env_file.write_text("", encoding="utf-8")

    def tearDown(self):
        # Restore write permission so cleanup works after read-only tests.
        for root, dirs, _files in os.walk(self.tmp):
            for d in dirs:
                p = os.path.join(root, d)
                if not os.path.islink(p):
                    os.chmod(p, 0o700)
        self._tmp.cleanup()

    def env(self, mock=True, **extra):
        e = {"HOME": str(self.home), "PULSE_OUT_DIR": str(self.out), "PULSE_STATE_DIR": str(self.state)}
        if mock:
            e["PULSE_MOCK"] = "1"
        e.update(extra)
        return e

    def run_cli(self, argv, env=None, scenario=None, factory=None, now=None):
        """Run cli.main in-process against temp dirs. Records every client built and every sleep."""
        env = dict(self.env() if env is None else env)
        if scenario:
            env["PULSE_MOCK_SCENARIO"] = scenario
        self.clients = []
        self.sleeps = Recorder()

        def fac(cfg, mailbox):
            c = (factory or gmail_client.make_client)(cfg, mailbox)
            self.clients.append(c)
            return c
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(argv, environ=env, env_file=self.env_file, client_factory=fac, sleep=self.sleeps,
                        now=now, stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()

    def calls(self) -> list:
        return [n for c in getattr(self, "clients", []) for n in getattr(c, "call_names", list)()]

    def audit_rows(self) -> list:
        return read_audit(self.state)


# ---------------------------------------------------------------- T2: config and error mappers
class ConfigTests(BaseCase):
    def test_config_shell_wins(self):  # AC-3
        self.env_file.write_text("PULSE_DOMAIN=a.test\n", encoding="utf-8")
        cfg = config.load(self.env(mock=False, PULSE_DOMAIN="b.test"), self.env_file, need_live_keys=False)
        self.assertEqual(cfg.domain, "b.test")
        cfg = config.load(self.env(mock=False, PULSE_DOMAIN=""), self.env_file, need_live_keys=False)
        self.assertEqual(cfg.domain, "a.test")

    def test_env_file_quotes_comments(self):
        self.env_file.write_text('# c\n\nPULSE_DOMAIN="q.test"\nPULSE_RETENTION_DAYS=\'7\'\n', encoding="utf-8")
        cfg = config.load(self.env(mock=False), self.env_file, need_live_keys=False)
        self.assertEqual(cfg.domain, "q.test")
        self.assertEqual(cfg.retention_days, 7)

    def test_mock_value_invalid(self):
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(PULSE_MOCK="yes"), self.env_file, need_live_keys=True)
        self.assertEqual(cm.exception.code, "config_invalid")
        self.assertIn("PULSE_MOCK", cm.exception.message)

    def test_retention_bounds(self):
        for bad in ("0", "3651", "x"):
            with self.assertRaises(PulseError) as cm:
                config.load(self.env(PULSE_RETENTION_DAYS=bad), self.env_file, need_live_keys=True)
            self.assertEqual(cm.exception.code, "config_invalid")
        for good in ("1", "3650"):
            cfg = config.load(self.env(PULSE_RETENTION_DAYS=good), self.env_file, need_live_keys=True)
            self.assertEqual(cfg.retention_days, int(good))

    def test_live_missing_key_config_missing(self):  # AC-4 (config part)
        secret_like = "placeholder-domain-value.test"
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(mock=False, PULSE_DOMAIN=secret_like, PULSE_ALLOWLIST="/x"),
                        self.env_file, need_live_keys=True)
        self.assertEqual(cm.exception.code, "config_missing")
        self.assertEqual(cm.exception.exit_code, 2)
        self.assertIn("PULSE_SA_KEY_PATH", cm.exception.message)
        self.assertNotIn(secret_like, cm.exception.message)

    def test_mock_ignores_live_values(self):  # AC-4 (config part), R-2
        cfg = config.load(self.env(PULSE_DOMAIN="realcompany.example", PULSE_SA_KEY_PATH="",
                                   PULSE_ALLOWLIST="/nope"), self.env_file, need_live_keys=True)
        self.assertTrue(cfg.mock)
        self.assertEqual(cfg.domain, "example.test")
        self.assertEqual(cfg.allowlist, config.FIXTURES / "allowlist.txt")
        self.assertIsNone(cfg.sa_key_path)

    def test_defaults_under_home(self):
        cfg = config.load({"HOME": str(self.home), "PULSE_MOCK": "1"}, self.env_file, need_live_keys=True)
        self.assertEqual(cfg.out_dir, self.home / ".sutra-pulse" / "out")
        self.assertEqual(cfg.state_dir, self.home / ".sutra-pulse" / "state")
        self.assertEqual(cfg.retention_days, 30)
        self.assertEqual(cfg.scenario, "default")

    def test_scenario_comment_key_rejected(self):  # R1-12
        self.assertNotIn("_note", config.scenario_names())
        self.assertIn("history_deleted", config.scenario_names())
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(PULSE_MOCK_SCENARIO="_note"), self.env_file, need_live_keys=True)
        self.assertEqual(cm.exception.code, "config_invalid")

    def test_bad_domain(self):
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(mock=False, PULSE_DOMAIN="a@b.test"), self.env_file, need_live_keys=False)
        self.assertEqual(cm.exception.code, "config_invalid")


class ErrorMapperTests(unittest.TestCase):
    def test_error_mapper(self):  # AC-13(c)
        self.assertEqual(errors.map_refresh_error(
            "('unauthorized_client: Client is unauthorized to retrieve access tokens', {})").code,
            "unauthorized_client")
        self.assertEqual(errors.map_refresh_error("invalid_grant: Invalid email or User ID").code, "invalid_grant")
        e = errors.map_refresh_error("something else")  # R1-5 / AC-43: unknown, not retryable
        self.assertEqual((e.code, e.exit_code), ("token_error", 4))
        self.assertNotIn("something else", e.message)
        self.assertIn("revoked or deleted", errors.map_refresh_error("invalid_grant: Invalid JWT Signature").message)
        t = errors.map_refresh_error("('Internal Error', {})", retryable=True)
        self.assertIsInstance(t, TransientError)
        self.assertEqual(t.kind, "token")
        e = errors.map_http_error(403, "accessNotConfigured")
        self.assertEqual((e.code, e.exit_code), ("access_denied", 4))
        self.assertIn("Enable the Gmail API", e.message)
        self.assertIsInstance(errors.map_http_error(404, "notFound"), HistoryExpired)
        for reason in ("rateLimitExceeded", "userRateLimitExceeded"):  # R1-4 / AC-42
            t = errors.map_http_error(403, reason)
            self.assertIsInstance(t, TransientError, reason)
            self.assertEqual(t.status, 429)
        for reason in ("RATE_LIMIT_EXCEEDED", "ratelimitexceeded", "USER_RATE_LIMIT_EXCEEDED"):  # R2-2
            self.assertIsInstance(errors.map_http_error(403, reason), TransientError, reason)
        self.assertEqual(errors.map_http_error(403, "RATE_LIMIT").code, "access_denied")
        e = errors.map_http_error(403, "dailyLimitExceeded")
        self.assertEqual((e.code, e.exit_code), ("rate_limited", 5))
        self.assertNotIn("Enable the Gmail API", e.message)
        for s in (429, 500, 503, 599):
            t = errors.map_http_error(s, "")
            self.assertIsInstance(t, TransientError)
            self.assertEqual(t.status, s)
        e = errors.map_http_error(418, "teapot")
        self.assertEqual(e.code, "internal")
        self.assertIn("418", e.message)
        self.assertIn("Domain-wide delegation", errors.map_refresh_error("unauthorized_client").message)

    def test_exit_table(self):
        self.assertEqual({errors.EXIT[c] for c in ("rate_limited", "server_error", "network_error")}, {5})
        with self.assertRaises(ValueError):
            PulseError("nope", "x")


# ---------------------------------------------------------------- T3: policy
import policy  # noqa: E402

FAKE_KEY = {"type": "service_account", "client_email": "pulse-test@example.test",
            "private_key": "placeholder, not a real key", "client_id": "000000000000",
            "token_uri": "https://oauth2.example.test/token"}


def write_fake_key(path: Path, mode=0o600, data=None):
    path.write_text(json.dumps(FAKE_KEY if data is None else data), encoding="utf-8")
    os.chmod(path, mode)
    return path


class PolicyTests(BaseCase):
    def test_wrong_domain(self):  # AC-8 (unit)
        policy.check_domain("ana@example.test", "example.test")
        for m in ("x@other.test", "x@sub.example.test"):
            with self.assertRaises(PulseError) as cm:
                policy.check_domain(m, "example.test")
            self.assertEqual((cm.exception.code, cm.exception.exit_code), ("wrong_domain", 3))

    def test_allowlist_parsing(self):  # AC-9 (unit)
        al = self.tmp / "allow.txt"
        al.write_text("# c\n\n Ana@Example.test \n", encoding="utf-8")
        self.assertEqual(policy.load_allowlist(al), frozenset({"ana@example.test"}))
        policy.check_allowlist("ana@example.test", al)
        with self.assertRaises(PulseError) as cm:
            policy.check_allowlist("bob@example.test", al)
        self.assertEqual(cm.exception.code, "not_allowlisted")

    def test_allowlist_missing_refuses_all(self):  # AC-9 (unit)
        for p in (self.tmp / "missing.txt", None, self.tmp):  # missing, unset, a directory (unreadable)
            with self.assertRaises(PulseError) as cm:
                policy.check_allowlist("ana@example.test", p)
            self.assertEqual(cm.exception.code, "not_allowlisted")

    def test_mailbox_format(self):  # AC-35 (unit)
        self.assertEqual(policy.normalise_mailbox("  Ana@Example.TEST "), "ana@example.test")
        for bad in ("../x@example.test", "a/b@example.test", "noat", "a@b@c.test", "", "a b@example.test"):
            with self.assertRaises(ValueError):
                policy.normalise_mailbox(bad)

    def test_reason_length(self):  # FR-10 helper
        self.assertEqual(policy.check_reason("  ten chars!  "), "ten chars!")
        for bad in ("", "short", "x" * 501):
            with self.assertRaises(ValueError):
                policy.check_reason(bad)
        policy.check_reason("x" * 500)

    def test_key_file_errors(self):  # AC-13(b) (unit)
        with self.assertRaises(PulseError) as cm:
            policy.check_key_file(self.tmp / "nokey.json")
        self.assertEqual((cm.exception.code, cm.exception.exit_code), ("key_missing", 4))
        sentinel = "SENTINEL-CONTENT-7f3a"
        cases = {"notjson.json": f"not json {sentinel}",
                 "wrongtype.json": json.dumps({"type": "authorized_user", "note": sentinel}),
                 "nokeys.json": json.dumps({"type": "service_account", "note": sentinel}),
                 "no_token_uri.json": json.dumps({**{k: v for k, v in FAKE_KEY.items() if k != "token_uri"},
                                                  "note": sentinel}),  # R1-6 / AC-44
                 "empty_token_uri.json": json.dumps({**FAKE_KEY, "token_uri": "", "note": sentinel})}
        for name, text in cases.items():
            p = self.tmp / name
            p.write_text(text, encoding="utf-8")
            os.chmod(p, 0o600)
            with self.assertRaises(PulseError) as cm:
                policy.check_key_file(p)
            self.assertEqual(cm.exception.code, "key_unreadable", name)
            self.assertIn(str(p), cm.exception.message)
            self.assertNotIn(sentinel, cm.exception.message)
        with self.assertRaises(PulseError) as cm:
            policy.check_key_file(self.tmp)  # a directory
        self.assertEqual(cm.exception.code, "key_unreadable")

    def test_key_perms_warning(self):  # AC-32 (unit)
        p = write_fake_key(self.tmp / "k.json", 0o600)
        self.assertEqual(policy.check_key_file(p), [])
        os.chmod(p, 0o644)
        warnings = policy.check_key_file(p)
        self.assertEqual(len(warnings), 1)
        self.assertIn("chmod 600", warnings[0])
        self.assertNotIn("placeholder", warnings[0])


# ---------------------------------------------------------------- T4: audit log
import audit  # noqa: E402

IS_ROOT = os.geteuid() == 0


def mode_of(p) -> int:
    return stat.S_IMODE(os.lstat(p).st_mode)


def read_audit(state: Path) -> list:
    p = state / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]


class AuditTests(BaseCase):
    def test_audit_create_and_roundtrip(self):
        sd = self.state / "nested"
        log = audit.AuditLog(sd)
        row = audit.build_row(mode="mock", command="check", mailbox="ana@example.test", reason="unit test",
                              count=0, result="ok")
        log.write(row)
        log.write(row)
        log.close()
        self.assertEqual(mode_of(sd / "audit.jsonl"), 0o600)
        self.assertEqual(mode_of(sd), 0o700)
        rows = read_audit(sd)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], row)
        self.assertEqual(list(rows[0]), list(audit.FIELDS))

    def test_build_row_rejects_unknown(self):
        with self.assertRaises(ValueError):
            audit.build_row(subject="x")
        row = audit.build_row(command="purge")
        self.assertIsNone(row["mailbox"])
        self.assertTrue(row["ts"].endswith("+00:00"))

    def test_audit_unavailable_state_is_file(self):  # AC-28 (unit), works as any user
        f = self.tmp / "statefile"
        f.write_text("x", encoding="utf-8")
        with self.assertRaises(PulseError) as cm:
            audit.AuditLog(f)
        self.assertEqual((cm.exception.code, cm.exception.exit_code), ("audit_unavailable", 3))

    @unittest.skipIf(IS_ROOT, "root ignores directory permissions")
    def test_audit_unavailable_readonly_dir(self):  # AC-28 (unit)
        os.chmod(self.state, 0o500)
        with self.assertRaises(PulseError) as cm:
            audit.AuditLog(self.state)
        self.assertEqual(cm.exception.code, "audit_unavailable")

    def test_audit_symlink_refused(self):  # AC-21 (audit part, unit)
        target = self.tmp / "target.txt"
        target.write_text("original\n", encoding="utf-8")
        (self.state / "audit.jsonl").symlink_to(target)
        with self.assertRaises(PulseError) as cm:
            audit.AuditLog(self.state)
        self.assertEqual(cm.exception.code, "audit_unavailable")
        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")


# ---------------------------------------------------------------- T5: fixtures
import base64  # noqa: E402
from email.header import decode_header, make_header  # noqa: E402

FIX = HERE / "fixtures"
# Copied from marketplace/plugin/hooks/keys-in-env-vars.sh:69 (PROTO-004).
PROTO004 = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|"
                      r"xoxb-[0-9A-Za-z-]{20,}|ya29\.[A-Za-z0-9_-]+|AIza[0-9A-Za-z_-]{35}|"
                      r"-----BEGIN [A-Z ]*PRIVATE KEY-----)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")
PHONE_RE = re.compile(r"\+91[\d ]*\d")


def load_inbox() -> dict:
    return json.loads((FIX / "inbox.json").read_text(encoding="utf-8"))


def fixture_msg(mid: str) -> dict:
    return next(m for m in load_inbox()["messages"] if m["id"] == mid)


def _b64d(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8")


def fixture_texts() -> list:
    """Every text in fixtures/, plus decoded bodies and decoded headers, so encoding cannot hide data."""
    texts = []
    for p in sorted(FIX.iterdir()):
        raw = p.read_text(encoding="utf-8")
        texts.append(raw)
        if p.suffix != ".json":
            continue

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "data" and isinstance(v, str):
                        texts.append(_b64d(v))
                    elif k == "value" and isinstance(v, str) and "=?" in v:
                        texts.append(str(make_header(decode_header(v))))
                    else:
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(json.loads(raw))
    return texts


class FixtureTests(unittest.TestCase):
    def test_fixture_coverage(self):  # AC-29 / FR-29
        inbox = load_inbox()
        msgs = {m["id"]: m for m in inbox["messages"]}
        self.assertGreaterEqual(len(msgs), 12)
        self.assertEqual(inbox["profile"]["messagesTotal"], len(msgs))
        self.assertEqual(inbox["profile"]["threadsTotal"], len({m["threadId"] for m in msgs.values()}))
        self.assertEqual(inbox["page_size"], 5)
        self.assertEqual(msgs["msg-01"]["payload"]["mimeType"], "text/plain")
        self.assertEqual(msgs["msg-02"]["payload"]["mimeType"], "text/html")
        self.assertIn("<script>", _b64d(msgs["msg-02"]["payload"]["body"]["data"]))
        self.assertTrue(any(p.get("filename") for p in msgs["msg-03"]["payload"]["parts"]))
        self.assertEqual(sum(1 for m in msgs.values() if m["threadId"] == "thr-plan"), 3)
        self.assertTrue(any(h["value"].startswith("=?utf-8?b?") for h in msgs["msg-07"]["payload"]["headers"]
                            if h["name"] == "Subject"))
        self.assertEqual(len(inbox["history"]["added"]), 3)
        self.assertTrue(set(inbox["history"]["added"]) <= set(msgs))
        scen = json.loads((FIX / "scenarios.json").read_text(encoding="utf-8"))
        for name in ("default", "mismatch", "history_expired", "history_many", "rate_limit_then_ok",
                     "server_error", "unauthorized_client", "invalid_grant", "access_denied", "boom"):
            self.assertIn(name, scen)
        self.assertEqual(len(scen["history_many"]["history_added"]), 6)
        self.assertTrue(set(scen["history_many"]["history_added"]) <= set(msgs))
        rules = json.loads((FIX / "rules.sample.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rules["rules"]), 1)
        allow = (FIX / "allowlist.txt").read_text(encoding="utf-8")
        self.assertIn("told in writing", allow)
        self.assertIn("ana@example.test", allow)

    def test_gitignore_keys(self):  # R1-7 / AC-45 / AC-2
        ignored = ["fixtures/sa-key.json", "fixtures/other.json", "sa-key.json", "keys/sa.json", "key.pem",
                   "fixtures/key.pem", "cert.p12", "id.key", ".env", ".env.local", "out/x.jsonl"]
        kept = ["fixtures/inbox.json", "fixtures/scenarios.json", "fixtures/rules.sample.json",
                "fixtures/allowlist.txt", ".env.example", "pulse.py"]
        text = (HERE / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn("!fixtures/*", text)
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
            inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=HERE,
                                    capture_output=True, text=True).stdout.strip() == "true"
        except (OSError, subprocess.CalledProcessError):
            inside = False
        if not inside:
            self.skipTest("git not available; pattern check above only")
        for path in ignored + kept:
            r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=HERE)
            self.assertEqual(r.returncode == 0, path in ignored, path)

    def test_fixture_scan(self):  # AC-29 / FR-30
        texts = fixture_texts()
        emails = [e for t in texts for e in EMAIL_RE.findall(t)]
        self.assertGreater(len(emails), 10)
        for e in emails:
            self.assertTrue(e.endswith("@example.test"), e)
        phones = [p for t in texts for p in PHONE_RE.findall(t)]
        self.assertGreaterEqual(len(phones), 2)
        for p in phones:
            self.assertRegex(p, r"^\+91 00000 \d{5}$")
        for t in texts:
            self.assertIsNone(PROTO004.search(t))
        self.assertIsNone(PROTO004.search(json.dumps(FAKE_KEY)))


# ---------------------------------------------------------------- T6: client, mock, retry
import gmail_client  # noqa: E402
from gmail_client import MockClient, with_retry  # noqa: E402


class Recorder:
    def __init__(self):
        self.delays = []

    def __call__(self, s):
        self.delays.append(s)


class ClientTests(unittest.TestCase):
    def mock(self, scenario="default"):
        return MockClient("ana@example.test", FIX, scenario)

    def test_list_pages(self):
        c = self.mock()
        r = c.list_messages(None, None, 100)
        self.assertEqual(len(r["messages"]), 5)
        self.assertEqual(r["nextPageToken"], "5")
        r2 = c.list_messages(None, r["nextPageToken"], 2)
        self.assertEqual([m["id"] for m in r2["messages"]], ["msg-06", "msg-07"])
        last = c.list_messages(None, "10", 100)
        self.assertEqual(len(last["messages"]), 3)
        self.assertNotIn("nextPageToken", last)

    def test_metadata_strips_body(self):
        m = self.mock().get_message("msg-03", "metadata")
        self.assertNotIn("parts", m["payload"])
        self.assertNotIn("body", m["payload"])
        self.assertEqual({h["name"] for h in m["payload"]["headers"]}, {"From", "To", "Cc", "Subject"})
        full = self.mock().get_message("msg-03", "full")
        self.assertIn("parts", full["payload"])

    def test_retry_429_then_ok(self):  # AC-14 (unit)
        c, rec = self.mock("rate_limit_then_ok"), Recorder()
        r = with_retry(lambda: c.list_messages(None, None, 10), rec)
        self.assertEqual(len(r["messages"]), 5)
        self.assertEqual(c.call_names(), ["list_messages"] * 3)
        self.assertEqual(rec.delays, [1, 2])

    def test_retry_5xx_exhausted(self):  # AC-14 (unit)
        c, rec = self.mock("server_error"), Recorder()
        with self.assertRaises(PulseError) as cm:
            with_retry(c.get_profile, rec)
        self.assertEqual((cm.exception.code, cm.exception.exit_code), ("server_error", 5))
        self.assertEqual(len(c.calls), 5)
        self.assertEqual(rec.delays, [1, 2, 4, 8])

    def test_retry_429_always(self):
        c, rec = self.mock("rate_limit_always"), Recorder()
        with self.assertRaises(PulseError) as cm:
            with_retry(c.get_profile, rec)
        self.assertEqual(cm.exception.code, "rate_limited")

    def test_retry_cap(self):
        rec = Recorder()

        def always():
            raise TransientError(500)
        with self.assertRaises(PulseError):
            with_retry(always, rec, attempts=8)
        self.assertEqual(rec.delays, [1, 2, 4, 8, 16, 32, 32])

    def test_history(self):
        h = self.mock().list_history("1500", None, 100)
        ids = [r["messagesAdded"][0]["message"]["id"] for r in h["history"]]
        self.assertEqual(ids, ["msg-11", "msg-12", "msg-13"])
        with self.assertRaises(HistoryExpired):
            self.mock("history_expired").list_history("1500", None, 100)

    def test_auth_and_http_scenarios(self):
        for scen, code in (("unauthorized_client", "unauthorized_client"), ("invalid_grant", "invalid_grant"),
                           ("access_denied", "access_denied")):
            with self.assertRaises(PulseError) as cm:
                self.mock(scen).get_profile()
            self.assertEqual(cm.exception.code, code)
        with self.assertRaises(RuntimeError):
            self.mock("boom").get_profile()
        self.assertEqual(self.mock("mismatch").get_profile()["emailAddress"], "other@example.test")


# ---------------------------------------------------------------- T7: parser
import parse  # noqa: E402

TAG_RE = re.compile(r"<\s*/?\s*(p|h1|script|style|html|head|body|div|br)\b", re.I)


class ParseTests(unittest.TestCase):
    def full(self, mid):
        return parse.to_row(fixture_msg(mid), full=True)

    def test_full_html_body(self):  # AC-17
        body = self.full("msg-02")["body_text"]
        self.assertIsNone(TAG_RE.search(body))
        self.assertNotIn("alert", body)
        self.assertNotIn("color: red", body)
        self.assertIn("Tom & Jerry joined the team.", body)
        self.assertIn("Read more <here>.", body)  # &nbsp; and &lt;/&gt; decoded

    def test_attachment_keys(self):  # AC-18
        atts = self.full("msg-03")["attachments"]
        self.assertEqual(atts, [{"name": "agreement-signed.pdf", "mime": "application/pdf", "size": 20480}])
        for a in atts:
            self.assertEqual(set(a), {"name", "mime", "size"})

    def test_rfc2047_subject(self):  # AC-19
        row = self.full("msg-07")
        self.assertEqual(row["subject"], "नमस्ते टीम")
        self.assertEqual(row["from"], "प्रिया शर्मा <priya.sharma@example.test>")
        self.assertIn("आज की बैठक 4 बजे है।", row["body_text"])

    def test_metadata_row_shape(self):
        msg = MockClient("ana@example.test", FIX).get_message("msg-03", "metadata")
        row = parse.to_row(msg, full=False)
        self.assertNotIn("body_text", row)
        self.assertNotIn("body_truncated", row)
        self.assertEqual(row["attachments"], [])
        self.assertEqual(row["subject"], "Signed agreement")
        self.assertEqual(set(row), {"id", "thread_id", "from", "to", "cc", "date", "subject", "snippet", "labels",
                                    "attachments"})

    def test_missing_headers_and_addresses(self):
        row = self.full("msg-09")
        self.assertEqual(row["subject"], "")
        self.assertEqual(row["cc"], [])
        row = self.full("msg-04")
        self.assertEqual(row["cc"], ['"Shah, Kiran" <kiran.shah@example.test>', "dev.team@example.test"])
        self.assertEqual(row["to"], ["Ana Rao <ana@example.test>"])
        self.assertRegex(row["date"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_plain_preferred_and_truncation(self):
        self.assertEqual(self.full("msg-08")["body_text"], "Plain version of the offsite agenda.")
        self.assertFalse(self.full("msg-08")["body_truncated"])
        row = self.full("msg-10")
        self.assertEqual(len(row["body_text"]), parse.BODY_MAX)
        self.assertTrue(row["body_truncated"])


# ---------------------------------------------------------------- T8: CLI and check
import cli  # noqa: E402

MB = ["--mailbox", "ana@example.test"]
WHY = ["--reason", "automated test of the pulse reader"]
CHECK = ["check", *MB, *WHY]
READ_CMDS = [["check"], ["fetch"], ["find", "--rules", str(FIX / "rules.sample.json")]]


class CheckCliTests(BaseCase):
    def test_check_output_and_calls(self):  # AC-12
        code, out, err = self.run_cli(CHECK)
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertIn("MOCK MODE", lines[0])
        self.assertIn("Mailbox: ana@example.test", out)
        inbox = load_inbox()
        self.assertIn(f"Messages: {inbox['profile']['messagesTotal']}", out)
        self.assertIn(f"Threads: {inbox['profile']['threadsTotal']}", out)
        self.assertEqual(self.calls(), ["get_profile"])

    def test_live_missing_key_cli(self):  # AC-4
        live = self.env(mock=False, PULSE_DOMAIN="example.test", PULSE_ALLOWLIST=str(FIX / "allowlist.txt"))
        code, _out, err = self.run_cli(CHECK, env=live)
        self.assertEqual(code, 2)
        self.assertIn("PULSE_SA_KEY_PATH", err)
        self.assertFalse((self.state / "audit.jsonl").exists())
        self.assertEqual(self.clients, [])
        mock = self.env(PULSE_DOMAIN="realcompany.example", PULSE_ALLOWLIST="/nowhere")
        code, out, err = self.run_cli(CHECK, env=mock)
        self.assertEqual(code, 0, err)

    def test_wrong_domain_cli(self):  # AC-8
        for cmd in READ_CMDS:
            for m in ("x@other.test", "x@sub.example.test"):
                code, _o, err = self.run_cli([*cmd, "--mailbox", m, *WHY])
                self.assertEqual(code, 3)
                self.assertIn("domain", err)
                self.assertEqual(self.clients, [])
        self.assertEqual({r["result"] for r in self.audit_rows()}, {"wrong_domain"})

    def test_not_allowlisted_cli(self):  # AC-9 (mock)
        code, _o, err = self.run_cli(["check", "--mailbox", "bob@example.test", *WHY])
        self.assertEqual(code, 3)
        self.assertIn("allowlist", err)
        self.assertEqual(self.clients, [])

    def test_reason_validation(self):  # AC-10
        for cmd in (["check", *MB], ["fetch", *MB], ["find", *MB, "--rules", str(FIX / "rules.sample.json")]):
            for reason in ([], ["--reason", "short"], ["--reason", "x" * 501]):
                code, _o, err = self.run_cli(cmd + reason)
                self.assertEqual(code, 2, (cmd, reason))
                self.assertIn("Usage error", err)
        self.assertEqual(self.audit_rows(), [])

    def test_mailbox_mismatch_check(self):  # AC-11 (check)
        code, _o, err = self.run_cli(CHECK, scenario="mismatch")
        self.assertEqual(code, 3)
        self.assertIn("other@example.test", err)
        self.assertEqual(self.calls(), ["get_profile"])
        self.assertEqual(self.audit_rows()[-1]["result"], "mailbox_mismatch")

    def test_auth_scenarios(self):  # AC-13(a)
        for scen, exit_code, phrase in (("unauthorized_client", 4, "Domain-wide delegation"),
                                        ("invalid_grant", 4, "suspended"),
                                        ("access_denied", 4, "Enable the Gmail API")):
            code, _o, err = self.run_cli(CHECK, scenario=scen)
            self.assertEqual(code, exit_code, scen)
            self.assertIn(phrase, err)
            self.assertEqual(self.audit_rows()[-1]["result"], scen)

    def test_audit_rows_check(self):  # AC-27 (check part)
        self.run_cli(CHECK)
        self.run_cli(["check", "--mailbox", "bob@example.test", *WHY])
        self.run_cli(["check", *MB, "--reason", "short"])
        rows = self.audit_rows()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(list(r), list(audit.FIELDS))
            self.assertEqual(r["mode"], "mock")
            self.assertEqual(r["command"], "check")
        self.assertEqual([r["result"] for r in rows], ["ok", "not_allowlisted"])
        self.assertEqual(rows[0]["reason"], "automated test of the pulse reader")

    def test_audit_unavailable_cli(self):  # AC-28
        state_file = self.tmp / "statefile"
        state_file.write_text("x", encoding="utf-8")
        code, _o, err = self.run_cli(["fetch", *MB, *WHY], env=self.env(PULSE_STATE_DIR=str(state_file)))
        self.assertEqual(code, 3)
        self.assertIn("audit log", err)
        self.assertEqual(self.clients, [])

    def test_max_bounds(self):  # AC-33
        for n in ("0", "501", "x"):
            code, _o, err = self.run_cli(["fetch", *MB, *WHY, "--max", n])
            self.assertEqual(code, 2)
            self.assertIn("--max", err)
        for s in ("7", "0d", "3651d", "87601h", "1w"):
            self.assertEqual(self.run_cli(["fetch", *MB, *WHY, "--since", s])[0], 2, s)
        self.assertEqual(self.audit_rows(), [])

    def test_mailbox_format_cli(self):  # AC-35
        for m in ("../x@example.test", "a/b@example.test"):
            code, _o, err = self.run_cli(["check", "--mailbox", m, *WHY])
            self.assertEqual(code, 2)
            self.assertIn("--mailbox", err)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_internal_error(self):  # AC-36
        code, _o, err = self.run_cli(CHECK, scenario="boom")
        self.assertEqual(code, 1)
        self.assertIn("Unexpected error", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(self.audit_rows()[-1]["result"], "internal")
        code, _o, err = self.run_cli(CHECK, env=self.env(PULSE_DEBUG="1"), scenario="boom")
        self.assertEqual(code, 1)
        self.assertIn("Traceback", err)

    def test_concurrent_audit(self):  # AC-34 / NFR-6
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.home), "PULSE_MOCK": "1",
               "PULSE_OUT_DIR": str(self.out), "PULSE_STATE_DIR": str(self.state), "PULSE_RETENTION_DAYS": "30",
               "PULSE_MOCK_SCENARIO": "default", "PULSE_DEBUG": "0", "PULSE_SA_KEY_PATH": "/nonexistent",
               "PULSE_DOMAIN": "example.test", "PULSE_ALLOWLIST": "/nonexistent"}
        procs = [subprocess.Popen([sys.executable, str(HERE / "pulse.py"), *CHECK], env=env, cwd=str(self.tmp),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for p in procs:
            _o, e = p.communicate(timeout=30)
            self.assertEqual(p.returncode, 0, e.decode())
        lines = (self.state / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(json.loads(line)["result"], "ok")


# ---------------------------------------------------------------- T9: store and fetch
import store  # noqa: E402

FIXED_NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
TODAY = FIXED_NOW.date().isoformat()
FETCH = ["fetch", *MB, *WHY]


def fixture_subjects() -> list:
    return [parse.to_row(m, False)["subject"] for m in load_inbox()["messages"] if parse.to_row(m, False)["subject"]]


class FetchBase(BaseCase):
    """Helpers for fetch-style tests; holds no tests itself."""

    def mbdir(self):
        return self.out / "_mock" / "ana@example.test"

    def out_file(self, suffix=".jsonl"):
        return self.mbdir() / f"{TODAY}{suffix}"

    def rows(self, suffix=".jsonl"):
        return [json.loads(x) for x in self.out_file(suffix).read_text(encoding="utf-8").splitlines()]

    def fetch(self, *extra, scenario=None, env=None):
        return self.run_cli([*FETCH, *extra], scenario=scenario, env=env, now=lambda: FIXED_NOW)


class FetchTests(FetchBase):
    def test_pagination_stops_at_max(self):  # AC-15
        code, out, err = self.fetch("--max", "7")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.rows()), 7)
        self.assertEqual(self.calls().count("list_messages"), 2)
        self.assertEqual(self.calls().count("get_message"), 7)
        self.assertEqual(self.audit_rows()[-1]["count"], 7)

    def test_metadata_only(self):  # AC-16
        code, _o, err = self.fetch()
        self.assertEqual(code, 0, err)
        rows = self.rows()
        self.assertEqual(len(rows), 13)
        for r in rows:
            self.assertNotIn("body_text", r)
        fmts = [args["fmt"] for c in self.clients for name, args in c.calls if name == "get_message"]
        self.assertEqual(set(fmts), {"metadata"})

    def test_full_fetch(self):
        code, _o, err = self.fetch("--full", "--max", "3")
        self.assertEqual(code, 0, err)
        self.assertTrue(all("body_text" in r for r in self.rows()))

    def test_output_path_modes_dedupe(self):  # AC-20
        self.assertEqual(self.fetch("--max", "5")[0], 0)
        code, out, _e = self.fetch("--max", "7")
        self.assertEqual(code, 0)
        self.assertIn("wrote 2 new rows", out)
        self.assertEqual([p.name for p in self.mbdir().iterdir()], [f"{TODAY}.jsonl"])
        self.assertEqual(mode_of(self.out_file()), 0o600)
        self.assertEqual(mode_of(self.mbdir()), 0o700)
        self.assertEqual(mode_of(self.out / "_mock"), 0o700)
        ids = [r["id"] for r in self.rows()]
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7)

    def test_symlink_output_refused(self):  # AC-21 (output)
        target = self.tmp / "target.txt"
        target.write_text("keep\n", encoding="utf-8")
        self.mbdir().mkdir(parents=True)
        self.out_file().symlink_to(target)
        code, _o, err = self.fetch()
        self.assertEqual(code, 3)
        self.assertIn("symlink", err)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")
        self.assertEqual(self.audit_rows()[-1]["result"], "unsafe_path")
        self.assertNotIn("get_message", self.calls())

    def test_symlink_mailbox_dir_refused(self):  # AC-21 (mailbox dir)
        real = self.tmp / "elsewhere"
        real.mkdir()
        (self.out / "_mock").mkdir()
        self.mbdir().symlink_to(real)
        code, _o, _e = self.fetch()
        self.assertEqual(code, 3)
        self.assertEqual(list(real.iterdir()), [])

    def test_mailbox_mismatch_fetch(self):  # AC-11 (fetch)
        code, _o, _e = self.fetch(scenario="mismatch")
        self.assertEqual(code, 3)
        self.assertNotIn("list_messages", self.calls())
        self.assertFalse(self.mbdir().exists())

    def test_retry_via_cli(self):  # AC-14 (CLI)
        code, _o, err = self.fetch("--max", "3", scenario="rate_limit_then_ok")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls().count("list_messages"), 3)
        self.assertEqual(self.sleeps.delays, [1, 2])
        code, _o, err = self.fetch(scenario="server_error")
        self.assertEqual(code, 5)
        self.assertEqual(self.sleeps.delays, [1, 2, 4, 8])
        self.assertEqual(self.audit_rows()[-1]["result"], "server_error")

    def test_query_and_stdout_has_no_mail(self):
        code, out, err = self.fetch("--query", "from:ops@example.test", "--since", "7d", "--full")
        self.assertEqual(code, 0, err)
        q = "(from:ops@example.test) newer_than:7d"
        self.assertEqual(self.audit_rows()[-1]["query"], q)
        self.assertEqual({a["query"] for c in self.clients for n, a in c.calls if n == "list_messages"}, {q})
        for s in fixture_subjects():
            self.assertNotIn(s, out + err)
        self.assertNotIn("Tom & Jerry", out + err)


# ---------------------------------------------------------------- T10: history and --since-last
class HistoryTests(FetchBase):
    def save_position(self, hid="1500"):
        p = self.state / "history.mock.json"
        p.write_text(json.dumps({"ana@example.test": {"history_id": hid, "updated": "2026-11-18T00:00:00+00:00"}}),
                     encoding="utf-8")
        os.chmod(p, 0o600)
        return p

    def test_since_last_uses_history(self):  # AC-22 (saved)
        self.save_position()
        code, out, err = self.fetch("--since-last")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["id"] for r in self.rows()], ["msg-11", "msg-12", "msg-13"])
        self.assertIn("list_history", self.calls())
        self.assertNotIn("list_messages", self.calls())
        self.assertNotIn("full list", out)

    def test_since_last_expired(self):  # AC-22 (404)
        self.save_position()
        code, out, err = self.fetch("--since-last", scenario="history_expired")
        self.assertEqual(code, 0, err)
        self.assertIn("Saved position expired, did a full list", out)
        self.assertIn("list_messages", self.calls())
        self.assertEqual(len(self.rows()), 13)

    def test_since_last_no_state(self):  # AC-22 (none saved)
        code, out, err = self.fetch("--since-last")
        self.assertEqual(code, 0, err)
        self.assertIn("No saved position, did a full list", out)
        self.assertNotIn("list_history", self.calls())

    def test_history_saved_mock_file(self):  # AC-23
        self.assertEqual(self.fetch("--since-last")[0], 0)
        p = self.state / "history.mock.json"
        self.assertEqual(mode_of(p), 0o600)
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data["ana@example.test"]["history_id"], load_inbox()["profile"]["historyId"])
        self.assertFalse((self.state / "history.json").exists())
        self.assertEqual([x.name for x in self.state.iterdir() if x.name.endswith(".tmp")], [])

    def test_since_last_truncated_keeps_position(self):  # AC-37
        p = self.save_position()
        before = p.read_bytes()
        code, out, err = self.fetch("--since-last", "--max", "2", scenario="history_many")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["id"] for r in self.rows()], ["msg-01", "msg-02"])
        self.assertIn("Stopped at --max, position not saved", out)
        self.assertEqual(p.read_bytes(), before)
        self.assertNotIn("To start tracking", out)  # history path truncated: no bootstrap hint

    def test_since_last_bootstrap_hint(self):  # R1-9 / AC-48
        code, out, err = self.fetch("--since-last", "--max", "5")
        self.assertEqual(code, 0, err)
        self.assertIn("Stopped at --max, position not saved", out)
        self.assertIn("run once with --since-last --since 1d", out)
        self.assertFalse((self.state / "history.mock.json").exists())
        code, out, err = self.fetch("--since-last", "--since", "1d")  # the documented way to start
        self.assertEqual(code, 0, err)
        self.assertTrue((self.state / "history.mock.json").exists())
        code, out, err = self.fetch("--since-last", "--max", "5")
        self.assertIn("list_history", self.calls())
        self.assertNotIn("To start tracking", out)

    def test_plain_fetch_never_moves_position(self):  # R1-1 / AC-39
        for extra in ([], ["--query", "from:nobody"], ["--since", "1d"], ["--query", "x", "--max", "500"]):
            code, out, err = self.fetch(*extra)
            self.assertEqual(code, 0, (extra, err))
            self.assertFalse((self.state / "history.mock.json").exists(), extra)
        p = self.save_position("1500")
        before = p.read_bytes()
        self.assertEqual(self.fetch("--query", "from:nobody")[0], 0)
        self.assertEqual(p.read_bytes(), before)

    def test_filtered_fallback_saves_with_note(self):  # R1-1 / AC-39
        code, out, err = self.fetch("--since-last", "--query", "from:ops@example.test")
        self.assertEqual(code, 0, err)
        self.assertIn("No saved position, did a full list", out)
        self.assertIn("did not match --query/--since was not read", out)
        data = json.loads((self.state / "history.mock.json").read_text(encoding="utf-8"))
        self.assertEqual(data["ana@example.test"]["history_id"], load_inbox()["profile"]["historyId"])
        self.save_position()
        code, out, err = self.fetch("--since-last", "--since", "1d", scenario="history_expired")
        self.assertEqual(code, 0, err)
        self.assertIn("Saved position expired", out)
        self.assertIn("was not read", out)
        code, out, _e = self.fetch("--since-last", scenario="history_expired")  # unfiltered fallback: no note
        self.assertIn("Saved position expired", out)
        self.assertNotIn("was not read", out)

    def test_audit_query_is_what_was_used(self):  # R1-10 / AC-47
        self.save_position()
        code, out, err = self.fetch("--since-last", "--query", "from:ops@example.test", "--since", "7d")
        self.assertEqual(code, 0, err)
        self.assertIn("--query/--since were not applied", out)
        self.assertIsNone(self.audit_rows()[-1]["query"])
        self.assertNotIn("list_messages", self.calls())
        self.save_position()
        code, out, err = self.fetch("--since-last", "--query", "in:inbox", scenario="history_expired")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.audit_rows()[-1]["query"], "in:inbox")  # fallback list did use it
        (self.state / "history.mock.json").unlink()
        self.assertEqual(self.fetch("--since-last", "--query", "in:inbox")[0], 0)
        self.assertEqual(self.audit_rows()[-1]["query"], "in:inbox")
        self.save_position()
        code, out, _e = self.fetch("--since-last")
        self.assertNotIn("not applied", out)

    def test_since_last_skips_deleted(self):  # R1-2 / AC-40 (mock)
        self.save_position()
        code, out, err = self.fetch("--since-last", scenario="history_deleted")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["id"] for r in self.rows()], ["msg-11", "msg-12"])
        self.assertIn("Skipped 2 deleted messages", out)
        self.assertNotIn("gone-01", out + err)
        row = self.audit_rows()[-1]
        self.assertEqual((row["result"], row["count"], row["skipped"]), ("ok", 2, 2))
        data = json.loads((self.state / "history.mock.json").read_text(encoding="utf-8"))
        self.assertEqual(data["ana@example.test"]["history_id"], load_inbox()["profile"]["historyId"])
        self.assertEqual(self.fetch("--max", "1")[0], 0)
        self.assertEqual(self.audit_rows()[-1]["skipped"], 0)
        self.assertNotIn("Skipped", self.fetch("--max", "1")[1])

    def test_paging_helper(self):  # R1-13: one loop for messages.list and history.list
        class R:
            def call(self, fn):
                return fn()

        class C:
            def __init__(self):
                self.calls = []

            def list_history(self, start, token, n):
                self.calls.append((token, n))
                pages = {None: ({"history": [{"messagesAdded": [{"message": {"id": "a"}}, {"message": {"id": "b"}}]}],
                                 "nextPageToken": "p2"}),
                         "p2": {"history": [{"messagesAdded": [{"message": {"id": "b"}}, {"message": {"id": "c"}}]}]}}
                return pages[token]

            def list_messages(self, q, token, n):
                self.calls.append((token, n))
                return {"messages": [{"id": "x"}, {"id": "y"}, {"id": "z"}], "nextPageToken": "more"}
        c = C()
        self.assertEqual(cli.history_ids(R(), c, "1", 10), (["a", "b", "c"], False))  # b deduped across pages
        self.assertEqual(c.calls, [(None, 10), ("p2", 8)])
        c = C()
        self.assertEqual(cli.history_ids(R(), c, "1", 2), (["a", "b"], True))
        self.assertEqual(cli.list_ids(R(), C(), None, 2), (["x", "y"], True))

    def test_symlink_history_refused(self):  # AC-21 (state)
        target = self.tmp / "target.json"
        target.write_text("{}", encoding="utf-8")
        (self.state / "history.mock.json").symlink_to(target)
        code, _o, err = self.fetch()
        self.assertEqual(code, 3)
        self.assertEqual(target.read_text(encoding="utf-8"), "{}")
        self.assertNotIn("get_message", self.calls())
        self.assertEqual(self.audit_rows()[-1]["result"], "unsafe_path")


# ---------------------------------------------------------------- T11: purge
def day(n: int) -> str:
    return (FIXED_NOW.date() - timedelta(days=n)).isoformat()


class PurgeTests(FetchBase):
    def seed(self):
        d = self.mbdir()
        d.mkdir(parents=True)
        files = {}
        for name in (f"{day(0)}.jsonl", f"{day(30)}.jsonl", f"{day(31)}.jsonl", f"{day(31)}.find.jsonl",
                     f"notes-{day(400)}.jsonl", f"{day(400)}.txt"):
            (d / name).write_text("{}\n", encoding="utf-8")
            files[name] = d / name
        live = self.out / "bob@example.test"  # a live-mode mailbox dir, old file only
        live.mkdir()
        (live / f"{day(90)}.jsonl").write_text("{}\n", encoding="utf-8")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / f"{day(400)}.jsonl").write_text("keep\n", encoding="utf-8")
        (self.out / "linked").symlink_to(outside, target_is_directory=True)
        (d / f"{day(500)}.jsonl").symlink_to(outside / f"{day(400)}.jsonl")
        (self.state / "audit.jsonl").write_text('{"seed": 1}\n', encoding="utf-8")
        (self.state / "history.mock.json").write_text('{"seed": 1}\n', encoding="utf-8")
        return files, live, outside

    def purge(self, *extra, env=None):
        return self.run_cli(["purge", *extra], env=env, now=lambda: FIXED_NOW)

    def test_purge_boundaries(self):  # AC-25
        files, live, outside = self.seed()
        hist = (self.state / "history.mock.json").read_bytes()
        code, out, err = self.purge("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("Would delete 3 files", out)
        self.assertTrue(all(p.exists() for p in files.values()))
        self.assertEqual(self.audit_rows()[-1]["count"], 0)
        code, out, err = self.purge()
        self.assertEqual(code, 0, err)
        self.assertIn("Deleted 3 files", out)
        gone = {f"{day(31)}.jsonl", f"{day(31)}.find.jsonl"}
        for name, p in files.items():
            self.assertEqual(p.exists(), name not in gone, name)
        self.assertFalse(live.exists())  # emptied mailbox dir removed
        self.assertEqual((outside / f"{day(400)}.jsonl").read_text(encoding="utf-8"), "keep\n")
        self.assertTrue((self.mbdir() / f"{day(500)}.jsonl").is_symlink())
        self.assertEqual((self.state / "history.mock.json").read_bytes(), hist)
        self.assertTrue((self.state / "audit.jsonl").read_text(encoding="utf-8").startswith('{"seed": 1}\n'))
        row = self.audit_rows()[-1]
        self.assertEqual((row["command"], row["mailbox"], row["reason"], row["count"], row["result"]),
                         ("purge", None, None, 3, "ok"))

    def test_purge_only_own_layout(self):  # R1-8 / AC-46
        old = f"{day(400)}.jsonl"
        strays = [self.out / old,                                   # top of OUT_DIR
                  self.out / "_mock" / old,                         # top of _mock
                  self.out / "notes" / old,                         # folder not named like a mailbox
                  self.out / "projects" / "sub" / old,              # deeper tree
                  self.mbdir() / "sub" / old,                       # below a mailbox dir
                  self.out / "bob@example.test" / "x" / old]
        for p in strays:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("keep\n", encoding="utf-8")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / old).write_text("keep\n", encoding="utf-8")
        (self.out / "_mock" / "link@example.test").symlink_to(outside, target_is_directory=True)
        own = self.out / "carl@example.test" / old
        own.parent.mkdir()
        own.write_text("{}\n", encoding="utf-8")
        code, out, err = self.purge()
        self.assertEqual(code, 0, err)
        self.assertIn("Deleted 1 files", out)
        self.assertFalse(own.exists())
        self.assertFalse(own.parent.exists())
        for p in strays + [outside / old]:
            self.assertTrue(p.exists(), p)
        self.assertTrue((self.out / "_mock").is_dir())

    def test_purge_through_symlinked_out_dir(self):  # R2-1: fetch and purge agree on a symlinked OUT_DIR
        real = self.tmp / "real-out"
        real.mkdir()
        link = self.tmp / "out-link"
        link.symlink_to(real, target_is_directory=True)
        env = self.env(PULSE_OUT_DIR=str(link))
        code, _o, err = self.run_cli(FETCH, env=env)
        self.assertEqual(code, 0, err)
        mb = real / "_mock" / "ana@example.test"
        self.assertTrue(mb.is_dir())
        old = mb / f"{day(400)}.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        code, out, err = self.purge(env=env)
        self.assertEqual(code, 0, err)
        self.assertFalse(old.exists())
        self.assertNotIn("Deleted 0 files", out)
        self.assertGreaterEqual(self.audit_rows()[-1]["count"], 1)
        self.assertTrue(link.is_symlink())  # the configured link itself is left alone
        # the home/root refusal applies to the resolved path
        home_link = self.tmp / "home-link"
        home_link.symlink_to(self.home, target_is_directory=True)
        code, _o, err = self.purge(env=self.env(PULSE_OUT_DIR=str(home_link)))
        self.assertEqual(code, 2)
        self.assertIn("PULSE_OUT_DIR", err)

    def test_out_dir_home_or_root_refused(self):  # R1-8 / AC-46
        for value in (str(self.home), "~", str(self.home) + "/", "/", str(self.home / "sub" / "..")):
            code, _o, err = self.purge(env=self.env(PULSE_OUT_DIR=value))
            self.assertEqual(code, 2, value)
            self.assertIn("PULSE_OUT_DIR", err)
        self.assertFalse((self.state / "audit.jsonl").exists())  # config error: no audit row
        code, _o, err = self.run_cli(FETCH, env=self.env(PULSE_OUT_DIR="/"))
        self.assertEqual(code, 2)
        self.assertEqual(self.purge(env=self.env(PULSE_OUT_DIR=str(self.home / "pulse-out")))[0], 0)

    def test_purge_live_without_key(self):  # purge needs no live keys
        code, _o, err = self.purge(env=self.env(mock=False))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.audit_rows()[-1]["mode"], "live")

    def test_fetch_auto_purge(self):  # AC-26
        self.mbdir().mkdir(parents=True)
        old = self.mbdir() / f"{day(31)}.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        code, out, err = self.fetch("--max", "1")
        self.assertEqual(code, 0, err)
        self.assertFalse(old.exists())
        self.assertEqual(self.audit_rows()[-1]["purged"], 1)
        self.assertEqual(self.fetch("--max", "1")[0], 0)
        self.assertEqual(self.audit_rows()[-1]["purged"], 0)


# ---------------------------------------------------------------- T12: rules and find
import rules  # noqa: E402


class FindTests(FetchBase):
    def write_rules(self, rule_list) -> str:
        p = self.tmp / "rules.json"
        p.write_text(json.dumps({"rules": rule_list}), encoding="utf-8")
        return str(p)

    def find(self, rules_path, *extra, scenario=None):
        return self.run_cli(["find", *MB, *WHY, "--rules", rules_path, *extra], scenario=scenario,
                            now=lambda: FIXED_NOW)

    def test_find_sample(self):  # AC-24 (match)
        code, out, err = self.find(str(FIX / "rules.sample.json"))
        self.assertEqual(code, 0, err)
        rows = self.rows(".find.jsonl")
        self.assertEqual([r["id"] for r in rows], ["msg-12"])
        self.assertEqual(rows[0]["rules_hit"], ["invoice-due"])
        self.assertEqual(rows[0]["fields_hit"], ["subject", "snippet"])
        self.assertIn("Rule invoice-due: 1 matches", out)
        self.assertEqual(mode_of(self.out_file(".find.jsonl")), 0o600)
        row = self.audit_rows()[-1]
        self.assertEqual((row["command"], row["count"], row["rules_file"], row["query"]),
                         ("find", 1, str(FIX / "rules.sample.json"), "subject:invoice"))
        self.assertFalse((self.state / "history.mock.json").exists())  # find never touches history
        self.assertEqual(self.find(str(FIX / "rules.sample.json"))[0], 0)  # rerun: deduped
        self.assertEqual(len(self.rows(".find.jsonl")), 1)

    def test_find_skips_deleted(self):  # R1-2 / AC-40 (find)
        def factory(cfg, mb):
            c = gmail_client.make_client(cfg, mb)
            real = c.get_message

            def get_message(msg_id, fmt):
                if msg_id == "msg-12":
                    c.calls.append(("get_message", {"msg_id": msg_id, "fmt": fmt}))
                    raise errors.MessageGone()
                return real(msg_id, fmt)
            c.get_message = get_message
            return c
        rules_path = self.write_rules([{"id": "all", "gmail_query": "in:inbox"},
                                       {"id": "again", "gmail_query": "label:x"}])
        code, out, err = self.run_cli(["find", *MB, *WHY, "--rules", rules_path], factory=factory,
                                      now=lambda: FIXED_NOW)
        self.assertEqual(code, 0, err)
        self.assertNotIn("msg-12", [r["id"] for r in self.rows(".find.jsonl")])
        self.assertEqual(len(self.rows(".find.jsonl")), 12)
        self.assertIn("Skipped 1 deleted messages", out)
        self.assertEqual(self.audit_rows()[-1]["skipped"], 1)

    def test_rules_invalid(self):  # AC-24 (validation)
        cases = {
            "bad regex": [{"id": "a", "regex": ["("]}],
            "unknown key": [{"id": "a", "keywords": ["x"], "colour": "red"}],
            "duplicate id": [{"id": "a", "keywords": ["x"]}, {"id": "a", "keywords": ["y"]}],
            "body without full": [{"id": "a", "keywords": ["x"], "fields": ["body_text"]}],
            "bad field": [{"id": "a", "keywords": ["x"], "fields": ["headers"]}],
            "bad id": [{"id": "Bad Id", "keywords": ["x"]}],
            "nothing to match": [{"id": "a", "description": "empty"}],
            "empty": [],
        }
        for label, rl in cases.items():
            code, _o, err = self.find(self.write_rules(rl))
            self.assertEqual(code, 2, label)
            self.assertIn("Rules file", err, label)
            self.assertEqual(self.clients, [], label)
            self.assertEqual(self.audit_rows()[-1]["result"], "rules_invalid")
        bad_json = self.tmp / "bad.json"
        bad_json.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.find(str(bad_json))[0], 2)
        self.assertEqual(self.find(str(self.tmp / "missing.json"))[0], 2)
        _c, _o, err = self.find(self.write_rules(cases["body without full"]))
        self.assertIn("needs --full", err)

    def test_find_attachment_and_body_fields(self):
        p = self.write_rules([{"id": "pdfs", "regex": [r"\.pdf$"], "fields": ["attachments.name"]},
                              {"id": "hindi", "keywords": ["आज की बैठक"], "fields": ["body_text"]}])
        code, out, err = self.find(p, "--full")
        self.assertEqual(code, 0, err)
        rows = {r["id"]: r for r in self.rows(".find.jsonl")}
        self.assertEqual(set(rows), {"msg-03", "msg-07"})
        self.assertEqual(rows["msg-03"]["fields_hit"], ["attachments.name"])
        self.assertEqual(rows["msg-07"]["rules_hit"], ["hindi"])
        self.assertEqual(self.calls().count("get_message"), 13)  # each message fetched once across rules

    def test_find_query_only_rule_matches_all(self):
        code, out, err = self.find(self.write_rules([{"id": "all", "gmail_query": "label:inbox"}]), "--max", "4")
        self.assertEqual(code, 0, err)
        rows = self.rows(".find.jsonl")
        self.assertEqual(len(rows), 4)
        self.assertEqual({tuple(r["fields_hit"]) for r in rows}, {()})

    def test_mailbox_mismatch_find(self):  # AC-11 (find)
        code, _o, _e = self.find(str(FIX / "rules.sample.json"), scenario="mismatch")
        self.assertEqual(code, 3)
        self.assertNotIn("list_messages", self.calls())
        self.assertFalse(self.mbdir().exists())

    def test_match_unit(self):
        rule = rules.load_rules(FIX / "rules.sample.json", full=False)[0]
        self.assertEqual(rules.match(rule, {"subject": "inv-1234 here", "snippet": ""}), ["subject"])
        self.assertEqual(rules.match(rule, {"subject": "nothing", "snippet": "DUE DATE soon"}), ["snippet"])
        self.assertEqual(rules.match(rule, {"subject": "nothing", "snippet": "none"}), [])


# ---------------------------------------------------------------- T13: LiveClient (stubbed, no Google libs)
import live_client  # noqa: E402


class _Req:
    def __init__(self, svc, name, kw):
        self.svc, self.name, self.kw = svc, name, kw

    def execute(self, num_retries=None):
        self.svc.log.append((self.name, self.kw, num_retries))
        r = self.svc.handler(self.name, self.kw)
        if isinstance(r, BaseException):
            raise r
        return r


class _Chain:
    def __init__(self, svc, path):
        self._svc, self._path = svc, path

    def __getattr__(self, name):
        def call(**kw):
            if name in ("getProfile", "list", "get"):
                return _Req(self._svc, ".".join(self._path[1:] + [name]), kw)
            return _Chain(self._svc, self._path + [name])
        return call


class FakeService(_Chain):
    """Stands in for googleapiclient's Gmail service: users().messages().get(...).execute()."""

    def __init__(self, handler=None):
        self.log = []
        self.handler = handler or (lambda name, kw: dict(load_inbox()["profile"]))
        super().__init__(self, [])


class RefreshError(Exception):  # same class name as google.auth.exceptions.RefreshError
    pass


class HttpError(Exception):  # same class name as googleapiclient.errors.HttpError
    def __init__(self, status, reason="", details=None):
        super().__init__(f"HTTP {status}")
        self.resp = type("Resp", (), {"status": status})()
        self.reason = reason
        if details is not None:
            self.error_details = details


class LiveTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.allow = self.tmp / "allowlist.txt"
        self.allow.write_text("ana@example.test\n", encoding="utf-8")
        self.key = write_fake_key(self.tmp / "sa-key.json", 0o600)

    def live_env(self, **kw):
        e = self.env(mock=False, PULSE_DOMAIN="example.test", PULSE_ALLOWLIST=str(self.allow),
                     PULSE_SA_KEY_PATH=str(self.key))
        e.update(kw)
        return e

    def stub_factory(self, handler=None):
        self.built = {}

        def creds_builder(key_path, scopes, subject):
            self.built.update(key_path=key_path, scopes=scopes, subject=subject)
            return "fake-creds"

        def service_builder(creds):
            self.built["creds"] = creds
            self.svc = FakeService(handler)
            return self.svc
        return lambda cfg, mb: live_client.LiveClient(mb, cfg.sa_key_path, creds_builder, service_builder)

    def test_live_deps_missing(self):  # AC-6
        code, _o, err = self.run_cli(CHECK, env=self.live_env())
        self.assertEqual(code, 2, err)
        self.assertIn("pip install -r", err)
        self.assertEqual(self.audit_rows()[-1]["result"], "deps_missing")
        self.assertEqual(self.audit_rows()[-1]["mode"], "live")

    def test_live_scope_and_subject(self):  # AC-7
        code, out, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory())
        self.assertEqual(code, 0, err)
        self.assertNotIn("MOCK MODE", out)
        self.assertIn("Mode: live", out)
        self.assertEqual(self.built["scopes"], ["https://www.googleapis.com/auth/gmail.readonly"])
        self.assertEqual(live_client.SCOPES, ["https://www.googleapis.com/auth/gmail.readonly"])
        self.assertEqual(self.built["subject"], "ana@example.test")
        self.assertEqual(Path(self.built["key_path"]), self.key)
        self.assertEqual(self.svc.log, [("getProfile", {"userId": "me"}, 0)])

    def test_key_perms_warning_cli(self):  # AC-32
        os.chmod(self.key, 0o644)
        code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory())
        self.assertEqual(code, 0, err)
        self.assertIn("readable by group or others", err)

    def test_allowlist_live_missing_refused_before_key(self):  # AC-9 (live)
        env = self.live_env(PULSE_ALLOWLIST=str(self.tmp / "nope.txt"), PULSE_SA_KEY_PATH=str(self.tmp / "nokey"))
        code, _o, err = self.run_cli(CHECK, env=env, factory=self.stub_factory())
        self.assertEqual(code, 3)
        self.assertIn("allowlist", err)
        self.assertEqual(self.clients, [])
        self.allow.write_text("# c\n\n Ana@Example.test \n", encoding="utf-8")
        self.assertEqual(self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory())[0], 0)
        code, _o, _e = self.run_cli(["check", "--mailbox", "bob@example.test", *WHY], env=self.live_env(),
                                    factory=self.stub_factory())
        self.assertEqual(code, 3)

    def test_key_file_errors_cli(self):  # AC-13(b)
        code, _o, err = self.run_cli(CHECK, env=self.live_env(PULSE_SA_KEY_PATH=str(self.tmp / "nokey.json")))
        self.assertEqual(code, 4)
        self.assertIn("PULSE_SA_KEY_PATH", err)
        self.assertEqual(self.audit_rows()[-1]["result"], "key_missing")
        bad = self.tmp / "bad.json"
        bad.write_text("SENTINEL-KEY-TEXT not json", encoding="utf-8")
        code, out, err = self.run_cli(CHECK, env=self.live_env(PULSE_SA_KEY_PATH=str(bad)))
        self.assertEqual(code, 4)
        self.assertNotIn("SENTINEL", out + err + (self.state / "audit.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(self.audit_rows()[-1]["result"], "key_unreadable")

    def test_live_error_translation(self):  # AC-13(c) through LiveClient
        cases = [(RefreshError("invalid_grant: Invalid email or User ID"), 4, "invalid_grant"),
                 (RefreshError("unauthorized_client: Client is unauthorized"), 4, "unauthorized_client"),
                 (HttpError(403, "accessNotConfigured"), 4, "access_denied"),
                 (HttpError(429, "rateLimitExceeded"), 5, "rate_limited"),
                 (HttpError(403, "userRateLimitExceeded"), 5, "rate_limited"),
                 (HttpError(503, "backendError"), 5, "server_error")]
        for exc, exit_code, result in cases:
            code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(lambda n, k, e=exc: e))
            self.assertEqual((code, self.audit_rows()[-1]["result"]), (exit_code, result), result)
        self.assertEqual(len(self.svc.log), 5)  # 503 retried 5 times
        code, _o, _e = self.run_cli(CHECK, env=self.live_env(),
                                    factory=self.stub_factory(lambda n, k: HttpError(403, "rateLimitExceeded")))
        self.assertEqual((code, len(self.svc.log), self.sleeps.delays), (5, 5, [1, 2, 4, 8]))  # R1-4: retried

    def test_live_403_reason_in_any_detail(self):  # R2-2: every error_details entry, any case
        rate = [HttpError(403, "forbidden", [{"reason": "other"}, {"reason": "RATE_LIMIT_EXCEEDED"}]),
                HttpError(403, "", [{"reason": "userRateLimitExceeded"}]),
                HttpError(403, "rateLimitExceeded", [{"reason": "somethingElse"}]),
                HttpError(403, "", ["not a dict", {"reason": "rateLimitExceeded"}])]
        for exc in rate:
            code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(lambda n, k, e=exc: e))
            self.assertEqual((code, self.audit_rows()[-1]["result"], len(self.svc.log)), (5, "rate_limited", 5), err)
        denied = [HttpError(403, "", [{"reason": "accessNotConfigured"}, {"reason": "SERVICE_DISABLED"}]),
                  HttpError(403, "", []), HttpError(403, "", None), HttpError(403, "", [{"reason": None}])]
        for exc in denied:  # unrecognised: still fails closed, tried once
            code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(lambda n, k, e=exc: e))
            self.assertEqual((code, self.audit_rows()[-1]["result"], len(self.svc.log)), (4, "access_denied", 1), err)
        code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(
            lambda n, k: HttpError(403, "", [{"reason": "accessNotConfigured"}])))
        self.assertIn("accessNotConfigured", err)  # first entry still named in the message

    def test_live_requests(self):
        profile = load_inbox()["profile"]
        msgs = {m["id"]: m for m in load_inbox()["messages"]}

        def handler(name, kw):
            if name == "getProfile":
                return dict(profile)
            if name == "messages.list":
                return {"messages": [{"id": "msg-01", "threadId": "thr-01"}]}
            if name == "messages.get":
                return msgs[kw["id"]]
            if name == "history.list":
                return HttpError(404, "notFound")
        self.save = self.state / "history.json"
        self.save.write_text(json.dumps({"ana@example.test": {"history_id": "1", "updated": "x"}}), encoding="utf-8")
        code, out, err = self.run_cli([*FETCH, "--since-last", "--query", "in:inbox"], env=self.live_env(),
                                      factory=self.stub_factory(handler), now=lambda: FIXED_NOW)
        self.assertEqual(code, 0, err)
        self.assertIn("Saved position expired", out)
        names = [n for n, _k, _r in self.svc.log]
        self.assertEqual(names, ["getProfile", "history.list", "messages.list", "messages.get"])
        get_kw = self.svc.log[-1][1]
        self.assertEqual((get_kw["format"], get_kw["metadataHeaders"]), ("metadata", ["From", "To", "Cc", "Subject"]))
        self.assertEqual(self.svc.log[1][1]["historyTypes"], ["messageAdded"])
        self.assertEqual(self.svc.log[2][1]["q"], "in:inbox")
        self.assertEqual({r for _n, _k, r in self.svc.log}, {0})
        self.assertTrue((self.out / "ana@example.test" / f"{TODAY}.jsonl").exists())  # live: no _mock
        self.assertEqual(json.loads(self.save.read_text(encoding="utf-8"))["ana@example.test"]["history_id"],
                         profile["historyId"])
        self.assertFalse((self.state / "history.mock.json").exists())

    def test_live_bad_pem_is_key_unreadable(self):  # R1-6 / AC-44
        def creds_builder(key_path, scopes, subject):
            raise ValueError("Could not deserialize key data SENTINEL-PEM-TEXT")
        def factory(cfg, mb):
            return live_client.LiveClient(mb, cfg.sa_key_path, creds_builder, lambda c: FakeService())
        code, out, err = self.run_cli(CHECK, env=self.live_env(), factory=factory)
        self.assertEqual((code, self.audit_rows()[-1]["result"]), (4, "key_unreadable"))
        self.assertIn(str(self.key), err)
        self.assertNotIn("SENTINEL", out + err + (self.state / "audit.jsonl").read_text(encoding="utf-8"))

    def test_live_refresh_errors(self):  # R1-5 / AC-43
        class RetryableRefresh(RefreshError):
            retryable = True
        code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(
            lambda n, k: RetryableRefresh("temporarily_unavailable")))
        self.assertEqual((code, self.audit_rows()[-1]["result"]), (5, "server_error"))
        self.assertIn("token service", err)
        self.assertEqual((len(self.svc.log), self.sleeps.delays), (5, [1, 2, 4, 8]))
        profile = load_inbox()["profile"]
        fails = [RetryableRefresh("x")]
        code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(
            lambda n, k: fails.pop(0) if fails else dict(profile)))
        self.assertEqual(code, 0, err)
        code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(
            lambda n, k: RefreshError("SENTINEL-REFRESH some new error")))
        self.assertEqual((code, self.audit_rows()[-1]["result"]), (4, "token_error"))
        self.assertNotIn("SENTINEL", err)
        self.assertEqual(len(self.svc.log), 1)  # not retryable: one attempt

    def test_live_network_errors(self):  # R1-3 / AC-41
        class TransportError(Exception):  # name of google.auth.exceptions.TransportError
            pass

        class HttpLib2Error(Exception):  # name of httplib2.HttpLib2Error
            pass

        class ServerNotFoundError(HttpLib2Error):
            pass
        for exc in (TransportError("token endpoint unreachable"), ServerNotFoundError("dns"),
                    socket.timeout("timed out"), ConnectionResetError("reset"), OSError("net down")):
            code, out, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(lambda n, k, e=exc: e))
            self.assertEqual((code, self.audit_rows()[-1]["result"]), (5, "network_error"), type(exc).__name__)
            self.assertIn("Could not reach Google", err)
            self.assertNotIn("Unexpected error", err)
            self.assertEqual(len(self.svc.log), 5)
            self.assertEqual(self.sleeps.delays, [1, 2, 4, 8])
        profile = load_inbox()["profile"]
        fails = [ConnectionResetError("reset"), TransportError("x")]
        code, _o, err = self.run_cli(CHECK, env=self.live_env(), factory=self.stub_factory(
            lambda n, k: fails.pop(0) if fails else dict(profile)))
        self.assertEqual(code, 0, err)  # retried, then succeeded
        self.assertEqual(self.sleeps.delays, [1, 2])

    def test_live_get_404_skipped(self):  # R1-2 / AC-40 (live stub)
        profile = load_inbox()["profile"]
        msgs = {m["id"]: m for m in load_inbox()["messages"]}

        def handler(name, kw):
            if name == "getProfile":
                return dict(profile)
            if name == "history.list":
                return {"history": [{"id": "1", "messagesAdded": [{"message": {"id": "gone"}}]},
                                    {"id": "2", "messagesAdded": [{"message": {"id": "msg-01"}}]}]}
            if name == "messages.get":
                return msgs[kw["id"]] if kw["id"] in msgs else HttpError(404, "notFound")
        hist = self.state / "history.json"
        hist.write_text(json.dumps({"ana@example.test": {"history_id": "100", "updated": "x"}}), encoding="utf-8")
        code, out, err = self.run_cli([*FETCH, "--since-last"], env=self.live_env(),
                                      factory=self.stub_factory(handler), now=lambda: FIXED_NOW)
        self.assertEqual(code, 0, err)
        self.assertIn("Skipped 1 deleted messages", out)
        rows = (self.out / "ana@example.test" / f"{TODAY}.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(r)["id"] for r in rows], ["msg-01"])
        self.assertEqual(json.loads(hist.read_text(encoding="utf-8"))["ana@example.test"]["history_id"],
                         profile["historyId"])
        self.assertEqual(self.audit_rows()[-1]["skipped"], 1)
        get_calls = [n for n, _k, _r in self.svc.log if n == "messages.get"]
        self.assertEqual(len(get_calls), 2)  # a 404 on get is not retried
        for failing in ("getProfile", "messages.list"):  # 404 elsewhere stays internal
            def h(name, kw, f=failing):
                return HttpError(404, "notFound") if name == f else (dict(profile) if name == "getProfile"
                                                                   else {"messages": []})
            code, _o, err = self.run_cli(FETCH, env=self.live_env(), factory=self.stub_factory(h))
            self.assertEqual((code, self.audit_rows()[-1]["result"]), (1, "internal"), failing)

    def test_requirements_pinned_set(self):  # NFR-7
        names = [line.strip() for line in (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.startswith("#")]
        self.assertEqual(sorted(re.split(r"[<>=!~ ]", n)[0] for n in names),
                         ["google-api-python-client", "google-auth"])
        for n in names:  # R1-11 / AC-49: a 2.x floor and a cap below the next major
            self.assertRegex(n, r"^[a-z-]+>=2\.\d+\.\d+,<3$", n)


# ---------------------------------------------------------------- T14: README and CHARTER
class DocsTests(unittest.TestCase):
    def test_readme_contents(self):  # AC-31 / FR-32 / NFR-10
        text = (HERE / "README.md").read_text(encoding="utf-8")
        for item in ("GCP project", "Enable the Gmail API", "service account", "outside the repo", "chmod 600",
                     "Admin console", "Security > Access and data control > API controls > Domain-wide delegation",
                     "client ID", "https://www.googleapis.com/auth/gmail.readonly", "No other scope",
                     "told in writing", "Workspace admin approves every allowlist entry", "365 days", "30 days",
                     "## Install", "pip install -r requirements.txt", "## Mock run", "PULSE_MOCK=1", "## Live run",
                     "What changes when the key arrives", "POSIX"):
            self.assertIn(item, text)
        m = re.search(r"```mermaid\n(.*?)```", text, re.S)
        self.assertIsNotNone(m)
        flow = m.group(1)
        self.assertIn("flowchart", flow)
        for node in ("setup", "auth", "list", "get", "parse", "store", "find"):
            self.assertRegex(flow, rf"\b{node}\[")
        self.assertRegex(flow, r"setup\[.*-->\s*auth\[")

    def test_charter_contents(self):  # FR-1
        text = (HERE / "CHARTER.md").read_text(encoding="utf-8")
        for item in ("Kaivan Shah", "Workspace admin", "365 days", "30 days", "told in writing",
                     "gmail.readonly", "snippet", "Non-goals", "Q-6"):
            self.assertIn(item, text)


# ---------------------------------------------------------------- T15: whole-tool checks
class EndToEndTests(FetchBase):
    RUNS = [CHECK, FETCH, [*FETCH, "--full"], ["find", *MB, *WHY, "--rules", str(FIX / "rules.sample.json")],
            ["purge"], ["purge", "--dry-run"]]

    def test_mock_all_commands_offline(self):  # AC-5 / FR-5 / NFR-1
        for argv in self.RUNS:
            code, out, err = self.run_cli(argv, now=lambda: FIXED_NOW)
            self.assertEqual(code, 0, (argv, err))
            self.assertTrue(out.startswith("MOCK MODE"), argv)
        self.assertIsNone(sys.modules.get("google"))
        self.assertIsNone(sys.modules.get("googleapiclient"))
        with self.assertRaises(RuntimeError):
            socket.socket()

    def test_audit_rows_schema_and_no_mail(self):  # AC-27 / FR-27 / FR-33
        for argv in self.RUNS:
            self.run_cli(argv, now=lambda: FIXED_NOW)
        refusals = [["check", "--mailbox", "bob@example.test", *WHY], ["fetch", "--mailbox", "x@other.test", *WHY]]
        for argv in refusals:
            self.assertEqual(self.run_cli(argv)[0], 3)
        self.assertEqual(self.run_cli(["fetch", *MB])[0], 2)  # usage: no row
        rows = self.audit_rows()
        self.assertEqual(len(rows), len(self.RUNS) + len(refusals))
        for r in rows:
            self.assertEqual(list(r), list(audit.FIELDS))
        self.assertEqual([r["command"] for r in rows],
                         ["check", "fetch", "fetch", "find", "purge", "purge", "check", "fetch"])
        self.assertEqual([r["result"] for r in rows][-2:], ["not_allowlisted", "wrong_domain"])
        log = (self.state / "audit.jsonl").read_text(encoding="utf-8")
        secrets = []
        for m in load_inbox()["messages"]:
            row = parse.to_row(m, full=True)
            secrets += [row["from"], row["snippet"], row["body_text"].splitlines()[0]]
            secrets += [row["subject"]] if row["subject"] else []
            secrets += [a["name"] for a in row["attachments"]]
        self.assertGreater(len(secrets), 40)
        for s in secrets:
            self.assertNotIn(s, log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
