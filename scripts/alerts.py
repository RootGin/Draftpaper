#!/usr/bin/env python3
import glob
import json
import os
import subprocess
import sys


def has_nerd_fonts():
    if os.environ.get("DRAFTPAPER_GLYPHS") == "0" or os.environ.get("NERD_FONTS") == "0":
        return False
    if os.environ.get("DRAFTPAPER_GLYPHS") == "1" or os.environ.get("NERD_FONTS") == "1":
        return True
    try:
        res = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "Nerd Font" in line:
                    return True
    except Exception:
        pass
    return False


def check_battery():
    battery_low = False
    battery_pct = None
    for bat_path in glob.glob("/sys/class/power_supply/BAT*"):
        try:
            status_file = os.path.join(bat_path, "status")
            cap_file = os.path.join(bat_path, "capacity")
            if os.path.exists(status_file) and os.path.exists(cap_file):
                with open(status_file, "r") as f:
                    status = f.read().strip()
                with open(cap_file, "r") as f:
                    cap = int(f.read().strip())
                battery_pct = cap
                if status == "Discharging" and cap < 15:
                    battery_low = True
                    break
        except Exception:
            continue
    return battery_low, battery_pct


def check_temperatures():
    hot = False
    max_temp = 0.0
    for temp_input in glob.glob("/sys/class/hwmon/hwmon*/temp*_input"):
        try:
            with open(temp_input, "r") as f:
                val = float(f.read().strip()) / 1000.0
            if val > max_temp:
                max_temp = val
            label_file = temp_input.replace("_input", "_label")
            label = ""
            if os.path.exists(label_file):
                with open(label_file, "r") as f:
                    label = f.read().strip().lower()
            if "nvme" in label or "composite" in label:
                if val >= 60.0:
                    hot = True
            elif val >= 85.0:
                hot = True
        except Exception:
            continue
    return hot, max_temp


def main():
    use_glyphs = has_nerd_fonts()
    battery_low, battery_pct = check_battery()
    hot, max_temp = check_temperatures()

    urgent = battery_low or hot
    alert_parts = []

    if hot:
        glyph = "󰘚" if use_glyphs else "HOT"
        alert_parts.append(f"{glyph} {int(max_temp)}°" if use_glyphs else f"HOT {int(max_temp)}°")

    if battery_low and battery_pct is not None:
        glyph = "󰂃" if use_glyphs else "BAT"
        alert_parts.append(f"{glyph} {battery_pct}%" if use_glyphs else f"BAT {battery_pct}%")

    text = "  ".join(alert_parts)

    payload = {
        "urgent": urgent,
        "hot": hot,
        "battery_low": battery_low,
        "text": text
    }
    print(json.dumps(payload), flush=True)


if __name__ == "__main__":
    main()
