#!/usr/bin/env python3
import fcntl
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from compositor import detect_compositor
except ImportError:
    from scripts.compositor import detect_compositor

DRAFTING_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def zones_down():
    try:
        return max(1, int(os.environ.get("DRAFTPAPER_ZONES_DOWN", "4")))
    except ValueError:
        return 4


def park_name():
    return os.environ.get("DRAFTPAPER_PARK_WORKSPACE", "parked")


def get_state_file():
    default = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "draftpaper-parked.json"
    return Path(os.environ.get("DRAFTPAPER_PARKED_STATE", str(default)))


def read_state():
    try:
        data = json.loads(get_state_file().read_text())
        if isinstance(data.get("parked"), list):
            data.setdefault("seq", 0)
            return data
    except Exception:
        pass
    return {"seq": 0, "parked": []}


def write_state(data):
    sf = get_state_file()
    tmp = sf.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(sf)


@contextmanager
def locked():
    lock = get_state_file().with_suffix(".lock")
    with open(lock, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def free(taken, total, after, step):
    n = max(total, 1)
    for k in range(1, total + 1):
        c = (after + step * k) % n
        if c not in taken:
            return c
    return max(max(taken, default=0), total - 1) + 1


def _run(cmd, timeout=2):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def niri(*args):
    r = _run(["niri", "msg", *args])
    return r.stdout if r is not None and r.returncode == 0 else None


class Niri:
    name = "niri"
    live = True

    def snapshot(self):
        try:
            wins = json.loads(niri("-j", "windows") or "[]")
            wss = json.loads(niri("-j", "workspaces") or "[]")
        except Exception:
            return [], []
        wss_out = [{"id": w.get("id"), "idx": w.get("idx"), "name": w.get("name"),
                    "output": w.get("output"), "focused": bool(w.get("is_focused"))} for w in wss]
        park_ids = {w["id"] for w in wss_out if w["name"] == park_name()}
        out = []
        for w in wins:
            pos = (w.get("layout") or {}).get("pos_in_scrolling_layout")
            out.append({
                "id": str(w.get("id")),
                "title": w.get("title") or "",
                "cls": w.get("app_id") or "",
                "ws": w.get("workspace_id"),
                "focused": bool(w.get("is_focused")),
                "floating": bool(w.get("is_floating")),
                "col": pos[0] if pos else None,
                "parked": w.get("workspace_id") in park_ids,
            })
        return out, wss_out

    def _ensure_park_ws(self, wss):
        if any(w["name"] == park_name() for w in wss):
            return True
        out = next((w["output"] for w in wss if w["focused"]), None)
        mine = sorted((w for w in wss if w["output"] == out and not w["name"]), key=lambda w: w["idx"])
        if not mine:
            return False
        return niri("action", "set-workspace-name", "--workspace", str(mine[-1]["idx"]), park_name()) is not None

    def park(self, win, wss):
        if not self._ensure_park_ws(wss):
            return False
        return niri("action", "move-window-to-workspace", "--window-id", win["id"], "--focus", "false", park_name()) is not None

    def _target(self, entry, wss):
        focused = next((w for w in wss if w["focused"]), None)
        home = next((w for w in wss if w["id"] == entry.get("ws_id")), None)
        if home is None and focused is not None:
            home = next((w for w in wss if w["output"] == focused["output"] and w["idx"] == entry.get("ws_idx")
                         and w["name"] != park_name()), None)
        home = home or focused
        if home is None:
            return None
        if home["name"]:
            return home["name"]
        return str(home["idx"]) if focused and home["output"] == focused["output"] else None

    def restore(self, entry, wss):
        ref = self._target(entry, wss)
        if ref is None:
            return False
        wid = entry["id"]
        if niri("action", "move-window-to-workspace", "--window-id", wid, "--focus", "false", ref) is None:
            return False
        niri("action", "focus-window", "--id", wid)
        if entry.get("floating"):
            niri("action", "move-window-to-floating", "--id", wid)
        elif entry.get("col"):
            niri("action", "move-column-to-index", str(entry["col"]))
        return True

    def focus(self, wid):
        niri("action", "focus-window", "--id", wid)

    def focus_dir(self, d):
        niri("action", "focus-column-right" if d > 0 else "focus-column-left")

    def events(self):
        try:
            p = subprocess.Popen(["niri", "msg", "--json", "event-stream"], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True)
        except Exception:
            return
        for line in p.stdout:
            yield line


class Hyprland:
    name = "hyprland"
    live = True
    SPECIAL = "special:parked"

    def _j(self, *a):
        r = _run(["hyprctl", "-j", *a])
        try:
            return json.loads(r.stdout) if r is not None and r.returncode == 0 else None
        except Exception:
            return None

    def snapshot(self):
        clients = self._j("clients") or []
        active = (self._j("activeworkspace") or {}).get("id")
        wss = [{"id": w.get("id"), "idx": w.get("id"), "name": None, "output": w.get("monitor"),
                "focused": w.get("id") == active} for w in (self._j("workspaces") or []) if w.get("id", 0) > 0]
        if active is not None and not any(w["id"] == active for w in wss):
            wss.append({"id": active, "idx": active, "name": None, "output": None, "focused": True})
        focus = (self._j("activewindow") or {}).get("address")
        wins = []
        for c in clients:
            wsn = (c.get("workspace") or {}).get("name", "")
            wins.append({"id": c.get("address"), "title": c.get("title", ""), "cls": c.get("class", ""),
                         "ws": (c.get("workspace") or {}).get("id"), "focused": c.get("address") == focus,
                         "floating": bool(c.get("floating")), "col": None, "parked": wsn == self.SPECIAL})
        return wins, wss

    def park(self, win, wss):
        r = _run(["hyprctl", "dispatch", "movetoworkspacesilent", f"{self.SPECIAL},address:{win['id']}"])
        return r is not None and r.returncode == 0

    def restore(self, entry, wss):
        focused = next((w for w in wss if w["focused"]), None)
        ids = {w["id"] for w in wss}
        ws = entry.get("ws_id") if entry.get("ws_id") in ids else (focused or {}).get("id")
        if ws is None:
            return False
        _run(["hyprctl", "dispatch", "movetoworkspacesilent", f"{ws},address:{entry['id']}"])
        _run(["hyprctl", "dispatch", "workspace", str(ws)])
        _run(["hyprctl", "dispatch", "focuswindow", f"address:{entry['id']}"])
        return True

    def focus(self, wid):
        _run(["hyprctl", "dispatch", "focuswindow", f"address:{wid}"])

    def focus_dir(self, d):
        _run(["hyprctl", "dispatch", "movefocus", "r" if d > 0 else "l"])

    def events(self):
        return iter(())


class Sway:
    name = "sway"
    live = True

    def _j(self, *a):
        r = _run(["swaymsg", "-t", *a])
        try:
            return json.loads(r.stdout) if r is not None and r.returncode == 0 else None
        except Exception:
            return None

    def snapshot(self):
        wss = [{"id": w.get("num"), "idx": w.get("num"), "name": None, "output": w.get("output"),
                "focused": bool(w.get("focused"))} for w in (self._j("get_workspaces") or []) if w.get("num", -1) >= 0]
        wins = []

        def walk(node, ws=None):
            if node.get("type") == "workspace":
                ws = node
            if node.get("pid") and node.get("type") in ("con", "floating_con"):
                wsn = (ws or {}).get("name", "")
                wins.append({"id": str(node["id"]), "title": node.get("name") or "",
                             "cls": node.get("app_id") or (node.get("window_properties") or {}).get("class", ""),
                             "ws": (ws or {}).get("num"), "focused": bool(node.get("focused")),
                             "floating": node.get("type") == "floating_con", "col": None,
                             "parked": wsn == "__i3_scratch"})
            for c in node.get("nodes", []) + node.get("floating_nodes", []):
                walk(c, ws)

        walk(self._j("get_tree") or {})
        return wins, wss

    def park(self, win, wss):
        r = _run(["swaymsg", f"[con_id={win['id']}]", "move", "scratchpad"])
        return r is not None and r.returncode == 0

    def restore(self, entry, wss):
        focused = next((w for w in wss if w["focused"]), None)
        ids = {w["id"] for w in wss}
        ws = entry.get("ws_id") if entry.get("ws_id") in ids else (focused or {}).get("id")
        if ws is None:
            return False
        sel = f"[con_id={entry['id']}]"
        _run(["swaymsg", f"{sel} move workspace number {ws}, floating {'enable' if entry.get('floating') else 'disable'}"])
        _run(["swaymsg", f"workspace number {ws}"])
        _run(["swaymsg", f"{sel} focus"])
        return True

    def focus(self, wid):
        _run(["swaymsg", f"[con_id={wid}]", "focus"])

    def focus_dir(self, d):
        _run(["swaymsg", "focus", "right" if d > 0 else "left"])

    def events(self):
        return iter(())


class Offline:
    name = "none"
    live = False

    def snapshot(self):
        return [], []

    def park(self, win, wss):
        return False

    def restore(self, entry, wss):
        return False

    def focus(self, wid):
        pass

    def focus_dir(self, d):
        pass

    def events(self):
        return iter(())


def get_backend():
    return {"niri": Niri, "hyprland": Hyprland, "sway": Sway}.get(detect_compositor(), Offline)()


class Parking:
    def __init__(self, backend):
        self.be = backend
        self.state = read_state()
        self.wins, self.wss = backend.snapshot()
        self._prune()

    def _prune(self):
        if not self.be.live or (not self.wins and not self.wss):
            return
        alive = {w["id"]: w for w in self.wins}
        keep = []
        for p in self.state["parked"]:
            w = alive.get(p["id"])
            if w is None or not w["parked"]:
                continue
            p["title"], p["cls"] = w["title"], w["cls"]
            keep.append(p)
        if len(keep) != len(self.state["parked"]):
            self.state["parked"] = keep
            self.save()

    def save(self):
        write_state(self.state)

    @property
    def current(self):
        return next((w for w in self.wss if w["focused"]), None)

    def home(self, p):
        ids = {w["id"] for w in self.wss}
        if p.get("ws_id") in ids:
            return p["ws_id"]
        cur = self.current
        if cur is not None:
            for w in self.wss:
                if w["output"] == cur["output"] and w["idx"] == p.get("ws_idx") and w["name"] != park_name():
                    return w["id"]
            return cur["id"]
        return p.get("ws_id")

    def here(self):
        cur = self.current
        if cur is None:
            return list(self.state["parked"]) if not self.be.live else []
        return [p for p in self.state["parked"] if self.home(p) == cur["id"]]

    def total(self):
        return 2 * zones_down()

    def focused_here(self):
        cur = self.current
        for w in self.wins:
            if w["focused"] and not w["parked"] and cur and w["ws"] == cur["id"]:
                return w
        return None

    def showing(self):
        cur = self.current
        return [w for w in self.wins if cur and w["ws"] == cur["id"] and not w["parked"]]

    def _park_window(self, win, cell):
        cur = self.current or {}
        if not self.be.park(win, self.wss):
            return False
        self.state["seq"] += 1
        self.state["parked"] = [p for p in self.state["parked"] if p["id"] != win["id"]]
        self.state["parked"].append({
            "id": win["id"], "cell": cell, "seq": self.state["seq"],
            "title": win["title"], "cls": win["cls"],
            "ws_id": cur.get("id"), "ws_idx": cur.get("idx"),
            "floating": win["floating"], "col": win["col"],
        })
        self.save()
        return True

    def _unpark_entry(self, p):
        ok = self.be.restore(p, self.wss)
        if ok:
            self.state["parked"] = [q for q in self.state["parked"] if q["id"] != p["id"]]
            self.save()
        return ok

    def toggle(self):
        win = self.focused_here()
        if win is not None:
            cell = free([p["cell"] for p in self.here()], self.total(), -1, 1)
            return self._park_window(win, cell)
        if not self.showing():
            return self.all_back()
        return False

    def all_back(self):
        mine = self.here()
        tiled = sorted((p for p in mine if not p.get("floating")), key=lambda p: p.get("col") or 0)
        floating = sorted((p for p in mine if p.get("floating")), key=lambda p: -p["seq"])
        back = tiled + floating
        for p in back:
            self._unpark_entry(p)
        if back:
            last = max(back, key=lambda p: p["seq"])
            self.be.focus(last["id"])
        return bool(back)

    def park_at(self, cell):
        if cell < 0 or cell >= self.total() or cell in {p["cell"] for p in self.here()}:
            return False
        win = self.focused_here()
        return win is not None and self._park_window(win, cell)

    def unpark(self, key):
        key = str(key)
        p = next((q for q in self.state["parked"] if q["id"] == key), None)
        if p is None and key.isdigit():
            p = next((q for q in self.here() if q["cell"] == int(key)), None)
        return p is not None and self._unpark_entry(p)

    def cycle(self, d):
        rows = sorted(self.here(), key=lambda p: p["cell"])
        if not rows:
            self.be.focus_dir(d)
            return True
        first, last = rows[0], rows[-1]
        back = first if d > 0 else last
        win = self.focused_here()
        if win is not None:
            others = [p["cell"] for p in rows if p["id"] != back["id"]]
            cell = free(others, self.total(), last["cell"], 1) if d > 0 else free(others, self.total(), first["cell"], -1)
            self._park_window(win, cell)
        return self._unpark_entry(back) and (self.be.focus(back["id"]) or True)

    def slots(self):
        by_cell = {p["cell"]: p for p in self.here()}
        z = zones_down()

        def slot(cell, side):
            p = by_cell.get(cell)
            return {
                "cell": cell,
                "letter": DRAFTING_LETTERS[(cell % z) % len(DRAFTING_LETTERS)],
                "occupied": p is not None,
                "title": p["title"] if p else "",
                "cls": p["cls"] if p else "",
                "window_id": p["id"] if p else "",
                "side": side,
            }

        return {"left": [slot(c, "left") for c in range(z)], "right": [slot(z + c, "right") for c in range(z)]}


def build_slots_payload(backend=None):
    return Parking(backend or get_backend()).slots()


def print_payload():
    print(json.dumps(build_slots_payload()), flush=True)


def update_eww():
    eww_bin = shutil.which("eww")
    if eww_bin:
        cfg = os.environ.get("EWW_CONFIG_DIR", str(Path(__file__).resolve().parent.parent))
        _run([eww_bin, "-c", cfg, "update", f"parked_slots={json.dumps(build_slots_payload())}"])


def stream_events():
    backend = get_backend()
    wake = threading.Event()

    def watch():
        for _ in backend.events():
            wake.set()

    threading.Thread(target=watch, daemon=True).start()
    last, mtime = None, None
    sf = get_state_file()
    while True:
        try:
            m = sf.stat().st_mtime if sf.exists() else None
            if last is None or wake.is_set() or m != mtime:
                wake.clear()
                mtime = m
                text = json.dumps(Parking(backend).slots())
                if text != last:
                    last = text
                    print(text, flush=True)
            wake.wait(0.5)
        except Exception:
            time.sleep(1)


def run_command(cmd, arg=None, backend=None):
    with locked():
        p = Parking(backend or get_backend())
        if cmd == "toggle":
            return p.toggle()
        if cmd == "park":
            if arg in (None, ""):
                win = p.focused_here()
                return win is not None and p._park_window(win, free([q["cell"] for q in p.here()], p.total(), -1, 1))
            return p.park_at(int(arg))
        if cmd == "unpark" and arg is not None:
            return p.unpark(arg)
        if cmd == "all":
            return p.all_back()
        if cmd == "next":
            return p.cycle(1)
        if cmd == "prev":
            return p.cycle(-1)
    return False


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--oneshot":
        print_payload()
        return
    if argv and argv[0] in ("toggle", "park", "unpark", "all", "next", "prev"):
        try:
            run_command(argv[0], argv[1] if len(argv) > 1 else None)
        except Exception as e:
            print(f"parked: {e}", file=sys.stderr)
        update_eww()
        return
    stream_events()


if __name__ == "__main__":
    main()
