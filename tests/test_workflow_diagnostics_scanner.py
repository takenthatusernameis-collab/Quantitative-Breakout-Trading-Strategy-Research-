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
        elif isinstance(node, ast.FunctionDef) and node.name in {"redact", "scan_log_archive"}:
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
