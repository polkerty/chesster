#!/usr/bin/env python3
"""
gather.py [dir] [ext1] [ext2] ... [extN]

Recursively finds all files under `dir` whose names end with any of the provided
extensions, and prints them concatenated to stdout.

For each file:
- prints the relative path (relative to `dir`) on its own line
- then prints the file contents wrapped in triple backticks

Examples:
  python gather.py . .py .md
  python gather.py src js ts css
  python gather.py /path/to/project .jsonl

Notes:
- Extensions can be provided with or without a leading dot. (".py" and "py" both work.)
- Matching is case-insensitive on extensions.
- Binary/unreadable files are skipped with a warning to stderr.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Set


def normalize_exts(exts: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for e in exts:
        e = e.strip()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        out.add(e.lower())
    return out


def iter_matching_files(root: Path, exts: Set[str]) -> List[Path]:
    files: List[Path] = []
    # rglob('*') will include directories too; filter to files.
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in exts:
            files.append(p)

    # Deterministic output order:
    files.sort(key=lambda p: str(p.relative_to(root)).replace(os.sep, "/"))
    return files


def read_text_file(path: Path) -> str:
    """
    Read text with a tolerant approach: try utf-8, then fall back to latin-1.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Recursively gather files by extension and print concatenated, wrapped in triple backticks.",
        usage="gather.py [dir] [ext1] [ext2] ... [extN]",
    )
    parser.add_argument("dir", help="Root directory to search from")
    parser.add_argument("exts", nargs="+", help="Extensions to include (e.g. .py .md or py md)")
    args = parser.parse_args(argv)

    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"error: directory does not exist: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    exts = normalize_exts(args.exts)
    matches = iter_matching_files(root, exts)

    for i, path in enumerate(matches):
        rel = path.relative_to(root)
        rel_posix = str(rel).replace(os.sep, "/")

        # Separate files by a blank line (not strictly required, but nicer).
        if i != 0:
            sys.stdout.write("\n")

        sys.stdout.write(f"{rel_posix}\n")
        sys.stdout.write("```\n")
        try:
            sys.stdout.write(read_text_file(path))
            # Ensure closing backticks start on a new line.
            if not sys.stdout.getvalue if hasattr(sys.stdout, "getvalue") else False:
                pass
        except Exception as e:
            print(f"warning: skipping unreadable file {rel_posix}: {e}", file=sys.stderr)
            sys.stdout.write(f"[unreadable: {e}]\n")
        finally:
            # Ensure there's a trailing newline before closing fence
            sys.stdout.write("" if (sys.stdout is None) else "")
        # Make sure content ends with newline before closing ```
        # (We can't easily inspect stdout, so we just write a newline unconditionally
        # if the last character wasn't newline by doing a safe check on the text.)
        try:
            txt = read_text_file(path)
            if not txt.endswith("\n"):
                sys.stdout.write("\n")
        except Exception:
            # If we couldn't read it above, we already wrote an error marker; ensure newline.
            sys.stdout.write("\n")

        sys.stdout.write("```\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
