import json
import os
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent


class Test05NotificationsOsd(unittest.TestCase):
    def setUp(self):
        self.counter_file = Path("/tmp/.draftpaper-osd-counter-test")
        self.state_file = Path("/tmp/.draftpaper-notifications-test.json")
        if self.counter_file.exists():
            self.counter_file.unlink()
        if self.state_file.exists():
            self.state_file.unlink()

    def tearDown(self):
        if self.counter_file.exists():
            self.counter_file.unlink()
        if self.state_file.exists():
            self.state_file.unlink()

    def test_osd_script_exists_and_debounces(self):
        script_path = WORKTREE_DIR / "scripts" / "osd.sh"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")
        self.assertTrue(os.access(script_path, os.X_OK), "osd.sh must be executable")

        env = dict(
            os.environ,
            DRAFTPAPER_OSD_COUNTER=str(self.counter_file),
            DRAFTPAPER_OSD_TIMEOUT="1",
            DRAFTPAPER_MOCK="1",
        )

        proc1 = subprocess.run(
            [str(script_path), "volume", "up", "5"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(proc1.returncode, 0, f"osd.sh failed: {proc1.stderr}")
        self.assertTrue(self.counter_file.exists())
        c1 = int(self.counter_file.read_text().strip())
        self.assertGreaterEqual(c1, 1)

        proc2 = subprocess.run(
            [str(script_path), "volume", "up", "5"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(proc2.returncode, 0)
        c2 = int(self.counter_file.read_text().strip())
        self.assertGreater(c2, c1)

        proc3 = subprocess.run(
            [str(script_path), "brightness", "up", "10"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(proc3.returncode, 0)
        c3 = int(self.counter_file.read_text().strip())
        self.assertGreater(c3, c2)

    def test_osd_script_status_json(self):
        script_path = WORKTREE_DIR / "scripts" / "osd.sh"
        env = dict(
            os.environ,
            DRAFTPAPER_OSD_COUNTER=str(self.counter_file),
            DRAFTPAPER_MOCK="1",
        )
        proc = subprocess.run(
            [str(script_path), "status"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout.strip())
        self.assertIn("type", data)
        self.assertIn("value", data)
        self.assertIn("text", data)
        self.assertIn("icon", data)

    def test_notifications_script_outputs_valid_json(self):
        script_path = WORKTREE_DIR / "scripts" / "notifications.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        env = dict(
            os.environ,
            DRAFTPAPER_NOTIFICATIONS_STATE=str(self.state_file),
        )

        proc = subprocess.run(
            ["python3", str(script_path), "--oneshot"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"notifications.py failed: {proc.stderr}")

        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)
        self.assertIn("has_notification", data)
        self.assertIn("count", data)
        self.assertIn("text", data)
        self.assertIn("urgency", data)

    def test_notifications_post_and_dismiss(self):
        script_path = WORKTREE_DIR / "scripts" / "notifications.py"
        env = dict(
            os.environ,
            DRAFTPAPER_NOTIFICATIONS_STATE=str(self.state_file),
        )

        post_proc = subprocess.run(
            ["python3", str(script_path), "post", "Test Title", "Test Body", "org.test.App", "normal"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(post_proc.returncode, 0)

        read_proc = subprocess.run(
            ["python3", str(script_path), "--oneshot"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(read_proc.returncode, 0)
        data = json.loads(read_proc.stdout.strip())
        self.assertTrue(data["has_notification"])
        self.assertEqual(data["count"], 1)
        self.assertIn("Test Title", data["text"])

        dismiss_proc = subprocess.run(
            ["python3", str(script_path), "dismiss"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(dismiss_proc.returncode, 0)

        read_proc2 = subprocess.run(
            ["python3", str(script_path), "--oneshot"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(read_proc2.returncode, 0)
        data2 = json.loads(read_proc2.stdout.strip())
        self.assertFalse(data2["has_notification"])
        self.assertEqual(data2["count"], 0)

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        yuck_file = WORKTREE_DIR / "yuck" / "notifications-osd.yuck"
        scss_file = WORKTREE_DIR / "scss" / "notifications-osd.scss"
        eww_yuck = WORKTREE_DIR / "eww.yuck"
        eww_scss = WORKTREE_DIR / "eww.scss"

        self.assertTrue(yuck_file.is_file(), f"Missing yuck file: {yuck_file}")
        self.assertTrue(scss_file.is_file(), f"Missing scss file: {scss_file}")

        sass_res = subprocess.run(
            ["npx", "sass", "--no-source-map", str(eww_scss)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
        )
        self.assertEqual(
            sass_res.returncode,
            0,
            f"SCSS compilation failed:\nstdout: {sass_res.stdout}\nstderr: {sass_res.stderr}",
        )

        proc = subprocess.Popen(
            ["eww", "-c", str(WORKTREE_DIR), "daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            ping_success = False
            for _ in range(10):
                time.sleep(0.3)
                ping = subprocess.run(
                    ["eww", "-c", str(WORKTREE_DIR), "ping"],
                    capture_output=True,
                    text=True,
                )
                if ping.returncode == 0 and "pong" in ping.stdout:
                    ping_success = True
                    break
            self.assertTrue(ping_success, "eww ping failed after starting daemon")

            open_notif = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "top-notifications"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_notif.returncode,
                0,
                f"Failed to open top-notifications: {open_notif.stderr}",
            )

            open_osd = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "top-osd"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_osd.returncode,
                0,
                f"Failed to open top-osd: {open_osd.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("top-notifications", active_res.stdout)
            self.assertIn("top-osd", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "top-notifications"],
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "top-osd"],
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "kill"],
                capture_output=True,
                text=True,
            )
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
