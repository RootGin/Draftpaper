import json
import os
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent


class Test04TopMargin(unittest.TestCase):
    def setUp(self):
        self.state_file = Path("/tmp/draftpaper-workspaces.json")
        if self.state_file.exists():
            self.state_file.unlink()

    def tearDown(self):
        if self.state_file.exists():
            self.state_file.unlink()

    def test_workspaces_script_outputs_valid_json_array(self):
        script_path = WORKTREE_DIR / "scripts" / "workspaces.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        proc = subprocess.Popen(
            ["python3", str(script_path), "--oneshot"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(WORKTREE_DIR),
        )
        stdout, stderr = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0, f"Script failed: {stderr}")

        data = json.loads(stdout.strip())
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 10)

        for idx, ws in enumerate(data, start=1):
            self.assertIn("id", ws)
            self.assertIn("name", ws)
            self.assertIn("focused", ws)
            self.assertIn("active", ws)
            self.assertIn("apps", ws)

            self.assertEqual(ws["id"], idx)
            self.assertEqual(str(ws["name"]), str(idx))
            self.assertIsInstance(ws["focused"], bool)
            self.assertIsInstance(ws["active"], bool)
            self.assertIsInstance(ws["apps"], list)
            self.assertLessEqual(len(ws["apps"]), 3)

        focused_workspaces = [w for w in data if w["focused"]]
        self.assertEqual(len(focused_workspaces), 1)

    def test_glyph_fallback_when_nerd_fonts_missing(self):
        script_path = WORKTREE_DIR / "scripts" / "workspaces.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        env_no_glyphs = dict(os.environ, DRAFTPAPER_GLYPHS="0")
        proc_no_glyphs = subprocess.run(
            ["python3", str(script_path), "--oneshot"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env_no_glyphs,
            timeout=5,
        )
        self.assertEqual(proc_no_glyphs.returncode, 0)
        data_no_glyphs = json.loads(proc_no_glyphs.stdout.strip())

        for ws in data_no_glyphs:
            for app in ws["apps"]:
                self.assertTrue(
                    all(ord(c) < 128 for c in app),
                    f"Expected plain-text ASCII app badge, got non-ASCII: {app}",
                )

        test_code = (
            "import importlib.util, json;"
            "spec = importlib.util.spec_from_file_location('workspaces', '" + str(script_path) + "');"
            "mod = importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(mod);"
            "badge = mod.get_app_representation('firefox', use_glyphs=False);"
            "glyph = mod.get_app_representation('firefox', use_glyphs=True);"
            "print(json.dumps({'badge': badge, 'glyph': glyph}))"
        )
        proc_eval = subprocess.run(
            ["python3", "-c", test_code],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc_eval.returncode, 0, f"Eval failed: {proc_eval.stderr}")
        eval_data = json.loads(proc_eval.stdout.strip())
        self.assertTrue(all(ord(c) < 128 for c in eval_data["badge"]))
        self.assertTrue(any(ord(c) >= 128 for c in eval_data["glyph"]))

    def test_switch_workspace_updates_state(self):
        script_path = WORKTREE_DIR / "scripts" / "workspaces.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        env = dict(
            os.environ,
            DRAFTPAPER_COMPOSITOR="fallback",
            DRAFTPAPER_WORKSPACE_STATE=str(self.state_file),
        )

        switch_proc = subprocess.run(
            ["python3", str(script_path), "switch", "4"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(switch_proc.returncode, 0, f"Switch failed: {switch_proc.stderr}")

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
        ws4 = next(w for w in data if w["id"] == 4)
        self.assertTrue(ws4["focused"])
        self.assertTrue(ws4["active"])

        other_focused = [w for w in data if w["id"] != 4 and w["focused"]]
        self.assertEqual(len(other_focused), 0)

        switch_proc2 = subprocess.run(
            ["python3", str(script_path), "switch", "7"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env,
            timeout=5,
        )
        self.assertEqual(switch_proc2.returncode, 0)

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
        ws7 = next(w for w in data2 if w["id"] == 7)
        self.assertTrue(ws7["focused"])
        self.assertTrue(ws7["active"])
        ws4_after = next(w for w in data2 if w["id"] == 4)
        self.assertFalse(ws4_after["focused"])

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        yuck_file = WORKTREE_DIR / "yuck" / "top-margin.yuck"
        scss_file = WORKTREE_DIR / "scss" / "top-margin.scss"
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
            self.assertTrue(ping_success, f"eww ping failed after starting daemon")

            open_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "top-margin"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_res.returncode,
                0,
                f"Failed to open top-margin window: {open_res.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("top-margin", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "top-margin"],
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
