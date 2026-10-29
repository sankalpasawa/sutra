#!/bin/bash
# The J2 page end to end in a real browser (UI port, package j2ui-verify, T5): the app from source on a record of its own, the
# five departments of test_fixtures/j2ui/seed.py on it (start, question, building, ready, hostile), and shot-j2.js on each.
#   usage: qa/walks/j2ui-e2e.sh [record-dir] [port] [out-dir]
#   record-dir  default: a new directory under $TMPDIR (kept, and named at the end)
#   port        default 8362 (not the walks' 8341, so a founder's own server is left alone)
#   out-dir     where the screenshots go, default design/j2ui
# The offline functions answer (SUTRA_WEBSITE_OFFLINE=1) and the motor is off (SUTRA_MOTOR_OFF=1, which wins over the SUTRA_MOTOR=1
# devserver.sh sets): nothing here calls a model, and no departments' records move while the browser looks at them. The server is this app's uvicorn and is
# stopped on the way out, whatever happened. After the five, the structure of the page is compared with the prototype's own
# (its pinned commit, extracted with git archive and served in mock mode on a scratch copy of one saved run; nothing in the
# prototype's folder is written) and written to <out-dir>/STRUCTURE.md; so is what the eye sees on the start screen (the computed
# style of the placeholder in the preview frame, which the app's server answers, and the layout box of every element of the Simple
# view, in the app and in the prototype). Exit 0 when every claim of shot-j2.js held on all five, the structure matched and the
# start screen is drawn the same, 1 otherwise. SHOT_PORT and PROTO_PORT move the DevTools and prototype ports.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
UI="$(cd "$HERE/../.." && pwd)"
REC="${1:-$(mktemp -d "${TMPDIR:-/tmp}/j2ui-e2e-XXXXXX")}"
PORT="${2:-8362}"
OUT="${3:-$UI/design/j2ui}"
PY="$UI/.venv/bin/python"
[ -x "$PY" ] || PY=python3
if [ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] && [ -z "${CHROME:-}" ]; then
  echo "j2ui-e2e: Google Chrome is not here (set CHROME); nothing was run"
  exit 0
fi
export SUTRA_WEBSITE_OFFLINE=1 SUTRA_MOTOR_OFF=1 J2_FLOW_V1=1 J1_FLOW_V1=1
mkdir -p "$REC" "$OUT"
cd "$UI" || exit 1
bash "$HERE/devserver-stop.sh" "$PORT" 2>&1 | tail -1
SEEDED="$("$PY" test_fixtures/j2ui/seed.py "$REC" start question building ready hostile kind_default kind_organic kind_root 2>/dev/null)" || { echo "j2ui-e2e: the seed failed"; exit 1; }
echo "$SEEDED"
ref_of() { echo "$SEEDED" | awk -v s="$1" '$1 == s { print $2 }'; }
PPORT="${PROTO_PORT:-8763}"
# the prototype's server is a child of the launcher that started it: stop the listener on its port, and only if it is the prototype's
stop_proto() {
  for P in $(lsof -nP -iTCP:"$PPORT" -sTCP:LISTEN -t 2>/dev/null | sort -u); do
    case "$(ps -o command= -p "$P")" in *j2_server.py*--port\ "$PPORT"*) kill "$P" ;; *) echo "NOT MINE, left alone: $P" ;; esac
  done
}
trap 'bash "$HERE/devserver-stop.sh" "$PORT" >/dev/null 2>&1; stop_proto' EXIT
bash "$HERE/devserver-detach.sh" "$REC" "$PORT" | tail -3
curl -s -m 5 "http://127.0.0.1:$PORT/j2ui/$(ref_of ready)/" -o /dev/null -w "page: %{http_code}\n"
RC=0
for st in start question building ready hostile; do
  echo "=== $st"
  node "$HERE/shot-j2.js" "$OUT" "http://127.0.0.1:$PORT" "$(ref_of "$st")" "$st" || RC=1
done

# ---- A5.1: the page for every kind: open it, say a word, see it in the chat (no browser: the page's own routes) -------------------
for st in kind_default kind_organic kind_root; do
  echo "=== $st"
  "$PY" - "http://127.0.0.1:$PORT/j2ui/$(ref_of "$st")/" "$st" <<'KPY' || RC=1
import json, sys, time, urllib.request
base, st = sys.argv[1], sys.argv[2]
get = lambda p: urllib.request.urlopen(base + p, timeout=10)
page = get("").read().decode("utf-8")
assert "const WD = " in page, "the page is the J2 page with the words helper"
state = json.load(get("api/state"))
assert state["output"] == st.split("_")[1] and state["words"]["pick"] is False and "website" not in json.dumps(state["words"]).lower(), state["words"]
assert state["cycle"] == 0 or st != "kind_root", "a Root with no cycle keeps cycle 0"
word = "hello from the walk"
req = urllib.request.Request(base + "api/say", data=json.dumps({"text": word}).encode(), headers={"Content-Type": "application/json"}, method="POST")
code = urllib.request.urlopen(req, timeout=15).status
assert code == 200, code
for _ in range(20):
    seen = [m for m in json.load(get("api/state"))["chat"] if word in str(m.get("text"))]
    if seen:
        break
    time.sleep(0.5)
assert seen, "the word said is in the chat"
print(st, "page 200, said a word, saw it in the chat")
KPY
done

# ---- the structure of the page: ours (in the app) and the prototype's own ---------------------------------------------------
SCR="$(mktemp -d "${TMPDIR:-/tmp}/j2ui-structure-XXXXXX")"
PINNED="$UI/j2ui_assets/PINNED.json"
PIN="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['source']['commit'])" "$PINNED" 2>/dev/null)"
PROTO="${J2_PROTOTYPE:-$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['source']['path'])" "$PINNED" 2>/dev/null)}"
PRC=""
echo "=== structure"
node "$HERE/shot-j2.js" "$SCR" "http://127.0.0.1:$PORT" "/j2ui/$(ref_of ready)/" outline ours || RC=1
node "$HERE/shot-j2.js" "$SCR" "http://127.0.0.1:$PORT" "/j2ui/$(ref_of start)/" layout ours || RC=1
if [ -n "$PROTO" ] && [ -d "$PROTO/.git" ] && git -C "$PROTO" cat-file -e "$PIN^{commit}" 2>/dev/null; then
  mkdir -p "$SCR/proto" "$SCR/runs"
  git -C "$PROTO" archive "$PIN" | tar -x -C "$SCR/proto"
  RUNID="j2-20261008-123848"
  RUNQ="/"
  if [ -d "$PROTO/runs/$RUNID" ]; then cp -R "$PROTO/runs/$RUNID" "$SCR/runs/"; RUNQ="/?run=$RUNID"; fi
  PPY="$PROTO/venv/bin/python"; [ -x "$PPY" ] || PPY=python3
  stop_proto
  ( cd "$SCR/proto" && J2_RUNS_DIR="$SCR/runs" STUDIO_MOCK=1 "$PPY" j2_server.py --port "$PPORT" --no-browser >"$SCR/proto.log" 2>&1 & disown )
  for i in $(seq 1 40); do curl -s -m 2 "http://127.0.0.1:$PPORT/api/runs" >/dev/null 2>&1 && break; sleep 0.5; done
  node "$HERE/shot-j2.js" "$SCR" "http://127.0.0.1:$PPORT" "$RUNQ" outline prototype || RC=1
  node "$HERE/shot-j2.js" "$SCR" "http://127.0.0.1:$PPORT" "/" layout prototype || RC=1   # the live run is idle: the prototype's own start screen
  stop_proto
  PRC=1
else
  echo "j2ui-e2e: the prototype's checkout or its pinned commit is not here (set J2_PROTOTYPE): the structure is written for the app's page only"
fi
"$PY" - "$SCR" "$OUT" "$PIN" "${PRC:-0}" <<'PYEOF' || RC=1
import difflib, json, os, sys
scr, out, pin, have = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
ours = json.load(open(os.path.join(scr, "outline-ours.json")))
theirs = json.load(open(os.path.join(scr, "outline-prototype.json"))) if have else None
lay_a = json.load(open(os.path.join(scr, "layout-ours.json"))) if os.path.exists(os.path.join(scr, "layout-ours.json")) else None
lay_b = json.load(open(os.path.join(scr, "layout-prototype.json"))) if have and os.path.exists(os.path.join(scr, "layout-prototype.json")) else None
skel = lambda lines: [l for l in lines if "~ " not in l.strip()[:2]]
vocab = lambda lines: {c.strip() for l in lines if l.strip().startswith("~ ") for c in l.strip()[2:].split(", ")}
md = ["# The page's structure, in the app and in the prototype", "",
      "Written by `qa/walks/j2ui-e2e.sh` (shot-j2.js, kind `outline`). The outline lists, for each view, every element of the page's own "
      "markup as `tag#id.classes` (no text), indented by depth. Where the page fills an element with data (a pane, the chat, the progress "
      "strip) the element is followed by one `~` line: the distinct tags and classes found beneath it, so a difference in data (more messages, "
      "another card) is not a difference in structure. The page is the prototype's file at commit `%s`, changed only by the three documented "
      "substitutions (S1 relative paths, S2 one script line, S3 fonts), so its skeleton must be the prototype's own." % pin[:12], ""]
bad = False
if theirs is None:
    md += ["The prototype was not available on this machine when this was written: the outline of the page in the app only.", ""]
for view, title in (("simple", "Simple view (`#sview`)"), ("detail", "Detailed view (`#dview`: the rail, the work panes, the chat)")):
    a, b = ours[view], (theirs or {}).get(view)
    md += ["## " + title, ""]
    if b is not None:
        same = skel(a) == skel(b)
        bad = bad or not same
        va, vb = vocab(a), vocab(b)
        md += ["- skeleton: **%s** (%d lines in the app, %d in the prototype's page)" % ("identical" if same else "DIFFERENT", len(skel(a)), len(skel(b))),
               "- classes and tags the page fills its panes with: %d in the app, %d in the prototype's page on its own saved run; %d shared" % (len(va), len(vb), len(va & vb)),
               "- only in the app (data it was given): " + (", ".join(sorted(va - vb)) or "none"),
               "- only in the prototype's page (data its run had): " + (", ".join(sorted(vb - va)) or "none"), ""]
        if not same:
            md += ["```diff"] + [l for l in difflib.unified_diff(skel(b), skel(a), "prototype", "app", lineterm="", n=2)][:80] + ["```", ""]
    md += ["```text"] + a + ["```", ""]
# what the eye sees on the start screen: the markup can be the prototype's own and the screen still differ, because the right-hand pane
# is a frame on a page the app's SERVER answers (the placeholder shown while nothing is built), and a font size there is not the page's
skeleton_differs = bad
md += ["## The start screen, as drawn (1280x900, the Simple view)", ""]
drawn = ""
if lay_a is None or lay_b is None:
    md += ["No comparison: %s." % ("the prototype was not available on this machine" if lay_a else "the app's start screen was not measured"), ""]
    drawn = "no comparison of the drawn start screen"
else:
    pa, pb = lay_a["placeholder"] or {}, lay_b["placeholder"] or {}
    fields = sorted(k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k))
    ba, bb = lay_a["boxes"], lay_b["boxes"]
    moved = sorted(k for k in set(ba) | set(bb) if ba.get(k) != bb.get(k))
    same_p, same_b = not fields and bool(pa), not moved
    bad = bad or not same_p or not same_b
    md += ["- the placeholder the preview frame shows while nothing is built (font size, family, weight, colour, padding, margin, line height, quirks mode, where the text ends): **%s** (%s, %s, padding %s, text ends at %s px in the app and %s px in the prototype)" % (
              "identical" if same_p else "DIFFERENT", pa.get("fontSize"), pa.get("color"), pa.get("padding"), pa.get("textRight"), pb.get("textRight")),
           "- the layout box (x, y, width, height) of each of the %d elements of the Simple view: **%s**" % (len(ba), "identical" if same_b else "DIFFERENT in %d" % len(moved)), ""]
    if fields:
        md += ["```text"] + ["placeholder %s: app %r, prototype %r" % (k, pa.get(k), pb.get(k)) for k in fields] + ["```", ""]
    if moved:
        md += ["```text"] + ["%s: app %s, prototype %s" % (k, ba.get(k), bb.get(k)) for k in moved[:40]] + ["```", ""]
    drawn = "the drawn start screen differs from the prototype's" if not (same_p and same_b) else "the drawn start screen matches the prototype's"
open(os.path.join(out, "STRUCTURE.md"), "w").write("\n".join(md))
print("STRUCTURE.md written;", "the skeleton differs from the prototype's" if skeleton_differs else "the skeleton matches the prototype's" if theirs else "no comparison", "; " + drawn)
sys.exit(1 if bad else 0)
PYEOF
rm -rf "$SCR"
echo "record: $REC   screenshots: $OUT   exit $RC"
exit $RC
