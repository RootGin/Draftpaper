#!/usr/bin/env bash
set -euo pipefail

use_glyphs=1
if [ "${DRAFTPAPER_GLYPHS:-}" = "0" ] || [ "${NERD_FONTS:-}" = "0" ]; then
    use_glyphs=0
elif [ "${DRAFTPAPER_GLYPHS:-}" = "1" ] || [ "${NERD_FONTS:-}" = "1" ]; then
    use_glyphs=1
elif ! fc-list : family 2>/dev/null | grep -q "Nerd Font"; then
    use_glyphs=0
fi

if [ -n "${DRAFTPAPER_BT_CONNECTED:-}" ]; then
    if [ "$DRAFTPAPER_BT_CONNECTED" = "1" ]; then
        connected=true
        dev_list="${DRAFTPAPER_BT_DEVICES:-Wireless Device}"
        text="$dev_list"
        if [ "$use_glyphs" -eq 1 ]; then
            icon="󰂱"
        else
            icon="BT"
        fi
        json_devs=$(python3 -c "import json, os; print(json.dumps([d.strip() for d in os.environ.get('DRAFTPAPER_BT_DEVICES', 'Wireless Device').split(',') if d.strip()]))")
    else
        connected=false
        text="NO DEVICES"
        if [ "$use_glyphs" -eq 1 ]; then
            icon="󰂯"
        else
            icon="BT"
        fi
        json_devs="[]"
    fi
    printf '{"connected": %s, "powered": true, "icon": "%s", "text": "%s", "devices": %s}\n' "$connected" "$icon" "$text" "$json_devs"
    exit 0
fi

if ! command -v bluetoothctl >/dev/null 2>&1; then
    if [ "$use_glyphs" -eq 1 ]; then
        icon="󰂲"
    else
        icon="BT-OFF"
    fi
    printf '{"connected": false, "powered": false, "icon": "%s", "text": "NO BLUETOOTH", "devices": []}\n' "$icon"
    exit 0
fi

show_out=$(bluetoothctl show 2>/dev/null || true)
if echo "$show_out" | grep -q "Powered: yes"; then
    powered=true
    connected_out=$(bluetoothctl devices Connected 2>/dev/null || true)
    if [ -n "$connected_out" ]; then
        connected=true
        if [ "$use_glyphs" -eq 1 ]; then
            icon="󰂱"
        else
            icon="BT"
        fi
        json_devs=$(echo "$connected_out" | sed -E 's/^Device [^ ]+ //' | python3 -c 'import sys, json; devs=[l.strip() for l in sys.stdin if l.strip()]; print(json.dumps(devs))')
        text=$(echo "$connected_out" | sed -E 's/^Device [^ ]+ //' | paste -sd ", " -)
    else
        connected=false
        if [ "$use_glyphs" -eq 1 ]; then
            icon="󰂯"
        else
            icon="BT"
        fi
        text="NO DEVICES"
        json_devs="[]"
    fi
else
    powered=false
    connected=false
    if [ "$use_glyphs" -eq 1 ]; then
        icon="󰂲"
    else
        icon="BT-OFF"
    fi
    text="BT OFF"
    json_devs="[]"
fi

printf '{"connected": %s, "powered": %s, "icon": "%s", "text": "%s", "devices": %s}\n' "$connected" "$powered" "$icon" "$text" "$json_devs"
