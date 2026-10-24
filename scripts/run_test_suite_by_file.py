#!/usr/bin/env python3
"""Run every pytest module in an isolated subprocess with durable per-file status.

This is a diagnostic/CI runner for a repository whose large tamper-test mirrors
can exceed a caller's command timeout. It does not skip tests or treat a timeout
as success. It is deliberately file-isolated: module/session fixtures are not
shared across subprocesses, so its report describes isolated module execution,
not a claim that a single-process test-suite run passed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

STATUSES = ("PASS", "FAIL", "TIMEOUT", "ERROR", "INTERRUPTED", "NOT_RUN")
SUMMARY_TOKEN = re.compile(
    r"\b(?P<count>\d+)\s+(?P<kind>passed|failed|errors?|skipped|xfailed|xpassed|deselected)\b",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def discover_test_modules(repo_root: Path, tests_dir: str = "tests") -> List[str]:
    """Return sorted pytest-style test-module paths relative to the repository."""
    root = Path(repo_root).resolve()
    test_root = (root / tests_dir).resolve()
    if not test_root.is_relative_to(root):
        raise ValueError("tests directory must be inside the repository root")
    if not test_root.is_dir():
        raise FileNotFoundError(f"tests directory not found: {test_root}")

    modules = []
    for path in test_root.rglob("*.py"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            modules.append(path.relative_to(root).as_posix())
    return sorted(set(modules))


def parse_pytest_counts(log_path: Path) -> Dict[str, int]:
    """Parse the compact pytest summary at the end of a module log, if present."""
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 16_384))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return {}

    counts: Dict[str, int] = {}
    for line in tail.splitlines():
        if " in " not in line or not any(
            token in line.lower()
            for token in ("passed", "failed", "error", "skipped", "xfailed", "xpassed", "deselected")
        ):
            continue
        for match in SUMMARY_TOKEN.finditer(line):
            kind = match.group("kind").lower()
            if kind == "errors":
                kind = "error"
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
    return counts


def summarize(results: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Count module statuses. Only a clean PASS contributes to passed."""
    summary = {status: 0 for status in STATUSES}
    for result in results:
        status = str(result.get("status", "ERROR"))
        if status not in summary:
            status = "ERROR"
        summary[status] += 1
    summary["TOTAL"] = len(results)
    return summary


def _stop_process_tree(process: subprocess.Popen, grace_seconds: float = 5.0) -> None:
    """Terminate a timed-out pytest process and its child processes."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
        # Kill the group even if the pytest leader exited but left a child behind.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
    else:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def run_test_module(
    repo_root: Path,
    module_path: str,
    log_path: Path,
    timeout_seconds: int,
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Run one module, capturing all output and enforcing a per-module timeout."""
    started_utc = utc_now()
    started = time.monotonic()
    command = [sys.executable, "-m", "pytest", "-q", module_path]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process: Optional[subprocess.Popen] = None
    status = "ERROR"
    exit_code: Optional[int] = None
    error: Optional[str] = None

    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(
                command,
                cwd=str(repo_root),
                env=dict(env) if env is not None else None,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name == "posix"),
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
                status = "PASS" if exit_code == 0 else "FAIL"
            except subprocess.TimeoutExpired:
                _stop_process_tree(process)
                status = "TIMEOUT"
            except KeyboardInterrupt:
                _stop_process_tree(process)
                status = "INTERRUPTED"
                error = "interrupted by user"
    except OSError as exc:
        error = f"{type(exc).__name__}: {exc}"
        try:
            with log_path.open("a", encoding="utf-8") as log:
                log.write("\nRUNNER ERROR: " + error + "\n")
        except OSError:
            pass

    duration = round(time.monotonic() - started, 3)
    return {
        "module": module_path,
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "started_at_utc": started_utc,
        "log_path": str(log_path),
        "pytest_counts": parse_pytest_counts(log_path),
        "error": error,
    }


def _aggregate_pytest_counts(results: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    aggregate: Dict[str, int] = {}
    for result in results:
        for kind, count in (result.get("pytest_counts") or {}).items():
            aggregate[kind] = aggregate.get(kind, 0) + int(count)
    return aggregate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run each pytest module in a separate process and report every module status."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (default: parent of this script's directory)",
    )
    parser.add_argument("--tests-dir", default="tests", help="test directory relative to repository root")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="per-module timeout in seconds (default: 900)",
    )
    parser.add_argument(
        "--overall-timeout-seconds",
        type=int,
        default=19_800,
        help="total time budget in seconds (default: 19,800; 5.5 hours)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("test-results/per-file-logs"),
        help="directory for module logs, relative to repository root unless absolute",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("test-results/per-file-report.json"),
        help="JSON report path, relative to repository root unless absolute",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.timeout_seconds < 1:
        raise SystemExit("--timeout-seconds must be at least 1")
    if args.overall_timeout_seconds < 1:
        raise SystemExit("--overall-timeout-seconds must be at least 1")

    try:
        modules = discover_test_modules(root, args.tests_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if not modules:
        raise SystemExit("no pytest test modules were discovered; refusing an empty-suite success")

    log_dir = args.log_dir if args.log_dir.is_absolute() else root / args.log_dir
    report_path = args.report_json if args.report_json.is_absolute() else root / args.report_json
    log_dir.mkdir(parents=True, exist_ok=True)
    started_utc = utc_now()
    started = time.monotonic()
    results: List[Dict[str, Any]] = []
    interrupted = False

    environment = os.environ.copy()
    print(
        f"Discovered {len(modules)} test modules; timeout={args.timeout_seconds}s/module; "
        f"overall budget={args.overall_timeout_seconds}s.",
        flush=True,
    )

    for index, module in enumerate(modules, start=1):
        elapsed = time.monotonic() - started
        remaining = args.overall_timeout_seconds - elapsed
        if remaining <= 0:
            for not_run in modules[index - 1 :]:
                results.append({
                    "module": not_run,
                    "status": "NOT_RUN",
                    "exit_code": None,
                    "duration_seconds": 0.0,
                    "started_at_utc": None,
                    "log_path": None,
                    "pytest_counts": {},
                    "error": "overall time budget exhausted before module started",
                })
            break

        safe_name = module.replace("/", "__").replace("\\", "__")
        log_path = log_dir / (safe_name + ".log")
        effective_timeout = max(1, min(args.timeout_seconds, int(remaining)))
        print(
            f"[{index}/{len(modules)}] RUN {module} (timeout {effective_timeout}s)",
            flush=True,
        )
        result = run_test_module(root, module, log_path, effective_timeout, environment)
        results.append(result)
        print(
            f"[{index}/{len(modules)}] {result['status']} {module} "
            f"({result['duration_seconds']}s; exit={result['exit_code']})",
            flush=True,
        )
        if result["status"] == "INTERRUPTED":
            interrupted = True
            for not_run in modules[index:]:
                results.append({
                    "module": not_run,
                    "status": "NOT_RUN",
                    "exit_code": None,
                    "duration_seconds": 0.0,
                    "started_at_utc": None,
                    "log_path": None,
                    "pytest_counts": {},
                    "error": "run interrupted before module started",
                })
            break

    finished_utc = utc_now()
    summary = summarize(results)
    report = {
        "runner": "scripts/run_test_suite_by_file.py",
        "mode": "isolated_pytest_module_subprocesses",
        "note": (
            "Module/session fixtures are not shared between subprocesses. "
            "A module timeout, failure, runner error, interruption, or NOT_RUN "
            "status makes the run non-green."
        ),
        "repository_root": str(root),
        "started_at_utc": started_utc,
        "finished_at_utc": finished_utc,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "per_module_timeout_seconds": args.timeout_seconds,
        "overall_timeout_seconds": args.overall_timeout_seconds,
        "discovered_modules": len(modules),
        "summary": summary,
        "pytest_case_counts_from_module_summaries": _aggregate_pytest_counts(results),
        "results": results,
    }
    _write_atomic(report_path, report)
    print(json.dumps({"summary": summary, "pytest_case_counts": report["pytest_case_counts_from_module_summaries"]}, sort_keys=True))
    print(f"Detailed report: {report_path}")
    print(f"Module logs: {log_dir}")

    if interrupted:
        return 130
    return 0 if summary["TOTAL"] == summary["PASS"] and summary["TOTAL"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
