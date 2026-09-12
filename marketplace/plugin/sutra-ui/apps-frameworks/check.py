#!/usr/bin/env python3
"""check.py -- the Apps frameworks checks runner (design v1, section Checks runner).

    python3 check.py <app folder> [--kind page|chat|link] [--home DIR] [--kit DIR]
                     [--allow-skip-render] [--waive C27 --why "..."] [--json] [--no-write]

Every check id C1..C38 has one evaluator here. Levels: the ids in kit.json
v1_must_fix report as `must-fix` and block "done"; every other id reports as
`suggest` and never blocks (its designed level stays in angles/*.json as the
target for a later promotion). Exit codes: 0 nothing blocking; 1 a blocking
failure; 2 the folder or manifest could not be read or the kind is unknown;
3 a page whose render did not run and --allow-skip-render was not passed.
Precedence 2 > 1 > 3 > 0.

Writers: the only thing this runner writes is the `## Checks` block of APP.md
(pass --no-write to skip). It never touches the stamp, module.json or events.
Constants are imported from the runtime (modules_api, modules_pkg) so a cap
quoted here can never drift from the server; the import falls back to the
literal values when the runner is used outside the sutra-ui venv.
"""
import argparse
import datetime
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

KIT = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(KIT)
LIB = os.path.join(os.path.dirname(os.path.dirname(UI)), "lib") if os.path.basename(os.path.dirname(UI)) == "plugin" else os.path.join(os.path.dirname(UI), "lib")
for p in (UI, LIB):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# ---- runtime constants (imported; literal fallback) --------------------------
try:
    import modules_api as _api
    HTML_MAX, INSTR_MAX, NAME_MAX, TAGLINE_MAX = _api.HTML_MAX, _api.INSTR_MAX, _api.NAME_MAX, _api.TAGLINE_MAX
    TOKEN_CSS, LINK_FORBIDDEN = _api.TOKEN_CSS, tuple(_api.LINK_FORBIDDEN)
except Exception:  # pragma: no cover - outside the venv
    _api = None
    HTML_MAX, INSTR_MAX, NAME_MAX, TAGLINE_MAX = 512 * 1024, 4000, 80, 140
    LINK_FORBIDDEN = ("terminal", "usage")
    try:
        _src = open(os.path.join(UI, "modules_api.py"), encoding="utf-8").read()
        TOKEN_CSS = re.search(r'TOKEN_CSS = """(.*?)"""', _src, re.S).group(1)
    except Exception:
        TOKEN_CSS = ""
try:
    import modules_pkg as _pkg
    MAX_MEMBERS, MAX_FILE, MAX_TOTAL = _pkg.MAX_MEMBERS, _pkg.MAX_FILE, _pkg.MAX_TOTAL
except Exception:  # pragma: no cover
    _pkg = None
    MAX_MEMBERS, MAX_FILE, MAX_TOTAL = 200, 5 * 1024 * 1024, 20 * 1024 * 1024

TOKENS = sorted(set(re.findall(r"--([a-z][a-z0-9-]*)\s*:", TOKEN_CSS)))
NOT_INJECTED = ("shadow", "bubble", "th-bg", "knob", "vld-tx")
KINDS = ("page", "chat", "link")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
SCREEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
RECORD = "APP.md"
TRIVIAL = {"it works", "works", "done", "no errors", "it runs", "passes", "ok", "fine", "good", "yes", "n/a", "none"}

# ---- C4: the single home of "nothing founder-only reaches a builder" ---------
LEAK_PATTERNS = (
    (re.compile(r"(?m)^\s*(INPUT|TYPE|ROUTE|DEPTH|TASK|TRIAGE|EFFORT|COST|IMPACT|ESTIMATE|ACTUAL):\s"), "a governance block line"),
    (re.compile(r"(?m)^\s*OS: .*>"), "an output-trace line"),
    (re.compile(r"\+-- (FLOW|BLUEPRINT|DISPATCH)"), "a governance box"),
    (re.compile(r"(?m)^\s*\[[A-Z][A-Z0-9-]*[.·][A-Z]"), "an H-Sutra header"),
    (re.compile(r"\bATOM:|\bBUILD-LAYER\b|\bROUTING PIN\b|Do not re-classify"), "internal routing text"),
    (re.compile(r"\bdref-[0-9a-f]{6,}"), "a department ref"),
    (re.compile(r"\bADR-[0-9]{3}\b"), "a decision record number"),
    # design decision ids only: a bare "D12" is a loan bucket or a chip, never governance (codex R2 P1)
    (re.compile(r"\bD-M[0-9]{1,2}\b"), "a design decision id"),
)
# The internal word. Applied ONLY to text the product itself puts in front of a
# person (kit files, seeds, an app's name, tagline and opening message), never
# to a builder's own answers or page prose, where "modules by owner" is theirs.
LEAK_STRICT = (re.compile(r"(?<![./\w-])modules?(?![./\w-])", re.IGNORECASE), "the internal word module")
LEAK_ALLOWED = ("module.json", "/api/modules", ".sutra-ui/modules", "modules_api", "modules home")


def leak_hits(text, strict=False):
    """-> [(reason, snippet)] for every founder-only fragment in builder-facing text.
    strict=True adds the internal-word rule (product copy, not builder prose)."""
    hits = []
    text = text or ""
    patterns = LEAK_PATTERNS + ((LEAK_STRICT,) if strict else ())
    for rx, reason in patterns:
        for m in rx.finditer(text):
            if reason == "the internal word module":
                ls = text.rfind("\n", 0, m.start()) + 1
                le = text.find("\n", m.end())
                line = text[ls: le if le != -1 else len(text)].lower()
                if any(a in line for a in LEAK_ALLOWED):
                    continue
            hits.append((reason, text[max(0, m.start() - 20): m.end() + 20].replace("\n", " ")))
    return hits


# ---- kit + record loading ----------------------------------------------------

def load_kit(kit_dir):
    kit = json.load(open(os.path.join(kit_dir, "kit.json"), encoding="utf-8"))
    checks, questions = {}, {}
    for name in ("product", "strategy", "design", "engineering", "backend", "frontend"):
        a = json.load(open(os.path.join(kit_dir, "angles", name + ".json"), encoding="utf-8"))
        for c in a["checks"]:
            checks[c["id"]] = dict(c, angle=name)
        for q in a["questions"]:
            questions[q["id"]] = dict(q, angle=name)
    profiles = {k: json.load(open(os.path.join(kit_dir, "profiles", k + ".json"), encoding="utf-8")) for k in KINDS}
    screens = json.load(open(os.path.join(kit_dir, "screens.json"), encoding="utf-8"))
    return {"kit": kit, "checks": checks, "questions": questions, "profiles": profiles, "screens": screens,
            "must_fix": set(kit.get("v1_must_fix") or [])}


STAMP_RE = re.compile(r"^frameworkKit:\s*(\{.*\})\s*$")


def parse_record(text):
    """-> {stamp, answers{id: answer}, owner_notes{Angle: text}, changes[list of bullet lines], has_checks}"""
    out = {"stamp": None, "stamp_line": None, "answers": {}, "owner_notes": {}, "changes": [], "has_checks": False}
    lines = text.splitlines()
    for l in lines:
        if l.strip():
            out["stamp_line"] = l
            m = STAMP_RE.match(l.strip())
            if m:
                try:
                    out["stamp"] = json.loads(m.group(1))
                except ValueError:
                    out["stamp"] = None
            break
    section = None
    for l in lines:
        if l.startswith("## "):
            section = l[3:].strip()
            if section == "Checks":
                out["has_checks"] = True
            continue
        if section == "Changes" and l.strip().startswith("- "):
            out["changes"].append(l.strip()[2:])
            continue
        if l.startswith("|") and not l.startswith("|---"):
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            if section is None and len(cells) >= 7 and cells[0] in ("Product", "Strategy", "Design", "Engineering", "Backend", "Frontend"):
                out["owner_notes"][cells[0]] = cells[6]
            elif section not in (None, "Checks", "Changes") and len(cells) >= 3 and re.match(r"^(P|S|DS|E|B|F)[0-9]{1,2}$", cells[0]):
                out["answers"][cells[0]] = cells[-1]
    return out


class _Census(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.top, self.tags, self.attrs, self.text, self.lang, self.styles = 0, 0, [], [], [], False, []
        self._in_style = False
        self.controls = []
    def handle_decl(self, decl):
        self.tags.append("!doctype")
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if self.depth == 0:
            self.top += 1
        self.depth += 1
        d = dict(attrs)
        if "lang" in d:
            self.lang = True
        self.attrs.append((tag, d))
        if tag == "style":
            self._in_style = True
        if tag in ("button", "a", "input", "select", "textarea", "div", "span", "img"):
            self.controls.append((tag, d))
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)
    def handle_endtag(self, tag):
        self.depth = max(0, self.depth - 1)
        if tag == "style":
            self._in_style = False
    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)
        elif data.strip():
            self.text.append(data.strip())


def census(html_text):
    c = _Census()
    try:
        c.feed(html_text or "")
    except Exception:
        pass
    return c


def css_text(html_text, cen):
    inline = re.findall(r'style\s*=\s*"([^"]*)"', html_text or "", re.IGNORECASE)
    return "\n".join(cen.styles + inline)


# ---- evaluators --------------------------------------------------------------
# each returns (status, detail); status in pass fail warn skip n/a

def _nt(cell):
    s = (cell or "").strip().lower().rstrip(".!")
    return s and s not in TRIVIAL and len(s.split()) >= 5


def c1(x):
    req = [q for q, m in x.q.items() if x.kind in m["required_for"]]
    missing = [q for q in req if not (x.answers.get(q) or "").strip()]
    nr = [q for q in req if (x.answers.get(q) or "").strip().lower() == "not recorded"]
    if not x.record_text:
        return "fail", "APP.md is missing at the folder root"
    if missing:
        return "fail", "unanswered: " + ", ".join(missing)
    if nr:
        return "warn", "not recorded yet (an imported app; the first edit fills these): " + ", ".join(nr)
    return "pass", "%d answers present" % len(req)


def c2(x):
    bad = []
    for q in ("P3", "P5"):
        if q in x.answers and not _nt(x.answers[q]):
            bad.append(q)
    if "P5" in x.answers and re.match(r"^\s*(none|nothing|n/a|it can'?t|won'?t happen)", x.answers["P5"], re.I):
        bad.append("P5 (a denial)")
    return ("fail", "not a real answer: " + ", ".join(bad)) if bad else ("pass", "success and failure answers are real sentences")


def c3(x):
    name, tag = str(x.raw.get("name") or ""), str(x.raw.get("tagline") or "")
    if not name.strip() or not tag.strip():
        return "fail", "name and tagline are both required"
    if len(name) > NAME_MAX or len(tag) > TAGLINE_MAX:
        return "fail", "name <= %d and tagline <= %d characters" % (NAME_MAX, TAGLINE_MAX)
    if name.strip().lower() == tag.strip().lower():
        return "fail", "name and tagline must differ"
    p2 = (x.answers.get("P2") or "").lower()
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
    if p2 and norm(tag) not in norm(p2) and norm(p2) not in norm(tag):
        return "fail", "the tagline should be the one line the builder gave (P2)"
    return "pass", "name and tagline set"


def c4(x):
    # governance text anywhere a person reads; the internal word only in the
    # product's own copy (name, tagline, opening message), never in the
    # builder's answers or page prose (codex R2 P1)
    hits = leak_hits(x.record_text) + (leak_hits(" ".join(x.cen.text)) if x.index_html else [])
    for t in (str(x.raw.get("name") or ""), str(x.raw.get("tagline") or ""), str((x.raw.get("surface") or {}).get("instructions") or "")):
        hits += leak_hits(t, strict=True)
    return ("fail", "; ".join("%s: %r" % h for h in hits[:4])) if hits else ("pass", "plain words only")


def c5(x):
    p1 = x.answers.get("P1") or ""
    if re.search(r"\band also\b|\bas well as\b|;", p1) or len(re.findall(r"[.!?](\s|$)", p1)) > 2:
        return "warn", "the first answer sounds like two jobs; consider two apps"
    return "pass", "one job"


def c6(x):
    dept = x.raw.get("department") if isinstance(x.raw.get("department"), dict) else None
    ref = dept.get("ref") if dept else None
    if not ref:
        s3 = (x.answers.get("S3") or "").strip().lower()
        if not s3 or "unassigned" in s3:
            return "pass", "no department; the row reads Unassigned"
        # must-fix since kit 1.1.0 (codex fold): the row names a department the app is not filed under
        return "fail", "the row names a department but the app is not filed under one; assign it, or write Unassigned"
    if not re.match(r"^dref-[0-9a-f]{16}$", str(ref)):
        return "fail", "department.ref is not a ref"
    try:
        import placement_engine as E
        domains = E.load_domains()
    except Exception:
        return "skip", "charter not read: the registry did not answer"
    d = domains.get(ref) if isinstance(domains, dict) else None
    if not d:
        return "warn", "the department ref is not in this machine's registry (reads as Unassigned)"
    name = str(d.get("name") or "")
    if name and name.lower() not in (x.answers.get("S3") or "").lower():
        return "fail", "the Department row should name %r" % name
    return "pass", "filed under %s" % name


def c7(x):
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", x.answers.get("P6") or "")
    if not m:
        return "fail", "the owner answer needs a review date as YYYY-MM-DD"
    try:
        d = datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return "fail", "review date does not parse"
    created = str(x.raw.get("created_at") or "")[:10]
    try:
        if created and d < datetime.date.fromisoformat(created):
            return "fail", "review date is before the app was created"
    except ValueError:
        pass
    return "pass", "review on %s" % d


def c8(x):
    pub = x.raw.get("publish")
    if pub in (None, {}):
        return "pass", "no publish block"
    if isinstance(pub, dict):
        extra = set(pub) - {"state", "checksum", "version"}
        if pub.get("state") in ("exported", "imported") and not extra:
            return "pass", "server-owned publish state %s" % pub["state"]
        return "fail", "publish was authored by hand (keys: %s); the desktop owns it" % ", ".join(sorted(pub))
    return "fail", "publish must be an object or absent"


def c9(x):
    s2 = (x.answers.get("S2") or "").strip()
    if not ID_RE.match(s2):
        return "pass", "replaces nothing by id"
    mj = os.path.join(x.home, s2, "module.json")
    if not os.path.isfile(mj):
        return "warn", "names app %r which does not exist here" % s2
    try:
        st = json.load(open(mj, encoding="utf-8")).get("status")
    except Exception:
        st = None
    return ("warn", "the replaced app %r is still ready; archive it when this one lands" % s2) if st == "ready" else ("pass", "replaces %s" % s2)


COLOR_LIT = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black|red|blue|green|gray|grey|orange|yellow|purple|pink|navy|teal|silver|gold)\b", re.IGNORECASE)


def c10(x):
    css = x.css
    lits = [m.group(0) for m in COLOR_LIT.finditer(css)]
    names = set(re.findall(r"var\(--([a-z][a-z0-9-]*)", css))
    unknown = sorted(n for n in names if n not in TOKENS)
    parts = []
    if lits:
        parts.append("literal colours: %s; use var(--ink), var(--acc)..." % ", ".join(sorted(set(lits))[:5]))
    if unknown:
        ni = [n for n in unknown if n in NOT_INJECTED]
        parts.append("unknown token names: %s%s" % (", ".join(unknown), " (these five are not injected: --shadow --bubble --th-bg --knob --vld-tx)" if ni else ""))
    return ("fail", "; ".join(parts)) if parts else ("pass", "%d token names, no literals" % len(names))


def c11(x):
    if re.search(r":root\s*[{,]|html\[data-theme|#sutra-tokens", x.css):
        return "fail", "the page redefines the theme set (:root / html[data-theme] / #sutra-tokens)"
    return "pass", "theme set untouched"


def c12(x):
    hs = [int(t[1]) for t in x.cen.tags if re.match(r"^h[1-6]$", t)]
    if hs.count(1) > 1:
        return "fail", "%d h1 elements; at most one" % hs.count(1)
    prev = 0
    for h in hs:
        if h > prev + 1 and prev:
            return "fail", "heading level jumps to h%d after h%d" % (h, prev)
        prev = h
    return "pass", "headings in order"


def c13(x):
    ins = str((x.raw.get("surface") or {}).get("instructions") or "")
    if not ins.strip():
        return "fail", "instructions are empty"
    if len(ins) > INSTR_MAX:
        return "fail", "instructions are %d characters; the cap is %d" % (len(ins), INSTR_MAX)
    lines = [l for l in ins.splitlines() if l.strip()]
    probs = []
    if not lines[0].strip().endswith("."):
        probs.append("the first line should be one sentence ending in a full stop")
    if sum(1 for l in lines if l.strip().startswith("-")) > 8:
        probs.append("more than eight dash rules")
    last = lines[-1].strip()
    if "?" not in last and not re.match(r"^(Start by|Ask)\b", last):
        probs.append("end with one question or an ask")
    return ("fail", "; ".join(probs)) if probs else ("pass", "reads as a first message")


def c14(x):
    head = " ".join(x.cen.text)[:400].lower()
    for k in ("name", "tagline"):
        v = str(x.raw.get(k) or "").strip().lower()
        if v and len(v) > 3 and v in head:
            return "warn", "the page repeats the %s the header already shows" % k
    return "pass", "no repeated header"


def c15(x):
    if re.search(r"@keyframes|animation\s*:|transition\s*:", x.css) and "prefers-reduced-motion" not in x.css:
        return "warn", "motion without a prefers-reduced-motion guard"
    return "pass", "no unguarded motion"


def c16(x):
    css = x.css
    for m in re.finditer(r"min-width\s*:\s*(\d+)px", css):
        if int(m.group(1)) > 320:
            return "warn", "min-width %spx may scroll sideways in a narrow pane" % m.group(1)
    for m in re.finditer(r"(?<!min-)(?<!max-)width\s*:\s*(\d+)px", css):
        if int(m.group(1)) > 360:
            return "warn", "a fixed width of %spx may not fit the pane" % m.group(1)
    if re.search(r"overflow-x\s*:\s*scroll", css):
        return "warn", "overflow-x: scroll invites sideways scrolling"
    return "pass", "fits a narrow pane (static read)"


def c17(x):
    raw = x.raw
    mid = os.path.basename(x.folder.rstrip("/"))
    if _pkg is not None:
        try:
            _pkg.validate_manifest(raw, mid)
        except Exception as e:
            return "fail", str(e)
    else:
        for k in ("schema", "id", "name", "kind", "status", "version"):
            if k not in raw:
                return "fail", "manifest lacks %s" % k
    if raw.get("id") != mid or not ID_RE.match(str(mid)) or str(mid).startswith("sys-"):
        return "fail", "manifest id must equal the folder name and not start with sys-"
    if raw.get("kind") != x.kind:
        return "fail", "manifest kind is %r, checked as %r" % (raw.get("kind"), x.kind)
    return "pass", "manifest valid"


def c18(x):
    allowed = x.profile.get("allowed_files") or []
    bad = []
    for rel in x.files:
        if any(part.startswith(".") for part in rel.split("/")):
            continue
        if rel.split("/")[0] == "holding":
            continue
        ok = rel == RECORD or rel in allowed or any(a.endswith("/**") and rel.startswith(a[:-2]) for a in allowed)
        if re.search(r"\.events\.", rel):
            bad.append(rel + " (a hand-written event log)")
        elif not ok:
            bad.append(rel + " (will not travel when you share the app)")
    return ("fail", "; ".join(bad)) if bad else ("pass", "%d allowed files" % len(x.files))


def c19(x):
    total, over = 0, []
    for rel in x.files:
        try:
            sz = os.path.getsize(os.path.join(x.folder, rel))
        except OSError:
            continue
        total += sz
        if sz > MAX_FILE:
            over.append(rel)
    probs = []
    if len(x.files) > MAX_MEMBERS:
        probs.append("%d files; the cap is %d" % (len(x.files), MAX_MEMBERS))
    if over:
        probs.append("over %d MB: %s" % (MAX_FILE // (1024 * 1024), ", ".join(over)))
    if total > MAX_TOTAL:
        probs.append("total %d MB; the cap is %d MB" % (total // (1024 * 1024), MAX_TOTAL // (1024 * 1024)))
    if x.kind == "page" and x.index_html is not None and len(x.index_html.encode("utf-8")) > HTML_MAX:
        probs.append("index.html is over %d KB" % (HTML_MAX // 1024))
    return ("fail", "; ".join(probs)) if probs else ("pass", "%d files, %d KB" % (len(x.files), total // 1024))


def c20(x):
    ms = x.raw.get("frameworkKit") if isinstance(x.raw.get("frameworkKit"), dict) else None
    rs = x.rec["stamp"]
    if not x.record_text and ms and (x.raw.get("origin") or {}).get("imported"):
        return "warn", "record reconstructed on import; answers are not recorded yet"
    if not rs:
        return "fail", "APP.md line 1 must be the frameworkKit stamp the desktop wrote"
    if not ms:
        return "fail", "module.json carries no frameworkKit mirror"
    for k in ("version", "digest", "created_at"):
        if rs.get(k) != ms.get(k):
            return "fail", "stamp %s differs between APP.md and module.json" % k
    if not re.match(r"^[0-9a-f]{12}$", str(rs.get("digest") or "")):
        return "fail", "stamp digest is not 12 hex characters"
    installed = x.kitmeta["kit"].get("version")
    if installed and str(rs.get("version")) != str(installed):
        return "warn", "built on kit %s; installed is %s (Edit in chat offers a migration)" % (rs.get("version"), installed)
    return "pass", "stamp present and agreeing"


def c21(x):
    v, ms = x.raw.get("version"), x.raw.get("updated_ms")
    if not isinstance(v, int) or v < 1:
        return "fail", "version must be a positive integer the desktop writes"
    if ms is not None and not isinstance(ms, int):
        return "fail", "updated_ms must be an integer the desktop writes"
    return "pass", "server-owned fields intact"


def c22(x):
    e2 = (x.answers.get("E2") or "").lower()
    if len(e2) < 12:
        return "fail", "the regression check needs a sentence someone can act on"
    # act + observe verb sets widened when C22 became must-fix (kit 1.1.0, codex fold): "reopen the page and
    # verify the total still matches" and "open it and confirm the new row is visible" are regression checks
    if (not re.search(r"\b(open|opens|click|paste|reopen|read|run|look)\b", e2)
            or not re.search(r"\b(see|sees|reads|shows|lands|land|top row|asks|verify|verifies|confirm|confirms|visible|appears|loads)\b", e2)):
        return "fail", "name an action (open, click, paste, look) and what you then see (reads, shows, appears, confirm)"
    return "pass", "regression check is actionable"


def c23(x):
    if not x.rec["changes"]:
        return "fail", "## Changes has no dated line"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", x.rec["changes"][0])
    if not m:
        return "fail", "the newest Changes line must start with a date"
    upd = str(x.raw.get("updated_at") or "")[:10]
    try:
        if upd and datetime.date.fromisoformat(m.group(1)) < datetime.date.fromisoformat(upd):
            return "fail", "the newest Changes line is older than the last edit"
    except ValueError:
        pass
    return "pass", "changes dated %s" % m.group(1)


def c24(x):
    return ("pass", "schema 2") if x.raw.get("schema") == 2 else ("warn", "manifest schema %r; sharing needs 2 (the next edit bumps it)" % x.raw.get("schema"))


NET_RE = re.compile(r"\bfetch\s*\(|XMLHttpRequest|new\s+WebSocket|EventSource|navigator\.sendBeacon|\bimport\s*\(|importScripts|<script[^>]+\bsrc=|<link[^>]+\bhref=|@import|<form\b|target=\"_top\"|target=\"_parent\"|window\.top\b", re.IGNORECASE)


def c25(x):
    hits = []
    for rel in x.files:
        if rel == "index.html" or rel.endswith((".js", ".htm")):
            try:
                text = open(os.path.join(x.folder, rel), encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if NET_RE.search(line):
                    hits.append("%s:%d" % (rel, i))
    return ("fail", "the page runs with no network; these calls do nothing: " + ", ".join(hits[:6])) if hits else ("pass", "no network calls")


def c26(x):
    bad = []
    for tag, d in x.cen.attrs:
        for k in ("src", "href", "srcset", "poster", "action"):
            v = d.get(k)
            if not v:
                continue
            v = v.strip()
            if v.startswith(("data:", "blob:", "#")):
                continue
            if v.startswith("assets/"):
                bad.append("%s %s=%r: assets ships inside the package but no route serves it at runtime; put the data inline" % (tag, k, v))
            elif v.startswith("/api/"):
                bad.append("%s %s=%r: a page cannot reach the desktop" % (tag, k, v))
            else:
                bad.append("%s %s=%r" % (tag, k, v))
    for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)", x.css):
        v = m.group(1).strip()
        if not v.startswith(("data:", "blob:", "#")):
            bad.append("css url(%r)" % v)
    return ("fail", "; ".join(bad[:5])) if bad else ("pass", "everything inline")


def c27(x):
    b1 = (x.answers.get("B1") or "").lower()
    if re.search(r"\bfetch\b|\bhttp|api call|endpoint|database|localstorage|saves? (it|them|the data)|\buploads?\b|reads? my .*\.(csv|json|xlsx)", b1):
        return "fail", "the answer assumes reach a page does not have (no network, no storage); the data is baked into the file"
    return "pass", "data answer fits a sealed page"


SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:api[_-]?key|secret|password|token)\s*[:=]\s*[\"'][^\"']{12,}[\"']", re.IGNORECASE)


def c28(x):
    hits = []
    for rel in x.files + ([RECORD] if x.record_text else []):
        if not (rel in ("module.json", "index.html", RECORD, "data-policy.json") or rel.endswith((".json", ".txt", ".env", ".csv", ".js", ".html"))):
            continue
        try:
            text = open(os.path.join(x.folder, rel), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in SECRET_RE.finditer(text):
            s = m.group(0)
            hits.append("%s: ...%s" % (rel, s[-4:]))
    return ("fail", "looks like a secret: " + ", ".join(hits[:4])) if hits else ("pass", "no secrets")


def c29(x):
    cwd = (x.raw.get("surface") or {}).get("cwd")
    if cwd in (None, ""):
        return "pass", "no folder named; the default applies"
    home = os.path.realpath(os.path.expanduser("~"))
    if not isinstance(cwd, str) or len(cwd) > 1024 or not os.path.isabs(cwd):
        return "fail", "the folder must be an absolute path under your home (at most 1024 characters)"
    real = os.path.realpath(os.path.expanduser(cwd))
    if not real.startswith(home + os.sep) and real != home:
        return "fail", "the folder is outside your home; the desktop would silently use its default instead"
    if not os.path.isdir(real):
        return "fail", "the folder does not exist"
    return "pass", "folder is real and under home"


CMD_RE = re.compile(r"curl |wget |\|\s*sh\b|bash -c|npm i(?:nstall)?\b|pip install|rm -rf|git push|ssh |open -a|osascript|launchctl")


def c30(x):
    ins = str((x.raw.get("surface") or {}).get("instructions") or "")
    notes = (x.rec["owner_notes"].get("Backend") or "").lower()
    missing = sorted({m.group(0).strip() for m in CMD_RE.finditer(ins) if m.group(0).strip().split()[0].lower() not in notes})
    return ("fail", "commands in the message that the record does not list: " + ", ".join(missing)) if missing else ("pass", "commands match the record")


def c31(x):
    b2 = (x.answers.get("B2") or "").strip().lower()
    first = re.split(r"[\s,.;:]+", b2)[0] if b2 else ""
    return ("pass", "data declared %s" % first) if first in ("real", "masked", "made-up", "aggregate") else ("warn", "say whether the data is real, masked, made-up or aggregate")


def c32(x):
    surf = x.raw.get("surface") if isinstance(x.raw.get("surface"), dict) else {}
    scr = surf.get("screen")
    probs = []
    if not isinstance(scr, str) or not SCREEN_RE.match(scr):
        probs.append("surface.screen must name a screen")
    elif scr in LINK_FORBIDDEN or scr not in (x.kitmeta["screens"].get("screens") or []):
        probs.append("%r is not a screen a link may open" % scr)
    if set(surf) - {"screen"}:
        probs.append("surface carries keys other than screen: %s" % ", ".join(sorted(set(surf) - {"screen"})))
    if "index.html" in x.files or any(f.startswith("assets/") for f in x.files):
        probs.append("a link has no page and no assets")
    return ("fail", "; ".join(probs)) if probs else ("pass", "opens %s" % scr)


def c33(x):
    tags = x.cen.tags
    probs = []
    for t in ("!doctype", "html", "head", "body", "frameset", "link"):
        if t in tags:
            probs.append("<%s> does not belong in a fragment" % t.lstrip("!"))
    if re.search(r"<script[^>]+\bsrc=", x.index_html or "", re.IGNORECASE):
        probs.append("<script src> loads nothing here; inline it")
    if not x.cen.lang:
        probs.append("the root element needs lang=")
    if probs:
        return "fail", "; ".join(probs)
    return ("warn", "%d top-level elements; one root element is the shape" % x.cen.top) if x.cen.top > 1 else ("pass", "a fragment with one root")


def c34(x):
    probs, warns = [], []
    for tag, d in x.cen.controls:
        if tag in ("div", "span") and any(k.startswith("on") for k in d):
            probs.append("a click handler on a <%s>" % tag)
        if d.get("role") == "button" and "tabindex" not in d:
            probs.append("role=button without tabindex")
        if tag == "img" and "alt" not in d:
            probs.append("an image without alt")
        try:
            if int(d.get("tabindex", "0")) > 0:
                probs.append("tabindex above 0")
        except ValueError:
            pass
        if tag in ("button", "a", "input", "select", "textarea") and not (d.get("aria-label") or d.get("title") or d.get("aria-labelledby") or d.get("placeholder") or tag in ("button", "a")):
            warns.append("a <%s> whose name I cannot read statically" % tag)
    if re.search(r"outline\s*:\s*none", x.css) and ":focus-visible" not in x.css:
        probs.append("outline:none without a :focus-visible rule")
    if probs:
        return "fail", "; ".join(sorted(set(probs)))
    return ("warn", "; ".join(sorted(set(warns)))) if warns else ("pass", "controls are real and named")


def c35(x):
    m = re.search(r"localStorage|sessionStorage|indexedDB|document\.cookie|caches\.|navigator\.storage|Notification\b|requestPermission", x.index_html or "")
    return ("fail", "the page cannot store anything (%s); state lives in the file or resets" % m.group(0)) if m else ("pass", "no storage use (dynamic property access is not caught)")


def c36(x):
    if x.kind != "page":
        return "n/a", "nothing to render for a %s; every %s check is a static read" % (x.kind, x.kind)
    if os.environ.get("KIT_NO_RENDER") == "1":
        return "skip", "render: not run (disabled for this run)"
    node = _which("node")
    chrome = _find_chrome()
    if not node or not chrome or not os.path.isfile(os.path.join(x.kitdir, "render_check.mjs")):
        return "skip", "render: not run (no headless browser or node on this machine)"
    results = []
    for theme in ("dark", "light"):
        doc = ('<!doctype html><html data-theme="%s"><head><meta charset="utf-8"><meta name="color-scheme" content="dark light">'
               '<style id="sutra-tokens">%s</style></head><body>%s</body></html>' % (theme, TOKEN_CSS, x.index_html or ""))
        fd, path = tempfile.mkstemp(suffix=".html", prefix="kit-render-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(doc)
        try:
            out = subprocess.run([node, os.path.join(x.kitdir, "render_check.mjs"), "file://" + path, chrome],
                                 capture_output=True, text=True, timeout=60)
            res = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {"ok": False, "errors": [out.stderr[-200:]]}
        except Exception as e:
            res = {"ok": False, "errors": [str(e)[:200]]}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        results.append((theme, res))
    bad = [t for t, r in results if not r.get("ok")]
    if bad:
        return "fail", "render errors in %s: %s" % (", ".join(bad), "; ".join(str(e) for t, r in results for e in (r.get("errors") or [])[:2]))
    return "pass", "rendered dark and light, no console errors"


def c37(x):
    f2 = re.sub(r"[^a-z ]", "", (x.answers.get("F2") or "").lower()).strip()
    return ("pass", f2) if f2.startswith(("resets each time", "baked into the file")) else ("fail", "answer 'resets each time' or 'baked into the file'")


def c38(x):
    ins = str((x.raw.get("surface") or {}).get("instructions") or "")
    names_call = "/api/" in ins or "/api/" in (x.rec["owner_notes"].get("Backend") or "") or "/api/" in (x.answers.get("B1") or "")
    dp = os.path.join(x.folder, "data-policy.json")
    if not names_call:
        return ("fail", "data-policy.json is present but nothing calls the desktop; delete this file") if os.path.isfile(dp) else ("pass", "no desktop service is called; no allowlist needed")
    if not os.path.isfile(dp):
        return "fail", "the message calls a desktop service; write data-policy.json with the call, why, the threat and the check that covers it"
    try:
        doc = json.load(open(dp, encoding="utf-8"))
    except Exception as e:
        return "fail", "data-policy.json does not parse: %s" % e
    schema_path = os.path.join(x.kitdir, "data-policy.schema.json")
    try:
        import jsonschema
        jsonschema.validate(doc, json.load(open(schema_path, encoding="utf-8")))
    except ImportError:
        pass
    except Exception as e:
        return "fail", "data-policy.json fails its schema: %s" % getattr(e, "message", e)
    apis = doc.get("panel_apis") if isinstance(doc, dict) else None
    if not isinstance(apis, list) or not apis:
        return "fail", "delete this file, nothing calls the desktop, or list the calls"
    for e in apis:
        if not all(isinstance(e.get(k), str) and e.get(k).strip() for k in ("call", "why", "threat", "check_id")):
            return "fail", "each entry needs call, why, threat and check_id"
        if e["check_id"] not in x.kitmeta["checks"]:
            return "fail", "check_id %r is not a check in this kit" % e["check_id"]
    return "pass", "%d desktop call(s) written down" % len(apis)


EVALUATORS = {"C%d" % i: globals()["c%d" % i] for i in range(1, 39)}

# Checks that judge an ANSWER cell. When the cell reads `not recorded` (a
# reconstructed record after an import) their failure is a WARN: the record
# was never written by a builder, so nothing was gotten wrong.
ANSWER_CHECKS = {"C2": ("P3", "P5"), "C3": ("P2",), "C5": ("P1",), "C6": ("S3",), "C7": ("P6",), "C9": ("S2",),
                 "C22": ("E2",), "C27": ("B1",), "C31": ("B2",), "C37": ("F2",)}


def _which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _find_chrome():
    for c in (os.environ.get("KIT_CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium", _which("google-chrome"), _which("chromium"), _which("chrome")):
        if c and os.path.isfile(c):
            return c
    return None


# ---- the run -----------------------------------------------------------------

class Ctx(object):
    pass


def run(folder, kind=None, home=None, kitdir=None, waivers=None, allow_skip_render=False):
    """-> (results, summary, exit_code). results: list of dicts id/level/status/detail."""
    folder = os.path.realpath(folder)
    kitdir = os.path.realpath(kitdir or KIT)
    meta = load_kit(kitdir)
    mj = os.path.join(folder, "module.json")
    if not os.path.isdir(folder) or not os.path.isfile(mj):
        return [], {"error": "no app folder with a module.json at %s" % folder}, 2
    try:
        raw = json.load(open(mj, encoding="utf-8"))
    except Exception as e:
        return [], {"error": "module.json does not parse: %s" % e}, 2
    kind = kind or raw.get("kind")
    if kind not in KINDS:
        return [], {"error": "unknown kind %r (page, chat or link)" % kind}, 2
    x = Ctx()
    x.folder, x.kind, x.raw, x.kitdir, x.kitmeta = folder, kind, raw, kitdir, meta
    x.home = home or os.path.dirname(folder)
    x.profile = meta["profiles"][kind]
    x.q = meta["questions"]
    rp = os.path.join(folder, RECORD)
    x.record_text = open(rp, encoding="utf-8", errors="replace").read() if os.path.isfile(rp) else ""
    x.rec = parse_record(x.record_text)
    x.answers = x.rec["answers"]
    files = []
    for root, dirs, fs in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in fs:
            if f.startswith("."):
                continue
            files.append(os.path.relpath(os.path.join(root, f), folder).replace(os.sep, "/"))
    x.files = sorted(files)
    ip = os.path.join(folder, "index.html")
    x.index_html = open(ip, encoding="utf-8", errors="replace").read() if os.path.isfile(ip) else None
    x.cen = census(x.index_html or "")
    x.css = css_text(x.index_html or "", x.cen)
    waivers = waivers or {}
    results = []
    for cid in sorted(x.profile["checks"], key=lambda s: int(s[1:])):
        c = meta["checks"][cid]
        level = "must-fix" if cid in meta["must_fix"] else "suggest"
        try:
            status, detail = EVALUATORS[cid](x)
        except Exception as e:  # an evaluator bug is a skip, never a silent pass
            status, detail = "skip", "check could not run: %s" % e
        if status == "fail" and cid in ANSWER_CHECKS and any((x.answers.get(q) or "").strip().lower() == "not recorded" for q in ANSWER_CHECKS[cid]):
            status, detail = "warn", "not recorded yet (an imported app; the first edit fills it): " + detail
        if cid in waivers and status == "fail":
            status, detail = "waived", waivers[cid]
        results.append({"id": cid, "level": level, "status": status, "detail": detail, "target_level": c["level"]})
    for cid in ("C36",):
        if cid not in x.profile["checks"] and kind != "page":
            results.append({"id": cid, "level": "suggest", "status": "n/a", "detail": c36(x)[1], "target_level": "required"})
    blocked = any(r["status"] == "fail" and r["level"] == "must-fix" for r in results)
    render = next((r for r in results if r["id"] == "C36"), None)
    render_line = ("render: dark+light" if render and render["status"] == "pass" else
                   "render: not run" if render and render["status"] == "skip" else
                   "render: n/a" if render and render["status"] == "n/a" else "render: errors")
    code = 1 if blocked else (3 if kind == "page" and render and render["status"] == "skip" and not allow_skip_render else 0)
    order = {"fail": 0, "waived": 1, "warn": 2, "skip": 3, "pass": 4, "n/a": 5}
    results.sort(key=lambda r: (0 if r["level"] == "must-fix" and r["status"] == "fail" else 1, order.get(r["status"], 9), int(r["id"][1:])))
    summary = {
        "kit": meta["kit"].get("version"), "kind": kind, "blocked": blocked, "exit": code, "render": render_line,
        "must_fix_pass": sum(1 for r in results if r["level"] == "must-fix" and r["status"] in ("pass", "n/a")),
        "must_fix_fail": sum(1 for r in results if r["level"] == "must-fix" and r["status"] == "fail"),
        "waived": sum(1 for r in results if r["status"] == "waived"),
        "suggestions": sum(1 for r in results if r["level"] == "suggest" and r["status"] in ("warn", "fail")),
        "skipped": sum(1 for r in results if r["status"] == "skip"),
        "confirm_by_hand": (x.answers.get("E2") or "").strip(),
    }
    return results, summary, code


def render_table(results, summary):
    lines = ["Check  Level     Status  Detail"]
    for r in results:
        lines.append("%-6s %-9s %-7s %s" % (r["id"], r["level"], r["status"], r["detail"]))
    lines.append("")
    lines.append(summary_line(summary))
    if summary.get("confirm_by_hand"):
        lines.append("confirm by hand: " + summary["confirm_by_hand"])
    return "\n".join(lines)


def summary_line(s):
    return "%d must-fix pass, %d fail, %d waived, %d suggestions, %d skipped, %s" % (
        s["must_fix_pass"], s["must_fix_fail"], s["waived"], s["suggestions"], s["skipped"], s["render"])


def write_checks_block(folder, results, summary, waivers):
    """Replace the ## Checks section of APP.md (the only thing this runner writes)."""
    rp = os.path.join(folder, RECORD)
    if not os.path.isfile(rp):
        return False
    text = open(rp, encoding="utf-8").read()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    block = ["## Checks", "", "kit %s | kind %s | %s" % (summary["kit"], summary["kind"], stamp), summary_line(summary)]
    for cid, why in sorted(waivers.items()):
        block.append("waived: %s - %s" % (cid, why))
    fails = [r for r in results if r["status"] == "fail" and r["level"] == "must-fix"]
    for r in fails:
        block.append("must-fix: %s - %s" % (r["id"], r["detail"]))
    if summary.get("confirm_by_hand"):
        block.append("confirm by hand: " + summary["confirm_by_hand"])
    block.append("")
    new = "\n".join(block)
    m = re.search(r"(?ms)^## Checks\n.*?(?=^## |\Z)", text)
    text = (text[:m.start()] + new + "\n" + text[m.end():]) if m else (text.rstrip("\n") + "\n\n" + new + "\n")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def main(argv):
    ap = argparse.ArgumentParser(description="Apps frameworks checks")
    ap.add_argument("folder")
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--home")
    ap.add_argument("--kit")
    ap.add_argument("--allow-skip-render", action="store_true")
    ap.add_argument("--waive", action="append", default=[])
    ap.add_argument("--why", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if len(a.waive) != len(a.why):
        print("every --waive needs a --why", file=sys.stderr)
        return 2
    waivers = dict(zip(a.waive, a.why))
    results, summary, code = run(a.folder, a.kind, a.home, a.kit, waivers, a.allow_skip_render)
    if code == 2 and not results:
        print(json.dumps(summary) if a.json else summary.get("error", "could not read the app"), file=sys.stderr)
        return 2
    if not a.no_write:
        write_checks_block(os.path.realpath(a.folder), results, summary, waivers)
    print(json.dumps({"results": results, "summary": summary}, indent=1) if a.json else render_table(results, summary))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
