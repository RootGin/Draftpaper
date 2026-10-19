import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent
READINGS_SCRIPT = WORKTREE_DIR / "scripts" / "readings.py"
TITLE_BLOCK_YUCK = WORKTREE_DIR / "yuck" / "title-block.yuck"
TITLE_BLOCK_SCSS = WORKTREE_DIR / "scss" / "title-block.scss"
EWW_YUCK = WORKTREE_DIR / "eww.yuck"
EWW_SCSS = WORKTREE_DIR / "eww.scss"

REQUIRED_KEYS = [
    "time",
    "date",
    "sheet",
    "project",
    "power",
    "battery",
    "profile",
    "cpu",
    "memory",
    "network",
    "temps",
    "fan",
    "processes",
    "drawn",
]


class Test03TitleBlock(unittest.TestCase):
    def test_readings_output_keys(self):
        self.assertTrue(READINGS_SCRIPT.is_file(), f"{READINGS_SCRIPT} does not exist")
        res = subprocess.run(
            [sys.executable, str(READINGS_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
        )
        self.assertEqual(res.returncode, 0, f"readings.py failed: {res.stderr}")
        line = res.stdout.strip().splitlines()[-1]
        data = json.loads(line)
        for key in REQUIRED_KEYS:
            self.assertIn(key, data, f"Missing required key '{key}' in readings.py output: {data}")

    def test_alert_states(self):
        self.assertTrue(READINGS_SCRIPT.is_file(), f"{READINGS_SCRIPT} does not exist")
        with tempfile.TemporaryDirectory() as tmpdir:
            sysfs = Path(tmpdir) / "sys"
            bat_dir = sysfs / "class" / "power_supply" / "BAT0"
            bat_dir.mkdir(parents=True)
            (bat_dir / "capacity").write_text("10\n", encoding="utf-8")
            (bat_dir / "status").write_text("Discharging\n", encoding="utf-8")

            hwmon_dir = sysfs / "class" / "hwmon" / "hwmon0"
            hwmon_dir.mkdir(parents=True)
            (hwmon_dir / "name").write_text("coretemp\n", encoding="utf-8")
            (hwmon_dir / "temp1_label").write_text("Package id 0\n", encoding="utf-8")
            (hwmon_dir / "temp1_input").write_text("90000\n", encoding="utf-8")

            env = dict(os.environ, SYSFS_ROOT=str(sysfs))
            res = subprocess.run(
                [sys.executable, str(READINGS_SCRIPT)],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                env=env,
            )
            self.assertEqual(res.returncode, 0, f"readings.py failed with mock sysfs: {res.stderr}")
            data = json.loads(res.stdout.strip().splitlines()[-1])
            is_battery_alert = (
                data.get("battery_alert") is True
                or "alert" in str(data.get("battery_class", ""))
                or data.get("alerts", {}).get("battery") is True
            )
            self.assertTrue(is_battery_alert, f"Battery alert flag not set when battery is 10%: {data}")

            is_temp_alert = (
                data.get("temp_alert") is True
                or data.get("hot") is True
                or "alert" in str(data.get("temp_class", ""))
                or data.get("alerts", {}).get("temp") is True
            )
            self.assertTrue(is_temp_alert, f"Temperature alert flag not set when CPU is 90C: {data}")

        with tempfile.TemporaryDirectory() as tmpdir:
            sysfs = Path(tmpdir) / "sys"
            bat_dir = sysfs / "class" / "power_supply" / "BAT0"
            bat_dir.mkdir(parents=True)
            (bat_dir / "capacity").write_text("80\n", encoding="utf-8")
            (bat_dir / "status").write_text("Discharging\n", encoding="utf-8")

            hwmon_dir = sysfs / "class" / "hwmon" / "hwmon0"
            hwmon_dir.mkdir(parents=True)
            (hwmon_dir / "name").write_text("coretemp\n", encoding="utf-8")
            (hwmon_dir / "temp1_label").write_text("Package id 0\n", encoding="utf-8")
            (hwmon_dir / "temp1_input").write_text("45000\n", encoding="utf-8")

            env = dict(os.environ, SYSFS_ROOT=str(sysfs))
            res = subprocess.run(
                [sys.executable, str(READINGS_SCRIPT)],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                env=env,
            )
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout.strip().splitlines()[-1])
            self.assertFalse(data.get("battery_alert", False))
            self.assertFalse(data.get("temp_alert", False))
            self.assertFalse(data.get("hot", False))

    def test_power_profile_cycling(self):
        self.assertTrue(READINGS_SCRIPT.is_file(), f"{READINGS_SCRIPT} does not exist")
        res = subprocess.run(
            [sys.executable, str(READINGS_SCRIPT), "--cycle-profile"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
        )
        self.assertEqual(res.returncode, 0, f"--cycle-profile failed: {res.stderr}")

    def test_files_exist_and_included(self):
        self.assertTrue(TITLE_BLOCK_YUCK.is_file(), "yuck/title-block.yuck does not exist")
        self.assertTrue(TITLE_BLOCK_SCSS.is_file(), "scss/title-block.scss does not exist")

        yuck_content = EWW_YUCK.read_text(encoding="utf-8")
        self.assertIn("title-block.yuck", yuck_content, "eww.yuck does not include yuck/title-block.yuck")

        scss_content = EWW_SCSS.read_text(encoding="utf-8")
        self.assertTrue(
            re.search(r'@import\s+["\'](?:\./)?scss/title-block(?:\.scss)?["\']\s*;', scss_content),
            f"eww.scss does not import scss/title-block: {scss_content}",
        )

    def test_scss_compiles(self):
        res = subprocess.run(
            ["npx", "sass", "--no-source-map", str(EWW_SCSS)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
        )
        self.assertEqual(res.returncode, 0, f"SCSS compilation failed:\nstdout: {res.stdout}\nstderr: {res.stderr}")

    def test_eww_daemon_loads_title_block(self):
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
            self.assertTrue(ping_success, "eww daemon failed to start and respond to ping")

            yuck_text = TITLE_BLOCK_YUCK.read_text(encoding="utf-8")
            self.assertIn("defwindow title-block", yuck_text)
        finally:
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
