#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import time

STATE_FILE = os.environ.get(
    "DRAFTPAPER_NOTIFICATIONS_STATE", "/tmp/draftpaper-notifications.json"
)

APP_GLYPHS = {
    "firefox": "󰈹",
    "chrome": "󰊯",
    "chromium": "󰊯",
    "brave": "󰊯",
    "terminal": "",
    "alacritty": "",
    "foot": "",
    "kitty": "",
    "wezterm": "",
    "code": "󰨞",
    "vscode": "󰨞",
    "vlc": "󰕼",
    "spotify": "󰓇",
    "discord": "󰙯",
    "slack": "󰒱",
    "signal": "󰭹",
    "telegram": "",
}


def load_notifications():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            return []
    return []


def save_notifications(notifs):
    with open(STATE_FILE, "w") as f:
        json.dump(notifs, f)


def get_glyph(app_name):
    if os.environ.get("DRAFTPAPER_GLYPHS", "1") == "0":
        return f"{app_name}: " if app_name else ""
    key = (app_name or "").lower()
    for k, v in APP_GLYPHS.items():
        if k in key:
            return f"{v} "
    return "󰂚 " if app_name else ""


def build_payload():
    notifs = load_notifications()
    if not notifs:
        return {
            "id": 0,
            "app_name": "",
            "summary": "",
            "body": "",
            "urgency": "normal",
            "count": 0,
            "waiting_count": 0,
            "text": "",
            "has_notification": False,
            "actions": [],
        }

    current = notifs[-1]
    count = len(notifs)
    app = current.get("app_name", "")
    summary = current.get("summary", "")
    body = current.get("body", "")
    urgency = current.get("urgency", "normal")
    notif_id = current.get("id", 1)
    actions = current.get("actions", [])

    clean_summary = re.sub(r"<[^>]*>", "", summary).replace("\n", " ").strip()
    clean_body = re.sub(r"<[^>]*>", "", body).replace("\n", " ").strip()
    glyph = get_glyph(app)

    if clean_body:
        text = f"{glyph}{clean_summary} — {clean_body}"
    else:
        text = f"{glyph}{clean_summary}"

    return {
        "id": notif_id,
        "app_name": app,
        "summary": clean_summary,
        "body": clean_body,
        "urgency": urgency,
        "count": count,
        "waiting_count": count - 1 if count > 1 else 0,
        "text": text,
        "has_notification": True,
        "actions": actions,
    }


def post_notification(summary, body="", app_name="", urgency="normal", actions=None):
    notifs = load_notifications()
    new_id = (max([n.get("id", 0) for n in notifs]) + 1) if notifs else 1
    notifs.append(
        {
            "id": new_id,
            "app_name": app_name,
            "summary": summary,
            "body": body,
            "urgency": urgency,
            "actions": actions or [],
            "timestamp": time.time(),
        }
    )
    save_notifications(notifs)
    return new_id


def dismiss_notification(notif_id=None):
    notifs = load_notifications()
    if notifs:
        if notif_id is not None:
            notifs = [n for n in notifs if n.get("id") != notif_id]
        else:
            notifs.pop()
        save_notifications(notifs)
    if notif_id is not None:
        try:
            subprocess.run(["end-rs", "close", str(notif_id)], capture_output=True)
        except Exception:
            pass


def action_notification(notif_id, action_name="default"):
    dismiss_notification(notif_id)
    try:
        subprocess.run(
            ["end-rs", "action", str(notif_id), action_name], capture_output=True
        )
    except Exception:
        pass


def main():
    args = sys.argv[1:]
    if "--oneshot" in args:
        print(json.dumps(build_payload()))
        return

    if len(args) > 0:
        cmd = args[0]
        if cmd == "post":
            summary = args[1] if len(args) > 1 else "Notification"
            body = args[2] if len(args) > 2 else ""
            app = args[3] if len(args) > 3 else ""
            urgency = args[4] if len(args) > 4 else "normal"
            post_notification(summary, body, app, urgency)
            return
        elif cmd == "dismiss":
            notif_id = int(args[1]) if len(args) > 1 else None
            dismiss_notification(notif_id)
            return
        elif cmd == "action":
            notif_id = int(args[1]) if len(args) > 1 else 1
            action_name = args[2] if len(args) > 2 else "default"
            action_notification(notif_id, action_name)
            return

    last_payload = ""
    while True:
        payload = json.dumps(build_payload())
        if payload != last_payload:
            print(payload)
            sys.stdout.flush()
            last_payload = payload
        time.sleep(0.5)


if __name__ == "__main__":
    main()
