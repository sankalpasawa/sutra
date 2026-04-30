#!/bin/bash
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

# Irreversible-domain denylist hits
assert_field "push the native v1.0.1 tag to origin/main" "reversibility" "irreversible"
assert_field "git push --force origin main" "reversibility" "irreversible"
assert_field "rm -rf old-files/" "reversibility" "irreversible"
assert_field "delete the database row" "reversibility" "irreversible"
assert_field "send email to clients" "reversibility" "irreversible"
assert_field "publish v2.0 to npm" "reversibility" "irreversible"

# Reversible defaults
assert_field "add a Slack connector for Testlify" "reversibility" "reversible"
assert_field "edit the README" "reversibility" "reversible"
assert_field "what is X?" "reversibility" "reversible"

# Risk inference
assert_field "push to origin/main" "decision_risk" "high"
assert_field "edit the README" "decision_risk" "low"
assert_field "modify auth config" "decision_risk" "high"

summary
