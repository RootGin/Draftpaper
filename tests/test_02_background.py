import re
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent

THEME_NAMES = [
    "nord",
    "softglow",
    "blueprint",
    "daypanel",
    "nightpanel",
]

REQUIRED_THEME_VARS = [
    "$paper",
    "$paper_light",
    "$paper_shade",
    "$glow",
    "$ink",
]


class Test02Background(unittest.TestCase):
    def test_files_exist(self):
        yuck_file = WORKTREE_DIR / "yuck" / "background.yuck"
        scss_file = WORKTREE_DIR / "scss" / "background.scss"
        self.assertTrue(
            yuck_file.is_file(),
            f"Expected {yuck_file} to exist",
        )
        self.assertTrue(
            scss_file.is_file(),
            f"Expected {scss_file} to exist",
        )

    def test_window_definition_properties(self):
        yuck_file = WORKTREE_DIR / "yuck" / "background.yuck"
        self.assertTrue(yuck_file.is_file(), "background.yuck does not exist")
        content = yuck_file.read_text(encoding="utf-8")

        self.assertRegex(
            content,
            r"\(defwindow\s+background\b",
            "background.yuck missing (defwindow background ...)",
        )
        self.assertRegex(
            content,
            r':width\s+"100%"',
            "background window geometry missing :width \"100%\"",
        )
        self.assertRegex(
            content,
            r':height\s+"100%"',
            "background window geometry missing :height \"100%\"",
        )
        self.assertRegex(
            content,
            r':stacking\s+"(?:bottom|bg)"',
            "background window missing :stacking \"bottom\" or \"bg\"",
        )
        self.assertRegex(
            content,
            r':windowtype\s+"desktop"',
            "background window missing :windowtype \"desktop\"",
        )
        self.assertRegex(
            content,
            r":wm-ignore\s+true",
            "background window missing :wm-ignore true",
        )

    def test_eww_includes(self):
        eww_yuck = WORKTREE_DIR / "eww.yuck"
        eww_scss = WORKTREE_DIR / "eww.scss"

        self.assertTrue(eww_yuck.is_file(), "eww.yuck does not exist")
        self.assertTrue(eww_scss.is_file(), "eww.scss does not exist")

        yuck_content = eww_yuck.read_text(encoding="utf-8")
        scss_content = eww_scss.read_text(encoding="utf-8")

        self.assertRegex(
            yuck_content,
            r'\(include\s+"(?:\./)?yuck/background\.yuck"\)',
            "eww.yuck missing (include \"./yuck/background.yuck\")",
        )
        self.assertRegex(
            scss_content,
            r'@import\s+["\'](?:\./)?scss/background(?:\.scss)?["\']\s*;',
            "eww.scss missing @import \"./scss/background\";",
        )

    def test_wallpaper_support(self):
        eww_yuck = WORKTREE_DIR / "eww.yuck"
        bg_yuck = WORKTREE_DIR / "yuck" / "background.yuck"
        self.assertIn("wallpaper_path", eww_yuck.read_text(encoding="utf-8"))
        bg_content = bg_yuck.read_text(encoding="utf-8")
        self.assertIn("wallpaper-layer", bg_content)
        self.assertIn("wallpaper_path", bg_content)
        self.assertRegex(bg_content, r"\(image\s+:path\s+wallpaper_path")

    def test_scss_tokens_and_compilation(self):
        scss_file = WORKTREE_DIR / "scss" / "background.scss"
        self.assertTrue(scss_file.is_file(), "background.scss does not exist")
        content = scss_file.read_text(encoding="utf-8")

        for var in REQUIRED_THEME_VARS:
            self.assertIn(
                var,
                content,
                f"background.scss does not reference theme variable {var}",
            )

        eww_scss = WORKTREE_DIR / "eww.scss"
        theme_scss = WORKTREE_DIR / "theme.scss"
        original_theme = theme_scss.read_text(encoding="utf-8")
        try:
            for theme in THEME_NAMES:
                theme_scss.write_text(f'@import "./themes/{theme}";\n', encoding="utf-8")
                result = subprocess.run(
                    ["npx", "sass", "--no-source-map", str(eww_scss)],
                    capture_output=True,
                    text=True,
                    cwd=str(WORKTREE_DIR),
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"npx sass failed with theme '{theme}': {result.stderr}",
                )
        finally:
            theme_scss.write_text(original_theme, encoding="utf-8")

    def test_eww_daemon_and_window_open(self):
        eww_yuck = WORKTREE_DIR / "eww.yuck"
        eww_scss = WORKTREE_DIR / "eww.scss"
        self.assertTrue(eww_yuck.is_file(), "eww.yuck does not exist")
        self.assertTrue(eww_scss.is_file(), "eww.scss does not exist")

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
            self.assertTrue(ping_success, "eww ping failed")

            open_result = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "open", "background"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                open_result.returncode,
                0,
                f"eww open background failed: {open_result.stderr}",
            )

            active = subprocess.run(
                ["eww", "-c", str(WORKTREE_DIR), "active-windows"],
                capture_output=True,
                text=True,
            )
            self.assertIn("background", active.stdout)
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
