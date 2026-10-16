"""Regression tests for the inline GitHub Actions diagnostic log scanner."""
import ast
import io
import re
import textwrap
import zipfile
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "main.yml"


def _load_scanner():
    """Load only the scanner's constants/functions; never execute workflow side effects."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines)
        if line.strip() == "python3 <<'PYTHON'"
    )
    end = next(
        i for i in range(start + 1, len(lines))
        if lines[i].strip() == "PYTHON"
    )
    source = textwrap.dedent("\n".join(lines[start + 1 : end]))
    parsed = ast.parse(source, filename=str(WORKFLOW))

    wanted_constants = {
        "MAX_ERROR_LINES_PER_RUN",
        "MAX_NEW_RUNS_PER_INVOCATION",
        "MAX_ERROR_CANDIDATES_PER_RUN",
        "MAX_PRIORITY_ERROR_CANDIDATES",
        "MAX_LOG_FILE_BYTES",
        "MAX_EXCERPT_CHARS",
        "ANSI_RE",
        "COMMAND_ECHO_RE",
        "KILO_INVALID_ARGUMENT_ABORT_RE",
        "KILO_EDIT_INVALID_ARGUMENT_RE",
        "ERROR_RE",
        "BEARER_RE",
        "GH_TOKEN_RE",
        "JWT_RE",
        "SECRET_ASSIGN_RE",
        "URL_SECRET_RE",
        "LONG_VALUE_RE",
    }
    selected = []
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if names & wanted_constants:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {
            "run_key", "redact", "scan_log_archive",
            "select_runs_for_processing", "preserve_additional_fields",
        }:
            selected.append(node)

    namespace = {"io": io, "re": re, "zipfile": zipfile}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(WORKFLOW), "exec"), namespace)
    return namespace


def _archive(log_lines):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("0_kilo.txt", "\n".join(log_lines))
    return stream.getvalue()


def test_scanner_filters_echoed_source_and_prioritizes_edit_abort():
    scanner = _load_scanner()
    log_lines = []

    # These cyan lines represent GitHub's echoed shell/workflow source. The old
    # scanner matched "failed" and "RuntimeError" in these lines as if they ran.
    for i in range(30):
        log_lines.append(
            f'2026-10-16T16:43:{i:02d}.0000000Z '
            f'\x1b[36;1m echo "source_echo_marker_{i}: failed RuntimeError:" \x1b[0m'
        )

    # More than the excerpt budget of ordinary errors makes prioritization observable.
    for i in range(25):
        log_lines.append(
            f"2026-10-16T16:50:{i:02d}.0000000Z TypeError: synthetic runtime error {i}"
        )

    for i in range(3):
        log_lines.append(
            f'2026-10-16T16:55:{i:02d}.0000000Z '
            '\x1b[91mError: \x1b[0mThe edit tool was called with invalid arguments: '
            '["filePath"] is missing and is required'
        )

    log_lines.append(
        '2026-10-16T16:55:51.6284984Z \x1b[91mError: \x1b[0m'
        'Stopped after 3 consecutive invalid-argument failures for the "edit" tool. '
        "The model kept re-issuing malformed input, so the turn was aborted."
    )

    archive_bytes = _archive(log_lines)
    scanner["download_log_archive"] = lambda run: (archive_bytes, False)
    signals, status = scanner["scan_log_archive"]({"id": 123})

    assert status == "scanned_with_excerpt_limit"
    assert len(signals) == scanner["MAX_ERROR_LINES_PER_RUN"]
    assert signals[0]["signal_kind"] == "kilo_invalid_argument_turn_abort"
    assert "Stopped after 3 consecutive invalid-argument failures" in signals[0]["excerpt"]
    assert [s["signal_kind"] for s in signals[1:4]] == [
        "kilo_edit_tool_invalid_arguments"
    ] * 3
    assert not any("source_echo_marker" in s["excerpt"] for s in signals)
    assert any("TypeError:" in s["excerpt"] for s in signals[4:])


def test_scanner_marks_small_clean_scan_without_excerpt_limit():
    scanner = _load_scanner()
    log_lines = [
        '2026-10-16T16:43:00.0000000Z \x1b[36;1m echo "failed source only" \x1b[0m',
        "2026-10-16T16:50:00.0000000Z normal progress output",
        '2026-10-16T16:55:51.6284984Z \x1b[91mError: \x1b[0m'
        'Stopped after 3 consecutive invalid-argument failures for the "edit" tool.',
    ]
    archive_bytes = _archive(log_lines)
    scanner["download_log_archive"] = lambda run: (archive_bytes, False)

    signals, status = scanner["scan_log_archive"]({"id": 124})

    assert status == "scanned"
    assert len(signals) == 1
    assert signals[0]["signal_kind"] == "kilo_invalid_argument_turn_abort"



def _api_completed_run(run_id, conclusion):
    return {
        "id": run_id,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": conclusion,
        "updated_at": "2026-10-16T20:00:00Z",
        "created_at": "2026-10-16T19:00:00Z",
    }


def _stale_ledger_record(run_id, status):
    return {
        "run_id": run_id,
        "run_attempt": 1,
        "status": status,
        "conclusion": "",
        "run_completed_at": None,
        "capture_status": "complete",
        "log_capture_status": "n/a",
        "next_action": "preserve this repository-specific note",
    }


def test_completed_success_refreshes_stale_in_progress_record():
    scanner = _load_scanner()
    run = _api_completed_run(201, "success")
    previous = _stale_ledger_record(201, "in_progress")

    selected = scanner["select_runs_for_processing"](
        [run], {"201:1": previous}
    )

    assert selected == [(run, previous)]
    refreshed = scanner["preserve_additional_fields"](
        {
            "run_id": 201,
            "run_attempt": 1,
            "status": run["status"],
            "conclusion": run["conclusion"],
            "run_completed_at": run["updated_at"],
            "capture_status": "complete",
        },
        previous,
    )
    assert refreshed["status"] == "completed"
    assert refreshed["conclusion"] == "success"
    assert refreshed["run_completed_at"] == "2026-10-16T20:00:00Z"
    assert refreshed["next_action"] == "preserve this repository-specific note"


def test_completed_cancelled_run_refreshes_stale_pending_record():
    scanner = _load_scanner()
    run = _api_completed_run(202, "cancelled")
    previous = _stale_ledger_record(202, "pending")

    selected = scanner["select_runs_for_processing"](
        [run], {"202:1": previous}
    )

    assert selected == [(run, previous)]


def test_fully_terminal_record_with_complete_capture_is_not_reprocessed():
    scanner = _load_scanner()
    run = _api_completed_run(203, "success")
    previous = {
        "run_id": 203,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "run_completed_at": run["updated_at"],
        "capture_status": "complete",
    }

    selected = scanner["select_runs_for_processing"](
        [run], {"203:1": previous}
    )

    assert selected == []


def test_partial_capture_is_still_retried_after_terminal_state_is_recorded():
    scanner = _load_scanner()
    run = _api_completed_run(204, "failure")
    previous = {
        "run_id": 204,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "failure",
        "run_completed_at": run["updated_at"],
        "capture_status": "partial",
    }

    selected = scanner["select_runs_for_processing"](
        [run], {"204:1": previous}
    )

    assert selected == [(run, previous)]


def test_missing_completion_timestamp_is_repaired_even_if_other_fields_are_terminal():
    scanner = _load_scanner()
    run = _api_completed_run(205, "success")
    previous = {
        "run_id": 205,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "run_completed_at": None,
        "capture_status": "complete",
    }

    selected = scanner["select_runs_for_processing"](
        [run], {"205:1": previous}
    )

    assert selected == [(run, previous)]
