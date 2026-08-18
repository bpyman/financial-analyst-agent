#!/usr/bin/env bash
set -eo pipefail

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <iterations>"
  exit 1
fi

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

for ((i=1; i<=$1; i++)); do
  tmpfile=$(mktemp)
  trap 'rm -f "$tmpfile"' EXIT

  commits=$(git log -n 5 \
    --format="%H%n%ad%n%B---" \
    --date=short 2>/dev/null || echo "No commits found")

  issues=$(cat issues/*.md 2>/dev/null || echo "No issues found")
  prompt=$(cat ralph/prompt.md)

  agent --print \
    --force \
    --output-format stream-json \
    --stream-partial-output \
    "Previous commits:

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