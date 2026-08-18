#!/usr/bin/env bash
# balance-observe.sh — Balance observe loop v2: HUMAN BEHAVIOR register.
#
# Founder ruling 2026-08-07 (approved via chat samples): insights speak about
# the FOUNDER — time, tempo, corrections — in plain human language. Rule #1:
# only HUMAN conversations count; machine prompts (cron runners, task
# notifications, hook echoes) are filtered out — the 6:15am-robot lesson.
# Card framework (the template, every run): time · energy · awareness ·
# understanding · actionable · custom — emitted only when evidence supports
# them, never padded. Energy = behavior tempo, never emotion (codex).
# Card text is plain language; backing metrics stay in `signals` for audit.
# OBSERVE-ONLY per BQ-2: action_taken=SILENT-BASELINE always.
# Kill-switch: ~/.balance-disabled. Design: holding/plans/insights-balance/DESIGN.md.
set -euo pipefail
[ -f "$HOME/.balance-disabled" ] && exit 0
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="$ROOT/holding/state/balance"; mkdir -p "$STATE_DIR"
STATE_DIR="${SUTRA_BALANCE_STATE_DIR:-${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.sutra/balance}}"
STATE_DIR="${STATE_DIR:-$ROOT/holding/state/balance}"
mkdir -p "$STATE_DIR" 2>/dev/null || true
export ROOT STATE="$STATE_DIR/balance-state.json" LOG="$STATE_DIR/balance-log.jsonl"
export NOW_EPOCH=$(date +%s)

/usr/bin/python3 <<'PY'
import json, os, time, calendar, tempfile, statistics

root = os.environ["ROOT"]; now = int(os.environ["NOW_EPOCH"])
lt = time.localtime(now)
day_start = int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))

MACHINE = ("<task-notification>", "You are the", "PLACEMENT:", "Base directory for this skill",
           "<local-command", "Stop hook feedback", "Daily governance-findings triage")
CORRECTIVE = ("not what", "i meant", "that's wrong", "this is wrong", "fix that",
              "don't see", "not working", "not opening")

prompts_path = os.path.join(root, time.strftime("holding/state/prompts/%Y-%m.jsonl", lt))
rows = []
try:
    for line in open(prompts_path):
        try: r = json.loads(line)
        except ValueError: continue
        ts = r.get("ts", "")
        try: ep = calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError: continue
        if ep < day_start or ep > now: continue
        p = (r.get("prompt") or "").strip()
        if not p or any(p.startswith(m) or m in p[:120] for m in MACHINE): continue
        rows.append((ep, r.get("session_id", "?"), p))
except OSError:
    pass
rows.sort()

cards, signals = [], {}
late_night_rows = []
if rows:
    # Sleep-boundary day model (founder correction 2026-08-07): midnight is not
    # the human day boundary. Work-day start = first message after the last gap
    # >= 5h, or >= 3h when the wake lands in the 6:00-11:59 morning band (codex:
    # a 3h nap ending at 5am is not a new day). No qualifying gap -> the span
    # keeps its overnight start honestly; pre-sleep rows become a custom card.
    boundary = 0
    for i in range(len(rows) - 1):
        gap_h = (rows[i+1][0] - rows[i][0]) / 3600
        wake_h = time.localtime(rows[i+1][0]).tm_hour
        if gap_h >= 5 or (gap_h >= 3 and 6 <= wake_h < 12):
            boundary = i + 1
    late_night_rows = rows[:boundary]
    rows = rows[boundary:]
if rows:
    first, last = rows[0][0], rows[-1][0]
    hours = (last - first) / 3600
    gaps = [(rows[i+1][0] - rows[i][0]) / 60 for i in range(len(rows) - 1)]
    med_gap = round(statistics.median(gaps), 1) if gaps else None
    breaks = [g for g in gaps if g > 30]
    sessions = len({s for _, s, _ in rows})
    recent = [r for r in rows if r[0] >= now - 7200]
    day_rate = len(rows) / max(hours, 0.5)
    recent_rate = len(recent) / 2.0
    corrections = sum(1 for _, _, p in rows if any(c in p.lower() for c in CORRECTIVE))
    late = lt.tm_hour >= 23 or lt.tm_hour < 6

    signals = {"human_asks": len(rows), "start_epoch": first, "active_hours": round(hours, 1),
               "median_gap_min": med_gap, "breaks_over_30min": len(breaks), "sessions": sessions,
               "asks_last_2h": len(recent), "day_rate_per_h": round(day_rate, 1),
               "recent_rate_per_h": round(recent_rate, 1), "correction_phrase_count": corrections,
               "late_night": late}

    fmt = lambda e: time.strftime("%-I:%M %p", time.localtime(e)).lower()
    btxt = ("no real break yet" if not breaks else
            f"{len(breaks)} break{'s' if len(breaks) > 1 else ''} over 30 minutes")
    cards.append({"kind": "time",
        "text": f"You started around {fmt(first)} and have been at it about "
                f"{round(hours,1)} hours — {len(rows)} messages from you, {btxt}."})

    if recent_rate > day_rate * 1.5 and len(recent) >= 6:
        etxt = "Your pace picked up in the last two hours — messages are coming faster than your day's average."
    elif recent_rate < day_rate * 0.5:
        etxt = "Your pace has eased off in the last two hours compared to earlier."
    else:
        etxt = "Your pace has been fairly even through the day."
    if late: etxt += " It's late — worth noticing, not judging."
    cards.append({"kind": "energy", "text": etxt + " (Read from message timing, not from you.)"})

    if sessions > 1:
        cards.append({"kind": "awareness",
            "text": f"You ran {sessions} parallel conversations today; most messages came within "
                    f"{med_gap} minutes of the previous reply."})
    if corrections >= 3:
        cards.append({"kind": "understanding",
            "text": "There were a few course corrections today — moments where the result wasn't "
                    "what you pictured. Your clearest direction tends to come after seeing something concrete."})
    if hours >= 8 and not breaks:
        cards.append({"kind": "actionable",
            "text": f"About {round(hours)} hours without a real break. Worth considering: a short one "
                    "before the next push."})
    if late_night_rows:
        until = time.strftime("%-I:%M %p", time.localtime(late_night_rows[-1][0])).lower()
        away = round((rows[0][0] - late_night_rows[-1][0]) / 3600)
        cards.append({"kind": "custom",
            "text": f"You were still working at {until} last night — {len(late_night_rows)} messages "
                    f"after midnight, then about {away} hours away before today started."})
else:
    cards.append({"kind": "time", "text": "Nothing from you yet today — nothing to report."})

# Pinned cards (founder-authored coach content) survive regeneration:
# pinned-cards.json next to the state file, sanitized + capped at ingestion
# (dual-lane consult 2026-08-17). Pins render in STATE only, never the
# append-only log — the log is the observation record; pins are not
# observations, and logging them would re-append the same bytes every tick.
pinned = []
try:
    pin_path = os.path.join(os.path.dirname(os.path.abspath(os.environ["STATE"])),
                            "pinned-cards.json")
    if os.path.getsize(pin_path) <= 16384:
        with open(pin_path) as f:
            pins = json.load(f)
        pinned = [{"kind": str(c.get("kind") or "custom")[:40],
                   "text": c["text"].strip()[:400]}
                  for c in pins
                  if isinstance(c, dict) and isinstance(c.get("text"), str)
                  and c["text"].strip()][:8]
except (OSError, ValueError):
    pass

obs = {"schema_version": 2, "observation_id": f"obs-{now}",
       "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "epoch": now,
       "register": "human-behavior v1 (approved 2026-08-07); machine prompts filtered",
       "signals": signals, "cards": cards + pinned,
       "recommended_action": "none-baseline", "action_taken": "SILENT-BASELINE",
       "mode": "observe-only (BQ-2 baseline)"}
log_obs = dict(obs, cards=cards)

fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.environ["STATE"]))
with os.fdopen(fd, "w") as f: json.dump(obs, f, indent=1)
os.replace(tmp, os.environ["STATE"])
with open(os.environ["LOG"], "a") as f: f.write(json.dumps(log_obs) + "\n")
print(f"balance-observe v2: {obs['observation_id']} cards={[c['kind'] for c in cards]}")
PY
