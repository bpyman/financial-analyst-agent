#!/usr/bin/env bash

CURSOR_AGENT='C:/Users/the_w/AppData/Local/cursor-agent/agent.ps1'

set -euo pipefail

issues=$(cat issues/*.md 2>/dev/null || echo "No issues found")
commits=$(git log -n 5 --format="%H%n%ad%n%B---" --date=short 2>/dev/null || echo "No commits found")
prompt=$(cat ralph/prompt.md)

powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File "$CURSOR_AGENT" \
  --print \
  --force \
  --output-format stream-json \
  --stream-partial-output \
  "Previous commits:
$commits

Issues:
$issues

Instructions:
$prompt"