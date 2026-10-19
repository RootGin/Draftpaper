#!/usr/bin/env bash
set -e

CONFIG_DIR="${DRAFTPAPER_CONFIG_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if ! eww -c "$CONFIG_DIR" ping >/dev/null 2>&1; then
  eww -c "$CONFIG_DIR" daemon &
  while ! eww -c "$CONFIG_DIR" ping >/dev/null 2>&1; do
    sleep 0.1
  done
fi

if command -v end-rs >/dev/null 2>&1; then
  if ! pgrep -x end-rs >/dev/null 2>&1; then
    end-rs daemon &
  fi
fi

eww -c "$CONFIG_DIR" open-many background title-block top-margin side-margins-left side-margins-right bottom-margin
