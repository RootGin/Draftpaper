#!/usr/bin/env python3
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from compositor import detect_compositor, get_active_window
except ImportError:
    from scripts.compositor import detect_compositor, get_active_window


def get_state_file():
    return Path(os.environ.get("DRAFTPAPER_PARKED_STATE", "/tmp/.draftpaper-parked.json"))


DRAFTING_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
ZONES_DOWN = 4



def read_state():
    sf = get_state_file()
    if sf.exists():
        try:
            with open(sf, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"parked": []}


def write_state(data):
    sf = get_state_file()
    tmp = sf.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f)
    tmp.replace(sf)



def perform_park(cell):
    comp = detect_compositor()
    active_win = get_active_window(comp)
    state = read_state()
    parked_list = [p for p in state.get("parked", []) if p.get("cell") != cell and p.get("id") != active_win.get("id")]
    parked_list.append({
        "cell": cell,
        "id": active_win.get("id"),
        "title": active_win.get("title"),
        "cls": active_win.get("cls"),
    })
    state["parked"] = parked_list
    write_state(state)

    if comp == "hyprland":
        try:
            subprocess.run(["hyprctl", "dispatch", "movetoworkspacesilent", "special:parked"], capture_output=True, timeout=1)
        except Exception:
            pass
    elif comp == "sway":
        try:
            subprocess.run(["swaymsg", "move", "to", "scratchpad"], capture_output=True, timeout=1)
        except Exception:
            pass


def perform_unpark(cell_or_id):
    comp = detect_compositor()
    state = read_state()
    parked_list = state.get("parked", [])
    found = None
    target_idx = None

    for idx, p in enumerate(parked_list):
        if str(p.get("cell")) == str(cell_or_id) or str(p.get("id")) == str(cell_or_id):
            found = p
            target_idx = idx
            break

    if found is not None:
        parked_list.pop(target_idx)
        state["parked"] = parked_list
        write_state(state)

        if comp == "hyprland":
            try:
                subprocess.run(["hyprctl", "dispatch", "movetoworkspace", f"current,address:{found.get('id')}"], capture_output=True, timeout=1)
            except Exception:
                pass
        elif comp == "sway":
            try:
                subprocess.run(["swaymsg", f"[con_id={found.get('id')}]", "focus"], capture_output=True, timeout=1)
            except Exception:
                pass


def build_slots_payload():
    state = read_state()
    parked_map = {p.get("cell"): p for p in state.get("parked", [])}

    left_slots = []
    right_slots = []

    for idx in range(ZONES_DOWN):
        cell_id = idx
        letter = DRAFTING_LETTERS[idx % len(DRAFTING_LETTERS)]
        item = parked_map.get(cell_id)
        left_slots.append({
            "cell": cell_id,
            "letter": letter,
            "occupied": item is not None,
            "title": item.get("title", "") if item else "",
            "cls": item.get("cls", "") if item else "",
            "window_id": item.get("id", "") if item else "",
            "side": "left",
        })

    for idx in range(ZONES_DOWN):
        cell_id = idx + ZONES_DOWN
        letter = DRAFTING_LETTERS[idx % len(DRAFTING_LETTERS)]
        item = parked_map.get(cell_id)
        right_slots.append({
            "cell": cell_id,
            "letter": letter,
            "occupied": item is not None,
            "title": item.get("title", "") if item else "",
            "cls": item.get("cls", "") if item else "",
            "window_id": item.get("id", "") if item else "",
            "side": "right",
        })

    return {"left": left_slots, "right": right_slots}


def print_payload():
    data = build_slots_payload()
    print(json.dumps(data), flush=True)


def update_eww():
    eww_bin = shutil.which("eww")
    if eww_bin:
        cfg = os.environ.get("EWW_CONFIG_DIR", str(Path(__file__).resolve().parent.parent))
        data = json.dumps(build_slots_payload())
        subprocess.run([eww_bin, "-c", cfg, "update", f"parked_slots={data}"], capture_output=True)


def stream_events():
    print_payload()
    comp = detect_compositor()
    last_mtime = 0
    sf = get_state_file()

    while True:
        try:
            if sf.exists():
                mtime = sf.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    print_payload()
            time.sleep(0.5)
        except Exception:
            time.sleep(1)


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--oneshot":
            print_payload()
            return
        elif cmd == "park" and len(sys.argv) > 2:
            try:
                cell = int(sys.argv[2])
                perform_park(cell)
                update_eww()
            except Exception:
                pass
            return
        elif cmd == "unpark" and len(sys.argv) > 2:
            perform_unpark(sys.argv[2])
            update_eww()
            return

    stream_events()


if __name__ == "__main__":
    main()
