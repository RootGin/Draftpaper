import json
import os
import shutil
import subprocess
from pathlib import Path


def detect_compositor():
    override = os.environ.get("DRAFTPAPER_COMPOSITOR")
    if override:
        return override
    if os.environ.get("NIRI_SOCKET"):
        return "niri"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if os.environ.get("SWAYSOCK"):
        return "sway"
    if shutil.which("hyprctl"):
        try:
            r = subprocess.run(["hyprctl", "-j", "activeworkspace"], capture_output=True, text=True, timeout=0.5)
            if r.returncode == 0:
                return "hyprland"
        except Exception:
            pass
    if shutil.which("swaymsg"):
        try:
            r = subprocess.run(["swaymsg", "-t", "get_workspaces"], capture_output=True, text=True, timeout=0.5)
            if r.returncode == 0:
                return "sway"
        except Exception:
            pass
    if shutil.which("niri"):
        try:
            r = subprocess.run(["niri", "msg", "-j", "workspaces"], capture_output=True, text=True, timeout=0.5)
            if r.returncode == 0:
                return "niri"
        except Exception:
            pass
    return "fallback"


def get_active_window(comp=None):
    if comp is None:
        comp = detect_compositor()
    if comp == "hyprland":
        try:
            res = subprocess.run(["hyprctl", "-j", "activewindow"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                addr = data.get("address", "")
                title = data.get("title", "")
                cls = data.get("class", "")
                pid = data.get("pid")
                if addr:
                    return {"id": addr, "title": title, "cls": cls, "pid": pid}
        except Exception:
            pass
    elif comp == "niri":
        try:
            res = subprocess.run(["niri", "msg", "-j", "focused-window"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                w_id = data.get("id")
                title = data.get("title", "")
                cls = data.get("app_id", "")
                pid = data.get("pid")
                if w_id is not None:
                    return {"id": str(w_id), "title": title, "cls": cls, "pid": pid}
        except Exception:
            pass
    elif comp == "sway":
        try:
            res = subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0:
                tree = json.loads(res.stdout)
                focused_node = None

                def find_focused(node):
                    nonlocal focused_node
                    if node.get("focused"):
                        focused_node = node
                        return
                    for c in node.get("nodes", []):
                        find_focused(c)
                        if focused_node:
                            return
                    for c in node.get("floating_nodes", []):
                        find_focused(c)
                        if focused_node:
                            return

                find_focused(tree)
                if focused_node:
                    return {
                        "id": str(focused_node.get("id")),
                        "title": focused_node.get("name", ""),
                        "cls": focused_node.get("app_id") or focused_node.get("window_properties", {}).get("class", ""),
                        "pid": focused_node.get("pid"),
                    }
        except Exception:
            pass
    mock_pid = os.environ.get("DRAFTPAPER_ACTIVE_WINDOW_PID")
    pid_val = int(mock_pid) if mock_pid and mock_pid.isdigit() else None
    return {
        "id": "win-demo",
        "title": "Terminal",
        "cls": "Alacritty",
        "pid": pid_val,
    }


def get_process_cwd(pid):
    if not pid:
        return None
    try:
        pid_int = int(pid)
    except (ValueError, TypeError):
        return None
    proc_path = Path(f"/proc/{pid_int}")
    if not proc_path.exists():
        return None
    target_pid = pid_int
    try:
        children_file = proc_path / "task" / str(pid_int) / "children"
        if children_file.exists():
            children = children_file.read_text().strip().split()
            while children:
                target_pid = int(children[-1])
                sub = Path(f"/proc/{target_pid}/task/{target_pid}/children")
                if sub.exists():
                    sub_children = sub.read_text().strip().split()
                    if sub_children:
                        children = sub_children
                        continue
                break
        cwd = os.readlink(f"/proc/{target_pid}/cwd")
        if os.path.isdir(cwd):
            return cwd
    except Exception:
        pass
    try:
        cwd = os.readlink(f"/proc/{pid_int}/cwd")
        if os.path.isdir(cwd):
            return cwd
    except Exception:
        pass
    return None
