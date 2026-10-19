#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${XDG_PICTURES_DIR:-$HOME/Pictures}"
mkdir -p "$TARGET_DIR"
FILENAME="$TARGET_DIR/screenshot-$(date +%Y%m%d-%H%M%S).png"

if command -v grim >/dev/null 2>&1; then
    if command -v slurp >/dev/null 2>&1; then
        GEOM=$(slurp 2>/dev/null || true)
        if [ -n "$GEOM" ]; then
            grim -g "$GEOM" "$FILENAME"
        else
            grim "$FILENAME"
        fi
    else
        grim "$FILENAME"
    fi
elif command -v scrot >/dev/null 2>&1; then
    scrot "$FILENAME"
fi
