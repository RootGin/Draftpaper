import json
import os
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent
GRAPHS_SCRIPT = WORKTREE_DIR / "scripts" / "graphs.py"
GRAPHS_YUCK = WORKTREE_DIR / "yuck" / "load-graphs.yuck"
GRAPHS_SCSS = WORKTREE_DIR / "scss" / "load-graphs.scss"
EWW_YUCK = WORKTREE_DIR / "eww.yuck"
EWW_SCSS = WORKTREE_DIR / "eww.scss"

REQUIRED_METRICS = ["power", "battery", "cpu", "ram", "network", "temperature"]


class Test09LoadGraphs(unittest.TestCase):
    def test_graphs_script_outputs_telemetry_history_json(self):
        self.assertTrue(GRAPHS_SCRIPT.is_file(), f"Missing script: {GRAPHS_SCRIPT}")
        proc = subprocess.run(
            ["python3", str(GRAPHS_SCRIPT), "data"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())
        self.assertIsInstance(data, dict)

        for metric in REQUIRED_METRICS:
            self.assertIn(metric, data, f"Missing metric '{metric}' in output")
            metric_data = data[metric]
            self.assertIsInstance(metric_data, dict)
            self.assertIn("values", metric_data)
            self.assertIsInstance(metric_data["values"], list)
            self.assertGreater(len(metric_data["values"]), 0)
            self.assertIn("min", metric_data)
            self.assertIsInstance(metric_data["min"], (int, float))
            self.assertIn("max", metric_data)
            self.assertIsInstance(metric_data["max"], (int, float))
            self.assertIn("points", metric_data)
            self.assertIn("current", metric_data)

    def test_graphs_toggle_subcommand(self):
        self.assertTrue(GRAPHS_SCRIPT.is_file(), f"Missing script: {GRAPHS_SCRIPT}")

        metrics_to_test = ["power", "battery", "cpu", "network", "temp"]

        env = os.environ.copy()
        test_mode_file = "/tmp/draftpaper-test-graph-mode"
        env["DRAFTPAPER_GRAPH_MODE_FILE"] = test_mode_file
        if os.path.exists(test_mode_file):
            os.remove(test_mode_file)

        proc = subprocess.run(
            ["python3", str(GRAPHS_SCRIPT), "toggle", "none"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "none")

        for metric in metrics_to_test:
            proc_on = subprocess.run(
                ["python3", str(GRAPHS_SCRIPT), "toggle", metric],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                env=env,
                timeout=5,
            )
            self.assertEqual(proc_on.returncode, 0, f"toggle {metric} on failed: {proc_on.stderr}")
            expected = "temperature" if metric == "temp" else metric
            self.assertIn(proc_on.stdout.strip(), [metric, expected])

            proc_off = subprocess.run(
                ["python3", str(GRAPHS_SCRIPT), "toggle", metric],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                env=env,
                timeout=5,
            )
            self.assertEqual(proc_off.returncode, 0, f"toggle {metric} off failed: {proc_off.stderr}")
            self.assertEqual(proc_off.stdout.strip(), "none")

        if os.path.exists(test_mode_file):
            os.remove(test_mode_file)

    def test_ring_buffer_accumulation(self):
        self.assertTrue(GRAPHS_SCRIPT.is_file(), f"Missing script: {GRAPHS_SCRIPT}")
        env = os.environ.copy()
        test_store_file = "/tmp/draftpaper-test-metrics-store.json"
        env["DRAFTPAPER_METRICS_STORE"] = test_store_file
        if os.path.exists(test_store_file):
            os.remove(test_store_file)

        try:
            for _ in range(3):
                proc = subprocess.run(
                    ["python3", str(GRAPHS_SCRIPT), "record"],
                    capture_output=True,
                    text=True,
                    cwd=str(WORKTREE_DIR),
                    env=env,
                    timeout=5,
                )
                self.assertEqual(proc.returncode, 0)

            proc = subprocess.run(
                ["python3", str(GRAPHS_SCRIPT), "data"],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                env=env,
                timeout=5,
            )
            self.assertEqual(proc.returncode, 0)
            data = json.loads(proc.stdout.strip())
            for metric in REQUIRED_METRICS:
                self.assertGreaterEqual(len(data[metric]["values"]), 3)
        finally:
            if os.path.exists(test_store_file):
                os.remove(test_store_file)

    def test_yuck_and_scss_files_exist_and_included(self):
        self.assertTrue(GRAPHS_YUCK.is_file(), f"Missing yuck file: {GRAPHS_YUCK}")
        self.assertTrue(GRAPHS_SCSS.is_file(), f"Missing scss file: {GRAPHS_SCSS}")

        yuck_content = EWW_YUCK.read_text(encoding="utf-8")
        self.assertIn("load-graphs.yuck", yuck_content)

        scss_content = EWW_SCSS.read_text(encoding="utf-8")
        self.assertIn("load-graphs", scss_content)

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        self.assertTrue(GRAPHS_YUCK.is_file(), f"Missing yuck file: {GRAPHS_YUCK}")
        self.assertTrue(GRAPHS_SCSS.is_file(), f"Missing scss file: {GRAPHS_SCSS}")

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
                ["eww", "-c", str(WORKTREE_DIR), "open", "load-graphs"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_win.returncode,
                0,
                f"Failed to open load-graphs window: {open_win.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("load-graphs", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "load-graphs"],
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
