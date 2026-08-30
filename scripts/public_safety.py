#!/usr/bin/env python3
"""Fail CI when tracked files or Git history contain likely credentials."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


SECRET_PATTERNS = (
    ("GitHub token", re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("OpenAI-style key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Stripe live key", re.compile(r"(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    ("PyPI token", re.compile(r"pypi-AgEIcHlwaS5vcmcC[A-Za-z0-9_-]{20,}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential-bearing URL", re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@", re.I)),
)

FORBIDDEN_SUFFIXES = {".key", ".keystore", ".p12", ".pem", ".pfx"}
FORBIDDEN_NAMES = {
    ".env",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "id_ed25519",
    "id_rsa",
    "secret.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8", errors="ignore")


def forbidden_path(path: str) -> bool:
    candidate = Path(path)
    name = candidate.name.casefold()
    if name in FORBIDDEN_NAMES or candidate.suffix.casefold() in FORBIDDEN_SUFFIXES:
        return True
    return name.startswith(".env.") and name != ".env.example"


def scan_text(label: str, text: str) -> list[str]:
    findings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule_name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{label}:{line_number} matches {rule_name}")
    return findings


def main() -> int:
    tracked = [item for item in git("ls-files", "-z").split("\0") if item]
    historical_paths = {
        item.strip()
        for item in git("log", "--all", "--name-only", "--pretty=format:").splitlines()
        if item.strip()
    }
    findings = [f"forbidden tracked or historical path: {path}" for path in sorted(set(tracked) | historical_paths) if forbidden_path(path)]

    for path in tracked:
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            findings.append(f"cannot inspect tracked file {path}: {exc}")
            continue
        findings.extend(scan_text(path, content))

    findings.extend(scan_text("git-history", git("log", "--all", "-p", "--format=")))
    if findings:
        print("Public safety check failed. Matched values are intentionally hidden.", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print(f"Public safety check passed: {len(tracked)} tracked files and full Git history scanned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
