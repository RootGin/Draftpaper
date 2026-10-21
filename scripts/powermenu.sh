#!/usr/bin/env bash
set -euo pipefail

LOCK="󰌾  Lock"
SUSPEND="󰤄  Suspend"
LOGOUT="󰍃  Logout"
REBOOT="󰜉  Reboot"
SHUTDOWN="󰐥  Power Off"

OPTIONS="${LOCK}\n${SUSPEND}\n${LOGOUT}\n${REBOOT}\n${SHUTDOWN}"

CHOSEN=$(printf "%b" "$OPTIONS" | fuzzel --dmenu --prompt "SYSTEM ▸ " --lines 5 --width 20)

case "$CHOSEN" in
  "$LOCK")
    loginctl lock-session 2>/dev/null || true
    ;;
  "$SUSPEND")
    systemctl suspend
    ;;
  "$LOGOUT")
    if command -v niri >/dev/null 2>&1; then
      niri msg action quit --skip-confirmation
    else
      loginctl terminate-user "$USER"
    fi
    ;;
  "$REBOOT")
    systemctl reboot
    ;;
  "$SHUTDOWN")
    systemctl poweroff
    ;;
esac
