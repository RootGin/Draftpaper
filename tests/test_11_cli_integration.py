import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

WORKTREE_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = WORKTREE_DIR / "bin" / "draftpaper-eww"

FORBIDDEN_SCSS_PATTERNS = [
    r"display\s*:\s*flex",
    r"position\s*:\s*absolute",
    r"position\s*:\s*relative",
    r"z-index\s*:",
    r"display\s*:\s*grid",
    r"grid-template",
    r"::before",
    r"::after",
    r"max-width\s*:",
    r"max-height\s*:",
]


class Test11CliIntegration(unittest.TestCase):
    def setUp(self):
        self.env = dict(
            os.environ,
            DRAFTPAPER_CONFIG_DIR=str(WORKTREE_DIR),
            EWW_DIR=str(WORKTREE_DIR),
            DRAFTPAPER_MOCK="1",
        )

    def test_cli_executable_exists(self):
        self.assertTrue(CLI_PATH.is_file(), f"{CLI_PATH} does not exist")
        self.assertTrue(os.access(CLI_PATH, os.X_OK), f"{CLI_PATH} is not executable")

    def test_cli_help_lists_all_subcommands(self):
        res = subprocess.run(
            [str(CLI_PATH), "--help"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        output = res.stdout + res.stderr
        expected_subcommands = [
            "schedule",
            "launcher",
            "theme",
            "osd",
            "readings",
            "graph",
            "park",
            "screenshot",
            "daemon",
        ]
        for cmd in expected_subcommands:
            self.assertIn(cmd, output, f"Subcommand '{cmd}' not found in help output")

    def test_cli_subcommand_schedule(self):
        res = subprocess.run(
            [str(CLI_PATH), "schedule", "data"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("equipment", data)
        self.assertIn("processes", data)
        self.assertIn("revisions", data)

    def test_cli_subcommand_launcher(self):
        res = subprocess.run(
            [str(CLI_PATH), "launcher", "list"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)

    def test_cli_subcommand_theme(self):
        res = subprocess.run(
            [str(CLI_PATH), "theme", "current"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn(res.stdout.strip(), ["nord", "softglow", "blueprint", "daypanel", "nightpanel"])

        res_list = subprocess.run(
            [str(CLI_PATH), "theme", "list"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res_list.returncode, 0)
        for t in ["nord", "softglow", "blueprint", "daypanel", "nightpanel"]:
            self.assertIn(t, res_list.stdout)

    def test_cli_subcommand_osd(self):
        res = subprocess.run(
            [str(CLI_PATH), "osd", "status"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("type", data)
        self.assertIn("value", data)

    def test_cli_subcommand_readings(self):
        res = subprocess.run(
            [str(CLI_PATH), "readings"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        required_keys = [
            "time",
            "date",
            "power",
            "battery",
            "cpu",
            "memory",
            "temps",
            "fan",
            "network",
            "profile",
        ]
        for key in required_keys:
            self.assertIn(key, data, f"Missing key '{key}' in readings output")

    def test_cli_subcommand_graph(self):
        res = subprocess.run(
            [str(CLI_PATH), "graph", "data"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("cpu", data)
        self.assertIn("values", data["cpu"])

    def test_cli_subcommand_park(self):
        res = subprocess.run(
            [str(CLI_PATH), "park", "--oneshot"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("left", data)
        self.assertIn("right", data)

    def test_cli_subcommand_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_env = dict(self.env, XDG_PICTURES_DIR=tmp_dir)
            res = subprocess.run(
                [str(CLI_PATH), "screenshot"],
                capture_output=True,
                text=True,
                env=test_env,
            )
            self.assertEqual(res.returncode, 0)

    def test_cli_subcommand_daemon(self):
        res = subprocess.run(
            [str(CLI_PATH), "daemon", "status"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_bin_dir = Path(tmp_dir) / "bin"
            mock_bin_dir.mkdir(parents=True, exist_ok=True)
            mock_eww = mock_bin_dir / "eww"
            log_file = Path(tmp_dir) / "eww_calls.log"

            mock_eww.write_text(
                f"#!/usr/bin/env bash\n"
                f'echo "$@" >> "{log_file}"\n'
                f"exit 0\n"
            )
            mock_eww.chmod(0o755)

            mock_env = dict(
                self.env,
                PATH=f"{mock_bin_dir}:{os.environ.get('PATH', '')}",
            )

            res_open = subprocess.run(
                [str(CLI_PATH), "daemon", "open"],
                capture_output=True,
                text=True,
                env=mock_env,
            )
            self.assertEqual(res_open.returncode, 0)
            calls = log_file.read_text()
            for w in ["background", "title-block", "top-margin", "side-margins-left", "side-margins-right", "bottom-margin"]:
                self.assertIn(w, calls)

    def test_cli_subcommand_drawn_click(self):
        res = subprocess.run(
            [str(CLI_PATH), "drawn-click"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(res.returncode, 0)

    def test_cli_eww_config_flag_isolation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_bin_dir = Path(tmp_dir) / "bin"
            mock_bin_dir.mkdir(parents=True, exist_ok=True)
            mock_eww = mock_bin_dir / "eww"
            log_file = Path(tmp_dir) / "eww_calls.log"

            mock_eww.write_text(
                f"#!/usr/bin/env bash\n"
                f'echo "$@" >> "{log_file}"\n'
                f'if [ "$1" = "ping" ] || [ "$3" = "ping" ]; then\n'
                f'  echo "pong"\n'
                f"fi\n"
                f"exit 0\n"
            )
            mock_eww.chmod(0o755)

            mock_env = dict(
                self.env,
                PATH=f"{mock_bin_dir}:{os.environ.get('PATH', '')}",
            )

            res = subprocess.run(
                [str(CLI_PATH), "daemon", "ping"],
                capture_output=True,
                text=True,
                env=mock_env,
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(log_file.exists(), "Mock eww was not called")
            log_content = log_file.read_text()
            self.assertIn("-c", log_content, "eww was invoked without -c flag")
            self.assertIn(str(WORKTREE_DIR), log_content, "eww was not passed worktree config directory")

    def test_scss_lint_no_forbidden_gtk_properties(self):
        scss_files = list(WORKTREE_DIR.glob("**/*.scss"))
        self.assertTrue(len(scss_files) > 0, "No SCSS files found")

        for scss_file in scss_files:
            content = scss_file.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_SCSS_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                self.assertIsNone(
                    match,
                    f"Forbidden GTK CSS pattern '{pattern}' found in {scss_file.relative_to(WORKTREE_DIR)}: {match.group(0) if match else ''}",
                )

        eww_scss = WORKTREE_DIR / "eww.scss"
        if shutil.which("npx"):
            compile_res = subprocess.run(
                ["npx", "sass", "--no-source-map", str(eww_scss)],
                capture_output=True,
                text=True,
                cwd=str(WORKTREE_DIR),
            )
            self.assertEqual(compile_res.returncode, 0, f"SCSS compilation failed: {compile_res.stderr}")
            compiled_css = compile_res.stdout
            for pattern in FORBIDDEN_SCSS_PATTERNS:
                match = re.search(pattern, compiled_css, re.IGNORECASE)
                self.assertIsNone(
                    match,
                    f"Forbidden GTK CSS pattern '{pattern}' found in compiled CSS: {match.group(0) if match else ''}",
                )

    def test_backend_scripts_json_contracts(self):
        scripts_dir = WORKTREE_DIR / "scripts"

        readings_res = subprocess.run(
            ["python3", str(scripts_dir / "readings.py")],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(readings_res.returncode, 0)
        readings_json = json.loads(readings_res.stdout)
        for k in ["time", "date", "power", "battery", "cpu", "memory", "temps", "fan", "network", "profile"]:
            self.assertIn(k, readings_json)

        schedules_res = subprocess.run(
            ["python3", str(scripts_dir / "schedules.py"), "data"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(schedules_res.returncode, 0)
        sched_json = json.loads(schedules_res.stdout)
        for k in ["equipment", "processes", "revisions"]:
            self.assertIn(k, sched_json)

        launcher_res = subprocess.run(
            ["python3", str(scripts_dir / "launcher.py"), "list"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(launcher_res.returncode, 0)
        launcher_json = json.loads(launcher_res.stdout)
        self.assertIn("items", launcher_json)
        self.assertIsInstance(launcher_json["items"], list)

        graphs_res = subprocess.run(
            ["python3", str(scripts_dir / "graphs.py"), "data"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(graphs_res.returncode, 0)
        graphs_json = json.loads(graphs_res.stdout)
        self.assertIn("cpu", graphs_json)
        self.assertIn("svg_path", graphs_json)

        parked_res = subprocess.run(
            ["python3", str(scripts_dir / "parked.py"), "--oneshot"],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(parked_res.returncode, 0)
        parked_json = json.loads(parked_res.stdout)
        self.assertIn("left", parked_json)
        self.assertIn("right", parked_json)

        alerts_res = subprocess.run(
            ["python3", str(scripts_dir / "alerts.py")],
            capture_output=True,
            text=True,
            env=self.env,
        )
        self.assertEqual(alerts_res.returncode, 0)
        alerts_json = json.loads(alerts_res.stdout)
        for k in ["urgent", "hot", "battery_low", "text"]:
            self.assertIn(k, alerts_json)


if __name__ == "__main__":
    unittest.main()
