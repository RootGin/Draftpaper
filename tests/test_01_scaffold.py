import os
import re
import subprocess
import time
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = [
    "yuck",
    "scss",
    "themes",
    "scripts",
    "bin",
]

REQUIRED_FILES = [
    "eww.yuck",
    "eww.scss",
    "theme.scss",
]

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
    "$ink_muted",
    "$alert",
    "$strong",
    "$accent",
    "$focused",
    "$unfocused",
]


class Test01Scaffold(unittest.TestCase):
    def test_required_directories_exist(self):
        for d in REQUIRED_DIRS:
            dir_path = WORKTREE_DIR / d
            self.assertTrue(
                dir_path.is_dir(),
                f"Required directory '{d}' does not exist at {dir_path}",
            )

    def test_required_files_exist(self):
        for f in REQUIRED_FILES:
            file_path = WORKTREE_DIR / f
            self.assertTrue(
                file_path.is_file(),
                f"Required file '{f}' does not exist at {file_path}",
            )

    def test_theme_files_and_variables(self):
        themes_dir = WORKTREE_DIR / "themes"
        self.assertTrue(themes_dir.is_dir(), "themes/ directory does not exist")

        for name in THEME_NAMES:
            theme_file = themes_dir / f"{name}.scss"
            self.assertTrue(
                theme_file.is_file(),
                f"Theme file '{name}.scss' does not exist in themes/",
            )

            content = theme_file.read_text(encoding="utf-8")
            for var in REQUIRED_THEME_VARS:
                pattern = rf"\{var}\s*:\s*[^;]+;"
                self.assertTrue(
                    re.search(pattern, content),
                    f"Theme '{name}.scss' is missing required variable '{var}'",
                )

    def test_theme_scss_points_to_nord_by_default(self):
        theme_scss = WORKTREE_DIR / "theme.scss"
        self.assertTrue(theme_scss.is_file(), "theme.scss does not exist")

        content = theme_scss.read_text(encoding="utf-8").strip()
        pattern = r'@import\s+["\'](?:\./)?themes/nord(?:\.scss)?["\']\s*;'
        self.assertTrue(
            re.search(pattern, content),
            f"theme.scss does not import themes/nord. Content: {content!r}",
        )

    def test_scss_compiles_cleanly(self):
        eww_scss = WORKTREE_DIR / "eww.scss"
        theme_scss = WORKTREE_DIR / "theme.scss"
        self.assertTrue(eww_scss.is_file(), "eww.scss does not exist")
        self.assertTrue(theme_scss.is_file(), "theme.scss does not exist")

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
                    f"npx sass failed to compile eww.scss with theme '{theme}':\nstdout: {result.stdout}\nstderr: {result.stderr}",
                )
        finally:
            theme_scss.write_text(original_theme, encoding="utf-8")

    def test_eww_daemon_and_ping(self):
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
            self.assertTrue(
                ping_success,
                f"eww ping failed after starting daemon. ping stdout: {ping.stdout}, stderr: {ping.stderr}",
            )
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
