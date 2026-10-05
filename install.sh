#!/usr/bin/env sh
# Install AI Skills into Claude Code's skills directory.
# Author: Pradip Subedi (@sprasapradip) - https://github.com/sprasapradip/ai-skills
#
# Usage: sh install.sh [--project DIR] [skill ...]
#   default target: ~/.claude/skills (all projects)
#   --project DIR : DIR/.claude/skills (one project)
#   skill ...     : install only the named skills (default: all)
# Exit codes: 0 = installed, 2 = usage error / unknown skill.
set -eu
SRC=$(cd "$(dirname "$0")" && pwd)
DEST="$HOME/.claude/skills"
if [ "${1:-}" = "--project" ]; then
  [ -n "${2:-}" ] || { echo "usage: $0 [--project DIR] [skill ...]" >&2; exit 2; }
  DEST="$2/.claude/skills"; shift 2
fi
if [ $# -eq 0 ]; then
  set -- $(for d in "$SRC"/*/SKILL.md; do basename "$(dirname "$d")"; done)
fi
mkdir -p "$DEST"
for skill in "$@"; do
  [ -f "$SRC/$skill/SKILL.md" ] || { echo "error: unknown skill '$skill'" >&2; exit 2; }
  rm -rf "${DEST:?}/$skill"
  cp -R "$SRC/$skill" "$DEST/$skill"
  chmod +x "$DEST/$skill"/scripts/* 2>/dev/null || true
  echo "installed $skill -> $DEST/$skill"
done
