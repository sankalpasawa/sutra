#!/usr/bin/env bash
# Every suite, against a throwaway data dir. Run this before calling anything done.
#
#   seo_agent/tests/run_all.sh            # from anywhere
#   PYTHON=/path/to/python seo_agent/tests/run_all.sh
#
# SEO_AGENT_DATA is set to a fresh temp folder unless you set it yourself, so no suite
# ever touches a real install. The suites never call the real Claude CLI or any API.
set -e
cd "$(dirname "$0")/../.."           # the folder that holds seo_agent/
# DEFAULT TO THE PROJECT VENV when there is one. PUBLISH-CHECK.md documents this
# script as a bare `bash seo_agent/tests/run_all.sh`, and that command failed on
# every suite with `ModuleNotFoundError: No module named 'httpx'` -- the system
# python3 has none of the runtime deps, they live in sutra-ui/.venv. A gate step
# whose documented invocation cannot pass is a gate step nobody runs. PYTHON=
# still overrides.
if [ -n "$PYTHON" ]; then PY="$PYTHON"
elif [ -x ".venv/bin/python" ]; then PY="$PWD/.venv/bin/python"
else PY="python3"; fi
made_tmp=0
if [ -z "$SEO_AGENT_DATA" ]; then
  SEO_AGENT_DATA="$(mktemp -d -t seo-agent-tests)"; made_tmp=1
fi
export SEO_AGENT_DATA
export SEO_AGENT_NO_CLI=1            # the model is stubbed; never shell out to claude here
echo "data dir: $SEO_AGENT_DATA"
fail=0
for t in test_loop test_tools test_endtoend test_behaviour test_checks_editing test_llm_cli test_foundation test_browser test_brand test_research test_write test_assets_wiring test_assets_formats test_assets_trends test_assets_competitors test_assets_merge test_assets_import test_store_live test_picture test_credit_guard; do
  [ -f "seo_agent/tests/$t.py" ] || { echo "══ $t (not written yet, skipped)"; continue; }
  echo "══ $t"
  # "$PY" IS QUOTED. Unquoted, an interpreter path containing a space splits on
  # it -- this checkout lives under ".../Desktop/Joy Stephen/", so every suite
  # died with `/Users/joytadanki/Desktop/Joy: No such file or directory`
  # (2026-09-08). The default python3 has no space in its path, which is why it
  # went unnoticed until someone passed PYTHON=<a venv under a spaced path>.
  ok=1
  out="$("$PY" -m seo_agent.tests.$t 2>&1)" || { fail=1; ok=0; }
  echo "$out" | grep -E "^  (PASS|FAIL)|passed|failed|FAILED|Error|Traceback" | tail -6
  # A SUITE THAT FAILED ALWAYS SHOWS SOMETHING. The grep above is a summary
  # filter, and it matched nothing at all for the failure above -- so eleven
  # suites printed their header, nothing else, and the run ended in a bare
  # "SOMETHING FAILED" with no way to tell what. A failure that produces no
  # matching line prints its own tail instead.
  if [ $ok -eq 0 ] && ! echo "$out" | grep -qE "^  (PASS|FAIL)|passed|failed|FAILED|Error|Traceback"; then
    echo "$out" | tail -6 | sed -e 's/^/  /'
  fi
done
echo
[ $made_tmp -eq 1 ] && rm -rf "$SEO_AGENT_DATA"
[ $fail -eq 0 ] && echo "ALL SUITES PASS" || { echo "SOMETHING FAILED — do not ship"; exit 1; }
