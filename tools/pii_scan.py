#!/usr/bin/env python3
"""pii_scan.py - the public-build guard for fact-provenance.

Fails whenever a file that would be published carries an internal marker: a
private LAN address, a host address, an internal job/agent name, or any
reference to the internal-only strategy build.

Usage
  python3 tools/pii_scan.py                  # scan the repo's tracked files
  python3 tools/pii_scan.py PATH [PATH...]   # scan explicit files/dirs
  python3 tools/pii_scan.py --self-test      # prove the guard can actually fail

Exit status
  0  clean: every scanned file is text and no marker appears anywhere
  1  at least one marker hit, or a scanned file could not be read as text

Design notes (the reasoning matters more than the code)
  * Scope is git's own view of the tree (`git ls-files`). Anything .gitignore'd
    stays out of scope, so local state (databases, logs, evidence dirs) cannot
    break the build - and a file that was accidentally git-added cannot hide
    from the scan.
  * This file is skipped when it scans the tree, and only this file: a list of
    what must never be published has to contain the things it looks for. The
    skip is printed on every run so it can never be silent.
  * A binary file is UNSCANNED, and UNSCANNED fails the build. Compressed
    formats (.docx, .zip) hide their text from a byte scan, so "not a text
    file" must never be reported as "clean" - that is the exact hole this guard
    exists to close.
  * Marker hit lines are truncated to 120 characters: enough to find the file
    and line, not so much that the artefact leaks into a CI log.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

MARKERS = [
    ".207",                     # private LAN host, internal fleet
    "fleet node",               # internal fleet vocabulary
    "fp-job",                   # internal job name
    "primary agent",            # internal role name
    "192.168.",                 # RFC1918 private LAN
    "63.35.224.96",             # public address of a private host
    'id="internal"',            # marker attribute of the internal plan build
    "stratplan-internal.html",  # filename of the internal plan build
    # added after a real miss: the published plan carried the internal build's
    # own scope label and infra paths, and this guard still said PASS
    "LAN only",
    "internal &middot; LAN only",
    "Internal annex",
    "Fleet roles",
    "/opt/",
    "/home/",
    "/srv/",
    "Cloudflare",
    "Lightsail",
    "Rennwick",
    "rennwick",
    "Churchill",
]

SELF = pathlib.Path(__file__).resolve()
IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "evidence", "node_modules"}


def tracked_files(root: pathlib.Path) -> list[pathlib.Path] | None:
    """Files git tracks under root, or None if root is not a git work tree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [root / name for name in out.stdout.decode().split("\0") if name]


def walk_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Fallback for a plain directory (not a git work tree)."""
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix in {".db", ".log"} or path.name.endswith((".db-wal", ".db-shm")):
            continue
        out.append(path)
    return out


def read_text(path: pathlib.Path) -> tuple[str | None, str | None]:
    """(text, None) for a text file, (None, reason) for anything else."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"unreadable ({exc.strerror or exc})"
    if b"\0" in raw[:8192]:
        return None, "binary (NUL byte in the first 8 KiB)"
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"binary (not UTF-8: {exc.reason} at byte {exc.start})"


def scan(path: pathlib.Path) -> tuple[list[tuple[int, str, str]], str | None]:
    text, why = read_text(path)
    if text is None:
        return [], why
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for marker in MARKERS:
            if marker in line:
                hits.append((lineno, marker, line.strip()[:120]))
    return hits, None


def self_test() -> int:
    """Write a file that carries a marker and check the guard refuses it."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bait = pathlib.Path(tmp) / "bait.txt"
        bait.write_text(f"a host replied: {MARKERS[0]} ok\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SELF), str(bait)], capture_output=True, text=True,
        )
    print(proc.stdout.strip())
    if proc.returncode == 1:
        print("self-test: PASS - the guard failed the bait file (exit 1)")
        return 0
    print(f"self-test: FAIL - the guard accepted a marker file (exit {proc.returncode})")
    return 1


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args and args[0] == "--self-test":
        return self_test()

    root = pathlib.Path.cwd()
    if args:
        mode = "explicit"
        targets: list[pathlib.Path] = []
        for arg in args:
            path = pathlib.Path(arg)
            if path.is_dir():
                targets += [p for p in sorted(path.rglob("*")) if p.is_file()]
            elif path.is_file():
                targets.append(path)
            else:
                print(f"pii_scan: no such path: {arg}")
                return 1
    else:
        mode = "tracked"
        targets = tracked_files(root) or []
        if not targets:
            mode = "walk"
            targets = walk_files(root)
        if not targets:
            print("pii_scan: nothing to scan (empty tree?)")
            return 1

    print(f"pii_scan: {len(MARKERS)} markers, mode={mode}, {len(targets)} file(s)")
    problems = 0
    for path in targets:
        # A marker list has to contain the markers, so this file is always skipped
        # unless the caller names it explicitly and nothing else - the skip is
        # printed on every run, never silent.
        if path.resolve() == SELF and not (mode == "explicit" and len(targets) == 1):
            print(f"  skip  {path}  (the marker list lives in this file)")
            continue
        hits, why = scan(path)
        if why:
            problems += 1
            print(f"  FAIL  {path}: UNSCANNED - {why}")
            print("        a binary artefact cannot be certified clean: keep it out of the public build")
            continue
        for lineno, marker, excerpt in hits:
            problems += 1
            print(f"  FAIL  {path}:{lineno}: marker {marker!r} - {excerpt}")
    if problems:
        print(f"\npii_scan: FAIL - {problems} problem(s). Nothing internal may be published.")
        return 1
    print(f"\npii_scan: PASS - 0 markers, 0 unscannable files.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
