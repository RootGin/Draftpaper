import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SYSFS_BASE = Path(os.environ.get("SYSFS_ROOT", "/sys"))
PROC_BASE = Path(os.environ.get("PROC_ROOT", "/proc"))
HWMON_DIR = SYSFS_BASE / "class" / "hwmon"
POWER_DIR = SYSFS_BASE / "class" / "power_supply"

RING_BUFFER_SIZE = 60
METRICS = ["power", "battery", "cpu", "ram", "network", "temperature"]


def get_store_path():
    custom = os.environ.get("DRAFTPAPER_METRICS_STORE")
    if custom:
        return Path(custom)
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        p = Path(xdg) / "draftpaper" / "metrics.json"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
    return Path("/tmp/draftpaper-metrics.json")


def get_mode_file():
    custom = os.environ.get("DRAFTPAPER_GRAPH_MODE_FILE")
    if custom:
        return Path(custom)
    return Path("/tmp/draftpaper-graph-mode")


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def read_int(path):
    val = read_text(path)
    if val:
        try:
            return int(val)
        except ValueError:
            return None
    return None


def sample_power_and_battery():
    power_w = 0.0
    bat_pct = 100.0
    if POWER_DIR.is_dir():
        bats = sorted([d for d in POWER_DIR.iterdir() if d.name.startswith("BAT")])
        if bats:
            b = bats[0]
            cap = read_int(b / "capacity")
            if cap is not None:
                bat_pct = float(cap)
            u_w = read_int(b / "power_now")
            if u_w is not None and u_w > 0:
                power_w = round(u_w / 1e6, 2)
            else:
                curr = read_int(b / "current_now")
                volt = read_int(b / "voltage_now")
                if curr and volt:
                    power_w = round((curr * volt) / 1e12, 2)
    return power_w, bat_pct


def sample_cpu_and_ram():
    cpu_pct = 0.0
    stat_file = PROC_BASE / "stat"
    if stat_file.is_file():
        try:
            prev_file = Path("/tmp/draftpaper-graphs-cpustat")
            stat_line = stat_file.read_text(encoding="utf-8").splitlines()[0]
            parts = [int(p) for p in stat_line.split()[1:]]
            idle = parts[3] + parts[4]
            total = sum(parts)
            if prev_file.is_file():
                prev = [int(p) for p in prev_file.read_text(encoding="utf-8").split()]
                d_idle = idle - prev[0]
                d_total = total - prev[1]
                if d_total > 0:
                    cpu_pct = round((1.0 - (d_idle / d_total)) * 100.0, 1)
            prev_file.write_text(f"{idle} {total}", encoding="utf-8")
        except Exception:
            cpu_pct = 0.0

    mem_pct = 0.0
    meminfo_file = PROC_BASE / "meminfo"
    if meminfo_file.is_file():
        try:
            total_kib = 0
            avail_kib = 0
            for line in meminfo_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    total_kib = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kib = int(line.split()[1])
            if total_kib > 0:
                mem_pct = round(((total_kib - avail_kib) / total_kib) * 100.0, 1)
        except Exception:
            mem_pct = 0.0

    return cpu_pct, mem_pct


def sample_network():
    netdev = PROC_BASE / "net" / "dev"
    if not netdev.is_file():
        return 0.0
    try:
        rx_total = 0
        tx_total = 0
        for line in netdev.read_text(encoding="utf-8").splitlines():
            if ":" in line:
                iface, data = line.split(":", 1)
                iface = iface.strip()
                if iface != "lo":
                    parts = data.split()
                    if len(parts) >= 9:
                        rx_total += int(parts[0])
                        tx_total += int(parts[8])
        now_t = time.time()
        prev_file = Path("/tmp/draftpaper-graphs-netstat")
        rate_kb = 0.0
        if prev_file.is_file():
            prev_data = prev_file.read_text(encoding="utf-8").split()
            if len(prev_data) == 3:
                p_time = float(prev_data[0])
                p_rx = int(prev_data[1])
                p_tx = int(prev_data[2])
                dt = now_t - p_time
                if dt > 0:
                    d_bytes = (rx_total - p_rx) + (tx_total - p_tx)
                    if d_bytes >= 0:
                        rate_kb = round((d_bytes / dt) / 1024.0, 1)
        prev_file.write_text(f"{now_t} {rx_total} {tx_total}", encoding="utf-8")
        return rate_kb
    except Exception:
        return 0.0


def sample_temperature():
    cpu_deg = 40.0
    if HWMON_DIR.is_dir():
        for d in sorted(HWMON_DIR.iterdir()):
            name = read_text(d / "name")
            if name in ["coretemp", "k10temp", "zenpower"]:
                for inp_file in sorted(d.glob("temp*_input")):
                    val = read_int(inp_file)
                    if val is not None and val > 0:
                        cpu_deg = float(round(val / 1000.0, 1))
                        return cpu_deg
            val = read_int(d / "temp1_input")
            if val is not None and val > 0:
                cpu_deg = float(round(val / 1000.0, 1))
                return cpu_deg
    thermal_dir = SYSFS_BASE / "class" / "thermal"
    if thermal_dir.is_dir():
        for tz in sorted(thermal_dir.glob("thermal_zone*")):
            val = read_int(tz / "temp")
            if val is not None and val > 0:
                cpu_deg = float(round(val / 1000.0, 1))
                return cpu_deg
    return cpu_deg


def sample_current_readings():
    power_w, bat_pct = sample_power_and_battery()
    cpu_pct, mem_pct = sample_cpu_and_ram()
    net_kb = sample_network()
    temp_c = sample_temperature()
    return {
        "power": power_w,
        "battery": bat_pct,
        "cpu": cpu_pct,
        "ram": mem_pct,
        "network": net_kb,
        "temperature": temp_c,
    }


def load_store():
    store_file = get_store_path()
    if store_file.is_file():
        try:
            data = json.loads(store_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {m: [] for m in METRICS}


def save_store(store):
    store_file = get_store_path()
    try:
        store_file.parent.mkdir(parents=True, exist_ok=True)
        store_file.write_text(json.dumps(store), encoding="utf-8")
    except Exception:
        pass


def record_sample():
    store = load_store()
    current = sample_current_readings()
    for m in METRICS:
        if m not in store or not isinstance(store[m], list):
            store[m] = []
        store[m].append(current[m])
        if len(store[m]) > RING_BUFFER_SIZE:
            store[m] = store[m][-RING_BUFFER_SIZE:]
    save_store(store)
    return store, current


def compute_points(values, width=240, height=60):
    if not values:
        return "0,30 240,30"
    n = len(values)
    if n == 1:
        return f"0,{height / 2:.1f} {width},{height / 2:.1f}"

    min_v = min(values)
    max_v = max(values)
    diff = max_v - min_v
    pad_y = 6.0
    drawable_h = height - 2 * pad_y

    pts = []
    for i, v in enumerate(values):
        x = round(i * width / (n - 1), 1)
        if diff == 0:
            y = round(height / 2.0, 1)
        else:
            y = round((height - pad_y) - ((v - min_v) / diff) * drawable_h, 1)
        pts.append(f"{x},{y}")
    return " ".join(pts)


def generate_sparkline_svg(metric_name, values, points_str, width=240, height=60):
    svg_dir = Path("/tmp/draftpaper-graphs")
    try:
        svg_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    svg_file = svg_dir / f"sparkline-{metric_name}.svg"

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">
  <line x1="0" y1="10" x2="{width}" y2="10" stroke="rgba(62,52,42,0.18)" stroke-dasharray="3,3" stroke-width="1"/>
  <line x1="0" y1="{height / 2}" x2="{width}" y2="{height / 2}" stroke="rgba(62,52,42,0.18)" stroke-dasharray="3,3" stroke-width="1"/>
  <line x1="0" y1="{height - 10}" x2="{width}" y2="{height - 10}" stroke="rgba(62,52,42,0.18)" stroke-width="1"/>
  <polyline fill="none" stroke="#E8B374" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="{points_str}"/>
</svg>"""
    try:
        svg_file.write_text(svg_content, encoding="utf-8")
        return str(svg_file)
    except Exception:
        return ""


def is_eww_running(eww_dir):
    try:
        res = subprocess.run(
            ["eww", "-c", str(eww_dir), "ping"],
            capture_output=True,
            text=True,
            timeout=0.15,
        )
        return res.returncode == 0 and "pong" in res.stdout
    except Exception:
        return False


def get_current_mode(eww_dir):
    mode_file = get_mode_file()
    if os.environ.get("DRAFTPAPER_GRAPH_MODE_FILE"):
        if mode_file.is_file():
            saved = read_text(mode_file)
            if saved:
                return saved
        return "none"

    if is_eww_running(eww_dir):
        try:
            res = subprocess.run(
                ["eww", "-c", str(eww_dir), "get", "graph_mode"],
                capture_output=True,
                text=True,
                timeout=0.3,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().strip('"')
        except Exception:
            pass

    if mode_file.is_file():
        saved = read_text(mode_file)
        if saved:
            return saved
    return "none"


def set_current_mode(new_mode, eww_dir):
    mode_file = get_mode_file()
    try:
        mode_file.write_text(new_mode, encoding="utf-8")
    except Exception:
        pass

    if is_eww_running(eww_dir):
        try:
            subprocess.run(
                ["eww", "-c", str(eww_dir), "update", f"graph_mode={new_mode}"],
                capture_output=True,
                text=True,
                timeout=0.3,
            )
        except Exception:
            pass

        if new_mode != "none":
            try:
                subprocess.run(
                    ["eww", "-c", str(eww_dir), "open", "load-graphs"],
                    capture_output=True,
                    text=True,
                    timeout=0.3,
                )
            except Exception:
                pass


def toggle_metric(target_metric, eww_dir):
    metric = target_metric.lower()
    if metric == "temp":
        metric = "temperature"
    elif metric == "load":
        metric = "cpu"
    elif metric == "mem":
        metric = "ram"

    current = get_current_mode(eww_dir)
    if current == "temp":
        current = "temperature"

    if metric == "none":
        new_mode = "none"
    elif current == metric:
        new_mode = "none"
    else:
        new_mode = metric

    set_current_mode(new_mode, eww_dir)
    print(new_mode)
    return new_mode


def get_all_data(eww_dir):
    store, current = record_sample()
    mode = get_current_mode(eww_dir)

    units = {
        "power": "W",
        "battery": "%",
        "cpu": "%",
        "ram": "%",
        "network": "KB/s",
        "temperature": "°C",
    }

    labels = {
        "power": "POWER DRAW",
        "battery": "BATTERY CAPACITY",
        "cpu": "CPU LOAD",
        "ram": "MEMORY LOAD",
        "network": "NETWORK THROUGHPUT",
        "temperature": "TEMPERATURE",
    }

    result = {
        "mode": mode,
        "active_metric": mode,
    }

    for m in METRICS:
        vals = store.get(m, [])
        if not vals:
            vals = [current.get(m, 0.0)]
        min_v = round(min(vals), 1)
        max_v = round(max(vals), 1)
        avg_v = round(sum(vals) / len(vals), 1)
        cur_v = vals[-1]
        pts = compute_points(vals)
        svg_p = generate_sparkline_svg(m, vals, pts)

        result[m] = {
            "name": m,
            "label": labels[m],
            "unit": units[m],
            "current": cur_v,
            "min": min_v,
            "max": max_v,
            "avg": avg_v,
            "values": vals,
            "points": pts,
            "svg_path": svg_p,
        }

    result["temp"] = result["temperature"]

    active_key = mode if mode in result and mode != "none" else "cpu"
    result["active"] = result[active_key]
    result["active_value"] = result[active_key]["current"]
    result["svg_path"] = result[active_key]["svg_path"]

    return result


def main():
    eww_dir = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description="Telemetry Load Graphs")
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="data",
        choices=["data", "record", "toggle"],
    )
    parser.add_argument("metric", nargs="?", default=None)

    args = parser.parse_args()

    if args.subcommand == "data":
        print(json.dumps(get_all_data(eww_dir)))
    elif args.subcommand == "record":
        store, current = record_sample()
        print(json.dumps({"recorded": True, "samples": len(store["cpu"])}))
    elif args.subcommand == "toggle":
        target = args.metric or "none"
        toggle_metric(target, eww_dir)


if __name__ == "__main__":
    main()
