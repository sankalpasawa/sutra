"""import_traffic.py — the tool wrapper around foundation/traffic_import.

Five brand builders choose which pages to learn from by search traffic and refuse without it.
That is right, but a person with a perfectly good export should not be stuck behind a balance.
"""
import os

from ..foundation import traffic_import
from . import _shared as sh


def run(ctx, path=""):
    say = sh.reporter(ctx, "import_traffic")
    p = os.path.expanduser((path or "").strip())
    if not p:
        return {"summary": "No file was named.",
                "error": "Tell me where the traffic file is on this Mac and I will read it."}
    if not os.path.exists(p):
        return {"summary": "There is no file at that path.",
                "error": "I looked for %s and found nothing. Check the path and try again." % p}
    try:
        with open(p, encoding="utf-8-sig") as f:
            text = f.read()
    except Exception as e:  # noqa: BLE001
        return {"summary": "That file could not be read.", "error": str(e)[:200]}
    out = traffic_import.apply(text, source=os.path.basename(p), say=say)
    if not out.get("ok"):
        return {"summary": "Nothing was imported.", "error": out.get("error", "")}
    return {"summary": out["summary"] + ". The brand pack can be built now.",
            "rows": out["rows"], "matched": out["matched"]}
