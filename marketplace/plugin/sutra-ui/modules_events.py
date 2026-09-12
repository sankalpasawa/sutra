"""modules_events.py -- the Apps event log (APPS-EVENTS.md, program step 57).

One JSON object per line in <home>/.events.jsonl, appended with a single
O_APPEND write so two writers never interleave. Every event carries an
idempotency key sha256(app_id|event|version|actor|ts) with ts FIXED at
creation (codex pre-consult P7): a retry re-sends the same key and the reader
de-duplicates. Reads tolerate corrupt lines (json_store's degrade posture) and
never raise. No event is ever emitted by a read of the folder.
"""
import datetime
import hashlib
import json
import os

EVENTS = ("app.created", "app.edited", "app.assigned", "app.archived", "app.exported", "app.imported",
          # 2026-09-12: an app built before the frameworks kit took the stamp and
          # got its record (migrate_kit on an unstamped app). Its own fact because
          # it writes more than a migration, which stays silent by design.
          "app.kit_adopted")
FILE = ".events.jsonl"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def path(home):
    return os.path.join(home, FILE)


def key_for(app_id, event, version, actor, ts):
    return hashlib.sha256("|".join([str(app_id), str(event), str(version), str(actor), str(ts)]).encode("utf-8")).hexdigest()


def append(home, event, app_id, kind=None, version=None, department_ref=None, actor="app", op_id=None, **extra):
    """Append one event; returns the row. Never raises on a full disk or a
    missing home -- an event is evidence, not a precondition of the write it
    describes (the folder stays the truth)."""
    if event not in EVENTS:
        raise ValueError("unknown event %r" % (event,))
    ts = _now()
    row = {"event": event, "app_id": app_id, "kind": kind, "version": version,
           "department_ref": department_ref, "actor": actor, "ts": ts, "op_id": op_id,
           "key": key_for(app_id, event, version, actor, ts)}
    row.update({k: v for k, v in extra.items() if v is not None})
    line = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        os.makedirs(home, exist_ok=True)
        fd = os.open(path(home), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass
    return row


def read(home, app_id=None, limit=None):
    """Rows, oldest first, de-duplicated by key; corrupt lines skipped and
    counted in the returned tuple's second slot."""
    rows, seen, corrupt = [], set(), 0
    try:
        with open(path(home), "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    corrupt += 1
                    continue
                if not isinstance(row, dict) or not row.get("key") or row["key"] in seen:
                    continue
                if app_id and row.get("app_id") != app_id:
                    continue
                seen.add(row["key"])
                rows.append(row)
    except OSError:
        pass
    if limit:
        rows = rows[-limit:]
    return rows, corrupt
