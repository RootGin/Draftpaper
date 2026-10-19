#!/usr/bin/env python3
import os
import sys
import time
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
WORKTREE_DIR = TESTS_DIR.parent
if str(WORKTREE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKTREE_DIR))

TEST_MODULES = [
    "tests.test_01_scaffold",
    "tests.test_02_background",
    "tests.test_03_title_block",
    "tests.test_04_top_margin",
    "tests.test_05_notifications_osd",
    "tests.test_06_bottom_margin",
    "tests.test_07_side_margins",
    "tests.test_08_schedules",
    "tests.test_09_load_graphs",
    "tests.test_10_launcher",
    "tests.test_11_cli_integration",
]


def run_suite():
    os.environ["DRAFTPAPER_CONFIG_DIR"] = str(WORKTREE_DIR)
    os.environ["EWW_DIR"] = str(WORKTREE_DIR)
    os.environ["DRAFTPAPER_MOCK"] = "1"

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for mod in TEST_MODULES:
        try:
            suite.addTests(loader.loadTestsFromName(mod))
        except Exception as e:
            sys.stderr.write(f"Failed to load {mod}: {e}\n")
            return 1

    runner = unittest.TextTestRunner(verbosity=2)
    start_time = time.time()
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print(
        f"\nRan {result.testsRun} tests across {len(TEST_MODULES)} modules in {elapsed:.2f}s "
        f"({len(result.failures)} failures, {len(result.errors)} errors, {len(result.skipped)} skipped)"
    )

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_suite())
