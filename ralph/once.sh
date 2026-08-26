#!/usr/bin/env bash
# One Ralph iteration. Optional feature slug scopes tickets.
# Usage: bash ralph/once.sh [feature-slug]
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
ralph_cd_root

feature="${1:-}"
issues=$(ralph_collect_issues "$feature")
commits=$(ralph_recent_commits)
prompt=$(cat ralph/prompt.md)

ralph_run_agent "Previous commits:
$commits

Issues:
$issues

Instructions:
$prompt"
