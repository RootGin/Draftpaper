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
    from compositor import detect_compositor
except ImportError:
    from scripts.compositor import detect_compositor


def get_state_file():
    return Path(os.environ.get("DRAFTPAPER_WORKSPACE_STATE", "/tmp/draftpaper-workspaces.json"))


APP_MAPPINGS = [
    (["firefox", "librewolf", "zen"], "󰈹", "web"),
    (["chromium", "chrome", "brave"], "󰊯", "web"),
    (["alacritty", "foot", "kitty", "xterm", "wezterm", "terminal", "konsole", "ghostty"], "", "term"),
    (["code", "codium"], "󰨞", "code"),
    (["claude"], "󰚩", "ai"),
    (["thunderbird", "evolution", "geary"], "󰇰", "mail"),
    (["signal"], "󰭹", "chat"),
    (["telegram"], "", "tg"),
    (["teams"], "󰊻", "team"),
    (["slack"], "󰒱", "slk"),
    (["discord", "vesktop"], "󰙯", "disc"),
    (["spotify"], "󰓇", "mus"),
    (["mpv", "vlc", "totem", "celluloid"], "󰕼", "med"),
    (["gimp", "inkscape", "krita"], "󰸾", "draw"),
    (["libreoffice", "soffice"], "󰈙", "doc"),
    (["nautilus", "thunar", "pcmanfm", "nemo", "dolphin"], "󰉋", "file"),
    (["evince", "zathura", "okular", "papers"], "󰈦", "pdf"),
    (["keepassxc", "bitwarden"], "󰌋", "pass"),
    (["obs"], "󰑋", "rec"),
    (["steam"], "", "game"),
    (["emacs"], "", "emacs"),
]
DEFAULT_GLYPH = "󰖯"
DEFAULT_BADGE = "app"


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


def get_app_representation(app_id, use_glyphs=None):
    if use_glyphs is None:
        use_glyphs = has_nerd_fonts()
    lowered = (app_id or "").lower()
    for prefixes, glyph, badge in APP_MAPPINGS:
        if any(p in lowered for p in prefixes):
            return glyph if use_glyphs else badge
    return DEFAULT_GLYPH if use_glyphs else DEFAULT_BADGE



def read_fallback_state():
    state_file = get_state_file()
    if state_file.is_file():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "focused": 1,
        "active": [1],
        "apps": {
            "1": []
        }
    }


def write_fallback_state(state):
    state_file = get_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state), encoding="utf-8")


def get_workspaces_hyprland():
    use_glyphs = has_nerd_fonts()
    active_ws_res = subprocess.run(["hyprctl", "-j", "activeworkspace"], capture_output=True, text=True, timeout=1)
    clients_res = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True, text=True, timeout=1)

    focused_id = 1
    if active_ws_res.returncode == 0:
        try:
            focused_id = json.loads(active_ws_res.stdout).get("id", 1)
        except Exception:
            pass

    clients = []
    if clients_res.returncode == 0:
        try:
            clients = json.loads(clients_res.stdout)
        except Exception:
            pass

    apps_by_ws = {i: [] for i in range(1, 11)}
    active_set = {focused_id}

    for c in clients:
        ws_id = c.get("workspace", {}).get("id")
        if ws_id in apps_by_ws:
            active_set.add(ws_id)
            app_id = c.get("initialClass") or c.get("class") or ""
            rep = get_app_representation(app_id, use_glyphs=use_glyphs)
            if rep not in apps_by_ws[ws_id] and len(apps_by_ws[ws_id]) < 3:
                apps_by_ws[ws_id].append(rep)

    workspaces = []
    for i in range(1, 11):
        workspaces.append({
            "id": i,
            "name": str(i),
            "focused": (i == focused_id),
            "active": (i in active_set),
            "apps": apps_by_ws[i]
        })
    return workspaces


def get_workspaces_sway():
    use_glyphs = has_nerd_fonts()
    ws_res = subprocess.run(["swaymsg", "-t", "get_workspaces"], capture_output=True, text=True, timeout=1)
    tree_res = subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True, text=True, timeout=1)

    focused_id = 1
    active_set = set()
    if ws_res.returncode == 0:
        try:
            ws_data = json.loads(ws_res.stdout)
            for w in ws_data:
                num = w.get("num")
                if isinstance(num, int):
                    active_set.add(num)
                    if w.get("focused"):
                        focused_id = num
        except Exception:
            pass

    active_set.add(focused_id)
    apps_by_ws = {i: [] for i in range(1, 11)}

    def extract_nodes(node, current_ws=None):
        if node.get("type") == "workspace":
            try:
                current_ws = int(node.get("num", 0))
            except Exception:
                current_ws = None
        app_id = node.get("app_id") or node.get("window_properties", {}).get("class") or ""
        if current_ws and current_ws in apps_by_ws and app_id:
            rep = get_app_representation(app_id, use_glyphs=use_glyphs)
            if rep not in apps_by_ws[current_ws] and len(apps_by_ws[current_ws]) < 3:
                apps_by_ws[current_ws].append(rep)
        for child in node.get("nodes", []):
            extract_nodes(child, current_ws)
        for child in node.get("floating_nodes", []):
            extract_nodes(child, current_ws)

    if tree_res.returncode == 0:
        try:
            extract_nodes(json.loads(tree_res.stdout))
        except Exception:
            pass

    workspaces = []
    for i in range(1, 11):
        workspaces.append({
            "id": i,
            "name": str(i),
            "focused": (i == focused_id),
            "active": (i in active_set),
            "apps": apps_by_ws[i]
        })
    return workspaces


def get_workspaces_niri():
    use_glyphs = has_nerd_fonts()
    ws_res = subprocess.run(["niri", "msg", "-j", "workspaces"], capture_output=True, text=True, timeout=1)
    win_res = subprocess.run(["niri", "msg", "-j", "windows"], capture_output=True, text=True, timeout=1)

    focused_id = 1
    active_set = set()
    ws_id_to_idx = {}
    parking_ids = set()
    if ws_res.returncode == 0:
        try:
            ws_data = json.loads(ws_res.stdout)
            for w in ws_data:
                idx = w.get("idx")
                w_id = w.get("id")
                if w.get("name") == os.environ.get("DRAFTPAPER_PARK_WORKSPACE", "parked"):
                    parking_ids.add(w_id)
                    continue
                if isinstance(idx, int):
                    active_set.add(idx)
                    if w_id is not None:
                        ws_id_to_idx[w_id] = idx
                    if w.get("is_focused"):
                        focused_id = idx
        except Exception:
            pass

    active_set.add(focused_id)
    apps_by_ws = {i: [] for i in range(1, 11)}

    if win_res.returncode == 0:
        try:
            windows = json.loads(win_res.stdout)
            for win in windows:
                raw_id = win.get("workspace_id")
                if raw_id in parking_ids:
                    continue
                target_idx = ws_id_to_idx.get(raw_id, raw_id)
                if target_idx in apps_by_ws:
                    active_set.add(target_idx)
                    app_id = win.get("app_id") or ""
                    rep = get_app_representation(app_id, use_glyphs=use_glyphs)
                    if rep not in apps_by_ws[target_idx] and len(apps_by_ws[target_idx]) < 3:
                        apps_by_ws[target_idx].append(rep)
        except Exception:
            pass

    workspaces = []
    for i in range(1, 11):
        workspaces.append({
            "id": i,
            "name": str(i),
            "focused": (i == focused_id),
            "active": (i in active_set),
            "apps": apps_by_ws[i]
        })
    return workspaces


def get_workspaces_fallback():
    use_glyphs = has_nerd_fonts()
    state = read_fallback_state()
    focused_id = state.get("focused", 1)
    active_list = state.get("active", [1])
    raw_apps = state.get("apps", {})

    workspaces = []
    for i in range(1, 11):
        raw_list = raw_apps.get(str(i), [])
        processed_apps = []
        for a in raw_list:
            rep = get_app_representation(a, use_glyphs=use_glyphs)
            if rep not in processed_apps and len(processed_apps) < 3:
                processed_apps.append(rep)
        is_focused = (i == focused_id)
        is_active = (i in active_list or is_focused or len(processed_apps) > 0)
        workspaces.append({
            "id": i,
            "name": str(i),
            "focused": is_focused,
            "active": is_active,
            "apps": processed_apps
        })
    return workspaces


def get_workspaces():
    comp = detect_compositor()
    if comp == "hyprland":
        try:
            return get_workspaces_hyprland()
        except Exception:
            pass
    elif comp == "sway":
        try:
            return get_workspaces_sway()
        except Exception:
            pass
    elif comp == "niri":
        try:
            return get_workspaces_niri()
        except Exception:
            pass
    return get_workspaces_fallback()


def switch_workspace(ws_id):
    ws_id = int(ws_id)
    comp = detect_compositor()

    if comp == "hyprland":
        try:
            subprocess.run(["hyprctl", "dispatch", "workspace", str(ws_id)], capture_output=True, timeout=1)
        except Exception:
            pass
    elif comp == "sway":
        try:
            subprocess.run(["swaymsg", "workspace", str(ws_id)], capture_output=True, timeout=1)
        except Exception:
            pass
    elif comp == "niri":
        try:
            subprocess.run(["niri", "msg", "action", "focus-workspace", str(ws_id)], capture_output=True, timeout=1)
        except Exception:
            pass

    state = read_fallback_state()
    state["focused"] = ws_id
    active_set = set(state.get("active", [1]))
    active_set.add(ws_id)
    state["active"] = sorted(list(active_set))
    write_fallback_state(state)


def stream_workspaces():
    last_output = ""
    comp = detect_compositor()

    initial = json.dumps(get_workspaces())
    print(initial, flush=True)
    last_output = initial

    if comp == "hyprland":
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = f"{xdg}/hypr/{sig}/.socket2.sock"
        if os.path.exists(sock_path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(sock_path)
                s_file = s.makefile("r", encoding="utf-8")
                while True:
                    line = s_file.readline()
                    if not line:
                        break
                    current = json.dumps(get_workspaces())
                    if current != last_output:
                        print(current, flush=True)
                        last_output = current
                return
            except Exception:
                pass

    state_file = get_state_file()
    last_mtime = state_file.stat().st_mtime if state_file.exists() else 0
    while True:
        time.sleep(0.3)
        curr_mtime = state_file.stat().st_mtime if state_file.exists() else 0
        if curr_mtime != last_mtime:
            last_mtime = curr_mtime
            current = json.dumps(get_workspaces())
            if current != last_output:
                print(current, flush=True)
                last_output = current
        else:
            current = json.dumps(get_workspaces())
            if current != last_output:
                print(current, flush=True)
                last_output = current


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "switch" and len(sys.argv) > 2:
            switch_workspace(sys.argv[2])
            sys.exit(0)
        elif sys.argv[1] in ("--oneshot", "get"):
            print(json.dumps(get_workspaces()), flush=True)
            sys.exit(0)

    stream_workspaces()


if __name__ == "__main__":
    main()
