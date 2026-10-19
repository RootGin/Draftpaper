#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_FILE="$ROOT_DIR/theme.scss"

THEMES=("nord" "softglow" "blueprint" "daypanel" "nightpanel")

get_current_theme() {
    if [ ! -f "$THEME_FILE" ]; then
        echo "nord"
        return
    fi
    local theme
    theme=$(grep -oE 'themes/[a-zA-Z0-9_-]+' "$THEME_FILE" 2>/dev/null | cut -d/ -f2 || true)
    echo "${theme:-nord}"
}

set_theme() {
    local target="$1"
    local valid=0
    for t in "${THEMES[@]}"; do
        if [ "$t" = "$target" ]; then
            valid=1
            break
        fi
    done
    if [ "$valid" -eq 0 ]; then
        printf "Invalid theme: %s\n" "$target" >&2
        exit 1
    fi

    printf '@import "./themes/%s";\n' "$target" > "$THEME_FILE"

    if command -v eww >/dev/null 2>&1; then
        eww -c "$ROOT_DIR" reload >/dev/null 2>&1 || true
        eww -c "$ROOT_DIR" update active_theme="$target" >/dev/null 2>&1 || true
    fi
    echo "$target"
}

rotate_theme() {
    local current
    current=$(get_current_theme)
    local idx=0
    for i in "${!THEMES[@]}"; do
        if [ "${THEMES[$i]}" = "$current" ]; then
            idx=$i
            break
        fi
    done

    local next_idx=$(( (idx + 1) % ${#THEMES[@]} ))
    local next_theme="${THEMES[$next_idx]}"
    set_theme "$next_theme"
}

action="${1:-current}"

case "$action" in
    current|get|name)
        get_current_theme
        ;;
    next|rotate|cycle)
        rotate_theme
        ;;
    set)
        if [ -z "${2:-}" ]; then
            printf "Usage: %s set <theme_name>\n" "$0" >&2
            exit 1
        fi
        set_theme "$2"
        ;;
    *)
        get_current_theme
        ;;
esac
