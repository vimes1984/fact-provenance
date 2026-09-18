#!/usr/bin/env python3
"""Documentation gate: every module, class and function carries a docstring.

  python3 tools/doc_coverage.py            # scan every .py file git tracks
  python3 tools/doc_coverage.py PATH ...   # scan explicit files or directories
  python3 tools/doc_coverage.py --min 90   # allow a floor (CI uses the default)

Why a gate rather than a convention: "the code is documented" is a claim about
the whole tree, and claims about the whole tree are exactly the kind that rot.
This counts what is there, names what is missing with a line number, and fails
below the floor, so the policy is a command instead of an intention.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys

IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "build", "dist", "node_modules"}
SKIP_FILES = {"setup.py"}  # keep in step with tools/pii_scan.py's ignore set where it matters


def python_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Every .py file git tracks under root, or every one on disk if it is not a work tree.

    Tracked is the right scope for the same reason it is in the release gate:
    generated or ignored code is not what a reader of this repository sees.
    """
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                             check=True, capture_output=True)
        names = [n for n in out.stdout.decode().split("\0") if n.endswith(".py")]
        return [root / n for n in names]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in sorted(root.rglob("*.py"))
                if not any(part in IGNORE_DIRS for part in p.parts)]


def nodes_of(tree: ast.Module) -> list[tuple[str, int, str | None]]:
    """(kind, line, docstring-or-None) for the module and every class/function in it.

    Nested functions are included: a helper that only exists inside another
    function still has to say what it does, or a reader has to reverse it.
    """
    out: list[tuple[str, int, str | None]] = [
        ("module", 1, ast.get_docstring(tree))]
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            out.append((kind, node.lineno, ast.get_docstring(node)))
    return sorted(out, key=lambda item: item[1])


def report(path: pathlib.Path, root: pathlib.Path) -> tuple[int, int, list[str]]:
    """(documented, total, missing-labels) for one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return 0, 1, [f"{path.relative_to(root)}: unreadable ({exc})"]

    documented, missing = 0, []
    for kind, line, doc in nodes_of(tree):
        label = f"{path}:{line} {kind}"
        if doc and doc.strip():
            documented += 1
        else:
            missing.append(label)
    return documented, documented + len(missing), missing


def main() -> int:
    """Scan the tree, print the coverage, exit non-zero if anything is undocumented."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="files or directories (default: the tree git tracks)")
    ap.add_argument("--min", type=float, default=100.0,
                    help="minimum coverage percent required to pass (default 100)")
    args = ap.parse_args()

    root = pathlib.Path.cwd()
    if args.paths:
        targets: list[pathlib.Path] = []
        for raw in args.paths:
            p = pathlib.Path(raw)
            if p.is_dir():
                targets += [q for q in sorted(p.rglob("*.py"))
                            if not any(part in IGNORE_DIRS for part in q.parts)]
            elif p.is_file():
                targets.append(p)
            else:
                print(f"doc_coverage: no such path: {raw}")
                return 1
    else:
        targets = [p for p in python_files(root) if p.name not in SKIP_FILES]

    if not targets:
        print("doc_coverage: nothing to scan")
        return 1

    documented = total = 0
    problems: list[str] = []
    print(f"doc_coverage: {len(targets)} file(s)")
    for path in targets:
        got, count, missing = report(path, root)
        documented += got
        total += count
        state = "ok" if not missing else f"{len(missing)} missing"
        print(f"  {state:>10}  {path.relative_to(root) if path.is_relative_to(root) else path}"
              f"  ({got}/{count})")
        problems += missing

    pct = 100.0 * documented / max(total, 1)
    for label in problems:
        print(f"  MISSING  {label}")

    print(f"\ndoc_coverage: {documented}/{total} documented ({pct:.1f}%), "
          f"floor {args.min:.0f}%")
    if problems or pct < args.min:
        print("doc_coverage: FAIL - every module, class and function needs a docstring, "
              "and nested helpers are not exempt.")
        return 1
    print("doc_coverage: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
