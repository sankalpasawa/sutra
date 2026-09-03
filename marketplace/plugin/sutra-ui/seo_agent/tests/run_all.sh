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
PY="${PYTHON:-python3}"
made_tmp=0
if [ -z "$SEO_AGENT_DATA" ]; then
  SEO_AGENT_DATA="$(mktemp -d -t seo-agent-tests)"; made_tmp=1
fi
export SEO_AGENT_DATA
export SEO_AGENT_NO_CLI=1            # the model is stubbed; never shell out to claude here
echo "data dir: $SEO_AGENT_DATA"
fail=0
for t in test_loop test_tools test_endtoend test_behaviour test_checks_editing test_llm_cli; do
  echo "══ $t"
  out="$($PY -m seo_agent.tests.$t 2>&1)" || fail=1
  echo "$out" | grep -E "^  (PASS|FAIL)|passed|failed|FAILED|Error|Traceback" | tail -6
done
echo
[ $made_tmp -eq 1 ] && rm -rf "$SEO_AGENT_DATA"
[ $fail -eq 0 ] && echo "ALL SUITES PASS" || { echo "SOMETHING FAILED — do not ship"; exit 1; }
