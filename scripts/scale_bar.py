import glob
import json
import os
import sys


def get_display_scale():
    if os.environ.get("DRAFTPAPER_NTS") in ("1", "true", "True"):
        return False, "NTS", None

    scale_override = os.environ.get("DRAFTPAPER_SCALE")
    if scale_override:
        return True, scale_override, 6.2

    for edid_path in glob.glob("/sys/class/drm/*/edid"):
        conn_dir = os.path.dirname(edid_path)
        status_file = os.path.join(conn_dir, "status")
        if os.path.exists(status_file):
            try:
                with open(status_file, "r") as f:
                    if f.read().strip() != "connected":
                        continue
            except Exception:
                continue

        try:
            with open(edid_path, "rb") as f:
                data = f.read(128)
            if len(data) >= 128:
                w_cm = data[21]
                h_cm = data[22]
                if w_cm > 0 and h_cm > 0:
                    w_mm = w_cm * 10
                    modes_file = os.path.join(conn_dir, "modes")
                    px_w = None
                    if os.path.exists(modes_file):
                        with open(modes_file, "r") as mf:
                            first_mode = mf.readline().strip()
                            if "x" in first_mode:
                                px_w = int(first_mode.split("x")[0])
                    if px_w:
                        px_per_mm = px_w / float(w_mm)
                        return True, "100mm true scale", px_per_mm
                    return True, "100mm true scale", 6.2
        except Exception:
            continue

    return False, "NTS", None


def main():
    if "--nts" in sys.argv:
        true_scale, text, px_per_mm = False, "NTS", None
    else:
        true_scale, text, px_per_mm = get_display_scale()

    if "--json" in sys.argv:
        payload = {
            "scale": text,
            "text": text,
            "true_scale": true_scale,
            "nts": not true_scale,
            "px_per_mm": px_per_mm,
        }
        print(json.dumps(payload), flush=True)
    else:
        print(text, flush=True)


if __name__ == "__main__":
    main()
