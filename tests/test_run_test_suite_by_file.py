"""Tests for the per-module pytest runner's discovery and status accounting."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run_test_suite_by_file.py"
SPEC = importlib.util.spec_from_file_location("run_test_suite_by_file", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def test_discovery_finds_pytest_patterns_in_stable_order_and_ignores_helpers(tmp_path: Path) -> None:
    tests = tmp_path / "unit_tests"
    (tests / "nested").mkdir(parents=True)
    (tests / "__pycache__").mkdir()
    (tests / "test_b.py").write_text("def test_b(): pass\n", encoding="utf-8")
    (tests / "nested" / "a_test.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tests / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "__pycache__" / "test_ignored.py").write_text("", encoding="utf-8")

    assert runner.discover_test_modules(tmp_path, "unit_tests") == [
        "unit_tests/nested/a_test.py",
        "unit_tests/test_b.py",
    ]


def test_discovery_rejects_test_directory_outside_repository_root(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path.parent / "outside-test-directory").mkdir(exist_ok=True)

    with pytest.raises(ValueError, match="inside the repository root"):
        runner.discover_test_modules(tmp_path, "../outside-test-directory")


def test_summary_never_counts_failure_or_timeout_as_passed() -> None:
    results = [
        {"status": "PASS"},
        {"status": "FAIL"},
        {"status": "TIMEOUT"},
        {"status": "ERROR"},
        {"status": "INTERRUPTED"},
        {"status": "NOT_RUN"},
    ]

    assert runner.summarize(results) == {
        "PASS": 1,
        "FAIL": 1,
        "TIMEOUT": 1,
        "ERROR": 1,
        "INTERRUPTED": 1,
        "NOT_RUN": 1,
        "TOTAL": 6,
    }


def test_pytest_summary_parser_reports_counts_from_module_log(tmp_path: Path) -> None:
    log = tmp_path / "module.log"
    log.write_text(
        "test_example.py ....\n"
        "4 passed, 1 skipped in 0.51s\n",
        encoding="utf-8",
    )

    assert runner.parse_pytest_counts(log) == {"passed": 4, "skipped": 1}


def test_module_timeout_is_reported_as_timeout_not_success(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_slow_case.py").write_text(
        "import time\n"
        "def test_slow_case():\n"
        "    time.sleep(5)\n",
        encoding="utf-8",
    )

    result = runner.run_test_module(
        tmp_path,
        "tests/test_slow_case.py",
        tmp_path / "logs" / "slow.log",
        timeout_seconds=1,
    )

    assert result["status"] == "TIMEOUT"
    assert result["exit_code"] is None
    assert Path(result["log_path"]).is_file()
