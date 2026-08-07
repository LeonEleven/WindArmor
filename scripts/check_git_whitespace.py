#!/usr/bin/env python3
"""Check committed GitHub event ranges, or local changes, for whitespace errors."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ZERO_SHA = "0" * 40


def _run(repo_root: Path, *args: str) -> None:
    print("+ git", " ".join(args), flush=True)
    subprocess.run(("git", *args), cwd=repo_root, check=True)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    head = os.environ.get("GITHUB_HEAD_SHA") or os.environ.get("GITHUB_SHA", "")
    if event == "pull_request":
        base = os.environ.get("GITHUB_BASE_SHA", "")
        if not base or not head:
            print("pull_request whitespace check requires base and head SHAs", file=sys.stderr)
            return 2
        _run(repo_root, "diff", "--check", f"{base}...{head}")
    elif event == "push":
        before = os.environ.get("GITHUB_EVENT_BEFORE", "")
        if not head:
            print("push whitespace check requires GITHUB_SHA", file=sys.stderr)
            return 2
        if before and before != ZERO_SHA:
            _run(repo_root, "diff", "--check", f"{before}..{head}")
        else:
            _run(repo_root, "diff-tree", "--check", "--root", "-r", head)
    elif event == "workflow_dispatch":
        if not head:
            print("workflow_dispatch whitespace check requires GITHUB_SHA", file=sys.stderr)
            return 2
        _run(repo_root, "diff-tree", "--check", "--root", "-r", head)
    else:
        _run(repo_root, "diff-tree", "--check", "--root", "-r", "HEAD")
        _run(repo_root, "diff", "--check", "--", ".", ":(exclude)docs/NEXT_COMMAND.md")
        _run(repo_root, "diff", "--cached", "--check")
    print("Git whitespace check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
