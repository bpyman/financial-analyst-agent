# Shared helpers for once.sh and afk.sh. Sourced; not executed.

ralph_cd_root() {
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
}

ralph_collect_issues() {
  local feature="${1:-}"
  local files=""
  local f status

  if [ -n "$feature" ]; then
    if [ ! -d ".scratch/${feature}/issues" ]; then
      echo "No issues found (.scratch/${feature}/issues missing)"
      return 0
    fi
    files=$(find ".scratch/${feature}/issues" -maxdepth 1 -type f -name '*.md' | sort)
  elif [ -d .scratch ]; then
    files=$(find .scratch -type f -name '*.md' -path '*/issues/*' ! -path '*/done/*' | sort)
  fi

  if [ -z "$files" ]; then
    echo "No issues found"
    return 0
  fi

  echo "Index (read ticket files from disk; bodies are not inlined):"
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    status=$(grep -m1 -E '^\*\*Status:\*\*|^Status:' "$f" || true)
    blocked=$(grep -m1 -E '^\*\*Blocked by:\*\*|^Blocked by:' "$f" || true)
    printf '  %s  %s  %s\n' "$f" "${status:-Status: (none)}" "${blocked:-}"
  done <<< "$files"
}

ralph_recent_commits() {
  git log -n 5 --format="%H%n%ad%n%B---" --date=short 2>/dev/null || echo "No commits found"
}

ralph_run_agent() {
  local payload="$1"
  local prompt_file=".scratch/.ralph-run.md"
  local short
  local ps_agent="${CURSOR_AGENT:-}"

  mkdir -p .scratch
  printf '%s\n' "$payload" > "$prompt_file"
  short="Read .scratch/.ralph-run.md from the workspace root and follow the Instructions section. The issue index and recent commits are in that file; open ticket files from disk."

  if [ -z "$ps_agent" ] && [ -f "${HOME}/AppData/Local/cursor-agent/agent.ps1" ]; then
    ps_agent="${HOME}/AppData/Local/cursor-agent/agent.ps1"
  fi
  if [ -z "$ps_agent" ] && [ -f "C:/Users/the_w/AppData/Local/cursor-agent/agent.ps1" ]; then
    ps_agent="C:/Users/the_w/AppData/Local/cursor-agent/agent.ps1"
  fi

  if command -v agent >/dev/null 2>&1; then
    agent --print --force --output-format stream-json --stream-partial-output "$short"
  elif [ -n "$ps_agent" ] && [ -f "$ps_agent" ]; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass \
      -File "$ps_agent" \
      --print \
      --force \
      --output-format stream-json \
      --stream-partial-output \
      "$short"
  else
    echo "cursor agent not found: put agent on PATH or set CURSOR_AGENT to agent.ps1" >&2
    exit 1
  fi
}
