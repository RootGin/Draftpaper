import glob
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_HISTORY_FILE = "/tmp/.draftpaper-launcher-history.json"
ACTIVE_MENU_FILE = "/tmp/.draftpaper-active-menu.json"


def get_history_file():
    return os.environ.get("DRAFTPAPER_LAUNCHER_HISTORY", DEFAULT_HISTORY_FILE)


def get_app_dirs():
    env_dirs = os.environ.get("DRAFTPAPER_APP_DIRS")
    if env_dirs:
        return [Path(p.strip()) for p in env_dirs.split(os.pathsep) if p.strip()]
    home = Path.home()
    return [
        home / ".local" / "share" / "applications",
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
    ]


def load_history():
    hist_file = Path(get_history_file())
    if hist_file.is_file():
        try:
            return json.loads(hist_file.read_text())
        except Exception:
            return {}
    return {}


def save_history(history):
    hist_file = Path(get_history_file())
    hist_file.parent.mkdir(parents=True, exist_ok=True)
    hist_file.write_text(json.dumps(history, indent=2))


def map_glyph(name, icon, categories, exec_cmd):
    combined = f"{name} {icon} {categories} {exec_cmd}".lower()
    if any(k in combined for k in ["firefox", "chrome", "chromium", "brave", "browser", "web"]):
        return "󰈹"
    if any(k in combined for k in ["foot", "terminal", "kitty", "alacritty", "wezterm", "console"]):
        return ""
    if any(k in combined for k in ["calc", "calculator", "math"]):
        return "󰃬"
    if any(k in combined for k in ["code", "vim", "nvim", "editor", "text", "sublime"]):
        return "󰨞"
    if any(k in combined for k in ["file", "nautilus", "thunar", "dolphin", "manager"]):
        return "󰝰"
    if any(k in combined for k in ["music", "audio", "spotify", "sound", "player"]):
        return "󰓇"
    if any(k in combined for k in ["video", "vlc", "mpv", "media"]):
        return "󰕼"
    if any(k in combined for k in ["setting", "control", "pref"]):
        return "󰒓"
    return "󰵆"


def clean_exec(cmd):
    cleaned = re.sub(r"%[a-zA-Z]", "", cmd)
    return cleaned.strip()


def parse_desktop_file(path):
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    in_entry = False
    data = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry:
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k not in data:
                data[k] = v

    if data.get("NoDisplay", "").lower() == "true":
        return None
    if "Type" in data and data["Type"].lower() != "application":
        return None
    if "Exec" not in data or "Name" not in data:
        return None

    name = data["Name"]
    generic_name = data.get("GenericName", "")
    comment = data.get("Comment", "")
    keywords = data.get("Keywords", "")
    categories = data.get("Categories", "")
    icon = data.get("Icon", "")
    raw_exec = data["Exec"]
    exec_cmd = clean_exec(raw_exec)
    desc = generic_name or comment or name
    glyph = map_glyph(name, icon, categories, exec_cmd)

    return {
        "id": path.name,
        "name": name,
        "generic_name": generic_name,
        "comment": comment,
        "keywords": keywords,
        "desc": desc,
        "icon": icon,
        "glyph": glyph,
        "exec": exec_cmd,
    }


def scan_applications():
    apps = {}
    for app_dir in get_app_dirs():
        if not app_dir.is_dir():
            continue
        for p in app_dir.glob("*.desktop"):
            if p.name not in apps:
                parsed = parse_desktop_file(p)
                if parsed:
                    apps[p.name] = parsed
    return list(apps.values())


def calculate_usage_score(app_id, history):
    entry = history.get(app_id)
    if not entry:
        return 0.0
    count = entry.get("count", 0)
    last_used = entry.get("last_used", 0)
    days_since = max(0.0, (time.time() - last_used) / 86400.0)
    decayed = count / (1.0 + days_since / 7.0)
    return min(200.0, 40.0 * math.log1p(decayed))


def score_text(pattern, text):
    p = pattern.lower()
    t = text.lower()
    if not p:
        return 0.0
    if t == p:
        return 1200.0
    if t.startswith(p):
        return 1000.0 - len(t)
    wb_idx = t.find(" " + p)
    if wb_idx != -1:
        return 800.0 - wb_idx
    sub_idx = t.find(p)
    if sub_idx != -1:
        return 600.0 - sub_idx

    ti = 0
    pi = 0
    score = 0.0
    consecutive = 0
    while pi < len(p) and ti < len(t):
        if p[pi] == t[ti]:
            score += 10.0 + (consecutive * 5.0)
            if ti == 0 or t[ti - 1] in " -_./":
                score += 20.0
            consecutive += 1
            pi += 1
        else:
            consecutive = 0
        ti += 1

    if pi == len(p):
        return max(50.0, score - len(t))
    return -1.0


def rank_applications(apps, query):
    history = load_history()
    q = query.strip()
    ranked = []

    for app in apps:
        usage = calculate_usage_score(app["id"], history)
        if not q:
            ranked.append((usage, app["name"], app))
        else:
            name_score = score_text(q, app["name"])
            generic_score = score_text(q, app.get("generic_name", "")) * 0.8
            keyword_score = score_text(q, app.get("keywords", "")) * 0.7
            id_score = score_text(q, app["id"]) * 0.6
            match_score = max(name_score, generic_score, keyword_score, id_score)
            if match_score >= 0:
                total_score = match_score + usage
                ranked.append((total_score, app["name"], app))

    ranked.sort(key=lambda x: (-x[0], x[1].lower()))
    return [item[2] for item in ranked]


def list_applications_json(query=""):
    all_apps = scan_applications()
    ranked = rank_applications(all_apps, query)
    items = []
    for idx, app in enumerate(ranked):
        items.append(
            {
                "i": idx,
                "num": f"{idx + 1:02d}",
                "glyph": app["glyph"],
                "name": app["name"],
                "desc": app["desc"],
                "exec": app["exec"],
                "id": app["id"],
            }
        )

    prefix = "RUN ▸ "
    header = f"REGISTER OF APPLICATIONS · {len(items)} OF {len(all_apps)}"
    return {
        "header": header,
        "matches": len(items),
        "total": len(all_apps),
        "prefix": prefix,
        "query": query,
        "items": items,
    }


def record_launch(app_id):
    history = load_history()
    entry = history.get(app_id, {"count": 0, "last_used": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["last_used"] = time.time()
    history[app_id] = entry
    save_history(history)


def eww_call(args):
    eww_dir = os.environ.get("EWW_DIR", str(Path(__file__).resolve().parent.parent))
    cmd = ["eww", "-c", eww_dir] + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    except Exception:
        return None


def launch_app(target, dry_run=False):
    apps = scan_applications()
    matched = None
    if target.isdigit():
        idx = int(target)
        if 0 <= idx < len(apps):
            matched = apps[idx]
    if not matched:
        for a in apps:
            if a["id"] == target or a["name"].lower() == target.lower():
                matched = a
                break
    if not matched:
        for a in apps:
            if target.lower() in a["name"].lower():
                matched = a
                break

    if not matched:
        target_exec = clean_exec(target)
        target_id = target
    else:
        target_exec = matched["exec"]
        target_id = matched["id"]

    record_launch(target_id)

    if not dry_run and target_exec:
        try:
            subprocess.Popen(
                shlex.split(target_exec),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            sys.stderr.write(f"Failed to launch {target_exec}: {e}\n")

    eww_call(["update", "launcher_visible=false"])
    eww_call(["close", "launcher"])


def handle_up(current_index_str, total_items_str):
    current_index = int(current_index_str)
    total_items = int(total_items_str)
    next_index = (current_index - 1) % total_items if total_items > 0 else 0
    eww_call(["update", f"launcher_index={next_index}"])
    sys.stdout.write(f"{next_index}\n")


def handle_down(current_index_str, total_items_str):
    current_index = int(current_index_str)
    total_items = int(total_items_str)
    next_index = (current_index + 1) % total_items if total_items > 0 else 0
    eww_call(["update", f"launcher_index={next_index}"])
    sys.stdout.write(f"{next_index}\n")


def handle_toggle():
    active = eww_call(["active-windows"])
    is_open = active and "launcher" in active.stdout
    if is_open:
        eww_call(["update", "launcher_visible=false"])
        eww_call(["close", "launcher"])
    else:
        eww_call(["update", "launcher_visible=true", "launcher_query=", "launcher_index=0"])
        eww_call(["open", "launcher"])


def handle_close():
    active_menu = Path(ACTIVE_MENU_FILE)
    if active_menu.is_file():
        try:
            menu_info = json.loads(active_menu.read_text())
            fifo_path = menu_info.get("fifo")
            if fifo_path and Path(fifo_path).exists():
                with open(fifo_path, "w") as f:
                    f.write("\n")
        except Exception:
            pass
    eww_call(["update", "launcher_visible=false"])
    eww_call(["close", "launcher"])


def handle_query(query_str):
    eww_call(["update", f"launcher_query={query_str}", "launcher_index=0"])


def handle_menu_select(choice):
    active_menu = Path(ACTIVE_MENU_FILE)
    if not active_menu.is_file():
        sys.exit(1)
    try:
        menu_info = json.loads(active_menu.read_text())
        fifo_path = menu_info.get("fifo")
        if fifo_path and Path(fifo_path).exists():
            with open(fifo_path, "w") as f:
                f.write(f"{choice}\n")
    except Exception:
        sys.exit(1)


def run_menu(prompt="CHOOSE"):
    pid = os.getpid()
    fifo_path = f"/tmp/draftpaper-menu-{pid}.fifo"
    if os.path.exists(fifo_path):
        os.unlink(fifo_path)
    os.mkfifo(fifo_path)

    active_file = Path(ACTIVE_MENU_FILE)
    active_file.write_text(json.dumps({"pid": pid, "fifo": fifo_path, "prompt": prompt}))

    raw_input = sys.stdin.read()
    lines = [line.strip() for line in raw_input.splitlines() if line.strip()]

    menu_items = []
    for idx, line in enumerate(lines):
        menu_items.append(
            {
                "i": idx,
                "num": f"{idx + 1:02d}",
                "glyph": "▸",
                "name": line,
                "desc": "",
                "exec": line,
                "id": f"menu-{idx}",
            }
        )

    menu_state = {
        "header": f"REGISTER OF SELECTIONS · {len(menu_items)} ITEMS",
        "matches": len(menu_items),
        "total": len(menu_items),
        "prefix": f"{prompt} ▸ ",
        "query": "",
        "items": menu_items,
    }

    eww_call(["update", f"launcher_entries={json.dumps(menu_state)}", "launcher_visible=true", "launcher_index=0"])
    eww_call(["open", "launcher"])

    selected = ""
    try:
        with open(fifo_path, "r") as fifo:
            selected = fifo.read().strip()
    finally:
        if os.path.exists(fifo_path):
            os.unlink(fifo_path)
        if active_file.exists():
            active_file.unlink()
        eww_call(["update", "launcher_visible=false"])
        eww_call(["close", "launcher"])

    if selected:
        sys.stdout.write(f"{selected}\n")
        sys.exit(0)
    else:
        sys.exit(1)


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(list_applications_json(q)))
    elif sys.argv[1] == "launch":
        target = sys.argv[2] if len(sys.argv) > 2 else ""
        dry_run = "--dry-run" in sys.argv
        launch_app(target, dry_run=dry_run)
    elif sys.argv[1] == "up":
        cur = sys.argv[2] if len(sys.argv) > 2 else "0"
        tot = sys.argv[3] if len(sys.argv) > 3 else "1"
        handle_up(cur, tot)
    elif sys.argv[1] == "down":
        cur = sys.argv[2] if len(sys.argv) > 2 else "0"
        tot = sys.argv[3] if len(sys.argv) > 3 else "1"
        handle_down(cur, tot)
    elif sys.argv[1] == "toggle":
        handle_toggle()
    elif sys.argv[1] == "close":
        handle_close()
    elif sys.argv[1] == "query":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        handle_query(q)
    elif sys.argv[1] == "menu-select":
        choice = sys.argv[2] if len(sys.argv) > 2 else ""
        handle_menu_select(choice)
    elif sys.argv[1] == "menu":
        prompt = "CHOOSE"
        if "--prompt" in sys.argv:
            p_idx = sys.argv.index("--prompt")
            if p_idx + 1 < len(sys.argv):
                prompt = sys.argv[p_idx + 1]
        run_menu(prompt=prompt)


if __name__ == "__main__":
    main()
