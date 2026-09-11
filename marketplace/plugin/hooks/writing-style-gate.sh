#!/usr/bin/env bash
# Sutra OS — Writing Style Gate (Stop event). HARD floor for core:writing-style.
#
# Contract of record: skills/writing-style/SKILL.md — §4 banned list (read at
# runtime from the file, never copied here), §5 budgets (numbers from
# sutra-defaults.json .output_discipline.writing_style), §9 enforcement.
#
# Reads the CURRENT TURN's assistant text (every text block after the last human
# user row; isMeta + tool_result rows excluded — per-turn-hard-gate.sh semantics),
# strips everything that is not prose (code fences, inline code, blockquotes,
# quoted spans, +-- box regions, governance field lines, H-Sutra header), then
# runs the checks. HARD: WS-1 banned phrase, WS-2 structural glyph, WS-3 prose
# budget, WS-4 task table without Impact/Effort, WS-5 ask-to-run (pinned
# projects). Everything else is advisory (ledger only).
#
# Block = JSON {"decision":"block"} on stdout + exit 0 (Stop-hook contract;
# never exit 2). Guards, in order: kill-switches -> fresh-install gate ->
# stop_hook_active (one redo max) -> ack marker -> revoke scope -> transcript.
# Fail-open on any infra failure. Ledger: .enforcement/writing-style.jsonl
#
# Kill ladder: WRITING_STYLE_DISABLED=1 | ~/.writing-style-disabled (founder)
#   | .claude/sutra-project.json "writing_style":"advisory" (ignored for pinned
#   projects) | per-turn .claude/sessions/<sid>/writing-style-ack (REASON=..., audited)
# Revoke: .claude/sessions/<sid>/.writing-style-revoked SCOPE=compress|candor|minimize|all
#   (dotfile, session-scoped by design; written ONLY by per-turn-discipline-prompt.sh).
# Audience: P2/P3 groups downgrade to advisory when the last user message names
#   customer copy or .claude/sessions/<sid>/writing-style-audience has AUDIENCE=customer.
# Test env: WRITING_STYLE_TRANSCRIPT, WRITING_STYLE_SKILL, WRITING_STYLE_DEFAULTS, WRITING_STYLE_SESSION
set -o pipefail

[ "${WRITING_STYLE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.writing-style-disabled" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SKILL="${WRITING_STYLE_SKILL:-$PLUGIN_ROOT/skills/writing-style/SKILL.md}"
DEFAULTS="${WRITING_STYLE_DEFAULTS:-$PLUGIN_ROOT/sutra-defaults.json}"
PROJECT_JSON="$REPO_ROOT/.claude/sutra-project.json"

# Fresh-install gate: never ambush a repo that never ran /core:start.
if [ -z "${SUTRA_DISCIPLINE_PRE_ACTIVATION:-}" ] && [ ! -f "$PROJECT_JSON" ]; then
  exit 0
fi

LEDGER="$REPO_ROOT/.enforcement/writing-style.jsonl"
mkdir -p "$(dirname "$LEDGER")" 2>/dev/null
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

STDIN_PAYLOAD=""
[ ! -t 0 ] && STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
SESSION_ID="${WRITING_STYLE_SESSION:-}"
TRANSCRIPT_PATH="${WRITING_STYLE_TRANSCRIPT:-}"
ACTIVE="false"
if command -v jq >/dev/null 2>&1 && [ -n "$STDIN_PAYLOAD" ]; then
  [ -z "$SESSION_ID" ] && SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)
  [ -z "$TRANSCRIPT_PATH" ] && TRANSCRIPT_PATH=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
  ACTIVE=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
fi
[ -z "$SESSION_ID" ] && SESSION_ID="${CLAUDE_CODE_SESSION_ID:-unknown}"
SESSION_DIR="$REPO_ROOT/.claude/sessions/$SESSION_ID"

log_row() { # decision reason [extra-json-fields]
  local d="$1" r="$2" extra="${3:-}"
  r=$(printf '%s' "$r" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g' | head -c 400)
  printf '{"ts":"%s","session_id":"%s","decision":"%s","reason":"%s"%s}\n' \
    "$NOW" "$SESSION_ID" "$d" "$r" "${extra:+,$extra}" >> "$LEDGER" 2>/dev/null
}

# Loop-breaker: one forced redo per turn, never re-judged.
if [ "$ACTIVE" = "true" ]; then log_row skipped stop_hook_active; exit 0; fi

# Per-turn audited override (Write-tool marker, never an env prefix).
if [ -f "$SESSION_DIR/writing-style-ack" ]; then
  log_row override "$(grep -m1 '^REASON=' "$SESSION_DIR/writing-style-ack" 2>/dev/null | cut -d= -f2- | head -c 300)"
  exit 0
fi

# Enforcement mode: fleet flag, then per-project opt-down unless pinned.
MODE="hard"; PINNED="0"; PROJECT=""
if command -v jq >/dev/null 2>&1; then
  MODE=$(jq -r '.output_discipline.writing_style.enforcement // "hard"' "$DEFAULTS" 2>/dev/null || echo hard)
  PROJECT=$(jq -r '.project_name // empty' "$PROJECT_JSON" 2>/dev/null)
  if [ -n "$PROJECT" ] && jq -e --arg p "$PROJECT" '.output_discipline.writing_style.pinned_hard_projects // [] | index($p)' "$DEFAULTS" >/dev/null 2>&1; then
    PINNED="1"
  fi
  if [ "$PINNED" = "0" ]; then
    OPT=$(jq -r '.writing_style // empty' "$PROJECT_JSON" 2>/dev/null)
    if [ "$OPT" = "advisory" ] || [ "$OPT" = "off" ]; then MODE="$OPT"; fi
  fi
fi
[ "$MODE" = "off" ] && { log_row skipped mode_off; exit 0; }

# Revoke scope (dotfile survives the per-turn marker wipe; session-scoped by design).
SCOPE="none"
[ -f "$SESSION_DIR/.writing-style-revoked" ] && SCOPE=$(grep -m1 '^SCOPE=' "$SESSION_DIR/.writing-style-revoked" 2>/dev/null | cut -d= -f2)
[ "$SCOPE" = "all" ] && MODE="advisory"
AUDIENCE="founder"
[ -f "$SESSION_DIR/writing-style-audience" ] && grep -q '^AUDIENCE=customer' "$SESSION_DIR/writing-style-audience" 2>/dev/null && AUDIENCE="customer"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then log_row skipped no_transcript; exit 0; fi
command -v python3 >/dev/null 2>&1 || { log_row skipped no_python3; exit 0; }

HARD_LINES=$(jq -r '.output_discipline.writing_style.turn_prose_hard // 60' "$DEFAULTS" 2>/dev/null || echo 60)
ADV_LINES=$(jq -r '.output_discipline.writing_style.turn_prose_advisory // 40' "$DEFAULTS" 2>/dev/null || echo 40)
OPENER_LINES=$(jq -r '.output_discipline.writing_style.outcome_lines // 5' "$DEFAULTS" 2>/dev/null || echo 5)

RESULT=$(WS_T="$TRANSCRIPT_PATH" WS_SKILL="$SKILL" WS_HARD="$HARD_LINES" WS_ADV="$ADV_LINES" WS_OPEN="$OPENER_LINES" \
         WS_SCOPE="$SCOPE" WS_AUD="$AUDIENCE" WS_PINNED="$PINNED" python3 - <<'PY' 2>/dev/null
import os, sys, json, re

T = os.environ["WS_T"]; SKILL = os.environ["WS_SKILL"]
HARD = int(os.environ["WS_HARD"]); ADV = int(os.environ["WS_ADV"]); OPEN = int(os.environ["WS_OPEN"])
SCOPE = os.environ["WS_SCOPE"]; AUD = os.environ["WS_AUD"]; PINNED = os.environ["WS_PINNED"] == "1"

def out(d): print(json.dumps(d)); sys.exit(0)

# ---- 1. current-turn assistant text ------------------------------------------
rows = []
try:
    with open(T) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except Exception: pass
except Exception:
    out({"skip": "unreadable_transcript"})

def is_human_user(r):
    if r.get("role") != "user" and r.get("type") != "user": return False
    if r.get("isMeta") is True: return False
    c = r.get("message", {}).get("content") or r.get("content")
    if isinstance(c, str): return True
    if isinstance(c, list):
        return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
    return False

last_user = -1; last_user_text = ""
for i, r in enumerate(rows):
    if is_human_user(r):
        last_user = i
        c = r.get("message", {}).get("content") or r.get("content")
        last_user_text = c if isinstance(c, str) else "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")

blocks = []; mutated = False
for r in rows[last_user + 1:]:
    if r.get("role") != "assistant" and r.get("type") != "assistant": continue
    c = r.get("message", {}).get("content") or r.get("content")
    if isinstance(c, str) and c.strip(): blocks.append(c)
    elif isinstance(c, list):
        for b in c:
            if not isinstance(b, dict): continue
            if b.get("type") == "text" and b.get("text", "").strip(): blocks.append(b["text"])
            elif b.get("type") == "tool_use" and b.get("name") in ("Edit", "Write", "MultiEdit", "NotebookEdit"): mutated = True
if not blocks:
    out({"skip": "unverifiable_flush_lag"})
full = "\n".join(blocks); final = blocks[-1]

# Deterministic audience classifier (codex P1, 2026-09-08): customer copy named in the ask.
if re.search(r"\b(prd|client|customer|email|support reply|regulated|copy for)\b", last_user_text, re.I):
    AUD = "customer"

# ---- 2. preprocessing ---------------------------------------------------------
FENCE = re.compile(r"(^|\n)(```|~~~).*?(\n\2[^\n]*|\Z)", re.S)
LABELS = (r"INPUT|TYPE|EXISTING HOME|ROUTE|FIT CHECK|ACTION|TASK|DEPTH|EFFORT|COST|IMPACT|TRIAGE|ESTIMATE|ACTUAL|"
          r"PLACEMENT|BUILD-LAYER|ACTIVATION-SCOPE|TARGET-PATH|WHY_NOT_L0_KIND|WHY_NOT_L0_REASON|PROMOTION|SOURCE|LAYER|SCOPE|OS|"
          r"SKILL|WHAT|WHY|EXPECT|ASKS|GRAIN|CLASS|FLOOR|TOUCHES|ATOM|Unit|Doing|Steps|Output looks like|Verified by( \(overall\))?|"
          r"Scale|Stops if|Switch|Verify|ADDED|RESTRUCTURED|SIMPLIFIED|DELETED|BY|OWNER|ACCEPTANCE-CRITERIA|STALE-DISPOSITION")
LABEL_RE = re.compile(r"^\s*(%s)\s*:" % LABELS)
BOX_EDGE = re.compile(r"^\s*\+[-=]{3,}.*$")
HEADER_RE = re.compile(r"^\s*\[(STAGE-1-FAIL|[A-Z0-9-]+·[A-Z0-9-]+)\b.*\]\s*$")
# A table separator row is pipes, colons, dashes and spaces only; "-- footnote" is prose.
SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
FIELD_MAX = 160          # a governance field is one line; a longer value is prose wearing a label
FIELD_FREE = 45          # a full block stack is ~35 fields; field lines past this count as prose
FIELD_QUOTE = {"INPUT"}  # paraphrases the user's words; never judged

def strip_fences(t): return FENCE.sub("\n", t)

def box_regions(t):
    keep = []; boxes = {}; inbox = False; title = None; n = 0
    for ln in t.split("\n"):
        if BOX_EDGE.match(ln):
            if not inbox:
                inbox = True; m = re.search(r"\+--\s*([A-Z-]+)", ln); title = m.group(1) if m else "BOX"; n = 0
            else:
                boxes[title] = boxes.get(title, 0) + n; inbox = False
            continue
        if inbox: n += 1; continue
        keep.append(ln)
    return "\n".join(keep), boxes

def preprocess(t):
    # -> (match_text, counted_lines, boxes). Lines are counted BEFORE inline code and
    # quoted spans are blanked, so a fully quoted line is still a line. Governance field
    # values are judged by unanchored rows only (the "= " prefix defeats ^ and sentence
    # anchors; codex P1 2026-09-11) and are not counted unless over FIELD_MAX chars or
    # past the FIELD_FREE-th field of the turn.
    t = strip_fences(t)
    t, boxes = box_regions(t)
    match = []; counted = []; fields = 0
    for ln in t.split("\n"):
        if HEADER_RE.match(ln) or re.match(r"^\s*>", ln) or SEP_RE.match(ln): continue
        m = LABEL_RE.match(ln)
        if m:
            val = ln[m.end():].strip(); fields += 1
            if m.group(1) not in FIELD_QUOTE: match.append("= " + val)
            if len(val) > FIELD_MAX or fields > FIELD_FREE: counted.append(val.lower())
            continue
        match.append(ln)
        if ln.strip(): counted.append(ln.lower())
    mt = "\n".join(match)
    mt = re.sub(r"`[^`\n]+`", " ", mt)
    mt = re.sub(r"\"[^\"\n]{1,200}\"", " ", mt)
    mt = re.sub(r"“[^”\n]{1,200}”", " ", mt)
    return mt.lower(), counted, boxes

prose, prose_lines, boxes = preprocess(full)
final_prose, _, _ = preprocess(final)
n_lines = len(prose_lines)

# ---- 3. banned list from the skill (single source) ----------------------------
rules = []; banned_status = "ok"
try:
    s = open(SKILL, encoding="utf-8").read()
    m = re.search(r"<!-- banned:start -->(.*?)<!-- banned:end -->", s, re.S)
    if not m: banned_status = "no_banned_list"
    else:
        for ln in m.group(1).split("\n"):
            p = ln.split(None, 2)
            if len(p) < 3 or p[1] not in ("H", "A"): continue
            try: rules.append((p[0], p[1], re.compile(p[2], re.I | re.M)))
            except re.error: banned_status = "bad_regex:" + p[0]
except Exception:
    banned_status = "no_skill_file"

hard = []; adv = []
def snip(m, text):
    a = max(0, m.start() - 25); b = min(len(text), m.end() + 25)
    return text[a:b].replace("\n", " ").strip()[:120]

def paragraph(text, pos):
    a = text.rfind("\n\n", 0, pos); a = 0 if a < 0 else a
    b = text.find("\n\n", pos); b = len(text) if b < 0 else b
    return text[a:b]

SKIP = set()
if SCOPE == "compress": SKIP |= {"FILLER", "PLEASANT", "HEDGE"}
if SCOPE == "candor":   SKIP |= {"GLAZE", "APOLOGY"}
SOFT = {"GLAZE", "APOLOGY", "PLEASANT", "CLOSER"} if AUD == "customer" else set()
FINAL_ONLY = {"NARRATE", "ECHO"}

for group, sev, rx in rules:
    if group in SKIP: continue
    text = final_prose if group in FINAL_ONLY else prose
    ms = list(rx.finditer(text))
    if not ms: continue
    if group == "FILLER" and len(ms) <= 3: continue
    if group == "HEDGE":
        ms = [m for m in ms if "confidence:" not in paragraph(text, m.start())]
        if not ms: continue
    if group == "ASKRUN": sev = "H" if PINNED else "A"
    if group in SOFT: sev = "A"
    row = {"id": "WS-1" if sev == "H" else "WS-A", "group": group, "snippet": snip(ms[0], text)}
    (hard if sev == "H" else adv).append(row)

# ---- 4. structural checks -----------------------------------------------------
# box-drawing + block + geometric (U+2500-25FF), braille (U+2800-28FF), symbols + arrows (U+2B00-2BFF)
m = re.search(r"[─-◿⠀-⣿⬀-⯿]", prose)
if m: hard.append({"id": "WS-2", "group": "GLYPH", "snippet": snip(m, prose)})

if SCOPE != "minimize":
    if n_lines > HARD: hard.append({"id": "WS-3", "group": "BUDGET", "snippet": "prose %d lines > %d" % (n_lines, HARD)})
    elif n_lines > ADV: adv.append({"id": "WS-A1", "group": "BUDGET", "snippet": "prose %d lines > %d" % (n_lines, ADV)})
    opener = 0
    for l in prose_lines:
        if re.match(r"^\s*(\||#)", l) or "|" in l: break
        opener += 1
    if opener > OPEN and n_lines > OPEN: adv.append({"id": "WS-A2", "group": "OPENER", "snippet": "%d prose lines before first structure" % opener})
    if mutated and n_lines > 25: adv.append({"id": "WS-A9", "group": "RESTATE", "snippet": "file written and %d prose lines" % n_lines})

# WS-4 task tables (fence-stripped original, case-insensitive; GFM rows need no outer pipes)
src = strip_fences(full).split("\n")
i = 0
while i < len(src) - 1:
    h = src[i]; sep = src[i + 1]
    if "|" in h and not SEP_RE.match(h) and SEP_RE.match(sep):
        body = 0; j = i + 2
        while j < len(src) and "|" in src[j] and not SEP_RE.match(src[j]): body += 1; j += 1
        hl = h.lower()
        if body >= 3 and re.search(r"\b(task|recommend|next step|backlog|roadmap|fix)\b", hl) and ("impact" not in hl or "effort" not in hl):
            hard.append({"id": "WS-4", "group": "TASK-TABLE", "snippet": h.strip()[:120]})
        i = j
    else:
        i += 1

# advisory-only heuristics
for title, cap in (("FLOW", 9), ("BLUEPRINT", 16), ("DISPATCH", 9)):
    if boxes.get(title, 0) > cap: adv.append({"id": "WS-A5", "group": "PADDING", "snippet": "%s box %d lines > %d" % (title, boxes[title], cap)})
run = 0
for l in prose_lines:
    run = run + 1 if re.match(r"^\s*(-\s*)?\[x\]|^\s*(-\s*)?(done|ok)\b", l) else 0
    if run > 5: adv.append({"id": "WS-A6", "group": "EXHAUSTIVE", "snippet": "6+ consecutive done markers"}); break
if sum(1 for l in prose_lines if l.startswith("#")) > 3: adv.append({"id": "WS-A6", "group": "EXHAUSTIVE", "snippet": "4+ headings in a chat turn"})
if not re.search(r"\bhtml\b", last_user_text, re.I) and re.search(r"<!doctype\s+html>|<html[\s>]|<body[\s>]", prose): adv.append({"id": "WS-A8", "group": "HTML", "snippet": "html without request"})
if re.search(r"^\s*(decision|recommendation|recommend)\s*:", prose, re.M): adv.append({"id": "WS-A12", "group": "UNBOXED", "snippet": "decision line outside a box"})

out({"hard": hard, "adv": adv, "lines": n_lines, "banned": banned_status, "audience": AUD})
PY
)

[ -z "$RESULT" ] && { log_row skipped python_failed; exit 0; }
SKIP=$(printf '%s' "$RESULT" | jq -r '.skip // empty' 2>/dev/null)
[ -n "$SKIP" ] && { log_row skipped "$SKIP"; exit 0; }

HARD_N=$(printf '%s' "$RESULT" | jq -r '.hard | length' 2>/dev/null || echo 0)
ADV_N=$(printf '%s' "$RESULT" | jq -r '.adv | length' 2>/dev/null || echo 0)
LINES=$(printf '%s' "$RESULT" | jq -r '.lines' 2>/dev/null)
BANNED=$(printf '%s' "$RESULT" | jq -r '.banned' 2>/dev/null)
AUD_OUT=$(printf '%s' "$RESULT" | jq -r '.audience' 2>/dev/null)
CHECKS=$(printf '%s' "$RESULT" | jq -c '{hard: [.hard[] | .id + ":" + .group], adv: [.adv[] | .id + ":" + .group]}' 2>/dev/null)
EXTRA="\"lines\":${LINES:-0},\"banned\":\"${BANNED}\",\"scope\":\"${SCOPE}\",\"mode\":\"${MODE}\",\"audience\":\"${AUD_OUT}\",\"checks\":${CHECKS:-null}"

[ "$BANNED" != "ok" ] && log_row note "$BANNED" "$EXTRA"

if [ "${HARD_N:-0}" = "0" ] || [ "$MODE" = "advisory" ]; then
  if [ "${HARD_N:-0}" != "0" ]; then log_row advisory "hard_in_advisory_mode" "$EXTRA"
  elif [ "${ADV_N:-0}" != "0" ]; then log_row advisory "advisory_only" "$EXTRA"
  else log_row pass "clean" "$EXTRA"; fi
  exit 0
fi

# ---- HARD block: one redo, self-compliant reason (<=12 ASCII lines) -------------
log_row block "hard" "$EXTRA"
FINDINGS=$(printf '%s' "$RESULT" | jq -r '.hard[] | "  - " + .id + " " + .group + ": \"" + (.snippet | gsub("[^ -~]"; "?")) + "\""' 2>/dev/null | head -5)
FINDINGS_ESC=$(printf '%s' "$FINDINGS" | sed 's/\\/\\\\/g; s/"/\\"/g' | awk '{printf "%s\\n", $0}')
cat <<JSON
{
  "decision": "block",
  "reason": "WRITING-STYLE GATE (core:writing-style, HARD).\nBlocked checks:\n${FINDINGS_ESC}Fix: outcome first, cut the phrase or glyph, move detail to a file (M7), add Impact + Effort columns.\nRules: skills/writing-style/SKILL.md sections 3-5.\nOverride (audited): write .claude/sessions/<sid>/writing-style-ack with a REASON= line.\nRevoke phrases (whole line): normal mode | stop anti-glaze | long form | stop writing-style."
}
JSON
exit 0
