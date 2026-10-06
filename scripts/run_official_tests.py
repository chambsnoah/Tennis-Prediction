#!/usr/bin/env python3
"""Run the API pytest suite, or the pytest arguments supplied by the caller."""

from pathlib import Path
import subprocess
import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return subprocess.run(
        [sys.executable, "-m", "pytest", *(args or ["tennis_api/tests"])],
        cwd=Path(__file__).resolve().parents[1],
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
