#!/usr/bin/env python3
"""Fail-closed accounting for controller-verified Kilo project progress.

A commit is eligible only when it is in this session's base-to-HEAD history,
the configured Kilo committer touched a path that remains changed, the net
change is not a workflow definition, and any supplied verified remote SHA
exactly matches HEAD.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

KILO_COMMITTER_EMAIL = "kilo-autonomous@users.noreply.github.com"


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {detail}")
    return result.stdout


def _is_ancestor(repo: Path, base_sha: str, head_sha: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", base_sha, head_sha],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"git merge-base could not verify ancestry: {detail}")


def _nul_paths(raw: bytes) -> set[str]:
    return {part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part}


def _meaningful_committed_paths(repo: Path, base_sha: str, head_sha: str) -> set[str]:
    """Return net-changed paths touched by Kilo-committed commits in this range."""
    if base_sha == head_sha or not _is_ancestor(repo, base_sha, head_sha):
        return set()

    net_changed = _nul_paths(_git(repo, "diff", "--name-only", "-z", base_sha, head_sha))
    if not net_changed:
        return set()

    log = _git(repo, "log", "--format=%H%x09%ce", f"{base_sha}..{head_sha}").decode(
        "utf-8", errors="replace"
    )
    kilo_touched: set[str] = set()
    for row in log.splitlines():
        commit_sha, separator, committer_email = row.partition("\t")
        if not separator or committer_email.casefold() != KILO_COMMITTER_EMAIL.casefold():
            continue
        # -m also handles merge commits conservatively; the final net diff below
        # removes paths later reverted to their base content.
        kilo_touched.update(
            _nul_paths(
                _git(
                    repo, "diff-tree", "--no-commit-id", "--name-only", "-r",
                    "-m", "--root", "-z", commit_sha
                )
            )
        )

    return {
        path
        for path in (net_changed & kilo_touched)
        if not path.startswith(".github/workflows/")
    }


def has_meaningful_committed_progress(
    repo: str | Path,
    base_sha: str,
    head_sha: str,
    verified_remote_sha: str | None = None,
) -> bool:
    """Check candidate progress; require exact remote verification when supplied.

    Without verified_remote_sha the result is only a recovery candidate, not
    creditable progress. The controller only sets its progress flag using the
    verified form.
    """
    if verified_remote_sha is not None and (
        not verified_remote_sha or verified_remote_sha != head_sha
    ):
        return False
    return bool(_meaningful_committed_paths(Path(repo), base_sha, head_sha))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--verified-remote-sha")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)
    try:
        eligible = has_meaningful_committed_progress(
            args.repo, args.base_sha, args.head_sha, args.verified_remote_sha
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"controller progress check failed closed: {exc}", file=sys.stderr)
        return 2
    if eligible:
        print("Meaningful committed project change detected.")
        return 0
    print("No eligible committed project change.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
