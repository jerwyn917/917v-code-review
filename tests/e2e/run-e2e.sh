#!/usr/bin/env bash
# End-to-end test: run a real review with Claude Code against a throwaway copy
# of a fixture, then score it with tests/evaluate.py.
#
#   tests/e2e/run-e2e.sh <fixture> <full|diff|security|architecture> <output-base-dir>
#
# The fixture is copied, never reviewed in place. The copy becomes a Git repo
# with one commit. For `diff`, tests/diff-changes/<fixture>/ is overlaid on top
# as uncommitted changes. Requires the `claude` CLI (authenticated) and python3.
set -euo pipefail

FIXTURE="${1:?fixture name}"
MODE="${2:?full|diff|security|architecture}"
BASE="${3:?output base dir}"
PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$BASE/$FIXTURE-$MODE"
REPO="$RUN/repo"

if [ -e "$RUN" ]; then echo "refusing to reuse existing $RUN" >&2; exit 2; fi
mkdir -p "$RUN"
cp -R "$PLUGIN/tests/fixtures/$FIXTURE" "$REPO"
git -C "$REPO" init -q -b main
git -C "$REPO" add -A
git -C "$REPO" -c user.email=e2e@example.com -c user.name=e2e commit -qm "fixture"

case "$MODE" in
  full) PROMPT="/917v-code-review:review"; EXPECTED="$PLUGIN/tests/expected/$FIXTURE.json"; EVAL_FLAGS="" ;;
  security) PROMPT="/917v-code-review:security"; EXPECTED="$PLUGIN/tests/expected/$FIXTURE.json"; EVAL_FLAGS="" ;;
  architecture) PROMPT="/917v-code-review:architecture"; EXPECTED="$PLUGIN/tests/expected/$FIXTURE.json"; EVAL_FLAGS="" ;;
  diff)
    cp -R "$PLUGIN/tests/diff-changes/$FIXTURE/." "$REPO/"
    PROMPT="/917v-code-review:review-diff"; EXPECTED="$PLUGIN/tests/expected/$FIXTURE.diff.json"; EVAL_FLAGS="--diff" ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac

# Pristine copy of exactly what the reviewer sees, to prove nothing was modified.
cp -R "$REPO" "$RUN/pristine"
rm -rf "$RUN/pristine/.git"

ALLOWED="Read,Grep,Glob,Write,Agent,Task,Skill,Bash(python3:*),Bash(git:*),Bash(mkdir:*),Bash(ls:*),Bash(wc:*),Bash(cat:*),Bash(head:*)"
export CODE_REVIEW_OUT_DIR="$RUN/reports"   # reports land here, outside the reviewed copy
START=$(date +%s)
( cd "$REPO" && claude -p "$PROMPT" --plugin-dir "$PLUGIN" --allowedTools "$ALLOWED" \
    --output-format stream-json --verbose > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log" ) || echo "claude exited non-zero" >&2
END=$(date +%s)
echo "review took $((END - START))s" | tee "$RUN/timing.txt"

set +e
python3 "$PLUGIN/tests/evaluate.py" --repo "$REPO" --expected "$EXPECTED" --original "$RUN/pristine" $EVAL_FLAGS \
  > "$RUN/evaluation.json"
STATUS=$?
set -e
python3 - "$RUN/evaluation.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
print("passed:", r.get("passed"), "| recall: %s (%d/%d)" % (r.get("recall"), len(r.get("found", {})), r.get("seeded", 0)))
print("totals:", json.dumps(r.get("totals", {}).get("by_severity")))
print("validation:", json.dumps(r.get("validation")))
print("missed:", r.get("missed"))
for f in r.get("failures", []):
    print("FAIL:", f)
EOF
exit $STATUS
