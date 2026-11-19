"""find rules: load and validate a JSON rules file, and match a rule against a mail row.

No keyword or pattern is hard-coded here; everything comes from the rules file (spec "find").
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from errors import PulseError

RULE_KEYS = {"id", "description", "gmail_query", "keywords", "regex", "fields"}
FIELDS = ("from", "to", "cc", "subject", "snippet", "attachments.name", "body_text")
DEFAULT_FIELDS = ("subject", "snippet")
ID_RE = re.compile(r"^[a-z0-9-]{1,40}$")


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    gmail_query: str | None
    keywords: tuple
    regex: tuple
    fields: tuple

    @property
    def local(self) -> bool:
        return bool(self.keywords or self.regex)


def _bad(path, problem: str) -> PulseError:
    return PulseError("rules_invalid", f"Rules file {path}: {problem}")


def _str_list(path, rid, rule, key) -> tuple:
    val = rule.get(key, [])
    if not isinstance(val, list) or not all(isinstance(v, str) and v for v in val):
        raise _bad(path, f"rule {rid}: {key} must be a list of non-empty strings.")
    return tuple(val)


def load_rules(path, full: bool) -> list:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise _bad(path, "cannot be read.") from None
    try:
        data = json.loads(text)
    except ValueError as e:
        raise _bad(path, f"is not valid JSON ({e.msg}, line {e.lineno}).") from None
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list) or not data["rules"]:
        raise _bad(path, 'must be a JSON object with a non-empty "rules" list.')
    out, seen = [], set()
    for n, r in enumerate(data["rules"], 1):
        if not isinstance(r, dict):
            raise _bad(path, f"rule #{n} must be a JSON object.")
        rid = r.get("id")
        if not isinstance(rid, str) or not ID_RE.match(rid):
            raise _bad(path, f"rule #{n}: id must match [a-z0-9-]{{1,40}}.")
        if rid in seen:
            raise _bad(path, f"rule {rid}: duplicate id.")
        seen.add(rid)
        unknown = set(r) - RULE_KEYS
        if unknown:
            raise _bad(path, f"rule {rid}: unknown key(s) {', '.join(sorted(unknown))}.")
        desc = r.get("description", "")
        query = r.get("gmail_query")
        if not isinstance(desc, str) or (query is not None and (not isinstance(query, str) or not query.strip())):
            raise _bad(path, f"rule {rid}: description and gmail_query must be strings.")
        keywords = _str_list(path, rid, r, "keywords")
        patterns = []
        for p in _str_list(path, rid, r, "regex"):
            try:
                patterns.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                raise _bad(path, f"rule {rid}: regex {p!r} is invalid ({e}).") from None
        fields = _str_list(path, rid, r, "fields") if "fields" in r else DEFAULT_FIELDS
        bad_fields = [f for f in fields if f not in FIELDS]
        if bad_fields or not fields:
            raise _bad(path, f"rule {rid}: fields must be from {', '.join(FIELDS)}.")
        if not (query or keywords or patterns):
            raise _bad(path, f"rule {rid}: needs at least one of gmail_query, keywords, regex.")
        if "body_text" in fields and not full:
            raise _bad(path, f"rule {rid} needs --full (it matches body_text).")
        out.append(Rule(rid, desc, query, keywords, tuple(patterns), tuple(fields)))
    return out


def _field_text(row: dict, field: str) -> str:
    if field == "attachments.name":
        return "\n".join(a.get("name", "") for a in row.get("attachments") or [])
    val = row.get(field, "")
    return "\n".join(val) if isinstance(val, list) else str(val or "")


def match(rule: Rule, row: dict) -> list:
    """Fields where any keyword (case-insensitive substring) or regex (case-insensitive) hits; [] if none."""
    hit = []
    for f in rule.fields:
        text = _field_text(row, f)
        low = text.casefold()
        if any(k.casefold() in low for k in rule.keywords) or any(p.search(text) for p in rule.regex):
            hit.append(f)
    return hit
