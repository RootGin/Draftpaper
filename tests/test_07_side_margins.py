import json
import os
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent


class Test07SideMargins(unittest.TestCase):
    def setUp(self):
        self.state_file = Path("/tmp/.draftpaper-parked.json")
        if self.state_file.exists():
            self.state_file.unlink()

    def tearDown(self):
        if self.state_file.exists():
            self.state_file.unlink()

    def test_parked_script_outputs_valid_json_array(self):
        script_path = WORKTREE_DIR / "scripts" / "parked.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        proc = subprocess.run(
            ["python3", str(script_path), "--oneshot"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed: {proc.stderr}")

        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)
        self.assertIn("left", data)
        self.assertIn("right", data)
        self.assertIsInstance(data["left"], list)
        self.assertIsInstance(data["right"], list)

        for side in ["left", "right"]:
            for slot in data[side]:
                self.assertIn("cell", slot)
                self.assertIn("letter", slot)
                self.assertIn("occupied", slot)
                self.assertIn("title", slot)
                self.assertIn("cls", slot)
                self.assertIn("window_id", slot)
                self.assertIn("side", slot)
        left_letters = [slot["letter"] for slot in data["left"]]
        right_letters = [slot["letter"] for slot in data["right"]]
        self.assertEqual(left_letters, ["A", "B", "C", "D"])
        self.assertEqual(right_letters, ["A", "B", "C", "D"])

    def test_park_and_unpark_subcommands(self):
        script_path = WORKTREE_DIR / "scripts" / "parked.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        env = dict(
            os.environ,
            DRAFTPAPER_COMPOSITOR="fallback",
            DRAFTPAPER_PARKED_STATE=str(self.state_file),
        )

        park_proc = subprocess.run(
            ["python3", str(script_path), "park", "0"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(park_proc.returncode, 0, f"Park failed: {park_proc.stderr}")

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
        cell_0 = next((s for s in data["left"] if s["cell"] == 0), None)
        self.assertIsNotNone(cell_0)
        self.assertTrue(cell_0["occupied"])
        self.assertTrue(len(cell_0["title"]) > 0)

        unpark_proc = subprocess.run(
            ["python3", str(script_path), "unpark", "0"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(unpark_proc.returncode, 0, f"Unpark failed: {unpark_proc.stderr}")

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
        cell_0_after = next((s for s in data2["left"] if s["cell"] == 0), None)
        self.assertIsNotNone(cell_0_after)
        self.assertFalse(cell_0_after["occupied"])

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        yuck_file = WORKTREE_DIR / "yuck" / "side-margins.yuck"
        scss_file = WORKTREE_DIR / "scss" / "side-margins.scss"
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

            open_left = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "side-margins-left"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_left.returncode,
                0,
                f"Failed to open side-margins-left window: {open_left.stderr}",
            )

            open_right = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "side-margins-right"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_right.returncode,
                0,
                f"Failed to open side-margins-right window: {open_right.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("side-margins-left", active_res.stdout)
            self.assertIn("side-margins-right", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "side-margins-left"],
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "side-margins-right"],
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
