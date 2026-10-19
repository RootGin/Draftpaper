import json
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent
SCHEDULES_SCRIPT = WORKTREE_DIR / "scripts" / "schedules.py"
SCHEDULES_YUCK = WORKTREE_DIR / "yuck" / "schedules.yuck"
SCHEDULES_SCSS = WORKTREE_DIR / "scss" / "schedules.scss"
EWW_YUCK = WORKTREE_DIR / "eww.yuck"
EWW_SCSS = WORKTREE_DIR / "eww.scss"


class Test08Schedules(unittest.TestCase):
    def test_schedules_script_outputs_equipment_json(self):
        self.assertTrue(SCHEDULES_SCRIPT.is_file(), f"Missing script: {SCHEDULES_SCRIPT}")
        proc = subprocess.run(
            ["python3", str(SCHEDULES_SCRIPT), "equipment"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)
        self.assertIn("title", data)
        self.assertIn("meta", data)
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        self.assertIsInstance(data["rows"], list)
        self.assertTrue(len(data["rows"]) > 0)
        first_row = data["rows"][0]
        self.assertIn("cells", first_row)
        self.assertIsInstance(first_row["cells"], list)
        self.assertGreaterEqual(len(first_row["cells"]), 3)

    def test_schedules_script_outputs_processes_json(self):
        self.assertTrue(SCHEDULES_SCRIPT.is_file(), f"Missing script: {SCHEDULES_SCRIPT}")
        proc = subprocess.run(
            ["python3", str(SCHEDULES_SCRIPT), "processes"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)
        self.assertIn("title", data)
        self.assertIn("meta", data)
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        self.assertIsInstance(data["rows"], list)
        if len(data["rows"]) > 0:
            first_row = data["rows"][0]
            self.assertIn("cells", first_row)
            self.assertIn("share", first_row)
            self.assertIsInstance(first_row["share"], (int, float))

    def test_schedules_script_outputs_revisions_json(self):
        self.assertTrue(SCHEDULES_SCRIPT.is_file(), f"Missing script: {SCHEDULES_SCRIPT}")
        proc = subprocess.run(
            ["python3", str(SCHEDULES_SCRIPT), "revisions"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)
        self.assertIn("title", data)
        self.assertIn("meta", data)
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        self.assertIsInstance(data["rows"], list)

    def test_schedules_script_outputs_combined_data_json(self):
        self.assertTrue(SCHEDULES_SCRIPT.is_file(), f"Missing script: {SCHEDULES_SCRIPT}")
        proc = subprocess.run(
            ["python3", str(SCHEDULES_SCRIPT), "data"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)
        self.assertIn("equipment", data)
        self.assertIn("processes", data)
        self.assertIn("revisions", data)

    def test_schedules_toggle_subcommand(self):
        self.assertTrue(SCHEDULES_SCRIPT.is_file(), f"Missing script: {SCHEDULES_SCRIPT}")

        cycle_map = {
            "none": "equipment",
            "equipment": "processes",
            "processes": "revisions",
            "revisions": "none",
        }

        for cur, nxt in cycle_map.items():
            proc = subprocess.run(
                ["python3", str(SCHEDULES_SCRIPT), "next-mode", cur],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                timeout=5,
            )
            self.assertEqual(proc.returncode, 0, f"next-mode failed: {proc.stderr}")
            self.assertEqual(proc.stdout.strip(), nxt)

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        self.assertTrue(SCHEDULES_YUCK.is_file(), f"Missing yuck file: {SCHEDULES_YUCK}")
        self.assertTrue(SCHEDULES_SCSS.is_file(), f"Missing scss file: {SCHEDULES_SCSS}")

        sass_res = subprocess.run(
            ["npx", "sass", "--no-source-map", str(EWW_SCSS)],
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

            open_win = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "schedules"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_win.returncode,
                0,
                f"Failed to open schedules window: {open_win.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("schedules", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "schedules"],
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
