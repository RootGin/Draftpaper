#!/usr/bin/env python3
import datetime
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

SYSFS_BASE = Path(os.environ.get("SYSFS_ROOT", "/sys"))
HWMON_DIR = SYSFS_BASE / "class" / "hwmon"
POWER_DIR = SYSFS_BASE / "class" / "power_supply"
NET_DIR = SYSFS_BASE / "class" / "net"

ORDERED_PROFILES = ["power-saver", "balanced", "performance"]
PROFILE_GLYPHS = {"power-saver": "󰌪", "balanced": "󰾅", "performance": "󰓅"}
PROFILE_SHORTS = {"power-saver": "saver", "balanced": "balanced", "performance": "perf"}
BATTERY_RAMPS = ["󰁺", "󰁻", "󰁼", "󰁽", "󰁾", "󰁿", "󰂀", "󰂁", "󰂂", "󰁹"]


def read_file(path):
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def read_int(path):
    val = read_file(path)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            return None
    return None


def get_active_profile():
    try:
        res = subprocess.run(
            ["busctl", "get-property", "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles", "ActiveProfile"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if res.returncode == 0:
            match = re.search(r'"([^"]+)"', res.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass
    try:
        res = subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    fallback_file = Path("/tmp/draftpaper-power-profile")
    if fallback_file.is_file():
        saved = read_file(fallback_file)
        if saved in ORDERED_PROFILES:
            return saved
    return "--"


def set_active_profile(profile):
    success = False
    try:
        res = subprocess.run(
            ["busctl", "set-property", "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles", "ActiveProfile", "s", profile],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if res.returncode == 0:
            success = True
    except Exception:
        pass
    if not success:
        try:
            res = subprocess.run(["powerprofilesctl", "set", profile], capture_output=True, text=True, timeout=1)
            if res.returncode == 0:
                success = True
        except Exception:
            pass
    try:
        Path("/tmp/draftpaper-power-profile").write_text(profile, encoding="utf-8")
    except Exception:
        pass
    return success


def cycle_profile():
    current = get_active_profile()
    try:
        idx = ORDERED_PROFILES.index(current)
    except ValueError:
        idx = 1
    next_profile = ORDERED_PROFILES[(idx + 1) % len(ORDERED_PROFILES)]
    set_active_profile(next_profile)
    return next_profile


def get_sheet():
    try:
        res = subprocess.run(["hyprctl", "activeworkspace", "-j"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            return str(data.get("name") or data.get("id") or "1")
    except Exception:
        pass
    try:
        res = subprocess.run(["niri", "msg", "-j", "workspaces"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            workspaces = json.loads(res.stdout)
            for ws in workspaces:
                if ws.get("is_focused"):
                    return str(ws.get("idx") or ws.get("name") or "1")
    except Exception:
        pass
    try:
        res = subprocess.run(["swaymsg", "-t", "get_workspaces"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            workspaces = json.loads(res.stdout)
            for ws in workspaces:
                if ws.get("focused"):
                    return str(ws.get("name") or "1")
    except Exception:
        pass
    fallback = Path("/tmp/draftpaper-workspace")
    if fallback.is_file():
        val = read_file(fallback)
        if val:
            return val
    return "1"


def get_power_and_battery():
    power_supply_dir = POWER_DIR
    if not power_supply_dir.is_dir():
        return "mains", 0, "--", False, ""
    bats = sorted([d for d in power_supply_dir.iterdir() if d.name.startswith("BAT")])
    if not bats:
        return "mains", 0, "--", False, ""
    power_str = "mains"
    bat_pct = 100
    bat_alert = False
    bat_class = ""
    for b in bats:
        cap = read_int(b / "capacity")
        if cap is not None:
            bat_pct = cap
        status = read_file(b / "status") or ""
        if status == "Discharging":
            u_w = read_int(b / "power_now")
            if u_w is not None and u_w > 0:
                power_str = f"󱐋 {u_w / 1e6:.1f} W"
            else:
                curr = read_int(b / "current_now")
                volt = read_int(b / "voltage_now")
                if curr and volt:
                    power_str = f"󱐋 {(curr * volt) / 1e12:.1f} W"
            if bat_pct < 15:
                bat_alert = True
                bat_class = "alert"
        elif bat_pct < 15 and status != "Charging":
            bat_alert = True
            bat_class = "alert"
        ramp_idx = min(9, max(0, bat_pct // 10))
        glyph = "󰂄" if status == "Charging" else BATTERY_RAMPS[ramp_idx]
        bat_text = f"{glyph} {bat_pct}%"
        return power_str, bat_pct, bat_text, bat_alert, bat_class
    return "mains", 100, "100%", False, ""


def get_cpu_and_mem():
    cpu_pct = 0
    try:
        prev_file = Path("/tmp/draftpaper-cpu-stat")
        stat_line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
        parts = [int(p) for p in stat_line.split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts)
        if prev_file.is_file():
            prev_parts = [int(p) for p in prev_file.read_text(encoding="utf-8").split()]
            prev_idle = prev_parts[0]
            prev_total = prev_parts[1]
            diff_idle = idle - prev_idle
            diff_total = total - prev_total
            if diff_total > 0:
                cpu_pct = max(0, min(100, int(round((1.0 - diff_idle / diff_total) * 100))))
        prev_file.write_text(f"{idle} {total}", encoding="utf-8")
    except Exception:
        pass
    mem_pct = 0
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        total_m = re.search(r"MemTotal:\s+(\d+)", meminfo)
        avail_m = re.search(r"MemAvailable:\s+(\d+)", meminfo)
        if total_m and avail_m:
            tot = int(total_m.group(1))
            avail = int(avail_m.group(1))
            if tot > 0:
                mem_pct = max(0, min(100, int(round((1.0 - avail / tot) * 100))))
    except Exception:
        pass
    return cpu_pct, mem_pct


def get_network():
    try:
        res = subprocess.run(
            ["nmcli", "-t", "-f", "IN-USE,SIGNAL,SSID", "dev", "wifi", "list", "--rescan", "no"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.startswith("*"):
                    parts = line.split(":")
                    if len(parts) >= 3:
                        ssid = ":".join(parts[2:])
                        if ssid:
                            return ssid
    except Exception:
        pass
    try:
        res = subprocess.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "dev"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                parts = line.split(":")
                if len(parts) >= 3 and parts[1] == "ethernet" and parts[2] == "connected":
                    return "wired"
    except Exception:
        pass
    if NET_DIR.is_dir():
        for iface in NET_DIR.iterdir():
            if iface.name != "lo":
                state = read_file(iface / "operstate")
                if state == "up":
                    return "wired"
    return "--"


def get_temps_and_fan():
    cpu_deg = None
    nvme_deg = None
    ram_deg = None
    fan_rpm = 0
    hot = False
    if HWMON_DIR.is_dir():
        for d in sorted(HWMON_DIR.iterdir()):
            name = read_file(d / "name") or ""
            if name in ["coretemp", "k10temp", "zenpower"] and cpu_deg is None:
                for lbl_file in sorted(d.glob("temp*_label")):
                    lbl = read_file(lbl_file)
                    if lbl in ["Package id 0", "Tctl", "Tdie"]:
                        inp_file = Path(str(lbl_file).replace("_label", "_input"))
                        val = read_int(inp_file)
                        if val is not None:
                            cpu_deg = int(round(val / 1000.0))
                            break
                if cpu_deg is None:
                    val = read_int(d / "temp1_input")
                    if val is not None:
                        cpu_deg = int(round(val / 1000.0))
            elif name == "nvme" and nvme_deg is None:
                val = read_int(d / "temp1_input")
                if val is not None:
                    nvme_deg = int(round(val / 1000.0))
            elif (name in ["jc42", "spd5118", "dram", "dimm"] or "ram" in name.lower() or "dimm" in name.lower()) and ram_deg is None:
                val = read_int(d / "temp1_input")
                if val is not None:
                    ram_deg = int(round(val / 1000.0))
            if ram_deg is None:
                for lbl_file in sorted(d.glob("temp*_label")):
                    lbl = (read_file(lbl_file) or "").lower()
                    if any(k in lbl for k in ["dimm", "ram", "dram", "memory"]):
                        inp_file = Path(str(lbl_file).replace("_label", "_input"))
                        val = read_int(inp_file)
                        if val is not None:
                            ram_deg = int(round(val / 1000.0))
                            break
            if fan_rpm == 0:
                fan_val = read_int(d / "fan1_input")
                if fan_val is not None and fan_val > 0:
                    fan_rpm = fan_val
    if cpu_deg is None:
        cpu_deg = 45
    if nvme_deg is None:
        nvme_deg = 40
    if ram_deg is None:
        mock_ram = os.environ.get("DRAFTPAPER_RAM_TEMP")
        ram_deg = int(mock_ram) if mock_ram and mock_ram.isdigit() else 35

    temps_dict = {
        "cpu": cpu_deg,
        "nvme": nvme_deg,
        "ram": ram_deg,
    }
    temps_list = [
        {"label": "CPU", "value": f"{cpu_deg}°"},
        {"label": "NVME", "value": f"{nvme_deg}°"},
        {"label": "RAM", "value": f"{ram_deg}°"},
    ]
    if cpu_deg >= 85 or nvme_deg >= 60 or ram_deg >= 70 or fan_rpm >= 5000:
        hot = True
    temp_class = "alert" if hot else ""
    return temps_dict, temps_list, cpu_deg, nvme_deg, ram_deg, fan_rpm, hot, temp_class


def get_processes():
    try:
        count = 0
        for entry in os.scandir("/proc"):
            if entry.is_dir() and entry.name.isdigit():
                count += 1
        return count
    except Exception:
        return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--cycle-profile":
        cycle_profile()
        sys.exit(0)
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%a %d %b %Y")
    sheet_str = get_sheet()
    project_str = socket.gethostname() or "draftpaper"
    power_str, bat_pct, bat_text, bat_alert, bat_class = get_power_and_battery()
    profile = get_active_profile()
    if not profile or profile == "--":
        profile_text = "--"
    else:
        profile_glyph = PROFILE_GLYPHS.get(profile, "󰾅")
        profile_short = PROFILE_SHORTS.get(profile, profile)
        profile_text = f"{profile_glyph} {profile_short}"
    cpu_pct, mem_pct = get_cpu_and_mem()
    cpu_text = f"{cpu_pct}%"
    mem_text = f"{mem_pct}%"
    cpumem_text = f"󰻠 {cpu_text}  󰍛 {mem_text}"
    net_val = get_network()
    temps_dict, temps_list, cpu_deg, nvme_deg, ram_deg, fan_rpm, hot, temp_class = get_temps_and_fan()
    temp_text = f"󰘚 {cpu_deg}°  󰋊 {nvme_deg}°"
    fan_text = f"󰈐 {fan_rpm} RPM"
    tempfan_text = f"{temp_text}  {fan_text}"
    procs = get_processes()
    procs_val = procs if procs > 0 else "--"
    drawn_str = os.environ.get("DRAFTPAPER_DRAWN", "RootGin")

    output = {
        "time": time_str,
        "date": date_str,
        "sheet": sheet_str,
        "project": project_str,
        "power": power_str,
        "battery": bat_pct,
        "battery_text": bat_text,
        "battery_alert": bat_alert,
        "battery_class": bat_class,
        "profile": profile,
        "profile_text": profile_text,
        "cpu": cpu_pct,
        "cpu_text": cpu_text,
        "memory": mem_pct,
        "memory_text": mem_text,
        "cpumem_text": cpumem_text,
        "network": net_val,
        "temps": temps_dict,
        "temps_list": temps_list,
        "temp_text": temp_text,
        "temp_alert": hot,
        "temp_class": temp_class,
        "hot": hot,
        "fan": fan_rpm,
        "fan_text": fan_text,
        "tempfan_text": tempfan_text,
        "processes": procs_val,
        "drawn": drawn_str,
        "alerts": {
            "battery": bat_alert,
            "temp": hot,
        },
    }
    for k, v in output.items():
        if k not in ["battery_class", "temp_class"] and (v is None or (isinstance(v, str) and not v.strip())):
            output[k] = "--"
    print(json.dumps(output))


if __name__ == "__main__":
    main()
