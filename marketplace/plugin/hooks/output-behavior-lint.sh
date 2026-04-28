#!/usr/bin/env bash
# Sutra OS — Output Behavior Lint (Stop event)
# Scans the last N assistant turns in the transcript for behavioral-rule
# violations that can't be hook-enforced at tool-call time.
#
# Rules audited (memory feedback, 2026-04-22 directions audit Part 2):
#   1. "Never ask to run" — flag "please run", "can you run", "could you run",
#      "try running" in assistant text blocks (outside code fences).
#   2. "No HTML unless asked" — flag `<!DOCTYPE html>` / `<html>` / `<body>`
#      in assistant text when the last user message didn't request HTML.
#
# Findings are written to .enforcement/routing-misses.log as JSON rows.
# Advisory only: always exits 0, never blocks, never emits to stdout.
#
# Wired from: holding/hooks/dispatcher-stop.sh section 16.
# Also invokable directly for tests.
#
# Env overrides (test hooks):
#   OUTPUT_LINT_TRANSCRIPT=/path/to/transcript.jsonl
#   OUTPUT_LINT_LOG=/path/to/routing-misses.log
#   OUTPUT_LINT_SCAN_TURNS=3
# ───────────────────────────────────────────────────────────────────────────────

set -o pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LOG_FILE="${OUTPUT_LINT_LOG:-$REPO_ROOT/.enforcement/routing-misses.log}"
SCAN_TURNS="${OUTPUT_LINT_SCAN_TURNS:-3}"

# ─── 1. Locate transcript ─────────────────────────────────────────────────────
TRANSCRIPT_PATH=""

if [ -n "${OUTPUT_LINT_TRANSCRIPT:-}" ] && [ -f "${OUTPUT_LINT_TRANSCRIPT}" ]; then
  TRANSCRIPT_PATH="$OUTPUT_LINT_TRANSCRIPT"
fi

if [ -z "$TRANSCRIPT_PATH" ] && [ ! -t 0 ]; then
  STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
  if [ -n "$STDIN_PAYLOAD" ]; then
    CANDIDATE=$(printf '%s' "$STDIN_PAYLOAD" | \
      sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    if [ -n "$CANDIDATE" ] && [ -f "$CANDIDATE" ]; then
      TRANSCRIPT_PATH="$CANDIDATE"
    fi
  fi
fi

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# ─── 2. Python helper — extract text + scan ──────────────────────────────────
command -v python3 >/dev/null 2>&1 || exit 0

FINDINGS=$(python3 - "$TRANSCRIPT_PATH" "$SCAN_TURNS" <<'PYEOF' 2>/dev/null
import json, sys, re, time

path = sys.argv[1]
scan_turns = int(sys.argv[2])

# Collect last N assistant turns + the last user turn they follow.
rows = []
try:
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") in ("assistant", "user"):
                rows.append(d)
except Exception:
    sys.exit(0)

assistant_rows = [r for r in rows if r.get("type") == "assistant"][-scan_turns:]

# Find the last user message preceding the first assistant in the scan window,
# to judge whether HTML was explicitly requested.
last_user_text = ""
if assistant_rows:
    first_asst_uuid = assistant_rows[0].get("uuid")
    for r in rows:
        if r.get("type") == "user":
            last_user_text_candidate = ""
            msg = r.get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                last_user_text_candidate = content
            elif isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        parts.append(c.get("text") or "")
                last_user_text_candidate = "\n".join(parts)
            last_user_text = last_user_text_candidate
        if r.get("uuid") == first_asst_uuid:
            break

html_requested = bool(re.search(r"\bhtml\b", last_user_text, re.IGNORECASE))

def strip_fences(text):
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)

def extract_text(asst):
    msg = asst.get("message") or {}
    content = msg.get("content")
    parts = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text") or "")
    return "\n".join(parts)

findings = []
ask_to_run_pattern = re.compile(
    r"\b(please|can you|could you|would you|try)\s+run(ning)?\b",
    re.IGNORECASE
)
html_pattern = re.compile(
    r"(<!DOCTYPE\s+html>|<html[\s>]|<body[\s>])",
    re.IGNORECASE
)

for asst in assistant_rows:
    text = strip_fences(extract_text(asst))
    if not text.strip():
        continue
    turn_ts = asst.get("timestamp") or ""
    turn_uuid = asst.get("uuid") or ""

    for m in ask_to_run_pattern.finditer(text):
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 40)
        findings.append({
            "rule": "never-ask-to-run",
            "snippet": text[start:end].strip()[:200],
            "turn": turn_uuid[:12],
            "ts": turn_ts,
        })

    if not html_requested:
        for m in html_pattern.finditer(text):
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 80)
            findings.append({
                "rule": "no-html-unless-asked",
                "snippet": text[start:end].strip()[:200],
                "turn": turn_uuid[:12],
                "ts": turn_ts,
            })

for f in findings:
    print(json.dumps(f))
PYEOF
)

# ─── 3. Append findings to routing-misses.log ────────────────────────────────
if [ -z "$FINDINGS" ]; then
  exit 0
fi

mkdir -p "$(dirname "$LOG_FILE")"
NOW_EPOCH=$(date +%s)

while IFS= read -r FINDING; do
  [ -z "$FINDING" ] && continue
  # Wrap with outer event envelope the rest of the enforcement log uses.
  RULE=$(printf '%s' "$FINDING" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["rule"])' 2>/dev/null)
  SNIPPET=$(printf '%s' "$FINDING" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d.get("snippet","").replace("\\","\\\\").replace("\"","\\\""))' 2>/dev/null)
  TURN=$(printf '%s' "$FINDING" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("turn",""))' 2>/dev/null)
  printf '{"ts":%s,"event":"output-behavior-lint","rule":"%s","turn":"%s","snippet":"%s"}\n' \
    "$NOW_EPOCH" "$RULE" "$TURN" "$SNIPPET" >> "$LOG_FILE"
done <<< "$FINDINGS"

exit 0

## Operationalization
#
### 1. Measurement mechanism
# Findings count per rule in .enforcement/routing-misses.log.
# Target: downward trend as behavioral drift is caught earlier.
#
### 2. Adoption mechanism
# Registered in .claude/settings.json Stop via dispatcher-stop.sh §16.
#
### 3. Monitoring / escalation
# Weekly: grep rule=never-ask-to-run or rule=no-html-unless-asked in
# routing-misses.log; if count rises >3/week for either rule, tune patterns
# or elevate to a PreToolUse gate.
#
### 4. Iteration trigger
# Revise when: false-positive rate exceeds 20% (pattern needs refinement),
# or a new behavioral rule is added to memory feedback.
#
### 5. DRI
# CEO of Asawa (memory feedback rules owner).
#
### 6. Decommission criteria
# Retire when: rule shipped to Sutra plugin as BASE check (DIRECTIONS-ENGINE
# resumed) AND zero findings for 30 consecutive days.
