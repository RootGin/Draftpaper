#!/usr/bin/env bash
set -e

COUNTER_FILE="${DRAFTPAPER_OSD_COUNTER:-/tmp/.draftpaper-osd-counter}"
TIMEOUT="${DRAFTPAPER_OSD_TIMEOUT:-3}"
CONFIG_DIR="${DRAFTPAPER_CONFIG_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
MOCK_DIR="/tmp"
VOL_MOCK="${MOCK_DIR}/.draftpaper-mock-volume"
BRT_MOCK="${MOCK_DIR}/.draftpaper-mock-brightness"
STATE_FILE="${MOCK_DIR}/.draftpaper-osd-state.json"

get_volume() {
  if [ "${DRAFTPAPER_MOCK:-0}" = "1" ] || (! command -v wpctl >/dev/null 2>&1 && ! command -v pamixer >/dev/null 2>&1); then
    if [ -f "$VOL_MOCK" ]; then
      read -r v m < "$VOL_MOCK"
      echo "${v:-50} ${m:-false}"
    else
      echo "50 false"
    fi
    return
  fi
  if command -v wpctl >/dev/null 2>&1; then
    out=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null || echo "Volume: 0.50")
    vol=$(echo "$out" | awk '{print int($2 * 100)}')
    muted=false
    if echo "$out" | grep -q "MUTED"; then
      muted=true
    fi
    echo "$vol $muted"
    return
  fi
  if command -v pamixer >/dev/null 2>&1; then
    vol=$(pamixer --get-volume 2>/dev/null || echo "50")
    muted=$(pamixer --get-mute 2>/dev/null || echo "false")
    echo "$vol $muted"
    return
  fi
  echo "50 false"
}

set_volume() {
  action="$1"
  step="${2:-5}"
  read -r cur_vol cur_muted < <(get_volume)
  new_vol=$cur_vol
  new_muted=$cur_muted

  if [ "$action" = "up" ]; then
    new_vol=$((cur_vol + step))
    if [ $new_vol -gt 100 ]; then new_vol=100; fi
    new_muted=false
  elif [ "$action" = "down" ]; then
    new_vol=$((cur_vol - step))
    if [ $new_vol -lt 0 ]; then new_vol=0; fi
  elif [ "$action" = "mute" ] || [ "$action" = "toggle" ]; then
    if [ "$cur_muted" = "true" ]; then
      new_muted=false
    else
      new_muted=true
    fi
  elif [ "$action" = "set" ]; then
    new_vol=$step
    if [ $new_vol -gt 100 ]; then new_vol=100; fi
    if [ $new_vol -lt 0 ]; then new_vol=0; fi
  fi

  if [ "${DRAFTPAPER_MOCK:-0}" = "1" ] || (! command -v wpctl >/dev/null 2>&1 && ! command -v pamixer >/dev/null 2>&1); then
    echo "$new_vol $new_muted" > "$VOL_MOCK"
  elif command -v wpctl >/dev/null 2>&1; then
    if [ "$action" = "mute" ] || [ "$action" = "toggle" ]; then
      wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle 2>/dev/null || true
    else
      wp_val=$(awk "BEGIN {print $new_vol / 100}")
      wpctl set-volume @DEFAULT_AUDIO_SINK@ "$wp_val" 2>/dev/null || true
    fi
  elif command -v pamixer >/dev/null 2>&1; then
    if [ "$action" = "mute" ] || [ "$action" = "toggle" ]; then
      pamixer -t 2>/dev/null || true
    else
      pamixer --set-volume "$new_vol" 2>/dev/null || true
    fi
  fi
  echo "$new_vol $new_muted"
}

get_brightness() {
  if [ "${DRAFTPAPER_MOCK:-0}" = "1" ] || ! command -v brightnessctl >/dev/null 2>&1; then
    if [ -f "$BRT_MOCK" ]; then
      cat "$BRT_MOCK" 2>/dev/null || echo "50"
    else
      echo "50"
    fi
    return
  fi
  cur=$(brightnessctl get 2>/dev/null || echo 50)
  max=$(brightnessctl max 2>/dev/null || echo 100)
  if [ "$max" -gt 0 ]; then
    echo $((cur * 100 / max))
  else
    echo "50"
  fi
}

set_brightness() {
  action="$1"
  step="${2:-5}"
  cur=$(get_brightness)
  new_brt=$cur
  if [ "$action" = "up" ]; then
    new_brt=$((cur + step))
    if [ $new_brt -gt 100 ]; then new_brt=100; fi
  elif [ "$action" = "down" ]; then
    new_brt=$((cur - step))
    if [ $new_brt -lt 0 ]; then new_brt=0; fi
  elif [ "$action" = "set" ]; then
    new_brt=$step
    if [ $new_brt -gt 100 ]; then new_brt=100; fi
    if [ $new_brt -lt 0 ]; then new_brt=0; fi
  fi

  if [ "${DRAFTPAPER_MOCK:-0}" = "1" ] || ! command -v brightnessctl >/dev/null 2>&1; then
    echo "$new_brt" > "$BRT_MOCK"
  else
    brightnessctl -q set "${new_brt}%" 2>/dev/null || true
  fi
  echo "$new_brt"
}

debounce_and_notify() {
  type="$1"
  val="$2"
  text="$3"
  icon="$4"

  json_data="{\"type\":\"$type\",\"value\":$val,\"text\":\"$text\",\"icon\":\"$icon\",\"visible\":true}"
  echo "$json_data" > "$STATE_FILE"

  mkdir -p "$(dirname "$COUNTER_FILE")"
  prev=0
  if [ -f "$COUNTER_FILE" ]; then
    prev=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
  fi
  current=$((prev + 1))
  echo "$current" > "$COUNTER_FILE"

  if [ "${DRAFTPAPER_MOCK:-0}" != "1" ] && command -v eww >/dev/null 2>&1; then
    if eww -c "$CONFIG_DIR" ping >/dev/null 2>&1; then
      eww -c "$CONFIG_DIR" open top-osd 2>/dev/null || true
      eww -c "$CONFIG_DIR" update osd_data="$json_data" 2>/dev/null || true
    fi
  fi

  (
    sleep "$TIMEOUT"
    curr=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
    if [ "$curr" -eq "$current" ]; then
      if [ "${DRAFTPAPER_MOCK:-0}" != "1" ] && command -v eww >/dev/null 2>&1; then
        if eww -c "$CONFIG_DIR" ping >/dev/null 2>&1; then
          eww -c "$CONFIG_DIR" close top-osd 2>/dev/null || true
          eww -c "$CONFIG_DIR" update osd_data="{\"type\":\"none\",\"value\":0,\"text\":\"\",\"icon\":\"\",\"visible\":false}" 2>/dev/null || true
        fi
      fi
    fi
  ) </dev/null >/dev/null 2>&1 &
  disown 2>/dev/null || true
}

cmd="${1:-status}"

case "$cmd" in
  volume)
    subcmd="${2:-up}"
    step="${3:-5}"
    step="${step%\%}"
    read -r v m < <(set_volume "$subcmd" "$step")
    if [ "$m" = "true" ]; then
      icon="󰝟"
      text="VOL muted"
    else
      if [ "$v" -lt 33 ]; then
        icon="󰕿"
      elif [ "$v" -lt 66 ]; then
        icon="󰖀"
      else
        icon="󰕾"
      fi
      text="VOL ${v}%"
    fi
    debounce_and_notify "volume" "$v" "$text" "$icon"
    ;;
  brightness)
    subcmd="${2:-up}"
    step="${3:-5}"
    step="${step%\%}"
    v=$(set_brightness "$subcmd" "$step")
    if [ "$v" -lt 33 ]; then
      icon="󰃞"
    elif [ "$v" -lt 66 ]; then
      icon="󰃟"
    else
      icon="󰃠"
    fi
    text="BRT ${v}%"
    debounce_and_notify "brightness" "$v" "$text" "$icon"
    ;;
  status)
    if [ -f "$STATE_FILE" ]; then
      cat "$STATE_FILE"
    else
      read -r v m < <(get_volume)
      if [ "$m" = "true" ]; then
        icon="󰝟"
        text="VOL muted"
      else
        if [ "$v" -lt 33 ]; then
          icon="󰕿"
        elif [ "$v" -lt 66 ]; then
          icon="󰖀"
        else
          icon="󰕾"
        fi
        text="VOL ${v}%"
      fi
      echo "{\"type\":\"volume\",\"value\":$v,\"text\":\"$text\",\"icon\":\"$icon\",\"visible\":false}"
    fi
    ;;
  get)
    target="${2:-volume}"
    if [ "$target" = "brightness" ]; then
      get_brightness
    else
      get_volume
    fi
    ;;
  *)
    echo "Usage: $0 {volume [up|down|mute|set]|brightness [up|down|set]|status|get}"
    exit 1
    ;;
esac
