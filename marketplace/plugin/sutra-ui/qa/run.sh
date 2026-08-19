#!/bin/sh
# sutra-ui design-QA child. Starts NOTHING: the panel must already be running.
set -eu

QA="$(cd "$(dirname "$0")" && pwd)"
URL="http://127.0.0.1:8330/"

# The product carries NO machine-specific fallback (by design — see its README:
# resolution is $PLAYWRIGHT, then a package resolvable from ITS directory).
# This child is machine-specific, so IT pins the install, not the product.
if [ -z "${PLAYWRIGHT:-}" ]; then
  PW="/Users/asawa/sutra-ui-workspace/app/node_modules/playwright/index.js"
  if [ -f "$PW" ]; then
    PLAYWRIGHT="$PW"
    export PLAYWRIGHT
  else
    echo "sutra-ui qa: PLAYWRIGHT is unset and the pinned install is gone: $PW" >&2
    echo "sutra-ui qa: export PLAYWRIGHT=/path/to/node_modules/playwright/index.js, then rerun." >&2
    echo "sutra-ui qa: find one:  find ~ -maxdepth 6 -path '*node_modules/playwright/index.js' 2>/dev/null | head -1" >&2
    exit 2
  fi
fi

if ! curl -sf -o /dev/null --max-time 3 "$URL"; then
  echo "sutra-ui qa: the panel is NOT running at $URL — this runner starts nothing." >&2
  echo "sutra-ui qa: start it first (plugin's run.sh / sutra-ui.sh), then rerun." >&2
  exit 2
fi

# Compose step, because the product CLI reads exactly ONE json file: the rules
# object is synced from rules-sutra.json and the captured fan-out fixture is
# written into the boot state's fixture action. Idempotent; sources of truth
# stay rules-sutra.json and ../tests/fixtures/toolruns-fanout.json.
node -e '
  const fs = require("fs");
  const qa = process.argv[1];
  const cfg = JSON.parse(fs.readFileSync(qa + "/config.json", "utf8"));
  cfg.rules = JSON.parse(fs.readFileSync(qa + "/rules-sutra.json", "utf8"));
  const fx = JSON.parse(fs.readFileSync(qa + "/../tests/fixtures/toolruns-fanout.json", "utf8"));
  const boot = cfg.states.find((s) => s.name === "boot");
  const slot = boot.actions.find((a) => a.eval && a.eval.startsWith("window.__qaRuns"));
  slot.eval = "window.__qaRuns = " + JSON.stringify(fx.toolRuns) + ";";
  fs.writeFileSync(qa + "/config.json", JSON.stringify(cfg, null, 2) + "\n");
' "$QA"

cd "$QA"
node /Users/asawa/Claude/dayflow/products/design-qa/cli.mjs run config.json
