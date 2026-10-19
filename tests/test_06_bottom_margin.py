import json
import os
import re
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent


class Test06BottomMargin(unittest.TestCase):
    def setUp(self):
        self.theme_scss = WORKTREE_DIR / "theme.scss"
        self.original_theme_content = self.theme_scss.read_text(encoding="utf-8") if self.theme_scss.exists() else None
        subprocess.run(["eww", "-c", str(WORKTREE_DIR), "kill"], capture_output=True)
        time.sleep(0.3)

    def tearDown(self):
        if self.original_theme_content and self.theme_scss.exists():
            self.theme_scss.write_text(self.original_theme_content, encoding="utf-8")
        subprocess.run(["eww", "-c", str(WORKTREE_DIR), "kill"], capture_output=True)

    def test_peripherals_output_valid_json(self):
        script_path = WORKTREE_DIR / "scripts" / "peripherals.sh"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        proc = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"peripherals.sh failed: {proc.stderr}")
        data = json.loads(proc.stdout.strip())
        self.assertIn("connected", data)
        self.assertIn("icon", data)
        self.assertIn("text", data)
        self.assertIn("devices", data)
        self.assertIsInstance(data["connected"], bool)
        self.assertIsInstance(data["icon"], str)
        self.assertIsInstance(data["text"], str)
        self.assertIsInstance(data["devices"], list)

        env_mock_connected = dict(
            os.environ,
            DRAFTPAPER_BT_CONNECTED="1",
            DRAFTPAPER_BT_DEVICES="Draft Mouse, Keychron K2",
        )
        proc_mock = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env_mock_connected,
            timeout=5,
        )
        self.assertEqual(proc_mock.returncode, 0)
        mock_data = json.loads(proc_mock.stdout.strip())
        self.assertTrue(mock_data["connected"])
        self.assertIn("Draft Mouse", mock_data["text"])
        self.assertEqual(len(mock_data["devices"]), 2)

        env_mock_disconnected = dict(
            os.environ,
            DRAFTPAPER_BT_CONNECTED="0",
        )
        proc_disc = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env_mock_disconnected,
            timeout=5,
        )
        self.assertEqual(proc_disc.returncode, 0)
        disc_data = json.loads(proc_disc.stdout.strip())
        self.assertFalse(disc_data["connected"])

    def test_scale_bar_output_scale_text(self):
        script_path = WORKTREE_DIR / "scripts" / "scale_bar.py"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        proc = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0, f"scale_bar.py failed: {proc.stderr}")
        stdout = proc.stdout.strip()
        self.assertTrue(
            "100mm" in stdout or "NTS" in stdout,
            f"Expected '100mm' or 'NTS' in scale bar output, got: {stdout!r}",
        )

        env_nts = dict(os.environ, DRAFTPAPER_NTS="1")
        proc_nts = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env_nts,
            timeout=5,
        )
        self.assertEqual(proc_nts.returncode, 0)
        self.assertIn("NTS", proc_nts.stdout.strip())

        env_scale = dict(os.environ, DRAFTPAPER_SCALE="100mm true scale")
        proc_scale = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            env=env_scale,
            timeout=5,
        )
        self.assertEqual(proc_scale.returncode, 0)
        self.assertIn("100mm", proc_scale.stdout.strip())

    def test_theme_script_rotates_themes_cyclically(self):
        script_path = WORKTREE_DIR / "scripts" / "theme.sh"
        self.assertTrue(script_path.is_file(), f"Missing script: {script_path}")

        self.theme_scss.write_text('@import "./themes/nord";\n', encoding="utf-8")

        proc_curr = subprocess.run(
            ["bash", str(script_path), "current"],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_DIR),
            timeout=5,
        )
        self.assertEqual(proc_curr.returncode, 0, f"theme.sh current failed: {proc_curr.stderr}")
        self.assertEqual(proc_curr.stdout.strip(), "nord")

        cycle = ["softglow", "blueprint", "daypanel", "nightpanel", "nord"]
        for expected in cycle:
            proc_next = subprocess.run(
                ["bash", str(script_path), "next"],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                timeout=5,
            )
            self.assertEqual(proc_next.returncode, 0, f"theme.sh next failed: {proc_next.stderr}")

            proc_check = subprocess.run(
                ["bash", str(script_path), "current"],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
                timeout=5,
            )
            self.assertEqual(proc_check.stdout.strip(), expected)

            content = self.theme_scss.read_text(encoding="utf-8").strip()
            pattern = rf'@import\s+["\'](?:\./)?themes/{expected}(?:\.scss)?["\']\s*;'
            self.assertTrue(
                re.search(pattern, content),
                f"theme.scss did not update to {expected}. Content: {content!r}",
            )

    def test_yuck_and_scss_compile_cleanly_in_eww(self):
        yuck_file = WORKTREE_DIR / "yuck" / "bottom-margin.yuck"
        scss_file = WORKTREE_DIR / "scss" / "bottom-margin.scss"
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

            open_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "bottom-margin"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_res.returncode,
                0,
                f"Failed to open bottom-margin window: {open_res.stderr}",
            )

            active_res = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("bottom-margin", active_res.stdout)
        finally:
            subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "close", "bottom-margin"],
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
