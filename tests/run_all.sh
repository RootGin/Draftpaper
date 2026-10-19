#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export DRAFTPAPER_CONFIG_DIR="$WORKTREE_DIR"
export EWW_DIR="$WORKTREE_DIR"
export DRAFTPAPER_MOCK=1

exec python3 "$SCRIPT_DIR/run_all.py" "$@"
