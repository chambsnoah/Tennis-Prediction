#!/usr/bin/env python3
"""Verify the current code with pytest rather than historical success claims."""

from pathlib import Path
import subprocess
import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=Path(__file__).resolve().parents[1],
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
