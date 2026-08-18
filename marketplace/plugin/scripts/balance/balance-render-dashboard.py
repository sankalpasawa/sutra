#!/usr/bin/env python3
"""Balance dashboard generator (plugin port, PLAN-25 step 20) — regenerates roles-dashboard.html with
TODAY | THIS WEEK | MONTH tabs from data on disk. Fully deterministic render;
all dynamic strings pass through html.escape; atomic write. Consult folds
2026-08-18: build-time authored markup, inert data, overflow wrappers,
aria labels, provenance footer.
"""
import json, os, subprocess, tempfile, time
from html import escape as esc

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# Same validated env override as the coach pass (consult fold: both scripts).
_ENV_BAL = os.environ.get("SUTRA_BALANCE_STATE_DIR", "")
_PROJ = os.environ.get("CLAUDE_PROJECT_DIR", "")
_CANDIDATES = [_ENV_BAL,
               os.path.join(_PROJ, ".sutra", "balance") if _PROJ else "",
               os.path.join(REPO, "holding", "state", "balance")]
BAL = next(c for c in _CANDIDATES if c and os.path.isabs(c) and os.path.isdir(c))
OUT = os.path.join(BAL, "roles-dashboard.html")
NOW = int(time.time())
TODAY = time.strftime("%Y-%m-%d", time.localtime(NOW))


def jload(name, default):
    try:
        with open(os.path.join(BAL, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def jrows(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("{"):
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    except OSError:
        return


def git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                              text=True, timeout=30).stdout
    except Exception:
        return ""


def bucket(path):
    if "sutra-ui" in path:
        return "Platform"
    if "hook" in path or "enforcement" in path or "dispatch" in path or "observability" in path:
        return "Governance"
    if path.startswith(("holding/plans", "holding/research", "os/native", "holding/departments")) or "native" in path:
        return "Architect"
    if "website" in path:
        return "Publisher"
    if any(s in path for s in ("marketplace", "skills", "bin", "lib", "tests")):
        return "Platform"
    return None


def collect():
    days = [time.strftime("%Y-%m-%d", time.localtime(NOW - i * 86400)) for i in range(29, -1, -1)]
    matrix = {r: {d: 0 for d in days} for r in ("Platform", "Governance", "Architect", "Publisher", "Portfolio")}
    hours = [0] * 24
    commits_by_day, subjects = {d: 0 for d in days}, []
    for repo in (REPO, os.path.join(REPO, "sutra")):
        day = None
        for line in git(repo, "log", "--since=30 days ago", "--pretty=format:@%ad|%H|%s",
                        "--date=format:%Y-%m-%d %H", "--name-only").splitlines():
            if line.startswith("@"):
                head = line[1:].split("|", 2)
                d, h = head[0].split(" ")
                day = d if d in matrix["Platform"] else None
                if day:
                    hours[int(h)] += 1
                    commits_by_day[day] += 1
                    subjects.append((d, head[2] if len(head) > 2 else ""))
            elif line.strip() and day:
                b = bucket(line.strip())
                if b:
                    matrix[b][day] += 1
    return days, matrix, hours, commits_by_day, subjects


CSS = """
/* app-tokens: sutra-ui — baked verbatim from sutra/marketplace/plugin/sutra-ui/static/panel.css
   (dark-first three-state pattern, same selectors). Heatmap ramp derived from --acc copper with
   deliberate lightness steps per mode (consult fold 2026-08-18). */
:root{--serif:ui-serif,"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
:root,[data-theme="dark"]{--paper:#0C0B09;--card:#1C1A17;--line:#2A2622;
--ink:#F5F0E8;--muted:#8C857D;--faint:#6E6860;
--acc:#C4956A;--amber:#C9A227;--ok:#5A9E6F;--block:#B8574B;--chip-low:#6E6860;
--h0:#262119;--h1:#4A3722;--h2:#7A5836;--h3:#A87B4E;--h4:#D9AC7C;
--shadow:0 1px 2px rgba(0,0,0,.16),0 18px 44px -18px rgba(0,0,0,.42)}
@media (prefers-color-scheme:light){:root:not([data-theme]){--paper:#fafaf9;--card:#ffffff;--line:#e2e0dd;
--ink:#1c1917;--muted:#78716c;--faint:#a8a29e;
--acc:#8A5D2E;--amber:#8a6d12;--ok:#3f7d54;--block:#9c3f34;--chip-low:#a8a29e;
--h0:#F3EBE1;--h1:#E4CDB2;--h2:#C4956A;--h3:#96683B;--h4:#5E3F20;
--shadow:0 1px 2px rgba(28,25,23,.05),0 18px 44px -20px rgba(28,25,23,.16)}}
[data-theme="light"]{--paper:#fafaf9;--card:#ffffff;--line:#e2e0dd;
--ink:#1c1917;--muted:#78716c;--faint:#a8a29e;
--acc:#8A5D2E;--amber:#8a6d12;--ok:#3f7d54;--block:#9c3f34;--chip-low:#a8a29e;
--h0:#F3EBE1;--h1:#E4CDB2;--h2:#C4956A;--h3:#96683B;--h4:#5E3F20;
--shadow:0 1px 2px rgba(28,25,23,.05),0 18px 44px -20px rgba(28,25,23,.16)}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);
padding:30px clamp(16px,4vw,52px) 60px}
.wrap{max-width:1040px;margin:0 auto}
.eyebrow{font:600 10.5px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
h1{font-family:var(--serif);font-size:clamp(28px,4vw,38px);
font-weight:600;letter-spacing:-.015em;margin:8px 0 14px;text-wrap:balance}
.tabs{display:flex;gap:8px;margin:14px 0 26px;flex-wrap:wrap}
.tabs button{font:600 12px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
background:var(--card);border:1px solid var(--line);border-radius:99px;padding:9px 18px;cursor:pointer}
.tabs button[aria-selected="true"]{color:var(--paper);background:var(--acc);border-color:var(--acc)}
section[data-tab]{display:none}section[data-tab].on{display:block}
h2{font-family:var(--serif);font-size:20px;font-weight:600;margin:30px 0 4px}
.sub{font-size:12.5px;color:var(--muted);margin:0 0 12px;max-width:70ch}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:8px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:13px 15px;box-shadow:var(--shadow)}
.tile b{display:block;font:600 24px/1.1 var(--serif);font-variant-numeric:tabular-nums;color:var(--acc)}
.tile span{font-size:11px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 17px;box-shadow:var(--shadow);margin-bottom:12px}
.act{display:flex;gap:12px;align-items:flex-start;border-left:3px solid var(--amber);border-radius:10px;
background:var(--card);border-top:1px solid var(--line);border-right:1px solid var(--line);border-bottom:1px solid var(--line);
padding:12px 14px;margin-bottom:9px}
.act.done{border-left-color:var(--acc);opacity:.75}
.act.esc{border-left-color:var(--block)}
.chip.esc{color:var(--block)}
.act .mark{font:700 13px/1 var(--mono);color:var(--acc);margin-top:2px}
.act .body{flex:1;font-size:13px}
.act .meta{font:10px var(--mono);color:var(--faint);margin-top:4px}
.chip{font:600 9px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;border:1px solid currentColor;
border-radius:99px;padding:3px 8px;white-space:nowrap}
.chip.open{color:var(--amber)}.chip.done{color:var(--acc)}
ul.plain{margin:4px 0;padding-left:18px;font-size:13px}ul.plain li{margin-bottom:3px}
.hm-wrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 17px;box-shadow:var(--shadow)}
.hm{min-width:640px}
.hm-row{display:grid;grid-template-columns:100px repeat(30,minmax(12px,1fr));gap:2px;margin-bottom:2px;align-items:center}
.hm-label{font:600 9.5px/1.2 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.hm-cell{height:15px;border-radius:3px;background:var(--h0)}
.hm-cell:focus{outline:2px solid var(--acc);outline-offset:1px}
.hm-dates{display:grid;grid-template-columns:100px repeat(30,minmax(12px,1fr));gap:2px;margin-top:5px}
.hm-dates span{font:8.5px var(--mono);color:var(--faint);text-align:center}
.legend{display:flex;gap:12px;align-items:center;margin-top:10px;font-size:10px;color:var(--muted)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:4px;vertical-align:-2px}
.bars{display:grid;grid-auto-flow:column;gap:2px;align-items:end;height:52px}
.bars div{background:var(--h2);border-radius:2px 2px 0 0;min-height:2px}
.bars div.hot{background:var(--amber)}
.role{border-left:3px solid var(--acc)}
.role h3{font-family:var(--serif);font-size:16.5px;margin:0 0 6px;font-weight:600}
.role h4{font:600 9.5px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;margin:8px 0 2px}
.role h4.g{color:var(--acc)}.role h4.s{color:var(--amber)}
.role .evi{font-size:10.5px;color:var(--faint)}
.ship{font-size:13px;margin-bottom:7px}
.ship time{font:600 10px var(--mono);color:var(--muted);margin-right:8px}
.foot{margin-top:28px;font:10px var(--mono);color:var(--faint)}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
"""


def step(n):
    return "--h0" if n == 0 else "--h1" if n < 10 else "--h2" if n < 50 else "--h3" if n < 200 else "--h4"


def render():
    days, matrix, hours, commits_by_day, subjects = collect()
    review = jload("roles-review.json", {})
    derived = jload("actionables.json", {"actionables": []})
    acts = derived.get("actionables", [])
    week_days = days[-7:]
    today_subj = [s for d, s in subjects if d == TODAY and not s.startswith("Merge")][:10]
    week_subj = [(d, s) for d, s in subjects
                 if d in week_days and (s.startswith(("feat", "release", "balance")) or "ship" in s.lower())][:12]
    n_windows = sum(1 for r in jrows(os.path.join(BAL, "balance-log.jsonl"))
                    if time.strftime("%Y-%m-%d", time.localtime(r.get("epoch", 0))) == TODAY)
    all_insights = [r for r in jrows(os.path.join(BAL, "insights.jsonl"))
                    if not (r.get("expiry") and str(r["expiry"]) < TODAY)]
    insights = [r for r in all_insights if r.get("kind") != "week"][-5:]
    week_insight = next((r for r in reversed(all_insights) if r.get("kind") == "week"), None)
    open_acts = [a for a in acts if a.get("status") == "open"]
    done_acts = [a for a in acts if a.get("status") == "done"]
    active_acts = [a for a in open_acts if a.get("active")]
    parked_acts = [a for a in open_acts if not a.get("active")]
    warnings = derived.get("profile_warnings", [])

    def act_html(a):
        done = a.get("status") == "done"
        escd = bool(a.get("escalated")) and not done
        mark = "[x]" if done else "[ ]"
        if done:
            meta = f"closed by {esc(str(a.get('closed_by','')))}"
        else:
            meta = f"open {a.get('days_open',0)}d"
            if a.get("movements"):
                meta += f" · {a['movements']} progress note{'s' if a['movements']!=1 else ''}"
                if a.get("last_movement"):
                    md = max(0, int((time.time() - a["last_movement"]) / 86400))
                    meta += f" · last movement {md}d ago"
            if escd:
                meta += f" · RECURRING — stalled {a.get('stalled_days',0)}d"
        cls = " done" if done else (" esc" if escd else "")
        chip_cls = "done" if done else ("esc" if escd else "open")
        chip = f'<span class="chip {chip_cls}">{ "done" if done else esc(a.get("role","")[:18]) }</span>'
        return (f'<div class="act{cls}"><span class="mark">{mark}</span>'
                f'<span class="body">{esc(a.get("text",""))}'
                f'<div class="meta">{meta}</div></span>{chip}</div>')

    def heat_rows():
        out = []
        for role in ("Platform", "Governance", "Architect", "Publisher", "Portfolio"):
            cells = []
            for d in days:
                n = matrix[role][d]
                t = f"{role}, {d}: {n} file-touches"
                cells.append(f'<div class="hm-cell" tabindex="0" style="background:var({step(n)})" '
                             f'title="{esc(t)}" aria-label="{esc(t)}"></div>')
            out.append(f'<div class="hm-row"><div class="hm-label">{role}</div>{"".join(cells)}</div>')
        dates = ['<span></span>'] + [f'<span>{d[5:] if i % 7 == 0 or i == 29 else ""}</span>'
                                     for i, d in enumerate(days)]
        out.append(f'<div class="hm-dates">{"".join(dates)}</div>')
        return "".join(out)

    def bars(vals, hot=lambda i: False, label=lambda i: str(i)):
        mx = max(vals) or 1
        out = []
        for i, v in enumerate(vals):
            h = 2 if v == 0 else round(4 + v / mx * 46)
            cls = ' class="hot"' if hot(i) else ""
            t = esc(f"{label(i)}: {v}")
            out.append(f'<div style="height:{h}px"{cls} title="{t}" aria-label="{t}"></div>')
        return "".join(out)

    roles_html = ""
    for r in review.get("roles", []):
        roles_html += (f'<div class="card role"><h3>{esc(r.get("role",""))}</h3>'
                       f'<div class="evi">{esc(r.get("evidence",""))} · confidence: {esc(r.get("confidence",""))}</div>'
                       f'<h4 class="g">What&rsquo;s working</h4><ul class="plain"><li>{esc(r.get("great",""))}</li></ul>'
                       f'<h4 class="s">Sharpen</h4><ul class="plain"><li>{esc(r.get("improve",""))}</li></ul>'
                       f'<ul class="plain"><li><b>How:</b> {esc(r.get("how",""))}</li></ul></div>')

    hour_label = lambda h: ("12am" if h == 0 else f"{h}am" if h < 12 else "12pm" if h == 12 else f"{h-12}pm")
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Five Hats</title>
<!-- generated {TODAY} by balance-render-dashboard.py; sources: roles-review.json,
     coach-ledger fold (actionables.json), balance-log.jsonl, git history 30d.
     ALL TEXT AUTHORED AT GENERATION TIME. -->
<style>{CSS}</style></head><body><div class="wrap">
<div class="eyebrow">Balance &middot; Founder Coach &middot; regenerated {TODAY}</div>
<h1>The Five Hats</h1>
<div class="tabs" role="tablist">
<button role="tab" aria-selected="true" data-for="today">Today</button>
<button role="tab" aria-selected="false" data-for="week">This Week</button>
<button role="tab" aria-selected="false" data-for="month">Month</button>
</div>

<section data-tab="today" class="on">
<div class="tiles">
<div class="tile"><b>{n_windows}</b><span>observation windows today</span></div>
<div class="tile"><b>{commits_by_day.get(TODAY, 0)}</b><span>commits today (both repos)</span></div>
<div class="tile"><b>{len(active_acts)}</b><span>active actionables</span></div>
<div class="tile"><b>{len(done_acts)}</b><span>done</span></div>
</div>
<h2>Actionables</h2>
<p class="sub">Your current focus — capped at {derived.get("max_active", 3)} so each one gets real attention. Auto-verified ones close themselves when the evidence appears; the rest close when you say so in Balance chat ("mark ... done").</p>
{"".join(act_html(a) for a in active_acts + done_acts) or '<p class="sub">Nothing tracked yet.</p>'}
{f'<p class="sub">{len(parked_acts)} more parked — queued, not forgotten; they surface as active slots free up or when you reprioritize.</p>' if parked_acts else ''}
{f'<p class="sub" style="color:var(--amber)">{esc("; ".join(warnings))}</p>' if warnings else ''}
<h2>Today&rsquo;s insights</h2>
<div class="card"><ul class="plain">{"".join(f"<li>{esc(i.get('text',''))} <span style='color:var(--faint)'>({esc(i.get('date',''))})</span></li>" for i in reversed(insights)) or "<li>First daily pass pending.</li>"}</ul></div>
<h2>Shipped today</h2>
<div class="card">{"".join(f'<div class="ship">{esc(s)}</div>' for s in today_subj) or '<p class="sub">Nothing committed yet today.</p>'}</div>
</section>

<section data-tab="week">
{f'<div class="card"><b style="font-family:var(--serif)">The week, read honestly.</b><p style="font-size:13px;margin:6px 0 0">{esc(week_insight["text"])}</p></div>' if week_insight else ''}
<h2>Commits per day</h2>
<div class="card"><div class="bars" style="max-width:420px">{bars([commits_by_day[d] for d in week_days], label=lambda i: week_days[i])}</div></div>
<h2>Shipped this week</h2>
<div class="card">{"".join(f'<div class="ship"><time>{esc(d[5:])}</time>{esc(s[:110])}</div>' for d, s in week_subj) or '<p class="sub">No feature/release commits this week.</p>'}</div>
<h2>Actionables movement</h2>
{"".join(act_html(a) for a in active_acts) or '<p class="sub">All clear.</p>'}
{f'<p class="sub">{len(parked_acts)} parked.</p>' if parked_acts else ''}
</section>

<section data-tab="month">
<h2>Where the month went</h2>
<p class="sub">File-touches per day by role, trailing 30 days. Darker = more. The empty Portfolio row is itself a finding.</p>
<div class="hm-wrap"><div class="hm">{heat_rows()}</div>
<div class="legend"><span><i style="background:var(--h0)"></i>0</span><span><i style="background:var(--h1)"></i>1&ndash;9</span>
<span><i style="background:var(--h2)"></i>10&ndash;49</span><span><i style="background:var(--h3)"></i>50&ndash;199</span>
<span><i style="background:var(--h4)"></i>200+</span></div></div>
<h2>When you work</h2>
<div class="hm-wrap"><div class="bars" style="min-width:480px">{bars(hours, hot=lambda h: 1 <= h < 5 and hours[h] > 0, label=hour_label)}</div></div>
<h2>The five roles, coached</h2>
{roles_html or '<p class="sub">roles-review.json missing.</p>'}
</section>

<p class="foot">balance V2 &middot; rendered {TODAY} {time.strftime("%H:%M", time.localtime(NOW))} &middot; sources: roles-review.json + coach ledger + balance-log + git &middot; observe-only, machine activity filtered</p>
</div>
<script>
document.querySelectorAll(".tabs button").forEach(function(b){{
  b.addEventListener("click", function(){{
    document.querySelectorAll(".tabs button").forEach(function(x){{x.setAttribute("aria-selected","false")}});
    document.querySelectorAll("section[data-tab]").forEach(function(s){{s.classList.remove("on")}});
    b.setAttribute("aria-selected","true");
    document.querySelector('section[data-tab="'+b.dataset.for+'"]').classList.add("on");
  }});
}});
</script></body></html>"""

    fd, tmp = tempfile.mkstemp(dir=BAL)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, OUT)
    print(f"dashboard: {OUT} ({len(html)} bytes, tabs=3)")


if __name__ == "__main__":
    render()
