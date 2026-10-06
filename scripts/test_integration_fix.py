#!/usr/bin/env python3
"""Run integration pytest checks and return pytest's exact exit status."""

from pathlib import Path
import subprocess
import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    return subprocess.run(
        [sys.executable, "-m", "pytest", *(args or ["tennis_api/tests/test_api_integration.py"])],
        cwd=Path(__file__).resolve().parents[1],
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
