"""Pulse command line: argument parsing, the guard pipeline, commands, output and exit codes.

Pipeline for check / fetch / find (spec "Commands"), stopping at the first failure:
  1 parse args (usage)  2 config (config_*)  3 audit open (audit_unavailable)  4 domain, allowlist
  5 rules (find)  6 key file (live)  7 Google imports (live)  8 profile must equal --mailbox  9 command work.
From step 3 on, exactly one audit row is written whatever happens (spec R-4).
"""
import argparse
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, TextIO

import audit
import config
import gmail_client
import parse
import policy
import rules
import store
from errors import HistoryExpired, MessageGone, PulseError

MAX_LIMIT = 500
SINCE_RE = re.compile(r"^(\d+)([dh])$")
SINCE_MAX = {"d": 3650, "h": 87600}


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def _arg(fn):
    def wrapped(raw):
        try:
            return fn(raw)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e))
    wrapped.__name__ = fn.__name__
    return wrapped


def _max(raw: str) -> int:
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if not 1 <= n <= MAX_LIMIT:
        raise ValueError(f"--max must be a whole number from 1 to {MAX_LIMIT}")
    return n


def _since(raw: str) -> str:
    m = SINCE_RE.match(raw or "")
    if not m or not 1 <= int(m.group(1)) <= SINCE_MAX[m.group(2)]:
        raise ValueError("--since must be Nd (1..3650) or Nh (1..87600), for example 7d or 12h")
    return f"{int(m.group(1))}{m.group(2)}"


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="pulse.py", description="Sutra Pulse: read-only Gmail reader for allowlisted mailboxes.")
    sub = p.add_subparsers(dest="command", required=True, metavar="{check,fetch,find,purge}")

    def common(sp):
        sp.add_argument("--mailbox", required=True, type=_arg(policy.normalise_mailbox),
                        help="Mailbox to open, name@domain (must be in the domain and the allowlist)")
        sp.add_argument("--reason", required=True, type=_arg(policy.check_reason),
                        help="Why this mailbox is read, 10 to 500 characters (written to the audit log)")

    common(sub.add_parser("check", help="Open the mailbox and print its profile"))
    f = sub.add_parser("fetch", help="Save mail rows for the mailbox")
    common(f)
    f.add_argument("--query", help="Gmail search query, passed as-is")
    f.add_argument("--since", type=_arg(_since), help="Only mail newer than Nd or Nh")
    f.add_argument("--max", type=_arg(_max), default=50, help="Stop after N messages (1..500, default 50)")
    f.add_argument("--full", action="store_true", help="Also save body text")
    f.add_argument("--since-last", action="store_true", help="Only mail added since the last saved position")
    fd = sub.add_parser("find", help="Save messages matching a rules file")
    common(fd)
    fd.add_argument("--rules", required=True, help="Rules JSON file")
    fd.add_argument("--since", type=_arg(_since), help="Only mail newer than Nd or Nh")
    fd.add_argument("--max", type=_arg(_max), default=50, help="Stop after N messages per rule (1..500, default 50)")
    fd.add_argument("--full", action="store_true", help="Also read body text (needed for body_text rules)")
    pg = sub.add_parser("purge", help="Delete mail output older than the retention period")
    pg.add_argument("--dry-run", action="store_true", help="List what would be deleted, delete nothing")
    return p


class Run:
    """State of one invocation: config, client factory, clock, streams and the audit row fields."""

    def __init__(self, args, cfg, client_factory, sleep, now, stdout, stderr):
        self.args, self.cfg = args, cfg
        self.client_factory, self.sleep, self.now = client_factory, sleep, now
        self.stdout, self.stderr = stdout, stderr
        self.row = {"mode": "mock" if cfg.mock else "live", "command": args.command,
                    "mailbox": getattr(args, "mailbox", None), "query": None, "rules_file": None,
                    "reason": getattr(args, "reason", None), "count": None, "purged": None, "skipped": None}

    def out(self, text: str) -> None:
        print(text, file=self.stdout)

    def err(self, text: str) -> None:
        print(text, file=self.stderr)

    def call(self, fn):
        return gmail_client.with_retry(fn, self.sleep)


def open_mailbox(run: Run, before_key=None):
    """Steps 4-8. Returns (client, profile). `before_key` runs after step 4 (rules check, auto purge)."""
    cfg, mailbox = run.cfg, run.args.mailbox
    policy.check_domain(mailbox, cfg.domain)
    policy.check_allowlist(mailbox, cfg.allowlist)
    if before_key:
        before_key()
    if not cfg.mock:
        for w in policy.check_key_file(cfg.sa_key_path):
            run.err(w)
    client = run.client_factory(cfg, mailbox)
    profile = run.call(client.get_profile)
    got = (profile.get("emailAddress") or "").strip().lower()
    if got != mailbox:
        raise PulseError("mailbox_mismatch",
                         f"Refused: asked for {mailbox} but Google opened {got or '(no address)'}. Nothing was read.")
    return client, profile


def cmd_check(run: Run) -> None:
    _client, profile = open_mailbox(run)
    run.out(f"Mailbox: {profile.get('emailAddress')}")
    run.out(f"Messages: {profile.get('messagesTotal')}")
    run.out(f"Threads: {profile.get('threadsTotal')}")
    run.out(f"Mode: {run.row['mode']}")
    run.row["count"] = 0


def effective_query(query, since):
    if query and since:
        return f"({query}) newer_than:{since}"
    if query:
        return query
    if since:
        return f"newer_than:{since}"
    return None


def list_ids(run: Run, client, query, limit: int):
    """Page through messages.list until `limit` ids or the end. Returns (ids, more_available)."""
    ids, token = [], None
    while True:
        remaining = limit - len(ids)
        resp = run.call(lambda: client.list_messages(query, token, min(remaining, 100)))
        got = [m["id"] for m in resp.get("messages") or []]
        ids.extend(got[:remaining])
        token = resp.get("nextPageToken")
        if len(ids) >= limit:
            return ids, bool(token) or len(got) > remaining
        if not token:
            return ids, False


def get_rows(run: Run, client, ids, full: bool) -> list:
    """Rows for ids. A message deleted since it was listed (404 on get) is skipped and counted in
    run.row["skipped"] (R1-2), so one deleted message cannot fail the run or block --since-last."""
    fmt = "full" if full else "metadata"
    rows = []
    for i in ids:
        try:
            msg = run.call(lambda i=i: client.get_message(i, fmt))
        except MessageGone:
            run.row["skipped"] = (run.row["skipped"] or 0) + 1
            continue
        rows.append(parse.to_row(msg, full))
    return rows


def report_skipped(run: Run) -> None:
    if run.row["skipped"]:
        run.out(f"Skipped {run.row['skipped']} deleted messages")


def output_path(run: Run, suffix: str) -> Path:
    d = store.mailbox_dir(run.cfg.out_dir, run.args.mailbox, run.cfg.mock)
    p = d / f"{run.now().astimezone(timezone.utc).date().isoformat()}{suffix}"
    store.check_file(p)
    return p


def history_ids(run: Run, client, start_id: str, limit: int):
    """Ids added since start_id, via history.list. Raises HistoryExpired on 404. Returns (ids, more_available)."""
    ids, token = [], None
    while True:
        remaining = limit - len(ids)
        resp = run.call(lambda: client.list_history(start_id, token, min(remaining, 100)))
        got = []
        for rec in resp.get("history") or []:
            for added in rec.get("messagesAdded") or []:
                mid = (added.get("message") or {}).get("id")
                if mid and mid not in ids and mid not in got:
                    got.append(mid)
        ids.extend(got[:remaining])
        token = resp.get("nextPageToken")
        if len(ids) >= limit:
            return ids, bool(token) or len(got) > remaining
        if not token:
            return ids, False


def auto_purge(run: Run) -> None:
    """Runs inside fetch and find after the mailbox policy checks, before the profile call (FR-26)."""
    gone = store.purge(run.cfg.out_dir, run.cfg.retention_days, run.now().astimezone(timezone.utc).date(), False)
    run.row["purged"] = len(gone)
    if gone:
        run.out(f"Purged {len(gone)} output files older than {run.cfg.retention_days} days")


def cmd_purge(run: Run) -> None:
    cfg, dry = run.cfg, run.args.dry_run
    files = store.purge(cfg.out_dir, cfg.retention_days, run.now().astimezone(timezone.utc).date(), dry)
    for p in files:
        run.out(f"{'Would delete' if dry else 'Deleted'}: {p}")
    run.out(f"{'Would delete' if dry else 'Deleted'} {len(files)} files older than {cfg.retention_days} days")
    run.row["count"] = 0 if dry else len(files)


def cmd_fetch(run: Run) -> None:
    a, cfg = run.args, run.cfg
    client, profile = open_mailbox(run, before_key=lambda: auto_purge(run))
    query = effective_query(a.query, a.since)
    run.row["query"] = query
    path = output_path(run, ".jsonl")
    store.check_file(store.history_path(cfg.state_dir, cfg.mock))
    filtered_fallback = False
    if a.since_last:
        saved = (store.load_history(cfg.state_dir, cfg.mock).get(a.mailbox) or {}).get("history_id")
        if not saved:
            ids, more = list_ids(run, client, query, a.max)
            run.out("No saved position, did a full list")
            filtered_fallback = bool(query)
        else:
            try:
                ids, more = history_ids(run, client, saved, a.max)
                run.row["query"] = None  # audit records what was used: no query on the history path (R1-10)
                if query:
                    run.out("Used the saved position; --query/--since were not applied")
            except HistoryExpired:
                run.row["query"] = query
                ids, more = list_ids(run, client, query, a.max)
                run.out("Saved position expired, did a full list")
                filtered_fallback = bool(query)
    else:
        ids, more = list_ids(run, client, query, a.max)
    run.row["skipped"] = 0
    rows = get_rows(run, client, ids, a.full)
    written = store.append_rows(path, rows)
    run.row["count"] = len(rows)
    run.out(f"Fetched {len(rows)} messages; wrote {written} new rows to {path}")
    report_skipped(run)
    if not a.since_last:
        return  # FR-23 (R-20): only --since-last runs move the saved position
    if more:
        run.out("Stopped at --max, position not saved")
        return
    store.save_history(cfg.state_dir, cfg.mock, a.mailbox, profile.get("historyId"), run.now())
    if filtered_fallback:
        run.out("Position saved. Mail before this point that did not match --query/--since was not read "
                "and later --since-last runs will not return it")


def cmd_find(run: Run) -> None:
    a = run.args
    run.row["rules_file"] = a.rules
    loaded = []

    def before_key():
        loaded.extend(rules.load_rules(Path(a.rules), a.full))  # step 5: all rules valid before any Google call
        auto_purge(run)

    client, _profile = open_mailbox(run, before_key=before_key)
    queries = [effective_query(r.gmail_query, a.since) for r in loaded]
    run.row["query"] = " | ".join(q for q in queries if q) or None
    path = output_path(run, ".find.jsonl")
    fmt_rows, merged, counts = {}, {}, {}
    run.row["skipped"] = 0
    for rule, query in zip(loaded, queries):
        ids, _more = list_ids(run, client, query, a.max)
        counts[rule.id] = 0
        for mid in ids:
            if mid not in fmt_rows:
                got = get_rows(run, client, [mid], a.full)
                fmt_rows[mid] = got[0] if got else None
            row = fmt_rows[mid]
            if row is None:  # deleted since listed; counted once in run.row["skipped"]
                continue
            hit = rules.match(rule, row)
            if rule.local and not hit:
                continue
            counts[rule.id] += 1
            m = merged.setdefault(mid, {**row, "rules_hit": [], "fields_hit": []})
            m["rules_hit"].append(rule.id)
            m["fields_hit"].extend(f for f in hit if f not in m["fields_hit"])
    written = store.append_rows(path, merged.values())
    run.row["count"] = len(merged)
    for rid, n in counts.items():
        run.out(f"Rule {rid}: {n} matches")
    run.out(f"Matched {len(merged)} messages; wrote {written} new rows to {path}")
    report_skipped(run)


COMMANDS = {"check": cmd_check, "fetch": cmd_fetch, "find": cmd_find, "purge": cmd_purge}


def main(argv: list, environ: Mapping[str, str] | None = None, env_file: Path | None = None,
         client_factory: Callable | None = None, sleep: Callable[[float], None] = time.sleep,
         now: Callable[[], datetime] | None = None, stdout: TextIO | None = None,
         stderr: TextIO | None = None) -> int:
    environ = os.environ if environ is None else environ
    env_file = config.ENV_FILE if env_file is None else env_file
    client_factory = client_factory or gmail_client.make_client
    now = now or (lambda: datetime.now(timezone.utc))
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    # 1. Arguments. No audit row.
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as e:
        print(f"Usage error: {e}. Run: python3 pulse.py {{check,fetch,find,purge}} --help", file=stderr)
        return 2
    except SystemExit as e:  # --help
        return e.code if isinstance(e.code, int) else 0

    # 2. Config. No audit row (the audit path may be unknown).
    try:
        cfg = config.load(environ, env_file, need_live_keys=args.command != "purge")
    except PulseError as e:
        print(e.message, file=stderr)
        return e.exit_code

    # 3. Audit log. Refusal here writes no row (the log is what failed).
    try:
        log = audit.AuditLog(cfg.state_dir)
    except PulseError as e:
        print(e.message, file=stderr)
        return e.exit_code

    run = Run(args, cfg, client_factory, sleep, now, stdout, stderr)
    result, code = "internal", 1
    try:
        if cfg.mock:
            run.out("MOCK MODE: fixture inbox, no Google calls")
        handler = COMMANDS.get(args.command)
        if handler is None:
            raise PulseError("internal", f"Unexpected error: command {args.command} is not built yet.")
        handler(run)
        result, code = "ok", 0
    except PulseError as e:
        result, code = e.code, e.exit_code
        run.err(e.message)
    except Exception:
        result, code = "internal", 1
        run.err("Unexpected error: Pulse stopped. Set PULSE_DEBUG=1 to see the stack trace.")
        if cfg.debug:
            traceback.print_exc(file=stderr)
    finally:
        try:
            log.write(audit.build_row(result=result, **run.row))
        except PulseError as e:
            run.err(e.message)
            if code == 0:
                code = e.exit_code
        finally:
            log.close()
    return code
