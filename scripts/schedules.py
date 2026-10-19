import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from compositor import detect_compositor, get_active_window, get_process_cwd
except ImportError:
    from scripts.compositor import detect_compositor, get_active_window, get_process_cwd

SYSFS_BASE = Path(os.environ.get("SYSFS_ROOT", "/sys"))
PROC_BASE = Path(os.environ.get("PROC_ROOT", "/proc"))


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def format_uptime(seconds):
    s = int(seconds)
    d = s // 86400
    h = (s % 86400) // 3600
    m = (s % 3600) // 60
    if d > 0:
        return f"up {d} d {h} h"
    elif h > 0:
        return f"up {h} h {m} min"
    else:
        return f"up {m} min"


def format_memory(bytes_val):
    b = float(bytes_val)
    if b >= 1e9:
        return f"{b / 1e9:.1f} GB"
    else:
        return f"{b / 1e6:.0f} MB"


def format_time(seconds):
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    else:
        return f"{m}:{sec:02d}"


def get_vendor(s):
    s = s.strip()
    if any(c.islower() for c in s) or len(s) <= 3:
        return s
    return s.capitalize()


def get_machine_info():
    v = read_text(SYSFS_BASE / "class" / "dmi" / "id" / "sys_vendor")
    version = read_text(SYSFS_BASE / "class" / "dmi" / "id" / "product_version")
    name = read_text(SYSFS_BASE / "class" / "dmi" / "id" / "product_name")

    bad = {"", "none", "default string", "to be filled by o.e.m.", "system product name"}
    model = version if version.lower() not in bad and any(c.isalpha() for c in version) and " " in version else name
    if model.lower() in bad:
        model = socket.gethostname()

    v = get_vendor(v)
    if v.lower() in bad or model.lower().startswith(v.lower()):
        return model
    return f"{v} {model}"


def get_cpu_info():
    cpuinfo = read_text(PROC_BASE / "cpuinfo")
    model = ""
    threads = 0
    cores = set()
    pkg = ""
    core = None

    for line in cpuinfo.splitlines():
        if line.startswith("model name"):
            parts = line.split(":", 1)
            if len(parts) == 2 and not model:
                model = parts[1].strip()
        elif line.startswith("processor"):
            threads += 1
        elif line.startswith("physical id"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                pkg = parts[1].strip()
        elif line.startswith("core id"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                core = parts[1].strip()
        elif not line.strip():
            if core is not None:
                cores.add((pkg, core))
                core = None

    if core is not None:
        cores.add((pkg, core))

    model = model.replace("(R)", "").replace("(TM)", "").replace("(tm)", "")
    model = model.split(" @ ")[0].replace(" CPU", "")
    model = " ".join(model.split())

    core_count = len(cores) if cores else (threads if threads else 1)
    return model or "Processor", core_count, threads or core_count


def get_gpus():
    gpus = []
    try:
        res = subprocess.run(["lspci"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if any(k in line for k in ["VGA compatible controller", "3D controller", "Display controller"]):
                    parts = line.split(": ", 1)
                    if len(parts) == 2:
                        name = parts[1].split(" (rev")[0].strip()
                        name = name.replace("Advanced Micro Devices, Inc. [AMD/ATI]", "AMD")
                        name = name.replace("NVIDIA Corporation", "NVIDIA")
                        name = name.replace("Intel Corporation", "Intel")
                        gpus.append(name)
    except Exception:
        pass

    if not gpus:
        drm_path = SYSFS_BASE / "class" / "drm"
        if drm_path.is_dir():
            for card in drm_path.glob("card*"):
                uevent = read_text(card / "device" / "uevent")
                for uline in uevent.splitlines():
                    if uline.startswith("DRIVER="):
                        drv = uline.split("=", 1)[1]
                        if drv not in gpus:
                            gpus.append(f"{drv.upper()} Graphics")
    return gpus or ["Integrated Graphics"]


def get_memory_info():
    meminfo = read_text(PROC_BASE / "meminfo")
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    kb = float(parts[1])
                    gib = round(kb / 1024.0 / 1024.0)
                    return f"{gib} GiB"
                except ValueError:
                    pass
    return "Unknown"


def get_storage_info():
    try:
        res = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    dev = parts[0]
                    size = parts[1]
                    used = parts[2]
                    pct = parts[4]
                    return dev, f"{used} of {size} used ({pct})"
    except Exception:
        pass
    try:
        st = os.statvfs("/")
        total_gb = round((st.f_blocks * st.f_frsize) / 1e9)
        used_gb = round(((st.f_blocks - st.f_bfree) * st.f_frsize) / 1e9)
        return "root", f"{used_gb} of {total_gb} GB used"
    except Exception:
        pass
    return "root", "Unknown"


def get_system_info():
    os_name = ""
    os_release = read_text(Path("/etc/os-release"))
    for line in os_release.splitlines():
        if line.startswith("PRETTY_NAME="):
            os_name = line.split("=", 1)[1].strip('"')
            break
    if not os_name:
        os_name = "Linux"

    kernel_raw = read_text(PROC_BASE / "sys" / "kernel" / "osrelease")
    k_parts = re.split(r"[.\-+]", kernel_raw) if kernel_raw else []
    if len(k_parts) >= 2:
        kernel = f"Linux {k_parts[0]}.{k_parts[1]}"
    else:
        kernel = f"Linux {kernel_raw}" if kernel_raw else "Linux"

    uptime_raw = read_text(PROC_BASE / "uptime")
    uptime_s = 0
    if uptime_raw:
        try:
            uptime_s = float(uptime_raw.split()[0])
        except (ValueError, IndexError):
            pass

    return os_name, kernel, format_uptime(uptime_s)


def build_equipment():
    machine = get_machine_info()
    cpu_model, cores, threads = get_cpu_info()
    gpus = get_gpus()
    mem = get_memory_info()
    disk_dev, disk_usage = get_storage_info()
    sys_name, kernel, uptime = get_system_info()

    rows = []
    rows.append({
        "ref": "M1",
        "item": "MACHINE",
        "desc": machine,
        "note": "",
        "cells": ["M1", "MACHINE", machine],
    })
    rows.append({
        "ref": "M2",
        "item": "PROCESSOR",
        "desc": cpu_model,
        "note": f"{cores} cores, {threads} threads",
        "cells": ["M2", "PROCESSOR", cpu_model],
    })

    n = 3
    for i, g in enumerate(gpus):
        ref_id = f"M{n + i}"
        rows.append({
            "ref": ref_id,
            "item": "GRAPHICS",
            "desc": g,
            "note": "",
            "cells": [ref_id, "GRAPHICS", g],
        })
    n += max(1, len(gpus))

    rows.append({
        "ref": f"M{n}",
        "item": "MEMORY",
        "desc": mem,
        "note": "",
        "cells": [f"M{n}", "MEMORY", mem],
    })
    rows.append({
        "ref": f"M{n + 1}",
        "item": "STORAGE",
        "desc": disk_dev,
        "note": disk_usage,
        "cells": [f"M{n + 1}", "STORAGE", disk_dev],
    })
    rows.append({
        "ref": "S1",
        "item": "SYSTEM",
        "desc": f"{sys_name} · {kernel}",
        "note": uptime,
        "cells": ["S1", "SYSTEM", f"{sys_name} · {kernel}"],
    })
    rows.append({
        "ref": "S2",
        "item": "DESKTOP",
        "desc": "Draftpaper Eww · Wayland",
        "note": "12-cell engineering layout",
        "cells": ["S2", "DESKTOP", "Draftpaper Eww · Wayland"],
    })

    hostname = socket.gethostname()
    return {
        "title": "SCHEDULE OF EQUIPMENT",
        "meta": f"{hostname.upper()} · SHEET 1",
        "columns": [
            {"name": "REF", "width": 45},
            {"name": "ITEM", "width": 140},
            {"name": "DESCRIPTION", "width": 0},
        ],
        "rows": rows,
    }


def build_processes():
    rows = []
    load_str = ""
    total_procs = 0

    try:
        lavg = os.getloadavg()
        load_str = f"{lavg[0]:.2f}, {lavg[1]:.2f}, {lavg[2]:.2f}"
    except Exception:
        load_str = "0.00, 0.00, 0.00"

    try:
        res = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,time,comm", "--sort=-pcpu"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                total_procs = len(lines) - 1
                for idx, line in enumerate(lines[1:13]):
                    parts = line.split(None, 4)
                    if len(parts) >= 5:
                        pid = parts[0]
                        try:
                            cpu_pct = float(parts[1])
                        except ValueError:
                            cpu_pct = 0.0
                        mem_val = f"{parts[2]}%"
                        time_str = parts[3]
                        comm = parts[4].split("/")[-1].replace("-wrapped", "").strip()

                        share = min(1.0, max(0.0, cpu_pct / 100.0))
                        alert = cpu_pct >= 80.0
                        row_no = f"{idx + 1:02d}"

                        rows.append({
                            "no": row_no,
                            "process": comm,
                            "pid": pid,
                            "cpu": f"{cpu_pct:.1f}%",
                            "memory": mem_val,
                            "time": time_str,
                            "share": share,
                            "alert": alert,
                            "cells": [row_no, comm, pid, f"{cpu_pct:.1f}%", mem_val, time_str],
                        })
    except Exception:
        pass

    return {
        "title": "PROCESS SCHEDULE",
        "meta": f"BY CPU · LOAD {load_str} · {total_procs} PROCESSES",
        "columns": [
            {"name": "NO.", "width": 35},
            {"name": "PROCESS", "width": 0},
            {"name": "PID", "width": 60},
            {"name": "CPU %", "width": 80},
            {"name": "MEMORY", "width": 70},
            {"name": "TIME", "width": 70},
        ],
        "rows": rows,
    }


def build_revisions():
    rows = []
    repo_name = ""

    repo_dir = None
    try:
        active_win = get_active_window()
        if active_win and active_win.get("pid"):
            proc_cwd = get_process_cwd(active_win["pid"])
            if proc_cwd:
                cmd_check = ["git", "-C", proc_cwd, "rev-parse", "--show-toplevel"]
                r_check = subprocess.run(cmd_check, capture_output=True, text=True, timeout=1)
                if r_check.returncode == 0 and r_check.stdout.strip():
                    repo_dir = r_check.stdout.strip()
    except Exception:
        pass

    if not repo_dir:
        repo_dir = os.environ.get("DRAFTPAPER_REPO_DIR")
    if not repo_dir:
        repo_dir = str(Path(__file__).resolve().parent.parent)

    try:
        cmd_top = ["git", "-C", repo_dir, "rev-parse", "--show-toplevel"]
        res_top = subprocess.run(cmd_top, capture_output=True, text=True, timeout=2)
        if res_top.returncode == 0 and res_top.stdout.strip():
            top_path = res_top.stdout.strip()
            repo_name = Path(top_path).name

            cmd_log = [
                "git",
                "-C",
                repo_dir,
                "--no-pager",
                "--no-optional-locks",
                "-c",
                "log.showSignature=false",
                "log",
                "-n",
                "12",
                "--format=%h%x1f%s%x1f%as%x1f%an",
            ]
            res_log = subprocess.run(cmd_log, capture_output=True, text=True, timeout=2)
            if res_log.returncode == 0:
                for line in res_log.stdout.strip().splitlines():
                    parts = line.split("\x1f")
                    if len(parts) == 4:
                        rev, desc, dt, by = parts[0], parts[1], parts[2], parts[3]
                        rows.append({
                            "rev": rev,
                            "description": desc,
                            "date": dt,
                            "by": by,
                            "cells": [rev, desc, dt, by],
                        })
    except Exception:
        pass

    title = f"REVISIONS · {repo_name.upper()}" if repo_name else "REVISIONS"
    return {
        "title": title,
        "meta": "SHEET 1",
        "columns": [
            {"name": "REV", "width": 70},
            {"name": "DESCRIPTION", "width": 0},
            {"name": "DATE", "width": 90},
            {"name": "BY", "width": 90},
        ],
        "rows": rows,
    }


def get_all_data():
    return {
        "equipment": build_equipment(),
        "processes": build_processes(),
        "revisions": build_revisions(),
    }


def next_mode(current):
    modes = ["none", "equipment", "processes", "revisions"]
    current = current.lower().strip()
    if current not in modes:
        return "none"
    idx = modes.index(current)
    return modes[(idx + 1) % len(modes)]


def toggle(target_mode=None):
    eww_dir = Path(__file__).resolve().parent.parent

    if target_mode and target_mode != "next":
        target = target_mode
    else:
        current = "none"
        try:
            res = subprocess.run(
                ["eww", "-c", str(eww_dir), "get", "schedule_mode"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0:
                current = res.stdout.strip().strip('"')
        except Exception:
            pass
        target = next_mode(current)

    try:
        subprocess.run(
            ["eww", "-c", str(eww_dir), "update", f"schedule_mode={target}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        pass
    print(target)


def main():
    parser = argparse.ArgumentParser(description="Draftpaper Eww Schedule Telemetry")
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="data",
        choices=["data", "equipment", "processes", "revisions", "toggle", "next-mode"],
    )
    parser.add_argument("argument", nargs="?", default=None)

    args = parser.parse_args()

    if args.subcommand == "data":
        print(json.dumps(get_all_data()))
    elif args.subcommand == "equipment":
        print(json.dumps(build_equipment()))
    elif args.subcommand == "processes":
        print(json.dumps(build_processes()))
    elif args.subcommand == "revisions":
        print(json.dumps(build_revisions()))
    elif args.subcommand == "next-mode":
        current = args.argument or "none"
        print(next_mode(current))
    elif args.subcommand == "toggle":
        toggle(args.argument)


if __name__ == "__main__":
    main()
