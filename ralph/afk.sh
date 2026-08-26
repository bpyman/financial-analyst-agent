#!/usr/bin/env bash
# Repeat Ralph until NO MORE TASKS or the iteration cap.
# Usage: bash ralph/afk.sh <iterations> [feature-slug]
set -eo pipefail

# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
ralph_cd_root

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <iterations> [feature-slug]"
  exit 1
fi

iterations="$1"
feature="${2:-}"

# Extract only new streaming text, excluding Cursor's duplicate flush events.
stream_text='
  select(
    .type == "assistant"
    and has("timestamp_ms")
    and (has("model_call_id") | not)
  )
  | .message.content[]?
  | select(.type == "text")
  | .text // empty
'

# Extract the completed assistant response.
final_result='
  select(.type == "result" and .subtype == "success")
  | .result // empty
'

for ((i=1; i<=iterations; i++)); do
  tmpfile=$(mktemp)
  trap 'rm -f "$tmpfile"' EXIT

  commits=$(ralph_recent_commits)
  issues=$(ralph_collect_issues "$feature")
  prompt=$(cat ralph/prompt.md)

  ralph_run_agent "Previous commits:

$commits

Issues:

$issues

Instructions:

$prompt" \
  | tee "$tmpfile" \
  | jq --unbuffered -rj "$stream_text"

  echo

  result=$(jq -r "$final_result" "$tmpfile")

  rm -f "$tmpfile"
  trap - EXIT

  if [[ "$result" == *"<promise>NO MORE TASKS</promise>"* ]]; then
    echo "Ralph complete after $i iterations."
    exit 0
  fi
done
