import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent
LAUNCHER_SCRIPT = WORKTREE_DIR / "scripts" / "launcher.py"
LAUNCHER_YUCK = WORKTREE_DIR / "yuck" / "launcher.yuck"
LAUNCHER_SCSS = WORKTREE_DIR / "scss" / "launcher.scss"
EWW_YUCK = WORKTREE_DIR / "eww.yuck"
EWW_SCSS = WORKTREE_DIR / "eww.scss"


class Test10Launcher(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app_dir = Path(self.temp_dir.name) / "applications"
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = Path(self.temp_dir.name) / "history.json"
        self.env = dict(
            os.environ,
            DRAFTPAPER_APP_DIRS=str(self.app_dir),
            DRAFTPAPER_LAUNCHER_HISTORY=str(self.history_file),
            EWW_DIR=str(WORKTREE_DIR),
        )

        firefox_desktop = self.app_dir / "firefox.desktop"
        firefox_desktop.write_text(
            "[Desktop Entry]\n"
            "Name=Firefox Web Browser\n"
            "GenericName=Web Browser\n"
            "Comment=Browse the World Wide Web\n"
            "Exec=firefox %u\n"
            "Icon=firefox\n"
            "Terminal=false\n"
            "Type=Application\n"
            "Categories=Network;WebBrowser;\n"
            "Keywords=web;browser;internet;\n"
        )

        term_desktop = self.app_dir / "foot.desktop"
        term_desktop.write_text(
            "[Desktop Entry]\n"
            "Name=Foot Terminal\n"
            "GenericName=Terminal Emulator\n"
            "Comment=A fast Wayland terminal\n"
            "Exec=foot\n"
            "Icon=foot\n"
            "Terminal=false\n"
            "Type=Application\n"
            "Categories=System;TerminalEmulator;\n"
            "Keywords=shell;prompt;command;terminal;\n"
        )

        calc_desktop = self.app_dir / "calc.desktop"
        calc_desktop.write_text(
            "[Desktop Entry]\n"
            "Name=Calculator\n"
            "GenericName=Scientific Calculator\n"
            "Comment=Perform arithmetic calculations\n"
            "Exec=gnome-calculator\n"
            "Icon=calc\n"
            "Terminal=false\n"
            "Type=Application\n"
            "Categories=Utility;Calculator;\n"
            "Keywords=math;arithmetic;\n"
        )

        hidden_desktop = self.app_dir / "hidden.desktop"
        hidden_desktop.write_text(
            "[Desktop Entry]\n"
            "Name=Hidden App\n"
            "Exec=hidden\n"
            "NoDisplay=true\n"
            "Type=Application\n"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_launcher_discovers_apps_and_fuzzy_searches(self):
        self.assertTrue(LAUNCHER_SCRIPT.is_file(), f"Missing launcher script: {LAUNCHER_SCRIPT}")

        proc = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "list"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"launcher list failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())

        self.assertIn("header", data)
        self.assertIn("matches", data)
        self.assertIn("total", data)
        self.assertIn("prefix", data)
        self.assertIn("items", data)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["matches"], 3)

        app_names = [item["name"] for item in data["items"]]
        self.assertIn("Firefox Web Browser", app_names)
        self.assertIn("Foot Terminal", app_names)
        self.assertIn("Calculator", app_names)
        self.assertNotIn("Hidden App", app_names)

        first_item = data["items"][0]
        self.assertIn("num", first_item)
        self.assertIn("glyph", first_item)
        self.assertIn("name", first_item)
        self.assertIn("desc", first_item)
        self.assertIn("exec", first_item)

        proc_search = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "list", "term"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc_search.returncode, 0)
        search_data = json.loads(proc_search.stdout.strip())
        self.assertGreaterEqual(search_data["matches"], 1)
        self.assertEqual(search_data["items"][0]["name"], "Foot Terminal")

    def test_frequency_and_recency_ranking(self):
        self.assertTrue(LAUNCHER_SCRIPT.is_file())
        now = time.time()
        initial_history = {
            "calc.desktop": {"count": 25, "last_used": now - 3600},
            "firefox.desktop": {"count": 2, "last_used": now - 7200},
            "foot.desktop": {"count": 0, "last_used": 0},
        }
        self.history_file.write_text(json.dumps(initial_history))

        proc = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "list"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout.strip())
        self.assertEqual(data["items"][0]["name"], "Calculator")

    def test_launch_execution_and_history_update(self):
        self.assertTrue(LAUNCHER_SCRIPT.is_file())
        proc = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "launch", "calc.desktop", "--dry-run"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"Launch failed: {proc.stderr}")
        self.assertTrue(self.history_file.exists())
        history = json.loads(self.history_file.read_text())
        self.assertIn("calc.desktop", history)
        self.assertGreaterEqual(history["calc.desktop"]["count"], 1)

    def test_keyboard_navigation_commands(self):
        self.assertTrue(LAUNCHER_SCRIPT.is_file())

        proc_down = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "down", "0", "5"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc_down.returncode, 0)
        self.assertEqual(proc_down.stdout.strip(), "1")

        proc_up = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "up", "1", "5"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc_up.returncode, 0)
        self.assertEqual(proc_up.stdout.strip(), "0")

        proc_up_wrap = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "up", "0", "5"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc_up_wrap.returncode, 0)
        self.assertEqual(proc_up_wrap.stdout.strip(), "4")

    def test_stdin_piping_mode_menu(self):
        self.assertTrue(LAUNCHER_SCRIPT.is_file())
        input_data = "First Choice\nSecond Choice\nThird Choice\n"
        proc = subprocess.Popen(
            ["python3", str(LAUNCHER_SCRIPT), "menu", "--prompt", "CHOOSE"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
        )
        proc.stdin.write(input_data)
        proc.stdin.close()

        time.sleep(0.5)
        proc_sel = subprocess.run(
            ["python3", str(LAUNCHER_SCRIPT), "menu-select", "Second Choice"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=self.env,
            timeout=5,
        )
        self.assertEqual(proc_sel.returncode, 0)

        stdout, stderr = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0, f"menu failed: {stderr}")
        self.assertEqual(stdout.strip(), "Second Choice")

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        self.assertTrue(LAUNCHER_YUCK.is_file(), f"Missing yuck: {LAUNCHER_YUCK}")
        self.assertTrue(LAUNCHER_SCSS.is_file(), f"Missing scss: {LAUNCHER_SCSS}")

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
                ["eww", "-c", str(WORKTREE_DIR), "open", "launcher"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_win.returncode,
                0,
                f"Failed to open launcher window: {open_win.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("launcher", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "launcher"],
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
