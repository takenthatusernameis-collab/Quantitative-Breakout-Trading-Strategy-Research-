"""Tests for fail-closed controller progress accounting."""
from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.controller_progress import (
    KILO_COMMITTER_EMAIL,
    has_meaningful_committed_progress,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "main.yml"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "kilo-autonomous")
    git(repo, "config", "user.email", KILO_COMMITTER_EMAIL)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "baseline")
    return repo, git(repo, "rev-parse", "HEAD")


def commit_file(
    repo: Path,
    path: str,
    content: str,
    *,
    committer_name: str = "kilo-autonomous",
    committer_email: str = KILO_COMMITTER_EMAIL,
) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "-c", f"user.name={committer_name}", "-c", f"user.email={committer_email}",
        "commit", "-m", f"change {path}")
    return git(repo, "rev-parse", "HEAD")


def test_independently_committed_change_counts_only_when_remote_sha_matches(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    head = commit_file(repo, "research_state/agent_handoff.md", "verified durable progress\n")

    assert has_meaningful_committed_progress(repo, base, head) is True
    assert has_meaningful_committed_progress(repo, base, head, verified_remote_sha=head) is True


def test_local_only_commit_is_not_credited_as_verified_progress(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    head = commit_file(repo, "research_state/agent_handoff.md", "local, not remotely verified\n")

    # A local commit may be retained as recovery work, but mismatched remote
    # evidence must not set the controller's meaningful-progress flag.
    assert has_meaningful_committed_progress(repo, base, head, verified_remote_sha=base) is False
    assert has_meaningful_committed_progress(repo, base, head, verified_remote_sha=None) is True


def test_workflow_definition_only_commit_is_not_meaningful_project_progress(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    head = commit_file(repo, ".github/workflows/main.yml", "name: changed workflow\n")

    assert has_meaningful_committed_progress(repo, base, head, verified_remote_sha=head) is False


def test_commit_from_another_committer_is_not_misattributed_to_kilo(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    head = commit_file(
        repo, "research_state/external_change.md", "external change\n",
        committer_name="external-contributor",
        committer_email="external@example.invalid",
    )

    assert has_meaningful_committed_progress(repo, base, head, verified_remote_sha=head) is False


def test_reverted_change_is_not_counted_as_net_progress(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)
    commit_file(repo, "research_state/agent_handoff.md", "temporary change\n")
    head = commit_file(repo, "research_state/agent_handoff.md", "baseline\n")

    assert has_meaningful_committed_progress(repo, base, head, verified_remote_sha=head) is False


def test_no_change_does_not_count_even_when_remote_matches(tmp_path: Path) -> None:
    repo, base = make_repo(tmp_path)

    assert has_meaningful_committed_progress(repo, base, base, verified_remote_sha=base) is False


def test_workflow_wires_progress_credit_to_remote_verification_and_safe_push_mode() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'verified_remote_sha="$remote_sha"' in workflow
    assert '|| "$local_head_sha" != "$base_sha"' in workflow
    assert '--verified-remote-sha "$verified_remote_sha"' in workflow
    assert 'pending_persistence_has_project_changes=1' in workflow
    assert "if: " + "$" + "{{ github.event_name != 'push' && inputs.diagnostics_only != true }}" in workflow
    assert "python3 scripts/controller_progress.py" in workflow
