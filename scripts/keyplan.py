#!/usr/bin/env python3
import glob
import json
import os
import subprocess
import sys


def detect_monitors():
    custom = os.environ.get("DRAFTPAPER_KEYPLAN_DATA")
    if custom:
        try:
            return json.loads(custom)
        except Exception:
            pass

    try:
        res = subprocess.run(["niri", "msg", "--json", "outputs"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and res.stdout.strip():
            raw = json.loads(res.stdout.strip())
            monitors = []
            sorted_names = sorted(raw.keys())
            for idx, name in enumerate(sorted_names, start=1):
                monitors.append({
                    "name": name,
                    "active": idx == 1,
                    "label": str(idx),
                })
            if monitors:
                return {"count": len(monitors), "monitors": monitors}
    except Exception:
        pass

    try:
        res = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and res.stdout.strip():
            raw = json.loads(res.stdout.strip())
            monitors = []
            for idx, mon in enumerate(raw, start=1):
                monitors.append({
                    "name": mon.get("name", str(idx)),
                    "active": mon.get("focused", idx == 1),
                    "label": str(idx),
                })
            if monitors:
                return {"count": len(monitors), "monitors": monitors}
    except Exception:
        pass

    connected_drm = []
    for status_file in glob.glob("/sys/class/drm/card*-*/status"):
        try:
            with open(status_file, "r") as f:
                if f.read().strip() == "connected":
                    name = os.path.basename(os.path.dirname(status_file))
                    if name.startswith("card"):
                        parts = name.split("-", 1)
                        if len(parts) > 1:
                            name = parts[1]
                    connected_drm.append(name)
        except Exception:
            continue

    if connected_drm:
        monitors = []
        for idx, name in enumerate(sorted(connected_drm), start=1):
            monitors.append({
                "name": name,
                "active": idx == 1,
                "label": str(idx),
            })
        return {"count": len(monitors), "monitors": monitors}

    return {
        "count": 1,
        "monitors": [{"name": "primary", "active": true, "label": "1"}]
    }


def main():
    data = detect_monitors()
    print(json.dumps(data), flush=True)


if __name__ == "__main__":
    main()
