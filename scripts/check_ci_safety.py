#!/usr/bin/env python3
"""Reject hardware-capable commands and runner settings from software CI."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


COMMAND_PATTERNS = (
    ("ROS node execution", re.compile(r"\bros2\s+(?:run|launch)\b", re.I)),
    (
        "CAN setup script",
        re.compile(
            r"(?:^|[\s;&|])(?:sudo\s+)?(?:\./)?(?:scripts/)?setup_can\.sh\b",
            re.I,
        ),
    ),
    ("robot CAN interface", re.compile(r"\bcan10\b", re.I)),
    ("IMU device", re.compile(r"/dev/imu_usb\b", re.I)),
    ("CAN link configuration", re.compile(r"\bip\s+link\s+set\b", re.I)),
    ("kernel module loading", re.compile(r"(?:^|[;&|]\s*|\bsudo\s+)modprobe\b", re.I)),
    ("GPIO write", re.compile(r"\bgpio\s+write\b", re.I)),
    ("privileged container", re.compile(r"--privileged\b", re.I)),
    ("container device passthrough", re.compile(r"\bdocker\b[^\n]*--device\b", re.I)),
)


def _without_comment_lines(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _yaml_run_blocks(text: str) -> list[str]:
    """Extract YAML run scalars without requiring a YAML dependency."""
    lines = text.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("#"):
            index += 1
            continue
        match = re.match(r"^(\s*)(?:-\s*)?run\s*:\s*(.*)$", line)
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        value = match.group(2).strip()
        if value not in {"|", ">", "|-", ">-", "|+", ">+"}:
            blocks.append(value)
            index += 1
            continue
        block_lines: list[str] = []
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= indent:
                break
            if not candidate.lstrip().startswith("#"):
                block_lines.append(candidate)
            index += 1
        blocks.append("\n".join(block_lines))
    return blocks


def check_path(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if path.suffix in {".yml", ".yaml"}:
        active_text = _without_comment_lines(text)
        if re.search(r"\bruns-on\s*:[^\n]*\bself-hosted\b", active_text, re.I):
            errors.append("self-hosted runner")
        if re.search(r"^\s*-\s*self-hosted\s*$", active_text, re.I | re.M):
            errors.append("self-hosted runner")
        if re.search(r"(?:--device(?:=|\s+)|devices?\s*:)[^\n]*/dev/", active_text, re.I):
            errors.append("/dev device mapping")
        if re.search(r"^\s*-\s*/dev(?:/|:)", active_text, re.I | re.M):
            errors.append("/dev volume mapping")
        if re.search(r"\boptions\s*:[^\n]*--privileged\b", active_text, re.I):
            errors.append("privileged container")
        command_text = "\n".join(_yaml_run_blocks(text))
    else:
        command_text = _without_comment_lines(text)
    command_text = re.sub(r"\\\s*\n", " ", command_text)

    for label, pattern in COMMAND_PATTERNS:
        if pattern.search(command_text):
            errors.append(label)
    return errors


def default_targets(repo_root: Path) -> list[Path]:
    workflows = sorted((repo_root / ".github" / "workflows").glob("*.y*ml"))
    return [*workflows, repo_root / "scripts" / "ci_software.sh"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    targets = args.paths or default_targets(repo_root)
    failed = False
    for path in targets:
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.is_file():
            print(f"CI safety target is missing: {resolved}", file=sys.stderr)
            failed = True
            continue
        for error in check_path(resolved):
            print(f"{resolved}: forbidden CI capability: {error}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    print(f"CI safety check passed for {len(targets)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
