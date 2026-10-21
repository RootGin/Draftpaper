#!/usr/bin/env python3
"""Draftpaper lockscreen controller (eww 0.6+, niri).

Opens the fullscreen `lockscreen` eww window, which holds exclusive keyboard
focus, and reads the typed passphrase straight from the keyboard event devices.

Why evdev instead of an eww `input` widget: eww pastes the widget text into
`sh -c "<onchange command>"` unescaped, so anyone at the lock box could type
`'; some-command; '` and run it as you. Here the typed text never goes near a
shell: it lives in this process, and eww only ever receives the mask and a
state word, passed as plain argv.

The devices are only read, never grabbed, and need membership of the `input`
group (the same requirement as any evdev reader). Keys are matched by physical
position on a US layout, which also sidesteps IMEs such as fcitx or ibus.

This is a privacy screen, not a security boundary. The password is a constant
below (or $DRAFTPAPER_LOCK_PASSWORD), and the compositor still handles its own
key bindings while the window is up.

Emergency unlock from another TTY:
    pkill -TERM -f scripts/lock.py; eww -c <config dir> close lockscreen
"""
import fcntl
import glob
import hmac
import os
import select
import signal
import struct
import subprocess
import sys
import time

DIR = os.environ.get("DRAFTPAPER_CONFIG_DIR") or os.path.dirname(
    os.path.dirname(os.path.realpath(__file__))
)
PASSWORD = os.environ.get("DRAFTPAPER_LOCK_PASSWORD", "shine")

LOCKFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "draftpaper-lock.lock")
MASK_CHAR = "●"
MAX_MASK = 24
MAX_ENTRY = 64
BASE_DELAY = 1.0
MAX_DELAY = 30.0
RESCAN = 2.0
OVERLAYS = ("launcher", "schedules", "load-graphs")

EVENT = struct.Struct("<qqHHi")
EV_KEY = 0x01
PRESS, REPEAT = 1, 2

KEY_ESC, KEY_BACKSPACE, KEY_ENTER, KEY_KPENTER = 1, 14, 28, 96
KEY_LEFTCTRL, KEY_RIGHTCTRL, KEY_LEFTSHIFT, KEY_RIGHTSHIFT = 29, 97, 42, 54
KEY_U = 22

PLAIN, SHIFTED = {}, {}


def _add(code, plain, shifted):
    PLAIN[code], SHIFTED[code] = plain, shifted


for _code, _ch in zip(
    (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44),
    "abcdefghijklmnopqrstuvwxyz",
):
    _add(_code, _ch, _ch.upper())
for _code, _p, _s in zip(range(2, 12), "1234567890", "!@#$%^&*()"):
    _add(_code, _p, _s)
for _code, _p, _s in (
    (12, "-", "_"), (13, "=", "+"), (26, "[", "{"), (27, "]", "}"), (39, ";", ":"),
    (40, "'", '"'), (41, "`", "~"), (43, "\\", "|"), (51, ",", "<"), (52, ".", ">"),
    (53, "/", "?"), (57, " ", " "),
):
    _add(_code, _p, _s)
for _code, _d in zip((82, 79, 80, 81, 75, 76, 77, 71, 72, 73), "0123456789"):
    _add(_code, _d, _d)

CHANGED, SUBMIT = "changed", "submit"


class Entry:
    """Turns key events into an entry buffer. Pure logic, no I/O."""

    def __init__(self, password):
        self.password = password
        self.buf = []
        self.shift = False
        self.ctrl = False

    def feed(self, code, value):
        """value: 0 release, 1 press, 2 repeat. Returns None, CHANGED or SUBMIT."""
        if code in (KEY_LEFTSHIFT, KEY_RIGHTSHIFT):
            self.shift = value != 0
            return None
        if code in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
            self.ctrl = value != 0
            return None
        if value == 0:
            return None
        if code == KEY_BACKSPACE:
            if not self.buf:
                return None
            self.buf.pop()
            return CHANGED
        if code in (KEY_ENTER, KEY_KPENTER):
            return SUBMIT if value == PRESS and self.buf else None
        if code == KEY_ESC or (self.ctrl and code == KEY_U):
            had = bool(self.buf)
            self.buf.clear()
            return CHANGED if had else None
        if self.ctrl:
            return None
        ch = (SHIFTED if self.shift else PLAIN).get(code)
        if ch is None or len(self.buf) >= MAX_ENTRY:
            return None
        self.buf.append(ch)
        return CHANGED

    def take(self):
        text = "".join(self.buf)
        self.buf.clear()
        return text

    def matches(self, text):
        return hmac.compare_digest(text.encode(), self.password.encode())

    @property
    def mask(self):
        return MASK_CHAR * min(len(self.buf), MAX_MASK)


class Dedupe:
    """Drop a key event repeated by a second device within a few ms (keyd, kmonad
    and similar expose a virtual keyboard next to the physical one)."""

    def __init__(self, window=0.004):
        self.window = window
        self.last = None

    def seen(self, fd, code, value, now):
        last, self.last = self.last, (fd, code, value, now)
        return bool(last) and last[0] != fd and last[1:3] == (code, value) and now - last[3] < self.window


class Devices:
    def __init__(self, pattern="/dev/input/event*"):
        self.pattern = pattern
        self.fds = {}  # path -> fd

    def refresh(self):
        for path in sorted(glob.glob(self.pattern)):
            if path in self.fds:
                continue
            try:
                self.fds[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                pass
        return bool(self.fds)

    def _drop(self, fd):
        for path, known in list(self.fds.items()):
            if known == fd:
                del self.fds[path]
        try:
            os.close(fd)
        except OSError:
            pass

    def read(self, timeout):
        """Wait up to `timeout`; return a list of (fd, code, value) key events."""
        if not self.fds:
            time.sleep(min(timeout or RESCAN, RESCAN))
            return []
        try:
            ready, _, _ = select.select(list(self.fds.values()), [], [], timeout)
        except (OSError, ValueError):
            return []
        events = []
        for fd in ready:
            try:
                data = os.read(fd, EVENT.size * 64)
            except BlockingIOError:
                continue
            except OSError:
                self._drop(fd)  # unplugged
                continue
            if not data:
                self._drop(fd)
                continue
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, off)
                if etype == EV_KEY:
                    events.append((fd, code, value))
        return events


def eww(*args):
    """Run eww with a plain argv (never a shell). Returns the exit status."""
    try:
        return subprocess.run(
            ["eww", "-c", DIR, *args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def run_lock(devices, entry):
    """Block until the right passphrase is entered. Returns 0 on unlock."""
    dedupe = Dedupe()
    fails = 0
    denied_until = None
    next_scan = 0.0
    while True:
        now = time.monotonic()
        if now >= next_scan:
            devices.refresh()
            next_scan = now + RESCAN
        timeout = RESCAN
        if denied_until is not None:
            if now >= denied_until:
                denied_until = None
                eww("update", "lock_state=idle")
            else:
                timeout = min(timeout, denied_until - now)
        for fd, code, value in devices.read(timeout):
            if dedupe.seen(fd, code, value, time.monotonic()):
                continue
            result = entry.feed(code, value)
            if denied_until is not None:
                entry.buf.clear()  # locked out: modifiers still tracked, text dropped
                continue
            if result == CHANGED:
                eww("update", f"lock_mask={entry.mask}")
            elif result == SUBMIT:
                text = entry.take()
                if entry.matches(text):
                    return 0
                fails += 1
                denied_until = time.monotonic() + min(BASE_DELAY * 2 ** (fails - 1), MAX_DELAY)
                eww("update", "lock_mask=", "lock_state=denied")


def main(argv):
    if "--selftest" in argv:
        return selftest()

    lock_fd = os.open(LOCKFILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("draftpaper-lock: already locked", file=sys.stderr)
        return 0
    
    devices = Devices()
    if not devices.refresh():
        print("draftpaper-lock: cannot read /dev/input/event* (add yourself to the `input` group); not locking",
              file=sys.stderr)
        return 1
    if eww("ping") != 0:
        print("draftpaper-lock: eww daemon is not running (start scripts/autostart.sh); not locking", file=sys.stderr)
        return 1

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))

    for name in OVERLAYS:
        eww("close", name)
    eww("close", "lockscreen")
    eww("update", "lock_mask=", "lock_state=idle")
    try:
        if eww("open", "lockscreen") != 0:
            print("draftpaper-lock: could not open the lockscreen window", file=sys.stderr)
            return 1
        return run_lock(devices, Entry(PASSWORD))
    finally:
        eww("close", "lockscreen")
        eww("update", "lock_mask=", "lock_state=idle")


def selftest():
    import tempfile
    import threading

    global eww, BASE_DELAY
    assert EVENT.size == 24, EVENT.size
    keys = {ch: code for code, ch in PLAIN.items()}

    def type_text(entry, text):
        for ch in text:
            if ch.isupper():
                entry.feed(KEY_LEFTSHIFT, 1)
                entry.feed(keys[ch.lower()], 1)
                entry.feed(KEY_LEFTSHIFT, 0)
            else:
                entry.feed(keys[ch], 1)

    e = Entry("Draft-1")
    type_text(e, "Draft-1")
    assert e.mask == MASK_CHAR * 7
    assert e.feed(KEY_ENTER, PRESS) == SUBMIT and e.matches(e.take())
    type_text(e, "abc")
    assert e.feed(KEY_BACKSPACE, PRESS) == CHANGED and e.mask == MASK_CHAR * 2
    e.feed(KEY_LEFTCTRL, 1)
    assert e.feed(KEY_U, PRESS) == CHANGED and e.mask == ""
    e.feed(KEY_LEFTCTRL, 0)
    assert e.feed(KEY_ENTER, PRESS) is None
    type_text(e, "x")
    assert e.feed(KEY_ENTER, REPEAT) is None
    assert e.feed(KEY_ESC, PRESS) == CHANGED and e.buf == []
    e.feed(keys["a"], 0)
    assert e.buf == []
    assert not e.matches("nope")

    d = Dedupe()
    assert not d.seen(1, 30, 1, 0.000) and d.seen(2, 30, 1, 0.001)
    assert not d.seen(1, 30, 1, 0.010) and not d.seen(1, 30, 1, 0.011)

    calls = []
    real_eww, real_delay = eww, BASE_DELAY
    eww = lambda *a: calls.append(a) or 0
    BASE_DELAY = 0.05
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fifo = os.path.join(tmp, "event0")
            os.mkfifo(fifo)
            dev = Devices(os.path.join(tmp, "event*"))
            assert dev.refresh()
            w = os.open(fifo, os.O_WRONLY)

            def send(text):
                buf = b""
                for ch in text:
                    buf += EVENT.pack(0, 0, EV_KEY, keys[ch], PRESS) + EVENT.pack(0, 0, EV_KEY, keys[ch], 0)
                os.write(w, buf + EVENT.pack(0, 0, EV_KEY, KEY_ENTER, PRESS))

            send("wrong")  # denied, then locked out for BASE_DELAY
            threading.Timer(0.4, lambda: send("right")).start()
            assert run_lock(dev, Entry("right")) == 0
            assert ("update", "lock_mask=", "lock_state=denied") in calls, calls
            assert ("update", "lock_state=idle") in calls, calls
            os.close(w)
    finally:
        eww, BASE_DELAY = real_eww, real_delay
    print("lock selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
