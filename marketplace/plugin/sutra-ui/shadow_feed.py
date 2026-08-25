"""The needs-you feed contract (PLAN-100 S41, stub).

Now (the module) renders this feed; Shadow is one producer among several.
This stub owns the CONTRACT: schema validation + dedupe + append. Rendering
lands in P4; nothing here draws UI.
"""
import json
import os

import shadow_ledger

REQUIRED = ("item_id", "producer", "kind", "title", "deep_link",
            "dedupe_key", "state")
OPTIONAL = ("mission_id", "thread_id", "severity", "why_now",
            "primary_action", "secondary_actions", "expires_at",
            "evidence_links")
STATES = ("new", "seen", "handled", "expired")


def _feed_path():
    d = os.path.join(os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_SHADOW_HOME", "~/.sutra-ui/shadow"))))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "feed.jsonl")


def validate(item):
    """Return a list of contract violations (empty = valid)."""
    problems = []
    if not isinstance(item, dict):
        return ["item must be an object"]
    for k in REQUIRED:
        if not item.get(k):
            problems.append("missing required field: %s" % k)
    if item.get("state") and item["state"] not in STATES:
        problems.append("unknown state %r" % (item["state"],))
    unknown = set(item) - set(REQUIRED) - set(OPTIONAL)
    if unknown:
        problems.append("unknown fields: %s" % ", ".join(sorted(unknown)))
    return problems


def emit(item):
    """Validate + dedupe + append. Returns (accepted, problems)."""
    problems = validate(item)
    if problems:
        return False, problems
    path = _feed_path()
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    if json.loads(line).get("dedupe_key") == item["dedupe_key"]:
                        return False, ["duplicate dedupe_key"]
                except ValueError:
                    continue
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(item) + "\n")
    return True, []
